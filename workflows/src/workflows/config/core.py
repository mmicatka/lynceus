# workflows/src/workflows/config/core.py


from dataclasses import dataclass
from pathlib import Path
from typing import Self

from workflows.config.candidates import CandidatesConfig, load_candidates_config
from workflows.config.paths import WorkflowPaths
from workflows.config.screen import ScreenConfig, load_screen_config
from workflows.config.templates import TemplatesConfig, load_templates_config


@dataclass(frozen=True, slots=True)
class WorkflowConfigs:
    candidates: CandidatesConfig
    templates: TemplatesConfig
    screen: ScreenConfig
    priority: int | None = None
    pod_priority_class_name: str | None = None

    @property
    def paths(self) -> WorkflowPaths:
        return WorkflowPaths(
            self.candidates,
            self.screen,
            self.templates.volume.mount_path,
        )

    @classmethod
    def load(
        cls,
        *,
        candidates_path: Path,
        templates_path: Path,
        screen_path: Path,
        priority: int | None = None,
        pod_priority_class_name: str | None = None,
    ) -> Self:
        candidates = load_candidates_config(candidates_path)
        templates = load_templates_config(templates_path)
        screen = load_screen_config(screen_path, candidates)
        return cls(
            candidates=candidates,
            templates=templates,
            screen=screen,
            priority=priority,
            pod_priority_class_name=pod_priority_class_name,
        )
