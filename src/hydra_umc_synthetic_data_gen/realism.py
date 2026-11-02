# =============================================================================
# HYDRA-UMC-SYNTHETIC-DATA-GEN - src/hydra_umc_synthetic_data_gen/realism.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
"""Making a flat-shaded scene look a little more like a photograph, to shrink the gap between synthetic and real images.

A model trained only on perfectly flat rectangles learns what flat rectangles look like. The effects here are the usual first steps against that gap, all with the
standard library and all drawn from a generator seeded by the seed of the scene and its index, so the same seed still gives the same bytes:

* a **texture** under everything (smooth value noise, so the background is not one grey);
* **uneven illumination** (a brighter side and a darker one, in a random direction);
* a small **rotation** and a **perspective** change of the whole image: the camera is never exactly square to the board. The boxes are moved with the image (the
  box of the four corners of every box, clipped to the image); one that is left less than `min_visibility` visible is dropped, like an object that is covered;
* a **blur** (a box filter of random radius, up to the configured one): the picture is never perfectly in focus;
* **sensor noise** (Gaussian, per channel).

Every effect is off at 0, and all of them are off unless the realism file says `"enabled": true` (the `--realism-config` option of `generate` and `calibration`). The
parameters are in that file, not in the code:

    {"enabled": true, "texture": {"amplitude": 8, "cell": 12}, "illumination": {"strength": 0.2}, "rotation": {"max_degrees": 4},
     "perspective": {"max_shift_fraction": 0.04}, "blur": {"max_radius": 2}, "noise": {"sigma": 3}, "min_visibility": 0.3, "max_pixels": 1048576}

It works one pixel at a time in Python, so an image above `max_pixels` (a megapixel by default) is refused rather than taking minutes. It is a cheap approximation of a
camera, not a renderer: it does not make the objects three-dimensional, and how much it narrows the gap for a real model has not been measured.
"""
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .scene import Component, Scene

_TOP = {"enabled", "texture", "illumination", "rotation", "perspective", "blur", "noise", "min_visibility", "max_pixels"}
_SECTIONS = {"texture": {"amplitude", "cell"}, "illumination": {"strength"}, "rotation": {"max_degrees"}, "perspective": {"max_shift_fraction"}, "blur": {"max_radius"}, "noise": {"sigma"}}
MAX_CONFIG_BYTES = 16 * 1024


class RealismError(ValueError):
    """The realism file cannot be used, or an image is too large for it."""


@dataclass(frozen=True)
class RealismConfig:
    enabled: bool = False
    texture_amplitude: float = 0.0
    texture_cell: int = 12
    illumination_strength: float = 0.0
    rotation_degrees: float = 0.0
    perspective_fraction: float = 0.0
    blur_radius: int = 0
    noise_sigma: float = 0.0
    min_visibility: float = 0.3
    max_pixels: int = 1_048_576

    def describe(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled, "texture": {"amplitude": self.texture_amplitude, "cell": self.texture_cell}, "illumination": {"strength": self.illumination_strength},
            "rotation": {"max_degrees": self.rotation_degrees}, "perspective": {"max_shift_fraction": self.perspective_fraction}, "blur": {"max_radius": self.blur_radius},
            "noise": {"sigma": self.noise_sigma}, "min_visibility": self.min_visibility, "max_pixels": self.max_pixels,
        }


def _number(section: dict, key: str, default: float, low: float, high: float, what: str) -> float:
    value = section.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise RealismError(f"{what} must be a number from {low:g} to {high:g}")
    return float(value)


def _whole(section: dict, key: str, default: int, low: int, high: int, what: str) -> int:
    value = section.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise RealismError(f"{what} must be an integer from {low} to {high}")
    return value


def parse_realism_config(config: object) -> RealismConfig:
    if not isinstance(config, dict) or set(config) - _TOP:
        raise RealismError(f"the realism file is an object with the keys {sorted(_TOP)}")
    enabled = config.get("enabled", False)
    if not isinstance(enabled, bool):
        raise RealismError("enabled must be true or false")
    sections: dict[str, dict] = {}
    for name, keys in _SECTIONS.items():
        section = config.get(name, {})
        if not isinstance(section, dict) or set(section) - keys:
            raise RealismError(f"{name} is an object with the keys {sorted(keys)}")
        sections[name] = section
    return RealismConfig(
        enabled=enabled,
        texture_amplitude=_number(sections["texture"], "amplitude", 0.0, 0.0, 60.0, "texture.amplitude"),
        texture_cell=_whole(sections["texture"], "cell", 12, 2, 64, "texture.cell"),
        illumination_strength=_number(sections["illumination"], "strength", 0.0, 0.0, 0.8, "illumination.strength"),
        rotation_degrees=_number(sections["rotation"], "max_degrees", 0.0, 0.0, 45.0, "rotation.max_degrees"),
        perspective_fraction=_number(sections["perspective"], "max_shift_fraction", 0.0, 0.0, 0.3, "perspective.max_shift_fraction"),
        blur_radius=_whole(sections["blur"], "max_radius", 0, 0, 8, "blur.max_radius"),
        noise_sigma=_number(sections["noise"], "sigma", 0.0, 0.0, 40.0, "noise.sigma"),
        min_visibility=_number(config, "min_visibility", 0.3, 0.0, 1.0, "min_visibility"),
        max_pixels=_whole(config, "max_pixels", 1_048_576, 256, 16_777_216, "max_pixels"),
    )


