# =============================================================================
# HYDRA-UMC-SYNTHETIC-DATA-GEN - src/hydra_umc_synthetic_data_gen/shapes.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Silhouettes of real parts: a catalogue of STL and URDF files, read with the standard library only.

A catalogue is a JSON file next to the part files:

    {"unit_scale": 0.001,
     "parts": [{"label": "bolt", "stl": "parts/bolt.stl"},
               {"label": "bracket", "urdf": "parts/bracket.urdf", "scale": 0.001}]}

`unit_scale` (default 0.001: the files are in millimetres) turns the units of the files into metres; a part can override it with
`scale`. A part file must sit inside the folder of the catalogue (no absolute path, no `..`). An STL is read in its binary or ASCII form.
A URDF contributes the `visual` geometry of its links (mesh, box, cylinder, sphere) at the origin of each visual; joints are ignored, so
a catalogue part is a single rigid piece. A URDF that declares a DOCTYPE or an entity is refused, and so is a mesh through `package://`.

The silhouette of a part is a convex approximation: the part is reduced to the points that stick out furthest in 128 directions (real
vertices of the file), and the outline of their projection is the convex hull. A part with a hole or a concavity is drawn without it, which
is a stated limit unless the catalogue says `"silhouette": "concave"`: an STL part with at most `concave_max_triangles` (default 20000)
triangles is then painted from above on a 64 x 64 grid and its real outer outline (concavities included, holes inside it not) is used; a URDF part
or a bigger mesh keeps the convex outline. Nothing here keeps a path or a name of the machine that made the catalogue: only the labels and the
SHA-256 of the part files reach a dataset.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import struct
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

Vec3 = tuple[float, float, float]
Point = tuple[float, float]

MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_TRIANGLES = 300_000
MAX_PARTS = 200
SUPPORT_DIRECTIONS = 128
_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
YAW_STEPS = 36
CONCAVE_MAX_TRIANGLES = 20_000
CONCAVE_GRID = 64


class CatalogError(ValueError):
    """The catalogue or one of its part files cannot be used."""


# -- 2D geometry --------------------------------------------------------------------------------------------------------------------

def convex_hull(points: Sequence[Point]) -> list[Point]:
    """Counter-clockwise convex hull (Andrew's monotone chain); fewer than three distinct points come back as they are."""
    pts = sorted(set(points))
    if len(pts) < 3:
        return pts

    def cross(o: Point, a: Point, b: Point) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[Point] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[Point] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def polygon_spans(polygon: Sequence[tuple[int, int]], width: int, height: int) -> list[tuple[int, int, int]]:
    """(row, first column, column after the last) of the pixels whose centre is inside `polygon` (even-odd rule, any simple polygon),
    clipped to the canvas."""
    if len(polygon) < 3:
        return []
    y_min = max(0, min(p[1] for p in polygon))
    y_max = min(height - 1, max(p[1] for p in polygon))
    spans: list[tuple[int, int, int]] = []
    count = len(polygon)
    for y in range(y_min, y_max + 1):
        sample = y + 0.5
        crossings: list[float] = []
        for i in range(count):
            x0, y0 = polygon[i]
            x1, y1 = polygon[(i + 1) % count]
            if (y0 <= sample < y1) or (y1 <= sample < y0):
                crossings.append(x0 + (sample - y0) * (x1 - x0) / (y1 - y0))
        crossings.sort()
        for k in range(0, len(crossings) - 1, 2):
            start = max(0, math.ceil(crossings[k] - 0.5))
            stop = min(width, math.ceil(crossings[k + 1] - 0.5))
            if stop > start:
                spans.append((y, start, stop))
    return spans


def spans_box(spans: Sequence[tuple[int, int, int]]) -> tuple[int, int, int, int] | None:
    """(x, y, width, height) of the pixels in `spans`, or None when there are none."""
    if not spans:
        return None
    x0 = min(s[1] for s in spans)
    x1 = max(s[2] for s in spans)
    y0 = spans[0][0]
    y1 = spans[-1][0]
    return x0, y0, x1 - x0, y1 - y0 + 1


