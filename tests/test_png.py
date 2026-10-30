# =============================================================================
# HYDRA-UMC-SYNTHETIC-DATA-GEN - tests/test_png.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
from __future__ import annotations

import random
import struct
import zlib
from pathlib import Path

from hydra_umc_synthetic_data_gen.main import main
from hydra_umc_synthetic_data_gen.render import _paint, render_png
from hydra_umc_synthetic_data_gen.scene import generate_scene
from hydra_umc_synthetic_data_gen.validate import validate_png_integrity


def _decode(path: Path) -> tuple[int, int, list[bytes]]:
    """A minimal reader of what render_png writes (8-bit RGB, filter 0), to compare with the painted rows."""
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", data[16:24])
    idat = b""
    position = 8
    while position < len(data):
        length = struct.unpack(">I", data[position : position + 4])[0]
        if data[position + 4 : position + 8] == b"IDAT":
            idat += data[position + 8 : position + 8 + length]
        position += 12 + length
    raw = zlib.decompress(idat)
    stride = 1 + 3 * width
    return width, height, [raw[y * stride + 1 : (y + 1) * stride] for y in range(height)]


def test_the_png_holds_the_same_pixels_the_bmp_is_painted_from(tmp_path: Path) -> None:
    scene = generate_scene(random.Random(5), width=40, height=30, num_components=4, defect_probability=0.5)
    path = tmp_path / "scene.png"
    render_png(scene, path)
    width, height, rows = _decode(path)
    assert (width, height) == (40, 30)
    for painted, stored in zip(_paint(scene), rows):
        bgr = bytes(painted)
        assert bytes(b for i in range(0, len(bgr), 3) for b in (bgr[i + 2], bgr[i + 1], bgr[i])) == stored


def test_a_png_render_is_the_same_bytes_every_time(tmp_path: Path) -> None:
    scene = generate_scene(random.Random(6), width=32, height=32, num_components=3)
    render_png(scene, tmp_path / "a.png")
    render_png(scene, tmp_path / "b.png")
    assert (tmp_path / "a.png").read_bytes() == (tmp_path / "b.png").read_bytes()


def test_png_integrity_accepts_a_real_render_and_flags_damage(tmp_path: Path) -> None:
    scene = generate_scene(random.Random(7), width=24, height=24, num_components=2)
    path = tmp_path / "scene.png"
    render_png(scene, path)
    assert validate_png_integrity("scene.png", path, 24, 24) == []
    assert [i.kind for i in validate_png_integrity("scene.png", path, 25, 24)] == ["corrupt_png"]
    good = path.read_bytes()
    path.write_bytes(good[: len(good) // 2])
    assert [i.kind for i in validate_png_integrity("scene.png", path, 24, 24)] == ["corrupt_png"]
    flipped = bytearray(good)
    flipped[40] ^= 0xFF  # inside the pixel data: the chunk checksum no longer matches
    path.write_bytes(bytes(flipped))
    assert [i.kind for i in validate_png_integrity("scene.png", path, 24, 24)] == ["corrupt_png"]
    path.write_bytes(b"not a png")
    assert [i.kind for i in validate_png_integrity("scene.png", path, 24, 24)] == ["corrupt_png"]
    assert [i.kind for i in validate_png_integrity("scene.png", tmp_path / "none.png", 24, 24)] == ["missing_file"]


def test_generate_in_png_makes_a_dataset_that_verifies(tmp_path: Path, capsys) -> None:
    out = tmp_path / "ds"
    assert main(["generate", "--out", str(out), "--count", "3", "--seed", "3", "--image-format", "png", "--split", "train=0.6,val=0.2,test=0.2"]) == 0
    assert sorted(p.name for p in (out / "images").iterdir()) == ["scene_0000.png", "scene_0001.png", "scene_0002.png"]
    assert not list((out / "images").glob("*.bmp"))
    assert main(["verify", "--out", str(out)]) == 0
    assert "VERIFY=PASS" in capsys.readouterr().out
    (out / "images" / "scene_0001.png").write_bytes(b"damaged")
    assert main(["verify", "--out", str(out)]) == 1


def test_the_default_format_stays_bmp(tmp_path: Path) -> None:
    out = tmp_path / "ds"
    assert main(["generate", "--out", str(out), "--count", "1", "--seed", "3"]) == 0
    assert [p.name for p in (out / "images").iterdir()] == ["scene_0000.bmp"]
