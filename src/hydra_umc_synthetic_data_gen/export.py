# =============================================================================
# HYDRA-UMC-SYNTHETIC-DATA-GEN - src/hydra_umc_synthetic_data_gen/export.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
"""Real YOLO and COCO annotation export from generated Scenes.

Bounding boxes come directly from the same Component coordinates scene.py
placed and render.py painted - no detection model in the loop. An object is
only labelled while at least a third of it is still visible, and a scratch is
boxed by the pixels it really paints. TFRecord export
(also promised by the README) is future work - it needs a real TensorFlow
dependency this v0 deliberately doesn't take on.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .scene import FIXED_CLASSES, Scene


@dataclass(frozen=True)
class Dataset:
    """A real, ordered collection of (image filename, Scene) pairs."""

    scenes: tuple[tuple[str, Scene], ...]


def _write_lf(path: Path, text: str) -> None:
    """Write text with `\n` line ends on every platform, so the files (and the hash of classes.txt) are the same bytes
    wherever the dataset is made."""
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def class_names(dataset: Dataset) -> list[str]:
    """The class list, in a fixed order that does not depend on which labels a
    run happens to contain (so class ids mean the same in every dataset). A
    label outside the known set, if one is ever generated, goes after them."""
    seen = {component.label for _, scene in dataset.scenes for component in scene.components}
    return list(FIXED_CLASSES) + sorted(seen - set(FIXED_CLASSES))


def export_yolo(dataset: Dataset, out_dir: Path) -> None:
    """Write real YOLO-format labels: one `.txt` per image plus `classes.txt`."""
    labels = class_names(dataset)
    class_index = {name: index for index, name in enumerate(labels)}

    labels_dir = out_dir / "labels"
    labels_dir.mkdir(parents=True, exist_ok=True)
    _write_lf(out_dir / "classes.txt", "\n".join(labels) + "\n")

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
        _write_lf(labels_dir / f"{stem}.txt", text)


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
    _write_lf(out_path, json.dumps(payload, indent=2))
