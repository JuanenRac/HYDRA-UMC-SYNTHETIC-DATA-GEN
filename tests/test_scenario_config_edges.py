# =============================================================================
# HYDRA-UMC-SYNTHETIC-DATA-GEN - tests/test_scenario_config_edges.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The files that shape a dataset, at their edges: a registry that is too large, not JSON or not a list; an entry without classes or with a bad input shape;
a scenario file with an unknown key, a wrong type, a number out of range, a minimum above its maximum, a zone that is malformed or repeated. Every one is an error
with the name of the key, and none of them is ever repaired."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hydra_umc_synthetic_data_gen import scenarios as sc


def _write(tmp_path: Path, data: object, name: str = "file.json") -> Path:
    path = tmp_path / name
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return path


def _entry(**over) -> dict:
    entry = {"name": "pcb", "version": "1.2.0", "classes": ["a", "b"], "input_shape": [480, 640, 3]}
    entry.update(over)
    return entry


def test_the_newest_stable_entry_is_chosen_and_a_channel_other_than_stable_is_skipped(tmp_path: Path):
    registry = _write(tmp_path, [_entry(version="1.2.0"), _entry(version="1.10.0"), _entry(version="2.0.0", channel="beta"), _entry(name="other", version="9.0.0")])
    chosen = sc.load_model_classes(registry, "pcb")
    assert chosen.version == "1.10.0" and chosen.classes == ("a", "b") and (chosen.height, chosen.width) == (480, 640)


def test_a_version_asked_for_by_name_wins_even_on_another_channel(tmp_path: Path):
    registry = _write(tmp_path, [_entry(version="1.0.0"), _entry(version="2.0.0", channel="beta")])
    assert sc.load_model_classes(registry, "pcb", "2.0.0").version == "2.0.0"
    with pytest.raises(sc.ScenarioError, match="version 3.0.0"):
        sc.load_model_classes(registry, "pcb", "3.0.0")


@pytest.mark.parametrize("content", ["{", "{}", '"text"', "null"])
def test_a_registry_that_is_not_a_json_array_is_refused(tmp_path: Path, content: str):
    with pytest.raises(sc.ScenarioError):
        sc.load_model_classes(_write(tmp_path, content), "pcb")


def test_a_registry_that_is_not_there_or_too_large_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    with pytest.raises(sc.ScenarioError, match="cannot read the registry"):
        sc.load_model_classes(tmp_path / "missing.json", "pcb")
    registry = _write(tmp_path, [_entry()])
    monkeypatch.setattr(sc, "MAX_REGISTRY_BYTES", 5)
    with pytest.raises(sc.ScenarioError):  # refused; the size check is inside the block that reports a bad file, so the words are those of a bad file
        sc.load_model_classes(registry, "pcb")


def test_entries_that_are_not_objects_or_have_a_bad_version_are_passed_over_and_no_entry_at_all_is_an_error(tmp_path: Path):
    registry = _write(tmp_path, ["x", 3, _entry(version="one"), _entry(version=2), _entry(version="1.0")])
    with pytest.raises(sc.ScenarioError, match="no stable entry"):
        sc.load_model_classes(registry, "pcb")


@pytest.mark.parametrize("over", [
    {"classes": []}, {"classes": "ab"}, {"classes": ["a", "a"]}, {"classes": ["a", " "]}, {"classes": ["a", 3]},
    {"input_shape": [480, 640]}, {"input_shape": [0, 640, 3]}, {"input_shape": [480, 640, 2]}, {"input_shape": [480, True, 3]}, {"input_shape": "big"},
])
def test_an_entry_with_bad_classes_or_a_bad_input_shape_is_refused(tmp_path: Path, over: dict):
    with pytest.raises(sc.ScenarioError):
        sc.load_model_classes(_write(tmp_path, [_entry(**over)]), "pcb")


