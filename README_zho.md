<p align="center">
  <img src="images/HYDRA_UMC_BANNER.svg" alt="HYDRA-UMC-SYNTHETIC-DATA-GEN banner" width="100%">
</p>

# 🎲 HYDRA-UMC-SYNTHETIC-DATA-GEN

<p align="center"><a href="README.md">🇺🇸 English</a> | <a href="README_spa.md">🇪🇸 Español</a> | <a href="README_fra.md">🇫🇷 Français</a> | <a href="README_ita.md">🇮🇹 Italiano</a> | <a href="README_deu.md">🇩🇪 Deutsch</a> | 🇨🇳 <b>简体中文</b> | <a href="README_jpn.md">🇯🇵 日本語</a></p>

### 📸 面向视觉 AI 节点训练的程序化数据集生成器

<p align="left">
  <img src="https://img.shields.io/badge/Licencia-GPL%203.0-blue.svg" alt="GPL 3.0">
  <img src="https://img.shields.io/badge/Format-YOLO%20%2F%20COCO-FF6F00.svg" alt="Format">
  <img src="https://img.shields.io/badge/Target-Vision%20AI%20Node-green.svg" alt="Target">
</p>

---

## 1. 🛠️ 技术概述

**HYDRA-UMC-SYNTHETIC-DATA-GEN** 是视觉 AI 节点的数据工厂。它利用数字
孪生系统的物理和渲染引擎，程序化地生成数千张带标注的图像，用于训练神经
网络。

它通过创建具有自动像素级精确标注（边界框、分割掩码和关键点）的照片级
真实 3D 场景，解决了新工业组件或罕见缺陷类型的"冷启动"问题。

### 关键特性：
* 🎲 **程序化场景（v0）：** 真实的、确定性的（给定种子）2D 组件位置、大小和颜色的随机化。*（已实现为真实的 2D 占位形状，尚非通过 HYDRA-UMC-TWIN 引擎实现的 3D 姿态/光照/纹理——见下方"构建与运行"）*
* 📸 **多摄像头渲染：** 同时从 8 个以上虚拟摄像头生成视图。*（计划中——需要 HYDRA-UMC-TWIN 的真实渲染引擎）*
* 🏷️ **自动标注（v0）：** 真实的、像素级精确的 YOLO 和 COCO 导出。*（已为 YOLO/COCO 实现；TFRecord 导出计划中）*
* 🛠️ **缺陷注入（v0）：** 每个组件真实的、随机的矩形叠加，概率可配置。*（已实现为简单的真实叠加——真实的划痕/缺失部件/焊桥形状计划中）*
* 📋 **数据集清单与验证（v0）：** 每次 `generate` 运行都会写入一个真实的 `manifest.json`（可复现种子标志、生成参数，以及每张图像真实的 sha256 校验和），并运行真实的生成后验证——场景边界、针对已知真实文件布局的 BMP 完整性、以及标签分布的合理性——若发现任何真实问题，则以非零退出码退出。

---

## 2. 🔄 生成流水线

```mermaid
flowchart LR
    MODELS["3D Component Models"] --> SCENE["Scene Randomizer"]
    SCENE --> RENDER["Physics-Based Renderer"]
    RENDER --> ANN["Auto-Annotation Engine"]
    ANN --> DATASET["Training Dataset (YOLO/COCO)"]
    DATASET --> TRAIN["Vision Node Training"]
```

---

## 3. 🧱 架构与设计决策

