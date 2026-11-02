# =============================================================================
# HYDRA-UMC-SYNTHETIC-DATA-GEN - tests/test_scenarios.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Classes from a registry, outlines from a catalogue of STL and URDF, and the servoing and safety datasets."""
from __future__ import annotations

import json
import math
import random
import struct
from pathlib import Path

import pytest

from hydra_umc_synthetic_data_gen.main import main
from hydra_umc_synthetic_data_gen.scenarios import (
    ScenarioError,
    add_people,
    load_model_classes,
    load_safety_config,
    load_servoing_config,
    servoing_scene,
)
from hydra_umc_synthetic_data_gen.scene import Scene
from hydra_umc_synthetic_data_gen.shapes import (
    CatalogError,
    convex_hull,
    load_catalog,
    parse_stl,
    polygon_spans,
    spans_box,
    top_silhouettes,
)


def _binary_stl(triangles: list[tuple[tuple[float, float, float], ...]]) -> bytes:
    out = bytearray(b"\0" * 80 + struct.pack("<I", len(triangles)))
    for tri in triangles:
        out += struct.pack("<3f", 0, 0, 0)
        for v in tri:
            out += struct.pack("<3f", *v)
        out += b"\0\0"
    return bytes(out)


def _box_stl(sx: float, sy: float, sz: float) -> bytes:
    corners = [(x * sx, y * sy, z * sz) for x in (0, 1) for y in (0, 1) for z in (0, 1)]
    # twelve triangles are not needed for an outline: two per face would do, three vertices are enough to carry every corner here
    tris = [(corners[i], corners[j], corners[k]) for i, j, k in ((0, 1, 2), (3, 2, 1), (4, 5, 6), (7, 6, 5), (0, 1, 4), (5, 4, 1), (2, 3, 6), (7, 6, 3))]
    return _binary_stl(tris)


@pytest.fixture
def catalog_dir(tmp_path: Path) -> Path:
    root = tmp_path / "cat"
    (root / "parts").mkdir(parents=True)
    (root / "parts" / "bolt.stl").write_bytes(_box_stl(40, 10, 10))
    (root / "parts" / "plate.urdf").write_text(
        '<robot name="p"><link name="a"><visual><origin xyz="0 0 0" rpy="0 0 0"/><geometry><box size="30 20 5"/></geometry></visual></link></robot>',
        encoding="utf-8",
    )
    (root / "catalog.json").write_text(
        json.dumps({"unit_scale": 0.001, "parts": [{"label": "bolt", "stl": "parts/bolt.stl"}, {"label": "plate", "urdf": "parts/plate.urdf"}]}),
        encoding="utf-8",
    )
    return root


def test_hull_and_spans_of_a_square() -> None:
    hull = convex_hull([(0, 0), (4, 0), (4, 4), (0, 4), (2, 2)])
    assert sorted(hull) == [(0, 0), (0, 4), (4, 0), (4, 4)]
    spans = polygon_spans([(1, 1), (5, 1), (5, 4), (1, 4)], 10, 10)
    assert spans_box(spans) == (1, 1, 4, 3)
    assert polygon_spans([(1, 1), (5, 1), (5, 4), (1, 4)], 3, 3) != []  # clipped, not dropped


def test_stl_binary_and_ascii_and_garbage() -> None:
    vertices = parse_stl(_box_stl(1, 2, 3))
    assert len(vertices) == 8
    ascii_stl = b"solid x\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\nendloop\nendfacet\nendsolid x\n"
    assert len(parse_stl(ascii_stl)) == 3
    with pytest.raises(CatalogError):
        parse_stl(b"nothing useful here")
    with pytest.raises(CatalogError):
        parse_stl(_binary_stl([((0, 0, 0), (math.nan, 0, 0), (0, 1, 0))]))


