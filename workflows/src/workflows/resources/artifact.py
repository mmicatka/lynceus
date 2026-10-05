# workflows/src/workflows/utils/artifact.py

from dataclasses import dataclass

from hera.workflows import ArchiveStrategy, Artifact, NoneArchiveStrategy


@dataclass(frozen=True)
class ArtifactSpec:
    name: str
    path: str

    def output(self, archive: ArchiveStrategy | None = None) -> Artifact:
        return Artifact(
            name=self.name,
            path=self.path,
            archive=archive if archive is not None else NoneArchiveStrategy(),
        )

    def input(self) -> Artifact:
        return Artifact(name=self.name, path=self.path)
