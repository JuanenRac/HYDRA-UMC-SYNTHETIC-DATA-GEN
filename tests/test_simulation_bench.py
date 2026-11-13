# =============================================================================
# HYDRA-UMC-SYNTHETIC-DATA-GEN - tests/test_simulation_bench.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Simulation bench: the real dataset factory, driven through its command line, against an independent reading of what it wrote.

The factory is the simulator of the camera: it draws a scene from a seed, renders it and writes the labels. This bench runs it for many seeds and every option and
checks the output from the other side: the labels against the manifest, the splits as a partition, the TFRecord against the labels, the same seed against itself
across formats, layouts and processes. Then it damages the dataset the way a copy, a disk or a careless edit does, with a fixed seed, and requires `verify` to see it.
Nothing here says how a model trained on these images behaves on a real camera: that needs the camera."""
from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

import pytest

from hydra_umc_synthetic_data_gen.main import main
from hydra_umc_synthetic_data_gen.split import assign_splits, parse_split
from hydra_umc_synthetic_data_gen.tfrecord import decode_example, read_tfrecord
from hydra_umc_synthetic_data_gen.verify import verify_output

SEED = 20260101


def _generate(out: Path, *extra: str, count: int = 8, seed: int = SEED) -> int:
    return main(["generate", "--out", str(out), "--count", str(count), "--seed", str(seed), *extra])


def _manifest(out: Path) -> dict:
    return json.loads((out / "manifest.json").read_text(encoding="utf-8"))


def _hashes(out: Path) -> dict[str, str]:
    return {scene["image"]: scene["sha256"] for scene in _manifest(out)["scenes"]}


def _label_files(out: Path) -> dict[str, Path]:
    return {path.stem: path for path in sorted((out / "labels").rglob("*.txt"))}


def test_the_labels_agree_with_the_manifest_scene_by_scene(tmp_path: Path) -> None:
    assert _generate(tmp_path, "--format", "yolo", count=12) == 0
    manifest = _manifest(tmp_path)
    classes = (tmp_path / "classes.txt").read_text(encoding="utf-8").split()
    labels = _label_files(tmp_path)
    for scene in manifest["scenes"]:
        lines = [line.split() for line in labels[Path(scene["image"]).stem].read_text(encoding="utf-8").splitlines() if line.strip()]
        assert len(lines) == scene["num_components"]
        counted: dict[str, int] = {}
        for line in lines:
            assert len(line) == 5 and all(0.0 <= float(v) <= 1.0 for v in line[1:])
            counted[classes[int(line[0])]] = counted.get(classes[int(line[0])], 0) + 1
        assert counted == scene["label_counts"]


@pytest.mark.parametrize("seed", [0, 1, 7, SEED])
def test_the_same_seed_gives_the_same_images_whatever_the_format_the_layout_and_the_number_of_processes(tmp_path: Path, seed: int) -> None:
    runs = {
        "flat": ("--format", "both"),
        "yolo-only": ("--format", "yolo"),
        "two-jobs": ("--format", "both", "--jobs", "2"),
        "split-flat": ("--format", "both", "--split", "train=0.5,val=0.25,test=0.25"),
        "ultralytics": ("--format", "both", "--split", "train=0.5,val=0.25,test=0.25", "--layout", "ultralytics"),
    }
    reference = None
    for name, flags in runs.items():
        out = tmp_path / name
        assert _generate(out, *flags, count=6, seed=seed) == 0, name
        hashes = _hashes(out)
        reference = reference or hashes
        assert hashes == reference, name
        assert verify_output(out) == [], name


def test_another_seed_gives_other_images_and_the_seed_is_recorded(tmp_path: Path) -> None:
    assert _generate(tmp_path / "a", seed=1) == 0 and _generate(tmp_path / "b", seed=2) == 0
    assert _hashes(tmp_path / "a") != _hashes(tmp_path / "b")
    manifest = _manifest(tmp_path / "a")
    assert manifest["seed"] == 1 and manifest["reproducible"] is True


def test_the_splits_are_a_partition_of_the_scenes_with_sizes_that_follow_the_fractions() -> None:
    rng = random.Random(SEED)
    for _ in range(200):
        count = rng.randint(3, 400)
        val = rng.randint(0, 30)
        test = rng.randint(0, 30)
        fractions = parse_split(f"train={(100 - val - test) / 100},val={val / 100},test={test / 100}")
        parts = assign_splits(count, rng.randrange(10_000), fractions)
        everything = sorted(i for indexes in parts.values() for i in indexes)
        assert everything == list(range(count))  # no scene in two parts, none lost
        for name, fraction in fractions.items():
            # the sizes are rounded to whole scenes; a part with a share gets at least one scene, which train pays for
            assert abs(len(parts[name]) - fraction * count) <= 2.0, (count, name, fractions)
            assert fraction == 0 or len(parts[name]) >= 1


def test_the_part_a_scene_goes_to_depends_on_the_seed_and_the_index_only() -> None:
    fractions = parse_split("train=0.6,val=0.2,test=0.2")
    first = assign_splits(50, 11, fractions)
    assert first == assign_splits(50, 11, fractions) and first != assign_splits(50, 12, fractions)


@pytest.mark.parametrize("spec", ["", "train", "train=1,val=0.5", "val=1", "train=0", "train=0.5,val=0.5,val=0", "train=nan,val=0", "train=-1,val=2", "dev=1", "train=a"])
def test_a_split_that_cannot_work_is_refused_before_anything_is_written(tmp_path: Path, spec: str, capsys) -> None:
    out = tmp_path / "never"
    assert _generate(out, "--split", spec) != 0
    assert not out.exists() or not any(out.iterdir())


def test_the_tfrecord_holds_the_same_boxes_as_the_labels(tmp_path: Path) -> None:
    assert _generate(tmp_path, "--format", "yolo", "--tfrecord", "--split", "train=0.5,val=0.25,test=0.25", "--layout", "ultralytics", count=12) == 0
    manifest = _manifest(tmp_path)
    classes = (tmp_path / "classes.txt").read_text(encoding="utf-8").split()
    by_split: dict[str, set[str]] = {}
    for scene in manifest["scenes"]:
        by_split.setdefault(scene["split"], set()).add(Path(scene["image"]).stem)
    labels = _label_files(tmp_path)
    seen = 0
    for split, stems in by_split.items():
        records = [decode_example(data) for data in read_tfrecord(tmp_path / "tfrecord" / f"{split}.tfrecord")]
        assert {record["image/source_id"][0].decode() for record in records} == stems
        for record in records:
            stem = record["image/source_id"][0].decode()
            expected = [line.split() for line in labels[stem].read_text(encoding="utf-8").splitlines() if line.strip()]
            assert [name.decode() for name in record["image/object/class/text"]] == [classes[int(line[0])] for line in expected]
            assert len(record["image/object/bbox/xmin"]) == len(expected)
            assert hashlib.sha256(record["image/encoded"][0]).hexdigest() == next(s["sha256"] for s in manifest["scenes"] if Path(s["image"]).stem == stem)
            seen += 1
    assert seen == 12


def test_a_tfrecord_cut_short_or_with_a_flipped_byte_is_refused_by_the_reader(tmp_path: Path) -> None:
    assert _generate(tmp_path, "--format", "yolo", "--tfrecord", count=4) == 0
    path = next((tmp_path / "tfrecord").glob("*.tfrecord"))
    data = path.read_bytes()
    rng = random.Random(SEED)
    for cut in sorted({rng.randrange(1, len(data) - 1) for _ in range(8)}):
        path.write_bytes(data[:cut])
        try:
            records = read_tfrecord(path)
        except ValueError:
            continue
        assert len(records) < 4  # a cut on the border of a record is a shorter file, never a longer one
    for position in sorted({rng.randrange(0, min(len(data), 4000)) for _ in range(10)}):
        flipped = bytearray(data)
        flipped[position] ^= 0x55
        path.write_bytes(bytes(flipped))
        with pytest.raises(ValueError):
            read_tfrecord(path)


def test_damage_to_a_dataset_is_always_seen_by_verify(tmp_path: Path) -> None:
    rng = random.Random(SEED)
    assert _generate(tmp_path / "ref", "--format", "both", count=10) == 0
    reference = tmp_path / "ref"
    assert verify_output(reference) == []
    images = sorted((reference / "images").iterdir())
    labels = sorted((reference / "labels").iterdir())
    for round_ in range(12):
        victim = tmp_path / f"damaged-{round_}"
        _generate(victim, "--format", "both", count=10)
        kind = rng.choice(["flip-image", "truncate-image", "delete-image", "delete-label", "empty-label", "extra-image", "bad-manifest", "wrong-count"])
        image = victim / "images" / rng.choice(images).name
        label = victim / "labels" / rng.choice(labels).name
        if kind == "flip-image":
            data = bytearray(image.read_bytes())
            data[rng.randrange(len(data))] ^= 1 << rng.randrange(8)
            image.write_bytes(bytes(data))
        elif kind == "truncate-image":
            image.write_bytes(image.read_bytes()[: rng.randrange(1, 60)])
        elif kind == "delete-image":
            image.unlink()
        elif kind == "delete-label":
            label.unlink()
        elif kind == "empty-label":
            label.write_text("", encoding="utf-8")
        elif kind == "extra-image":
            (victim / "images" / "stray.bmp").write_bytes(b"BM")
        elif kind == "bad-manifest":
            (victim / "manifest.json").write_text("{ not json", encoding="utf-8")
        else:
            manifest = _manifest(victim)
            manifest["count"] += 1
            (victim / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        assert verify_output(victim) != [], kind
        assert main(["verify", "--out", str(victim)]) == 1, kind


@pytest.mark.parametrize("flags", [["--count", "0"], ["--count", "-3"], ["--width", "0"], ["--height", "-1"], ["--components", "0"], ["--defect-rate", "2"], ["--defect-rate", "-0.1"], ["--jobs", "0"]])
def test_values_that_cannot_work_are_refused_without_leaving_a_half_written_dataset(tmp_path: Path, flags: list[str]) -> None:
    out = tmp_path / "never"
    assert main(["generate", "--out", str(out), "--seed", "1", *flags]) != 0
    assert not (out / "manifest.json").exists()

