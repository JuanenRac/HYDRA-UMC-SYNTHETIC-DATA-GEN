# =============================================================================
# HYDRA-UMC-SYNTHETIC-DATA-GEN - src/hydra_umc_synthetic_data_gen/export.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
"""Real YOLO and COCO annotation export from generated Scenes.

Pixel-perfect by construction: bounding boxes come directly from the same
Component coordinates scene.py placed and render.py painted - no detection
model in the loop, so there is nothing to be inaccurate. TFRecord export
(also promised by the README) is future work - it needs a real TensorFlow
dependency this v0 deliberately doesn't take on.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .scene import Scene


@dataclass(frozen=True)
class Dataset:
    """A real, ordered collection of (image filename, Scene) pairs."""

    scenes: tuple[tuple[str, Scene], ...]


def class_names(dataset: Dataset) -> list[str]:
    """Real, stable (sorted) list of every label seen across the dataset."""
    names = {component.label for _, scene in dataset.scenes for component in scene.components}
    return sorted(names)


def export_yolo(dataset: Dataset, out_dir: Path) -> None:
    """Write real YOLO-format labels: one `.txt` per image plus `classes.txt`."""
    labels = class_names(dataset)
    class_index = {name: index for index, name in enumerate(labels)}

    labels_dir = out_dir / "labels"
    labels_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "classes.txt").write_text("\n".join(labels) + "\n", encoding="utf-8")

    for image_name, scene in dataset.scenes:
        lines = []
        for component in scene.components:
            cx = (component.x + component.width / 2) / scene.width
            cy = (component.y + component.height / 2) / scene.height
            w = component.width / scene.width
            h = component.height / scene.height
            lines.append(f"{class_index[component.label]} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
        stem = Path(image_name).stem
        text = "\n".join(lines) + ("\n" if lines else "")
        (labels_dir / f"{stem}.txt").write_text(text, encoding="utf-8")


def export_coco(dataset: Dataset, out_path: Path) -> None:
    """Write a single real COCO-format JSON annotation file for the dataset."""
    labels = class_names(dataset)
    category_id = {name: index + 1 for index, name in enumerate(labels)}

    images = []
    annotations = []
    next_annotation_id = 1

    for image_id, (image_name, scene) in enumerate(dataset.scenes, start=1):
        images.append({"id": image_id, "file_name": image_name, "width": scene.width, "height": scene.height})
        for component in scene.components:
            annotations.append(
                {
                    "id": next_annotation_id,
                    "image_id": image_id,
                    "category_id": category_id[component.label],
                    "bbox": [component.x, component.y, component.width, component.height],
                    "area": component.width * component.height,
                    "iscrowd": 0,
                }
            )
            next_annotation_id += 1

    categories = [{"id": index + 1, "name": name} for index, name in enumerate(labels)]
    payload = {"images": images, "annotations": annotations, "categories": categories}

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
