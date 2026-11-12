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
import json
import secrets
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import cast

from .export import Dataset, export_coco, export_coco_by_split, export_yolo
from .manifest import build_manifest, write_manifest
from .realism import RealismError, apply_realism, load_realism_config
from .render import paint_scene, render_bmp, render_png
from .scenarios import (
    PERSON_LABEL,
    SafetyConfig,
    ScenarioError,
    ServoingConfig,
    add_people,
    camera_intrinsics,
    load_model_classes,
    load_safety_config,
    load_servoing_config,
    servoing_scene,
)
from .scene import DEFAULT_LABELS, DEFECT_LABEL, FIXED_CLASSES, Scene, generate_scene
from .shapes import CatalogError, Catalog, Silhouette, load_catalog, top_silhouettes
from .split import LAYOUTS, SPLIT_FILES, assign_splits, parse_split, split_names, write_splits
from .tfrecord import export_tfrecord
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


@dataclass(frozen=True)
class ScenePlan:
    """What the optional scenarios add to the plain procedural scene; None everywhere means the scene of every earlier version."""

    labels: tuple[str, ...] = DEFAULT_LABELS
    shapes: dict[str, tuple[Silhouette, ...]] | None = None
    catalog: Catalog | None = None
    servoing: ServoingConfig | None = None
    safety: SafetyConfig | None = None


def _make_scene(task: tuple) -> tuple[str, Scene, dict]:
    """Generate and render one scene. Top level so a worker process can run it; the result depends only on the task.

    The third element holds the extra annotations of the scenarios (poses, people against zones); empty for a plain scene."""
    base_seed, index, width, height, components, defect_rate, images_dir, image_format, realism = task[:9]
    plan: ScenePlan | None = task[9] if len(task) > 9 else None
    extra: dict = {}
    rng = random.Random(_scene_seed(base_seed, index))
    if plan is not None and plan.servoing is not None and plan.catalog is not None:
        scene, poses = servoing_scene(rng, plan.catalog.parts, plan.servoing, width, height)
        extra["poses"] = poses
    elif plan is not None:
        scene = generate_scene(
            rng, width=width, height=height, num_components=components, defect_probability=defect_rate,
            labels=plan.labels, shapes=plan.shapes,
        )
    else:
        scene = generate_scene(rng, width=width, height=height, num_components=components, defect_probability=defect_rate)
    if plan is not None and plan.safety is not None:
        scene, extra["safety"] = add_people(random.Random(_scene_seed(base_seed, index) ^ 0x5AFE), scene, plan.safety)
    image_name = f"scene_{index:04d}.{image_format}"
    render = render_png if image_format == "png" else render_bmp
    if realism is not None and realism.enabled:
        # the effects have their own generator, seeded from the scene seed, so the scene itself is the one of a run without them
        rows, scene = apply_realism(paint_scene(scene), scene, realism, random.Random(_scene_seed(base_seed, index) ^ 0x5EA1157))
        render(scene, Path(images_dir) / image_name, rows)
    else:
        render(scene, Path(images_dir) / image_name)
    return image_name, scene, extra


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


