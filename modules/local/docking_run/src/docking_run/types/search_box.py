# modules/local/docking_run/src/docking_run/types/search_box.py


from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SearchBox:
    center: tuple[float, float, float]
    size: tuple[float, float, float]
