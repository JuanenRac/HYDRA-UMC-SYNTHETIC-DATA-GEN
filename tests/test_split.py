# =============================================================================
# HYDRA-UMC-SYNTHETIC-DATA-GEN - tests/test_split.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hydra_umc_synthetic_data_gen.main import main
from hydra_umc_synthetic_data_gen.split import assign_splits, parse_split
from hydra_umc_synthetic_data_gen.verify import verify_output


def test_parse_split_accepts_a_valid_spec() -> None:
    assert parse_split("train=0.8,val=0.1,test=0.1") == {"train": 0.8, "val": 0.1, "test": 0.1}


@pytest.mark.parametrize("spec", ["train=0.5", "train=0.9,val=0.3", "val=1", "train=1,train=0", "train=nan", "x=1", "train=-1,val=2", "train"])
def test_parse_split_rejects_bad_specs(spec: str) -> None:
    with pytest.raises(ValueError):
        parse_split(spec)


def test_every_scene_is_in_exactly_one_part_and_the_split_is_stable() -> None:
    fractions = {"train": 0.8, "val": 0.1, "test": 0.1}
    parts = assign_splits(50, 7, fractions)
    flat = sorted(i for idx in parts.values() for i in idx)
    assert flat == list(range(50))
    assert [len(parts[n]) for n in ("train", "val", "test")] == [40, 5, 5]
    assert parts == assign_splits(50, 7, fractions)
    assert parts != assign_splits(50, 8, fractions)


def test_small_counts_still_give_every_part_a_scene() -> None:
    parts = assign_splits(4, 1, {"train": 0.8, "val": 0.1, "test": 0.1})
    assert sorted(len(v) for v in parts.values()) == [1, 1, 2]


def test_generate_with_split_writes_lists_and_verifies(tmp_path: Path) -> None:
    out = tmp_path / "ds"
    assert main(["generate", "--out", str(out), "--count", "10", "--seed", "3", "--split", "train=0.7,val=0.2,test=0.1"]) == 0
    train = (out / "train.txt").read_text().splitlines()
    val = (out / "val.txt").read_text().splitlines()
    test = (out / "test.txt").read_text().splitlines()
    assert (len(train), len(val), len(test)) == (7, 2, 1)
    assert not set(train) & set(val) and not set(train) & set(test) and not set(val) & set(test)
    assert all(line.startswith("./images/scene_") for line in train)
    yaml = (out / "data.yaml").read_text()
    assert "train: train.txt" in yaml and "nc: 5" in yaml and '0: "bolt"' in yaml
    assert verify_output(out) == []
    data = json.loads((out / "splits.json").read_text())
    data["splits"]["val"].append(data["splits"]["train"][0])
    (out / "splits.json").write_text(json.dumps(data))
    assert any(i.kind == "split_mismatch" for i in verify_output(out))


def test_generate_rejects_a_bad_split_and_coco_only(tmp_path: Path) -> None:
    assert main(["generate", "--out", str(tmp_path / "a"), "--split", "train=0.5"]) == 2
    assert main(["generate", "--out", str(tmp_path / "b"), "--split", "train=1", "--format", "coco"]) == 2


def test_nearby_seeds_do_not_share_a_scene_in_train_and_val(tmp_path: Path) -> None:
    for name, seed in (("a", 0), ("b", 50)):
        main(["generate", "--out", str(tmp_path / name), "--count", "10", "--seed", str(seed)])
    hashes = [
        {s["sha256"] for s in json.loads((tmp_path / n / "manifest.json").read_text())["scenes"]} for n in ("a", "b")
    ]
    assert not hashes[0] & hashes[1]
