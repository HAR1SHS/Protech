# 🌟 ProTech Data Ecosystem Architecture Visualizer

Welcome to the **ProTech Data Ecosystem Architecture Visualizer**! This repository hosts a premium, interactive, light-themed presentation deck that visually maps out ProTech's real-time IoT ingestion pipelines, source-to-database telemetry parser, and Databricks Medallion data engineering architecture.

The entire experience has been compiled into a **single, 100% self-contained static page (`index.html`)** making it incredibly easy to share, run locally, or host on GitHub Pages!

---

## 🚀 Key Features

* **🎨 Premium Light Aesthetics**: Harmonized slate-50 backgrounds, pure white node cards with elegant drop shadows, and category-segregated pastel highlights (Lavender for Sources, Mint for Consumption, etc.).
* **⚡ Alive Flow Animation**: SVG connection lines pulse constantly with dynamic dash animations. Hovering over any card instantly highlights its active pipeline (speeding up flow) and dims all unrelated routes to `15%` opacity for clear telemetry tracing.
* **📈 100% Crossing-Free Orthogonal Routing**: All connection lines route cleanly down empty column gaps, bypass intermediate cards, and utilize custom bottom-loops and overhead bypass paths to eliminate crossings.
* **📱 Bulletproof ResizeObserver Layouts**: SVG lines are robustly calculated relative to actual DOM box boundaries and instantly redraw upon resizing or switching tabs.
* **📦 100% Zero-Dependency Single-File Deck**: Fully self-contained `index.html` file using JavaScript-injected `srcdoc` frames. Runs flawlessly anywhere, even offline, with no external network requests or script name conflicts!

---

## 📁 Repository Structure

* **`index.html`** *(Root)*: The compiled, self-contained single-file deck served by GitHub Pages. Double-click to run the entire visualizer instantly!
* **`deck/`**: The deck source — one HTML file per tab plus the build tooling.
  * `Protech_Presentation.html` — the modular tab shell (iframe controller / build template).
  * `Protech_Source_Architecture.html` — Source Architecture (edge gateway + Data/Control planes).
  * `Protech_Gateway_Architecture.html` — Gateway / PortApps (on-prem BMS ingestion).
  * `Protech_TCPListener_Architecture.html` — Cloud TCP Listener (pt-tcp-listener).
  * `Protech_Databricks_Architecture.html` — Databricks Medallion (Bronze/Silver/Gold).
  * `Protech_CloudPipeline_Architecture.html` — Streaming Pipeline (Gateway → Event Hubs → Decoding → Silver).
  * `Protech_Meter_Utility_Master.html` — Meter-Utility Dictionary (generated from CSV).
  * `source/IoT_Payload_Visualizer.html` — IoT Payload Visualizer (ASCII → Float32 decoder).
  * `combine_presentation.py` — bundles the tabs into the root `index.html` (run from `deck/`).
  * `build_step.py` — regenerates the Meter-Utility Dictionary from the reference CSV.
* **`data/`**: Reference data — `gateway/` (PortApps & pt-tcp-listener analyses) and `Meter-Utility master/` (CSV source for the dictionary).
* **`reference/`**: Supporting docs — admin console guide, admin panel flow, onboarding flow, and dataflow/process drafts.
* **`exports/`**: Print-ready exports — `Protech_Pipeline_Flow_PDF.html` and the generated `ProTech_Streaming_Pipeline.pdf`.

### Rebuilding `index.html`

```bash
cd deck
python combine_presentation.py   # writes the self-contained ../index.html
```

---

## 🛠️ How to View Locally

Simply double-click **`index.html`** in your file manager, or run a simple local web server in your terminal:
```bash
# Using Python
python -m http.server 8000

# Using Node.js
npx serve .
```
Then navigate to `http://localhost:8000` in your browser!

---

## 🌐 Deploying to GitHub Pages

Since the presentation is completely static, it can be hosted on GitHub Pages for free in seconds:
1. Push this folder to your repository: `https://github.com/HAR1SHS/Protech.git`
2. Go to **Settings ➔ Pages** inside your GitHub repository page.
3. Under **Build and deployment**, set **Branch** to `main` (or `master`) and folder to `/ (root)`.
4. Click **Save**!

Your presentation will go live instantly at:
👉 **`https://HAR1SHS.github.io/Protech/`**

---

*Crafted with 💙 by Antigravity.*
