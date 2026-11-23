# projects/candidates/src/candidates/preprocess/preprocess_candidate_shard.py


import datetime
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import click
import dimorphite_dl
import pyarrow as pa
import pyarrow.parquet as pq
from lynceus_core.cli import NumWorkers
from lynceus_core.io.staged_io import staged_output
from lynceus_core.logging import get_lynceus_logger, wide_log
from lynceus_core.manifest.common import Manifest
from rdkit import rdBase
from rdkit.Chem import AddHs, AllChem, MolFromSmiles, MolToMolBlock

STAGED_OUTPUT_TRANSFERS = 1

RUN_TIME_KEY = "run_time"

MANIFEST_FILE_SUFFIX = ".manifest.json"

CONFORMER_COLUMN = "conformer"

logger = get_lynceus_logger()

# RDKit prints a lot of low-level parsing warnings to stderr by default;
# we handle/report parse failures ourselves, so silence RDKit's own logger.
rdBase.DisableLog("rdApp.*")

MAX_PROTONATION_VARIANTS = 4

EMBED_PARAMS = AllChem.ETKDGv3()
EMBED_PARAMS.randomSeed = 1000
EMBED_PARAMS.maxIterations = 50
EMBED_PARAMS.numThreads = 1

OPTIMIZE_MAX_ITERS = 50

MANIFEST_FILE_SUFFIX = ".manifest.json"
NUM_ROWS_KEY = "num_rows"


def _manifest_path(manifest_dir: Path, output_path: Path) -> Path:
    return manifest_dir / f"{output_path.stem}{MANIFEST_FILE_SUFFIX}"


def _input_manifest(
    input_path: str,
    manifest_path: Path,
    source_root: Path,
    expected_state: dict,
) -> Manifest:
    return Manifest(filepath=manifest_path, data=expected_state).set_source_files(
        [input_path], source_root
    )


def _already_generated(manifest: Manifest, output_path: Path) -> bool:
    return output_path.is_file() and manifest.exists_superset()


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


def _generate_batch_conformers(
    executor: ProcessPoolExecutor, batch: pa.RecordBatch, chunk_size: int
) -> pa.RecordBatch:
    id_smiles_list = list(zip(batch["id"].to_pylist(), batch["smiles"].to_pylist()))

    futures = [
        executor.submit(_process_chunk, chunk)
        for chunk in _chunk_list(id_smiles_list, chunk_size)
    ]

    conformers = []
    for future in futures:
        conformers.extend(future.result())

    return batch.append_column(CONFORMER_COLUMN, pa.array(conformers, type=pa.string()))


def _write_conformer_file(
    input_path: str,
    output_file: Path,
    batch_size: int,
    chunk_size: int,
    num_workers: int,
) -> None:
    parquet_file = pq.ParquetFile(input_path)
    num_rows = parquet_file.metadata.num_rows
    output_schema = parquet_file.schema_arrow.append(
        pa.field(CONFORMER_COLUMN, pa.string())
    )

    with (
        ProcessPoolExecutor(max_workers=num_workers) as executor,
        pq.ParquetWriter(output_file, output_schema) as writer,
    ):
        for i, batch in enumerate(parquet_file.iter_batches(batch_size=batch_size)):
            writer.write_batch(_generate_batch_conformers(executor, batch, chunk_size))

            logger.info(
                "Processed batch",
                batch_index=i + 1,
                processed=min((i + 1) * batch_size, num_rows),
                total_rows=num_rows,
            )


def _generate_via_staged_output(
    input_path: str,
    output_path: Path,
    batch_size: int,
    chunk_size: int,
    num_workers: int,
    scratch_dir: str | None,
) -> None:
    with staged_output(
        output_path.parent,
        transfers=STAGED_OUTPUT_TRANSFERS,
        scratch_dir=scratch_dir,
    ) as local_output:
        _write_conformer_file(
            input_path,
            local_output / output_path.name,
            batch_size,
            chunk_size,
            num_workers,
        )


@click.command("generate_conformers")
@click.option(
    "--source-root",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Directory to base the relative paths on in the manifest.",
)
@click.option(
    "--input",
    "input_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, readable=True),
    help="Path to the input Parquet file.",
)
@click.option(
    "--output",
    "output_path",
    required=True,
    type=click.Path(dir_okay=False, path_type=Path),
)
@click.option(
    "--manifest-dir",
    "manifest_dir",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Directory the shard manifest is written to, named after the output file.",
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
@click.option(
    "--scratch-dir",
    type=str,
    default=None,
    help="Local directory for the conformer file before it is copied to --output "
    "(defaults to the system temp directory).",
)
@wide_log(logger)
def preprocess_candidate_shard(
    source_root: Path,
    input_path: str,
    output_path: Path,
    manifest_dir: Path,
    batch_size: int,
    chunk_size: int,
    num_workers: int,
    scratch_dir: str | None,
) -> None:
    click.echo(f"Processing {input_path}...")

    expected_state = {"batch_size": batch_size, "chunk_size": chunk_size}
    manifest = _input_manifest(
        input_path,
        _manifest_path(manifest_dir, output_path),
        source_root,
        expected_state,
    )

    try:
        if _already_generated(manifest, output_path):
            logger.info("Valid manifest found.", manifest=manifest.data)
            click.echo("Done!")
            return
    except Exception as e:
        logger.warning("Failed to load existing manifest, re-generating.", error=str(e))

    logger.info(
        "Preprocessing",
        source=input_path,
        output_path=output_path,
        source_root=str(source_root),
        workers=num_workers,
        scratch_dir=scratch_dir,
    )

    start_time = time.perf_counter()

    _generate_via_staged_output(
        input_path,
        output_path,
        batch_size,
        chunk_size,
        num_workers,
        scratch_dir,
    )

    elapsed_time = time.perf_counter() - start_time
    manifest.data[RUN_TIME_KEY] = str(datetime.timedelta(seconds=elapsed_time))
    manifest.data[NUM_ROWS_KEY] = pq.ParquetFile(input_path).metadata.num_rows
    manifest.save()

    logger.info("Finished preprocessing", manifest=manifest.data)
    click.echo("Done!")


if __name__ == "__main__":
    preprocess_candidate_shard()
