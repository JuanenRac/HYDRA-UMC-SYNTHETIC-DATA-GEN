# =============================================================================
# HYDRA-UMC-SYNTHETIC-DATA-GEN - src/hydra_umc_synthetic_data_gen/validate.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
"""Real post-generation validation: structural scene invariants, corrupt
BMP-output detection, and label-distribution sanity - the checks a
consumer of this dataset would otherwise have to do by hand before
trusting it for training.

Corruption is checked against the exact known-good BMP layout
`render.py` itself writes (stdlib-only, no Pillow to lean on for a
second opinion) - a truncated or partially-written file is caught by
comparing the header's own declared size against both the recomputed
expected size and the actual bytes on disk.
"""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

from .export import Dataset
from .render import PNG_SIGNATURE, _row_size
from .scene import DEFECT_LABEL, Scene

BMP_HEADER_SIZE = 54  # 14-byte BITMAPFILEHEADER + 40-byte BITMAPINFOHEADER


@dataclass(frozen=True)
class ValidationIssue:
    kind: str
    detail: str


def validate_scene_bounds(image_name: str, scene: Scene) -> list[ValidationIssue]:
    """Every component must fit entirely within its own scene - a
    component that doesn't is either a scene.py bug or hand-edited data,
    and its bounding box would be nonsense to a downstream trainer."""
    issues: list[ValidationIssue] = []
    for c in scene.components:
        if c.x < 0 or c.y < 0 or c.x + c.width > scene.width or c.y + c.height > scene.height:
            issues.append(
                ValidationIssue(
                    "out_of_bounds",
                    f"{image_name}: component '{c.label}' at ({c.x},{c.y}) size {c.width}x{c.height} "
                    f"exceeds scene bounds {scene.width}x{scene.height}",
                )
            )
    return issues


def validate_png_integrity(image_name: str, path: Path, expected_width: int, expected_height: int) -> list[ValidationIssue]:
    """The PNG counterpart: signature, the CRC of every chunk, the size in the header and a pixel stream that inflates to
    exactly one filter byte plus three bytes a pixel for every row."""
    if not path.exists():
        return [ValidationIssue("missing_file", f"{image_name}: expected image file not found at {path}")]
    data = path.read_bytes()
    bad = lambda why: [ValidationIssue("corrupt_png", f"{image_name}: {why}")]  # noqa: E731
    if data[:8] != PNG_SIGNATURE:
        return bad("not a valid PNG (missing signature)")
    position, width, height, pixels, ended = 8, None, None, bytearray(), False
    while position + 12 <= len(data):
        length = struct.unpack(">I", data[position : position + 4])[0]
        kind = data[position + 4 : position + 8]
        body = data[position + 8 : position + 8 + length]
        crc = data[position + 8 + length : position + 12 + length]
        if len(body) != length or len(crc) != 4 or struct.unpack(">I", crc)[0] != zlib.crc32(kind + body) & 0xFFFFFFFF:
            return bad(f"chunk {kind!r} is truncated or its checksum is wrong")
        if kind == b"IHDR" and length == 13:
            width, height = struct.unpack(">II", body[:8])
        elif kind == b"IDAT":
            pixels.extend(body)
        elif kind == b"IEND":
            ended = True
        position += 12 + length
    if not ended or width is None:
        return bad("truncated PNG (no header or no end chunk)")
    if (width, height) != (expected_width, expected_height):
        return bad(f"PNG header reports {width}x{height}, expected {expected_width}x{expected_height}")
    try:
        raw = zlib.decompress(bytes(pixels))
    except zlib.error:
        return bad("the pixel data cannot be decompressed")
    if len(raw) != (1 + 3 * width) * height:
        return bad(f"pixel data is {len(raw)} bytes, expected {(1 + 3 * width) * height}")
    return []


def validate_bmp_integrity(image_name: str, path: Path, expected_width: int, expected_height: int) -> list[ValidationIssue]:
    """Catches a truncated, zero-length, or otherwise corrupt BMP write by
    recomputing the exact expected file size from `render.py`'s own row
    layout and comparing it against both the header's own declared size
    and the real size on disk - three numbers that must all agree."""
    if not path.exists():
        return [ValidationIssue("missing_file", f"{image_name}: expected image file not found at {path}")]

    data = path.read_bytes()
    if len(data) < BMP_HEADER_SIZE or data[0:2] != b"BM":
        return [ValidationIssue("corrupt_bmp", f"{image_name}: not a valid BMP (missing header/magic bytes)")]

    declared_file_size = struct.unpack("<I", data[2:6])[0]
    width, height = struct.unpack("<ii", data[18:26])
    expected_size = BMP_HEADER_SIZE + _row_size(width) * abs(height)

    issues: list[ValidationIssue] = []
    if declared_file_size != expected_size or len(data) != expected_size:
        issues.append(
            ValidationIssue(
                "corrupt_bmp",
                f"{image_name}: size mismatch (header declares {declared_file_size} bytes, "
                f"layout expects {expected_size}, actual file is {len(data)} bytes) - likely a truncated write",
            )
        )
    if (width, height) != (expected_width, expected_height):
        issues.append(
            ValidationIssue(
                "dimension_mismatch",
                f"{image_name}: BMP header reports {width}x{height}, expected {expected_width}x{expected_height}",
            )
        )
    return issues


def validate_label_distribution(
    dataset: Dataset,
    expected_labels: tuple[str, ...],
    defect_rate: float,
    *,
    tolerance: float = 0.25,
    min_sample: int = 20,
) -> list[ValidationIssue]:
    """A deterministic sanity check, not a strict statistical test - this
    is procedural placeholder data, not a real sensor feed. Only flags a
    deviation once there are enough non-defect components (`min_sample`)
    for the check to mean something, so it stays non-flaky on small
    `--count` runs while still catching a badly wired defect_rate (e.g.
    effectively always-defect or never-defect)."""
    non_defect = 0
    defect = 0
    unexpected: set[str] = set()
    for _, scene in dataset.scenes:
        for c in scene.components:
            if c.label == DEFECT_LABEL:
                defect += 1
            else:
                non_defect += 1
                if c.label not in expected_labels:
                    unexpected.add(c.label)

    issues: list[ValidationIssue] = []
    if unexpected:
        issues.append(ValidationIssue("unexpected_label", f"labels outside the configured set: {sorted(unexpected)}"))
    if non_defect >= min_sample:
        observed_rate = defect / non_defect
        if abs(observed_rate - defect_rate) > tolerance:
            issues.append(
                ValidationIssue(
                    "distribution_anomaly",
                    f"observed defect rate {observed_rate:.3f} deviates from configured {defect_rate:.3f} "
                    f"by more than tolerance {tolerance:.3f} across {non_defect} component(s)",
                )
            )
    return issues


def validate_dataset(
    dataset: Dataset,
    images_dir: Path,
    *,
    expected_labels: tuple[str, ...],
    defect_rate: float,
) -> list[ValidationIssue]:
    """Runs every real check above across the whole dataset - the single
    entry point `main.py`'s `generate` subcommand calls after rendering."""
    issues: list[ValidationIssue] = []
    for image_name, scene in dataset.scenes:
        issues.extend(validate_scene_bounds(image_name, scene))
        check = validate_png_integrity if image_name.endswith(".png") else validate_bmp_integrity
        issues.extend(check(image_name, images_dir / image_name, scene.width, scene.height))
    issues.extend(validate_label_distribution(dataset, expected_labels, defect_rate))
    return issues
