# =============================================================================
# HYDRA-UMC-SYNTHETIC-DATA-GEN - tests/test_verify_jobs_render.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
"""The faster renderer writes the same bytes, --jobs does not change the dataset, the manifest carries the hash of the
class list, and verify reads a dataset folder back and catches what was changed in it."""
from __future__ import annotations

import hashlib
import json
import random
import struct
from pathlib import Path

import pytest

from hydra_umc_synthetic_data_gen.main import main
from hydra_umc_synthetic_data_gen.manifest import classes_hash
from hydra_umc_synthetic_data_gen.render import _row_size, render_bmp
from hydra_umc_synthetic_data_gen.scene import FIXED_CLASSES, generate_scene
from hydra_umc_synthetic_data_gen.verify import verify_output


def reference_bmp_bytes(scene) -> bytes:
    """The renderer as it was before the flat rows: a list of lists of tuples, a loop over every pixel."""
    width, height = scene.width, scene.height
    pixels = [[scene.background_color for _ in range(width)] for _ in range(height)]
    for comp in scene.components:
        if comp.scratch is not None:
            for sp in comp.scratch:
                for oy in range(-sp.half_width, sp.half_width + 1):
                    for ox in range(-sp.half_width, sp.half_width + 1):
                        px, py = sp.x + ox, sp.y + oy
                        if 0 <= px < width and 0 <= py < height:
                            base = pixels[py][px]
                            pixels[py][px] = (
                                int(base[0] * (1 - sp.opacity) + comp.color[0] * sp.opacity),
                                int(base[1] * (1 - sp.opacity) + comp.color[1] * sp.opacity),
                                int(base[2] * (1 - sp.opacity) + comp.color[2] * sp.opacity),
                            )
            continue
        for py in range(max(0, comp.y), min(height, comp.y + comp.height)):
            for px in range(max(0, comp.x), min(width, comp.x + comp.width)):
                pixels[py][px] = comp.color
    row_size = _row_size(width)
    out = bytearray(b"BM" + struct.pack("<IHHI", 54 + row_size * height, 0, 0, 54))
    out += struct.pack("<IiiHHIIiiII", 40, width, height, 1, 24, 0, row_size * height, 0, 0, 0, 0)
    padding = b"\x00" * (row_size - width * 3)
    for y in range(height - 1, -1, -1):
        for r, g, b in pixels[y]:
            out += bytes((b, g, r))
        out += padding
    return bytes(out)


@pytest.mark.parametrize("seed", range(12))
def test_the_flat_renderer_writes_exactly_the_bytes_the_old_one_did(seed: int, tmp_path: Path) -> None:
    rng = random.Random(seed)
    scene = generate_scene(
        rng, width=rng.choice([5, 17, 64, 101]), height=rng.choice([1, 9, 48]), num_components=rng.choice([0, 3, 12]),
        defect_probability=0.6,
    )
    path = tmp_path / "scene.bmp"
    render_bmp(scene, path)
    assert path.read_bytes() == reference_bmp_bytes(scene)


def generate(out: Path, *extra: str) -> int:
    return main(["generate", "--out", str(out), "--count", "6", "--width", "96", "--height", "64", "--components", "5", "--seed", "11", *extra])


def test_the_dataset_is_the_same_with_one_process_or_several(tmp_path: Path) -> None:
    assert generate(tmp_path / "one") == 0
    assert generate(tmp_path / "three", "--jobs", "3") == 0
    one = json.loads((tmp_path / "one" / "manifest.json").read_text(encoding="utf-8"))
    three = json.loads((tmp_path / "three" / "manifest.json").read_text(encoding="utf-8"))
    assert one == three
    for name in ("labels/scene_0000.txt", "annotations.json", "classes.txt"):
        assert (tmp_path / "one" / name).read_bytes() == (tmp_path / "three" / name).read_bytes()


def test_the_number_of_jobs_is_bounded(tmp_path: Path, capsys) -> None:
    assert generate(tmp_path / "x", "--jobs", "0") == 2
    assert generate(tmp_path / "y", "--jobs", "999") == 2
    assert "--jobs" in capsys.readouterr().err


def test_the_manifest_carries_the_class_list_and_its_hash(tmp_path: Path) -> None:
    assert generate(tmp_path) == 0
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["classes"][: len(FIXED_CLASSES)] == list(FIXED_CLASSES)
    assert manifest["classes_sha256"] == classes_hash(manifest["classes"])
    assert manifest["classes_sha256"] == hashlib.sha256((tmp_path / "classes.txt").read_bytes()).hexdigest()


# ------------------------------------------------------------------ verify
@pytest.fixture()
def dataset(tmp_path: Path) -> Path:
    assert generate(tmp_path) == 0
    return tmp_path


def kinds(out: Path) -> set[str]:
    return {issue.kind for issue in verify_output(out)}


