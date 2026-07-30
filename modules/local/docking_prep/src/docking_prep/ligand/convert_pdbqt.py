# modules/local/docking_prep/src/docking_prep/ligand/convert_pdbqt.py

import argparse
import io
import logging
import sys
import zlib
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from meeko import MoleculePreparation, PDBQTWriterLegacy
from rdkit import Chem, RDLogger

# RDKit prints a lot of low-level parsing warnings to stderr by default;
# we handle/report parse failures ourselves, so silence RDKit's own logger.
RDLogger.DisableLog("rdApp.*")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


def _convert_sdf_to_pdbqt(sdf_bytes: bytes) -> tuple[bytes | None, str]:
    supplier = Chem.ForwardSDMolSupplier(io.BytesIO(sdf_bytes), removeHs=False)
    mol = next(supplier, None)
    if mol is None:
        return None, "SDF_PARSE_FAILED"

    try:
        prep = MoleculePreparation()
        mol_setups = prep.prepare(mol)
        pdbqt_string, is_ok, error_msg = PDBQTWriterLegacy.write_string(mol_setups[0])
        if not is_ok:
            return None, f"MEEKO_CONVERSION_FAILED: {error_msg}"
    except Exception as exc:
        return None, f"MEEKO_CONVERSION_EXCEPTION: {exc}"

    return pdbqt_string.encode(), "SUCCESS"


def _convert_pdbqt(input: Path, output: Path, num_shards: int, batch_size: int = 5000):
    input_pq = pq.ParquetFile(input)
    schema = input_pq.schema.to_arrow_schema()
    schema = schema.append(pa.field("conversion_error", pa.string()))

    # Prepare output directories
    output.mkdir(parents=True, exist_ok=True)
    out_partitions_dir = output / "partitions"
    for i in range(num_shards):
        (out_partitions_dir / str(i)).mkdir(parents=True, exist_ok=True)

    # Infer input partitions directory relative to the input parquet file
    in_partitions_dir = input.parent / "partitions"

    with pq.ParquetWriter(output / "output.parquet", schema) as writer:
        for batch_idx, batch in enumerate(input_pq.iter_batches(batch_size=batch_size)):
            logger.info(f"Processing batch {batch_idx + 1}...")
            processed_records = []

            for row in batch.to_pylist():
                cat_key = next(
                    (
                        k
                        for k in row.keys()
                        if k.lower() in ("catalog_id", "candidate_id", "id")
                    ),
                    "catalog_id",
                )
                catalog_id = row.get(cat_key)

                conversion_error = "SUCCESS"

                if catalog_id is None:
                    conversion_error = "NO_CATALOG_ID"
                else:
                    # Sharding logic matches conformer_generate.py
                    try:
                        shard = int(catalog_id) % num_shards
                    except (ValueError, TypeError):
                        shard = zlib.crc32(str(catalog_id).encode()) % num_shards

                    sdf_path = in_partitions_dir / str(shard) / f"{catalog_id}.sdf"
                    pdbqt_path = out_partitions_dir / str(shard) / f"{catalog_id}.pdbqt"

                    if not sdf_path.exists():
                        conversion_error = "SDF_NOT_FOUND"
                    else:
                        sdf_bytes = sdf_path.read_bytes()
                        pdbqt_bytes, error_msg = _convert_sdf_to_pdbqt(sdf_bytes)

                        if pdbqt_bytes:
                            pdbqt_path.write_bytes(pdbqt_bytes)
                            conversion_error = "SUCCESS"
                        else:
                            conversion_error = error_msg

                row["conversion_error"] = conversion_error
                processed_records.append(row)

            # Write updated batch
            out_batch = pa.RecordBatch.from_pylist(processed_records, schema=schema)
            writer.write_batch(out_batch)

    logger.info("Conversion complete.")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Generate ranked, deduplicated multi-conformer PDBQT sets per "
            "candidate from a Parquet file of SMILES, packaged as an LMDB "
            "keyed by candidate id."
        )
    )
    p.add_argument("--input", required=True, type=Path, help="Input Parquet file.")
    p.add_argument("--output", required=True, type=Path, help="Output directory.")
    p.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging.")
    p.add_argument("--num_shards", type=int, default=10, help="Number of shards.")
    return p.parse_args()


def convert_pdbqt():
    args = _parse_args()
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    _convert_pdbqt(
        input=args.input,
        output=args.output,
        num_shards=args.num_shards,
    )
