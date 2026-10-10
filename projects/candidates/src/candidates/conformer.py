# projects/candidates/src/candidates/processing/conformer.py


import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import click
import dimorphite_dl
import pyarrow as pa
import pyarrow.parquet as pq
import structlog
from lynceus_core.cli import NumWorkers
from lynceus_core.logging import wide_log
from rdkit import rdBase
from rdkit.Chem import AddHs, AllChem, MolFromSmiles, MolToMolBlock


def configure_logging():
    if sys.stdout.isatty():
        processor = structlog.dev.ConsoleRenderer(colors=True)
    else:
        processor = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            processor,
        ]
    )


configure_logging()
logger = structlog.get_logger()

# RDKit prints a lot of low-level parsing warnings to stderr by default;
# we handle/report parse failures ourselves, so silence RDKit's own logger.
rdBase.DisableLog("rdApp.*")

MAX_PROTONATION_VARIANTS = 4

EMBED_PARAMS = AllChem.ETKDGv3()
EMBED_PARAMS.randomSeed = 1000
EMBED_PARAMS.maxIterations = 50
EMBED_PARAMS.numThreads = 1

OPTIMIZE_MAX_ITERS = 50


def _process_chunk(
    smiles_chunk: list[tuple[str, str]], max_variants: int = MAX_PROTONATION_VARIANTS
) -> list[str]:
    res = []

    for id, smiles in smiles_chunk:
        variants = dimorphite_dl.protonate_smiles(
            smiles, validate_output=True, max_variants=max_variants
        )
        target_smiles = variants[0] if variants else smiles

        _mol = MolFromSmiles(target_smiles)

        if _mol is None:
            res.append("")
            continue

        try:
            _mol = AddHs(_mol)
        except Exception:
            res.append("")
            continue

        if AllChem.EmbedMolecule(_mol, EMBED_PARAMS) != -1:
            if AllChem.MMFFOptimizeMolecule(_mol, maxIters=OPTIMIZE_MAX_ITERS) != -1:
                _mol.SetIntProp("conf_id", 0)
                _mol.SetProp("_Name", str(id))

                res.append(MolToMolBlock(_mol))
                continue

        res.append("")

    return res


def _chunk_list(input_list, size):
    for i in range(0, len(input_list), size):
        yield input_list[i : i + size]


def _marker_path(output_path: str, identifier: str) -> str:
    base_dir = os.path.dirname(output_path)
    return os.path.join(base_dir, f"_SUCCESS_{identifier}")


def _state_is_valid(output_path: str, num_rows: int, identifier: str) -> bool:
    marker_path = _marker_path(output_path, identifier)
    if not os.path.exists(marker_path):
        return False
    try:
        with open(marker_path, "r") as f:
            data = json.load(f)
            return data.get("num_rows") == num_rows
    except Exception:
        return False


def _write_success_marker(output_path: str, num_rows: int, identifier: str) -> None:
    marker_path = _marker_path(output_path, identifier)
    os.makedirs(os.path.dirname(marker_path), exist_ok=True)
    with open(marker_path, "w") as f:
        json.dump({"num_rows": num_rows}, f)


@click.command("generate_conformers")
@click.option(
    "--input",
    "input_path",
    type=str,
    required=True,
    help="Path to the input Parquet file.",
)
@click.option(
    "--output",
    "output_path",
    type=str,
    required=True,
    help="Path to the output Parquet file.",
)
@click.option(
    "--batch-size",
    "batch_size",
    default=10_000,
    type=click.IntRange(min=1),
    show_default=True,
    help="Parquet read batch size.",
)
@click.option(
    "--chunk-size",
    "chunk_size",
    default=25,
    type=click.IntRange(min=1),
    show_default=True,
    help="Worker chunk size for the conformer process pool.",
)
@click.option(
    "--num-workers",
    "num_workers",
    default="auto",
    type=NumWorkers(),
    show_default=True,
    help="Number of parallel workers (integer >= 1 or 'auto').",
)
@wide_log(logger)
def generate_conformers(
    input_path: str,
    output_path: str,
    batch_size: int,
    chunk_size: int,
    num_workers: int,
):
    click.echo(f"Processing {input_path}...")

    if not os.path.isfile(input_path):
        raise RuntimeError(f"Input file not found: {input_path}")

    identifier = os.path.basename(input_path).replace(".parquet", "")

    parquet_file = pq.ParquetFile(input_path)
    num_rows = parquet_file.metadata.num_rows

    if _state_is_valid(output_path, num_rows, identifier):
        logger.info(
            "Conformers already valid, skipping generation",
            file=identifier,
            num_rows=num_rows,
            output_path=output_path,
        )
        click.echo("Done!")
        return

    logger.info(
        "Generating conformers",
        source=input_path,
        output_path=output_path,
        num_rows=num_rows,
        workers=num_workers,
    )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    writer = None

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        for i, batch in enumerate(parquet_file.iter_batches(batch_size=batch_size)):
            id_list = batch["id"].to_pylist()
            smiles_list = batch["smiles"].to_pylist()

            id_smiles_list = list(zip(id_list, smiles_list))

            futures = [
                executor.submit(_process_chunk, chunk)
                for chunk in _chunk_list(id_smiles_list, chunk_size)
            ]

            conformers = []
            for future in futures:
                conformers.extend(future.result())

            new_batch = batch.append_column(
                "conformer", pa.array(conformers, type=pa.string())
            )

            if writer is None:
                writer = pq.ParquetWriter(output_path, new_batch.schema)

            writer.write_batch(new_batch)

            logger.info(
                "Processed batch",
                batch_index=i + 1,
                processed=(i + 1) * batch_size,
                total_rows=num_rows,
            )

    if writer is not None:
        writer.close()

    _write_success_marker(output_path, num_rows, identifier)

    logger.info(
        "Finished generating conformers",
        file=identifier,
        num_rows=num_rows,
        output_path=output_path,
    )
    click.echo("Done!")


if __name__ == "__main__":
    generate_conformers()
