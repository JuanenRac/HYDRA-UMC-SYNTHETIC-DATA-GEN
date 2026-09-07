# Security Policy 🔒 (HYDRA-UMC-SYNTHETIC-DATA-GEN)

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.x.x  | ✅ Yes             |

## Reporting a Vulnerability

**CRITICAL: Do not report safety-critical vulnerabilities through public GitHub issues.**

In a data generation pipeline, a security flaw can lead to "backdoored" training datasets or model poisoning. If you discover a vulnerability affecting the **auto-annotation logic**, **randomization seeds**, or **asset injection**:

1. **Email**: Send a detailed report to `electrohobby3d@gmail.com`.
2. **Impact**: Describe if the bug allows generating mislabeled data to degrade vision node accuracy, injecting malicious 3D assets, or leaking proprietary component models.
3. **Response**: Initial acknowledgment within 48 hours.

We follow a coordinated disclosure policy to ensure hardware safety before public release.