@pytest.mark.parametrize("content", ["{", "[]", '"x"'])
def test_a_scenario_file_that_is_not_a_json_object_is_refused(tmp_path: Path, content: str):
    for loader in (sc.load_servoing_config, sc.load_safety_config):
        with pytest.raises(sc.ScenarioError):
            loader(_write(tmp_path, content))


def test_a_scenario_file_that_is_not_there_is_refused(tmp_path: Path):
    with pytest.raises(sc.ScenarioError, match="cannot read the file"):
        sc.load_servoing_config(tmp_path / "missing.json")


@pytest.mark.parametrize("data", [
    {"surprise": 1},
    {"enabled": "yes"},
    {"fov_deg": 5}, {"fov_deg": 200}, {"fov_deg": True}, {"fov_deg": "60"}, {"fov_deg": float("nan")},
    {"objects": []}, {"objects": {"min": 0}}, {"objects": {"min": 4, "max": 2}}, {"objects": {"max": 99}}, {"objects": {"min": True}},
    {"depth_m": 3}, {"depth_m": {"min": 5.0, "max": 1.0}}, {"depth_m": {"min": 0.0}},
    {"max_tilt_deg": 120}, {"min_inside_fraction": 0.1}, {"max_attempts": 0}, {"max_attempts": 1.5},
])
def test_a_servoing_file_with_a_wrong_value_is_refused(tmp_path: Path, data: dict):
    with pytest.raises(sc.ScenarioError):
        sc.load_servoing_config(_write(tmp_path, data))


def test_a_servoing_file_with_nothing_in_it_gives_the_defaults_and_describes_itself(tmp_path: Path):
    config = sc.load_servoing_config(_write(tmp_path, {}))
    assert config == sc.ServoingConfig()
    assert config.enabled is False and config.describe()["objects"] == [1, 3]


ZONE = {"name": "bench", "kind": sc.ZONE_KINDS[0], "rect": [0.1, 0.1, 0.5, 0.5]}


@pytest.mark.parametrize("data", [
    {"surprise": 1},
    {"enabled": 1},
    {"zones": "all"}, {"zones": [ZONE] * 17},
    {"zones": ["bench"]}, {"zones": [{**ZONE, "extra": 1}]},
    {"zones": [{**ZONE, "name": "no good!"}]}, {"zones": [{**ZONE, "name": 3}]}, {"zones": [ZONE, ZONE]},
    {"zones": [{**ZONE, "kind": "swamp"}]},
    {"zones": [{**ZONE, "rect": [0.1, 0.1, 0.5]}]}, {"zones": [{**ZONE, "rect": [0.5, 0.1, 0.1, 0.5]}]}, {"zones": [{**ZONE, "rect": [0.1, 0.1, 1.5, 0.5]}]},
    {"zones": [{**ZONE, "rect": [0.1, True, 0.5, 0.5]}]},
    {"zones": [ZONE], "people": {"min": 5, "max": 1}}, {"zones": [ZONE], "people": 2}, {"zones": [ZONE], "people": {"max": 11}},
    {"zones": [ZONE], "height_fraction": {"min": 0.9, "max": 0.2}}, {"zones": [ZONE], "height_fraction": 3},
    {"zones": [ZONE], "in_zone_probability": 2}, {"zones": [ZONE], "min_overlap": 0},
    {"enabled": True},
])
def test_a_safety_file_with_a_wrong_value_is_refused(tmp_path: Path, data: dict):
    with pytest.raises(sc.ScenarioError):
        sc.load_safety_config(_write(tmp_path, data))


def test_a_safety_file_with_zones_is_read_and_describes_itself(tmp_path: Path):
    config = sc.load_safety_config(_write(tmp_path, {"enabled": True, "zones": [ZONE], "people": {"min": 1, "max": 2}}))
    assert config.enabled and config.zones[0].rect == (0.1, 0.1, 0.5, 0.5)
    assert config.describe()["people"] == [1, 2] and config.describe()["zones"][0]["name"] == "bench"
    assert sc.load_safety_config(_write(tmp_path, {}, "empty.json")) == sc.SafetyConfig()
