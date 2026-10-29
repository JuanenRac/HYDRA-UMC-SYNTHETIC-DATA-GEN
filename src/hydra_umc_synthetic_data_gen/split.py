# =============================================================================
# HYDRA-UMC-SYNTHETIC-DATA-GEN - src/hydra_umc_synthetic_data_gen/split.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
"""Train/validation/test split of a generated dataset.

The split is a function of the base seed and the scene index only, so it is the same whatever the number of jobs, and
every scene lands in exactly one part. The folders `images/` and `labels/` stay flat (the manifest and `verify` rely on
that); the parts are written as list files at the root of the dataset, which is what a YOLO trainer reads from
`data.yaml`, plus `splits.json` with the same assignment for any other tool.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

SPLIT_NAMES = ("train", "val", "test")
SPLIT_FILES = ("splits.json", "data.yaml", "train.txt", "val.txt", "test.txt")


def parse_split(spec: str) -> dict[str, float]:
    """`train=0.8,val=0.1,test=0.1` -> fractions. Names must be train/val/test, fractions finite, >= 0, summing to 1."""
    fractions: dict[str, float] = {}
    for part in spec.split(","):
        name, sep, raw = part.strip().partition("=")
        if not sep or name not in SPLIT_NAMES:
            raise ValueError(f"--split expects train=A,val=B,test=C (names: {', '.join(SPLIT_NAMES)}); got {part!r}")
        if name in fractions:
            raise ValueError(f"--split names {name} twice")
        try:
            value = float(raw)
        except ValueError:
            raise ValueError(f"--split: {raw!r} is not a number") from None
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"--split: {name} must be a finite number >= 0")
        fractions[name] = value
    if "train" not in fractions or fractions["train"] <= 0:
        raise ValueError("--split needs a train part greater than 0")
    if abs(sum(fractions.values()) - 1.0) > 1e-6:
        raise ValueError("--split fractions must add up to 1")
    return fractions


def _order_key(base_seed: int, index: int) -> str:
    return hashlib.sha256(f"{base_seed}:split:{index}".encode("ascii")).hexdigest()


def assign_splits(count: int, base_seed: int, fractions: dict[str, float]) -> dict[str, list[int]]:
    """Scene indexes per part. Largest-remainder sizes; a part with a fraction > 0 gets at least one scene when
    `count` allows it (train keeps the rest)."""
    names = [n for n in SPLIT_NAMES if n in fractions]
    raw = {n: fractions[n] * count for n in names}
    sizes = {n: int(math.floor(raw[n])) for n in names}
    for n in sorted(names, key=lambda k: raw[k] - sizes[k], reverse=True)[: count - sum(sizes.values())]:
        sizes[n] += 1
    for n in names:
        if n != "train" and fractions[n] > 0 and sizes[n] == 0 and sizes["train"] > 1:
            sizes[n] += 1
            sizes["train"] -= 1
    order = sorted(range(count), key=lambda i: _order_key(base_seed, i))
    parts: dict[str, list[int]] = {}
    start = 0
    for n in names:
        parts[n] = sorted(order[start : start + sizes[n]])
        start += sizes[n]
    return parts


def write_splits(out_dir: Path, image_names: list[str], parts: dict[str, list[int]], class_list: list[str]) -> None:
    """Write `train.txt`/`val.txt`/`test.txt` (paths relative to the file, `./images/...`), `data.yaml` and `splits.json`."""
    def write(path: Path, text: str) -> None:
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)

    for name in SPLIT_NAMES:
        if name in parts:
            write(out_dir / f"{name}.txt", "".join(f"./images/{image_names[i]}\n" for i in parts[name]))
    yaml = ["path: .", "train: train.txt"]
    if "val" in parts:
        yaml.append("val: val.txt")
    if "test" in parts:
        yaml.append("test: test.txt")
    yaml.append(f"nc: {len(class_list)}")
    yaml.append("names:")
    yaml.extend(f"  {i}: {json.dumps(n)}" for i, n in enumerate(class_list))
    write(out_dir / "data.yaml", "\n".join(yaml) + "\n")
    payload = {"splits": {name: [image_names[i] for i in parts[name]] for name in parts}}
    write(out_dir / "splits.json", json.dumps(payload, indent=2))


def check_splits(out_dir: Path, image_names: set[str]) -> list[str]:
    """Problems in `splits.json` (empty when absent): every scene in exactly one part and nothing foreign."""
    path = out_dir / "splits.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))["splits"]
        seen: dict[str, str] = {}
        problems: list[str] = []
        for part, names in data.items():
            for name in names:
                if name in seen:
                    problems.append(f"{name} is in both {seen[name]} and {part}")
                seen[name] = part
        if set(seen) != image_names:
            problems.append("splits.json does not list exactly the scenes of the manifest")
        return problems
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return ["splits.json cannot be read"]