def fit_polygon(unit_points: Sequence[Point], x: int, y: int, width: int, height: int) -> tuple[tuple[int, int], ...]:
    """The points of a polygon given in a unit box, placed in the box x, y, width, height of the canvas."""
    return tuple((x + round(px * (width - 1)), y + round(py * (height - 1))) for px, py in unit_points)


# -- meshes -------------------------------------------------------------------------------------------------------------------------

def _read_limited(path: Path, label: str) -> bytes:
    try:
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            raise CatalogError(f"{label}: the file is larger than {MAX_FILE_BYTES // (1024 * 1024)} MiB")
        return path.read_bytes()
    except OSError as error:
        raise CatalogError(f"{label}: cannot read the file ({error.__class__.__name__})") from error


def parse_stl(data: bytes, label: str = "stl", max_triangles: int = MAX_TRIANGLES) -> list[Vec3]:
    """The distinct vertices of an STL (binary or ASCII)."""
    return parse_stl_mesh(data, label, max_triangles)[0]


def parse_stl_mesh(data: bytes, label: str = "stl", max_triangles: int = MAX_TRIANGLES) -> tuple[list[Vec3], list[tuple[Vec3, Vec3, Vec3]]]:
    """The distinct vertices and the triangles of an STL (binary or ASCII)."""
    vertices: set[Vec3] = set()
    mesh: list[tuple[Vec3, Vec3, Vec3]] = []
    if len(data) >= 84:
        triangles = struct.unpack_from("<I", data, 80)[0]
        if len(data) == 84 + 50 * triangles:
            if triangles == 0 or triangles > max_triangles:
                raise CatalogError(f"{label}: {triangles} triangle(s), the limit is {max_triangles}")
            for i in range(triangles):
                base = 84 + 50 * i + 12
                corner: list[Vec3] = []
                for v in range(3):
                    x, y, z = struct.unpack_from("<3f", data, base + 12 * v)
                    if not all(math.isfinite(c) for c in (x, y, z)):
                        raise CatalogError(f"{label}: a vertex is not a finite number")
                    vertices.add((x, y, z))
                    corner.append((x, y, z))
                mesh.append((corner[0], corner[1], corner[2]))
            return list(vertices), mesh
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise CatalogError(f"{label}: neither a binary nor an ASCII STL") from error
    if "solid" not in text[:200].lower():
        raise CatalogError(f"{label}: neither a binary nor an ASCII STL")
    count = 0
    pending: list[Vec3] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 4 and parts[0] == "vertex":
            try:
                vertex = (float(parts[1]), float(parts[2]), float(parts[3]))
            except ValueError as error:
                raise CatalogError(f"{label}: a vertex is not a number") from error
            if not all(math.isfinite(c) for c in vertex):
                raise CatalogError(f"{label}: a vertex is not a finite number")
            vertices.add(vertex)
            pending.append(vertex)
            if len(pending) == 3:
                mesh.append((pending[0], pending[1], pending[2]))
                pending = []
            count += 1
            if count > 3 * max_triangles:
                raise CatalogError(f"{label}: more than {max_triangles} triangles")
    if not vertices:
        raise CatalogError(f"{label}: no vertex found")
    return list(vertices), mesh


