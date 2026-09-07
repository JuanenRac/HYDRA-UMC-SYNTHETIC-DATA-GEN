# =============================================================================
# HYDRA-UMC-SYNTHETIC-DATA-GEN - tests/test_manifest.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from hydra_umc_synthetic_data_gen.export import Dataset
from hydra_umc_synthetic_data_gen.manifest import build_manifest, write_manifest
from hydra_umc_synthetic_data_gen.render import render_bmp
from hydra_umc_synthetic_data_gen.scene import Component, Scene
from hydra_umc_synthetic_data_gen.validate import ValidationIssue

LABELS = ("bolt", "bracket", "gear", "connector")


def _rendered_dataset(tmp_path: Path) -> tuple[Dataset, Path]:
    images_dir = tmp_path / "images"
    scene = Scene(
        width=32,
        height=32,
        background_color=(200, 200, 200),
        components=(Component(label="bolt", x=0, y=0, width=8, height=8, color=(10, 20, 30)),),
    )
    render_bmp(scene, images_dir / "scene_0000.bmp")
    dataset = Dataset(scenes=(("scene_0000.bmp", scene),))
    return dataset, images_dir


def test_build_manifest_records_reproducible_true_when_seeded(tmp_path: Path) -> None:
    dataset, images_dir = _rendered_dataset(tmp_path)

    manifest = build_manifest(
        dataset,
        images_dir,
        seed=42,
        width=32,
        height=32,
        requested_components=1,
        defect_rate=0.2,
        labels=LABELS,
        fmt="both",
        issues=[],
    )

    assert manifest.seed == 42
    assert manifest.reproducible is True
    assert manifest.is_clean is True


def test_build_manifest_records_reproducible_false_when_unseeded(tmp_path: Path) -> None:
    dataset, images_dir = _rendered_dataset(tmp_path)

    manifest = build_manifest(
        dataset,
        images_dir,
        seed=None,
        width=32,
        height=32,
        requested_components=1,
        defect_rate=0.2,
        labels=LABELS,
        fmt="both",
        issues=[],
    )

    assert manifest.seed is None
    assert manifest.reproducible is False


def test_build_manifest_checksum_matches_the_real_rendered_file(tmp_path: Path) -> None:
    dataset, images_dir = _rendered_dataset(tmp_path)

    manifest = build_manifest(
        dataset,
        images_dir,
        seed=1,
        width=32,
        height=32,
        requested_components=1,
        defect_rate=0.2,
        labels=LABELS,
        fmt="both",
        issues=[],
    )

    expected_sha256 = hashlib.sha256((images_dir / "scene_0000.bmp").read_bytes()).hexdigest()
    assert len(manifest.scenes) == 1
    assert manifest.scenes[0].sha256 == expected_sha256
    assert manifest.scenes[0].label_counts == {"bolt": 1}


def test_build_manifest_records_validation_issues_as_readable_strings(tmp_path: Path) -> None:
    dataset, images_dir = _rendered_dataset(tmp_path)
    issues = [ValidationIssue(kind="out_of_bounds", detail="scene_0000.bmp: component 'bolt' escapes the frame")]

    manifest = build_manifest(
        dataset,
        images_dir,
        seed=1,
        width=32,
        height=32,
        requested_components=1,
        defect_rate=0.2,
        labels=LABELS,
        fmt="both",
        issues=issues,
    )

    assert manifest.is_clean is False
    assert manifest.validation_issues == ("out_of_bounds: scene_0000.bmp: component 'bolt' escapes the frame",)


def test_write_manifest_round_trips_through_json(tmp_path: Path) -> None:
    dataset, images_dir = _rendered_dataset(tmp_path)
    manifest = build_manifest(
        dataset,
        images_dir,
        seed=7,
        width=32,
        height=32,
        requested_components=1,
        defect_rate=0.2,
        labels=LABELS,
        fmt="yolo",
        issues=[],
    )

    manifest_path = tmp_path / "manifest.json"
    write_manifest(manifest, manifest_path)

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["seed"] == 7
    assert payload["reproducible"] is True
    assert payload["count"] == 1
    assert payload["labels"] == list(LABELS)
    assert payload["format"] == "yolo"
    assert payload["scenes"][0]["image"] == "scene_0000.bmp"
    assert payload["scenes"][0]["sha256"] == manifest.scenes[0].sha256
    assert payload["validation_issues"] == []
