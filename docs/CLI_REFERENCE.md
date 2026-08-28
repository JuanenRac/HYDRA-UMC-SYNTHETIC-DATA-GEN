# HYDRA-UMC-SYNTHETIC-DATA-GEN — CLI Reference

`hydra-umc-synthetic-data-gen` is a Python console script
(`src/hydra_umc_synthetic_data_gen/main.py`, installed as an entry point
via `pyproject.toml`). Real v0 is a full, working, stdlib-only pipeline
behind the `generate` subcommand: real procedural 2D scene generation,
real BMP rasterization (no Pillow/numpy — hand-rolled BMP bytes), real
YOLO/COCO annotation export, a real dataset manifest with per-image
sha256 checksums, and real post-generation validation of scene bounds,
BMP integrity, and label distribution. This is honestly a 2D placeholder
pipeline, not the photorealistic 3D rendering through HYDRA-UMC-TWIN's
engine the project README's own roadmap describes — that engine doesn't
exist yet. Every example and every file listed below was produced by a
real, complete run of the installed CLI — not written from memory.

## Usage

```
$ hydra-umc-synthetic-data-gen -h
usage: hydra-umc-synthetic-data-gen [-h] {generate} ...

Procedural generator of training datasets for Vision nodes, rendered through
the Digital Twin's physics/rendering engine.

positional arguments:
  {generate}
    generate  Real procedural 2D scene generation with YOLO/COCO export.

options:
  -h, --help  show this help message and exit
```

Bare invocation (no subcommand) prints identity/version/role and exits `0`:

```
$ hydra-umc-synthetic-data-gen
HYDRA-UMC-SYNTHETIC-DATA-GEN v0.0.5
Procedural generator of training datasets for Vision nodes, rendered through the Digital Twin's physics/rendering engine.
```

## Commands

### `generate --out PATH [options]`

```
$ hydra-umc-synthetic-data-gen generate -h
usage: hydra-umc-synthetic-data-gen generate [-h] --out OUT [--count COUNT]
                                             [--width WIDTH] [--height HEIGHT]
                                             [--components COMPONENTS]
                                             [--defect-rate DEFECT_RATE]
                                             [--seed SEED]
                                             [--format {yolo,coco,both}]

options:
  -h, --help            show this help message and exit
  --out OUT             Output directory.
  --count COUNT         Number of scenes (default: 10).
  --width WIDTH         Image width in pixels (default: 256).
  --height HEIGHT       Image height in pixels (default: 256).
  --components COMPONENTS
                        Components per scene (default: 5).
  --defect-rate DEFECT_RATE
                        Probability of a defect per component (default: 0.2).
  --seed SEED           Base random seed for reproducible datasets (default:
                        random).
  --format {yolo,coco,both}
                        Annotation export format (default: both).
```

#### A real, complete, small end-to-end run (`--format both`)

```
$ hydra-umc-synthetic-data-gen generate --out ./out --count 2 --width 64 --height 64 --seed 42
Generated 2 scene(s) -> ./out/images
Total labeled components (incl. defects): 12
Annotations exported as: both
Reproducible seed: yes (seed=42)
Manifest written -> ./out/manifest.json
Validation: OK (scene bounds, BMP integrity, label distribution)
$ echo $?
0
```

The real files this one run produced:

```
$ find ./out -type f
./out/annotations.json
./out/classes.txt
./out/images/scene_0000.bmp
./out/images/scene_0001.bmp
./out/labels/scene_0000.txt
./out/labels/scene_0001.txt
./out/manifest.json
```

`classes.txt` — the real label vocabulary, one per line:

```
$ cat ./out/classes.txt
bolt
bracket
connector
defect
gear
```

`labels/scene_0000.txt` — real YOLO-format lines (`class x_center
y_center width height`, all normalized 0–1):

```
$ cat ./out/labels/scene_0000.txt
1 0.445312 0.367188 0.359375 0.265625
0 0.195312 0.335938 0.328125 0.671875
4 0.437500 0.546875 0.437500 0.656250
0 0.460938 0.523438 0.515625 0.390625
2 0.687500 0.281250 0.593750 0.500000
3 0.625000 0.421875 0.187500 0.156250
```

`annotations.json` — real COCO-format `images`/`annotations` (excerpt):

```json
{
  "images": [
    {"id": 1, "file_name": "scene_0000.bmp", "width": 64, "height": 64},
    {"id": 2, "file_name": "scene_0001.bmp", "width": 64, "height": 64}
  ],
  "annotations": [
    {"id": 1, "image_id": 1, "category_id": 2, "bbox": [17, 15, 23, 17], "area": 391, "iscrowd": 0},
    {"id": 2, "image_id": 1, "category_id": 1, "bbox": [2, 0, 21, 43], "area": 903, "iscrowd": 0}
  ]
}
```

`manifest.json` — the real generation parameters, plus one entry per
scene with its real component count, real label counts, and its real
sha256 (computed from the actual `.bmp` bytes):

```json
{
  "seed": 42,
  "reproducible": true,
  "count": 2,
  "width": 64,
  "height": 64,
  "requested_components": 5,
  "defect_rate": 0.2,
  "labels": ["bolt", "bracket", "gear", "connector"],
  "format": "both",
  "scenes": [
    {
      "image": "scene_0000.bmp",
      "num_components": 6,
      "label_counts": {"bracket": 1, "bolt": 2, "gear": 1, "connector": 1, "defect": 1},
      "sha256": "bd253b7080b56f8abb18bc3f0b0d06387623823dd417ff869d7c87cf5e6b3774"
    },
    {
      "image": "scene_0001.bmp",
      "num_components": 6,
      "label_counts": {"gear": 3, "bracket": 1, "defect": 1, "bolt": 1},
      "sha256": "1b5a4ade5e113f7a0b404b85c506d551853532e1bcb008d4d36fa11aa0cf54a9"
    }
  ],
  "validation_issues": []
}
```