def test_a_fresh_dataset_verifies_and_so_does_the_command(dataset: Path, capsys) -> None:
    assert verify_output(dataset) == []
    assert main(["verify", "--out", str(dataset)]) == 0
    assert "VERIFY=PASS" in capsys.readouterr().out


def test_a_changed_image_is_a_checksum_mismatch(dataset: Path, capsys) -> None:
    image = dataset / "images" / "scene_0002.bmp"
    data = bytearray(image.read_bytes())
    data[100] ^= 0xFF
    image.write_bytes(bytes(data))
    assert "checksum_mismatch" in kinds(dataset)
    assert main(["verify", "--out", str(dataset)]) == 1
    assert "VERIFY=FAIL" in capsys.readouterr().out


def test_a_missing_or_extra_file_is_reported(dataset: Path) -> None:
    (dataset / "images" / "scene_0001.bmp").unlink()
    (dataset / "labels" / "scene_0003.txt").unlink()
    (dataset / "labels" / "stray.txt").write_text("0 0.5 0.5 0.1 0.1\n", encoding="utf-8")
    (dataset / "images" / "stray.bmp").write_bytes(b"BM")
    found = kinds(dataset)
    assert {"missing_file", "missing_label", "unexpected_file"} <= found


def test_yolo_lines_out_of_range_or_malformed_are_reported(dataset: Path) -> None:
    label = dataset / "labels" / "scene_0000.txt"
    original = label.read_text(encoding="utf-8")
    cases = {
        "bad_yolo_line": "0 0.5 0.5 0.1\n",
        "bad_yolo_class": "99 0.5 0.5 0.1 0.1\n",
        "yolo_out_of_range": "0 1.5 0.5 0.1 0.1\n",
    }
    for kind, text in cases.items():
        label.write_text(text, encoding="utf-8")
        assert kind in kinds(dataset), kind
    label.write_text("0 0.99 0.5 0.1 0.1\n", encoding="utf-8")  # inside [0, 1] but the box leaves the image
    assert "yolo_out_of_range" in kinds(dataset)
    label.write_text(original, encoding="utf-8")
    assert verify_output(dataset) == []


def test_a_line_count_that_is_not_the_component_count_is_reported(dataset: Path) -> None:
    label = dataset / "labels" / "scene_0000.txt"
    lines = label.read_text(encoding="utf-8").splitlines()
    label.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    assert "count_mismatch" in kinds(dataset)


def test_coco_duplicates_dangling_references_and_boxes_outside_the_image_are_reported(dataset: Path) -> None:
    path = dataset / "annotations.json"
    original = json.loads(path.read_text(encoding="utf-8"))

    def changed(edit) -> set[str]:
        data = json.loads(json.dumps(original))
        edit(data)
        path.write_text(json.dumps(data), encoding="utf-8")
        return kinds(dataset)

    assert "coco_duplicate_id" in changed(lambda d: d["annotations"][1].update(id=d["annotations"][0]["id"]))
    assert "coco_duplicate_id" in changed(lambda d: d["images"][1].update(id=d["images"][0]["id"]))
    assert "coco_dangling" in changed(lambda d: d["annotations"][0].update(image_id=999))
    assert "coco_dangling" in changed(lambda d: d["annotations"][0].update(category_id=999))
    assert "coco_out_of_range" in changed(lambda d: d["annotations"][0].update(bbox=[90, 60, 50, 50]))
    assert "bad_coco" in changed(lambda d: d["annotations"][0].update(area=1))
    assert "count_mismatch" in changed(lambda d: d["annotations"].pop())
    path.write_text(json.dumps(original), encoding="utf-8")
    assert verify_output(dataset) == []


def test_a_class_list_that_does_not_match_its_hash_or_classes_txt_is_reported(dataset: Path) -> None:
    (dataset / "classes.txt").write_text("gear\nbolt\nbracket\nconnector\ndefect\n", encoding="utf-8")
    assert "class_mismatch" in kinds(dataset)
    manifest_path = dataset / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["classes_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert "class_mismatch" in kinds(dataset)


def test_a_manifest_from_an_older_version_is_checked_as_far_as_it_allows(dataset: Path) -> None:
    manifest_path = dataset / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    del manifest["classes"], manifest["classes_sha256"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    found = verify_output(dataset)
    assert [issue.kind for issue in found] == ["class_mismatch"]
    assert "older version" in found[0].detail


def test_a_folder_without_a_manifest_is_reported_not_a_crash(tmp_path: Path, capsys) -> None:
    assert verify_output(tmp_path)[0].kind == "missing_manifest"
    assert main(["verify", "--out", str(tmp_path)]) == 1
    (tmp_path / "manifest.json").write_text("not json", encoding="utf-8")
    assert verify_output(tmp_path)[0].kind == "missing_manifest"
