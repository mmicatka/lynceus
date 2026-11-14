# projects/candidates/src/candidates/load/common.py


from dataclasses import dataclass
from pathlib import Path

ID_PLACEHOLDER = "{id}"


@dataclass(frozen=True)
class ShardLayout:
    num_shards: int
    filename_template: str
    folder_prefix: str
    shards_dir: Path
    staging_dir: Path

    def __post_init__(self) -> None:
        if ID_PLACEHOLDER not in self.filename_template:
            raise ValueError(
                f"filename template {self.filename_template!r} "
                f"must contain {ID_PLACEHOLDER}"
            )

    @property
    def filename_glob(self) -> str:
        return self.filename_template.replace(ID_PLACEHOLDER, "*")

    @property
    def expected_filenames(self) -> frozenset[str]:
        return frozenset(
            self.filename_template.replace(ID_PLACEHOLDER, str(shard_id))
            for shard_id in range(self.num_shards)
        )

    @property
    def staging_folder_names(self) -> list[str]:
        return [
            f"{self.folder_prefix}{shard_id}" for shard_id in range(self.num_shards)
        ]


def unexpected_final_shards(layout: ShardLayout) -> list[str]:
    found = {path.name for path in layout.shards_dir.glob(layout.filename_glob)}
    return sorted(found - layout.expected_filenames)


def missing_final_shards(layout: ShardLayout) -> list[str]:
    return sorted(
        name
        for name in layout.expected_filenames
        if not (layout.shards_dir / name).is_file()
    )


def missing_staging_folders(layout: ShardLayout) -> list[str]:
    return [
        name
        for name in layout.staging_folder_names
        if not (layout.staging_dir / name).is_dir()
    ]


def leftover_staging_files(layout: ShardLayout) -> list[str]:
    pattern = f"{layout.folder_prefix}*/**/*"
    return sorted(
        str(path.relative_to(layout.staging_dir))
        for path in layout.staging_dir.glob(pattern)
        if path.is_file()
    )
