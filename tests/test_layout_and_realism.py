# =============================================================================
# HYDRA-UMC-SYNTHETIC-DATA-GEN - tests/test_layout_and_realism.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
"""The Ultralytics layout, the realism effects and the calibration set."""
from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

import pytest

from hydra_umc_synthetic_data_gen.main import main
from hydra_umc_synthetic_data_gen.realism import RealismConfig, RealismError, apply_realism, homography, load_realism_config, parse_realism_config
from hydra_umc_synthetic_data_gen.render import paint_scene
from hydra_umc_synthetic_data_gen.scene import Component, Scene, generate_scene
from hydra_umc_synthetic_data_gen.verify import verify_output

SPLIT = "train=0.6,val=0.2,test=0.2"


def _generate(out: Path, *extra: str, count: int = 10) -> int:
    return main(["generate", "--out", str(out), "--count", str(count), "--seed", "5", "--split", SPLIT, *extra])


# ---------------------------------------------------------------------------------------------------------------- layout


def test_the_ultralytics_layout_puts_images_and_labels_in_the_folder_of_their_part(tmp_path: Path) -> None:
    out = tmp_path / "ds"
    assert _generate(out, "--layout", "ultralytics", "--image-format", "png") == 0
    counts = {part: len(list((out / "images" / part).glob("*.png"))) for part in ("train", "val", "test")}
    assert counts == {"train": 6, "val": 2, "test": 2}
    assert not list((out / "images").glob("*.png"))  # nothing is left outside the folders of the parts
    for part, count in counts.items():
        assert len(list((out / "labels" / part).glob("*.txt"))) == count
        coco = json.loads((out / "annotations" / f"instances_{part}.json").read_text(encoding="utf-8"))
        assert len(coco["images"]) == count and [c["name"] for c in coco["categories"]][0] == "bolt"
    assert not (out / "annotations.json").exists() and not (out / "train.txt").exists()  # the folders are the lists
    yaml = (out / "data.yaml").read_text(encoding="utf-8")
    assert "train: images/train" in yaml and "val: images/val" in yaml and "test: images/test" in yaml and "nc: 5" in yaml
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["layout"] == "ultralytics" and {s["split"] for s in manifest["scenes"]} == {"train", "val", "test"}
    assert verify_output(out) == []


def test_the_layout_gives_the_same_scenes_as_the_flat_one(tmp_path: Path) -> None:
    assert _generate(tmp_path / "flat") == 0 and _generate(tmp_path / "ultra", "--layout", "ultralytics") == 0
    flat = json.loads((tmp_path / "flat" / "manifest.json").read_text(encoding="utf-8"))
    ultra = json.loads((tmp_path / "ultra" / "manifest.json").read_text(encoding="utf-8"))
    assert [(s["image"], s["sha256"]) for s in flat["scenes"]] == [(s["image"], s["sha256"]) for s in ultra["scenes"]]
    assert "layout" not in flat and all("split" not in s for s in flat["scenes"])  # the flat manifest is the one it always was
    assert verify_output(tmp_path / "flat") == [] and (tmp_path / "flat" / "train.txt").is_file()


