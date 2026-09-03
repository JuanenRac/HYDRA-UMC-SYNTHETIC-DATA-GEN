<p align="center">
  <img src="images/HYDRA_UMC_BANNER.svg" alt="HYDRA-UMC-SYNTHETIC-DATA-GEN banner" width="100%">
</p>

# 🎲 HYDRA-UMC-SYNTHETIC-DATA-GEN

<p align="center"><a href="README.md">🇺🇸 English</a> | <a href="README_spa.md">🇪🇸 Español</a> | <a href="README_fra.md">🇫🇷 Français</a> | <a href="README_ita.md">🇮🇹 Italiano</a> | <a href="README_deu.md">🇩🇪 Deutsch</a> | <a href="README_zho.md">🇨🇳 简体中文</a> | 🇯🇵 <b>日本語</b></p>

### 📸 ビジョン AI ノードの学習向けプロシージャルデータセットジェネレーター

<p align="left">
  <img src="https://img.shields.io/badge/Licencia-GPL%203.0-blue.svg" alt="GPL 3.0">
  <img src="https://img.shields.io/badge/Format-YOLO%20%2F%20COCO-FF6F00.svg" alt="Format">
  <img src="https://img.shields.io/badge/Target-Vision%20AI%20Node-green.svg" alt="Target">
</p>

---

## 1. 🛠️ 技術概要

**HYDRA-UMC-SYNTHETIC-DATA-GEN** は、ビジョン AI ノードのためのデータ
工場です。デジタルツインの物理エンジンとレンダリングエンジンを活用し、
ニューラルネットワークの学習用にラベル付けされた画像を数千枚単位で
プロシージャルに生成します。

自動的にピクセル単位で正確な注釈（バウンディングボックス、セグメン
テーションマスク、キーポイント）が付与されたフォトリアリスティックな
3D シナリオを作成することで、新しい工業部品や稀な欠陥タイプにおける
「コールドスタート」問題を解決します。

### 主な機能：
* 🎲 **プロシージャルシナリオ（v0）：** シード指定による実際の決定論的な、2D コンポーネントの位置・サイズ・色のランダム化。*（実際の 2D プレースホルダー形状として実装済み——HYDRA-UMC-TWIN のエンジンを通じた 3D の姿勢/照明/テクスチャはまだです。下記の「ビルドと実行」を参照）*
* 📸 **マルチカメラレンダリング：** 8 台以上の仮想カメラから同時にビューを生成します。*（計画中——HYDRA-UMC-TWIN の実際のレンダリングエンジンが必要です）*
* 🏷️ **自動ラベリング（v0）：** YOLO と COCO への実際のピクセル単位で正確なエクスポート。*（YOLO/COCO について実装済み。TFRecord エクスポートは計画中）*
* 🛠️ **欠陥注入（v0）：** コンポーネントごとの実際のランダムな矩形オーバーレイ、確率は設定可能。*（シンプルな実際のオーバーレイとして実装済み——実際の傷/部品欠落/はんだブリッジ形状は計画中）*
* 📋 **データセットマニフェストと検証（v0）：** `generate` を実行するたびに、実際の `manifest.json`（再現可能シードのフラグ、生成パラメータ、各画像の実際の sha256 チェックサム）が書き込まれ、実際の生成後検証——シーン境界、既知の実際のファイルレイアウトに対する BMP の整合性、ラベル分布の妥当性——が実行されます。実際の問題が見つかった場合はゼロ以外の終了コードで終了します。

---

## 2. 🔄 生成パイプライン

```mermaid
flowchart LR
    MODELS["3D Component Models"] --> SCENE["Scene Randomizer"]
    SCENE --> RENDER["Physics-Based Renderer"]
    RENDER --> ANN["Auto-Annotation Engine"]
    ANN --> DATASET["Training Dataset (YOLO/COCO)"]
    DATASET --> TRAIN["Vision Node Training"]
```

---

## 3. 🧱 アーキテクチャと設計上の決定

