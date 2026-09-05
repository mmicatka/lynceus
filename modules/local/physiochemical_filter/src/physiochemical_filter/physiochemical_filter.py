# modules/local/physiochemical_filter/src/physiochemical_filter/physiochemical_filter.py

import logging
from typing import Any

import click
import duckdb
from lynceus_utils.duckdb import export_parquet, get_connection
from lynceus_utils.storage.blob_storage import get_blob_storage_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _property_filter_expr(name: str, bounds: dict[str, float]) -> str:
    clauses = []
    if "min" in bounds and bounds["min"] is not None:
        clauses.append(f"{name} >= {bounds['min']}")
    if "max" in bounds and bounds["max"] is not None:
        clauses.append(f"{name} <= {bounds['max']}")
    return " AND ".join(clauses) if clauses else "TRUE"


def _apply_pains_filter(
    rel: duckdb.DuckDBPyRelation, pains_cfg: dict[str, Any]
) -> duckdb.DuckDBPyRelation:
    if not pains_cfg.get("enabled", False):
        return rel
    return rel.filter("len(pains) = 0")


def _apply_cns_mpo_filter(
    rel: duckdb.DuckDBPyRelation, cns_mpo_cfg: dict[str, Any]
) -> duckdb.DuckDBPyRelation:
    if not cns_mpo_cfg.get("enabled", False):
        return rel
    min_score = cns_mpo_cfg.get("min_score", 4.0)
    return rel.filter(f"cns_mpo >= {min_score}")


def _apply_property_filters(
    rel: duckdb.DuckDBPyRelation,
    property_cfg: dict[str, dict[str, float]],
    columns: set[str],
) -> duckdb.DuckDBPyRelation:
    for name, bounds in (property_cfg or {}).items():
        if not bounds:
            continue
        if name not in columns:
            logger.warning(
                "Configured property filter %r not found in input columns — skipping",
                name,
            )
            continue
        expr = _property_filter_expr(name, bounds)
        if expr != "TRUE":
            rel = rel.filter(expr)
    return rel


def _apply_all_filters(
    rel: duckdb.DuckDBPyRelation, config: dict[str, Any]
) -> duckdb.DuckDBPyRelation:
    columns = set(rel.columns)

    rel = _apply_property_filters(rel, config.get("properties", {}), columns)
    rel = _apply_pains_filter(rel, config.get("pains", {}))
    rel = _apply_cns_mpo_filter(rel, config.get("cns_mpo", {}))

    return rel


def _clean_bounds(min_val: float | None, max_val: float | None) -> dict[str, float]:
    bounds = {}
    if min_val is not None:
        bounds["min"] = min_val
    if max_val is not None:
        bounds["max"] = max_val
    return bounds


@click.command()
@click.option(
    "--input",
    "input_path",
    required=True,
    type=str,
    help="Input .parquet file path.",
)
@click.option(
    "--output",
    "output_path",
    type=str,
    required=True,
    help="Output Parquet file path.",
)
@click.option(
    "--use-blob-storage",
    is_flag=True,
    help="Output Parquet file to blob storage.",
)
@click.option(
    "--bucket", type=str, default="lynceus", help="S3-compatible bucket name."
)
@click.option(
    "--mol-weight-min",
    type=float,
    help="Molecular weight minimum.",
)
@click.option(
    "--mol-weight-max",
    type=float,
    help="Molecular weight maximum.",
)
@click.option(
    "--heavy-atom-min",
    type=int,
    help="Heavy atom count minimum.",
)
@click.option(
    "--heavy-atom-max",
    type=int,
    help="Heavy atom count maximum.",
)
@click.option(
    "--cns-mpo",
    type=float,
    help="CNS-MPO minimum score.",
)
@click.option(
    "--use-pains",
    is_flag=True,
    help="Enable PAINS filter.",
)
def physiochemical_filter(
    input_path: str,
    output_path: str,
    use_blob_storage: bool,
    bucket: str,
    mol_weight_min: float | None,
    mol_weight_max: float | None,
    heavy_atom_min: int | None,
    heavy_atom_max: int | None,
    cns_mpo: float | None,
    use_pains: bool,
) -> None:
    if use_blob_storage:
        blob_storage_settings = get_blob_storage_settings()
        conn = get_connection(blob_storage_settings)
        input_path = f"s3://{bucket}/{input_path.lstrip('/')}"
        output_path = f"s3://{bucket}/{output_path.lstrip('/')}"
    else:
        conn = get_connection()

    config = {
        "properties": {
            "molecular_weight": _clean_bounds(mol_weight_min, mol_weight_max),
            "heavy_atom_count": _clean_bounds(heavy_atom_min, heavy_atom_max),
        },
        "pains": {"enabled": use_pains},
        "cns_mpo": {
            "enabled": cns_mpo is not None,
            "min_score": cns_mpo,
        },
    }

    rel = conn.read_parquet(str(input_path))
    filtered_rel = _apply_all_filters(rel, config)
    export_parquet(conn, filtered_rel, output_path)
