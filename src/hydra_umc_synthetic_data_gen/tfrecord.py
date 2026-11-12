# =============================================================================
# HYDRA-UMC-SYNTHETIC-DATA-GEN - src/hydra_umc_synthetic_data_gen/tfrecord.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
"""TFRecord export with no TensorFlow dependency.

A TFRecord file is a plain sequence of records, each framed as

    uint64 length | uint32 masked CRC-32C of the length | data | uint32 masked CRC-32C of the data

and the data of an image record is a serialised `tf.train.Example` protocol buffer: a map from a name to a list of byte
strings, floats or integers. Both are small and fixed formats, so they are written here with the standard library alone;
nothing is imported from TensorFlow or protobuf. The keys follow the TensorFlow Object Detection API (normalised boxes in
`image/object/bbox/*`, the class name in `image/object/class/text`, a class id that starts at 1 in
`image/object/class/label`, because 0 is the background there).

The export is off unless `generate --tfrecord` asks for it. `read_tfrecord` reads a file back (checking every CRC) so the
output can be verified without TensorFlow too.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from .export import Dataset, class_names

_POLY = 0x82F63B78  # CRC-32C (Castagnoli), reflected
_MASK_DELTA = 0xA282EAD8


def _table() -> tuple[int, ...]:
    out = []
    for n in range(256):
        c = n
        for _ in range(8):
            c = (c >> 1) ^ _POLY if c & 1 else c >> 1
        out.append(c)
    return tuple(out)


_TABLE = _table()


def crc32c(data: bytes) -> int:
    crc = 0xFFFFFFFF
    for byte in data:
        crc = _TABLE[(crc ^ byte) & 0xFF] ^ (crc >> 8)
    return crc ^ 0xFFFFFFFF


def masked_crc32c(data: bytes) -> int:
    """The CRC TFRecord stores: rotated by 15 bits and offset, so a CRC of data that holds its own CRC stays useful."""
    crc = crc32c(data)
    return (((crc >> 15) | (crc << 17)) + _MASK_DELTA) & 0xFFFFFFFF


def frame_record(data: bytes) -> bytes:
    length = struct.pack("<Q", len(data))
    return length + struct.pack("<I", masked_crc32c(length)) + data + struct.pack("<I", masked_crc32c(data))


# ------------------------------------------------------------------ protocol buffer encoding (only what Example needs)
def _varint(value: int) -> bytes:
    if value < 0:
        value += 1 << 64  # int64 is stored as its two's complement
    out = bytearray()
    while True:
        part = value & 0x7F
        value >>= 7
        if value:
            out.append(part | 0x80)
        else:
            out.append(part)
            return bytes(out)


def _field(number: int, payload: bytes) -> bytes:
    """A length-delimited field (wire type 2)."""
    return _varint((number << 3) | 2) + _varint(len(payload)) + payload


def bytes_feature(values: list[bytes]) -> bytes:
    return _field(1, b"".join(_field(1, v) for v in values))


def float_feature(values: list[float]) -> bytes:
    return _field(2, _field(1, b"".join(struct.pack("<f", v) for v in values)))


def int64_feature(values: list[int]) -> bytes:
    return _field(3, _field(1, b"".join(_varint(v) for v in values)))


def encode_example(features: dict[str, bytes]) -> bytes:
    """A serialised `tf.train.Example`; the keys are sorted, so the same features always give the same bytes."""
    entries = b"".join(_field(1, _field(1, key.encode("utf-8")) + _field(2, features[key])) for key in sorted(features))
    return _field(1, entries)


# ------------------------------------------------------------------ reading back
def _read_varint(buf: bytes, pos: int) -> tuple[int, int]:
    shift = result = 0
    while True:
        byte = buf[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
        shift += 7


def _fields(buf: bytes) -> Iterator[tuple[int, bytes]]:
    pos = 0
    while pos < len(buf):
        tag, pos = _read_varint(buf, pos)
        if tag & 7 != 2:
            raise ValueError("unexpected wire type in an Example")
        size, pos = _read_varint(buf, pos)
        yield tag >> 3, buf[pos : pos + size]
        pos += size


def decode_example(data: bytes) -> dict[str, list]:
    """The features of a serialised Example as `{key: list of bytes | floats | ints}`."""
    out: dict[str, list] = {}
    for _, features in _fields(data):
        for _, entry in _fields(features):
            key = ""
            value = b""
            for number, payload in _fields(entry):
                if number == 1:
                    key = payload.decode("utf-8")
                else:
                    value = payload
            kind, inner = next(_fields(value))
            if kind == 1:
                out[key] = [payload for _, payload in _fields(inner)]
                continue
            packed = next((payload for _, payload in _fields(inner)), b"")
            if kind == 2:
                out[key] = list(struct.unpack(f"<{len(packed) // 4}f", packed))
            else:
                values, pos = [], 0
                while pos < len(packed):
                    number, pos = _read_varint(packed, pos)
                    values.append(number - (1 << 64) if number >= 1 << 63 else number)
                out[key] = values
    return out


def read_tfrecord(path: Path) -> list[bytes]:
    """The records of a TFRecord file; a length or data CRC that does not match, or a file that ends inside a record, raises ValueError."""
    raw = path.read_bytes()
    records, pos = [], 0
    while pos < len(raw):
        if pos + 12 > len(raw):
            raise ValueError(f"{path.name}: the file ends inside a record header")
        length_bytes = raw[pos : pos + 8]
        if struct.unpack("<I", raw[pos + 8 : pos + 12])[0] != masked_crc32c(length_bytes):
            raise ValueError(f"{path.name}: bad length CRC at byte {pos}")
        (length,) = struct.unpack("<Q", length_bytes)
        start, end = pos + 12, pos + 12 + length
        if end + 4 > len(raw):
            raise ValueError(f"{path.name}: the file ends inside a record")
        data = raw[start:end]
        if struct.unpack("<I", raw[end : end + 4])[0] != masked_crc32c(data):
            raise ValueError(f"{path.name}: bad data CRC at byte {pos}")
        records.append(data)
        pos = end + 4
    return records


# ------------------------------------------------------------------ the dataset
@dataclass(frozen=True)
class TfrecordResult:
    path: Path
    records: int


def scene_example(image_name: str, image_bytes: bytes, scene, class_id: dict[str, int]) -> bytes:
    """One Example for a scene: the encoded image and its boxes, normalised to [0, 1] and clipped to the image."""
    xmin, xmax, ymin, ymax, text, label = [], [], [], [], [], []
    for component in scene.components:
        xmin.append(max(0.0, component.x / scene.width))
        xmax.append(min(1.0, (component.x + component.width) / scene.width))
        ymin.append(max(0.0, component.y / scene.height))
        ymax.append(min(1.0, (component.y + component.height) / scene.height))
        text.append(component.label.encode("utf-8"))
        label.append(class_id[component.label])
    suffix = Path(image_name).suffix.lstrip(".").lower()
    return encode_example(
        {
            "image/height": int64_feature([scene.height]),
            "image/width": int64_feature([scene.width]),
            "image/filename": bytes_feature([image_name.encode("utf-8")]),
            "image/source_id": bytes_feature([Path(image_name).stem.encode("utf-8")]),
            "image/encoded": bytes_feature([image_bytes]),
            "image/format": bytes_feature([suffix.encode("ascii")]),
            "image/object/bbox/xmin": float_feature(xmin),
            "image/object/bbox/xmax": float_feature(xmax),
            "image/object/bbox/ymin": float_feature(ymin),
            "image/object/bbox/ymax": float_feature(ymax),
            "image/object/class/text": bytes_feature(text),
            "image/object/class/label": int64_feature(label),
        }
    )


def export_tfrecord(dataset: Dataset, images_dir: Path, out_dir: Path, split_of: dict[str, str] | None = None) -> list[TfrecordResult]:
    """Write `tfrecord/<part>.tfrecord` (one file per part with `split_of`, otherwise `tfrecord/all.tfrecord`) from the images already
    written under `images_dir` (`images_dir/<part>/` in the Ultralytics layout, which `split_of` signals). Scenes are written in dataset
    order, so the same dataset gives the same bytes."""
    class_id = {name: index + 1 for index, name in enumerate(class_names(dataset))}
    groups: dict[str, list[bytes]] = {}
    for image_name, scene in dataset.scenes:
        part = split_of[image_name] if split_of else "all"
        source = images_dir / part / image_name if split_of else images_dir / image_name
        groups.setdefault(part, []).append(scene_example(image_name, source.read_bytes(), scene, class_id))
    target = out_dir / "tfrecord"
    target.mkdir(parents=True, exist_ok=True)
    results = []
    for part in sorted(groups):
        path = target / f"{part}.tfrecord"
        path.write_bytes(b"".join(frame_record(example) for example in groups[part]))
        results.append(TfrecordResult(path=path, records=len(groups[part])))
    return results
