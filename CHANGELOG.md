# Changelog

All notable changes to this project are documented here.

## [Unreleased]

- **PNG images (`generate --image-format png`).** The scenes can be written as 8-bit RGB PNG files (compressed, stdlib only) instead of BMP; the pixels are the ones the BMP holds, the validation checks the signature, the chunk checksums, the size and the pixel stream of each file, and `verify` reads such a dataset back like any other. The default stays BMP, so existing datasets and commands are unchanged.

- **`generate --split train=0.8,val=0.1,test=0.1`:** also writes `train.txt`, `val.txt` and `test.txt` (image paths relative to the dataset), a `data.yaml` for YOLO trainers (class names in the fixed order) and `splits.json`. The assignment depends only on the seed and the scene index, each scene is in exactly one part, and `verify` checks it. `images/` and `labels/` stay flat. Without `--split` nothing changes.

- **README in the universal layout:** the README and its seven translations follow the layout that the four families share (22 sections in a fixed order), with an architecture picture and a repository-structure picture drawn from `docs/architecture.json` and `docs/structure.json`; the CI validator checks both pictures and the file tree.

- **The layout of the README is checked in the CI:** the validator runs `tools/universal_readme_check.py` and lists, as a warning, what differs from the universal layout of the README.
- The README in the eight languages gives the real order of the build scripts (compile-check, then the test suite) and, in Portuguese, no longer says that the build raises the version.

## [0.1.1] - `verify --out DIR`, and `generate` runs it on its own output and the manifest records the class list and its hash

- **`verify --out DIR`, and `generate` runs it on its own output**: the folder is read back and checked against its manifest and against itself: every image against the sha256 of the manifest, the YOLO labels (five fields, a class id that exists, every value inside [0, 1], the box inside the image, as many lines as components), the COCO file (unique image, annotation and category ids, no dangling references, boxes inside the image, `area = width x height`, as many annotations as components), the labels per class, `classes.txt` against the class list of the manifest, and files that belong to no scene. A manifest from an older version is checked as far as it allows.
- **The manifest records the class list and its hash** (`classes`, `classes_sha256`, the sha256 of the text of `classes.txt`) so a model registered in DETECTION-HEF can be checked against the order it was trained with. The check on the DETECTION-HEF side is not written yet.
- **`--jobs N` (default 1, at most 32)** renders scenes in N processes; every scene has its own random generator seeded from the seed and its index, so the manifest, the labels and the images are the same whatever N is (tested).
- **The BMP renderer paints by slice** on flat rows of bytes instead of a list of lists of tuples with a loop per pixel (the old shape cost about 8 bytes of pointer per pixel): the bytes written are identical, checked against the old renderer on random scenes.
- The labels, `classes.txt`, the COCO file and the manifest are written with `\n` line ends on every platform, so a dataset made on Windows has the same bytes (and the same `classes_sha256`) as one made on Linux.
- 24 new tests (82 in all).
- Building no longer changes the version; raising it is the explicit `bump` command (`python tools/hydra_project_tool.py bump`). The build scripts only report the version they built, and CI fails if a build script runs a bump.
- The banner follows the animated style of the ecosystem banners, with the name, the kind and the technologies of the project.
- **The licence declared in the package metadata is GPL-3.0-or-later,** like the headers of the code and the rest of the ecosystem (it said GPL-3.0-only).
- Added `tools/hydra_project_tool.py`: the same `validate`, `test`, `version`, `status` and `bump` commands in every repository. The checks run with `HYDRA_UMC_CI=1` and fail if the version changes; only `bump` changes it.

## [0.1.0] - Stable class ids, labels that follow what is visible, no leakage between seeds

