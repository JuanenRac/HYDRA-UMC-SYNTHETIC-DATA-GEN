# =============================================================================
# HYDRA-UMC-SYNTHETIC-DATA-GEN - tests/test_cli.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hydra_umc_synthetic_data_gen.main import main


def test_bare_invocation_prints_identity(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "HYDRA-UMC-SYNTHETIC-DATA-GEN" in captured.out


def test_generate_real_end_to_end_dataset(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out_dir = tmp_path / "dataset"

    exit_code = main(
        [
            "generate",
            "--out", str(out_dir),
            "--count", "3",
            "--seed", "10",
            "--components", "2",
            "--format", "both",
        ]
    )

    assert exit_code == 0
    images = sorted((out_dir / "images").glob("*.bmp"))
    assert len(images) == 3

    labels = sorted((out_dir / "labels").glob("*.txt"))
    assert len(labels) == 3
    assert (out_dir / "classes.txt").is_file()

    coco = json.loads((out_dir / "annotations.json").read_text(encoding="utf-8"))
    assert len(coco["images"]) == 3

    captured = capsys.readouterr()
    assert "Generated 3 scene(s)" in captured.out


def test_generate_is_reproducible_with_a_seed(tmp_path: Path) -> None:
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"

    main(["generate", "--out", str(out_a), "--count", "2", "--seed", "99"])
    main(["generate", "--out", str(out_b), "--count", "2", "--seed", "99"])

    bmp_a = (out_a / "images" / "scene_0000.bmp").read_bytes()
    bmp_b = (out_b / "images" / "scene_0000.bmp").read_bytes()
    assert bmp_a == bmp_b


def test_generate_yolo_only_skips_coco(tmp_path: Path) -> None:
    out_dir = tmp_path / "dataset"

    main(["generate", "--out", str(out_dir), "--count", "1", "--format", "yolo"])

    assert (out_dir / "classes.txt").is_file()
    assert not (out_dir / "annotations.json").exists()