* **本ジェネレーターに `hardware/`/`firmware/`/`os/` フォルダがない理由。** 純粋なソフトウェアです——HYDRA-UMC-TWIN 自身のエンジンを通じてシーンをレンダリングするだけで、自らハードウェアを所有していません。
* **HYDRA-UMC-TWIN のサブモジュールではなく兄弟プロジェクトである理由。** データセット生成はバッチ処理のオフラインワークロード（レンダリングに数時間かかることもあります）であり、ツイン自身のリアルタイムループとは根本的に異なります——これを独立させておくことで、長時間のエクスポート処理が同一プロセスの CPU/GPU 時間をリアルタイムシミュレーションと奪い合うことは決してありません。
* **エントリポイントが今日は身元/バージョン/役割のみを表示する理由。** 足場（アンダミアヘ、スキャフォールディング）段階にあります：本パッケージが正しくインストールされ、問題なくインポートできることを証明することが、実際のプロシージャルなランダム化/レンダリング/アノテーションエクスポートロジックに先立ちます。
* **エコシステムの他の部分との関係。** HYDRA-UMC-TWIN 自身のエンジンを通じて、（自動 YOLO/COCO/TFRecord アノテーション付きの）学習データセットをレンダリングし、HYDRA-UMC-VISION-NODE と HYDRA-UMC-DETECTION-HEF がそれを用いて学習できるようにします——実際のカメラ映像を手作業でラベリングする代わりに、合成データを使用します。
* **v0 が HYDRA-UMC-TWIN を待たずに実際の 2D プレースホルダー形状をレンダリングする理由。** HYDRA-UMC-TWIN（本プロジェクト自身の統合親プロジェクト）自体がまだ足場段階にあります——データセット生成を実際の 3D エンジンに完全に依存させると、アノテーションパイプライン（配置、ラベリング、YOLO/COCO エクスポートという、実際に難しく再利用可能な部分）が未テストのまま残ってしまいます。標準ライブラリのみに依存する実際の BMP ラスタライザーは、今日すでに実際のピクセル単位で正確な正解データを提供します——後で TWIN の実際のエンジンに置き換えても、変わるのはピクセルの描画方法だけで、`Scene`/`Component`/エクスポートの契約は変わりません。
* **バウンディングボックスが構造的にピクセル単位で正確である理由。** `export.py` は `scene.py` が配置し `render.py` が描画したのとまったく同じ `Component` の座標を読み取ります——この v0 のループには検出モデルも手動ラベリングの手順も存在しないため、アノテーションがそこからずれる余地がありません。
* **検証が独立した第二のパーサーではなく `render.py` 自身の行サイズ計算式を再利用する理由。** `validate_bmp_integrity()` は BMP の行パディング計算を再度導出するのではなく、`render.py` から `_row_size()` を直接インポートします——正確なバイトレイアウトについて単一の真実の情報源を持つことで、将来ライター側に加えられる実際の変更がチェッカーと気づかぬうちに食い違ってしまうことを防ぎます。
* **「再現可能」が `--seed` の暗黙のプロパティではなく、マニフェストのフィールドである理由。** この変更以前から `--seed` は生成を決定論的にしていましたが、ディスク上の特定のデータセットが実際にシードを使用したかどうかを記録するものは何もありませんでした——利用者は後から再現可能な実行とランダムな実行を区別する手段を持っていませんでした。`manifest.json` の `reproducible` フラグと各画像の実際の sha256 により、この主張が検証可能になります。

---

## 📂 リポジトリ構成

純粋なソフトウェアのデータセットジェネレーターであり、独自のハード
ウェア設計を持たないため、本プロジェクトは `hardware/`、`firmware/`、
`os/` フォルダを携えておらず、リポジトリ構造ポリシーに従っています。

```text
HYDRA-UMC-SYNTHETIC-DATA-GEN/
├── src/hydra_umc_synthetic_data_gen/
│   ├── __init__.py            # パッケージバージョン
│   ├── scene.py          # 実際のプロシージャルな 2D シーン/コンポーネント生成
│   ├── render.py          # 実際の、標準ライブラリのみによる BMP ラスタライズ
│   ├── export.py           # 実際の YOLO/COCO アノテーションエクスポート
│   ├── manifest.py           # 実際のデータセット manifest.json（シード、チェックサム）
│   ├── validate.py           # 実際の境界/BMP 整合性/分布の検証
│   └── main.py               # エントリポイント + 実際の `generate` サブコマンド
├── tests/               # 実際のテスト：生成、レンダリング、エクスポート、エンドツーエンド CLI
├── docs/                # ドキュメントとプロシージャル生成ガイド
├── build/               # ビルド出力（ローカルの .venv もリポジトリルートに存在）
├── images/              # メディアと図表
├── tools/               # ci_validate.py —— CI が使用する manifest/CHANGELOG/docs の検証
├── pyproject.toml       # パッケージメタデータ、依存関係、オドメーターバージョン
├── bump_version.py      # オドメーター式バージョンインクリメント（build.sh/.bat が使用）
├── bump_manifest_version.py # hydra-umc.project.json のバージョンをネイティブ側と同期（--sync）
├── build.sh / build.bat # venv + editable インストール（dev エクストラ付き）+ 実際のテスト + コンパイルチェック
└── run.sh / run.bat     # ローカル venv からエントリポイントを実行（引数を転送、例：`generate`）
```

