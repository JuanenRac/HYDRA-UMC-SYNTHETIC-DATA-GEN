# Changelog

All notable work on **HYDRA-UMC-SYNTHETIC-DATA-GEN** is summarized here, newest first. Full
session-by-session detail (including dates) lives in a private,
unpublished internal log - this file is public, so it intentionally
omits calendar dates.

## Versioning scheme

`pyproject.toml`'s `version` field bumps automatically on every real
build (`build.sh`/`.bat` - see `bump_version.py`, run as the first real
step of both scripts).

It follows the ecosystem-wide base-10 "odometer" rule rather than
semantic-versioning judgment calls:

- `PATCH` +1 on every build
- when `PATCH` would exceed 9, it resets to 0 and `MINOR` +1 instead (e.g. `0.0.9` -> `0.1.0`, never `0.0.10`)
- the same carry cascades into `MAJOR` if `MINOR` would exceed 9

---

## CI - real pytest suite now actually runs

- **`.github/workflows/ci.yml`** - the real `tests/` pytest suite is now
  actually installed and run in CI. The baseline workflow's Python
  handling previously only compile-checked (`py_compile`) every `.py`
  file and validated the manifest/docs - it never ran `pytest`, so a
  regression in `tests/` could be merged without CI ever failing.
  CI-only fix, no runtime code changed, no version bump.

## [0.0.7]

- **Fixed a real bug found by an ecosystem-wide bug audit: a small scene
  could always generate components larger than the canvas itself.**
  `generate_scene()`'s own `min_size`/`max_size` (defaults 16/48) were
  never compared against the real `width`/`height` being generated, and
  aren't exposed as CLI flags either - `main.py`'s own `MIN_DIMENSION`
  only validates that width/height are at least 16, never that they're
  large enough for a real component to actually fit. A CLI-accepted
  scene as small as `--width 20 --height 20` could produce a component
  wider/taller than the canvas, always position-clamped to `x=0`/`y=0`
  and overflowing the edge - `validate_scene_bounds` correctly caught it
  as `out_of_bounds`, but only after the invalid image/annotation files
  were already written to disk. `generate_scene()` now clamps both
  `min_size` and `max_size` to the real scene dimensions itself before
  ever picking a component size, so no caller (CLI or direct) can
  produce an out-of-canvas component regardless of what it passes. New
  regression test sweeping 50 seeds against a real 20x20 scene.

## [0.0.6] - Bounded dataset generation inputs

- **`main.py`** - `generate` rejects zero/oversized scene counts,
  dimensions outside 16..4096, invalid component counts and non-finite or
  out-of-range defect probabilities before it creates output files. This
  keeps malformed automation from producing invalid scenes or exhausting
  host resources.
- Added CLI regression coverage for each rejected input category.
- 41/41 tests passing.

## [0.0.5] - Reproducible-seed manifest and real output validation

- **`manifest.py`** - a real `manifest.json` is now written into every `generate` output directory: `seed`, a `reproducible` flag (true only when a `--seed` was given), the requested generation parameters, and one entry per scene with its label counts and a real sha256 checksum of the rendered BMP bytes. Reproducibility was already true in practice (`--seed` already drove a deterministic `random.Random` per scene) but was never a recorded, checkable claim - now two runs with the same seed can be proven byte-identical by comparing checksums instead of re-rendering and diffing files by hand.
- **`validate.py`** - real post-generation validation, run automatically at the end of every `generate` call: (1) scene-bounds checking, catching any component whose rectangle doesn't fully fit inside its own scene; (2) BMP-integrity checking, which recomputes the exact expected file size from `render.py`'s own row-padding layout and flags a truncated/corrupt image file (verified against a real truncated file, not just a synthetic byte string); (3) label-distribution sanity, flagging an observed defect rate that deviates from the configured `--defect-rate` by more than a tolerance once there are enough samples to mean something (guarded by a minimum sample size so small `--count` runs never flake). `generate` now exits 1 and prints every issue if validation fails, 0 otherwise - closes the audit's "distribution/corrupt-output validation" requirement with real, tested checks rather than a TODO.
- **`main.py`** - `_run_generate()` now runs validation and writes the manifest after export, printing whether the run was reproducible and where the manifest landed; existing `--seed`/`--count`/`--format` behavior is unchanged.
- **`build.sh`** - fixed a version double-bump: the manifest-sync step ran `bump_manifest_version.py` without `--sync` *before* the native `bump_version.py` step, so `pyproject.toml` advanced twice per build while the manifest advanced once. Reordered to bump native first, then `--sync` after (matching `build.bat`, which already had the correct order).
- 17 new tests (`test_manifest.py`, `test_validate.py`, plus 3 new assertions in `test_cli.py` covering the manifest end-to-end and the seeded-checksum-match case) - 35 total, all passing. Verified live: a real `generate` run producing a real `manifest.json` with real sha256 checksums, and a real truncated BMP file (a genuine render cut in half, not a synthetic corrupt string) correctly caught by `validate_bmp_integrity` as a size mismatch.

## [0.0.4] - Real v0 procedural 2D dataset generation

- **`scene.py`** - real, deterministic (given a seeded `random.Random`) procedural placement of labeled rectangles, with a real "defect" overlay injected per component at a configurable probability. Honestly 2D placeholder shapes, not real 3D component meshes - the real photorealistic rendering needs HYDRA-UMC-TWIN's own physics/rendering engine, which doesn't exist yet (TWIN is itself still scaffolding).
- **`render.py`** - real, stdlib-only 24-bit BMP rasterization (`struct` only, no Pillow): writes a real, valid, viewable image file for each generated scene. `read_bmp_dimensions()` is used by this project's own tests.
- **`export.py`** - real YOLO (`classes.txt` + one label `.txt` per image, normalized boxes) and COCO (`annotations.json`, full images/annotations/categories schema) export, pixel-perfect by construction since bounding boxes come directly from the same coordinates `scene.py` placed and `render.py` painted. TFRecord export is future work (needs a real TensorFlow dependency this v0 doesn't take on).
- **`main.py`** - new `generate` subcommand (`--out`, `--count`, `--width`/`--height`, `--components`, `--defect-rate`, `--seed`, `--format yolo|coco|both`). Bare invocation is unchanged: identity/version/role.
- 16 new real tests (`tests/`) - generation determinism and bounds-checking, real BMP file validity (magic bytes, parsed dimensions, exact padded file size), YOLO/COCO export correctness against hand-computed expected values, and a real end-to-end CLI round-trip that generates a dataset and inspects the files on disk.
- Real verification beyond the test suite: generated a real 5-scene dataset via the CLI, opened one of the real output BMP files with an independent image library (.NET `System.Drawing`, re-encoded to PNG) and visually confirmed real colored rectangles including a visible defect overlay.

## [0.0.1] - Initial scaffolding

- **`src/hydra_umc_synthetic_data_gen/main.py`** - minimal real entry point. No generation logic yet - procedural scene randomization, physics-based rendering through HYDRA-UMC-TWIN, and automatic YOLO/COCO/TFRecord annotation export land in a later pass.
- **`pyproject.toml`** - packaging metadata, no runtime dependencies yet.
- **`bump_version.py`** - ecosystem-standard odometer bump script.
- **`build.sh` / `build.bat`**, **`run.sh` / `run.bat`** - venv creation, editable install, compile-check, and entry-point execution.
