# projects/candidates/src/candidates/processing/conformer.py

import datetime
import json
import os
import time
from collections import deque
from concurrent.futures import ProcessPoolExecutor

import click
import dimorphite_dl
import pyarrow as pa
import pyarrow.parquet as pq
from lynceus_core.cli import NumWorkers
from lynceus_core.logging import get_lynceus_logger, wide_log
from rdkit import rdBase
from rdkit.Chem import AddHs, AllChem, MolFromSmiles, MolToMolBlock

logger = get_lynceus_logger()

# RDKit prints a lot of low-level parsing warnings to stderr by default;
# we handle/report parse failures ourselves, so silence RDKit's own logger.
rdBase.DisableLog("rdApp.*")

MAX_PROTONATION_VARIANTS = 1

EMBED_PARAMS = AllChem.ETKDGv3()
EMBED_PARAMS.randomSeed = 1000
EMBED_PARAMS.useRandomCoords = False
EMBED_PARAMS.maxIterations = 10
EMBED_PARAMS.numThreads = 1
EMBED_PARAMS.clearConfs = True
EMBED_PARAMS.enforceChirality = True


class Manifest:
    def __init__(self, data: dict, filepath: str):
        self.data = data
        self.filepath = filepath

    def exists_superset(self) -> bool:
        if not os.path.exists(self.filepath):
            return False
        try:
            with open(self.filepath, "r") as f:
                saved_data = json.load(f)
            for key, value in self.data.items():
                if saved_data.get(key) != value:
                    return False
            return True
        except Exception:
            return False

    def save(self):
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        with open(self.filepath, "w") as f:
            json.dump(self.data, f, indent=2)


def _process_chunk(
    smiles_chunk: list[tuple[str, str]],
    max_variants: int = MAX_PROTONATION_VARIANTS,
) -> list[str]:
    res = []

    for id, smiles in smiles_chunk:
        variants = dimorphite_dl.protonate_smiles(
            smiles, validate_output=False, max_variants=max_variants
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
            _mol.SetIntProp("conf_id", 0)
            _mol.SetProp("_Name", str(id))
            res.append(MolToMolBlock(_mol))
        else:
            res.append("")

    return res


def _chunk_list(input_list, size):
    for i in range(0, len(input_list), size):
        yield input_list[i : i + size]


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
    default=100,  # OPTIMIZATION: Increased from 25 to reduce IPC overhead
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

    manifest_data = {
        "input_path": input_path,
        "output_path": output_path,
        "num_rows": num_rows,
        "batch_size": batch_size,
        "chunk_size": chunk_size,
    }

    manifest_path = f"{output_path.rstrip('/')}.manifest.json"
    manifest = Manifest(data=manifest_data, filepath=manifest_path)

    try:
        if manifest.exists_superset():
            logger.info(
                "Valid manifest found.",
                manifest=manifest.data,
            )
            click.echo("Done!")
            return
    except Exception as e:
        logger.warning("Failed to load existing manifest, re-generating.", error=str(e))

    logger.info(
        "Generating conformers",
        source=input_path,
        output_path=output_path,
        num_rows=num_rows,
        workers=num_workers,
    )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    writer = None

    start_time = time.perf_counter()

    pending_batches = deque()
    MAX_IN_FLIGHT = 3

    def flush_oldest_batch(current_writer):
        old_batch, old_futures, batch_idx = pending_batches.popleft()

        conformers = []
        for future in old_futures:
            conformers.extend(future.result())

        new_batch = old_batch.append_column(
            "conformer", pa.array(conformers, type=pa.string())
        )

        if current_writer is None:
            current_writer = pq.ParquetWriter(output_path, new_batch.schema)

        current_writer.write_batch(new_batch)

        logger.info(
            "Processed batch",
            batch_index=batch_idx + 1,
            processed=min((batch_idx + 1) * batch_size, num_rows),
            total_rows=num_rows,
        )
        return current_writer

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        for i, batch in enumerate(parquet_file.iter_batches(batch_size=batch_size)):
            id_list = batch["id"].to_pylist()
            smiles_list = batch["smiles"].to_pylist()

            id_smiles_list = list(zip(id_list, smiles_list))

            futures = [
                executor.submit(_process_chunk, chunk, MAX_PROTONATION_VARIANTS)
                for chunk in _chunk_list(id_smiles_list, chunk_size)
            ]

            pending_batches.append((batch, futures, i))

            if len(pending_batches) >= MAX_IN_FLIGHT:
                writer = flush_oldest_batch(writer)

        while pending_batches:
            writer = flush_oldest_batch(writer)

    if writer is not None:
        writer.close()

    elapsed_time = time.perf_counter() - start_time
    manifest.data["run_time"] = str(datetime.timedelta(seconds=elapsed_time))
    manifest.save()

    logger.info(
        "Finished generating conformers",
        file=identifier,
        num_rows=num_rows,
        output_path=output_path,
        run_time=str(datetime.timedelta(seconds=elapsed_time)),
    )
    click.echo("Done!")


if __name__ == "__main__":
    generate_conformers()
