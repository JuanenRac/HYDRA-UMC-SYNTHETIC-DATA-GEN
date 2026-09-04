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


def test_components_stay_within_a_small_canvas_smaller_than_default_max_size() -> None:
    # Real bug found by an ecosystem-wide audit: a small scene (real,
    # CLI-accepted dimensions - main.py's own MIN_DIMENSION is 16) with
    # the real default max_size=48 used to produce components wider/
    # taller than the canvas itself, always clamped to x=0/y=0 and
    # overflowing the edge - swept across many seeds since the original
    # bug was probabilistic (only manifested when a random size actually
    # exceeded the canvas).
    for seed in range(50):
        scene = generate_scene(random.Random(seed), width=20, height=20, num_components=10)
        for component in scene.components:
            assert 0 <= component.x, f"seed={seed}"
            assert 0 <= component.y, f"seed={seed}"
            assert component.x + component.width <= 20, f"seed={seed}"
            assert component.y + component.height <= 20, f"seed={seed}"


def test_zero_defect_probability_produces_no_defects() -> None:
    scene = generate_scene(random.Random(3), num_components=10, defect_probability=0.0)

    assert all(component.label != DEFECT_LABEL for component in scene.components)


def test_certain_defect_probability_always_adds_one_per_component() -> None:
    scene = generate_scene(random.Random(3), num_components=4, defect_probability=1.0)

    defect_count = sum(1 for component in scene.components if component.label == DEFECT_LABEL)
    assert defect_count == 4
    assert len(scene.components) == 8
