# =============================================================================
# HYDRA-UMC-SYNTHETIC-DATA-GEN - tests/test_export.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
from __future__ import annotations

import json
from pathlib import Path

from hydra_umc_synthetic_data_gen.export import Dataset, export_coco, export_yolo
from hydra_umc_synthetic_data_gen.scene import Component, Scene


def _sample_dataset() -> Dataset:
    scene = Scene(
        width=100,
        height=100,
        background_color=(200, 200, 200),
        components=(
            Component(label="bolt", x=10, y=20, width=20, height=10, color=(0, 0, 0)),
            Component(label="gear", x=50, y=50, width=30, height=30, color=(10, 10, 10)),
        ),
    )
    return Dataset(scenes=(("scene_0000.bmp", scene),))


def test_export_yolo_writes_normalized_boxes(tmp_path: Path) -> None:
    dataset = _sample_dataset()

    export_yolo(dataset, tmp_path)

    classes = (tmp_path / "classes.txt").read_text(encoding="utf-8").splitlines()
    assert classes == ["bolt", "gear"]

    label_lines = (tmp_path / "labels" / "scene_0000.txt").read_text(encoding="utf-8").splitlines()
    assert len(label_lines) == 2

    bolt_class, cx, cy, w, h = label_lines[0].split()
    assert bolt_class == "0"
    assert abs(float(cx) - 0.20) < 1e-6
    assert abs(float(cy) - 0.25) < 1e-6
    assert abs(float(w) - 0.20) < 1e-6
    assert abs(float(h) - 0.10) < 1e-6


def test_export_coco_writes_valid_json(tmp_path: Path) -> None:
    dataset = _sample_dataset()
    out_path = tmp_path / "annotations.json"

    export_coco(dataset, out_path)

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert len(payload["images"]) == 1
    assert payload["images"][0]["file_name"] == "scene_0000.bmp"
    assert len(payload["annotations"]) == 2
    assert payload["annotations"][0]["bbox"] == [10, 20, 20, 10]
    assert payload["annotations"][0]["area"] == 200
    assert {c["name"] for c in payload["categories"]} == {"bolt", "gear"}


def test_export_yolo_on_scene_with_no_components_writes_empty_label_file(tmp_path: Path) -> None:
    scene = Scene(width=50, height=50, background_color=(200, 200, 200), components=())
    dataset = Dataset(scenes=(("empty.bmp", scene),))

    export_yolo(dataset, tmp_path)

    assert (tmp_path / "labels" / "empty.txt").read_text(encoding="utf-8") == ""
