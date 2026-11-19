# workflows/src/workflows/registry/surrogate/dags/sample.py


import glob
import os
from pathlib import Path
from typing import Any

from hera.workflows import DAG, Parameter, Task

from workflows.config.core import WorkflowConfigs
from workflows.config.paths import SamplePaths
from workflows.registry.common.core import ITEM_PARAM, shard_ids
from workflows.registry.common.manifest_gate import (
    MATCHES_PATH,
    json_arg,
    when_unmatched,
)
from workflows.registry.surrogate.common import SampleSpec, SampleTemplates
from workflows.registry.surrogate.layout import SiteLayout

SHARD_FILENAME_PATTERN = "shard_{shard}.parquet"
SAMPLE_PARAMETERS = ("ensemble", "site_id")

SOURCE_GLOB = "*.parquet"
PLAN_SUFFIX = ".plan.json"
STATE_SUFFIX = ".state.json"

NUM_SHARDS_KEY = "num_shards"
SAMPLED_KEY = "sampled"
MERGED_KEY = "merged"


def _sample_paths(configs: WorkflowConfigs) -> SamplePaths:
    return configs.paths.sample(configs.screen.candidates)


def _num_shards(configs: WorkflowConfigs) -> int:
    return configs.candidates.candidate_pool.sharding.num_shards


def _shard_filename(shard: str) -> str:
    return SHARD_FILENAME_PATTERN.format(shard=shard)


def _plan_path(layout: SiteLayout, spec: SampleSpec) -> str:
    return str(Path(layout.manifest_path(spec.label)).with_suffix(PLAN_SUFFIX))


def _state_path(layout: SiteLayout, spec: SampleSpec) -> str:
    return str(Path(layout.manifest_path(spec.label)).with_suffix(STATE_SUFFIX))


def _model_globs(layout: SiteLayout, spec: SampleSpec) -> list[str]:
    model_path = spec.plan_arguments().get("model_path")
    if not model_path:
        return []
    return [glob.escape(os.path.relpath(model_path, layout.base_path))]


def _source_globs(
    sample_paths: SamplePaths, layout: SiteLayout, spec: SampleSpec
) -> list[str]:
    return [
        f"{sample_paths.featurized}/{SOURCE_GLOB}",
        f"{sample_paths.preprocessed}/{SOURCE_GLOB}",
        *_model_globs(layout, spec),
    ]


def _manifest_fields(configs: WorkflowConfigs, spec: SampleSpec) -> dict[str, Any]:
    num_shards = _num_shards(configs)
    return {NUM_SHARDS_KEY: num_shards, **spec.shard_arguments(num_shards)}


def _plan_task(
    templates: SampleTemplates,
    sample_paths: SamplePaths,
    layout: SiteLayout,
    spec: SampleSpec,
) -> Task:
    return templates.plan(
        name="plan-sources",
        arguments={
            "base_path": layout.base_path,
            "featurized_prefix": sample_paths.featurized_shards,
            "preprocessed_prefix": sample_paths.preprocessed_shards,
            "persist_file": _plan_path(layout, spec),
            **spec.plan_arguments(),
        },
    )


def _check_task(
    templates: SampleTemplates,
    configs: WorkflowConfigs,
    sample_paths: SamplePaths,
    layout: SiteLayout,
    spec: SampleSpec,
    name: str,
    completion_key: str,
) -> Task:
    expected = {**_manifest_fields(configs, spec), completion_key: True}
    return templates.verify_manifest(
        name=name,
        arguments={
            "base_path": layout.base_path,
            "manifest": _state_path(layout, spec),
            "expect": json_arg(expected),
            "source_globs": _source_globs(sample_paths, layout, spec),
            "result_file": MATCHES_PATH,
        },
    )


def _update_manifest_task(
    templates: SampleTemplates,
    layout: SiteLayout,
    spec: SampleSpec,
    name: str,
    source: str,
    fields: dict[str, Any],
    when: str,
) -> Task:
    return templates.update_manifest(
        name=name,
        when=when,
        arguments={
            "base_path": layout.base_path,
            "source": source,
            "output": _state_path(layout, spec),
            "fields": json_arg(fields),
        },
    )


def _sample_shards_task(
    templates: SampleTemplates,
    configs: WorkflowConfigs,
    sample_paths: SamplePaths,
    layout: SiteLayout,
    spec: SampleSpec,
    when: str,
) -> Task:
    num_shards = _num_shards(configs)

    return templates.sample_for(spec)(
        name="sample-shards",
        when=when,
        with_items=shard_ids(num_shards),
        arguments={
            "base_path": layout.base_path,
            "source": _shard_filename(ITEM_PARAM),
            "featurized_input_prefix": sample_paths.featurized,
            "preprocessed_input_prefix": sample_paths.preprocessed,
            "output_prefix": layout.staging_prefix(spec.label),
            **spec.shard_arguments(num_shards),
        },
    )


def _merge_samples_task(
    templates: SampleTemplates,
    layout: SiteLayout,
    spec: SampleSpec,
    when: str,
) -> Task:
    return templates.merge_shards(
        name="merge-samples",
        when=when,
        arguments={
            "base_path": layout.base_path,
            "input_path": layout.staging_prefix(spec.label),
            "output_path": layout.features_file(spec.label),
        },
    )


def build_sample_dag(
    templates: SampleTemplates,
    configs: WorkflowConfigs,
    layout: SiteLayout,
    spec: SampleSpec,
) -> DAG:
    sample_paths = _sample_paths(configs)
    fields = _manifest_fields(configs, spec)

    with DAG(
        name=spec.dag_name,
        inputs=[Parameter(name=name) for name in SAMPLE_PARAMETERS],
    ) as dag:
        plan_task = _plan_task(templates, sample_paths, layout, spec)
        check_sampled = _check_task(
            templates, configs, sample_paths, layout, spec, "check-sampled", SAMPLED_KEY
        )
        check_merged = _check_task(
            templates, configs, sample_paths, layout, spec, "check-merged", MERGED_KEY
        )
        sample_gate = when_unmatched(check_sampled)
        merge_gate = when_unmatched(check_merged)

        sample_task = _sample_shards_task(
            templates, configs, sample_paths, layout, spec, sample_gate
        )
        write_task = _update_manifest_task(
            templates,
            layout,
            spec,
            "write-manifest",
            _plan_path(layout, spec),
            {**fields, SAMPLED_KEY: True},
            sample_gate,
        )
        merge_task = _merge_samples_task(templates, layout, spec, merge_gate)
        mark_task = _update_manifest_task(
            templates,
            layout,
            spec,
            "mark-merged",
            _state_path(layout, spec),
            {MERGED_KEY: True},
            merge_gate,
        )

        plan_task >> [check_sampled, check_merged]  # type: ignore
        check_sampled >> sample_task >> write_task >> merge_task  # type: ignore
        check_merged >> merge_task  # type: ignore
        merge_task >> mark_task  # type: ignore

    return dag
