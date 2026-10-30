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
import hashlib
import math
import os
import random
import secrets
import sys
from concurrent.futures import ProcessPoolExecutor
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from .export import Dataset, export_coco, export_yolo
from .manifest import build_manifest, write_manifest
from .render import render_bmp, render_png
from .scene import FIXED_CLASSES, generate_scene
from .split import SPLIT_FILES, assign_splits, parse_split, write_splits
from .validate import validate_dataset
from .verify import verify_output

PROJECT_NAME = "HYDRA-UMC-SYNTHETIC-DATA-GEN"
DIST_NAME = "hydra-umc-synthetic-data-gen"
ROLE = (
    "Procedural generator of training datasets for Vision nodes "
    "(rendering through the Digital Twin's physics engine is planned)."
)
MIN_DIMENSION = 16
MAX_DIMENSION = 4096
MAX_SCENES = 10_000
MAX_COMPONENTS = 1_000
# Each scene is an uncompressed 24-bit BMP, so the individual limits above still allow
# 10,000 scenes of 4096x4096 (about 500 GB) from one command, which would silently fill
# the disk of the machine it runs on (a CM5 has a few tens of GB). The size of the whole
# dataset is bounded as well.
MAX_DATASET_BYTES = 4 * 1024**3


MAX_JOBS = 32


def _scene_seed(base_seed: int, index: int) -> int:
    """Each scene's seed is a hash of the base seed and its index, so two runs with nearby seeds (train 0, val 50) do
    not share scenes, and a scene never depends on how many other scenes there are or on which process makes it."""
    digest = hashlib.sha256(f"{base_seed}:{index}".encode("ascii")).digest()
    return int.from_bytes(digest[:8], "big")


