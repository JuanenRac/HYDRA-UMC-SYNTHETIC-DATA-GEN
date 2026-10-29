# =============================================================================
# HYDRA-UMC-SYNTHETIC-DATA-GEN - src/hydra_umc_synthetic_data_gen/verify.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
"""Checks a finished dataset directory against its own manifest and against itself.

validate.py checks the scenes in memory while they are generated. What a trainer receives is the directory, so this
reads the directory back: the images against the checksums of manifest.json, the YOLO labels and the COCO annotations
against the scenes and against each other, and the class list against its hash. It needs nothing but the folder, so it
also runs on a dataset copied from another machine (`verify --out DIR`).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .manifest import classes_hash
from .split import check_splits
from .validate import ValidationIssue

_SLACK = 1e-6  # YOLO coordinates are written with six decimals


def _issue(kind: str, detail: str) -> ValidationIssue:
    return ValidationIssue(kind, detail)


def _read_json(path: Path, kind: str, issues: list[ValidationIssue]) -> object | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        issues.append(_issue(kind, f"{path.name} cannot be read: {exc}"))
        return None


def _check_yolo_label(stem: str, path: Path, class_count: int | None, issues: list[ValidationIssue]) -> list[int]:
    """The class ids of a label file, after checking every line."""
    ids: list[int] = []
    try:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError as exc:
        issues.append(_issue("missing_label", f"{stem}: label file cannot be read: {exc}"))
        return ids
    for number, line in enumerate(lines, start=1):
        fields = line.split()
        where = f"{stem}.txt line {number}"
        if len(fields) != 5:
            issues.append(_issue("bad_yolo_line", f"{where}: {len(fields)} fields, expected 5"))
            continue
        try:
            class_id = int(fields[0])
            cx, cy, w, h = (float(value) for value in fields[1:])
        except ValueError:
            issues.append(_issue("bad_yolo_line", f"{where}: not numbers"))
            continue
        if class_count is not None and not 0 <= class_id < class_count:
            issues.append(_issue("bad_yolo_class", f"{where}: class id {class_id} outside 0..{class_count - 1}"))
        if not all(0.0 <= value <= 1.0 for value in (cx, cy, w, h)) or w <= 0 or h <= 0:
            issues.append(_issue("yolo_out_of_range", f"{where}: values must be inside [0, 1] with a positive size"))
        elif cx - w / 2 < -_SLACK or cx + w / 2 > 1 + _SLACK or cy - h / 2 < -_SLACK or cy + h / 2 > 1 + _SLACK:
            issues.append(_issue("yolo_out_of_range", f"{where}: the box leaves the image"))
        ids.append(class_id)
    return ids


def _check_coco(path: Path, classes: list[str], issues: list[ValidationIssue]) -> dict[str, int]:
    """Checks annotations.json; returns how many annotations each image file has."""
    counts: dict[str, int] = {}
    data = _read_json(path, "bad_coco", issues)
    if not isinstance(data, dict):
        return counts
    categories = data.get("categories", [])
    category_ids = [c.get("id") for c in categories if isinstance(c, dict)]
    if len(set(category_ids)) != len(category_ids):
        issues.append(_issue("coco_duplicate_id", "category ids are not unique"))
    if classes and [c.get("name") for c in categories if isinstance(c, dict)] != classes:
        issues.append(_issue("class_mismatch", "COCO categories are not the class list of the manifest, in its order"))
    image_ids: dict[object, tuple[str, int, int]] = {}
    for image in data.get("images", []):
        if not isinstance(image, dict):
            continue
        if image.get("id") in image_ids:
            issues.append(_issue("coco_duplicate_id", f"image id {image.get('id')} is used twice"))
        image_ids[image.get("id")] = (str(image.get("file_name")), int(image.get("width", 0)), int(image.get("height", 0)))
        counts.setdefault(str(image.get("file_name")), 0)
    seen_annotation_ids: set[object] = set()
    for annotation in data.get("annotations", []):
        if not isinstance(annotation, dict):
            continue
        identifier = annotation.get("id")
        if identifier in seen_annotation_ids:
            issues.append(_issue("coco_duplicate_id", f"annotation id {identifier} is used twice"))
        seen_annotation_ids.add(identifier)
        if annotation.get("image_id") not in image_ids:
            issues.append(_issue("coco_dangling", f"annotation {identifier} names image {annotation.get('image_id')}, which is not listed"))
            continue
        name, width, height = image_ids[annotation["image_id"]]
        counts[name] = counts.get(name, 0) + 1
        if annotation.get("category_id") not in category_ids:
            issues.append(_issue("coco_dangling", f"annotation {identifier} names category {annotation.get('category_id')}, which is not listed"))
        box = annotation.get("bbox")
        if not (isinstance(box, list) and len(box) == 4 and all(isinstance(v, (int, float)) for v in box)):
            issues.append(_issue("bad_coco", f"annotation {identifier} has no usable bbox"))
            continue
        x, y, w, h = box
        if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > width or y + h > height:
            issues.append(_issue("coco_out_of_range", f"annotation {identifier}: bbox {box} leaves the {width}x{height} image"))
        if annotation.get("area") != w * h:
            issues.append(_issue("bad_coco", f"annotation {identifier}: area is not width x height"))
    return counts


def verify_output(out_dir: Path) -> list[ValidationIssue]:
    """Every problem found in the dataset folder `out_dir`; an empty list means it is what its manifest says."""
    issues: list[ValidationIssue] = []
    manifest = _read_json(out_dir / "manifest.json", "missing_manifest", issues)
    if not isinstance(manifest, dict):
        return issues

    fmt = manifest.get("format", "both")
    classes = manifest.get("classes")
    if not isinstance(classes, list) or not all(isinstance(c, str) for c in classes):
        # a manifest written before the class list was recorded: the labels it was made with are the start of the list
        classes = []
        issues.append(_issue("class_mismatch", "the manifest has no class list (made by an older version); class ids cannot be checked"))
    elif manifest.get("classes_sha256") != classes_hash(classes):
        issues.append(_issue("class_mismatch", "classes_sha256 of the manifest is not the hash of its own class list"))
    if fmt in ("yolo", "both"):
        try:
            on_disk = (out_dir / "classes.txt").read_text(encoding="utf-8")
        except OSError:
            on_disk = None
            issues.append(_issue("class_mismatch", "classes.txt is missing"))
        if on_disk is not None and classes and hashlib.sha256(on_disk.encode("utf-8")).hexdigest() != classes_hash(classes):
            issues.append(_issue("class_mismatch", "classes.txt is not the class list of the manifest"))

    scenes = manifest.get("scenes", [])
    if manifest.get("count") != len(scenes):
        issues.append(_issue("manifest_mismatch", f"the manifest says {manifest.get('count')} scene(s) and lists {len(scenes)}"))

    listed = {scene.get("image") for scene in scenes if isinstance(scene, dict)}
    images_dir = out_dir / "images"
    if images_dir.is_dir():
        for extra in sorted(p.name for p in images_dir.iterdir() if p.is_file() and p.name not in listed):
            issues.append(_issue("unexpected_file", f"images/{extra} is not in the manifest"))

    coco_counts: dict[str, int] = {}
    if fmt in ("coco", "both"):
        coco_counts = _check_coco(out_dir / "annotations.json", classes, issues)

    labels_dir = out_dir / "labels"
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        name = str(scene.get("image"))
        image_path = images_dir / name
        if not image_path.is_file():
            issues.append(_issue("missing_file", f"{name}: image listed in the manifest is not in images/"))
        else:
            if hashlib.sha256(image_path.read_bytes()).hexdigest() != scene.get("sha256"):
                issues.append(_issue("checksum_mismatch", f"{name}: the image is not the one the manifest checksummed"))
        expected = scene.get("num_components")
        if fmt in ("yolo", "both"):
            ids = _check_yolo_label(Path(name).stem, labels_dir / f"{Path(name).stem}.txt", len(classes) or None, issues)
            if expected is not None and len(ids) != expected:
                issues.append(_issue("count_mismatch", f"{name}: {len(ids)} YOLO line(s), the manifest says {expected} component(s)"))
            if classes:
                counted: dict[str, int] = {}
                for class_id in ids:
                    if 0 <= class_id < len(classes):
                        counted[classes[class_id]] = counted.get(classes[class_id], 0) + 1
                if counted != scene.get("label_counts"):
                    issues.append(_issue("count_mismatch", f"{name}: the labels per class in the YOLO file are not those of the manifest"))
        if fmt in ("coco", "both") and expected is not None and coco_counts.get(name, 0) != expected:
            issues.append(_issue("count_mismatch", f"{name}: {coco_counts.get(name, 0)} COCO annotation(s), the manifest says {expected} component(s)"))
    if labels_dir.is_dir():
        stems = {Path(str(scene.get("image"))).stem for scene in scenes if isinstance(scene, dict)}
        for extra in sorted(p.name for p in labels_dir.glob("*.txt") if p.stem not in stems):
            issues.append(_issue("unexpected_file", f"labels/{extra} belongs to no scene of the manifest"))
    for problem in check_splits(out_dir, {str(name) for name in listed}):
        issues.append(_issue("split_mismatch", problem))
    return issues
