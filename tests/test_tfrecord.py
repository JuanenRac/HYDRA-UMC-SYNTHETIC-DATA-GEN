# =============================================================================
# HYDRA-UMC-SYNTHETIC-DATA-GEN - tests/test_tfrecord.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
#
# The TFRecord export is written without TensorFlow, so it is checked here against the published CRC-32C test vector, the
# framing of the format, the encoding of an Example read back by an independent decoder, and the files `generate --tfrecord`
# writes.
# =============================================================================
from __future__ import annotations

import struct
from pathlib import Path

import pytest

from hydra_umc_synthetic_data_gen.main import main
from hydra_umc_synthetic_data_gen.tfrecord import (
    bytes_feature,
    crc32c,
    decode_example,
    encode_example,
    float_feature,
    frame_record,
    int64_feature,
    masked_crc32c,
    read_tfrecord,
)


def test_crc32c_matches_the_published_test_vectors() -> None:
    assert crc32c(b"123456789") == 0xE3069283
    assert crc32c(b"") == 0
    assert crc32c(b"\x00" * 32) == 0x8A9136AA  # iSCSI test vector: 32 bytes of zeros


def test_the_mask_rotates_and_offsets_the_crc() -> None:
    crc = crc32c(b"hydra")
    assert masked_crc32c(b"hydra") == (((crc >> 15) | (crc << 17)) + 0xA282EAD8) & 0xFFFFFFFF


def test_a_record_is_framed_with_length_and_two_masked_crcs() -> None:
    framed = frame_record(b"abc")
    assert struct.unpack("<Q", framed[:8])[0] == 3
    assert struct.unpack("<I", framed[8:12])[0] == masked_crc32c(framed[:8])
    assert framed[12:15] == b"abc"
    assert struct.unpack("<I", framed[15:19])[0] == masked_crc32c(b"abc")
    assert len(framed) == 19


def test_an_example_round_trips_all_three_kinds_of_list() -> None:
    features = {
        "b": bytes_feature([b"one", b"", b"three"]),
        "f": float_feature([0.5, 0.25, 1.0]),
        "i": int64_feature([0, 1, 300, 2**40, -7]),
    }
    assert decode_example(encode_example(features)) == {
        "b": [b"one", b"", b"three"],
        "f": [0.5, 0.25, 1.0],
        "i": [0, 1, 300, 2**40, -7],
    }


def test_the_encoding_of_an_example_is_known_bytes() -> None:
    # Example{features{feature{key:"a" value{int64_list{value:[1]}}}}} as protoc writes it
    assert encode_example({"a": int64_feature([1])}) == bytes.fromhex("0a0c0a0a0a01611205" "1a030a0101")


def test_the_keys_are_sorted_so_the_bytes_do_not_depend_on_the_order() -> None:
    a = encode_example({"x": int64_feature([1]), "y": int64_feature([2])})
    b = encode_example({"y": int64_feature([2]), "x": int64_feature([1])})
    assert a == b


def test_read_tfrecord_rejects_corruption(tmp_path: Path) -> None:
    good = frame_record(b"payload") + frame_record(b"second")
    path = tmp_path / "x.tfrecord"
    path.write_bytes(good)
    assert read_tfrecord(path) == [b"payload", b"second"]

    flipped = bytearray(good)
    flipped[13] ^= 0xFF  # inside the data of the first record
    path.write_bytes(bytes(flipped))
    with pytest.raises(ValueError, match="data CRC"):
        read_tfrecord(path)

    flipped = bytearray(good)
    flipped[2] ^= 0x01  # inside the length
    path.write_bytes(bytes(flipped))
    with pytest.raises(ValueError, match="length CRC"):
        read_tfrecord(path)

    path.write_bytes(good[:-3])
    with pytest.raises(ValueError, match="ends inside"):
        read_tfrecord(path)
    path.write_bytes(good[:5])
    with pytest.raises(ValueError, match="header"):
        read_tfrecord(path)


def _generate(out: Path, *extra: str) -> int:
    return main(["generate", "--out", str(out), "--count", "4", "--seed", "7", "--components", "3", "--format", "yolo", *extra])


def test_generate_writes_no_tfrecord_unless_asked(tmp_path: Path) -> None:
    assert _generate(tmp_path / "d") == 0
    assert not (tmp_path / "d" / "tfrecord").exists()


def test_generate_tfrecord_holds_every_scene_with_its_boxes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "d"
    assert _generate(out, "--tfrecord", "--image-format", "png") == 0
    assert "TFRecord: all.tfrecord=4" in capsys.readouterr().out

    records = [decode_example(r) for r in read_tfrecord(out / "tfrecord" / "all.tfrecord")]
    assert len(records) == 4
    classes = (out / "classes.txt").read_text(encoding="utf-8").splitlines()
    for index, example in enumerate(records):
        name = f"scene_{index:04d}.png"
        assert example["image/filename"] == [name.encode()]
        assert example["image/format"] == [b"png"]
        assert example["image/encoded"] == [(out / "images" / name).read_bytes()]
        labels = (out / "labels" / f"scene_{index:04d}.txt").read_text(encoding="utf-8").splitlines()
        assert len(example["image/object/class/label"]) == len(labels)
        for line, label, text, xmin, xmax, ymin, ymax in zip(
            labels, example["image/object/class/label"], example["image/object/class/text"],
            example["image/object/bbox/xmin"], example["image/object/bbox/xmax"],
            example["image/object/bbox/ymin"], example["image/object/bbox/ymax"], strict=True,
        ):
            cls, cx, cy, w, h = line.split()
            assert label == int(cls) + 1  # the ids of the Object Detection API start at 1
            assert text.decode() == classes[int(cls)]
            assert (xmin + xmax) / 2 == pytest.approx(float(cx), abs=1e-4)
            assert (ymin + ymax) / 2 == pytest.approx(float(cy), abs=1e-4)
            assert xmax - xmin == pytest.approx(float(w), abs=1e-4)
            assert ymax - ymin == pytest.approx(float(h), abs=1e-4)
            assert 0.0 <= xmin < xmax <= 1.0 and 0.0 <= ymin < ymax <= 1.0


def test_generate_tfrecord_is_reproducible(tmp_path: Path) -> None:
    assert _generate(tmp_path / "a", "--tfrecord") == 0
    assert _generate(tmp_path / "b", "--tfrecord") == 0
    assert (tmp_path / "a" / "tfrecord" / "all.tfrecord").read_bytes() == (tmp_path / "b" / "tfrecord" / "all.tfrecord").read_bytes()


def test_generate_tfrecord_writes_one_file_per_part_in_the_ultralytics_layout(tmp_path: Path) -> None:
    out = tmp_path / "d"
    code = main([
        "generate", "--out", str(out), "--count", "10", "--seed", "3", "--components", "2", "--format", "yolo",
        "--layout", "ultralytics", "--split", "train=0.6,val=0.2,test=0.2", "--tfrecord",
    ])
    assert code == 0
    files = sorted(p.name for p in (out / "tfrecord").iterdir())
    assert files == ["test.tfrecord", "train.tfrecord", "val.tfrecord"]
    total = sum(len(read_tfrecord(out / "tfrecord" / name)) for name in files)
    assert total == 10


def test_a_second_generate_over_the_same_folder_is_refused(tmp_path: Path) -> None:
    out = tmp_path / "d"
    assert _generate(out, "--tfrecord") == 0
    assert _generate(out, "--tfrecord") == 2
