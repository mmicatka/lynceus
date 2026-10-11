# workflows/src/workflows/templates/config.py


from typing import Optional

from hera.workflows import ExistingVolume, Resources, RetryStrategy

from workflows.config.base import StrictModel


class ImageConfig(StrictModel):
    image: str
    image_pull_policy: str = "always"


class TemplateConfig(StrictModel):
    image_config: ImageConfig
    resources: Resources
    volumes: list[ExistingVolume]
    retry_strategy: Optional[RetryStrategy]
