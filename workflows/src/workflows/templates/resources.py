# workflows/src/workflows/templates/common.py

from hera.workflows import Resources

from workflows.config.infrastructure import TemplateConfig


def template_resources(template_config: TemplateConfig) -> Resources:
    return Resources(
        cpu_request=template_config.requests.cpu,
        memory_request=template_config.requests.memory,
        cpu_limit=template_config.limits.cpu,
        memory_limit=template_config.limits.memory,
    )
