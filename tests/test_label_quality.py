# =============================================================================
# HYDRA-UMC-SYNTHETIC-DATA-GEN - tests/test_label_quality.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
"""Boxes must describe what is visible in the image."""
import random

from hydra_umc_synthetic_data_gen.scene import (
    MIN_SCRATCH_POINTS,
    Component,
    ScratchPoint,
    generate_scene,
    visible_components,
)


def _solid(x, y, w, h, label="bolt"):
    return Component(label=label, x=x, y=y, width=w, height=h, color=(0, 0, 0))


def test_a_component_completely_covered_by_a_later_one_is_not_labelled():
    hidden, cover = _solid(10, 10, 20, 20), _solid(0, 0, 60, 60, "gear")
    assert visible_components((hidden, cover), 100, 100) == (cover,)


def test_a_mostly_visible_component_keeps_its_box():
    first, second = _solid(10, 10, 20, 20), _solid(25, 10, 20, 20, "gear")  # covers a quarter of the first
    assert visible_components((first, second), 100, 100) == (first, second)


def test_heavily_overlapped_scenes_never_label_an_invisible_object():
    for seed in range(40):
        scene = generate_scene(random.Random(seed), width=64, height=64, num_components=20, defect_probability=0.0)
        kept = scene.components
        # what is rendered is exactly what is labelled: nothing left to drop
        assert visible_components(kept, 64, 64) == kept
        assert len(kept) >= 1


def test_a_scratch_is_boxed_by_the_pixels_it_paints():
    found = 0
    for seed in range(200):
        scene = generate_scene(random.Random(seed), width=128, height=128, num_components=4, defect_probability=1.0)
        for component in scene.components:
            if component.scratch is None:
                continue
            found += 1
            xs = [p.x + d for p in component.scratch for d in (-p.half_width, p.half_width)]
            ys = [p.y + d for p in component.scratch for d in (-p.half_width, p.half_width)]
            assert component.x == max(0, min(xs)) and component.y == max(0, min(ys))
            assert component.x + component.width - 1 == min(127, max(xs))
            assert component.y + component.height - 1 == min(127, max(ys))
            assert len(component.scratch) >= MIN_SCRATCH_POINTS
    assert found > 0


def test_every_box_stays_inside_the_scene():
    for seed in range(60):
        scene = generate_scene(random.Random(seed), width=48, height=48, num_components=8, defect_probability=0.8)
        for c in scene.components:
            assert 0 <= c.x and 0 <= c.y and c.x + c.width <= 48 and c.y + c.height <= 48


def test_a_later_scratch_does_not_hide_a_component():
    base = _solid(10, 10, 20, 20)
    scratch = Component(
        label="defect", x=10, y=10, width=20, height=20, color=(200, 30, 30),
        scratch=tuple(ScratchPoint(10 + i, 10 + i, 0, 0.5) for i in range(20)),
    )
    assert visible_components((base, scratch), 100, 100) == (base, scratch)
