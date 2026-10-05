# workflows/src/workflows/templates/folders.py


from hera.workflows import RetryStrategy, script

from workflows.utils import LYNCEUS_VOLUME


@script(volumes=[LYNCEUS_VOLUME])
def list_folders(root: str, prefix: str = ""):
    import json
    from pathlib import Path

    folders = sorted(
        entry.name
        for entry in Path(root).iterdir()
        if entry.is_dir() and entry.name.startswith(prefix)
    )
    Path("/tmp/folders.json").write_text(json.dumps(folders))


@script(volumes=[LYNCEUS_VOLUME], retry_strategy=RetryStrategy(limit=2))
def process_folder(root: str, folder: str):
    from pathlib import Path

    files = [path for path in (Path(root) / folder).iterdir() if path.is_file()]
    print(f"{folder}: {len(files)} files")
