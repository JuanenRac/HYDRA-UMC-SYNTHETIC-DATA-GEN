# Simulation bench

The dataset factory is the simulator of the camera: it draws a scene from a seed, renders it and writes the labels. The bench runs it through its command line for many seeds and every option and reads the output from the other side, with code that does not share anything with the factory: the labels against the manifest, the splits as a partition, the TFRecord against the labels, the same seed against itself across formats, layouts and processes. Then it damages the dataset the way a copy, a disk or a careless edit does, with a fixed seed, and requires the verify command to see it.

## Run it

```
python -m pytest -q tests/test_simulation_bench.py
```

## What the scenarios check

| Scenario | What it shows |
|----------|---------------|
| labels against the manifest | every scene has as many label lines as components, with the class counts of the manifest and every number inside the image |
| four seeds across five ways of writing the dataset | the images are the same bytes whatever the format, the layout, the split and the number of processes, and every run verifies |
| another seed | other images, and the seed is recorded |
| two hundred random split requests | the parts are a partition of the scenes and their sizes follow the fractions |
| the part of a scene | it depends on the seed and the index only |
| ten split requests that cannot work | refused before anything is written |
| the TFRecord | it holds the same boxes, class names and image bytes as the labels and the manifest |
| a TFRecord cut short or with a flipped byte | refused by the reader |
| twelve random damages to a dataset (a flipped bit, a cut image, a missing file, an empty label, a stray file, a broken or wrong manifest) | verify sees every one |
| values that cannot work (count, size, components, defect rate, jobs) | refused with no half-written dataset |

The workflow named "Simulation bench" runs the bench on every change, so the simulated path has its own visible job.

## What it cannot show

How a model trained on these images behaves on a real camera, with real light, real parts and real defects, needs the camera. The status of the repository therefore stays at "simulated" for the hardware row until a person has run the service on the bench.
