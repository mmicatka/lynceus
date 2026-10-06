# workflows/src/workflows/templates/common.py

from hera.workflows import Resources

from workflows.config.infrastructure import TemplateConfig


def template_resources(template_config: TemplateConfig) -> Resources:
    return Resources(
        cpu_request=template_config.cpu,
        cpu_limit=template_config.cpu,
        memory_request=template_config.memory,
        memory_limit=template_config.memory,
    )
