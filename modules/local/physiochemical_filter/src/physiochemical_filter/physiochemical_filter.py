# modules/local/physiochemical_filter/src/physiochemical_filter/physiochemical_filter.py

import logging
from pathlib import Path

import click
import duckdb
import pyarrow as pa
import yaml
from lynceus_utils.duckdb import export_parquet, get_connection
from lynceus_utils.storage.blob_storage import get_blob_storage_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _property_filter_expr(name: str, bounds: dict) -> str:
    clauses = []
    if "min" in bounds:
        clauses.append(f"{name} >= {bounds['min']}")
    if "max" in bounds:
        clauses.append(f"{name} <= {bounds['max']}")
    return " AND ".join(clauses) if clauses else "TRUE"


def _apply_pains_filter(
    rel: duckdb.DuckDBPyRelation, pains_cfg: dict
) -> duckdb.DuckDBPyRelation:
    if not pains_cfg.get("enabled", True):
        return rel
    return rel.filter("len(pains) = 0")


def _apply_cns_mpo_filter(
    rel: duckdb.DuckDBPyRelation, cns_mpo_cfg: dict
) -> duckdb.DuckDBPyRelation:
    if not cns_mpo_cfg.get("enabled", False):
        return rel
    min_score = cns_mpo_cfg.get("min_score", 4.0)
    return rel.filter(f"cns_mpo >= {min_score}")


def _apply_property_filters(
    rel: duckdb.DuckDBPyRelation, property_cfg: dict, columns: set[str]
) -> duckdb.DuckDBPyRelation:
    for name, bounds in (property_cfg or {}).items():
        if name not in columns:
            logger.warning(
                "Configured property filter %r not found in input columns — skipping",
                name,
            )
            continue
        rel = rel.filter(_property_filter_expr(name, bounds))
    return rel


def load_config(config_path: Path) -> dict:
    with open(config_path) as fh:
        return yaml.safe_load(fh) or {}


def _apply_all_filters(rel: duckdb.DuckDBPyRelation, config: dict) -> pa.Table:
    columns = set(rel.columns)

    rel = _apply_property_filters(rel, config.get("properties", {}), columns)
    rel = _apply_pains_filter(rel, config.get("pains", {}))
    rel = _apply_cns_mpo_filter(rel, config.get("cns_mpo", {}))

    result = rel.arrow()
    if isinstance(result, pa.RecordBatchReader):
        result = result.read_all()

    return result


@click.command()
@click.option(
    "--input",
    required=True,
    type=str,
    help="Input .parquet file",
)
@click.option(
    "--config",
    required=True,
    type=str,
    help="YAML filter configuration",
)
@click.option(
    "--output",
    "output",
    type=str,
    required=True,
    help="Output Parquet file.",
)
@click.option(
    "--use-blob-storage",
    is_flag=True,
    help="Output Parquet file to blob storage.",
)
@click.option("--bucket", type=str, default="lynceus", help="Output bucket name")
def physiochemical_filter(
    input: str,
    config: str,
    output: str,
    use_blob_storage: bool,
    bucket: str,
) -> None:

    blob_storage_settings = None

    if use_blob_storage:
        blob_storage_settings = get_blob_storage_settings()
        output = f"s3://{bucket}/{output.lstrip('/')}"

    conn = get_connection(blob_storage_settings)

    config = load_config(config)

    con = get_connection()
    rel = con.read_parquet(str(input_path))

    table = _apply_all_filters(rel, config)

    export_parquet(conn, table, output)
