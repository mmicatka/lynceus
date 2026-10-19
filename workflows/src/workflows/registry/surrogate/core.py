# workflows/src/workflows/registry/surrogate/core.py

from hera.workflows import Workflow

from workflows.config import InfraConfig, ScreenConfig
from workflows.registry.common import get_template_factory, new_workflow


def build_surrogate_sample_workflow(
    infra_config: InfraConfig, screen_config: ScreenConfig
) -> Workflow:
    templates = get_template_factory(infra_config)

    with new_workflow(screen_config.name, "surrogate-sample") as w:
        # for each binding site in binding_sites.json from infra_config.storage.prefixes.target.ensembles/{ for ensemble in  screen_config.targets.ensembles}

        # run this
        # sample_dag = build_surrogate_sample_dag(templates, infra_config, screen_config)

        # with DAG(name=ENTRYPOINT_DAG):
        #     sample_dag(name="surrogate-sample")

        pass

    return w
