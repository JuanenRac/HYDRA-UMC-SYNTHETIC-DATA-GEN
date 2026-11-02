# =============================================================================
# HYDRA-UMC-SYNTHETIC-DATA-GEN - tests/test_concave_and_segmentation.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Concave outlines of catalogue parts and the COCO segmentation of parts painted as polygons."""
from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

from hydra_umc_synthetic_data_gen.export import Dataset, export_coco
from hydra_umc_synthetic_data_gen.scene import Component, Scene
from hydra_umc_synthetic_data_gen.shapes import CatalogError, load_catalog, polygon_spans, top_silhouettes


def _stl(triangles: list[tuple[tuple[float, float, float], ...]]) -> bytes:
    out = bytearray(b"\0" * 80 + struct.pack("<I", len(triangles)))
    for tri in triangles:
        out += struct.pack("<3f", 0, 0, 0)
        for v in tri:
            out += struct.pack("<3f", *v)
        out += b"\0\0"
    return bytes(out)


def _quad(x0: float, y0: float, x1: float, y1: float) -> list[tuple[tuple[float, float, float], ...]]:
    return [((x0, y0, 0), (x1, y0, 0), (x1, y1, 0)), ((x0, y0, 0), (x1, y1, 0), (x0, y1, 0))]


def _l_shape() -> bytes:
    # an L of 100 x 100 mm with arms 30 mm wide: the notch (x > 30, y > 30) is a quarter of the area of the hull box
    return _stl(_quad(0, 0, 100, 30) + _quad(0, 30, 30, 100))


def _catalog(tmp_path: Path, extra: dict[str, object]) -> Path:
    (tmp_path / "l.stl").write_bytes(_l_shape())
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps({"parts": [{"label": "bracket", "stl": "l.stl"}], **extra}), encoding="utf-8")
    return path


def _area(points: tuple[tuple[float, float], ...]) -> float:
    n = len(points)
    return abs(sum(points[i][0] * points[(i + 1) % n][1] - points[(i + 1) % n][0] * points[i][1] for i in range(n))) / 2


def test_convex_is_the_default_and_hides_the_notch(tmp_path: Path) -> None:
    part = load_catalog(_catalog(tmp_path, {})).parts[0]
    assert part.triangles == ()
    first = top_silhouettes(part)[0]
    assert _area(first.points) > 0.6  # the hull of an L fills the notch (area 0.755 of the box at yaw 0)


def test_concave_outline_follows_the_notch(tmp_path: Path) -> None:
    part = load_catalog(_catalog(tmp_path, {"silhouette": "concave"})).parts[0]
    assert len(part.triangles) == 4
    first = top_silhouettes(part)[0]  # yaw 0: the L as drawn, 51 percent of its box
    assert 0.45 < _area(first.points) < 0.58
    assert first.aspect == pytest.approx(1.0, abs=0.01)
    # every point stays in the unit box and the outline is a real polygon
    assert len(first.points) >= 6 and all(0 <= x <= 1 and 0 <= y <= 1 for x, y in first.points)
    spans = polygon_spans([(round(x * 99), round(y * 99)) for x, y in first.points], 100, 100)
    painted = sum(b - a for _, a, b in spans)
    assert 4300 < painted < 5800  # about 51 percent of 100 x 100


def test_concave_mesh_over_the_limit_keeps_the_convex_outline(tmp_path: Path) -> None:
    part = load_catalog(_catalog(tmp_path, {"silhouette": "concave", "concave_max_triangles": 3})).parts[0]
    assert part.triangles == ()


@pytest.mark.parametrize("extra", [{"silhouette": "round"}, {"concave_max_triangles": 0}, {"concave_max_triangles": True}])
def test_bad_outline_settings_are_refused(tmp_path: Path, extra: dict[str, object]) -> None:
    with pytest.raises(CatalogError):
        load_catalog(_catalog(tmp_path, extra))


def test_coco_has_segmentation_only_for_polygon_components(tmp_path: Path) -> None:
    scene = Scene(
        width=100,
        height=100,
        background_color=(0, 0, 0),
        components=(
            Component(label="bolt", x=10, y=10, width=20, height=10, color=(1, 1, 1)),
            Component(label="gear", x=40, y=40, width=21, height=20, color=(2, 2, 2), polygon=((40, 40), (60, 40), (60, 59), (40, 59))),
            Component(label="gear", x=90, y=90, width=10, height=10, color=(2, 2, 2), polygon=((90, 90), (120, 90), (120, 120), (90, 120))),
        ),
    )
    out = tmp_path / "a.json"
    export_coco(Dataset(scenes=(("s.bmp", scene),)), out)
    annotations = json.loads(out.read_text(encoding="utf-8"))["annotations"]
    assert "segmentation" not in annotations[0]
    assert annotations[1]["segmentation"] == [[40.0, 40.0, 60.0, 40.0, 60.0, 59.0, 40.0, 59.0]]
    assert annotations[1]["area"] == 20 * 19
    clipped = annotations[2]["segmentation"][0]
    assert max(clipped) <= 100 and annotations[2]["area"] == 100  # clipped to the image: 10 x 10 pixels


def test_generate_with_a_concave_catalogue_and_verify(tmp_path: Path) -> None:
    from hydra_umc_synthetic_data_gen.main import main

    catalog = _catalog(tmp_path, {"silhouette": "concave"})
    out = tmp_path / "ds"
    assert main(["generate", "--out", str(out), "--count", "3", "--seed", "4", "--width", "128", "--height", "128",
                 "--catalog", str(catalog), "--defect-rate", "0", "--format", "coco"]) == 0
    coco = next(out.rglob("*.json"), None)
    files = [p for p in out.rglob("*.json") if "images" in json.loads(p.read_text(encoding="utf-8")) and "annotations" in json.loads(p.read_text(encoding="utf-8"))]
    assert coco is not None and files
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["annotations"] and all("segmentation" in a for a in data["annotations"])
    assert main(["verify", "--out", str(out)]) == 0
    # a polygon outside the image, or an area that is not a count of pixels, is noticed
    data["annotations"][0]["segmentation"] = [[0.0, 0.0, 500.0, 0.0, 500.0, 500.0]]
    files[0].write_text(json.dumps(data), encoding="utf-8")
    assert main(["verify", "--out", str(out)]) == 1
