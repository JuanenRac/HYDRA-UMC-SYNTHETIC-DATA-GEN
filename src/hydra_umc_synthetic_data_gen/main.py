# =============================================================================
# HYDRA-UMC-SYNTHETIC-DATA-GEN - src/hydra_umc_synthetic_data_gen/main.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
"""Entry point for HYDRA-UMC-SYNTHETIC-DATA-GEN.

Bare invocation prints identity/version/role, unchanged from the
scaffolding stage. The real v0 work lives behind the `generate`
subcommand: real procedural 2D scene generation (scene.py), real
stdlib-only BMP rasterization (render.py), real YOLO/COCO annotation
export (export.py), a real dataset manifest with per-image checksums
(manifest.py), and real post-generation validation of scene bounds,
BMP integrity, and label distribution (validate.py) - honestly a 2D
placeholder pipeline, not the real photorealistic 3D rendering through
HYDRA-UMC-TWIN's engine the README's own roadmap describes (that engine
doesn't exist yet).
"""
from __future__ import annotations

import argparse
import random
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from .export import Dataset, export_coco, export_yolo
from .manifest import build_manifest, write_manifest
from .render import render_bmp
from .scene import DEFAULT_LABELS, generate_scene
from .validate import validate_dataset

PROJECT_NAME = "HYDRA-UMC-SYNTHETIC-DATA-GEN"
DIST_NAME = "hydra-umc-synthetic-data-gen"
ROLE = (
    "Procedural generator of training datasets for Vision nodes, rendered "
    "through the Digital Twin's physics/rendering engine."
)


def get_version() -> str:
    """Read the running version from installed package metadata, which is
    sourced from pyproject.toml - the single place bump_version.py edits."""
    try:
        return version(DIST_NAME)
    except PackageNotFoundError:
        return "0.0.0-dev (package not installed - run build.sh/build.bat first)"


def _print_identity() -> None:
    print(f"{PROJECT_NAME} v{get_version()}")
    print(ROLE)


def _run_generate(args: argparse.Namespace) -> int:
    out_dir = args.out
    images_dir = out_dir / "images"
    scenes: list[tuple[str, object]] = []

    for index in range(args.count):
        seed = args.seed + index if args.seed is not None else None
        rng = random.Random(seed)
        scene = generate_scene(
            rng,
            width=args.width,
            height=args.height,
            num_components=args.components,
            defect_probability=args.defect_rate,
        )
        image_name = f"scene_{index:04d}.bmp"
        render_bmp(scene, images_dir / image_name)
        scenes.append((image_name, scene))

    dataset = Dataset(scenes=tuple(scenes))

    if args.format in ("yolo", "both"):
        export_yolo(dataset, out_dir)
    if args.format in ("coco", "both"):
        export_coco(dataset, out_dir / "annotations.json")

    issues = validate_dataset(
        dataset, images_dir, expected_labels=DEFAULT_LABELS, defect_rate=args.defect_rate
    )
    manifest = build_manifest(
        dataset,
        images_dir,
        seed=args.seed,
        width=args.width,
        height=args.height,
        requested_components=args.components,
        defect_rate=args.defect_rate,
        labels=DEFAULT_LABELS,
        fmt=args.format,
        issues=issues,
    )
    write_manifest(manifest, out_dir / "manifest.json")

    total_components = sum(len(scene.components) for _, scene in dataset.scenes)
    print(f"Generated {args.count} scene(s) -> {images_dir}")
    print(f"Total labeled components (incl. defects): {total_components}")
    print(f"Annotations exported as: {args.format}")
    print(f"Reproducible seed: {'yes (seed=' + str(args.seed) + ')' if manifest.reproducible else 'no (random)'}")
    print(f"Manifest written -> {out_dir / 'manifest.json'}")

    if issues:
        print(f"VALIDATION FAILED - {len(issues)} issue(s):")
        for issue in issues:
            print(f"  [{issue.kind}] {issue.detail}")
        return 1

    print("Validation: OK (scene bounds, BMP integrity, label distribution)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hydra-umc-synthetic-data-gen", description=ROLE)
    subparsers = parser.add_subparsers(dest="command")

    generate_parser = subparsers.add_parser(
        "generate", help="Real procedural 2D scene generation with YOLO/COCO export."
    )
    generate_parser.add_argument("--out", type=Path, required=True, help="Output directory.")
    generate_parser.add_argument("--count", type=int, default=10, help="Number of scenes (default: 10).")
    generate_parser.add_argument("--width", type=int, default=256, help="Image width in pixels (default: 256).")
    generate_parser.add_argument("--height", type=int, default=256, help="Image height in pixels (default: 256).")
    generate_parser.add_argument(
        "--components", type=int, default=5, help="Components per scene (default: 5)."
    )
    generate_parser.add_argument(
        "--defect-rate", type=float, default=0.2, help="Probability of a defect per component (default: 0.2)."
    )
    generate_parser.add_argument(
        "--seed", type=int, default=None, help="Base random seed for reproducible datasets (default: random)."
    )
    generate_parser.add_argument(
        "--format", choices=("yolo", "coco", "both"), default="both", help="Annotation export format (default: both)."
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "generate":
        return _run_generate(args)

    _print_identity()
    return 0


if __name__ == "__main__":
    sys.exit(main())