- **Class ids are stable:** the YOLO class index and the COCO category id came from the labels present in that particular dataset, sorted alphabetically, so a run without a "defect" (or with a missing class) shifted every id. They now follow a fixed order (`bolt`, `bracket`, `gear`, `connector`, `defect`), written to `classes.txt` and to the manifest, whatever the run contains.
- **Labels follow what is visible:** a component that later components cover (almost) completely is no longer labelled, and a scratch is boxed by the pixels it really paints (thickness included) instead of the whole area it was drawn in; a scratch shorter than four points becomes a rectangular defect.
- **No data leaking between splits:** the seed of each scene was `seed + index`, so `--seed 0` and `--seed 50` shared fifty scenes. It is now a hash of the seed and the index.
- **Old files never mix with new ones:** `generate` refuses an `--out` folder that already holds a dataset.
- **Always reproducible:** without `--seed` one is drawn and written to the manifest.
- **A useful distribution check:** the defect-rate tolerance is three binomial standard deviations (plus a little slack) instead of a flat 0.25, which let "never any defect" pass.
- **Docs and metadata:** the package description and the identity message no longer say the Digital Twin renders the images, the deployment target is a PC, `build/` and `dist/` are ignored, and the README (all languages) documents classes, labels, seeds and splits (58 tests).

## [0.0.9] - Dataset size limit, Portuguese README

- **A single command could fill the disk:** `generate` range-checked each argument (`--count` up to 10,000, `--width`/`--height` up to 4096) but not their product, and every scene is an uncompressed 24-bit BMP, so `--count 10000 --width 4096 --height 4096` would have written about 500 GB of images before anything complained - enough to fill the SD card of a CM5 from a typo. The estimated size of the images of the whole dataset is now checked before anything is written and a command over 4 GiB is refused with exit code 2 and a message naming the size and the three arguments to lower.
- **Tests:** a new test checks that the oversized command is refused with nothing created and another that a reasonable large dataset (two 1024x1024 scenes) is still generated (49 tests). The reproducibility of a seeded run and the rejection of out-of-range values were also confirmed against the real command.
- **Docs:** the README documents the argument ranges and the size limit and the test count is corrected (it said 47 in some languages and 42 in others), and a README in Portuguese (`README_por.md`) joins the other translations.

## [0.0.8] - A real Bresenham-line scratch, alongside the original rectangular defect overlay

- **`scene.py`**: `generate_scratch()` draws a real scratch defect via
  Bresenham's line algorithm between two randomized endpoints within a
  defect's bounding box, with independently randomized per-point
  half-width and opacity so it reads as an irregular surface scratch
  rather than a uniform stroke. `generate_scene()` now picks between
  this and the original solid rectangle 50/50 (same seeded `rng`, fully
  deterministic). The bounding box `Component` already carried for
  annotation purposes is unchanged either way - `export.py`'s YOLO/COCO
  writers needed no changes.
- **`render.py`**: a scratch-kind `Component` blends its line pixels
  into whatever is already painted beneath them (the parent component's
  own fill) instead of a flat rectangle overwrite.
- 5 new tests: Bresenham correctness (8-connected path, real start/end
  endpoints across several slopes/directions), scratch determinism,
  scratch points staying within their own bounding box, and a real
  pixel-level proof the render path actually blends scratch pixels
  against the background. 47/47 passing (was 42).

## [0.0.7]

- **Fixed a real bug found on code review: a small scene
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
- **`validate.py`** - real post-generation validation, run automatically at the end of every `generate` call: (1) scene-bounds checking, catching any component whose rectangle doesn't fully fit inside its own scene; (2) BMP-integrity checking, which recomputes the exact expected file size from `render.py`'s own row-padding layout and flags a truncated/corrupt image file (verified against a real truncated file, not just a synthetic byte string); (3) label-distribution sanity, flagging an observed defect rate that deviates from the configured `--defect-rate` by more than a tolerance once there are enough samples to mean something (guarded by a minimum sample size so small `--count` runs never flake). `generate` now exits 1 and prints every issue if validation fails, 0 otherwise - closes the "distribution/corrupt-output validation" requirement with real, tested checks rather than a TODO.
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
- **`bump_version.py`** - ecosystem-standard version bump script.
- **`build.sh` / `build.bat`**, **`run.sh` / `run.bat`** - venv creation, editable install, compile-check, and entry-point execution.

## Earlier history

### CI - real pytest suite now actually runs

- **`.github/workflows/ci.yml`** - the real `tests/` pytest suite is now
  actually installed and run in CI. The baseline workflow's Python
  handling previously only compile-checked (`py_compile`) every `.py`
  file and validated the manifest/docs - it never ran `pytest`, so a
  regression in `tests/` could be merged without CI ever failing.
  CI-only fix, no runtime code changed, no version bump.