---

## 🏗️ ビルドと実行

Python 3.10+ が必要です。

```bash
# Linux / macOS
./build.sh   # オドメーター式バージョンインクリメント、.venv を作成し、
             # パッケージを editable モード（dev エクストラ付き）で
             # インストールし、実際のテストスイートを実行し、
             # src/ 全体をコンパイルチェックします
./run.sh     # .venv からエントリポイントを実行し、名前 + バージョン + 役割を表示します
```

```bat
:: Windows
build.bat
run.bat
```

`build.sh`/`build.bat` は、実際の各ビルドの前に、エコシステムの
「オドメーター」規則（PATCH+1、9 を超えると MINOR に繰り上がる）に
従って本プロジェクト自身の `pyproject.toml` のバージョンを増加させ、
実際のテストスイートを実行し（`pytest tests/`）、その後
`python -m compileall` でソースをコンパイルチェックします。

実際の `generate` サブコマンドは、実際のデータセットをディスクに
書き込みます：

```bash
./run.sh generate --out dataset/ --count 20 --components 6 --defect-rate 0.3 --seed 42 --format both

# Windows
run.bat generate --out dataset\ --count 20 --components 6 --defect-rate 0.3 --seed 42 --format both
```

`--format` に応じて、実際の BMP 画像を `dataset/images/` に、実際の
YOLO ラベルを `dataset/labels/` + `dataset/classes.txt` に、および/または
実際の `dataset/annotations.json`（COCO 形式）を書き込みます。特定の
`--seed` を指定すると、データセットはバイト単位で再現可能になります。

各実行は実際の `dataset/manifest.json` も書き込み、自身の出力を検証します：

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

検証で実際の問題（境界を超えたコンポーネント、切り詰められた/破損した BMP
ファイル、`--defect-rate` から大きく外れた欠陥率）が見つかった場合、
`generate` は終了コード `1` で終了し、欠陥のあるデータセットを黙って
出荷する代わりに、すべての問題を一覧表示します。

---

## 🚀 ロードマップ
* **フェーズ 1：** リアルタイムハードウェアテレメトリとのデジタルツイン同期、サブ 10ms の遅延。
* **フェーズ 2：** 産業グレードのシミュレーター（Isaac Sim）との Physics Replica 統合、変形体サポート。
* **フェーズ 3：** 分散型フェイルオーバーと早期センサー劣化検知のためのノード自己修復自動化パターン。
* **フェーズ 4：** 超リアルな産業用素材のための GAN ベースのテクスチャリファインメントとフォトリアリスティックなデータセット生成。

---

## 🔗 関連プロジェクト

本プロジェクトは、同じ作者(JuanenRac / Electro Hobby 3D)による HYDRA-UMC ロボティクスエコシステムの一部です。リクエストが実はこの中のどれかについてのものである可能性があるため、知っておく価値があります。