* **为何本生成器没有 `hardware/`/`firmware/`/`os/` 文件夹。** 纯软件——它通过 HYDRA-UMC-TWIN 自身的引擎渲染场景，而非自己拥有任何硬件。
* **为何它是 HYDRA-UMC-TWIN 的兄弟项目，而非子模块。** 数据集生成是一项批量的、离线的工作负载（可能需要数小时的渲染时间），与孪生系统自身的实时循环有本质区别——将其保持独立，意味着一次长时间的导出运行永远不会与实时仿真争夺同一进程的 CPU/GPU 时间。
* **为何入口点今天只打印身份/版本/角色。** 处于脚手架（scaffolding）阶段：证明该包能够正确安装并被导入，先于真正的程序化随机化/渲染/标注导出逻辑。
* **这如何融入生态系统的其余部分。** 通过 HYDRA-UMC-TWIN 自身的引擎渲染训练数据集（带自动 YOLO/COCO/TFRecord 标注），供 HYDRA-UMC-VISION-NODE 和 HYDRA-UMC-DETECTION-HEF 用于训练——以合成数据取代手动标注真实摄像头画面。
* **为何 v0 渲染真实的 2D 占位形状，而不是等待 HYDRA-UMC-TWIN。** HYDRA-UMC-TWIN（本项目自身的集成父项目）本身仍处于脚手架阶段——如果将数据集生成完全阻塞在它的真实 3D 引擎上，标注流水线（真正困难、可复用的部分：放置、标注、YOLO/COCO 导出）就得不到测试。一个真实的、仅依赖标准库的 BMP 光栅化器如今就能提供真实的、像素级精确的真值数据；日后替换为 TWIN 的真实引擎，改变的只是像素如何被绘制，而不是 `Scene`/`Component`/导出的契约。
* **为何边界框在构造上就是像素级精确的。** `export.py` 读取的正是 `scene.py` 放置、`render.py` 绘制的同一组 `Component` 坐标——这个 v0 循环中没有任何检测模型，也没有任何人工标注步骤，标注不会有偏差的来源。
* **为何验证复用 `render.py` 自身的行大小公式，而非使用第二个独立的解析器。** `validate_bmp_integrity()` 直接从 `render.py` 导入 `_row_size()`，而不是重新推导 BMP 行填充计算——对确切字节布局采用单一事实来源，可避免未来对写入器的真实改动在无声中与校验器失步。
* **为何“可复现”是清单中的一个字段，而不仅是 `--seed` 隐含的一种属性。** 在此改动之前，`--seed` 已经使生成过程具有确定性，但没有任何记录能说明磁盘上某个数据集是否真的使用了种子——消费者事后无法区分一次可复现的运行和一次随机的运行。`manifest.json` 的 `reproducible` 标志加上每张图像真实的 sha256，使这一断言变得可核实。

---

## 📂 目录结构

纯软件数据集生成器，没有自己的硬件设计——因此本项目不携带 `hardware/`、
`firmware/` 或 `os/` 文件夹，遵循仓库结构策略。

```text
HYDRA-UMC-SYNTHETIC-DATA-GEN/
├── src/hydra_umc_synthetic_data_gen/
│   ├── scene.py          # 真实的程序化 2D 场景/组件生成
│   ├── render.py          # 真实的、仅依赖标准库的 BMP 光栅化
│   ├── export.py           # 真实的 YOLO/COCO 标注导出
│   ├── manifest.py           # 真实的数据集 manifest.json（种子、校验和）
│   ├── validate.py           # 真实的边界/BMP 完整性/分布验证
│   └── main.py               # 入口点 + 真实的 `generate` 子命令
├── tests/               # 真实测试：生成、渲染、导出、端到端 CLI
├── docs/                # 文档与程序化生成指南
├── build/               # 构建输出（本地 .venv 也位于仓库根目录）
├── images/              # 媒体与图表
├── scripts/             # 实用脚本
├── pyproject.toml       # 包元数据、依赖项、里程表版本号
├── bump_version.py      # 里程表式版本递增（由 build.sh/.bat 使用）
├── build.sh / build.bat # venv + 可编辑安装（含 dev 附加依赖）+ 真实测试 + 编译检查
└── run.sh / run.bat     # 从本地 venv 运行入口点（转发参数，例如 `generate`）
```

---

## 🏗️ 构建与运行

需要 Python 3.10+。

