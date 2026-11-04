# =============================================================================
# HYDRA-UMC-SYNTHETIC-DATA-GEN - tests/test_urdf_joints.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""URDF catalogue parts: the chain of joint origins places the links of an assembly when the catalogue asks for it."""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from hydra_umc_synthetic_data_gen.shapes import CatalogError, load_catalog

URDF = """<robot name="r">
  <link name="base"><visual><geometry><box size="1 1 1"/></geometry></visual></link>
  <link name="arm"><visual><geometry><box size="1 1 1"/></geometry></visual></link>
  <joint name="j" type="revolute"><parent link="base"/><child link="arm"/><origin xyz="4 0 0" rpy="0 0 1.5707963267948966"/></joint>
</robot>"""


def _catalog(tmp_path: Path, extra: dict[str, object], urdf: str = URDF) -> Path:
    (tmp_path / "a.urdf").write_text(urdf, encoding="utf-8")
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps({"unit_scale": 1, "parts": [{"label": "assembly", "urdf": "a.urdf"}], **extra}), encoding="utf-8")
    return path


def _extent(tmp_path: Path, extra: dict[str, object], urdf: str = URDF) -> float:
    xs = [p[0] for p in load_catalog(_catalog(tmp_path, extra, urdf)).parts[0].points]
    return max(xs) - min(xs)


def test_joints_are_ignored_by_default(tmp_path: Path) -> None:
    assert _extent(tmp_path, {}) == pytest.approx(1.0)


def test_zero_places_the_second_link_by_the_joint_origin(tmp_path: Path) -> None:
    # the arm sits 4 m along x: the two unit boxes span -0.5 .. 4.5
    assert _extent(tmp_path, {"urdf_joints": "zero"}) == pytest.approx(5.0)


def test_zero_applies_the_rotation_of_the_joint(tmp_path: Path) -> None:
    urdf = URDF.replace('<box size="1 1 1"/></geometry></visual></link>\n  <joint', '<box size="1 1 1"/></geometry></visual></link>\n  <joint').replace(
        '<link name="arm"><visual><geometry><box size="1 1 1"/>', '<link name="arm"><visual><geometry><box size="1 3 1"/>')
    pts = load_catalog(_catalog(tmp_path, {"urdf_joints": "zero"}, urdf)).parts[0].points
    xs = [p[0] for p in pts]
    # turned a quarter about z, the 3 m side of the arm lies along x: 4 +- 1.5 and the base reaches -0.5
    assert max(xs) == pytest.approx(5.5, abs=1e-6)
    assert math.isclose(min(xs), -0.5, abs_tol=1e-6)


@pytest.mark.parametrize("bad", ["zeroish", 1, None])
def test_bad_value_is_refused(tmp_path: Path, bad: object) -> None:
    with pytest.raises(CatalogError):
        load_catalog(_catalog(tmp_path, {"urdf_joints": bad}))


def test_a_joint_to_an_unknown_link_or_a_loop_is_refused(tmp_path: Path) -> None:
    unknown = URDF.replace('<child link="arm"/>', '<child link="ghost"/>')
    with pytest.raises(CatalogError):
        load_catalog(_catalog(tmp_path, {"urdf_joints": "zero"}, unknown))
    loop = URDF.replace("</robot>", '<joint name="k" type="fixed"><parent link="arm"/><child link="base"/></joint></robot>')
    with pytest.raises(CatalogError):
        load_catalog(_catalog(tmp_path, {"urdf_joints": "zero"}, loop))
