# =============================================================================
# HYDRA-UMC-SYNTHETIC-DATA-GEN - tests/test_render.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
from __future__ import annotations

import random
from pathlib import Path

from hydra_umc_synthetic_data_gen.render import read_bmp_dimensions, render_bmp
from hydra_umc_synthetic_data_gen.scene import generate_scene


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