```bash
# Linux / macOS
./build.sh   # 里程表式版本递增，创建 .venv，以可编辑模式（含 dev 附加
             # 依赖）安装该包，运行真实测试套件，对整个 src/ 进行编译检查
./run.sh     # 从 .venv 运行入口点，打印名称 + 版本 + 角色
```

```bat
:: Windows
build.bat
run.bat
```

`build.sh`/`build.bat` 会在每次真实构建之前，按照生态系统的"里程表"
规则（PATCH+1，超过 9 时进位到 MINOR）递增本项目自身的
`pyproject.toml` 版本号，运行真实测试套件（`pytest tests/`），然后使用
`python -m compileall` 对源代码进行编译检查。

真实的 `generate` 子命令会将真实数据集写入磁盘：

```bash
./run.sh generate --out dataset/ --count 20 --components 6 --defect-rate 0.3 --seed 42 --format both

# Windows
run.bat generate --out dataset\ --count 20 --components 6 --defect-rate 0.3 --seed 42 --format both
```

根据 `--format`，将真实的 BMP 图像写入 `dataset/images/`，真实的 YOLO
标注写入 `dataset/labels/` + `dataset/classes.txt`，和/或将真实的
`dataset/annotations.json`（COCO 格式）写入磁盘。给定 `--seed` 可使数据
集实现逐字节可复现。

每次运行还会写入一个真实的 `dataset/manifest.json`，并验证自身的输出：

```
Generated 20 scene(s) -> dataset/images
Total labeled components (incl. defects): 132
Annotations exported as: both
Reproducible seed: yes (seed=42)
Manifest written -> dataset/manifest.json
Validation: OK (scene bounds, BMP integrity, label distribution)
```

```json
{
  "seed": 42,
  "reproducible": true,
  "count": 20,
  "scenes": [
    { "image": "scene_0000.bmp", "num_components": 7,
      "label_counts": {"bolt": 3, "gear": 2, "defect": 2},
      "sha256": "7a422d05948fa43f04e738716883841ee1f493449c1023bc8dc711ffe7ffca2c" }
  ],
  "validation_issues": []
}
```

如果验证发现真实问题（超出边界的组件、被截断/损坏的 BMP 文件，或缺陷率
与 `--defect-rate` 出现严重偏离），`generate` 会以退出码 `1` 结束，并
列出每一个问题，而不是悄悄交付一个有缺陷的数据集。

---

## 🚀 路线图
* **第一阶段：** 数字孪生与实时硬件遥测的同步，延迟低于 10ms。
* **第二阶段：** 物理复制品与工业级仿真器（Isaac Sim）的集成，以及可变形体支持。
* **第三阶段：** 用于去中心化故障转移和早期传感器退化检测的节点自愈自动化恢复模式。
* **第四阶段：** 基于 GAN 的纹理优化，用于超逼真工业材质和照片级真实数据集生成。

---

## 🔗 相关项目

本项目是同一作者（JuanenRac / Electro Hobby 3D）打造的更大规模机器人生态
系统的一部分，涵盖固件、控制软件、AI 节点和车队工具。值得了解，因为某个
需求实际上可能是关于这些项目之一，而非本仓库。

### 项目族

