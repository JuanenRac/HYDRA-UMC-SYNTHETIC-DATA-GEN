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
    """Render `scene` to a real BMP file at `path`.

    The image is held as one flat `bytearray` of BGR bytes per row (3 bytes a pixel) and rectangles are painted by
    slice, not pixel by pixel: the old list of lists of tuples cost about 8 bytes of pointer per pixel plus a Python
    loop over every one, minutes for a 4096x4096 scene. The bytes written are exactly the same."""
    width, height = scene.width, scene.height

    background = bytes((scene.background_color[2], scene.background_color[1], scene.background_color[0]))
    pixels = [bytearray(background * width) for _ in range(height)]
    for comp in scene.components:
        if comp.scratch is not None:
            # Blended into whatever's already painted beneath it (the
            # parent component's own fill, since it was appended earlier
            # in scene.components and painted first) rather than a flat
            # overwrite - see ScratchPoint's own docstring for why.
            for sp in comp.scratch:
                for oy in range(-sp.half_width, sp.half_width + 1):
                    for ox in range(-sp.half_width, sp.half_width + 1):
                        px, py = sp.x + ox, sp.y + oy
                        if 0 <= px < width and 0 <= py < height:
                            row = pixels[py]
                            offset = px * 3
                            # the row holds B, G, R; the blend is the one the tuple version computed per channel
                            row[offset] = int(row[offset] * (1 - sp.opacity) + comp.color[2] * sp.opacity)
                            row[offset + 1] = int(row[offset + 1] * (1 - sp.opacity) + comp.color[1] * sp.opacity)
                            row[offset + 2] = int(row[offset + 2] * (1 - sp.opacity) + comp.color[0] * sp.opacity)
            continue
        y_start = max(0, comp.y)
        y_end = min(height, comp.y + comp.height)
        x_start = max(0, comp.x)
        x_end = min(width, comp.x + comp.width)
        if x_end > x_start:
            fill = bytes((comp.color[2], comp.color[1], comp.color[0])) * (x_end - x_start)
            for py in range(y_start, y_end):
                pixels[py][x_start * 3 : x_end * 3] = fill

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
            f.write(pixels[y])
            f.write(padding)


def read_bmp_dimensions(path: Path) -> tuple[int, int]:
    """Real BMP header parser - width/height, used by this project's own tests."""
    with open(path, "rb") as f:
        header = f.read(14 + 40)
    width, height = struct.unpack("<ii", header[18:26])
    return width, height
