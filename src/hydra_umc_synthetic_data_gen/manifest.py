# =============================================================================
# HYDRA-UMC-SYNTHETIC-DATA-GEN - src/hydra_umc_synthetic_data_gen/manifest.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
"""Real dataset manifest: what was actually generated, how, and whether it
passed validation - written as manifest.json alongside the images/labels
so a consumer never has to guess the generation parameters, trust an
unverified dataset, or re-render to check whether two runs match.

Each scene entry carries a real sha256 of its rendered BMP bytes, which
is what makes "reproducible seed" a checkable claim rather than a
comment: two runs with the same seed must produce byte-identical
checksums, and the regression test in test_manifest.py proves it.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .export import Dataset, class_names
from .scene import Scene
from .validate import ValidationIssue


@dataclass(frozen=True)
class SceneManifestEntry:
    image: str
    num_components: int
    label_counts: dict[str, int]
    sha256: str


@dataclass(frozen=True)
class DatasetManifest:
    seed: int | None
    reproducible: bool
    count: int
    width: int
    height: int
    requested_components: int
    defect_rate: float
    labels: tuple[str, ...]
    format: str
    scenes: tuple[SceneManifestEntry, ...]
    validation_issues: tuple[str, ...]
    # The class list exactly as the exports use it (FIXED_CLASSES first, then any other label seen), in order, and a
    # hash of it: a consumer that registers a model trained on this dataset can check that the class order it was
    # trained with is this one. The hash is of the text of classes.txt, so `sha256sum classes.txt` gives the same.
    classes: tuple[str, ...] = ()
    classes_sha256: str = ""

    @property
    def is_clean(self) -> bool:
        return len(self.validation_issues) == 0


def classes_hash(classes: tuple[str, ...] | list[str]) -> str:
    """sha256 of the class list written as classes.txt writes it: one name a line, a final newline."""
    return hashlib.sha256(("\n".join(classes) + "\n").encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _label_counts(scene: Scene) -> dict[str, int]:
    counts: dict[str, int] = {}
    for c in scene.components:
        counts[c.label] = counts.get(c.label, 0) + 1
    return counts


def build_manifest(
    dataset: Dataset,
    images_dir: Path,
    *,
    seed: int | None,
    width: int,
    height: int,
    requested_components: int,
    defect_rate: float,
    labels: tuple[str, ...],
    fmt: str,
    issues: list[ValidationIssue],
) -> DatasetManifest:
    scene_entries = tuple(
        SceneManifestEntry(
            image=image_name,
            num_components=len(scene.components),
            label_counts=_label_counts(scene),
            sha256=_sha256_file(images_dir / image_name),
        )
        for image_name, scene in dataset.scenes
    )
    classes = tuple(class_names(dataset))
    return DatasetManifest(
        seed=seed,
        reproducible=seed is not None,
        count=len(dataset.scenes),
        width=width,
        height=height,
        requested_components=requested_components,
        defect_rate=defect_rate,
        labels=tuple(labels),
        format=fmt,
        scenes=scene_entries,
        validation_issues=tuple(f"{issue.kind}: {issue.detail}" for issue in issues),
        classes=classes,
        classes_sha256=classes_hash(classes),
    )


def write_manifest(manifest: DatasetManifest, path: Path) -> None:
    payload = {
        "seed": manifest.seed,
        "reproducible": manifest.reproducible,
        "count": manifest.count,
        "width": manifest.width,
        "height": manifest.height,
        "requested_components": manifest.requested_components,
        "defect_rate": manifest.defect_rate,
        "labels": list(manifest.labels),
        "format": manifest.format,
        "scenes": [
            {
                "image": entry.image,
                "num_components": entry.num_components,
                "label_counts": entry.label_counts,
                "sha256": entry.sha256,
            }
            for entry in manifest.scenes
        ],
        "validation_issues": list(manifest.validation_issues),
        "classes": list(manifest.classes),
        "classes_sha256": manifest.classes_sha256,
    }
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, indent=2))
