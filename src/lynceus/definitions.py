# src/lynceus/definitions.py

from pathlib import Path

import dagster as dg

from lynceus.candidate import CANDIDATE_ASSETS
from lynceus.configuration import load_configs


REPO_ROOT = Path(__file__).parent.parent.parent
CONFIGS_DIR = REPO_ROOT / "configs"

ASSETS = [_asset for _assets in [CANDIDATE_ASSETS] for _asset in _assets]

BASE_JOB_NAME = "full_pipeline_job"


def _build_job_variants(configs_dir: Path) -> list[dg.JobDefinition]:
    return [
        dg.define_asset_job(
            name=f"{BASE_JOB_NAME}_{config.name}",
            selection=ASSETS,
            config=config.run_config,
            description=f"Full pipeline job using config from {config.path.name}",
        )
        for config in load_configs(configs_dir)
    ]


defs = dg.Definitions(
    assets=ASSETS,
    jobs=_build_job_variants(CONFIGS_DIR),
)
