# modules/local/generate_docking_boxes/src/generate_docking_boxes/generate_docking_boxes.py
from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sites-json", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def sphere_to_box(site: dict) -> dict:
    extent = site["extent"]
    kind = extent.get("kind")

    if kind != "sphere":
        msg = (
            f"Binding site {site.get('site_id', '<unknown>')!r} has extent.kind "
            f"{kind!r}; only 'sphere' is currently supported for box conversion."
        )
        raise NotImplementedError(msg)

    center_x, center_y, center_z = extent["center"]
    diameter = 2.0 * extent["radius"]

    return {
        "site_id": site["site_id"],
        "conformational_state_id": site["conformational_state_id"],
        "center_x": center_x,
        "center_y": center_y,
        "center_z": center_z,
        "size_x": diameter,
        "size_y": diameter,
        "size_z": diameter,
        "pocket_score": site.get("pocket_score"),
    }


def main() -> None:
    args = parse_args()

    sites = json.loads(args.sites_json.read_text())
    boxes = [sphere_to_box(site) for site in sites]

    conformational_state_id = sites[0]["conformational_state_id"] if sites else "empty"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / f"{conformational_state_id}.boxes.json"
    output_path.write_text(json.dumps(boxes, indent=2))


if __name__ == "__main__":
    main()
