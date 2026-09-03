<p align="center">
  <img src="images/HYDRA_UMC_BANNER.svg" alt="HYDRA-UMC-SYNTHETIC-DATA-GEN banner" width="100%">
</p>

# 🎲 HYDRA-UMC-SYNTHETIC-DATA-GEN

<p align="center"><a href="README.md">🇺🇸 English</a> | <a href="README_spa.md">🇪🇸 Español</a> | <a href="README_fra.md">🇫🇷 Français</a> | 🇮🇹 <b>Italiano</b> | <a href="README_deu.md">🇩🇪 Deutsch</a> | <a href="README_zho.md">🇨🇳 简体中文</a> | <a href="README_jpn.md">🇯🇵 日本語</a></p>

### 📸 Generatore di dataset procedurali per l'addestramento dei Vision AI Node

<p align="left">
  <img src="https://img.shields.io/badge/Licenza-GPL%203.0-blue.svg" alt="GPL 3.0">
  <img src="https://img.shields.io/badge/Formato-YOLO%20%2F%20COCO-FF6F00.svg" alt="Format">
  <img src="https://img.shields.io/badge/Target-Vision%20AI%20Node-green.svg" alt="Target">
</p>

---

## 1. 🛠️ PANORAMICA TECNICA

**HYDRA-UMC-SYNTHETIC-DATA-GEN** è la fabbrica di dati per i Vision AI Node. Sfrutta i motori di fisica e rendering del Digital Twin per generare proceduralmente migliaia di immagini etichettate per l'addestramento delle reti neurali.

Risolve il problema del «cold start» per i nuovi componenti industriali o i tipi di difetti rari creando scenari 3D fotorealistici con annotazioni automatiche perfette al pixel (bounding box, maschere di segmentazione e keypoint).