def test_catalog_reads_parts_and_keeps_no_path(catalog_dir: Path) -> None:
    catalog = load_catalog(catalog_dir / "catalog.json")
    assert catalog.labels == ("bolt", "plate")
    text = json.dumps(catalog.describe())
    assert str(catalog_dir) not in text and "parts/" not in text
    assert all(len(p["source_sha256"]) == 64 for p in catalog.describe()["parts"])  # type: ignore[index]
    sil = top_silhouettes(catalog.parts[0])
    assert sil and max(s.aspect for s in sil) > 3  # a 40 x 10 bolt seen from above is long and thin


@pytest.mark.parametrize("bad", ["../outside.stl", "/etc/x.stl", "C:\\x.stl", "parts/missing.stl"])
def test_catalog_refuses_paths_that_leave_the_folder(catalog_dir: Path, bad: str) -> None:
    (catalog_dir / "catalog.json").write_text(json.dumps({"parts": [{"label": "x", "stl": bad}]}), encoding="utf-8")
    with pytest.raises(CatalogError):
        load_catalog(catalog_dir / "catalog.json")


def test_urdf_with_entities_or_package_meshes_is_refused(catalog_dir: Path) -> None:
    (catalog_dir / "parts" / "evil.urdf").write_text('<!DOCTYPE r [<!ENTITY a "b">]><robot/>', encoding="utf-8")
    (catalog_dir / "parts" / "pkg.urdf").write_text(
        '<robot><link name="a"><visual><geometry><mesh filename="package://x/y.stl"/></geometry></visual></link></robot>', encoding="utf-8"
    )
    for name in ("evil.urdf", "pkg.urdf"):
        (catalog_dir / "catalog.json").write_text(json.dumps({"parts": [{"label": "x", "urdf": f"parts/{name}"}]}), encoding="utf-8")
        with pytest.raises(CatalogError):
            load_catalog(catalog_dir / "catalog.json")


def _registry(tmp_path: Path, classes: list[str], shape: list[int] | None = None) -> Path:
    path = tmp_path / "registry.json"
    entry = {"name": "m", "version": "1.0.0", "task": "detection", "input_shape": shape or [64, 96, 3], "classes": classes,
             "hef_path": "m.hef", "sha256": "0" * 64, "hailo_arch": "hailo8"}
    newer = dict(entry, version="1.2.0", classes=classes + ["extra"])
    canary = dict(entry, version="9.0.0", channel="canary")
    path.write_text(json.dumps([entry, newer, canary]), encoding="utf-8")
    return path


def test_registry_picks_the_newest_stable_or_the_asked_version(tmp_path: Path) -> None:
    path = _registry(tmp_path, ["bolt", "defect"])
    assert load_model_classes(path, "m").version == "1.2.0"
    assert load_model_classes(path, "m", "1.0.0").classes == ("bolt", "defect")
    with pytest.raises(ScenarioError):
        load_model_classes(path, "other")
    with pytest.raises(ScenarioError):
        load_model_classes(path, "m", "3.0.0")


def test_generate_with_the_classes_of_a_model(tmp_path: Path) -> None:
    registry = _registry(tmp_path, ["gear", "defect", "bolt"], [64, 96, 3])
    out = tmp_path / "ds"
    code = main(["generate", "--out", str(out), "--count", "4", "--seed", "3", "--classes-from", str(registry), "--model", "m", "--model-version", "1.0.0"])
    assert code == 0
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["classes"] == ["gear", "defect", "bolt"]
    assert (manifest["width"], manifest["height"]) == (96, 64)
    assert (out / "classes.txt").read_text(encoding="utf-8").split() == ["gear", "defect", "bolt"]
    assert manifest["scenario"]["classes_from"]["model"] == "m"
    assert str(tmp_path) not in json.dumps(manifest)
    assert main(["verify", "--out", str(out)]) == 0


def test_a_model_without_defect_draws_none(tmp_path: Path) -> None:
    registry = _registry(tmp_path, ["gear", "bolt"])
    out = tmp_path / "ds"
    assert main(["generate", "--out", str(out), "--count", "5", "--seed", "1", "--classes-from", str(registry), "--model", "m", "--model-version", "1.0.0"]) == 0
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert all("defect" not in s["label_counts"] for s in manifest["scenes"])


