# =============================================================================
# HYDRA-UMC-SYNTHETIC-DATA-GEN - src/hydra_umc_synthetic_data_gen/render.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
"""Real, stdlib-only BMP rasterization of a Scene - no Pillow dependency.

Writes a real, valid, viewable 24-bit uncompressed BMP (BITMAPFILEHEADER +
BITMAPINFOHEADER, bottom-up row order, BGR pixels, rows padded to a
multiple of 4 bytes) using only `struct`. Flat-shaded rectangles, not
photorealistic rendering - see scene.py's own module docstring for why.
"""
from __future__ import annotations

import struct
from pathlib import Path

from .scene import Scene


def _row_size(width: int) -> int:
    return (width * 3 + 3) & ~3


def render_bmp(scene: Scene, path: Path) -> None:
    """Render `scene` to a real BMP file at `path`."""
    width, height = scene.width, scene.height

    pixels = [[scene.background_color for _ in range(width)] for _ in range(height)]
    for comp in scene.components:
        y_start = max(0, comp.y)
        y_end = min(height, comp.y + comp.height)
        x_start = max(0, comp.x)
        x_end = min(width, comp.x + comp.width)
        for py in range(y_start, y_end):
            row = pixels[py]
            for px in range(x_start, x_end):
                row[px] = comp.color

    row_size = _row_size(width)
    pixel_data_size = row_size * height
    file_size = 14 + 40 + pixel_data_size

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"BM")
        f.write(struct.pack("<IHHI", file_size, 0, 0, 14 + 40))
        f.write(
            struct.pack(
                "<IiiHHIIiiII",
                40, width, height, 1, 24, 0, pixel_data_size, 0, 0, 0, 0,
            )
        )
        padding = b"\x00" * (row_size - width * 3)
        for y in range(height - 1, -1, -1):
            row_bytes = bytearray()
            for r, g, b in pixels[y]:
                row_bytes += bytes((b, g, r))
            f.write(row_bytes)
            f.write(padding)


def read_bmp_dimensions(path: Path) -> tuple[int, int]:
    """Real BMP header parser - width/height, used by this project's own tests."""
    with open(path, "rb") as f:
        header = f.read(14 + 40)
    width, height = struct.unpack("<ii", header[18:26])
    return width, height
