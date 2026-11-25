# workflows/src/workflows/config/paths.py


from dataclasses import dataclass
from pathlib import PurePosixPath

from workflows.config.candidates import CandidatesConfig
from workflows.config.screen import ScreenConfig

ENSEMBLES_DIR = PurePosixPath("ensembles")
VALIDATION_DIR = "validation"
TARGET_PDBS_DIR = "pdbs"
TARGET_STRUCTURES_DIR = "structures"
BINDING_SITES_DIR = "binding_sites"
SURROGATE_DIR = "surrogate"

PLAN_MANIFEST_FILENAME = "plan.manifest.json"
SHARDS_DIR = "shards"
MANIFESTS_DIR = "manifests"


def _join(mount_path: str, relative: str) -> str:
    return f"{mount_path}/{relative}"


@dataclass(frozen=True, slots=True)
class SamplePaths:
    mount_path: str
    root: str
    raw: str
    preprocessed: str
    featurized: str

    @property
    def preprocessed_manifest(self) -> str:
        return f"{self.preprocessed}/{PLAN_MANIFEST_FILENAME}"

    @property
    def preprocessed_shards(self) -> str:
        return f"{self.preprocessed}/{SHARDS_DIR}"

    @property
    def preprocessed_manifests(self) -> str:
        return f"{self.preprocessed}/{MANIFESTS_DIR}"

    @property
    def featurized_manifest(self) -> str:
        return f"{self.featurized}/{PLAN_MANIFEST_FILENAME}"

    @property
    def featurized_shards(self) -> str:
        return f"{self.featurized}/{SHARDS_DIR}"

    @property
    def featurized_manifests(self) -> str:
        return f"{self.featurized}/{MANIFESTS_DIR}"


@dataclass(frozen=True, slots=True)
class WorkflowPaths:
    candidates: CandidatesConfig
    screen: ScreenConfig
    mount_path: str

    def volume_path(self, relative: str) -> str:
        return _join(self.mount_path, relative)

    def ensemble_root(self, ensemble_id: str) -> PurePosixPath:
        return ENSEMBLES_DIR / ensemble_id

    def target_pdbs(self, ensemble_id: str) -> str:
        return str(self.ensemble_root(ensemble_id) / TARGET_PDBS_DIR)

    def target_structures(self, ensemble_id: str) -> str:
        return str(self.ensemble_root(ensemble_id) / TARGET_STRUCTURES_DIR)

    def binding_sites(self, ensemble_id: str) -> str:
        return str(self.ensemble_root(ensemble_id) / BINDING_SITES_DIR)

    @property
    def smiles(self) -> str:
        return str(self.candidates.candidate_pool.smiles_prefix(self.candidates.root))

    @property
    def staging(self) -> str:
        return str(self.candidates.candidate_pool.staging_prefix(self.candidates.root))

    @property
    def merged(self) -> str:
        return str(self.candidates.candidate_pool.merged_prefix(self.candidates.root))

    @property
    def manifests(self) -> str:
        return str(
            self.candidates.candidate_pool.manifests_prefix(self.candidates.root)
        )

    @property
    def ensembles(self) -> str:
        return str(ENSEMBLES_DIR)

    def surrogate(self, ensemble_id: str) -> str:
        return str(self.ensemble_root(ensemble_id) / SURROGATE_DIR)

    def surrogate_site(self, ensemble_id: str, site_id: str) -> PurePosixPath:
        return (
            self.ensemble_root(ensemble_id)
            / SURROGATE_DIR
            / f"site_{site_id}"
            / self.screen.candidates
        )

    def validation_slice(self, ensemble_id: str, site_id: str) -> PurePosixPath:
        val_dirname = self.screen.filter.surrogate.validation.dirname
        return self.surrogate_site(ensemble_id, site_id) / VALIDATION_DIR / val_dirname

    def surrogate_screen(self, ensemble_id: str, site_id: str) -> PurePosixPath:
        return self.surrogate_site(ensemble_id, site_id) / self.screen.name

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
