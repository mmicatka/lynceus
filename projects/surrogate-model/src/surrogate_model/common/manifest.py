# projects/surrogate-model/src/surrogate_model/common/manifest.py


from pathlib import Path

from lynceus_core.logging import get_lynceus_logger
from lynceus_core.manifest.common import Manifest

MANIFEST_FILE_SUFFIX = ".manifest.json"

logger = get_lynceus_logger()


def input_manifest(
    input_files: list[str],
    output_path: str,
    source_root: Path,
    expected_state: dict,
) -> Manifest:
    manifest_path = Path(output_path).with_suffix(MANIFEST_FILE_SUFFIX)
    return Manifest(filepath=manifest_path, data=expected_state).set_source_files(
        input_files, source_root
    )


def is_up_to_date(manifest: Manifest, output_path: str) -> bool:
    try:
        return Path(output_path).is_file() and manifest.exists_superset()
    except Exception as error:
        logger.warning(
            "Failed to load existing manifest, re-generating.", error=str(error)
        )
        return False
