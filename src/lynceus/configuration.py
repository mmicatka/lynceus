# src/lynceus/configuration/discovery.py

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import dagster as dg
import yaml

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LynceusConfig:
    name: str
    path: Path
    run_config: dg.RunConfig


SECTION_TO_OPS: dict[str, tuple[str, ...]] = {
    "candidate": ("retrieve_candidates",),
    "target": ("retrieve_targets",),
}


def _sections_to_op_config(raw_config: dict) -> dict[str, dict]:
    values_by_op: dict[str, dict] = {}
    for section, values in raw_config.items():
        for op_name in SECTION_TO_OPS.get(section, ()):
            values_by_op[op_name] = values
    return values_by_op


def _load_yaml(path: Path) -> dict | None:
    with path.open() as f:
        loaded = yaml.safe_load(f)

    if not loaded:
        logger.warning(f"Config file {path.name} is empty or invalid, skipping.")
        return None

    logger.debug(f"Loaded config: {path.stem}")
    return loaded


def _build_run_config(raw_config: dict) -> dg.RunConfig:
    values_by_op = _sections_to_op_config(raw_config)
    return dg.RunConfig(ops={op: {"config": v} for op, v in values_by_op.items()})


def load_configs(
    configs_dir: Path,
    *,
    pattern: str = "*.yaml",
) -> list[LynceusConfig]:
    if not configs_dir.is_dir():
        raise FileNotFoundError(f"Config directory not found: {configs_dir}")

    configs = []
    for path in sorted(configs_dir.glob(pattern)):
        loaded = _load_yaml(path)
        if loaded is None:
            continue

        run_config = _build_run_config(loaded)
        configs.append(LynceusConfig(name=path.stem, path=path, run_config=run_config))

    if not configs:
        logger.warning(
            f"No configs found in {configs_dir} matching pattern '{pattern}'"
        )
    else:
        logger.info(f"Discovered {len(configs)} config(s) from {configs_dir}")

    return configs
