# =============================================================================
# HYDRA-UMC-SYNTHETIC-DATA-GEN - src/hydra_umc_synthetic_data_gen/scenarios.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Datasets for visual servoing (known 6-DOF poses) and for the safety zones (stylised people in zones), and the classes of a registered model.

Everything here is OFF unless a file asks for it on the command line:

* `--classes-from REGISTRY --model NAME`: the classes (in the order of the model, which is the class id) and the input size of a model of
  the registry of HYDRA-UMC-DETECTION-HEF. Only the name, the version, the size and the classes reach the dataset, never a path.
* `--servoing-config FILE` (with a catalogue): each image holds catalogue parts at a sampled pose in front of a pinhole camera; the pose of
  every part (translation in metres, rotation as a quaternion and as degrees, in the OpenCV camera frame) is written to `poses.json`
  together with the intrinsics, so that a pose estimator can be trained against it.
* `--safety-config FILE`: each image also holds stylised people (an abstract pictogram, nobody real) placed in or out of rectangular zones; the
  zones, the boxes and the action a safety system should take (`stop`, `slow` or `clear`) are written to `zones.json`.

Every value comes from the file given, with the limits checked; a file whose `enabled` is not `true` changes nothing.
"""
from __future__ import annotations

import json
import math
import random
import re
from dataclasses import dataclass
from pathlib import Path

from .scene import Component, Scene, visible_components
from .shapes import Part, Vec3, convex_hull, fit_polygon, polygon_spans, rotate, spans_box

_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_VERSION = re.compile(r"^\d+\.\d+\.\d+$")
PERSON_LABEL = "person"
MAX_REGISTRY_BYTES = 8 * 1024 * 1024


class ScenarioError(ValueError):
    """A registry or a scenario file that cannot be used."""


# -- classes from the registry ---------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class ModelClasses:
    name: str
    version: str
    classes: tuple[str, ...]
    height: int
    width: int

    def describe(self) -> dict[str, object]:
        return {"model": self.name, "version": self.version, "input_shape": [self.height, self.width], "classes": list(self.classes)}


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in version.split("."))


def load_model_classes(registry: str | Path, model: str, version: str | None = None) -> ModelClasses:
    """The entry `model` of a registry file (a JSON array); without `version`, the newest stable one."""
    path = Path(registry)
    try:
        if path.stat().st_size > MAX_REGISTRY_BYTES:
            raise ScenarioError("the registry is too large")
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ScenarioError(f"cannot read the registry ({error.__class__.__name__})") from error
    except ValueError as error:
        raise ScenarioError("the registry is not valid JSON") from error
    if not isinstance(raw, list):
        raise ScenarioError("the registry must be a JSON array of entries")
    best: dict | None = None
    for entry in raw:
        if not isinstance(entry, dict) or entry.get("name") != model:
            continue
        entry_version = entry.get("version")
        if not isinstance(entry_version, str) or not _VERSION.match(entry_version):
            continue
        if version is not None:
            if entry_version == version:
                best = entry
                break
            continue
        if entry.get("channel", "stable") != "stable":
            continue
        if best is None or _version_key(entry_version) > _version_key(best["version"]):
            best = entry
    if best is None:
        raise ScenarioError(f"the registry has no {'stable ' if version is None else ''}entry for model {model!r}" + (f" version {version}" if version else ""))
    classes = best.get("classes")
    shape = best.get("input_shape")
    if (
        not isinstance(classes, list) or not classes or not all(isinstance(c, str) and c.strip() for c in classes)
        or len(set(classes)) != len(classes)
    ):
        raise ScenarioError("the classes of the entry must be a non-empty list of distinct names")
    if (
        not isinstance(shape, list) or len(shape) != 3 or any(isinstance(d, bool) or not isinstance(d, int) or d <= 0 for d in shape)
        or shape[2] not in (1, 3, 4)
    ):
        raise ScenarioError("the input_shape of the entry must be height, width, channels")
    return ModelClasses(model, best["version"], tuple(classes), shape[0], shape[1])


# -- common reading of a scenario file -------------------------------------------------------------------------------------------------

def _read_section(path: str | Path, allowed: set[str], what: str) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ScenarioError(f"{what}: cannot read the file ({error.__class__.__name__})") from error
    if not isinstance(data, dict):
        raise ScenarioError(f"{what}: the file must hold a JSON object")
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ScenarioError(f"{what}: unknown keys: {', '.join(unknown)}")
    return data


def _number(data: dict, key: str, default: float, low: float, high: float, what: str) -> float:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ScenarioError(f"{what}.{key} must be a number in {low}..{high}")
    return float(value)


def _integer(data: dict, key: str, default: int, low: int, high: int, what: str) -> int:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ScenarioError(f"{what}.{key} must be an integer in {low}..{high}")
    return value


# -- servoing -------------------------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class ServoingConfig:
    enabled: bool = False
    fov_deg: float = 60.0
    min_objects: int = 1
    max_objects: int = 3
    min_depth_m: float = 0.15
    max_depth_m: float = 0.6
    max_tilt_deg: float = 25.0
    min_inside_fraction: float = 0.95
    max_attempts: int = 30

    def describe(self) -> dict[str, object]:
        return {
            "fov_deg": self.fov_deg, "objects": [self.min_objects, self.max_objects], "depth_m": [self.min_depth_m, self.max_depth_m],
            "max_tilt_deg": self.max_tilt_deg, "min_inside_fraction": self.min_inside_fraction,
        }


def load_servoing_config(path: str | Path) -> ServoingConfig:
    data = _read_section(path, {"enabled", "fov_deg", "objects", "depth_m", "max_tilt_deg", "min_inside_fraction", "max_attempts"}, "servoing config")
    enabled = data.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ScenarioError("servoing config.enabled must be true or false")
    objects = data.get("objects", {})
    depth = data.get("depth_m", {})
    if not isinstance(objects, dict) or not isinstance(depth, dict):
        raise ScenarioError("servoing config: objects and depth_m must be objects with min and max")
    config = ServoingConfig(
        enabled=enabled,
        fov_deg=_number(data, "fov_deg", 60.0, 10.0, 150.0, "servoing config"),
        min_objects=_integer(objects, "min", 1, 1, 20, "servoing config.objects"),
        max_objects=_integer(objects, "max", 3, 1, 20, "servoing config.objects"),
        min_depth_m=_number(depth, "min", 0.15, 0.01, 100.0, "servoing config.depth_m"),
        max_depth_m=_number(depth, "max", 0.6, 0.01, 100.0, "servoing config.depth_m"),
        max_tilt_deg=_number(data, "max_tilt_deg", 25.0, 0.0, 90.0, "servoing config"),
        min_inside_fraction=_number(data, "min_inside_fraction", 0.95, 0.5, 1.0, "servoing config"),
        max_attempts=_integer(data, "max_attempts", 30, 1, 1000, "servoing config"),
    )
    if config.min_objects > config.max_objects or config.min_depth_m > config.max_depth_m:
        raise ScenarioError("servoing config: a minimum is above its maximum")
    return config


def _quaternion(matrix: list[list[float]]) -> tuple[float, float, float, float]:
    """(w, x, y, z) of a rotation matrix."""
    m = matrix
    trace = m[0][0] + m[1][1] + m[2][2]
    if trace > 0:
        s = math.sqrt(trace + 1.0) * 2
        q = (0.25 * s, (m[2][1] - m[1][2]) / s, (m[0][2] - m[2][0]) / s, (m[1][0] - m[0][1]) / s)
    elif m[0][0] > m[1][1] and m[0][0] > m[2][2]:
        s = math.sqrt(1.0 + m[0][0] - m[1][1] - m[2][2]) * 2
        q = ((m[2][1] - m[1][2]) / s, 0.25 * s, (m[0][1] + m[1][0]) / s, (m[0][2] + m[2][0]) / s)
    elif m[1][1] > m[2][2]:
        s = math.sqrt(1.0 + m[1][1] - m[0][0] - m[2][2]) * 2
        q = ((m[0][2] - m[2][0]) / s, (m[0][1] + m[1][0]) / s, 0.25 * s, (m[1][2] + m[2][1]) / s)
    else:
        s = math.sqrt(1.0 + m[2][2] - m[0][0] - m[1][1]) * 2
        q = ((m[1][0] - m[0][1]) / s, (m[0][2] + m[2][0]) / s, (m[1][2] + m[2][1]) / s, 0.25 * s)
    norm = math.sqrt(sum(c * c for c in q))
    return tuple(round(c / norm, 9) for c in q)  # type: ignore[return-value]


def _euler_matrix(roll: float, pitch: float, yaw: float) -> list[list[float]]:
    cr, sr, cp, sp, cy, sy = math.cos(roll), math.sin(roll), math.cos(pitch), math.sin(pitch), math.cos(yaw), math.sin(yaw)
    return [
        [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
        [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
        [-sp, cp * sr, cp * cr],
    ]


def camera_intrinsics(config: ServoingConfig, width: int, height: int) -> dict[str, float]:
    """A pinhole camera whose horizontal field of view is `fov_deg`, principal point at the centre of the image."""
    fx = (width / 2) / math.tan(math.radians(config.fov_deg) / 2)
    return {"fx": round(fx, 6), "fy": round(fx, 6), "cx": width / 2, "cy": height / 2, "width": width, "height": height}


def servoing_scene(
    rng: random.Random, parts: tuple[Part, ...], config: ServoingConfig, width: int, height: int
) -> tuple[Scene, list[dict[str, object]]]:
    """A scene of catalogue parts at sampled 6-DOF poses, and the record of each pose. Parts that do not fit the image are not placed."""
    intr = camera_intrinsics(config, width, height)
    fx, fy, cx, cy = intr["fx"], intr["fy"], intr["cx"], intr["cy"]
    background = (rng.randint(180, 230),) * 3
    wanted = rng.randint(config.min_objects, config.max_objects)
    placed: list[tuple[float, Component, dict[str, object]]] = []
    attempts = 0
    while len(placed) < wanted and attempts < config.max_attempts * wanted:
        attempts += 1
        part = rng.choice(parts)
        depth = rng.uniform(config.min_depth_m, config.max_depth_m)
        u = rng.uniform(0.2, 0.8) * width
        v = rng.uniform(0.2, 0.8) * height
        translation: Vec3 = ((u - cx) * depth / fx, (v - cy) * depth / fy, depth)
        roll = math.radians(rng.uniform(-config.max_tilt_deg, config.max_tilt_deg))
        pitch = math.radians(rng.uniform(-config.max_tilt_deg, config.max_tilt_deg))
        yaw = math.radians(rng.uniform(0.0, 360.0))
        matrix = _euler_matrix(roll, pitch, yaw)
        projected: list[tuple[float, float]] = []
        for point in part.points:
            r = rotate(matrix, point)
            z = r[2] + translation[2]
            if z <= 1e-6:
                projected = []
                break
            projected.append((fx * (r[0] + translation[0]) / z + cx, fy * (r[1] + translation[1]) / z + cy))
        hull = convex_hull(projected)
        if len(hull) < 3:
            continue
        polygon = tuple((round(px), round(py)) for px, py in hull)
        area_full = _polygon_area(hull)
        inside = _polygon_area(_clip_to_canvas(hull, width, height))
        if area_full <= 0 or inside / area_full < config.min_inside_fraction:
            continue
        box = spans_box(polygon_spans(polygon, width, height))
        if box is None or box[2] < 3 or box[3] < 3:
            continue
        color = (rng.randint(0, 180), rng.randint(0, 180), rng.randint(0, 180))
        component = Component(label=part.label, x=box[0], y=box[1], width=box[2], height=box[3], color=color, polygon=polygon)
        record = {
            "label": part.label,
            "translation_m": [round(c, 6) for c in translation],
            "rotation_quaternion_wxyz": list(_quaternion(matrix)),
            "rotation_rpy_deg": [round(math.degrees(a), 4) for a in (roll, pitch, yaw)],
            "box": [box[0], box[1], box[2], box[3]],
        }
        placed.append((depth, component, record))
    # the far parts first, so that a near one covers them as a camera would see it
    placed.sort(key=lambda item: -item[0])
    scene = Scene(width, height, background, visible_components(tuple(c for _, c, _ in placed), width, height))
    kept_boxes = {(c.x, c.y, c.width, c.height, c.label) for c in scene.components}
    records = [r for _, c, r in placed if (c.x, c.y, c.width, c.height, c.label) in kept_boxes]
    return scene, records


def _polygon_area(points: list[tuple[float, float]]) -> float:
    if len(points) < 3:
        return 0.0
    return abs(sum(points[i][0] * points[(i + 1) % len(points)][1] - points[(i + 1) % len(points)][0] * points[i][1] for i in range(len(points)))) / 2


def _clip_to_canvas(points: list[tuple[float, float]], width: int, height: int) -> list[tuple[float, float]]:
    """Sutherland-Hodgman clip of a convex polygon to the canvas."""
    def clip(poly: list[tuple[float, float]], inside, intersect) -> list[tuple[float, float]]:
        out: list[tuple[float, float]] = []
        for i, current in enumerate(poly):
            previous = poly[i - 1]
            if inside(current):
                if not inside(previous):
                    out.append(intersect(previous, current))
                out.append(current)
            elif inside(previous):
                out.append(intersect(previous, current))
        return out

    def at_x(x: float):
        return lambda a, b: (x, a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0]))

    def at_y(y: float):
        return lambda a, b: (a[0] + (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]), y)

    poly = points
    for inside, intersect in (
        (lambda p: p[0] >= 0, at_x(0.0)), (lambda p: p[0] <= width, at_x(float(width))),
        (lambda p: p[1] >= 0, at_y(0.0)), (lambda p: p[1] <= height, at_y(float(height))),
    ):
        if not poly:
            break
        poly = clip(poly, inside, intersect)
    return poly


# -- safety zones -----------------------------------------------------------------------------------------------------------------------

# A stylised pictogram of a person in a unit box; it stands for nobody.
_PERSON = (
    (0.38, 0.0), (0.62, 0.0), (0.66, 0.14), (0.60, 0.20), (0.92, 0.28), (0.92, 0.62), (0.78, 0.62), (0.74, 0.40), (0.72, 1.0),
    (0.54, 1.0), (0.50, 0.66), (0.46, 1.0), (0.28, 1.0), (0.26, 0.40), (0.22, 0.62), (0.08, 0.62), (0.08, 0.28), (0.40, 0.20),
    (0.34, 0.14),
)
ZONE_KINDS = ("stop", "slow")


@dataclass(frozen=True)
class Zone:
    name: str
    kind: str
    rect: tuple[float, float, float, float]  # x0, y0, x1, y1 as fractions of the image


@dataclass(frozen=True)
class SafetyConfig:
    enabled: bool = False
    zones: tuple[Zone, ...] = ()
    min_people: int = 0
    max_people: int = 2
    min_height_fraction: float = 0.25
    max_height_fraction: float = 0.5
    in_zone_probability: float = 0.5
    min_overlap: float = 0.2

    def describe(self) -> dict[str, object]:
        return {
            "zones": [{"name": z.name, "kind": z.kind, "rect": list(z.rect)} for z in self.zones], "people": [self.min_people, self.max_people],
            "height_fraction": [self.min_height_fraction, self.max_height_fraction], "min_overlap": self.min_overlap,
        }


def load_safety_config(path: str | Path) -> SafetyConfig:
    data = _read_section(path, {"enabled", "zones", "people", "height_fraction", "in_zone_probability", "min_overlap"}, "safety config")
    enabled = data.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ScenarioError("safety config.enabled must be true or false")
    raw_zones = data.get("zones", [])
    if not isinstance(raw_zones, list) or len(raw_zones) > 16:
        raise ScenarioError("safety config.zones must be a list of at most 16 zones")
    zones: list[Zone] = []
    for index, item in enumerate(raw_zones):
        if not isinstance(item, dict) or set(item) - {"name", "kind", "rect"}:
            raise ScenarioError(f"safety config.zones[{index}] must be an object with name, kind and rect")
        name, kind, rect = item.get("name"), item.get("kind"), item.get("rect")
        if not isinstance(name, str) or not _NAME.match(name) or any(z.name == name for z in zones):
            raise ScenarioError(f"safety config.zones[{index}].name must be a short, distinct name")
        if kind not in ZONE_KINDS:
            raise ScenarioError(f"safety config.zones[{index}].kind must be one of {', '.join(ZONE_KINDS)}")
        if (
            not isinstance(rect, list) or len(rect) != 4
            or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not 0.0 <= v <= 1.0 for v in rect)
            or rect[0] >= rect[2] or rect[1] >= rect[3]
        ):
            raise ScenarioError(f"safety config.zones[{index}].rect must be [x0, y0, x1, y1] as fractions with x0 < x1 and y0 < y1")
        zones.append(Zone(name, kind, (float(rect[0]), float(rect[1]), float(rect[2]), float(rect[3]))))
    people = data.get("people", {})
    height = data.get("height_fraction", {})
    if not isinstance(people, dict) or not isinstance(height, dict):
        raise ScenarioError("safety config: people and height_fraction must be objects with min and max")
    config = SafetyConfig(
        enabled=enabled, zones=tuple(zones),
        min_people=_integer(people, "min", 0, 0, 10, "safety config.people"),
        max_people=_integer(people, "max", 2, 0, 10, "safety config.people"),
        min_height_fraction=_number(height, "min", 0.25, 0.05, 1.0, "safety config.height_fraction"),
        max_height_fraction=_number(height, "max", 0.5, 0.05, 1.0, "safety config.height_fraction"),
        in_zone_probability=_number(data, "in_zone_probability", 0.5, 0.0, 1.0, "safety config"),
        min_overlap=_number(data, "min_overlap", 0.2, 0.01, 1.0, "safety config"),
    )
    if config.min_people > config.max_people or config.min_height_fraction > config.max_height_fraction:
        raise ScenarioError("safety config: a minimum is above its maximum")
    if enabled and not config.zones:
        raise ScenarioError("safety config: at least one zone is needed")
    return config


def _overlap(box: tuple[int, int, int, int], rect_px: tuple[float, float, float, float]) -> float:
    x, y, w, h = box
    ix = max(0.0, min(x + w, rect_px[2]) - max(x, rect_px[0]))
    iy = max(0.0, min(y + h, rect_px[3]) - max(y, rect_px[1]))
    return (ix * iy) / (w * h) if w * h else 0.0


def add_people(
    rng: random.Random, scene: Scene, config: SafetyConfig
) -> tuple[Scene, dict[str, object]]:
    """The scene with stylised people on top and the record of where they are against the zones."""
    width, height = scene.width, scene.height
    rects = {z.name: (z.rect[0] * width, z.rect[1] * height, z.rect[2] * width, z.rect[3] * height) for z in config.zones}
    people: list[Component] = []
    records: list[dict[str, object]] = []
    for _ in range(rng.randint(config.min_people, config.max_people)):
        person_h = max(8, round(rng.uniform(config.min_height_fraction, config.max_height_fraction) * height))
        person_w = max(4, round(person_h * 0.45))
        person_h, person_w = min(person_h, height), min(person_w, width)
        if config.zones and rng.random() < config.in_zone_probability:
            zone = rng.choice(config.zones)
            zx0, zy0, zx1, zy1 = rects[zone.name]
            x = round(rng.uniform(zx0, max(zx0, zx1 - person_w)))
            y = round(rng.uniform(zy0, max(zy0, zy1 - person_h)))
        else:
            x = rng.randint(0, max(0, width - person_w))
            y = rng.randint(0, max(0, height - person_h))
        x = min(max(0, x), width - person_w)
        y = min(max(0, y), height - person_h)
        polygon = fit_polygon(_PERSON, x, y, person_w, person_h)
        box = spans_box(polygon_spans(polygon, width, height))
        if box is None:
            continue
        color = (rng.randint(30, 90), rng.randint(90, 150), rng.randint(160, 230))
        people.append(Component(label=PERSON_LABEL, x=box[0], y=box[1], width=box[2], height=box[3], color=color, polygon=polygon))
        records.append({
            "box": list(box),
            "overlap": {name: round(_overlap(box, rect), 4) for name, rect in rects.items()},
        })
    if not people:
        return scene, {"people": [], "expected_action": "clear"}
    # the people go last, so none of them is covered by a part
    combined = Scene(width, height, scene.background_color, visible_components(scene.components + tuple(people), width, height))
    kept = {(c.x, c.y, c.width, c.height) for c in combined.components if c.label == PERSON_LABEL}
    records = [r for r in records if tuple(r["box"]) in kept]  # type: ignore[arg-type]
    action = "clear"
    for record in records:
        for zone in config.zones:
            if record["overlap"][zone.name] >= config.min_overlap:  # type: ignore[index]
                if zone.kind == "stop":
                    action = "stop"
                elif action != "stop":
                    action = "slow"
    return combined, {"people": records, "expected_action": action}
