# =============================================================================
# HYDRA-UMC-SYNTHETIC-DATA-GEN - tests/test_render.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
from __future__ import annotations

import random
from pathlib import Path

from hydra_umc_synthetic_data_gen.render import read_bmp_dimensions, render_bmp
from hydra_umc_synthetic_data_gen.scene import Component, Scene, generate_scene, generate_scratch


def test_render_bmp_writes_a_real_valid_file(tmp_path: Path) -> None:
    scene = generate_scene(random.Random(1), width=64, height=48, num_components=3)
    path = tmp_path / "scene_0000.bmp"

    render_bmp(scene, path)

    assert path.is_file()
    with open(path, "rb") as f:
        magic = f.read(2)
    assert magic == b"BM"


def test_render_bmp_dimensions_match_scene(tmp_path: Path) -> None:
    scene = generate_scene(random.Random(2), width=100, height=80, num_components=2)
    path = tmp_path / "scene.bmp"

    render_bmp(scene, path)

    width, height = read_bmp_dimensions(path)
    assert width == 100
    assert height == 80


def test_render_bmp_row_padding_produces_expected_file_size(tmp_path: Path) -> None:
    # 5x1 canvas: row = 5*3 = 15 bytes, padded to 16 (multiple of 4).
    scene = generate_scene(random.Random(1), width=5, height=1, num_components=0)
    path = tmp_path / "tiny.bmp"

    render_bmp(scene, path)

    expected_size = 14 + 40 + 16 * 1
    assert path.stat().st_size == expected_size


def test_render_bmp_creates_parent_directories(tmp_path: Path) -> None:
    scene = generate_scene(random.Random(1), width=8, height=8, num_components=1)
    path = tmp_path / "nested" / "images" / "scene.bmp"

    render_bmp(scene, path)

    assert path.is_file()


def test_render_bmp_paints_a_scratch_defect_over_its_background(tmp_path: Path) -> None:
    # A real, direct proof the scratch rendering path (render_bmp's own
    # `comp.scratch is not None` branch) actually changes pixels along
    # the Bresenham line, blended against the background, rather than a
    # silent no-op - built directly from a real generate_scratch() call
    # and a hand-built one-component Scene so the test doesn't depend on
    # generate_scene()'s own 50/50 defect-kind coin flip to land on a
    # scratch.
    bg = (200, 200, 200)
    scratch = generate_scratch(random.Random(5), x=2, y=2, width=6, height=6)
    scene = Scene(
        width=10, height=10, background_color=bg,
        components=(Component(label="defect", x=2, y=2, width=6, height=6, color=(200, 30, 30), scratch=scratch),),
    )
    path = tmp_path / "scratch.bmp"

    render_bmp(scene, path)

    # Re-read the raw pixel data and confirm at least one real scratch
    # point's own pixel differs from the untouched background - proves
    # the blend actually wrote something, not just that the file exists.
    with open(path, "rb") as f:
        data = f.read()
    row_size = (10 * 3 + 3) & ~3
    pixel_offset = 14 + 40
    changed = False
    for point in scratch:
        # BMP rows are stored bottom-up.
        bmp_row = 10 - 1 - point.y
        offset = pixel_offset + bmp_row * row_size + point.x * 3
        b, g, r = data[offset], data[offset + 1], data[offset + 2]
        if (r, g, b) != bg:
            changed = True
            break
    assert changed, "expected at least one real scratch pixel to differ from the untouched background"