def _make_scene(task: tuple[int, int, int, int, int, float, str, str]) -> tuple[str, object]:
    """Generate and render one scene. Top level so a worker process can run it; the result depends only on the task."""
    base_seed, index, width, height, components, defect_rate, images_dir, image_format = task
    scene = generate_scene(
        random.Random(_scene_seed(base_seed, index)),
        width=width,
        height=height,
        num_components=components,
        defect_probability=defect_rate,
    )
    image_name = f"scene_{index:04d}.{image_format}"
    (render_png if image_format == "png" else render_bmp)(scene, Path(images_dir) / image_name)
    return image_name, scene


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
    errors: list[str] = []
    if not 1 <= args.count <= MAX_SCENES:
        errors.append(f"--count must be in 1..{MAX_SCENES}")
    for label, value in (("--width", args.width), ("--height", args.height)):
        if not MIN_DIMENSION <= value <= MAX_DIMENSION:
            errors.append(f"{label} must be in {MIN_DIMENSION}..{MAX_DIMENSION}")
    if not 1 <= args.jobs <= MAX_JOBS:
        errors.append(f"--jobs must be in 1..{MAX_JOBS}")
    if not 1 <= args.components <= MAX_COMPONENTS:
        errors.append(f"--components must be in 1..{MAX_COMPONENTS}")
    if not math.isfinite(args.defect_rate) or not 0.0 <= args.defect_rate <= 1.0:
        errors.append("--defect-rate must be a finite value in 0.0..1.0")
    fractions = None
    if args.split is not None:
        try:
            fractions = parse_split(args.split)
        except ValueError as error:
            errors.append(str(error))
        else:
            if args.format == "coco":
                errors.append("--split writes YOLO lists; use --format yolo or both")
    if not errors:
        bytes_per_image = 54 + ((3 * args.width + 3) & ~3) * args.height  # BMP header + 4-byte-aligned rows (the bound for a PNG too)
        total_bytes = bytes_per_image * args.count
        if total_bytes > MAX_DATASET_BYTES:
            errors.append(
                f"{args.count} scene(s) of {args.width}x{args.height} would take about {total_bytes / 1024**3:.1f} GiB "
                f"of images, over the {MAX_DATASET_BYTES // 1024**3} GiB limit - lower --count, --width or --height"
            )
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 2

    out_dir = args.out
    images_dir = out_dir / "images"
    leftovers = [name for name in ("images", "labels", "annotations.json", "classes.txt", "manifest.json", *SPLIT_FILES) if (out_dir / name).exists()]
    if leftovers:
        # Generating over an old dataset would leave its files next to the new
        # ones, and a trainer that lists the folder would pick up both.
        print(
            f"error: {out_dir} already holds a dataset ({', '.join(leftovers)}) - choose an empty --out directory",
            file=sys.stderr,
        )
        return 2

    # Without --seed one is drawn and recorded, so the dataset can always be reproduced.
    base_seed = args.seed if args.seed is not None else secrets.randbits(31)

    tasks = [
        (base_seed, index, args.width, args.height, args.components, args.defect_rate, str(images_dir), args.image_format)
        for index in range(args.count)
    ]
    jobs = min(args.jobs, os.cpu_count() or 1, args.count)
    if jobs > 1:
        # Every scene has its own random generator seeded from (seed, index), so the scenes come out the same as with
        # one job; map() keeps them in order.
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            scenes = list(pool.map(_make_scene, tasks, chunksize=max(1, args.count // (jobs * 4))))
    else:
        scenes = [_make_scene(task) for task in tasks]

    dataset = Dataset(scenes=tuple(scenes))

    if args.format in ("yolo", "both"):
        export_yolo(dataset, out_dir)
    if args.format in ("coco", "both"):
        export_coco(dataset, out_dir / "annotations.json")

    issues = validate_dataset(
        dataset, images_dir, expected_labels=FIXED_CLASSES, defect_rate=args.defect_rate
    )
    manifest = build_manifest(
        dataset,
        images_dir,
        seed=base_seed,
        width=args.width,
        height=args.height,
        requested_components=args.components,
        defect_rate=args.defect_rate,
        labels=FIXED_CLASSES,
        fmt=args.format,
        issues=issues,
    )
    write_manifest(manifest, out_dir / "manifest.json")
    if fractions is not None:
        parts = assign_splits(args.count, base_seed, fractions)
        write_splits(out_dir, [name for name, _ in dataset.scenes], parts, list(manifest.classes))
        print("Split: " + ", ".join(f"{name}={len(idx)}" for name, idx in parts.items()))

    total_components = sum(len(scene.components) for _, scene in dataset.scenes)
    print(f"Generated {args.count} scene(s) -> {images_dir}")
    print(f"Total labeled components (incl. defects): {total_components}")
    print(f"Annotations exported as: {args.format}")
    print(f"Seed: {base_seed} ({'given' if args.seed is not None else 'drawn at random and recorded in the manifest'})")
    print(f"Manifest written -> {out_dir / 'manifest.json'}")

    # what is on disk, read back: the labels and annotations against the scenes, the images against the manifest
    issues = list(issues) + verify_output(out_dir)
    if issues:
        print(f"VALIDATION FAILED - {len(issues)} issue(s):")
        for issue in issues:
            print(f"  [{issue.kind}] {issue.detail}")
        return 1

    print("Validation: OK (scene bounds, image integrity, label distribution, exported files against the manifest)")
    return 0


def _run_verify(args: argparse.Namespace) -> int:
    issues = verify_output(args.out)
    if issues:
        print(f"VERIFY=FAIL {len(issues)} issue(s) in {args.out}:")
        for issue in issues:
            print(f"  [{issue.kind}] {issue.detail}")
        return 1
    print(f"VERIFY=PASS {args.out} is what its manifest says")
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
    generate_parser.add_argument(
        "--image-format", choices=("bmp", "png"), default="bmp",
        help="Image file format (default: bmp). png is compressed, so the dataset is smaller; the pixels are the same.",
    )
    generate_parser.add_argument(
        "--jobs", type=int, default=1,
        help=f"Processes that render scenes (default: 1, up to {MAX_JOBS}). The dataset is the same whatever the number.",
    )

    generate_parser.add_argument(
        "--split", default=None, metavar="train=A,val=B,test=C",
        help="Also write train.txt/val.txt/test.txt, data.yaml and splits.json (fractions adding up to 1). The assignment "
        "depends only on the seed and the scene index.",
    )

    verify_parser = subparsers.add_parser(
        "verify", help="Read a dataset folder back and check it against its own manifest (images, labels, annotations, classes)."
    )
    verify_parser.add_argument("--out", type=Path, required=True, help="The dataset folder to check.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "generate":
        return _run_generate(args)
    if args.command == "verify":
        return _run_verify(args)

    _print_identity()
    return 0


if __name__ == "__main__":
    sys.exit(main())
