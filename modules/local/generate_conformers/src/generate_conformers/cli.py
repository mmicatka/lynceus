# modules/local/generate_conformers/src/generate_conformers/cli.py

import logging
import sys
from concurrent.futures import ProcessPoolExecutor

import click
import dimorphite_dl
import pyarrow as pa
import pyarrow.parquet as pq
from lynceus_utils.cli import NumWorkers
from lynceus_utils.storage.blob_storage import get_blob_storage_settings
from lynceus_utils.storage.filesystem import get_filesystem
from rdkit import rdBase
from rdkit.Chem import AddHs, AllChem, MolFromSmiles, MolToMolBlock

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)

# RDKit prints a lot of low-level parsing warnings to stderr by default;
# we handle/report parse failures ourselves, so silence RDKit's own logger.
rdBase.DisableLog("rdApp.*")

MAX_PROTONATION_VARIANTS = 4

EMBED_PARAMS = AllChem.ETKDGv3()
EMBED_PARAMS.randomSeed = 1000
EMBED_PARAMS.maxIterations = 50

OPTIMIZE_MAX_ITERS = 50


def _process_chunk(
    smiles_chunk: list[str], max_variants: int = MAX_PROTONATION_VARIANTS
) -> list[str]:
    res = []

    for smiles in smiles_chunk:
        variants = dimorphite_dl.protonate_smiles(
            smiles, validate_output=True, max_variants=max_variants
        )
        target_smiles = variants[0] if variants else smiles

        mol = MolFromSmiles(target_smiles)

        if mol is None:
            res.append("")
            continue

        try:
            mol = AddHs(mol)
        except Exception:
            res.append("")
            continue

        if AllChem.EmbedMolecule(mol, EMBED_PARAMS) != -1:
            if AllChem.MMFFOptimizeMolecule(mol, maxIters=OPTIMIZE_MAX_ITERS) != -1:
                res.append(MolToMolBlock(mol))
                continue

        res.append("")

    return res


def _chunk_list(input_list, size):
    for i in range(0, len(input_list), size):
        yield input_list[i : i + size]


def _output_matches_input_row_count(fs, output: str, expected_rows: int) -> bool:
    try:
        existing_num_rows = pq.ParquetFile(output, filesystem=fs).metadata.num_rows
    except FileNotFoundError:
        return False
    return existing_num_rows == expected_rows


@click.command()
@click.option(
    "--input", type=str, required=True, help="Path to the input Parquet file."
)
@click.option(
    "--output", type=str, required=True, help="Path to the output Parquet file."
)
@click.option(
    "--use-blob-storage",
    is_flag=True,
    help="Read input and write output via blob storage.",
)
@click.option(
    "--bucket", type=str, default="lynceus", help="S3-compatible bucket name."
)
@click.option("--batch-size", default=10_000, type=int, help="Parquet read batch size.")
@click.option(
    "--chunk-size",
    default=25,
    type=int,
    help="Worker chunk size for the conformer process pool.",
)
@click.option(
    "--num-workers",
    default="auto",
    type=NumWorkers(),
    show_default=True,
    help="Number of parallel workers (integer >= 1 or 'auto').",
)
def generate_conformers(
    input: str,
    output: str,
    use_blob_storage: bool,
    bucket: str,
    batch_size: int,
    chunk_size: int,
    num_workers: int,
):
    logger.info("generating conformers for %s", input)

    blob_storage_settings = get_blob_storage_settings() if use_blob_storage else None
    fs = get_filesystem(blob_storage_settings)

    input = f"s3://{bucket}/{input}" if use_blob_storage else input
    output = f"s3://{bucket}/{output}" if use_blob_storage else output

    parquet_file = pq.ParquetFile(input, filesystem=fs)

    num_rows = parquet_file.metadata.num_rows

    if _output_matches_input_row_count(fs, output, num_rows):
        logger.info(
            "%s already exists with %d rows matching input. Skipping.",
            output,
            num_rows,
        )
        return

    writer = None

    logger.info("processed 0 of %d", num_rows)

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        for i, batch in enumerate(parquet_file.iter_batches(batch_size=batch_size)):
            smiles_list = batch["smiles"].to_pylist()

            futures = [
                executor.submit(_process_chunk, chunk)
                for chunk in _chunk_list(smiles_list, chunk_size)
            ]

            conformers = []
            for future in futures:
                conformers.extend(future.result())

            new_batch = batch.append_column(
                "conformer", pa.array(conformers, type=pa.string())
            )

            if writer is None:
                writer = pq.ParquetWriter(output, new_batch.schema, filesystem=fs)

            writer.write_batch(new_batch)
            logger.info("processed %d of %d", (i + 1) * batch_size, num_rows)

    if writer is not None:
        writer.close()
