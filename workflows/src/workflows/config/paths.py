# workflows/src/workflows/config/paths.py


from dataclasses import dataclass
from pathlib import PurePosixPath

from workflows.config.candidates import CandidatesConfig
from workflows.config.screen import ScreenConfig

SCREENS_DIR = PurePosixPath("screens")
TARGETS_DIR = "targets"
TARGET_PDBS_DIR = "pdbs"
TARGET_ENSEMBLES_DIR = "ensembles"
FILTER_DIR = "filter"
SURROGATE_DIR = "surrogate"


def _join(mount_path: str, relative: str) -> str:
    return f"{mount_path}/{relative}"


@dataclass(frozen=True, slots=True)
class SamplePaths:
    mount_path: str
    root: str
    raw: str
    preprocessed: str
    featurized: str


@dataclass(frozen=True, slots=True)
class WorkflowPaths:
    candidates: CandidatesConfig
    screen: ScreenConfig
    mount_path: str

    def volume_path(self, relative: str) -> str:
        return _join(self.mount_path, relative)

    @property
    def screen_root(self) -> PurePosixPath:
        return SCREENS_DIR / self.screen.name

    @property
    def targets_root(self) -> PurePosixPath:
        return self.screen_root / TARGETS_DIR

    @property
    def target_pdbs(self) -> str:
        return str(self.targets_root / TARGET_PDBS_DIR)

    @property
    def target_ensembles(self) -> str:
        return str(self.targets_root / TARGET_ENSEMBLES_DIR)

    @property
    def smiles(self) -> str:
        pool = self.candidates.candidate_pool
        return str(pool.smiles_prefix(self.candidates.root))

    @property
    def staging(self) -> str:
        pool = self.candidates.candidate_pool
        return str(pool.staging_prefix(self.candidates.root))

    @property
    def merged(self) -> str:
        pool = self.candidates.candidate_pool
        return str(pool.merged_prefix(self.candidates.root))

    @property
    def manifests(self) -> str:
        pool = self.candidates.candidate_pool
        return str(pool.manifests_prefix(self.candidates.root))

    @property
    def surrogate(self) -> str:
        return str(self.screen_root / FILTER_DIR / SURROGATE_DIR)

    def state_path(self, filename: str) -> str:
        return self.volume_path(f"{self.manifests}/{filename}")

    def sample(self, name: str) -> SamplePaths:
        sample_root = self.candidates.sample_root(name)
        sample = self.candidates.samples[name]
        return SamplePaths(
            mount_path=self.mount_path,
            root=str(sample_root),
            raw=str(sample.raw_prefix(sample_root)),
            preprocessed=str(sample.preprocessed_prefix(sample_root)),
            featurized=str(sample.featurized_prefix(sample_root)),
        )
