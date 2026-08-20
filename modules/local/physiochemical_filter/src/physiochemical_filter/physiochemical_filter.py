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
    rel = rel.filter(f"cns_mpo >= {min_score}")
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


def _parse_args() -> argparse.Namespace:
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
        "--output",
        required=True,
        type=Path,
        help="Path to write the single output parquet file",
    )
    p.add_argument(
        "--report",
        required=True,
        type=Path,
        help="Path to write a JSON filter-attrition report",
    )
    return p.parse_args()


def load_config(config_path: Path) -> dict:
    with open(config_path) as fh:
        return yaml.safe_load(fh) or {}


def apply_all_filters(
    rel: duckdb.DuckDBPyRelation, config: dict, report: dict
) -> duckdb.DuckDBPyRelation:
    columns = set(rel.columns)

    rel = _apply_property_filters(rel, config.get("properties", {}), columns, report)
    rel = _apply_pains_filter(rel, config.get("pains", {}), report)
    rel = _apply_cns_mpo_filter(rel, config.get("cns_mpo", {}), report)

    return rel


def save_outputs(
    rel: duckdb.DuckDBPyRelation, report: dict, output_path: Path, report_path: Path
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rel.write_parquet(str(output_path))
    logger.info("Wrote output file to %s", output_path)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as fh:
        json.dump(report, fh, indent=2)


def physiochemical_filter():
    args = _parse_args()
    config = load_config(args.config)

    logger.info(
        "Reading %d input parquet file(s) as a combined dataset", len(args.input)
    )
    rel = duckdb.read_parquet([str(p) for p in args.input])

    report = {"n_input": rel.count("*").fetchone()[0], "fail_reasons": {}}

    rel = apply_all_filters(rel, config, report)

    report["n_pass"] = rel.count("*").fetchone()[0]
    report["n_fail"] = report["n_input"] - report["n_pass"]

    logger.info(
        "Filtered %d -> %d rows (%d failed)",
        report["n_input"],
        report["n_pass"],
        report["n_fail"],
    )

    save_outputs(rel, report, args.output, args.report)
