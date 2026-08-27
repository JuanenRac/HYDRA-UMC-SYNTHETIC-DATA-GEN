# =============================================================================
# HYDRA-UMC-SYNTHETIC-DATA-GEN - tests/test_validate.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
from __future__ import annotations

from pathlib import Path

from hydra_umc_synthetic_data_gen.export import Dataset
from hydra_umc_synthetic_data_gen.render import render_bmp
from hydra_umc_synthetic_data_gen.scene import Component, Scene
from hydra_umc_synthetic_data_gen.validate import (
    validate_bmp_integrity,
    validate_dataset,
    validate_label_distribution,
    validate_scene_bounds,
)

LABELS = ("bolt", "bracket", "gear", "connector")


def _scene(components: tuple[Component, ...], width: int = 64, height: int = 64) -> Scene:
    return Scene(width=width, height=height, background_color=(200, 200, 200), components=components)


def test_scene_bounds_accepts_a_component_fully_inside() -> None:
    scene = _scene((Component(label="bolt", x=0, y=0, width=32, height=32, color=(1, 2, 3)),))

    assert validate_scene_bounds("scene_0.bmp", scene) == []


def test_scene_bounds_flags_a_component_exceeding_the_right_edge() -> None:
    scene = _scene((Component(label="bolt", x=50, y=0, width=32, height=32, color=(1, 2, 3)),))

    issues = validate_scene_bounds("scene_0.bmp", scene)

    assert len(issues) == 1
    assert issues[0].kind == "out_of_bounds"
    assert "bolt" in issues[0].detail


def test_scene_bounds_flags_a_negative_origin() -> None:
    scene = _scene((Component(label="gear", x=-1, y=0, width=10, height=10, color=(1, 2, 3)),))

    issues = validate_scene_bounds("scene_0.bmp", scene)

    assert len(issues) == 1
    assert issues[0].kind == "out_of_bounds"


def test_bmp_integrity_accepts_a_real_render(tmp_path: Path) -> None:
    scene = _scene((Component(label="bolt", x=0, y=0, width=16, height=16, color=(1, 2, 3)),))
    path = tmp_path / "scene_0.bmp"
    render_bmp(scene, path)

    assert validate_bmp_integrity("scene_0.bmp", path, 64, 64) == []


def test_bmp_integrity_flags_a_missing_file(tmp_path: Path) -> None:
    issues = validate_bmp_integrity("scene_0.bmp", tmp_path / "does_not_exist.bmp", 64, 64)

    assert len(issues) == 1
    assert issues[0].kind == "missing_file"


def test_bmp_integrity_flags_a_truncated_file(tmp_path: Path) -> None:
    scene = _scene((Component(label="bolt", x=0, y=0, width=16, height=16, color=(1, 2, 3)),))
    path = tmp_path / "scene_0.bmp"
    render_bmp(scene, path)

    full = path.read_bytes()
    path.write_bytes(full[: len(full) // 2])

    issues = validate_bmp_integrity("scene_0.bmp", path, 64, 64)

    assert any(issue.kind == "corrupt_bmp" for issue in issues)


def test_bmp_integrity_flags_missing_magic_bytes(tmp_path: Path) -> None:
    path = tmp_path / "scene_0.bmp"
    path.write_bytes(b"not a bitmap" + b"\x00" * 100)

    issues = validate_bmp_integrity("scene_0.bmp", path, 64, 64)

    assert len(issues) == 1
    assert issues[0].kind == "corrupt_bmp"


def test_bmp_integrity_flags_a_dimension_mismatch(tmp_path: Path) -> None:
    scene = _scene((Component(label="bolt", x=0, y=0, width=16, height=16, color=(1, 2, 3)),), width=64, height=64)
    path = tmp_path / "scene_0.bmp"
    render_bmp(scene, path)

    issues = validate_bmp_integrity("scene_0.bmp", path, 128, 128)

    assert any(issue.kind == "dimension_mismatch" for issue in issues)


def test_label_distribution_accepts_a_matching_rate() -> None:
    # 40 non-defect components, 8 defects -> 0.2 observed rate, matches configured 0.2.
    components = tuple(Component(label="bolt", x=0, y=0, width=1, height=1, color=(0, 0, 0)) for _ in range(40))
    components += tuple(
        Component(label="defect", x=0, y=0, width=1, height=1, color=(0, 0, 0)) for _ in range(8)
    )
    dataset = Dataset(scenes=(("scene_0.bmp", _scene(components)),))

    assert validate_label_distribution(dataset, LABELS, 0.2) == []


def test_label_distribution_flags_a_wildly_off_rate() -> None:
    # 40 non-defect components, 39 defects -> observed rate ~0.975, configured 0.1.
    components = tuple(Component(label="bolt", x=0, y=0, width=1, height=1, color=(0, 0, 0)) for _ in range(40))
    components += tuple(
        Component(label="defect", x=0, y=0, width=1, height=1, color=(0, 0, 0)) for _ in range(39)
    )
    dataset = Dataset(scenes=(("scene_0.bmp", _scene(components)),))

    issues = validate_label_distribution(dataset, LABELS, 0.1)

    assert len(issues) == 1
    assert issues[0].kind == "distribution_anomaly"


def test_label_distribution_ignores_small_samples_even_when_off() -> None:
    # Only 3 non-defect components (below min_sample=20) - never flagged, avoids flakiness on small --count runs.
    components = (
        Component(label="bolt", x=0, y=0, width=1, height=1, color=(0, 0, 0)),
        Component(label="defect", x=0, y=0, width=1, height=1, color=(0, 0, 0)),
        Component(label="defect", x=0, y=0, width=1, height=1, color=(0, 0, 0)),
    )
    dataset = Dataset(scenes=(("scene_0.bmp", _scene(components)),))

    assert validate_label_distribution(dataset, LABELS, 0.1) == []


def test_label_distribution_flags_an_unexpected_label() -> None:
    components = (Component(label="wingnut", x=0, y=0, width=1, height=1, color=(0, 0, 0)),)
    dataset = Dataset(scenes=(("scene_0.bmp", _scene(components)),))

    issues = validate_label_distribution(dataset, LABELS, 0.2)

    assert any(issue.kind == "unexpected_label" for issue in issues)


def test_validate_dataset_combines_bounds_and_bmp_checks(tmp_path: Path) -> None:
    out_of_bounds = _scene((Component(label="bolt", x=60, y=0, width=32, height=32, color=(1, 2, 3)),))
    render_bmp(out_of_bounds, tmp_path / "scene_0.bmp")
    dataset = Dataset(scenes=(("scene_0.bmp", out_of_bounds), ("scene_1.bmp", _scene(()))))

    issues = validate_dataset(dataset, tmp_path, expected_labels=LABELS, defect_rate=0.2)

    kinds = {issue.kind for issue in issues}
    assert "out_of_bounds" in kinds
    assert "missing_file" in kinds  # scene_1.bmp was never rendered