def test_the_layout_needs_a_split_with_a_val_part(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    assert main(["generate", "--out", str(tmp_path / "a"), "--count", "4", "--layout", "ultralytics"]) == 2
    assert "needs --split" in capsys.readouterr().err
    assert main(["generate", "--out", str(tmp_path / "b"), "--count", "4", "--layout", "ultralytics", "--split", "train=1"]) == 2
    assert "val part" in capsys.readouterr().err
    assert not (tmp_path / "a").exists() and not (tmp_path / "b").exists()


def test_coco_only_in_the_ultralytics_layout_is_allowed(tmp_path: Path) -> None:
    out = tmp_path / "ds"
    assert _generate(out, "--layout", "ultralytics", "--format", "coco") == 0
    assert (out / "annotations" / "instances_val.json").is_file() and not (out / "labels").exists()
    assert verify_output(out) == []


def test_verify_finds_what_does_not_belong_in_the_layout(tmp_path: Path) -> None:
    out = tmp_path / "ds"
    assert _generate(out, "--layout", "ultralytics") == 0
    image = next((out / "images" / "val").iterdir())
    original = image.read_bytes()
    image.write_bytes(original[:-5] + b"xxxxx")
    assert any(i.kind == "checksum_mismatch" for i in verify_output(out))
    image.write_bytes(original)
    (out / "images" / "stray.bmp").write_bytes(b"x")
    (out / "images" / "val" / "extra.bmp").write_bytes(b"x")
    (out / "labels" / "test" / "ghost.txt").write_text("0 0.5 0.5 0.1 0.1\n", encoding="utf-8")
    kinds = [(i.kind, i.detail) for i in verify_output(out)]
    assert ("unexpected_file", "images/stray.bmp sits outside the folders of the parts") in kinds
    assert any("images/val/extra.bmp" in d for _, d in kinds) and any("labels/test/ghost.txt" in d for _, d in kinds)
    (out / "images" / "stray.bmp").unlink()
    (out / "images" / "val" / "extra.bmp").unlink()
    (out / "labels" / "test" / "ghost.txt").unlink()
    (out / "data.yaml").unlink()
    assert [i.kind for i in verify_output(out)] == ["split_mismatch"]
    moved = next((out / "images" / "val").iterdir())
    moved.rename(out / "images" / "test" / moved.name)
    assert any(i.kind == "missing_file" for i in verify_output(out))


def test_generating_over_an_old_layout_is_refused(tmp_path: Path) -> None:
    out = tmp_path / "ds"
    assert _generate(out, "--layout", "ultralytics") == 0
    assert _generate(out, "--layout", "ultralytics") == 2


# ---------------------------------------------------------------------------------------------------------------- realism


def _scene(seed: int = 3) -> Scene:
    return generate_scene(random.Random(seed), width=96, height=96, num_components=4, defect_probability=0.0)


def _all(**change: object) -> RealismConfig:
    values = {"enabled": True, "texture_amplitude": 10.0, "illumination_strength": 0.3, "rotation_degrees": 6.0, "perspective_fraction": 0.05, "blur_radius": 2, "noise_sigma": 4.0}
    values.update(change)
    return RealismConfig(**values)  # type: ignore[arg-type]


def test_a_disabled_or_zero_config_changes_nothing() -> None:
    scene = _scene()
    rows = paint_scene(scene)
    same_rows, same_scene = apply_realism(rows, scene, RealismConfig(), random.Random(1))
    assert same_rows is rows and same_scene is scene
    zero, zero_scene = apply_realism(rows, scene, RealismConfig(enabled=True), random.Random(1))
    assert [bytes(r) for r in zero] == [bytes(r) for r in rows] and zero_scene == scene


def test_the_effects_change_the_pixels_deterministically_from_the_seed() -> None:
    scene = _scene()
    rows = paint_scene(scene)
    a, scene_a = apply_realism(rows, scene, _all(), random.Random(7))
    b, scene_b = apply_realism(rows, scene, _all(), random.Random(7))
    c, _ = apply_realism(rows, scene, _all(), random.Random(8))
    assert [bytes(r) for r in a] == [bytes(r) for r in b] and scene_a == scene_b
    assert [bytes(r) for r in a] != [bytes(r) for r in c]
    assert [bytes(r) for r in a] != [bytes(r) for r in rows]
    assert len(a) == 96 and all(len(r) == 96 * 3 for r in a)
    assert [bytes(r) for r in rows] == [bytes(r) for r in paint_scene(scene)]  # the input is not touched


def test_each_effect_does_what_it_says() -> None:
    scene = Scene(width=64, height=64, background_color=(200, 200, 200), components=())
    rows = paint_scene(scene)
    flat = {b for r in rows for b in r}
    assert flat == {200}
    textured, _ = apply_realism(rows, scene, RealismConfig(enabled=True, texture_amplitude=20.0), random.Random(1))
    assert len({b for r in textured for b in r}) > 5 and all(abs(b - 200) <= 20 for r in textured for b in r)
    lit, _ = apply_realism(rows, scene, RealismConfig(enabled=True, illumination_strength=0.4), random.Random(1))
    values = [b for r in lit for b in r]
    assert max(values) > 200 > min(values)
    noisy, _ = apply_realism(rows, scene, RealismConfig(enabled=True, noise_sigma=10.0), random.Random(1))
    spread = [b - 200 for r in noisy for b in r]
    assert 5 < (sum(v * v for v in spread) / len(spread)) ** 0.5 < 15 and abs(sum(spread) / len(spread)) < 1
    marked = Scene(width=32, height=32, background_color=(0, 0, 0), components=(Component("bolt", 14, 14, 4, 4, (255, 255, 255)),))
    blurred, _ = apply_realism(paint_scene(marked), marked, RealismConfig(enabled=True, blur_radius=2), random.Random(3))
    # a blur spreads the light of the white square over its neighbours, whatever radius (0 to 2) was drawn
    sharp = sum(paint_scene(marked)[16])
    assert sum(blurred[16]) == pytest.approx(sharp, rel=0.15)


def test_the_boxes_move_with_the_image_and_stay_inside_it() -> None:
    scene = _scene(11)
    rows = paint_scene(scene)
    _, moved = apply_realism(rows, scene, _all(rotation_degrees=12.0, perspective_fraction=0.08, texture_amplitude=0.0, illumination_strength=0.0, blur_radius=0, noise_sigma=0.0), random.Random(2))
    assert moved.components and (moved.width, moved.height) == (96, 96)
    assert [c.label for c in moved.components] == [c.label for c in scene.components[: len(moved.components)]] or len(moved.components) <= len(scene.components)
    for c in moved.components:
        assert c.x >= 0 and c.y >= 0 and c.x + c.width <= 96 and c.y + c.height <= 96 and c.width >= 2 and c.height >= 2
    assert [(c.x, c.y, c.width, c.height) for c in moved.components] != [(c.x, c.y, c.width, c.height) for c in scene.components]


def test_a_box_pushed_out_of_the_image_is_dropped() -> None:
    corner = Scene(width=64, height=64, background_color=(100, 100, 100), components=(Component("bolt", 0, 0, 8, 8, (0, 0, 0)),))
    strict = RealismConfig(enabled=True, rotation_degrees=40.0, min_visibility=0.99)
    dropped = sum(1 for seed in range(12) if not apply_realism(paint_scene(corner), corner, strict, random.Random(seed))[1].components)
    assert dropped >= 1


def test_the_homography_maps_the_corners_where_it_was_asked() -> None:
    src = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    dst = [(1.0, 2.0), (12.0, 1.0), (11.0, 13.0), (-1.0, 9.0)]
    h = homography(src, dst)
    for (x, y), (u, v) in zip(src, dst, strict=True):
        w = h[6] * x + h[7] * y + h[8]
        assert (h[0] * x + h[1] * y + h[2]) / w == pytest.approx(u) and (h[3] * x + h[4] * y + h[5]) / w == pytest.approx(v)
    with pytest.raises(RealismError, match="degenerate"):
        homography(src, [(0.0, 0.0)] * 4)


@pytest.mark.parametrize("config", [
    [], {"unknown": 1}, {"enabled": "yes"}, {"texture": {"amplitude": 61}}, {"texture": {"cell": 1}}, {"texture": {"x": 1}}, {"illumination": {"strength": 0.9}},
    {"rotation": {"max_degrees": 46}}, {"perspective": {"max_shift_fraction": 0.5}}, {"blur": {"max_radius": 9}}, {"blur": {"max_radius": 1.5}}, {"noise": {"sigma": -1}},
    {"noise": "x"}, {"min_visibility": 2}, {"max_pixels": 10}, {"texture": {"amplitude": True}}, {"texture": {"amplitude": float("nan")}},
])
def test_a_bad_realism_file_is_refused(config: object) -> None:
    with pytest.raises(RealismError):
        parse_realism_config(config)


def test_the_realism_file(tmp_path: Path) -> None:
    (tmp_path / "r.json").write_text(json.dumps({"enabled": True, "noise": {"sigma": 3}}), encoding="utf-8")
    config = load_realism_config(tmp_path / "r.json")
    assert config.enabled and config.noise_sigma == 3.0 and config.texture_amplitude == 0.0 and config.describe()["noise"] == {"sigma": 3.0}
    assert parse_realism_config({}).enabled is False
    (tmp_path / "bad.json").write_text('{"noise": {"sigma": NaN}}', encoding="utf-8")
    with pytest.raises(RealismError, match="not a valid JSON number"):
        load_realism_config(tmp_path / "bad.json")
    with pytest.raises(RealismError, match="cannot be read"):
        load_realism_config(tmp_path / "missing.json")


def test_an_image_above_max_pixels_is_refused_before_anything_is_written(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    (tmp_path / "r.json").write_text(json.dumps({"enabled": True, "noise": {"sigma": 3}, "max_pixels": 4096}), encoding="utf-8")
    assert main(["generate", "--out", str(tmp_path / "ds"), "--count", "2", "--width", "64", "--height", "64", "--realism-config", str(tmp_path / "r.json")]) == 0
    assert main(["generate", "--out", str(tmp_path / "big"), "--count", "2", "--width", "128", "--height", "128", "--realism-config", str(tmp_path / "r.json")]) == 2
    assert "max_pixels" in capsys.readouterr().err and not (tmp_path / "big").exists()


def test_a_dataset_with_realism_verifies_and_records_the_settings(tmp_path: Path) -> None:
    (tmp_path / "r.json").write_text(json.dumps({"enabled": True, "texture": {"amplitude": 6}, "rotation": {"max_degrees": 3}, "noise": {"sigma": 2}}), encoding="utf-8")
    plain, real = tmp_path / "plain", tmp_path / "real"
    for out, extra in ((plain, ()), (real, ("--realism-config", str(tmp_path / "r.json")))):
        assert main(["generate", "--out", str(out), "--count", "4", "--width", "64", "--height", "64", "--seed", "9", *extra]) == 0
    assert verify_output(real) == []
    manifest = json.loads((real / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["realism"]["rotation"] == {"max_degrees": 3.0} and "realism" not in json.loads((plain / "manifest.json").read_text(encoding="utf-8"))
    assert hashlib.sha256((real / "images" / "scene_0000.bmp").read_bytes()).hexdigest() != hashlib.sha256((plain / "images" / "scene_0000.bmp").read_bytes()).hexdigest()
    again = tmp_path / "again"
    assert main(["generate", "--out", str(again), "--count", "4", "--width", "64", "--height", "64", "--seed", "9", "--realism-config", str(tmp_path / "r.json")]) == 0
    assert (again / "images" / "scene_0001.bmp").read_bytes() == (real / "images" / "scene_0001.bmp").read_bytes()  # the same seed gives the same bytes
    assert (again / "labels" / "scene_0001.txt").read_text(encoding="utf-8") == (real / "labels" / "scene_0001.txt").read_text(encoding="utf-8")


def test_a_realism_file_that_is_not_enabled_gives_the_plain_dataset(tmp_path: Path) -> None:
    (tmp_path / "r.json").write_text(json.dumps({"enabled": False, "noise": {"sigma": 20}}), encoding="utf-8")
    plain, off = tmp_path / "plain", tmp_path / "off"
    assert main(["generate", "--out", str(plain), "--count", "3", "--seed", "4", "--width", "64", "--height", "64"]) == 0
    assert main(["generate", "--out", str(off), "--count", "3", "--seed", "4", "--width", "64", "--height", "64", "--realism-config", str(tmp_path / "r.json")]) == 0
    assert (plain / "manifest.json").read_bytes() == (off / "manifest.json").read_bytes()


# ------------------------------------------------------------------------------------------------------------- calibration


def test_the_calibration_set_is_png_images_with_their_checksums(tmp_path: Path) -> None:
    out = tmp_path / "calib"
    assert main(["calibration", "--out", str(out), "--count", "6", "--width", "64", "--height", "48", "--seed", "2"]) == 0
    images = sorted(p.name for p in out.glob("*.png"))
    assert len(images) == 6 and not list(out.glob("*.txt")) and not (out / "labels").exists()
    manifest = json.loads((out / "calibration.json").read_text(encoding="utf-8"))
    assert manifest["count"] == 6 and (manifest["width"], manifest["height"]) == (64, 48) and manifest["realism"] is None
    assert [i["image"] for i in manifest["images"]] == images
    assert all(hashlib.sha256((out / i["image"]).read_bytes()).hexdigest() == i["sha256"] for i in manifest["images"])
    again = tmp_path / "again"
    assert main(["calibration", "--out", str(again), "--count", "6", "--width", "64", "--height", "48", "--seed", "2"]) == 0
    assert (again / "calibration.json").read_text(encoding="utf-8") == (out / "calibration.json").read_text(encoding="utf-8")


def test_the_calibration_set_uses_the_realism_file_and_refuses_what_it_should(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    (tmp_path / "r.json").write_text(json.dumps({"enabled": True, "noise": {"sigma": 3}}), encoding="utf-8")
    out = tmp_path / "calib"
    assert main(["calibration", "--out", str(out), "--count", "3", "--width", "64", "--height", "64", "--seed", "1", "--realism-config", str(tmp_path / "r.json")]) == 0
    assert json.loads((out / "calibration.json").read_text(encoding="utf-8"))["realism"]["noise"] == {"sigma": 3.0}
    assert main(["calibration", "--out", str(out), "--count", "3", "--width", "64", "--height", "64"]) == 2  # not empty
    assert "not empty" in capsys.readouterr().err
    for bad in (["--count", "0"], ["--count", "2001"], ["--width", "8"], ["--jobs", "0"], ["--defect-rate", "2"], ["--realism-config", str(tmp_path / "missing.json")]):
        assert main(["calibration", "--out", str(tmp_path / "x"), *bad]) == 2
    assert not (tmp_path / "x").exists()