**父项目：** **[HYDRA-UMC-TWIN](https://github.com/JuanenRac/HYDRA-UMC-TWIN)** —— 其引擎为本项目渲染数据集的集成父项目。

**同族项目：**
- **[HYDRA-UMC-PHYSICS-REPLICA](https://github.com/JuanenRac/HYDRA-UMC-PHYSICS-REPLICA)** —— 同级仿真服务，同一父项目。
- **[HYDRA-UMC-HIL-BRIDGE](https://github.com/JuanenRac/HYDRA-UMC-HIL-BRIDGE)** —— 同级仿真服务，同一父项目。

### 直接相关（项目族之外）

- **[HYDRA-UMC-VISION-NODE](https://github.com/JuanenRac/HYDRA-UMC-VISION-NODE)** —— 基于本项目生成的数据集进行训练。
- **[HYDRA-UMC-DETECTION-HEF](https://github.com/JuanenRac/HYDRA-UMC-DETECTION-HEF)** —— 基于本项目生成的数据集进行训练。

### 生态系统的其余部分

**HYDRA-UMC 平台** —— 多机器人微工厂单元
- **[HYDRA-UMC](https://github.com/JuanenRac/HYDRA-UMC)** —— 协调最多 8 条机械臂的 CM5 + STM32H745 主板。
- **[HYDRA-UMC-SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER)** —— 每个控制客户端所对接的 Express/WebSocket 后端。
- **[HYDRA-UMC-STUDIO](https://github.com/JuanenRac/HYDRA-UMC-STUDIO)** —— 基于 Web 的控制仪表盘，多机器人 3D 可视化。
- **[HYDRA-UMC-ANDROID-CONTROL](https://github.com/JuanenRac/HYDRA-UMC-ANDROID-CONTROL)** —— 通过 Wi-Fi/蓝牙的 Android 控制应用。
- **[HYDRA-UMC-IOS-CONTROL](https://github.com/JuanenRac/HYDRA-UMC-IOS-CONTROL)** —— 基于 Flutter 构建的 iOS/iPadOS 控制应用。
- **[HYDRA-UMC-SUITE](https://github.com/JuanenRac/HYDRA-UMC-SUITE)** —— 桌面端集群指挥中心（Python/PySide6）。
- **[HYDRA-UMC-EDITOR-URDF](https://github.com/JuanenRac/HYDRA-UMC-EDITOR-URDF)** —— 用于机器人目录的桌面端 URDF 模型编辑器。
- **[HYDRA-UMC-DSI](https://github.com/JuanenRac/HYDRA-UMC-DSI)** —— 机载 DSI 触摸屏的原生触控 UI。

**URTC 平台** —— 每台 HYDRA-UMC 机械臂搭载的工具头控制器
- **[URTC](https://github.com/JuanenRac/URTC)** —— CAN 总线工具头控制器，25 种工具配置。
- **[URTC-FLASHER](https://github.com/JuanenRac/URTC-FLASHER)** —— 桌面端 CAN-OTA + SWD/JTAG 刷写工具。
- **[URTC-TESTER](https://github.com/JuanenRac/URTC-TESTER)** —— 桌面端实时 CAN 总线诊断工具。
- **[URTC-WEB-STUDIO](https://github.com/JuanenRac/URTC-WEB-STUDIO)** —— 通过 Web Serial API 的浏览器端替代方案。

**🎥 视觉 AI 节点（Hailo-8）**
- [HYDRA-UMC-VISION-NODE](https://github.com/JuanenRac/HYDRA-UMC-VISION-NODE)
- [HYDRA-UMC-VISION-STREAMER](https://github.com/JuanenRac/HYDRA-UMC-VISION-STREAMER)
- [HYDRA-UMC-DETECTION-HEF](https://github.com/JuanenRac/HYDRA-UMC-DETECTION-HEF)
- [HYDRA-UMC-SAFETY-ZONES](https://github.com/JuanenRac/HYDRA-UMC-SAFETY-ZONES)
- [HYDRA-UMC-VISUAL-SERVOING-API](https://github.com/JuanenRac/HYDRA-UMC-VISUAL-SERVOING-API)

**🧠 认知 AI 节点（Hailo-10）**
- [HYDRA-UMC-COGNITIVE-NODE](https://github.com/JuanenRac/HYDRA-UMC-COGNITIVE-NODE)
- [HYDRA-UMC-VLA-ENGINE](https://github.com/JuanenRac/HYDRA-UMC-VLA-ENGINE)
- [HYDRA-UMC-VOICE-UI](https://github.com/JuanenRac/HYDRA-UMC-VOICE-UI)
- [HYDRA-UMC-SEMANTIC-PLANNER](https://github.com/JuanenRac/HYDRA-UMC-SEMANTIC-PLANNER)
- [HYDRA-UMC-DOCS-QA](https://github.com/JuanenRac/HYDRA-UMC-DOCS-QA)

**🐝 编排与集群**
- [HYDRA-UMC-ORCHESTRATOR](https://github.com/JuanenRac/HYDRA-UMC-ORCHESTRATOR)
- [HYDRA-UMC-SWARM-SYNC](https://github.com/JuanenRac/HYDRA-UMC-SWARM-SYNC)
- [HYDRA-UMC-PATH-PLANNER-3D](https://github.com/JuanenRac/HYDRA-UMC-PATH-PLANNER-3D)
- [HYDRA-UMC-JOB-DISPATCHER](https://github.com/JuanenRac/HYDRA-UMC-JOB-DISPATCHER)
- [HYDRA-UMC-NODE-HEALING](https://github.com/JuanenRac/HYDRA-UMC-NODE-HEALING)

**📊 数据与分析**
- [HYDRA-UMC-DATALAKE](https://github.com/JuanenRac/HYDRA-UMC-DATALAKE)
- [HYDRA-UMC-TELEMETRY-COLLECTOR](https://github.com/JuanenRac/HYDRA-UMC-TELEMETRY-COLLECTOR)
- [HYDRA-UMC-ANOMALY-DETECTOR](https://github.com/JuanenRac/HYDRA-UMC-ANOMALY-DETECTOR)
- [HYDRA-UMC-PRODUCTION-REPORTS](https://github.com/JuanenRac/HYDRA-UMC-PRODUCTION-REPORTS)

**🏭 工业网关**
- [HYDRA-UMC-GATEWAY-INDUSTRIAL](https://github.com/JuanenRac/HYDRA-UMC-GATEWAY-INDUSTRIAL)
- [HYDRA-UMC-OPCUA-SERVER](https://github.com/JuanenRac/HYDRA-UMC-OPCUA-SERVER)
- [HYDRA-UMC-MQTT-BROKER](https://github.com/JuanenRac/HYDRA-UMC-MQTT-BROKER)
- [HYDRA-UMC-MTCONNECT-ADAPTER](https://github.com/JuanenRac/HYDRA-UMC-MTCONNECT-ADAPTER)

**🛠️ 配套工具**
- [URTC-SMART-RACK](https://github.com/JuanenRac/URTC-SMART-RACK)
- [URTC-VISION-TOOL](https://github.com/JuanenRac/URTC-VISION-TOOL)
- [HYDRA-UMC-WATCH](https://github.com/JuanenRac/HYDRA-UMC-WATCH)
- [HYDRA-UMC-TOOL-CLI](https://github.com/JuanenRac/HYDRA-UMC-TOOL-CLI)
- [HYDRA-UMC-DASHBOARD-AI](https://github.com/JuanenRac/HYDRA-UMC-DASHBOARD-AI)


## 👤 作者
**JuanenRac**（Electro Hobby 3D）
📧 electrohobby3d@gmail.com

## 📜 许可证
GPL-3.0 —— 详见 LICENSE。

## 🛠️ BUILD & RUN

请在发布构建前使用不改动版本的构建检查：

| 操作 | Windows | Linux / macOS |
|---|---|---|
| 构建检查（不修改版本或 CHANGELOG） | `build-test.bat` | `./build-test.sh` |
| 运行 / 开发（如提供） | `run*.bat` 或 `dev*.bat` | `./run*.sh` 或 `./dev*.sh` |

`build-test.bat` 和 `build-test.sh` 会编译或验证项目技术栈，但不会递增 `hydra-umc.project.json`，也不会修改 `CHANGELOG.md`。它们仅可能生成正常的编译器输出。现有的 `build*.bat`、`build*.sh`、`run*` 和 `dev*` 脚本保留各自的版本化或运行时行为；需要该行为时请使用它们。