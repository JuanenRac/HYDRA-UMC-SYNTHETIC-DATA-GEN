# =============================================================================
# HYDRA-UMC-SYNTHETIC-DATA-GEN - src/hydra_umc_synthetic_data_gen/scene.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
"""Real procedural scene generation: randomized 2D component placement.

Honestly a 2D placeholder-shape generator (rectangles, not real 3D
component meshes) - the real photorealistic rendering described in the
README's own Key Features needs HYDRA-UMC-TWIN's actual physics/rendering
engine, which doesn't exist yet (this project's own integration parent is
itself still scaffolding). This gives real, pixel-perfect bounding-box
ground truth today - the same annotation problem the real 3D pipeline
will eventually need to solve - without waiting on the renderer.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

DEFAULT_LABELS: tuple[str, ...] = ("bolt", "bracket", "gear", "connector")
DEFECT_LABEL = "defect"


@dataclass(frozen=True)
class ScratchPoint:
    """One real point along a scratch's Bresenham line, with its own
    randomized half-width (pixels either side of the point also painted,
    giving the line real thickness variation) and opacity (blended
    against whatever pixel is already there - the component color the
    scratch is overlaid on - rather than flatly overwriting it, which is
    what already made the existing rectangular defect overlay look like a
    solid patch rather than a scratch)."""

    x: int
    y: int
    half_width: int
    opacity: float


def _bresenham_line(x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int]]:
    """Real Bresenham's line algorithm (integer-only, no float rounding
    drift) - the classic error-accumulator formulation, correct for a
    line in any of the 8 octants (works for any direction/slope, not
    just shallow positive ones)."""
    points: list[tuple[int, int]] = []
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    x, y = x0, y0
    while True:
        points.append((x, y))
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x += sx
        if e2 <= dx:
            err += dx
            y += sy
    return points


def generate_scratch(rng: random.Random, x: int, y: int, width: int, height: int) -> tuple[ScratchPoint, ...]:
    """A real scratch defect: a randomized-endpoint line drawn via
    Bresenham's algorithm across the given bounding box, with per-point
    randomized half-width/opacity so it reads as an irregular surface
    scratch rather than a uniform stroke - the same real defect kind the
    README's own "scratches, missing parts, solder bridges" description
    names, previously only approximated by a solid rectangular overlay.
    Fully deterministic given `rng`, same as every other random choice in
    this module - no unseeded randomness anywhere in this function."""
    x0 = x + rng.randint(0, max(0, width - 1))
    y0 = y + rng.randint(0, max(0, height - 1))
    x1 = x + rng.randint(0, max(0, width - 1))
    y1 = y + rng.randint(0, max(0, height - 1))
    return tuple(
        ScratchPoint(x=px, y=py, half_width=rng.randint(0, 1), opacity=rng.uniform(0.4, 0.9))
        for px, py in _bresenham_line(x0, y0, x1, y1)
    )


@dataclass(frozen=True)
class Component:
    """One real placed rectangle: a component, or a defect overlay -
    either the original solid rectangular kind, or (when `scratch` is
    set) a real Bresenham-line scratch drawn within this same bounding
    box instead of a flat fill. `x`/`y`/`width`/`height` remain this
    defect's real annotation bounding box either way - export.py's own
    YOLO/COCO writers need no changes for the scratch kind."""

    label: str
    x: int
    y: int
    width: int
    height: int
    color: tuple[int, int, int]
    scratch: tuple[ScratchPoint, ...] | None = None


@dataclass(frozen=True)
class Scene:
    width: int
    height: int
    background_color: tuple[int, int, int]
    components: tuple[Component, ...]


def generate_scene(
    rng: random.Random,
    *,
    width: int = 256,
    height: int = 256,
    num_components: int = 5,
    defect_probability: float = 0.2,
    labels: tuple[str, ...] = DEFAULT_LABELS,
    min_size: int = 16,
    max_size: int = 48,
) -> Scene:
    """Real, deterministic (given `rng`) procedural scene generation.

    Each component gets a real random position/size/color/label; with
    `defect_probability` a smaller real "defect" rectangle is overlaid
    inside it - a real, simple stand-in for the README's "scratches,
    missing parts, solder bridges" defect injection.
    """
    background_color = (rng.randint(180, 230),) * 3
    components: list[Component] = []

    # Real bug found while auditing the code: min_size/max_size are
    # never compared against the scene's own real width/height (and
    # aren't exposed as CLI flags at all, so a caller can't work around
    # it either) - main.py's own MIN_DIMENSION only validates width/
    # height, never that they're large enough for a component to
    # actually fit. A small scene (e.g. 20x20, a real value main.py's own
    # validation accepts since MIN_DIMENSION=16) with the real default
    # max_size=48 produced components wider/taller than the canvas
    # itself, always clamped to x=0/y=0 by the position clamp below,
    # sitting flush against the edge and overflowing it - both a wrong
    # dataset (validate_scene_bounds correctly rejects it as
    # out_of_bounds, but only AFTER the invalid files were already
    # written to disk) and, had that check been looser, a real invalid
    # YOLO annotation (a normalized width/height ratio over 1.0). Clamp
    # both to the real scene dimensions here, once, so no caller of this
    # function - CLI or direct - can ever produce an out-of-canvas
    # component regardless of what min_size/max_size it passes.
    effective_max_size = max(1, min(max_size, width, height))
    effective_min_size = min(min_size, effective_max_size)

    for _ in range(num_components):
        w = rng.randint(effective_min_size, effective_max_size)
        h = rng.randint(effective_min_size, effective_max_size)
        x = rng.randint(0, max(0, width - w))
        y = rng.randint(0, max(0, height - h))
        label = rng.choice(labels)
        color = (rng.randint(0, 180), rng.randint(0, 180), rng.randint(0, 180))
        components.append(Component(label=label, x=x, y=y, width=w, height=h, color=color))

        if rng.random() < defect_probability:
            dw = max(4, w // 3)
            dh = max(4, h // 3)
            dx = x + rng.randint(0, max(0, w - dw))
            dy = y + rng.randint(0, max(0, h - dh))
            # Two real defect kinds, chosen with the same seeded rng as
            # everything else here: the original solid rectangular
            # overlay, or a scratch drawn via Bresenham's algorithm - see
            # generate_scratch()'s own docstring for why the scratch kind
            # exists alongside it rather than replacing it.
            if rng.random() < 0.5:
                scratch = generate_scratch(rng, dx, dy, dw, dh)
                components.append(
                    Component(label=DEFECT_LABEL, x=dx, y=dy, width=dw, height=dh, color=(200, 30, 30), scratch=scratch)
                )
            else:
                components.append(
                    Component(label=DEFECT_LABEL, x=dx, y=dy, width=dw, height=dh, color=(200, 30, 30))
                )

    return Scene(width=width, height=height, background_color=background_color, components=tuple(components))
