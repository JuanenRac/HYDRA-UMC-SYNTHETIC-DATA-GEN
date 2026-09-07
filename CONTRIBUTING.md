# Contributing to HYDRA-UMC-SYNTHETIC-DATA-GEN 🦾

We welcome contributions to the synthetic data factory of the HYDRA-UMC platform.

## Technology Stack
- **Language**: Python 3.12.
- **Engines**: Blender (Cycles/Evee), Bevy (Real-time).
- **Data Formats**: YOLO, COCO, TFRecord, glTF.
- **Libraries**: OpenCV, NumPy, PySide6.

## Guidelines
1. **Annotation Accuracy**: Ensure that all procedurally generated labels (bounding boxes and masks) are pixel-perfect and match the visual mesh boundaries.
2. **Domain Randomization**: When adding new texture or lighting randomizers, ensure they cover a wide enough spectrum to prevent neural network overfitting.
3. **Asset Quality**: Use high-quality PBR (Physically Based Rendering) materials for components to ensure realistic light interaction.
4. **Performance**: Render scripts should be optimized for multi-GPU parallelization where possible.