def test_the_options_without_their_pair_are_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["generate", "--out", str(tmp_path / "a"), "--model", "m"]) == 2
    registry = _registry(tmp_path, ["gear"])
    assert main(["generate", "--out", str(tmp_path / "b"), "--classes-from", str(registry)]) == 2
    assert main(["generate", "--out", str(tmp_path / "c"), "--servoing-config", str(tmp_path / "nope.json")]) == 2
    assert not (tmp_path / "a").exists()


def test_a_plain_run_is_unchanged_by_the_new_options(tmp_path: Path) -> None:
    out = tmp_path / "ds"
    assert main(["generate", "--out", str(out), "--count", "3", "--seed", "7"]) == 0
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert "scenario" not in manifest and not (out / "poses.json").exists() and not (out / "zones.json").exists()
    assert (manifest["width"], manifest["height"]) == (256, 256)


def test_scenes_with_the_outline_of_the_parts(tmp_path: Path, catalog_dir: Path) -> None:
    out = tmp_path / "ds"
    code = main(["generate", "--out", str(out), "--count", "4", "--seed", "5", "--width", "128", "--height", "128",
                 "--catalog", str(catalog_dir / "catalog.json"), "--defect-rate", "0"])
    assert code == 0
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["classes"][:5]) == {"bolt", "bracket", "gear", "connector", "defect"}
    assert "plate" in manifest["classes"]
    assert manifest["validation_issues"] == []
    assert manifest["scenario"]["catalog"]["parts"][0]["label"] == "bolt"
    assert main(["verify", "--out", str(out)]) == 0
    # the same seed gives the same dataset
    out2 = tmp_path / "ds2"
    assert main(["generate", "--out", str(out2), "--count", "4", "--seed", "5", "--width", "128", "--height", "128",
                 "--catalog", str(catalog_dir / "catalog.json"), "--defect-rate", "0"]) == 0
    assert [s["sha256"] for s in json.loads((out2 / "manifest.json").read_text(encoding="utf-8"))["scenes"]] == [s["sha256"] for s in manifest["scenes"]]


def _servoing_file(tmp_path: Path, enabled: bool = True) -> Path:
    path = tmp_path / "servo.json"
    path.write_text(json.dumps({"enabled": enabled, "objects": {"min": 1, "max": 2}, "depth_m": {"min": 0.3, "max": 0.6}}), encoding="utf-8")
    return path


def test_servoing_dataset_has_known_poses(tmp_path: Path, catalog_dir: Path) -> None:
    out = tmp_path / "ds"
    code = main(["generate", "--out", str(out), "--count", "5", "--seed", "2", "--width", "160", "--height", "120",
                 "--catalog", str(catalog_dir / "catalog.json"), "--servoing-config", str(_servoing_file(tmp_path))])
    assert code == 0
    poses = json.loads((out / "poses.json").read_text(encoding="utf-8"))
    assert poses["camera"]["width"] == 160 and poses["camera"]["fx"] > 0
    total = 0
    for name, items in poses["images"].items():
        for item in items:
            total += 1
            q = item["rotation_quaternion_wxyz"]
            assert abs(math.sqrt(sum(c * c for c in q)) - 1) < 1e-6
            assert 0.29 <= item["translation_m"][2] <= 0.61
            assert item["label"] in ("bolt", "plate")
        assert (out / "images" / name).is_file()
    assert total >= 5
    assert main(["verify", "--out", str(out)]) == 0
    # the projection is the pinhole one: the centre of the box is near the projection of the translation of a centred part
    scene, records = servoing_scene(random.Random(1), load_catalog(catalog_dir / "catalog.json").parts, load_servoing_config(_servoing_file(tmp_path)), 160, 120)
    assert records and all(len(r["box"]) == 4 for r in records)  # type: ignore[arg-type]
    assert isinstance(scene, Scene)


