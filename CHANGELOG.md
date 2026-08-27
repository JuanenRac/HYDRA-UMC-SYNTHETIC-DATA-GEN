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
