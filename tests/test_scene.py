# =============================================================================
# HYDRA-UMC-SYNTHETIC-DATA-GEN - tests/test_scene.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
from __future__ import annotations

import random

from hydra_umc_synthetic_data_gen.scene import DEFECT_LABEL, generate_scene


def test_same_seed_is_deterministic() -> None:
    scene_a = generate_scene(random.Random(42), num_components=5)
    scene_b = generate_scene(random.Random(42), num_components=5)

    assert scene_a == scene_b


def test_different_seeds_differ() -> None:
    scene_a = generate_scene(random.Random(1), num_components=5)
    scene_b = generate_scene(random.Random(2), num_components=5)

    assert scene_a.components != scene_b.components


def test_components_stay_within_canvas_bounds() -> None:
    scene = generate_scene(random.Random(7), width=200, height=150, num_components=20)

    for component in scene.components:
        assert 0 <= component.x
        assert 0 <= component.y
        assert component.x + component.width <= 200
        assert component.y + component.height <= 150


def test_zero_defect_probability_produces_no_defects() -> None:
    scene = generate_scene(random.Random(3), num_components=10, defect_probability=0.0)

    assert all(component.label != DEFECT_LABEL for component in scene.components)


def test_certain_defect_probability_always_adds_one_per_component() -> None:
    scene = generate_scene(random.Random(3), num_components=4, defect_probability=1.0)

    defect_count = sum(1 for component in scene.components if component.label == DEFECT_LABEL)
    assert defect_count == 4
    assert len(scene.components) == 8
