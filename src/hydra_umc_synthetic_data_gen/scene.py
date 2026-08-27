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

    for _ in range(num_components):
        w = rng.randint(min_size, max_size)
        h = rng.randint(min_size, max_size)
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