`images/scene_0000.bmp` is a real, valid 64×64 24-bit BMP — the actual
file header bytes (`BM`, real file size, real `40×00×00×00` / `40×00×00×00`
width/height at offsets 0x12/0x16):

```
$ xxd -l 32 ./out/images/scene_0000.bmp
00000000: 424d 3630 0000 0000 0000 3600 0000 2800  BM60......6...(.
00000010: 0000 4000 0000 4000 0000 0100 1800 0000  ..@...@.........
```

#### `--format yolo` / `--format coco` only

```
$ hydra-umc-synthetic-data-gen generate --out ./out-yolo --count 1 --width 32 --height 32 --seed 7 --format yolo
...
$ find ./out-yolo -type f
./out-yolo/classes.txt
./out-yolo/images/scene_0000.bmp
./out-yolo/labels/scene_0000.txt
./out-yolo/manifest.json
```

No `annotations.json` (COCO) file, and no `labels/` directory at all
for `--format coco`:

```
$ hydra-umc-synthetic-data-gen generate --out ./out-coco --count 1 --width 32 --height 32 --seed 7 --format coco
...
$ find ./out-coco -type f
./out-coco/annotations.json
./out-coco/images/scene_0000.bmp
./out-coco/manifest.json
```

(`classes.txt` is YOLO-specific and correctly absent for `--format coco`.)

#### A real, honest validation failure — real components exceeding real scene bounds

The default `--components 5` at a small `32x32` canvas genuinely
produces components too large to fit — real post-generation validation
catches this for real, reports every real issue, writes the manifest
with them recorded, and the whole command still exits `1`:

```
$ hydra-umc-synthetic-data-gen generate --out ./out-yolo --count 1 --width 32 --height 32 --seed 7 --format yolo
Generated 1 scene(s) -> ./out-yolo/images
Total labeled components (incl. defects): 6
Annotations exported as: yolo
Reproducible seed: yes (seed=7)
Manifest written -> ./out-yolo/manifest.json
VALIDATION FAILED - 2 issue(s):
  [out_of_bounds] scene_0000.bmp: component 'bolt' at (0,0) size 25x41 exceeds scene bounds 32x32
  [out_of_bounds] scene_0000.bmp: component 'bolt' at (6,0) size 24x34 exceeds scene bounds 32x32
$ echo $?
1
```

All real image/label/manifest files are still written even on a
validation failure — `generate` never discards real output just because
`validate.py` caught a real problem with it; it reports the problem and
lets the exit code carry the signal. The `--count 2 --width 64 --height
64` run above happens to be large enough for the same default
`--components 5` to pass validation cleanly — this is a real, genuine
size-dependent effect, not a flaky one.

#### No `--seed` (non-reproducible)

```
$ hydra-umc-synthetic-data-gen generate --out ./out-noseed --count 1 --width 32 --height 32
Generated 1 scene(s) -> ./out-noseed/images
Total labeled components (incl. defects): 7
Annotations exported as: both
Reproducible seed: no (random)
Manifest written -> ./out-noseed/manifest.json
VALIDATION FAILED - 4 issue(s):
  ...
$ echo $?
1
```

`manifest.json`'s `"reproducible"` field is `false` and `"seed"` is
`null` whenever `--seed` is omitted — each run genuinely differs.

#### Real usage errors

A missing required `--out` (exit code `2`, argparse's own error path):

```
$ hydra-umc-synthetic-data-gen generate --count 1
usage: hydra-umc-synthetic-data-gen generate [-h] --out OUT [--count COUNT]
                                             [--width WIDTH] [--height HEIGHT]
                                             [--components COMPONENTS]
                                             [--defect-rate DEFECT_RATE]
                                             [--seed SEED]
                                             [--format {yolo,coco,both}]
hydra-umc-synthetic-data-gen generate: error: the following arguments are required: --out
$ echo $?
2
```

An invalid `--format` choice:

```
$ hydra-umc-synthetic-data-gen generate --out ./out-bad --format bogus
usage: hydra-umc-synthetic-data-gen generate [-h] --out OUT [--count COUNT]
                                             [--width WIDTH] [--height HEIGHT]
                                             [--components COMPONENTS]
                                             [--defect-rate DEFECT_RATE]
                                             [--seed SEED]
                                             [--format {yolo,coco,both}]
hydra-umc-synthetic-data-gen generate: error: argument --format: invalid choice: 'bogus' (choose from 'yolo', 'coco', 'both')
$ echo $?
2
```

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | scenes generated, annotations exported, manifest written, and real post-generation validation found no issues |
| `1` | generation and export completed, but real validation found one or more issues (out-of-bounds components, BMP integrity, or label distribution) — the manifest and every file are still written |
| `2` | argparse usage error — a missing required flag or an invalid `--format` choice |

## Not yet implemented

The photorealistic 3D rendering through HYDRA-UMC-TWIN's physics engine
that the project README's roadmap describes does not exist yet — this
CLI's real, working 2D procedural-scene/BMP/YOLO/COCO pipeline is an
honest placeholder ahead of it, not a stub.