**親プロジェクト**
- **[HYDRA-UMC-TWIN](https://github.com/JuanenRac/HYDRA-UMC-TWIN)** — デジタルツインエンジンの統合ハブ、実際のバージョン互換性同期契約付き。本リポジトリは、その自身のデジタルツインエンジン内における特定のシミュレーションサービスとして、この親の一部を成す。

**兄弟プロジェクト** —— HYDRA-UMC-TWIN 自身のデジタルツインエンジンにおける他のシミュレーションサービス
- **[HYDRA-UMC-PHYSICS-REPLICA](https://github.com/JuanenRac/HYDRA-UMC-PHYSICS-REPLICA)** — 実際の URDF サブセットに対する、実際の順運動学と関節限界検証。
- **[HYDRA-UMC-HIL-BRIDGE](https://github.com/JuanenRac/HYDRA-UMC-HIL-BRIDGE)** — シミュレーションと実際のハードウェアの間でコマンドをルーティングする、実際のハードウェア・イン・ザ・ループ安全インターロック。

**直接関連**
- **[HYDRA-UMC-VISION-NODE](https://github.com/JuanenRac/HYDRA-UMC-VISION-NODE)** — Hailo-8 ビジョンパイプラインの統合ハブ、段階ごとの実際のハードウェア準備状況チェック付き ——本プロジェクトが生成するデータセットで学習される。
- **[HYDRA-UMC-DETECTION-HEF](https://github.com/JuanenRac/HYDRA-UMC-DETECTION-HEF)** — Hailo アーキテクチャ/チェックサムによる安全読み込み検証を備えた、実際のコンパイル済みモデルレジストリ ——本プロジェクトが生成するデータセットで学習される。

**エコシステムの他のプロジェクト**

*コアハードウェア&プラットフォーム*
- **[HYDRA-UMC](https://github.com/JuanenRac/HYDRA-UMC)** — 実際のロボットアームのマザーボード——CM5 ホスト + デュアルコア STM32H745、CAN-OTA/SPI-OTA 経由で最大 8 本のツールアームを統括。
- **[HYDRA-UMC-OS](https://github.com/JuanenRac/HYDRA-UMC-OS)** — CM5 向けの再現可能な Raspberry Pi OS プロダクト層——読み取り専用エージェント、検証済み設定/プロファイル、WiFi 初回接続プロビジョニング。
- **[HYDRA-UMC-SDK](https://github.com/JuanenRac/HYDRA-UMC-SDK)** — すべてのブリッジが自身のコマンドを検証する共有 JSON-Schema 契約と安全ゲートの境界。

*コアバックエンド&クライアント*
- **[HYDRA-UMC-SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER)** — すべての制御クライアントが実際に通信する、本物のヘッドレスバックエンド(REST/WebSocket)。
- **[HYDRA-UMC-STUDIO](https://github.com/JuanenRac/HYDRA-UMC-STUDIO)** — リアルタイムのマルチロボット 3D 可視化を備えたウェブ制御ダッシュボード。
- **[HYDRA-UMC-SUITE](https://github.com/JuanenRac/HYDRA-UMC-SUITE)** — 複数のサーバーを同時に扱えるデスクトップ(PySide6)スウォームコマンドセンター、スタンドアロン実行ファイルとしてパッケージ化。
- **[HYDRA-UMC-ANDROID-CONTROL](https://github.com/JuanenRac/HYDRA-UMC-ANDROID-CONTROL)** — 生体認証ログインとペアリングされた Wear OS コンパニオンを備えたネイティブ Android 制御アプリ。
- **[HYDRA-UMC-IOS-CONTROL](https://github.com/JuanenRac/HYDRA-UMC-IOS-CONTROL)** — リアルタイム WebSocket 同期を備えた iOS/iPadOS 制御アプリ(Flutter)。
- **[HYDRA-UMC-DSI](https://github.com/JuanenRac/HYDRA-UMC-DSI)** — 本体搭載の 7 インチ DSI タッチスクリーン向けネイティブタッチ UI、CM5 自体に組み込み。
- **[HYDRA-UMC-EDITOR-URDF](https://github.com/JuanenRac/HYDRA-UMC-EDITOR-URDF)** — 完成したモデルを STUDIO 自身のカタログへ送信するデスクトップ用グラフィカル URDF 作成/編集ツール。
- **[HYDRA-UMC-BRIDGE-AMR](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-AMR)** — 実際の VDA 5050 MQTT パブリッシャーによる AGV/AMR フリートの調整境界。
- **[HYDRA-UMC-BRIDGE-CNC](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-CNC)** — 実際の GRBL ステータス/制御バイトへのアクセスを持つ、CNC セルの高レベルコーディネーター。
- **[HYDRA-UMC-BRIDGE-DROIDS](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-DROIDS)** — 実際の Boston Dynamics Spot コマンド送信機能を持つ、脚型/ヒューマノイドドロイドの調整境界。
- **[HYDRA-UMC-BRIDGE-LASER](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-LASER)** — 実際のキー/筐体/インターロック GPIO セーフガード 3 系統を読み取る、レーザーセルの安全コーディネーター。
- **[HYDRA-UMC-BRIDGE-OPENPNP](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-OPENPNP)** — OpenPnP ピックアンドプレースの基板フローを安全に統括する高レベルコーディネーター。
- **[HYDRA-UMC-BRIDGE-PRINTER3D](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-PRINTER3D)** — 実際にゲート制御されたジョブコマンドを持つ、Moonraker/Klipper 3D プリンター向けの安全な調整境界。
- **[HYDRA-UMC-BRIDGE-ROS2](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-ROS2)** — 実際の遅延インポート rclpy ROS 2 トランスポートを持つ安全コーディネーター。
- **[HYDRA-UMC-BRIDGE-UAV](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-UAV)** — 実際の MAVLink コマンド送信機能を持つ、カメラ搭載 UAV の調整境界。

*URTC ツールプラットフォーム*
- **[URTC](https://github.com/JuanenRac/URTC)** — 物理的な Universal Robot Tool Controller 基板向けファームウェア、CAN バス経由の 25 以上のツールプロファイル。
- **[URTC-FLASHER](https://github.com/JuanenRac/URTC-FLASHER)** — URTC 基板用のデスクトップ GUI 書き込みツール、CAN-OTA およびフルチップ SWD/JTAG。
- **[URTC-TESTER](https://github.com/JuanenRac/URTC-TESTER)** — URTC 基板向けのデスクトップ CAN バスライブ診断ツール、ツールプロファイルごとに 1 パネル。
- **[URTC-WEB-STUDIO](https://github.com/JuanenRac/URTC-WEB-STUDIO)** — Web Serial API を使ったブラウザベースの URTC-TESTER の代替、ローカルインストール不要。

*ビジョン AI ノード(Hailo-8)*
- **[HYDRA-UMC-VISION-STREAMER](https://github.com/JuanenRac/HYDRA-UMC-VISION-STREAMER)** — 実際の HailoRT 統合境界を持つ、実際の GStreamer パイプライン + MediaMTX 設定生成器。
- **[HYDRA-UMC-VISUAL-SERVOING-API](https://github.com/JuanenRac/HYDRA-UMC-VISUAL-SERVOING-API)** — 上流のゾーン状態に応じて安全ゲート制御される、実際の Position-Based Visual Servoing 補正則。
- **[HYDRA-UMC-SAFETY-ZONES](https://github.com/JuanenRac/HYDRA-UMC-SAFETY-ZONES)** — キャリブレーションの鮮度を強制する、実際のゾーン侵入チェックと E-STOP 要求。

*コグニティブ AI ノード(Hailo-10)*
- **[HYDRA-UMC-COGNITIVE-NODE](https://github.com/JuanenRac/HYDRA-UMC-COGNITIVE-NODE)** — Hailo-10 コグニティブパイプライン(LLM/VLA/音声オーケストレーション)の統合ハブ。
- **[HYDRA-UMC-VLA-ENGINE](https://github.com/JuanenRac/HYDRA-UMC-VLA-ENGINE)** — Vision-Language-Action モデル向けの、実際のアクショントークンのエンコード/デコードと軌道生成。
- **[HYDRA-UMC-VOICE-UI](https://github.com/JuanenRac/HYDRA-UMC-VOICE-UI)** — 確認ゲート付きの限定的な Watch リレーを備えた、実際の音声フロントエンド(VAD + 意図解析)。
- **[HYDRA-UMC-SEMANTIC-PLANNER](https://github.com/JuanenRac/HYDRA-UMC-SEMANTIC-PLANNER)** — MCU エラーコードに対する、実際のルールベースのタスク分解と意味的エラー復旧。
- **[HYDRA-UMC-DOCS-QA](https://github.com/JuanenRac/HYDRA-UMC-DOCS-QA)** — このエコシステム自身の Markdown ドキュメントに対する、標準ライブラリのみの実際の TF-IDF 文書検索。

*オーケストレーション&スウォーム*
- **[HYDRA-UMC-ORCHESTRATOR](https://github.com/JuanenRac/HYDRA-UMC-ORCHESTRATOR)** — 実際の gRPC/Protobuf ヘルスレポート契約とミッションステートマシンを持つ統合ハブ。
- **[HYDRA-UMC-JOB-DISPATCHER](https://github.com/JuanenRac/HYDRA-UMC-JOB-DISPATCHER)** — 実際の HTTP API 上に構築された、優先度ベースの実際のジョブキュー(重複排除付き)。
- **[HYDRA-UMC-NODE-HEALING](https://github.com/JuanenRac/HYDRA-UMC-NODE-HEALING)** — リトライ/バックオフとアイデンティティ不一致検出を備えた、実際の gRPC ベースのフリートヘルスウォッチドッグ。
- **[HYDRA-UMC-PATH-PLANNER-3D](https://github.com/JuanenRac/HYDRA-UMC-PATH-PLANNER-3D)** — 実際の障害物/ワークスペース衝突検証を備えた、実際の RRT ベースの 3D 経路プランナー。
- **[HYDRA-UMC-SWARM-SYNC](https://github.com/JuanenRac/HYDRA-UMC-SWARM-SYNC)** — 複数セルの収束についてプロパティテストされた、実際の CRDT LWW-Element-Map 状態同期。

*データ&分析*
- **[HYDRA-UMC-DATALAKE](https://github.com/JuanenRac/HYDRA-UMC-DATALAKE)** — 実際の取り込み/クエリ HTTP API を備えた、実際の sqlite3 ベースの時系列ストア。
- **[HYDRA-UMC-ANOMALY-DETECTOR](https://github.com/JuanenRac/HYDRA-UMC-ANOMALY-DETECTOR)** — ドリフト監視を備えた、実際の FFT + 統計ベースラインによる異常検知器。
- **[HYDRA-UMC-PRODUCTION-REPORTS](https://github.com/JuanenRac/HYDRA-UMC-PRODUCTION-REPORTS)** — DATALAKE の履歴に対する実際の OEE/稼働率計算、再現可能な CSV エクスポート付き。
- **[HYDRA-UMC-TELEMETRY-COLLECTOR](https://github.com/JuanenRac/HYDRA-UMC-TELEMETRY-COLLECTOR)** — シーケンス重複排除機能を備えた、DATALAKE への実際の CAN/WebSocket 取り込みパイプライン。

*産業用ゲートウェイ*
- **[HYDRA-UMC-GATEWAY-INDUSTRIAL](https://github.com/JuanenRac/HYDRA-UMC-GATEWAY-INDUSTRIAL)** — 実際のコマンド許可リスト/バックプレッシャー層を持つ、産業用プロトコルへ中継する統合ハブ。
- **[HYDRA-UMC-OPCUA-SERVER](https://github.com/JuanenRac/HYDRA-UMC-OPCUA-SERVER)** — 実際のバイナリプロトコルクライアントセッションで検証された、実際の OPC-UA アドレス空間。
- **[HYDRA-UMC-MQTT-BROKER](https://github.com/JuanenRac/HYDRA-UMC-MQTT-BROKER)** — クライアント単位のオプション認証とトピック ACL を備えた、実際の MQTT ブローカー。
- **[HYDRA-UMC-MTCONNECT-ADAPTER](https://github.com/JuanenRac/HYDRA-UMC-MTCONNECT-ADAPTER)** — 縮退モード出力を備えた、実際の MTConnect `/probe` および `/current` XML エンドポイント。

*補完ツール&エコシステム運用*
- **[HYDRA-UMC-DASHBOARD-AI](https://github.com/JuanenRac/HYDRA-UMC-DASHBOARD-AI)** — 誠実な統計フォールバックを備えた、DATALAKE/ANOMALY-DETECTOR 上のスマートサマリーと異常ハイライトパネル。
- **[HYDRA-UMC-TOOL-CLI](https://github.com/JuanenRac/HYDRA-UMC-TOOL-CLI)** — 実際の安定した終了コード契約を持つフリート CLI、HYDRA-UMC-SERVER 自身の API の本物のライブクライアント。
- **[HYDRA-UMC-WATCH](https://github.com/JuanenRac/HYDRA-UMC-WATCH)** — 実際の触覚アラートとペアリングされたスマートフォンへの音声リレーを備えた WearOS コンパニオンアプリ。
- **[URTC-SMART-RACK](https://github.com/JuanenRac/URTC-SMART-RACK)** — 実際の工具 ID デコードと Smart Idle 予熱ロジックを備えた、基板搭載ラック用ファームウェア。
- **[URTC-VISION-TOOL](https://github.com/JuanenRac/URTC-VISION-TOOL)** — サーマル/RGB 検査ツールヘッド向けの、ファームウェアと実際の Python ビジョンコンパニオン。
- **[HYDRA-UMC-UPDATER](https://github.com/JuanenRac/HYDRA-UMC-UPDATER)** — このエコシステム内のすべてのリポジトリを検出・クローン・更新する、管理用デスクトップツール。


## 👤 作者
**JuanenRac** (Electro Hobby 3D)
📧 electrohobby3d@gmail.com
📺 [youtube.com/@electrohobby3d](https://youtube.com/@electrohobby3d)

## 📜 ライセンス
GPL-3.0 —— 詳細は LICENSE を参照してください。