def _rotation_rpy(roll: float, pitch: float, yaw: float) -> list[list[float]]:
    cr, sr, cp, sp, cy, sy = math.cos(roll), math.sin(roll), math.cos(pitch), math.sin(pitch), math.cos(yaw), math.sin(yaw)
    return [
        [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
        [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
        [-sp, cp * sr, cp * cr],
    ]


def rotate(matrix: Sequence[Sequence[float]], v: Vec3) -> Vec3:
    return (
        matrix[0][0] * v[0] + matrix[0][1] * v[1] + matrix[0][2] * v[2],
        matrix[1][0] * v[0] + matrix[1][1] * v[1] + matrix[1][2] * v[2],
        matrix[2][0] * v[0] + matrix[2][1] * v[1] + matrix[2][2] * v[2],
    )


def _floats(text: str | None, count: int, default: float, label: str) -> list[float]:
    if text is None:
        return [default] * count
    try:
        values = [float(t) for t in text.split()]
    except ValueError as error:
        raise CatalogError(f"{label}: a number is expected") from error
    if len(values) != count or not all(math.isfinite(v) for v in values):
        raise CatalogError(f"{label}: {count} finite number(s) expected")
    return values


def _box_vertices(sx: float, sy: float, sz: float) -> list[Vec3]:
    return [(a * sx / 2, b * sy / 2, c * sz / 2) for a in (-1, 1) for b in (-1, 1) for c in (-1, 1)]


def _cylinder_vertices(radius: float, length: float) -> list[Vec3]:
    return [
        (radius * math.cos(2 * math.pi * k / 24), radius * math.sin(2 * math.pi * k / 24), z * length / 2)
        for k in range(24) for z in (-1, 1)
    ]


def _sphere_vertices(radius: float) -> list[Vec3]:
    pts: list[Vec3] = [(0.0, 0.0, radius), (0.0, 0.0, -radius)]
    for i in range(1, 8):
        phi = math.pi * i / 8
        for k in range(16):
            theta = 2 * math.pi * k / 16
            pts.append((radius * math.sin(phi) * math.cos(theta), radius * math.sin(phi) * math.sin(theta), radius * math.cos(phi)))
    return pts


def parse_urdf(data: bytes, base_dir: Path, root_dir: Path, label: str, max_triangles: int = MAX_TRIANGLES) -> list[Vec3]:
    """The vertices of the visual geometry of a URDF, each at the origin of its visual (joints are ignored)."""
    head = data[:4096].lower()
    if b"<!doctype" in head or b"<!entity" in data.lower():
        raise CatalogError(f"{label}: a URDF with a DOCTYPE or an entity is refused")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as error:
        raise CatalogError(f"{label}: not a valid URDF (XML)") from error
    vertices: list[Vec3] = []
    for visual in root.iter("visual"):
        geometry = visual.find("geometry")
        if geometry is None or len(geometry) != 1:
            continue
        shape = geometry[0]
        if shape.tag == "mesh":
            filename = shape.get("filename", "")
            if "://" in filename:
                raise CatalogError(f"{label}: a mesh through {filename.split('://')[0]}:// is not read; use a relative file")
            mesh = resolve_inside(root_dir, base_dir, filename, f"{label} mesh")
            scale = _floats(shape.get("scale"), 3, 1.0, label)
            points = [(x * scale[0], y * scale[1], z * scale[2]) for x, y, z in parse_stl(_read_limited(mesh, f"{label} mesh"), label, max_triangles)]
        elif shape.tag == "box":
            points = _box_vertices(*_floats(shape.get("size"), 3, 1.0, label))
        elif shape.tag == "cylinder":
            points = _cylinder_vertices(_floats(shape.get("radius"), 1, 0.0, label)[0], _floats(shape.get("length"), 1, 0.0, label)[0])
        elif shape.tag == "sphere":
            points = _sphere_vertices(_floats(shape.get("radius"), 1, 0.0, label)[0])
        else:
            continue
        origin = visual.find("origin")
        xyz = _floats(origin.get("xyz") if origin is not None else None, 3, 0.0, label)
        rpy = _floats(origin.get("rpy") if origin is not None else None, 3, 0.0, label)
        matrix = _rotation_rpy(*rpy)
        for p in points:
            r = rotate(matrix, p)
            vertices.append((r[0] + xyz[0], r[1] + xyz[1], r[2] + xyz[2]))
    if not vertices:
        raise CatalogError(f"{label}: no visual geometry found")
    return vertices


def resolve_inside(root_dir: Path, base_dir: Path, relative: str, label: str) -> Path:
    """`relative` (from `base_dir`) as a path that must stay inside `root_dir`."""
    if not relative or relative != relative.strip() or Path(relative).is_absolute() or re.match(r"^[A-Za-z]:", relative) or relative.startswith(("/", "\\")):
        raise CatalogError(f"{label}: {relative!r} must be a relative path")
    target = (base_dir / relative).resolve()
    try:
        target.relative_to(root_dir.resolve())
    except ValueError as error:
        raise CatalogError(f"{label}: {relative!r} leaves the folder of the catalogue") from error
    if not target.is_file():
        raise CatalogError(f"{label}: {relative!r} is not a file")
    return target


def support_points(vertices: Sequence[Vec3], directions: int = SUPPORT_DIRECTIONS) -> list[Vec3]:
    """The vertices that stick out furthest along `directions` spread evenly over the sphere (all of them for a small part)."""
    if len(vertices) <= directions:
        return list(vertices)
    golden = math.pi * (3.0 - math.sqrt(5.0))
    chosen: dict[Vec3, None] = {}
    for i in range(directions):
        z = 1 - 2 * (i + 0.5) / directions
        r = math.sqrt(max(0.0, 1 - z * z))
        d = (r * math.cos(golden * i), r * math.sin(golden * i), z)
        best = max(vertices, key=lambda v: v[0] * d[0] + v[1] * d[1] + v[2] * d[2])
        chosen[best] = None
    return list(chosen)


# -- catalogue ----------------------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Part:
    """One catalogue part: its class label, the points that outline it (in metres, mesh frame) and the checksum of its file."""

    label: str
    points: tuple[Vec3, ...]
    source_sha256: str
    # the triangles of an STL part (metres), kept only when the catalogue asks for `concave` outlines; empty otherwise
    triangles: tuple[tuple[Vec3, Vec3, Vec3], ...] = ()


@dataclass(frozen=True)
class Silhouette:
    """A silhouette in a unit box (0..1 on both axes) and the width over height of the box it came from."""

    points: tuple[Point, ...]
    aspect: float


@dataclass(frozen=True)
class Catalog:
    parts: tuple[Part, ...]
    unit_scale: float

    @property
    def labels(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(p.label for p in self.parts))

    def describe(self) -> dict[str, object]:
        """What a dataset may say about the catalogue: labels and checksums, never a path."""
        return {"unit_scale": self.unit_scale, "parts": [{"label": p.label, "source_sha256": p.source_sha256} for p in self.parts]}


def load_catalog(path: str | Path) -> Catalog:
    catalog_path = Path(path)
    try:
        raw = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise CatalogError(f"cannot read the catalogue ({error.__class__.__name__})") from error
    if not isinstance(raw, dict) or not isinstance(raw.get("parts"), list) or not raw["parts"]:
        raise CatalogError("the catalogue must be an object with a non-empty list `parts`")
    unknown = sorted(set(raw) - {"unit_scale", "parts", "max_triangles", "silhouette", "concave_max_triangles"})
    if unknown:
        raise CatalogError(f"the catalogue has unknown keys: {', '.join(unknown)}")
    unit_scale = raw.get("unit_scale", 0.001)
    max_triangles = raw.get("max_triangles", MAX_TRIANGLES)
    if isinstance(unit_scale, bool) or not isinstance(unit_scale, (int, float)) or not 0 < unit_scale <= 1000:
        raise CatalogError("unit_scale must be a number above 0")
    if isinstance(max_triangles, bool) or not isinstance(max_triangles, int) or not 1 <= max_triangles <= MAX_TRIANGLES:
        raise CatalogError(f"max_triangles must be an integer in 1..{MAX_TRIANGLES}")
    outline = raw.get("silhouette", "convex")
    if outline not in ("convex", "concave"):
        raise CatalogError('silhouette must be "convex" or "concave"')
    concave_max = raw.get("concave_max_triangles", CONCAVE_MAX_TRIANGLES)
    if isinstance(concave_max, bool) or not isinstance(concave_max, int) or not 1 <= concave_max <= MAX_TRIANGLES:
        raise CatalogError(f"concave_max_triangles must be an integer in 1..{MAX_TRIANGLES}")
    if len(raw["parts"]) > MAX_PARTS:
        raise CatalogError(f"the catalogue has more than {MAX_PARTS} parts")
    root_dir = catalog_path.parent
    parts: list[Part] = []
    for index, item in enumerate(raw["parts"]):
        where = f"part {index}"
        if not isinstance(item, dict):
            raise CatalogError(f"{where}: must be an object")
        extra = sorted(set(item) - {"label", "stl", "urdf", "scale"})
        if extra:
            raise CatalogError(f"{where}: unknown keys: {', '.join(extra)}")
        label = item.get("label")
        if not isinstance(label, str) or not _LABEL.match(label):
            raise CatalogError(f"{where}: label must be a short name (letters, digits, '_', '-', '.')")
        if ("stl" in item) == ("urdf" in item):
            raise CatalogError(f"{where}: give exactly one of `stl` or `urdf`")
        scale = item.get("scale", unit_scale)
        if isinstance(scale, bool) or not isinstance(scale, (int, float)) or not 0 < scale <= 1000:
            raise CatalogError(f"{where}: scale must be a number above 0")
        kind = "stl" if "stl" in item else "urdf"
        if not isinstance(item[kind], str):
            raise CatalogError(f"{where}: {kind} must be a relative path")
        file = resolve_inside(root_dir, root_dir, item[kind], where)
        data = _read_limited(file, where)
        kept: tuple[tuple[Vec3, Vec3, Vec3], ...] = ()
        if kind == "stl":
            vertices, mesh = parse_stl_mesh(data, where, max_triangles)
            # a mesh over the limit keeps its convex outline: the painting of the triangles is plain Python
            if outline == "concave" and len(mesh) <= concave_max:
                kept = tuple(tuple((x * scale, y * scale, z * scale) for x, y, z in tri) for tri in mesh)  # type: ignore[misc]
        else:
            vertices = parse_urdf(data, file.parent, root_dir, where, max_triangles)
        points = support_points(vertices)
        parts.append(Part(label, tuple((x * scale, y * scale, z * scale) for x, y, z in points), hashlib.sha256(data).hexdigest(), kept))
    return Catalog(tuple(parts), float(unit_scale))


def _simplify(points: list[Point], tolerance: float) -> list[Point]:
    """Douglas-Peucker on a closed loop: split at the point furthest from the first, simplify each half."""
    if len(points) <= 4:
        return points

    def dist(p: Point, a: Point, b: Point) -> float:
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        if length == 0:
            return math.hypot(p[0] - a[0], p[1] - a[1])
        return abs(dx * (a[1] - p[1]) - (a[0] - p[0]) * dy) / length

    def chain(seq: list[Point]) -> list[Point]:
        if len(seq) < 3:
            return seq
        worst, at = 0.0, 0
        for k in range(1, len(seq) - 1):
            d = dist(seq[k], seq[0], seq[-1])
            if d > worst:
                worst, at = d, k
        if worst <= tolerance:
            return [seq[0], seq[-1]]
        return chain(seq[: at + 1])[:-1] + chain(seq[at:])

    far = max(range(len(points)), key=lambda k: math.hypot(points[k][0] - points[0][0], points[k][1] - points[0][1]))
    a = points[: far + 1]
    b = points[far:] + points[:1]
    return chain(a)[:-1] + chain(b)[:-1]


def raster_outline(triangles: Sequence[tuple[Point, Point, Point]], grid: int = CONCAVE_GRID) -> list[Point]:
    """The outer outline, in a unit box, of the union of 2D `triangles`: they are painted on a grid x grid canvas that spans their box
    and the boundary of the biggest connected piece is walked and simplified. A hole inside the part is not kept (a stated limit)."""
    xs = [p[0] for tri in triangles for p in tri]
    ys = [p[1] for tri in triangles for p in tri]
    x0, y0 = min(xs), min(ys)
    w, h = max(xs) - x0, max(ys) - y0
    if w <= 0 or h <= 0:
        return []
    cells: set[tuple[int, int]] = set()
    for tri in triangles:
        g = [((p[0] - x0) / w * grid, (p[1] - y0) / h * grid) for p in tri]
        (ax, ay), (bx, by), (cx, cy) = g
        area = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
        lo_x, hi_x = int(min(ax, bx, cx)), min(grid - 1, int(max(ax, bx, cx)))
        lo_y, hi_y = int(min(ay, by, cy)), min(grid - 1, int(max(ay, by, cy)))
        # the corners and the centre of a triangle always mark their cell: thin or tiny triangles must not leave gaps
        for px, py in ((ax, ay), (bx, by), (cx, cy), ((ax + bx + cx) / 3, (ay + by + cy) / 3)):
            cells.add((min(grid - 1, int(px)), min(grid - 1, int(py))))
        if area == 0:
            continue
        for gy in range(lo_y, hi_y + 1):
            for gx in range(lo_x, hi_x + 1):
                px, py = gx + 0.5, gy + 0.5
                w0 = (bx - ax) * (py - ay) - (by - ay) * (px - ax)
                w1 = (cx - bx) * (py - by) - (cy - by) * (px - bx)
                w2 = (ax - cx) * (py - cy) - (ay - cy) * (px - cx)
                if (w0 >= 0 and w1 >= 0 and w2 >= 0) or (w0 <= 0 and w1 <= 0 and w2 <= 0):
                    cells.add((gx, gy))
    # directed boundary edges of the cells (clockwise on screen, y down), chained into loops
    nxt: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for gx, gy in cells:
        if (gx, gy - 1) not in cells:
            nxt.setdefault((gx, gy), []).append((gx + 1, gy))
        if (gx + 1, gy) not in cells:
            nxt.setdefault((gx + 1, gy), []).append((gx + 1, gy + 1))
        if (gx, gy + 1) not in cells:
            nxt.setdefault((gx + 1, gy + 1), []).append((gx, gy + 1))
        if (gx - 1, gy) not in cells:
            nxt.setdefault((gx, gy + 1), []).append((gx, gy))
    loops: list[list[tuple[int, int]]] = []
    while nxt:
        start = next(iter(nxt))
        loop = [start]
        cur = start
        while True:
            options = nxt.get(cur)
            if not options:
                break
            step = options.pop()
            if not options:
                del nxt[cur]
            cur = step
            if cur == start:
                break
            loop.append(cur)
        if len(loop) >= 3:
            loops.append(loop)

    def area_of(loop: list[tuple[int, int]]) -> float:
        n = len(loop)
        return abs(sum(loop[k][0] * loop[(k + 1) % n][1] - loop[(k + 1) % n][0] * loop[k][1] for k in range(n))) / 2

    if not loops:
        return []
    outer = max(loops, key=area_of)
    simple = _simplify([(float(x), float(y)) for x, y in outer], 0.75)
    return [(px / grid, py / grid) for px, py in simple]


def _concave_silhouettes(part: Part, steps: int) -> tuple[Silhouette, ...]:
    out: list[Silhouette] = []
    for k in range(steps):
        angle = 2 * math.pi * k / steps
        c, s = math.cos(angle), math.sin(angle)
        flat = [tuple((x * c - y * s, x * s + y * c) for x, y, _ in tri) for tri in part.triangles]
        outline = raster_outline(flat)  # type: ignore[arg-type]
        if len(outline) < 3:
            continue
        xs = [p[0] for tri in flat for p in tri]
        ys = [p[1] for tri in flat for p in tri]
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        out.append(Silhouette(tuple(outline), w / h))
    return tuple(out)


def top_silhouettes(part: Part, steps: int = YAW_STEPS) -> tuple[Silhouette, ...]:
    """The outline of `part` seen from above (along z) for `steps` turns about z, each in a unit box. Convex unless the part kept its
    triangles (`silhouette: concave` in the catalogue): then the real outer outline, with its concavities."""
    if part.triangles:
        return _concave_silhouettes(part, steps)
    out: list[Silhouette] = []
    for k in range(steps):
        angle = 2 * math.pi * k / steps
        c, s = math.cos(angle), math.sin(angle)
        hull = convex_hull([(x * c - y * s, x * s + y * c) for x, y, _ in part.points])
        if len(hull) < 3:
            continue
        xs = [p[0] for p in hull]
        ys = [p[1] for p in hull]
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        if w <= 0 or h <= 0:
            continue
        unit = tuple(((x - min(xs)) / w, (y - min(ys)) / h) for x, y in hull)
        out.append(Silhouette(unit, w / h))
    return tuple(out)
