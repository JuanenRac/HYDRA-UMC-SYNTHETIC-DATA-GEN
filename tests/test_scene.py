# =============================================================================
# HYDRA-UMC-SYNTHETIC-DATA-GEN - tests/test_scene.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
from __future__ import annotations

import random

from hydra_umc_synthetic_data_gen.scene import DEFECT_LABEL, _bresenham_line, generate_scene, generate_scratch


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
    # Real bug found while auditing the code: a small scene (real,
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


def test_certain_defect_probability_produces_a_real_mix_of_both_defect_kinds() -> None:
    # With enough components, the 50/50 scratch-vs-rectangle choice
    # inside generate_scene() should produce at least one of each real
    # kind, not always the same one - proves the scratch path is
    # actually reachable through the public generate_scene() API, not
    # just directly callable via generate_scratch().
    scene = generate_scene(random.Random(11), num_components=40, defect_probability=1.0)
    defects = [c for c in scene.components if c.label == DEFECT_LABEL]
    assert any(d.scratch is not None for d in defects), "expected at least one scratch-kind defect"
    assert any(d.scratch is None for d in defects), "expected at least one rectangle-kind defect"


def test_bresenham_line_connects_start_to_end_with_no_gaps() -> None:
    # A real correctness property of Bresenham's algorithm: consecutive
    # points must each move by at most 1 pixel in x and 1 in y (an
    # 8-connected path), and the line must actually start and end at the
    # requested endpoints - checked across several real slopes/directions
    # (shallow, steep, vertical, horizontal, and all 4 diagonal signs).
    cases = [(0, 0, 10, 3), (0, 0, 3, 10), (5, 5, 5, 5), (5, 5, 5, 0), (5, 5, 0, 5), (10, 10, 0, 0), (0, 10, 10, 0)]
    for x0, y0, x1, y1 in cases:
        points = _bresenham_line(x0, y0, x1, y1)
        assert points[0] == (x0, y0)
        assert points[-1] == (x1, y1)
        for (px0, py0), (px1, py1) in zip(points, points[1:]):
            assert abs(px1 - px0) <= 1
            assert abs(py1 - py0) <= 1


def test_generate_scratch_is_deterministic_given_the_same_rng_state() -> None:
    scratch_a = generate_scratch(random.Random(99), x=10, y=10, width=20, height=20)
    scratch_b = generate_scratch(random.Random(99), x=10, y=10, width=20, height=20)
    assert scratch_a == scratch_b
    assert len(scratch_a) > 0


def test_generate_scratch_points_stay_within_its_own_bounding_box() -> None:
    for seed in range(30):
        x, y, w, h = 10, 15, 25, 18
        scratch = generate_scratch(random.Random(seed), x=x, y=y, width=w, height=h)
        for point in scratch:
            assert x <= point.x < x + w, f"seed={seed}"
            assert y <= point.y < y + h, f"seed={seed}"
            assert 0.0 <= point.opacity <= 1.0, f"seed={seed}"