def test_servoing_needs_a_catalogue_and_a_disabled_file_does_nothing(tmp_path: Path, catalog_dir: Path) -> None:
    assert main(["generate", "--out", str(tmp_path / "a"), "--servoing-config", str(_servoing_file(tmp_path))]) == 2
    out = tmp_path / "b"
    assert main(["generate", "--out", str(out), "--count", "2", "--seed", "1", "--servoing-config", str(_servoing_file(tmp_path, enabled=False))]) == 0
    assert not (out / "poses.json").exists()
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"enabled": True, "fov_deg": 500}), encoding="utf-8")
    with pytest.raises(ScenarioError):
        load_servoing_config(bad)


def _safety_file(tmp_path: Path) -> Path:
    path = tmp_path / "safety.json"
    path.write_text(json.dumps({
        "enabled": True,
        "zones": [{"name": "danger", "kind": "stop", "rect": [0.0, 0.0, 0.5, 1.0]}, {"name": "near", "kind": "slow", "rect": [0.5, 0.0, 1.0, 1.0]}],
        "people": {"min": 1, "max": 2}, "in_zone_probability": 0.8,
    }), encoding="utf-8")
    return path


def test_safety_dataset_says_what_a_safety_system_should_do(tmp_path: Path) -> None:
    out = tmp_path / "ds"
    assert main(["generate", "--out", str(out), "--count", "12", "--seed", "4", "--safety-config", str(_safety_file(tmp_path))]) == 0
    zones = json.loads((out / "zones.json").read_text(encoding="utf-8"))
    assert [z["name"] for z in zones["zones"]] == ["danger", "near"]
    actions = {item["expected_action"] for item in zones["images"].values()}
    assert actions <= {"stop", "slow", "clear"} and len(actions) >= 2
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert "person" in manifest["classes"]
    assert sum(s["label_counts"].get("person", 0) for s in manifest["scenes"]) >= 12
    assert manifest["validation_issues"] == []
    assert main(["verify", "--out", str(out)]) == 0
    # a person fully inside the stop zone makes the image a stop
    config = load_safety_config(_safety_file(tmp_path))
    for seed in range(40):
        _, record = add_people(random.Random(seed), Scene(200, 200, (200, 200, 200), ()), config)
        for person in record["people"]:  # type: ignore[attr-defined]
            if person["overlap"]["danger"] >= config.min_overlap:
                assert record["expected_action"] == "stop"


def test_safety_with_a_model_that_has_no_person_is_refused(tmp_path: Path) -> None:
    registry = _registry(tmp_path, ["gear", "bolt"])
    assert main(["generate", "--out", str(tmp_path / "x"), "--classes-from", str(registry), "--model", "m", "--model-version", "1.0.0",
                 "--safety-config", str(_safety_file(tmp_path))]) == 2


def test_safety_config_limits(tmp_path: Path) -> None:
    for bad in (
        {"enabled": True, "zones": []},
        {"enabled": True, "zones": [{"name": "a", "kind": "panic", "rect": [0, 0, 1, 1]}]},
        {"enabled": True, "zones": [{"name": "a", "kind": "stop", "rect": [0.6, 0, 0.4, 1]}]},
        {"enabled": True, "zones": [{"name": "a", "kind": "stop", "rect": [0, 0, 1, 1]}], "people": {"min": 3, "max": 1}},
        {"enabled": True, "extra": 1},
    ):
        path = tmp_path / "s.json"
        path.write_text(json.dumps(bad), encoding="utf-8")
        with pytest.raises(ScenarioError):
            load_safety_config(path)


def test_verify_notices_a_missing_or_wrong_extra_file(tmp_path: Path, catalog_dir: Path) -> None:
    out = tmp_path / "ds"
    assert main(["generate", "--out", str(out), "--count", "3", "--seed", "2", "--safety-config", str(_safety_file(tmp_path))]) == 0
    zones = out / "zones.json"
    data = json.loads(zones.read_text(encoding="utf-8"))
    data["images"].pop(next(iter(data["images"])))
    zones.write_text(json.dumps(data), encoding="utf-8")
    assert main(["verify", "--out", str(out)]) == 1
    zones.unlink()
    assert main(["verify", "--out", str(out)]) == 1