def load_realism_config(path: str | Path) -> RealismConfig:
    file = Path(path)

    def refuse(name: str) -> float:
        raise ValueError(f"{name} is not a valid JSON number")

    try:
        if file.stat().st_size > MAX_CONFIG_BYTES:
            raise RealismError(f"the realism file is larger than {MAX_CONFIG_BYTES} bytes")
        data = json.loads(file.read_text(encoding="utf-8"), parse_constant=refuse)
    except OSError as error:
        raise RealismError(f"the realism file cannot be read: {error.strerror}") from None
    except ValueError as error:
        if isinstance(error, RealismError):
            raise
        raise RealismError(f"the realism file is not valid JSON: {error}") from None
    return parse_realism_config(data)


# --------------------------------------------------------------------------------------------------------------------- effects


def _solve(matrix: list[list[float]], vector: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting for the 8x8 system of a homography."""
    n = len(vector)
    a = [row[:] + [vector[i]] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < 1e-12:
            raise RealismError("the distortion is degenerate")
        a[col], a[pivot] = a[pivot], a[col]
        for r in range(col + 1, n):
            factor = a[r][col] / a[col][col]
            for c in range(col, n + 1):
                a[r][c] -= factor * a[col][c]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        x[r] = (a[r][n] - sum(a[r][c] * x[c] for c in range(r + 1, n))) / a[r][r]
    return x


def homography(src: list[tuple[float, float]], dst: list[tuple[float, float]]) -> list[float]:
    """The 3x3 projective transform (h33 = 1) that takes the four points `src` to the four points `dst`."""
    matrix: list[list[float]] = []
    vector: list[float] = []
    for (x, y), (u, v) in zip(src, dst, strict=True):
        matrix.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        vector.append(u)
        matrix.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        vector.append(v)
    return [*_solve(matrix, vector), 1.0]


def _apply(h: list[float], x: float, y: float) -> tuple[float, float]:
    w = h[6] * x + h[7] * y + h[8]
    return (h[0] * x + h[1] * y + h[2]) / w, (h[3] * x + h[4] * y + h[5]) / w


def _texture_and_light(rows: list[bytearray], width: int, height: int, config: RealismConfig, rng: random.Random) -> None:
    cell = config.texture_cell
    gw, gh = width // cell + 2, height // cell + 2
    grid = [[rng.uniform(-1.0, 1.0) for _ in range(gw)] for _ in range(gh)]
    angle = rng.uniform(0.0, 2.0 * math.pi)
    ca, sa = math.cos(angle), math.sin(angle)
    amplitude, strength = config.texture_amplitude, config.illumination_strength
    for y in range(height):
        gy, fy = divmod(y / cell, 1.0)
        gy = int(gy)
        top, bottom = grid[gy], grid[gy + 1]
        row = rows[y]
        ly = (y / height - 0.5) * sa
        for x in range(width):
            value = 0.0
            if amplitude:
                gx, fx = divmod(x / cell, 1.0)
                gx = int(gx)
                value = amplitude * ((top[gx] * (1 - fx) + top[gx + 1] * fx) * (1 - fy) + (bottom[gx] * (1 - fx) + bottom[gx + 1] * fx) * fy)
            gain = 1.0 + 2.0 * strength * ((x / width - 0.5) * ca + ly) if strength else 1.0
            base = x * 3
            for c in range(3):
                v = row[base + c] * gain + value
                row[base + c] = 0 if v < 0 else 255 if v > 255 else int(v)


def _warp(rows: list[bytearray], width: int, height: int, scene: Scene, config: RealismConfig, rng: random.Random) -> tuple[list[bytearray], Scene]:
    cx, cy = (width - 1) / 2.0, (height - 1) / 2.0
    theta = math.radians(rng.uniform(-config.rotation_degrees, config.rotation_degrees))
    ct, st = math.cos(theta), math.sin(theta)
    reach = config.perspective_fraction * min(width, height)
    corners = [(0.0, 0.0), (width - 1.0, 0.0), (width - 1.0, height - 1.0), (0.0, height - 1.0)]
    moved = []
    for x, y in corners:
        dx, dy = x - cx, y - cy
        moved.append((cx + dx * ct - dy * st + rng.uniform(-reach, reach), cy + dx * st + dy * ct + rng.uniform(-reach, reach)))
    forward = homography(corners, moved)
    inverse = homography(moved, corners)
    fill = bytes(scene.background_color[::-1])  # the rows hold B, G, R
    out: list[bytearray] = []
    for y in range(height):
        line = bytearray(fill * width)
        for x in range(width):
            u, v = _apply(inverse, x, y)
            if 0.0 <= u <= width - 1 and 0.0 <= v <= height - 1:
                u0, v0 = int(u), int(v)
                u1, v1 = min(u0 + 1, width - 1), min(v0 + 1, height - 1)
                fu, fv = u - u0, v - v0
                a, b, c, d = rows[v0], rows[v0], rows[v1], rows[v1]
                for ch in range(3):
                    top = a[u0 * 3 + ch] * (1 - fu) + b[u1 * 3 + ch] * fu
                    bottom = c[u0 * 3 + ch] * (1 - fu) + d[u1 * 3 + ch] * fu
                    line[x * 3 + ch] = int(top * (1 - fv) + bottom * fv + 0.5)
        out.append(line)
    kept: list[Component] = []
    for comp in scene.components:
        box = [(comp.x, comp.y), (comp.x + comp.width, comp.y), (comp.x + comp.width, comp.y + comp.height), (comp.x, comp.y + comp.height)]
        points = [_apply(forward, px, py) for px, py in box]
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        full = max(max(xs) - min(xs), 1e-9) * max(max(ys) - min(ys), 1e-9)
        x0, x1 = max(0.0, min(xs)), min(float(width), max(xs))
        y0, y1 = max(0.0, min(ys)), min(float(height), max(ys))
        if x1 - x0 < 2 or y1 - y0 < 2 or (x1 - x0) * (y1 - y0) / full < config.min_visibility:
            continue
        ix0, iy0, ix1, iy1 = int(math.floor(x0)), int(math.floor(y0)), min(width, int(math.ceil(x1))), min(height, int(math.ceil(y1)))
        kept.append(Component(label=comp.label, x=ix0, y=iy0, width=ix1 - ix0, height=iy1 - iy0, color=comp.color))
    return out, Scene(width=width, height=height, background_color=scene.background_color, components=tuple(kept))


def _blur(rows: list[bytearray], width: int, height: int, radius: int) -> list[bytearray]:
    """A box blur of the given radius, rows first, then columns (edges repeat)."""
    size = 2 * radius + 1
    horizontal: list[bytearray] = []
    for row in rows:
        line = bytearray(len(row))
        for ch in range(3):
            padded = [row[ch]] * radius + [row[x * 3 + ch] for x in range(width)] + [row[(width - 1) * 3 + ch]] * radius
            total = sum(padded[:size])
            for x in range(width):
                line[x * 3 + ch] = total // size
                if x + size < len(padded):
                    total += padded[x + size] - padded[x]
        horizontal.append(line)
    result = [bytearray(len(row)) for row in rows]
    for x3 in range(width * 3):
        column = [horizontal[0][x3]] * radius + [horizontal[y][x3] for y in range(height)] + [horizontal[-1][x3]] * radius
        total = sum(column[:size])
        for y in range(height):
            result[y][x3] = total // size
            if y + size < len(column):
                total += column[y + size] - column[y]
    return result


def _noise(rows: list[bytearray], sigma: float, rng: random.Random) -> None:
    for row in rows:
        for i in range(len(row)):
            v = row[i] + rng.gauss(0.0, sigma)
            row[i] = 0 if v < 0 else 255 if v > 255 else int(v + 0.5)


def apply_realism(rows: list[bytearray], scene: Scene, config: RealismConfig, rng: random.Random) -> tuple[list[bytearray], Scene]:
    """The rows (B, G, R) and the scene (with its boxes) after the effects of `config`. The scene comes back as it was when nothing moves."""
    if not config.enabled:
        return rows, scene
    width, height = scene.width, scene.height
    if width * height > config.max_pixels:
        raise RealismError(f"a {width}x{height} image is above max_pixels ({config.max_pixels}) of the realism file")
    rows = [bytearray(r) for r in rows]
    if config.texture_amplitude or config.illumination_strength:
        _texture_and_light(rows, width, height, config, rng)
    if config.rotation_degrees or config.perspective_fraction:
        rows, scene = _warp(rows, width, height, scene, config, rng)
    radius = rng.randint(0, config.blur_radius) if config.blur_radius else 0
    if radius:
        rows = _blur(rows, width, height, radius)
    if config.noise_sigma:
        _noise(rows, config.noise_sigma, rng)
    return rows, scene
