# modules/local/physiochemical_filter/src/physiochemical_filter.py

import argparse
import json
import logging
from pathlib import Path

import duckdb
import yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _property_filter_expr(name: str, bounds: dict) -> str:
    """Build a single SQL boolean expression for a property range filter."""
    clauses = []
    if "min" in bounds:
        clauses.append(f"{name} >= {bounds['min']}")
    if "max" in bounds:
        clauses.append(f"{name} <= {bounds['max']}")
    return " AND ".join(clauses) if clauses else "TRUE"


def _apply_pains_filter(
    rel: duckdb.DuckDBPyRelation, pains_cfg: dict, report: dict
) -> duckdb.DuckDBPyRelation:
    if not pains_cfg.get("enabled", True):
        return rel
    n_before = rel.count("*").fetchone()[0]
    rel = rel.filter("len(pains_flags) = 0")
    n_after = rel.count("*").fetchone()[0]
    report["fail_reasons"]["pains"] = report["fail_reasons"].get("pains", 0) + (
        n_before - n_after
    )
    return rel


def _apply_cns_mpo_filter(
    rel: duckdb.DuckDBPyRelation, cns_mpo_cfg: dict, report: dict
) -> duckdb.DuckDBPyRelation:
    if not cns_mpo_cfg.get("enabled", False):
        return rel
    min_score = cns_mpo_cfg.get("min_score", 4.0)
    n_before = rel.count("*").fetchone()[0]
    rel = rel.filter(f"cns_mpo_score >= {min_score}")
    n_after = rel.count("*").fetchone()[0]
    report["fail_reasons"]["cns_mpo"] = report["fail_reasons"].get("cns_mpo", 0) + (
        n_before - n_after
    )
    return rel


def _apply_property_filters(
    rel: duckdb.DuckDBPyRelation, property_cfg: dict, columns: set[str], report: dict
) -> duckdb.DuckDBPyRelation:
    for name, bounds in (property_cfg or {}).items():
        if name not in columns:
            logger.warning(
                "Configured property filter %r not found in input columns — skipping",
                name,
            )
            continue
        n_before = rel.count("*").fetchone()[0]
        rel = rel.filter(_property_filter_expr(name, bounds))
        n_after = rel.count("*").fetchone()[0]
        report["fail_reasons"][name] = report["fail_reasons"].get(name, 0) + (
            n_before - n_after
        )
    return rel


def _write_partitions(
    rel: duckdb.DuckDBPyRelation,
    n_rows: int,
    output_dir: Path,
    prefix: str,
    partition_size: int,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    n_partitions = max(1, (n_rows + partition_size - 1) // partition_size)
    width = max(5, len(str(n_partitions)))

    written = []
    for i in range(n_partitions):
        offset = i * partition_size
        chunk = rel.limit(partition_size, offset=offset)
        out_path = output_dir / f"{prefix}-{i:0{width}d}.parquet"
        chunk.write_parquet(str(out_path))
        written.append(out_path)

    return written


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--input",
        required=True,
        nargs="+",
        type=Path,
        help="One or more input .parquet files",
    )
    p.add_argument(
        "--config", required=True, type=Path, help="YAML filter configuration"
    )
    p.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Directory to write partitioned output parquet files",
    )
    p.add_argument(
        "--output-prefix",
        default="candidates_filtered",
        help="Filename prefix for output partitions",
    )
    p.add_argument(
        "--partition-size",
        required=True,
        type=int,
        help="Max rows per output partition file",
    )
    p.add_argument(
        "--report",
        required=True,
        type=Path,
        help="Path to write a JSON filter-attrition report",
    )
    return p.parse_args()


def main():
    args = parse_args()

    with open(args.config) as fh:
        config = yaml.safe_load(fh) or {}

    property_cfg = config.get("properties", {})
    pains_cfg = config.get("pains", {})
    cns_mpo_cfg = config.get("cns_mpo", {})

    logger.info(
        "Reading %d input parquet file(s) as a combined dataset", len(args.input)
    )
    rel = duckdb.read_parquet([str(p) for p in args.input])
    columns = set(rel.columns)

    report = {"n_input": rel.count("*").fetchone()[0], "fail_reasons": {}}

    rel = _apply_property_filters(rel, property_cfg, columns, report)
    rel = _apply_pains_filter(rel, pains_cfg, report)
    rel = _apply_cns_mpo_filter(rel, cns_mpo_cfg, report)

    n_pass = rel.count("*").fetchone()[0]
    report["n_pass"] = n_pass
    report["n_fail"] = report["n_input"] - n_pass

    logger.info(
        "Filtered %d -> %d rows (%d failed); writing partitions of up to %d rows",
        report["n_input"],
        report["n_pass"],
        report["n_fail"],
        args.partition_size,
    )

    written = _write_partitions(
        rel, n_pass, args.output_dir, args.output_prefix, args.partition_size
    )
    report["n_partitions"] = len(written)

    with open(args.report, "w") as fh:
        json.dump(report, fh, indent=2)

    logger.info("Wrote %d partition file(s) to %s", len(written), args.output_dir)


if __name__ == "__main__":
    main()
