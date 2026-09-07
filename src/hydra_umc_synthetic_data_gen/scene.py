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
class Component:
    """One real placed rectangle: a component or a defect overlay."""

    label: str
    x: int
    y: int
    width: int
    height: int
    color: tuple[int, int, int]


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

    # Real bug found by an ecosystem-wide audit: min_size/max_size are
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
            components.append(
                Component(label=DEFECT_LABEL, x=dx, y=dy, width=dw, height=dh, color=(200, 30, 30))
            )

    return Scene(width=width, height=height, background_color=background_color, components=tuple(components))