def _resolve_scenarios(args: argparse.Namespace, errors: list[str]) -> tuple[ScenePlan | None, tuple[str, ...] | None, dict | None]:
    """(plan, exact class list, what the manifest says about the scenarios) from the optional files of `generate`; errors are appended to `errors`.

    Each option is off unless it is given, and a servoing or safety file whose `enabled` is not true changes nothing."""
    model_classes = catalog = None
    servoing: ServoingConfig | None = None
    safety: SafetyConfig | None = None
    if args.classes_from is not None:
        if not args.model:
            errors.append("--classes-from needs --model")
        else:
            try:
                model_classes = load_model_classes(args.classes_from, args.model, args.model_version)
            except ScenarioError as error:
                errors.append(f"--classes-from: {error}")
    elif args.model or args.model_version:
        errors.append("--model and --model-version go with --classes-from")
    if args.catalog is not None:
        try:
            catalog = load_catalog(args.catalog)
        except CatalogError as error:
            errors.append(f"--catalog: {error}")
    for option, loader, name in (("servoing_config", load_servoing_config, "--servoing-config"), ("safety_config", load_safety_config, "--safety-config")):
        value = getattr(args, option)
        if value is None:
            continue
        try:
            loaded = loader(value)
        except ScenarioError as error:
            errors.append(f"{name}: {error}")
            continue
        if loaded.enabled:
            if option == "servoing_config":
                servoing = cast(ServoingConfig, loaded)
            else:
                safety = cast(SafetyConfig, loaded)
        else:
            print(f"note: {name} is not enabled (enabled: true is needed); it is ignored")
    if servoing is not None and catalog is None:
        errors.append("--servoing-config needs --catalog: the poses are those of the parts of the catalogue")
    if errors or (model_classes is None and catalog is None and servoing is None and safety is None):
        return None, None, None

    classes = model_classes.classes if model_classes is not None else None
    labels: tuple[str, ...] = DEFAULT_LABELS
    shapes: dict[str, tuple[Silhouette, ...]] | None = None
    if catalog is not None:
        shapes = {}
        for part in catalog.parts:
            shapes[part.label] = shapes.get(part.label, ()) + top_silhouettes(part)
        missing = [label for label, outlines in shapes.items() if not outlines]
        if missing:
            errors.append(f"--catalog: the part(s) {', '.join(sorted(missing))} have no outline from above (flat or too small)")
        labels = tuple(shapes)
    elif classes is not None:
        labels = tuple(c for c in classes if c != DEFECT_LABEL) or labels
    if classes is not None:
        stray = [label for label in labels if label not in classes]
        if stray:
            errors.append(f"the classes of model {args.model!r} do not include: {', '.join(sorted(stray))}")
        if safety is not None and PERSON_LABEL not in classes:
            errors.append(f"--safety-config puts people in the images but the model {args.model!r} has no class {PERSON_LABEL!r}")
    info: dict[str, object] = {}
    if model_classes is not None:
        info["classes_from"] = model_classes.describe()
    if catalog is not None:
        info["catalog"] = catalog.describe()
    if servoing is not None:
        info["servoing"] = servoing.describe()
    if safety is not None:
        info["safety"] = safety.describe()
    plan = ScenePlan(labels=labels, shapes=shapes, catalog=catalog, servoing=servoing, safety=safety)
    return plan, classes, info


