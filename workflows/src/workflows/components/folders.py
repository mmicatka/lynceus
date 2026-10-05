# workflows/src/workflows/components/folders.py

from hera.workflows import script

from workflows.resources import LYNCEUS_VOLUME

FOLDERS_PARAMETER = "folders"
FOLDERS_OUTPUT_PATH = "/tmp/folders.json"


@script(volumes=[LYNCEUS_VOLUME])
def list_folders(root: str, prefix: str = ""):
    import json
    from pathlib import Path

    folders = sorted(
        entry.name
        for entry in Path(root).iterdir()
        if entry.is_dir() and entry.name.startswith(prefix)
    )
    Path(FOLDERS_OUTPUT_PATH).write_text(json.dumps(folders))
