# workflows/src/workflows/config/candidates.py


from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Annotated

from pydantic import AfterValidator, Field, PositiveInt

from workflows.config.common import (
    ConfigSlug,
    StoragePrefix,
    StrictModel,
    load_config,
)
from workflows.config.storage import BasedPrefixGroup, PrefixGroup


class CandidateFeature(StrEnum):
    ATOM_PAIR = "atom_pair"
    AUTOCORR = "autocorr"
    DESCRIPTORS = "descriptors"
    ECFP = "ecfp"
    FUNCTIONAL_GROUPS = "functional_groups"
    MORSE = "morse"
    RDF = "rdf"
    TOPOLOGICAL_TORSION = "topological_torsion"
    USRCAT = "usrcat"
    WHIM = "whim"


def _reject_duplicate_features(
    features: tuple[CandidateFeature, ...],
) -> tuple[CandidateFeature, ...]:
    if len(set(features)) != len(features):
        raise ValueError("feature_types must not contain duplicates")
    return features


FeatureTypes = Annotated[
    tuple[CandidateFeature, ...],
    Field(min_length=1),
    AfterValidator(_reject_duplicate_features),
]


class ShardPrefixes(PrefixGroup):
    staging: StoragePrefix
    merged: StoragePrefix
    manifests: StoragePrefix


class PoolStorage(BasedPrefixGroup):
    smiles: StoragePrefix
    parquet: StoragePrefix
    shards: ShardPrefixes


class SampleStorage(PrefixGroup):
    raw: StoragePrefix
    preprocessed: StoragePrefix
    featurized: StoragePrefix


class ShardingConfig(StrictModel):
    max_batch_gib: PositiveInt
    num_shards: PositiveInt


class CandidatePoolConfig(StrictModel):
    storage: PoolStorage
    sharding: ShardingConfig

    def base_prefix(self, root: PurePosixPath) -> PurePosixPath:
        return root / self.storage.base

    def smiles_prefix(self, root: PurePosixPath) -> PurePosixPath:
        return self.base_prefix(root) / self.storage.smiles

    def parquet_prefix(self, root: PurePosixPath) -> PurePosixPath:
        return self.base_prefix(root) / self.storage.parquet

    def staging_prefix(self, root: PurePosixPath) -> PurePosixPath:
        return self.base_prefix(root) / self.storage.shards.staging

    def merged_prefix(self, root: PurePosixPath) -> PurePosixPath:
        return self.base_prefix(root) / self.storage.shards.merged

    def manifests_prefix(self, root: PurePosixPath) -> PurePosixPath:
        return self.base_prefix(root) / self.storage.shards.manifests


class CandidateSampleConfig(StrictModel):
    num_samples: PositiveInt
    storage: SampleStorage
    feature_types: FeatureTypes

    @property
    def feature_names(self) -> list[str]:
        return sorted(feature.value for feature in self.feature_types)

    def raw_prefix(self, sample_root: PurePosixPath) -> PurePosixPath:
        return sample_root / self.storage.raw

    def preprocessed_prefix(self, sample_root: PurePosixPath) -> PurePosixPath:
        return sample_root / self.storage.preprocessed

    def featurized_prefix(self, sample_root: PurePosixPath) -> PurePosixPath:
        return sample_root / self.storage.featurized


class CandidatesConfig(StrictModel):
    storage: BasedPrefixGroup
    candidate_pool: CandidatePoolConfig
    samples: Mapping[ConfigSlug, CandidateSampleConfig]

    @property
    def root(self) -> PurePosixPath:
        return PurePosixPath(self.storage.base)

    def sample_root(self, name: str) -> PurePosixPath:
        if name not in self.samples:
            raise KeyError(
                f"unknown sample {name!r}, available: {sorted(self.samples)}"
            )
        return self.root / name


def load_candidates_config(path: Path) -> CandidatesConfig:
    return load_config(path, CandidatesConfig)