def _run_generate(args: argparse.Namespace) -> int:
    errors: list[str] = []
    plan, classes, scenario = _resolve_scenarios(args, errors)
    if args.width is None or args.height is None:
        # the size of the images is the input of the model when one is given, else the 256 of earlier versions
        if args.classes_from is not None and not errors:
            model = load_model_classes(args.classes_from, args.model, args.model_version)
            args.width = model.width if args.width is None else args.width
            args.height = model.height if args.height is None else args.height
        args.width = 256 if args.width is None else args.width
        args.height = 256 if args.height is None else args.height
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
    realism = None
    if args.realism_config is not None:
        try:
            realism = load_realism_config(args.realism_config)
        except RealismError as error:
            errors.append(f"--realism-config: {error}")
        else:
            if realism.enabled and args.width * args.height > realism.max_pixels:
                errors.append(f"--realism-config: a {args.width}x{args.height} image is above max_pixels ({realism.max_pixels})")
    if classes is not None and DEFECT_LABEL not in classes and args.defect_rate > 0:
        print(f"note: the model has no class {DEFECT_LABEL!r}, so no defect is drawn (--defect-rate is taken as 0)")
        args.defect_rate = 0.0
    fractions = None
    if args.layout == "ultralytics" and args.split is None:
        errors.append("--layout ultralytics needs --split with a val part (images/train, images/val, ...)")
    if args.split is not None:
        try:
            fractions = parse_split(args.split)
        except ValueError as error:
            errors.append(str(error))
        else:
            if args.format == "coco" and args.layout == "flat":
                errors.append("--split writes YOLO lists; use --format yolo or both (or --layout ultralytics)")
            if args.layout == "ultralytics" and fractions.get("val", 0.0) <= 0.0:
                errors.append("--layout ultralytics needs a val part greater than 0 in --split")
    if not errors:
        bytes_per_image = 54 + ((3 * args.width + 3) & ~3) * args.height  # BMP header + 4-byte-aligned rows (the bound for a PNG too)
        total_bytes = bytes_per_image * args.count
        if total_bytes > MAX_DATASET_BYTES:
            errors.append(
                f"{args.count} scene(s) of {args.width}x{args.height} would take about {total_bytes / 1024**3:.1f} GiB "
                f"of images, over the {MAX_DATASET_BYTES // 1024**3} GiB limit - lower --count, --width or --height"
            )
    if errors:
        for message in errors:
            print(f"error: {message}", file=sys.stderr)
        return 2

    out_dir = args.out
    images_dir = out_dir / "images"
    leftovers = [name for name in ("images", "labels", "annotations", "annotations.json", "classes.txt", "manifest.json", "poses.json", "zones.json", "tfrecord", *SPLIT_FILES) if (out_dir / name).exists()]
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

    # the parts depend only on the seed and the number of scenes, so they are known before anything is rendered and each image can go to its folder
    parts = assign_splits(args.count, base_seed, fractions) if fractions is not None else None
    part_of_index = {i: name for name, indexes in parts.items() for i in indexes} if parts is not None else {}
    ultralytics = args.layout == "ultralytics"
    tasks = [
        (base_seed, index, args.width, args.height, args.components, args.defect_rate,
         str(images_dir / part_of_index[index]) if ultralytics else str(images_dir), args.image_format, realism, plan)
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

    extras = {name: extra for name, _, extra in scenes}
    dataset = Dataset(scenes=tuple((name, scene) for name, scene, _ in scenes), classes=classes)
    expected_labels = classes if classes is not None else tuple(dict.fromkeys(
        FIXED_CLASSES + (plan.labels if plan is not None else ()) + ((PERSON_LABEL,) if plan is not None and plan.safety is not None else ())
    ))

    image_parts = split_names([name for name, _ in dataset.scenes], parts) if ultralytics and parts is not None else None
    if args.format in ("yolo", "both"):
        export_yolo(dataset, out_dir, image_parts)
    if args.format in ("coco", "both"):
        if image_parts is not None:
            export_coco_by_split(dataset, out_dir, image_parts)
        else:
            export_coco(dataset, out_dir / "annotations.json")
    if args.tfrecord:
        tfrecords = export_tfrecord(dataset, images_dir, out_dir, image_parts)

    issues = validate_dataset(
        dataset, images_dir, expected_labels=expected_labels, defect_rate=args.defect_rate, image_parts=image_parts
    )
    manifest = build_manifest(
        dataset,
        images_dir,
        seed=base_seed,
        width=args.width,
        height=args.height,
        requested_components=args.components,
        defect_rate=args.defect_rate,
        labels=expected_labels,
        fmt=args.format,
        issues=issues,
        layout=args.layout,
        image_parts=image_parts,
        realism=realism.describe() if realism is not None and realism.enabled else None,
        scenario=scenario,
    )
    write_manifest(manifest, out_dir / "manifest.json")
    _write_extras(out_dir, extras, plan, args.width, args.height)
    if parts is not None:
        write_splits(out_dir, [name for name, _ in dataset.scenes], parts, list(manifest.classes), args.layout)
        print("Split: " + ", ".join(f"{name}={len(idx)}" for name, idx in parts.items()))

    total_components = sum(len(scene.components) for _, scene in dataset.scenes)
    print(f"Generated {args.count} scene(s) -> {images_dir}")
    print(f"Total labeled components (incl. defects): {total_components}")
    print(f"Annotations exported as: {args.format}")
    if args.tfrecord:
        print("TFRecord: " + ", ".join(f"{r.path.name}={r.records}" for r in tfrecords))
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


def _write_extras(out_dir: Path, extras: dict[str, dict], plan: ScenePlan | None, width: int, height: int) -> None:
    """poses.json (servoing) and zones.json (safety) next to the manifest; nothing is written for a plain dataset."""
    if plan is None:
        return
    if plan.servoing is not None:
        payload = {
            "camera": camera_intrinsics(plan.servoing, width, height),
            "frame": "OpenCV camera: x right, y down, z forward",
            "images": {name: extra.get("poses", []) for name, extra in extras.items()},
        }
        with open(out_dir / "poses.json", "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, indent=2))
    if plan.safety is not None:
        zones_payload = {
            "zones": [{"name": z.name, "kind": z.kind, "rect": list(z.rect)} for z in plan.safety.zones],
            "min_overlap": plan.safety.min_overlap,
            "images": {name: extra.get("safety", {"people": [], "expected_action": "clear"}) for name, extra in extras.items()},
        }
        with open(out_dir / "zones.json", "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(zones_payload, indent=2))


MAX_CALIBRATION_IMAGES = 2_000


def _run_calibration(args: argparse.Namespace) -> int:
    """A set of images for the quantization of a model (the calibration of the Hailo Dataflow Compiler asks for a few hundred representative ones):
    PNG files at the size of the model input, in a folder of their own, with a small manifest of their checksums. No labels: calibration needs none."""
    errors: list[str] = []
    if not 1 <= args.count <= MAX_CALIBRATION_IMAGES:
        errors.append(f"--count must be in 1..{MAX_CALIBRATION_IMAGES}")
    for label, value in (("--width", args.width), ("--height", args.height)):
        if not MIN_DIMENSION <= value <= MAX_DIMENSION:
            errors.append(f"{label} must be in {MIN_DIMENSION}..{MAX_DIMENSION}")
    if not 1 <= args.jobs <= MAX_JOBS:
        errors.append(f"--jobs must be in 1..{MAX_JOBS}")
    if not 1 <= args.components <= MAX_COMPONENTS:
        errors.append(f"--components must be in 1..{MAX_COMPONENTS}")
    if not math.isfinite(args.defect_rate) or not 0.0 <= args.defect_rate <= 1.0:
        errors.append("--defect-rate must be a finite value in 0.0..1.0")
    realism = None
    if args.realism_config is not None:
        try:
            realism = load_realism_config(args.realism_config)
        except RealismError as error:
            errors.append(f"--realism-config: {error}")
        else:
            if realism.enabled and args.width * args.height > realism.max_pixels:
                errors.append(f"--realism-config: a {args.width}x{args.height} image is above max_pixels ({realism.max_pixels})")
    if not errors and (54 + ((3 * args.width + 3) & ~3) * args.height) * args.count > MAX_DATASET_BYTES:
        errors.append(f"the set would take more than {MAX_DATASET_BYTES // 1024**3} GiB - lower --count, --width or --height")
    if not errors and args.out.exists() and any(args.out.iterdir()):
        errors.append(f"{args.out} is not empty - choose an empty --out directory")
    if errors:
        for message in errors:
            print(f"error: {message}", file=sys.stderr)
        return 2
    base_seed = args.seed if args.seed is not None else secrets.randbits(31)
    args.out.mkdir(parents=True, exist_ok=True)
    tasks = [(base_seed, index, args.width, args.height, args.components, args.defect_rate, str(args.out), "png", realism) for index in range(args.count)]
    jobs = min(args.jobs, os.cpu_count() or 1, args.count)
    if jobs > 1:
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            made = list(pool.map(_make_scene, tasks, chunksize=max(1, args.count // (jobs * 4))))
    else:
        made = [_make_scene(task) for task in tasks]
    manifest = {
        "purpose": "calibration set for the quantization of a model; images only, no labels",
        "seed": base_seed, "count": args.count, "width": args.width, "height": args.height, "format": "png",
        "realism": realism.describe() if realism is not None and realism.enabled else None,
        "images": [{"image": name, "sha256": hashlib.sha256((args.out / name).read_bytes()).hexdigest()} for name, _, _ in made],
    }
    with open(args.out / "calibration.json", "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(manifest, indent=2))
    print(f"Calibration set: {args.count} PNG image(s) of {args.width}x{args.height} -> {args.out}")
    print(f"Seed: {base_seed} ({'given' if args.seed is not None else 'drawn at random and recorded in calibration.json'})")
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
    generate_parser.add_argument("--width", type=int, default=None, help="Image width in pixels (default: the input width of --model when given, else 256).")
    generate_parser.add_argument("--height", type=int, default=None, help="Image height in pixels (default: the input height of --model when given, else 256).")
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
        "--tfrecord", action="store_true",
        help="Also write tfrecord/<part>.tfrecord (tfrecord/all.tfrecord without the ultralytics layout): the images and their boxes as tf.train.Example "
        "records of the TensorFlow Object Detection API, written without TensorFlow. Off by default.",
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
        "--layout", choices=LAYOUTS, default="flat",
        help="flat (default): images/ and labels/ hold everything and the parts are lists. ultralytics: images/<part>/, labels/<part>/ and "
        "annotations/instances_<part>.json, with a data.yaml that names the folders; needs --split with a val part.",
    )
    generate_parser.add_argument(
        "--realism-config", default=None, metavar="FILE",
        help="JSON file with the effects that make the images look less flat (texture, uneven light, rotation, perspective, blur, noise); off unless the file says enabled: true.",
    )
    generate_parser.add_argument(
        "--split", default=None, metavar="train=A,val=B,test=C",
        help="Also write train.txt/val.txt/test.txt, data.yaml and splits.json (fractions adding up to 1). The assignment "
        "depends only on the seed and the scene index.",
    )

    generate_parser.add_argument(
        "--classes-from", default=None, metavar="REGISTRY",
        help="Registry file of HYDRA-UMC-DETECTION-HEF (a JSON array). With --model the dataset has exactly the classes of that model, in its order, "
        "and the size of its input.",
    )
    generate_parser.add_argument("--model", default=None, help="Name of the model in the registry (the newest stable version unless --model-version).")
    generate_parser.add_argument("--model-version", default=None, metavar="X.Y.Z", help="Version of the model in the registry.")
    generate_parser.add_argument(
        "--catalog", default=None, metavar="FILE",
        help="Catalogue of parts (JSON with STL or URDF files next to it): the objects are drawn with the outline of the real parts instead of rectangles.",
    )
    generate_parser.add_argument(
        "--servoing-config", default=None, metavar="FILE",
        help="JSON file (off unless it says enabled: true; needs --catalog): parts at sampled 6-DOF poses in front of a pinhole camera; the poses go to poses.json.",
    )
    generate_parser.add_argument(
        "--safety-config", default=None, metavar="FILE",
        help="JSON file (off unless it says enabled: true) with rectangular zones: stylised people are placed in and out of them; zones.json says where and what a safety system should do.",
    )

    calibration_parser = subparsers.add_parser(
        "calibration", help="A set of PNG images, without labels, for the quantization of a model (a few hundred at the size of its input)."
    )
    calibration_parser.add_argument("--out", type=Path, required=True, help="Output directory (empty or new).")
    calibration_parser.add_argument("--count", type=int, default=256, help=f"Number of images (default: 256, up to {MAX_CALIBRATION_IMAGES}).")
    calibration_parser.add_argument("--width", type=int, default=640, help="Image width, the width of the model input (default: 640).")
    calibration_parser.add_argument("--height", type=int, default=640, help="Image height, the height of the model input (default: 640).")
    calibration_parser.add_argument("--components", type=int, default=5, help="Components per scene (default: 5).")
    calibration_parser.add_argument("--defect-rate", type=float, default=0.2, help="Probability of a defect per component (default: 0.2).")
    calibration_parser.add_argument("--seed", type=int, default=None, help="Base random seed (default: random, recorded in calibration.json).")
    calibration_parser.add_argument("--jobs", type=int, default=1, help=f"Processes that render images (default: 1, up to {MAX_JOBS}).")
    calibration_parser.add_argument("--realism-config", default=None, metavar="FILE", help="JSON file with the realism effects; off unless the file says enabled: true.")

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
    if args.command == "calibration":
        return _run_calibration(args)

    _print_identity()
    return 0


if __name__ == "__main__":
    sys.exit(main())