### Caratteristiche principali:
* 🎲 **Scenari procedurali (v0):** Randomizzazione reale e deterministica (con seed) di posizione, dimensione e colore dei componenti 2D. *(implementato come vere forme 2D segnaposto, non ancora pose/illuminazione/texture 3D tramite il motore di HYDRA-UMC-TWIN - vedi BUILD E RUN sotto)*
* 📸 **Rendering multi-camera:** Genera viste simultanee da oltre 8 telecamere virtuali. *(pianificato - richiede il vero motore di rendering di HYDRA-UMC-TWIN)*
* 🏷️ **Etichettatura automatica (v0):** Esportazione reale e perfetta al pixel in YOLO e COCO. *(implementato per YOLO/COCO; l'esportazione TFRecord è pianificata)*
* 🛠️ **Iniezione di difetti (v0):** Sovrapposizione rettangolare reale e casuale per componente, con probabilità configurabile. *(implementato come una semplice sovrapposizione reale - vere forme di graffio/parte mancante/ponte di saldatura sono pianificate)*
* 📋 **Manifesto del dataset e validazione (v0):** Ogni esecuzione di `generate` scrive un vero `manifest.json` (flag di seed riproducibile, parametri di generazione, e un vero checksum sha256 per immagine) ed esegue una vera validazione post-generazione - limiti di scena, integrità BMP rispetto al layout di file reale noto, e sanità della distribuzione delle etichette - uscendo con codice diverso da zero se viene trovato un problema reale.

---

## 2. 🔄 PIPELINE DI GENERAZIONE

```mermaid
flowchart LR
    MODELS["Modelli 3D dei componenti"] --> SCENE["Scene Randomizer"]
    SCENE --> RENDER["Physics-Based Renderer"]
    RENDER --> ANN["Motore di auto-annotazione"]
    ANN --> DATASET["Dataset di addestramento (YOLO/COCO)"]
    DATASET --> TRAIN["Addestramento Vision Node"]
```

---

## 3. 🧱 ARCHITETTURA E DECISIONI DI PROGETTAZIONE

* **Perché questo generatore non ha cartelle `hardware/`/`firmware/`/`os/`.** Software puro - renderizza scene tramite il motore proprio di HYDRA-UMC-TWIN invece di possedere hardware proprio.
* **Perché è fratello, non un sottomodulo, di HYDRA-UMC-TWIN.** La generazione di dataset è un carico di lavoro batch, offline (potenzialmente ore di rendering) fondamentalmente diverso dal ciclo in tempo reale proprio del gemello - tenerla separata significa che un lungo export non compete mai con la simulazione in tempo reale per la CPU/GPU dello stesso processo.
* **Perché il punto di ingresso oggi stampa solo identità/versione/ruolo.** Fase di andamiaje: dimostrare che il pacchetto si installa e importa in modo pulito precede la vera logica di randomizzazione procedurale/rendering/esportazione annotazioni.
* **Come si inserisce nel resto dell'ecosistema.** Renderizza dataset di addestramento (con annotazione automatica YOLO/COCO/TFRecord) tramite il motore proprio di HYDRA-UMC-TWIN, perché HYDRA-UMC-VISION-NODE e HYDRA-UMC-DETECTION-HEF si addestrino su di essi - dati sintetici invece di etichettare a mano filmati reali della camera.
* **Perché v0 renderizza vere forme 2D segnaposto invece di aspettare HYDRA-UMC-TWIN.** HYDRA-UMC-TWIN (il proprio genitore di integrazione di questo progetto) è a sua volta ancora in fase di andamiaje - bloccare del tutto la generazione di dataset sul suo vero motore 3D lascerebbe non testata la pipeline di annotazione (la parte davvero difficile e riutilizzabile: posizionamento, etichettatura, esportazione YOLO/COCO). Un rasterizzatore BMP reale, solo stdlib, offre oggi dati reali e perfetti al pixel; sostituire in seguito il vero motore di TWIN cambia solo il modo in cui i pixel vengono dipinti, non i contratti `Scene`/`Component`/esportazione.
* **Perché i bounding box sono perfetti al pixel per costruzione.** `export.py` legge esattamente le stesse coordinate di `Component` che `scene.py` ha posizionato e `render.py` ha dipinto - non c'è alcun modello di rilevamento né alcun passo di etichettatura manuale in questo ciclo v0 da cui le annotazioni potrebbero divergere.
* **Perché la validazione riutilizza la formula di dimensione riga di `render.py` invece di un secondo parser indipendente.** `validate_bmp_integrity()` importa direttamente `_row_size()` da `render.py` invece di ri-derivare il calcolo del padding di riga BMP - un'unica fonte di verità per il layout esatto dei byte evita che un futuro cambiamento reale nello scrittore si desincronizzi silenziosamente dal validatore.
* **Perché "riproducibile" è un campo del manifesto, non solo una proprietà implicita di `--seed`.** `--seed` rendeva già la generazione deterministica prima di questo cambiamento, ma nulla registrava se un dato dataset su disco avesse effettivamente usato un seed - un consumatore non aveva modo di distinguere a posteriori un'esecuzione riproducibile da una casuale. Il flag `reproducible` di `manifest.json` più un vero sha256 per immagine rende questa affermazione verificabile.

---

## 📂 STRUTTURA DELLE CARTELLE

Generatore di dataset puramente software, senza progettazione hardware
propria - per questo il progetto non ha cartelle `hardware/`, `firmware/`
né `os/`, secondo la politica della struttura del repository.

```text
HYDRA-UMC-SYNTHETIC-DATA-GEN/
├── src/hydra_umc_synthetic_data_gen/
│   ├── __init__.py            # Versione del pacchetto
│   ├── scene.py          # Generazione reale di scene/componenti 2D procedurali
│   ├── render.py          # Rasterizzazione BMP reale, solo stdlib
│   ├── export.py           # Esportazione reale delle annotazioni YOLO/COCO
│   ├── manifest.py           # Vero manifest.json del dataset (seed, checksum)
│   ├── validate.py           # Vera validazione limiti/integrità BMP/distribuzione
│   └── main.py               # Punto di ingresso + sottocomando reale `generate`
├── tests/               # Test reali: generazione, rendering, esportazione, CLI end-to-end
├── docs/                # Documentazione e guide procedurali
├── build/               # Output di build (il .venv locale vive anche nella radice del repo)
├── images/              # Media e diagrammi
├── tools/               # ci_validate.py - validazione manifest/CHANGELOG/docs usata dalla CI
├── pyproject.toml       # Metadati del pacchetto, dipendenze, version contachilometri
├── bump_version.py      # Bump di version tipo contachilometri (usato da build.sh/.bat)
├── bump_manifest_version.py # Sincronizza la versione di hydra-umc.project.json con quella nativa (--sync)
├── build.sh / build.bat # venv + installazione editabile (con extra dev) + test reali + compile-check
└── run.sh / run.bat     # Esegue l'entry point dal venv locale (inoltra gli argomenti, es. `generate`)
```

---

## 🏗️ BUILD E RUN

Richiede Python 3.10+.

```bash
# Linux / macOS
./build.sh   # bump di version contachilometri, crea .venv, installa il
             # pacchetto in modalità editabile (con extra dev), esegue la
             # vera suite di test, compile-check di tutto src/
./run.sh     # esegue l'entry point da .venv, stampa nome + version + ruolo
```

```bat
:: Windows
build.bat
run.bat
```

`build.sh`/`build.bat` incrementano la version del proprio `pyproject.toml` di questo progetto seguendo la regola "contachilometri" dell'ecosistema (PATCH+1, con riporto a MINOR superato 9) prima di ogni build reale, eseguono la vera suite di test (`pytest tests/`), e poi fanno il compile-check del codice sorgente con `python -m compileall`.

Il vero sottocomando `generate` scrive un vero dataset su disco:

```bash
./run.sh generate --out dataset/ --count 20 --components 6 --defect-rate 0.3 --seed 42 --format both

# Windows
run.bat generate --out dataset\ --count 20 --components 6 --defect-rate 0.3 --seed 42 --format both
```

Scrive vere immagini BMP in `dataset/images/`, vere etichette YOLO in `dataset/labels/` + `dataset/classes.txt`, e/o un vero `dataset/annotations.json` in formato COCO, a seconda di `--format`. Un `--seed` dato rende il dataset riproducibile byte per byte.

Ogni esecuzione scrive anche un vero `dataset/manifest.json` e valida il proprio output:

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

Se la validazione trova un problema reale (un componente fuori intervallo, un BMP troncato/corrotto, o un tasso di difetti che si è discostato molto da `--defect-rate`), `generate` esce con codice `1` ed elenca ogni problema invece di consegnare silenziosamente un dataset difettoso.

---

## 🚀 TABELLA DI MARCIA
* **Fase 1:** Sincronizzazione del Digital Twin con telemetria hardware in tempo reale e latenza inferiore a 10 ms.
* **Fase 2:** Integrazione di Physics Replica con simulatori di livello industriale (Isaac Sim) e supporto per corpi deformabili.
* **Fase 3:** Modelli di ripristino automatizzati di Node Healing per failover decentralizzato e rilevamento precoce del degrado dei sensori.
* **Fase 4:** Affinamento delle texture basato su GAN per materiali industriali iper-realistici e generazione di dataset fotorealistici.

---

## 🔗 Progetti Correlati

Questo progetto fa parte dell'ecosistema robotico HYDRA-UMC dello stesso autore (JuanenRac / Electro Hobby 3D). Vale la pena conoscerlo, poiché una richiesta potrebbe in realtà riguardare uno di questi invece di questo repository.

**Progetto Padre**
- **[HYDRA-UMC-TWIN](https://github.com/JuanenRac/HYDRA-UMC-TWIN)** — hub di integrazione per il motore di gemello digitale, con un vero contratto di sincronizzazione per compatibilità di versione; il genitore di cui questo repository è un servizio di simulazione specifico, all'interno del proprio motore di gemello digitale.

**Progetti Fratelli** — gli altri servizi di simulazione del motore di gemello digitale proprio di HYDRA-UMC-TWIN
- **[HYDRA-UMC-PHYSICS-REPLICA](https://github.com/JuanenRac/HYDRA-UMC-PHYSICS-REPLICA)** — vera cinematica diretta e validazione dei limiti articolari su un vero sottoinsieme URDF.
- **[HYDRA-UMC-HIL-BRIDGE](https://github.com/JuanenRac/HYDRA-UMC-HIL-BRIDGE)** — vero interblocco di sicurezza hardware-in-the-loop che instrada i comandi tra simulazione e hardware reale.

**Direttamente Correlati**
- **[HYDRA-UMC-VISION-NODE](https://github.com/JuanenRac/HYDRA-UMC-VISION-NODE)** — hub di integrazione per la pipeline di visione Hailo-8, con un vero controllo di prontezza hardware per fase — addestrato sui dataset che questo progetto genera.
- **[HYDRA-UMC-DETECTION-HEF](https://github.com/JuanenRac/HYDRA-UMC-DETECTION-HEF)** — registro reale di modelli compilati con verifica di caricamento sicuro per architettura Hailo/checksum — addestrato sui dataset che questo progetto genera.

**Fa Anche Parte dell'Ecosistema**

*Hardware e Piattaforma di Base*
- **[HYDRA-UMC](https://github.com/JuanenRac/HYDRA-UMC)** — la scheda madre fisica del braccio robotico: host CM5 + coprocessore STM32H745 dual-core, che coordina fino a 8 bracci utensile via CAN-OTA/SPI-OTA.
- **[HYDRA-UMC-OS](https://github.com/JuanenRac/HYDRA-UMC-OS)** — livello prodotto riproducibile su Raspberry Pi OS per il CM5: agente in sola lettura, config/profili validati, provisioning WiFi al primo contatto.
- **[HYDRA-UMC-SDK](https://github.com/JuanenRac/HYDRA-UMC-SDK)** — il contratto JSON-Schema condiviso e la barriera di sicurezza contro cui ogni bridge valida i propri comandi.

*Backend Centrale e Client*
- **[HYDRA-UMC-SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER)** — il vero backend headless (REST/WebSocket) con cui parla davvero ogni client di controllo.
- **[HYDRA-UMC-STUDIO](https://github.com/JuanenRac/HYDRA-UMC-STUDIO)** — dashboard di controllo web con visualizzazione 3D multi-robot in tempo reale.
- **[HYDRA-UMC-SUITE](https://github.com/JuanenRac/HYDRA-UMC-SUITE)** — centro di comando sciame desktop (PySide6) per più server contemporaneamente, pacchettizzato come eseguibile standalone.
- **[HYDRA-UMC-ANDROID-CONTROL](https://github.com/JuanenRac/HYDRA-UMC-ANDROID-CONTROL)** — app di controllo nativa per Android con login biometrico e un companion Wear OS abbinato.
- **[HYDRA-UMC-IOS-CONTROL](https://github.com/JuanenRac/HYDRA-UMC-IOS-CONTROL)** — app di controllo per iOS/iPadOS (Flutter) con sincronizzazione WebSocket in tempo reale.
- **[HYDRA-UMC-DSI](https://github.com/JuanenRac/HYDRA-UMC-DSI)** — interfaccia touch nativa per il touchscreen DSI da 7" a bordo, incorporata direttamente nel CM5.
- **[HYDRA-UMC-EDITOR-URDF](https://github.com/JuanenRac/HYDRA-UMC-EDITOR-URDF)** — creatore/editor grafico desktop di URDF che invia i modelli finiti al catalogo di STUDIO.
- **[HYDRA-UMC-BRIDGE-AMR](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-AMR)** — barriera di coordinamento per flotte AGV/AMR tramite un publisher MQTT VDA 5050 reale.
- **[HYDRA-UMC-BRIDGE-CNC](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-CNC)** — coordinatore ad alto livello per celle CNC con accesso reale a stato/byte di controllo GRBL.
- **[HYDRA-UMC-BRIDGE-DROIDS](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-DROIDS)** — barriera di coordinamento per droidi con zampe/umanoidi, con un vero mittente di comandi per Boston Dynamics Spot.
- **[HYDRA-UMC-BRIDGE-LASER](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-LASER)** — coordinatore di sicurezza per celle laser che legge 3 salvaguardie GPIO reali di chiave/involucro/interblocco.
- **[HYDRA-UMC-BRIDGE-OPENPNP](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-OPENPNP)** — coordinatore ad alto livello sicuro per il flusso schede del pick-and-place OpenPnP.
- **[HYDRA-UMC-BRIDGE-PRINTER3D](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-PRINTER3D)** — barriera di coordinamento sicura per stampanti 3D Moonraker/Klipper, con comandi di lavoro reali e controllati.
- **[HYDRA-UMC-BRIDGE-ROS2](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-ROS2)** — coordinatore di sicurezza con un vero trasporto ROS 2 rclpy, importato in modo lazy.
- **[HYDRA-UMC-BRIDGE-UAV](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-UAV)** — barriera di coordinamento per UAV dotati di fotocamera, con un vero mittente di comandi MAVLink.

*Piattaforma Strumenti URTC*
- **[URTC](https://github.com/JuanenRac/URTC)** — firmware per la scheda fisica dell'Universal Robot Tool Controller, oltre 25 profili utensile su bus CAN.
- **[URTC-FLASHER](https://github.com/JuanenRac/URTC-FLASHER)** — strumento desktop con GUI per il flashing delle schede URTC, CAN-OTA più SWD/JTAG a chip intero.
- **[URTC-TESTER](https://github.com/JuanenRac/URTC-TESTER)** — strumento desktop di diagnostica CAN-bus dal vivo per schede URTC, un pannello per profilo utensile.
- **[URTC-WEB-STUDIO](https://github.com/JuanenRac/URTC-WEB-STUDIO)** — alternativa basata su browser a URTC-TESTER tramite la Web Serial API, senza installazione locale.

*Nodo IA Visione (Hailo-8)*
- **[HYDRA-UMC-VISION-STREAMER](https://github.com/JuanenRac/HYDRA-UMC-VISION-STREAMER)** — generatore reale di pipeline GStreamer + config MediaMTX, con una vera barriera di integrazione HailoRT.
- **[HYDRA-UMC-VISUAL-SERVOING-API](https://github.com/JuanenRac/HYDRA-UMC-VISUAL-SERVOING-API)** — vera legge di correzione Position-Based Visual Servoing, con cancello di sicurezza sullo stato di zona a monte.
- **[HYDRA-UMC-SAFETY-ZONES](https://github.com/JuanenRac/HYDRA-UMC-SAFETY-ZONES)** — vero controllo di violazione zona e richiesta E-STOP, con imposizione della freschezza di calibrazione.

*Nodo IA Cognitivo (Hailo-10)*
- **[HYDRA-UMC-COGNITIVE-NODE](https://github.com/JuanenRac/HYDRA-UMC-COGNITIVE-NODE)** — hub di integrazione per la pipeline cognitiva Hailo-10 (orchestrazione LLM/VLA/voce).
- **[HYDRA-UMC-VLA-ENGINE](https://github.com/JuanenRac/HYDRA-UMC-VLA-ENGINE)** — vera codifica/decodifica di token d'azione e generazione di traiettoria per un modello Vision-Language-Action.
- **[HYDRA-UMC-VOICE-UI](https://github.com/JuanenRac/HYDRA-UMC-VOICE-UI)** — vero front-end vocale (VAD + parser di intenti) con un relay verso Watch limitato e soggetto a conferma.
- **[HYDRA-UMC-SEMANTIC-PLANNER](https://github.com/JuanenRac/HYDRA-UMC-SEMANTIC-PLANNER)** — vera scomposizione dei task basata su regole e recupero semantico degli errori sui codici errore MCU.
- **[HYDRA-UMC-DOCS-QA](https://github.com/JuanenRac/HYDRA-UMC-DOCS-QA)** — vera ricerca documentale TF-IDF (solo libreria standard) sui documenti Markdown di questo ecosistema.

*Orchestrazione e Sciame*
- **[HYDRA-UMC-ORCHESTRATOR](https://github.com/JuanenRac/HYDRA-UMC-ORCHESTRATOR)** — hub di integrazione con un vero contratto di health-report gRPC/Protobuf e una macchina a stati di missione.
- **[HYDRA-UMC-JOB-DISPATCHER](https://github.com/JuanenRac/HYDRA-UMC-JOB-DISPATCHER)** — vera coda di lavori basata su priorità con deduplicazione, su una vera API HTTP.
- **[HYDRA-UMC-NODE-HEALING](https://github.com/JuanenRac/HYDRA-UMC-NODE-HEALING)** — vero watchdog di salute della flotta basato su gRPC, con retry/backoff e rilevamento di discrepanza d'identità.
- **[HYDRA-UMC-PATH-PLANNER-3D](https://github.com/JuanenRac/HYDRA-UMC-PATH-PLANNER-3D)** — vero pianificatore di percorsi 3D basato su RRT, con vera validazione delle collisioni ostacolo/spazio di lavoro.
- **[HYDRA-UMC-SWARM-SYNC](https://github.com/JuanenRac/HYDRA-UMC-SWARM-SYNC)** — vera sincronizzazione di stato CRDT LWW-Element-Map, con property test per la convergenza multi-cella.

*Dati e Analisi*
- **[HYDRA-UMC-DATALAKE](https://github.com/JuanenRac/HYDRA-UMC-DATALAKE)** — vero archivio di serie temporali basato su sqlite3, con una vera API HTTP di ingestione/query.
- **[HYDRA-UMC-ANOMALY-DETECTOR](https://github.com/JuanenRac/HYDRA-UMC-ANOMALY-DETECTOR)** — vero rilevatore di anomalie FFT + baseline statistica, con monitoraggio della deriva.
- **[HYDRA-UMC-PRODUCTION-REPORTS](https://github.com/JuanenRac/HYDRA-UMC-PRODUCTION-REPORTS)** — vero calcolo OEE/disponibilità sullo storico di DATALAKE, con esportazione CSV riproducibile.
- **[HYDRA-UMC-TELEMETRY-COLLECTOR](https://github.com/JuanenRac/HYDRA-UMC-TELEMETRY-COLLECTOR)** — vera pipeline di ingestione CAN/WebSocket verso DATALAKE, con deduplicazione per sequenza.

*Gateway Industriale*
- **[HYDRA-UMC-GATEWAY-INDUSTRIAL](https://github.com/JuanenRac/HYDRA-UMC-GATEWAY-INDUSTRIAL)** — hub di integrazione che inoltra ai protocolli industriali, con un vero livello di allowlist dei comandi/backpressure.
- **[HYDRA-UMC-OPCUA-SERVER](https://github.com/JuanenRac/HYDRA-UMC-OPCUA-SERVER)** — vero spazio di indirizzi OPC-UA, verificato con una vera sessione client del protocollo binario.
- **[HYDRA-UMC-MQTT-BROKER](https://github.com/JuanenRac/HYDRA-UMC-MQTT-BROKER)** — vero broker MQTT con autenticazione opzionale per client e ACL sui topic.
- **[HYDRA-UMC-MTCONNECT-ADAPTER](https://github.com/JuanenRac/HYDRA-UMC-MTCONNECT-ADAPTER)** — veri endpoint XML `/probe` e `/current` di MTConnect, con output in modalità degradata.

*Strumenti Complementari e Operazioni dell'Ecosistema*
- **[HYDRA-UMC-DASHBOARD-AI](https://github.com/JuanenRac/HYDRA-UMC-DASHBOARD-AI)** — pannelli Smart Summaries e Anomaly Highlighting su DATALAKE/ANOMALY-DETECTOR, con un fallback statistico onesto.
- **[HYDRA-UMC-TOOL-CLI](https://github.com/JuanenRac/HYDRA-UMC-TOOL-CLI)** — CLI di flotta con un vero e stabile contratto di exit-code, un client live reale della stessa API di HYDRA-UMC-SERVER.
- **[HYDRA-UMC-WATCH](https://github.com/JuanenRac/HYDRA-UMC-WATCH)** — app companion WearOS con avvisi aptici reali e un relay vocale verso il telefono abbinato.
- **[URTC-SMART-RACK](https://github.com/JuanenRac/URTC-SMART-RACK)** — firmware per un rack di montaggio schede con decodifica reale dell'ID utensile e logica di preriscaldamento Smart Idle.
- **[URTC-VISION-TOOL](https://github.com/JuanenRac/URTC-VISION-TOOL)** — firmware più un vero companion di visione Python per una testa utensile di ispezione termica/RGB.
- **[HYDRA-UMC-UPDATER](https://github.com/JuanenRac/HYDRA-UMC-UPDATER)** — strumento amministrativo desktop che scopre, clona e aggiorna ogni repository di questo ecosistema.


---

## 📚 Documentazione e Comunità

- **[CONTRIBUTING.md](CONTRIBUTING.md)** — stack tecnologico e linee guida di codifica per una pull request.
- **[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)** — gli standard di comportamento attesi in questa comunità.
- **[SECURITY.md](SECURITY.md)** — come segnalare una vulnerabilità, e le reali aree di attenzione sulla sicurezza di questo progetto.
- **[SUPPORT.md](SUPPORT.md)** — dove porre domande e segnalare bug.
- **[LICENSE.md](LICENSE.md)** — la licenza propria di questo progetto.

## 👤 AUTORE
**JuanenRac** (Electro Hobby 3D)
📧 electrohobby3d@gmail.com
📺 [youtube.com/@electrohobby3d](https://youtube.com/@electrohobby3d)

## 📜 LICENZA
GPL-3.0 - Vedere LICENSE per i dettagli.
