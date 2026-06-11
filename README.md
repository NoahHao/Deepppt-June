# PPT Master — AI generates natively editable PPTX from any document

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

English | [中文](./README_CN.md)

<p align="center">
  <a href="./examples/"><strong>Examples</strong></a> ·
  <a href="./docs/faq.md"><strong>FAQ</strong></a> ·
  <a href="./docs/roadmap.md"><strong>Roadmap</strong></a>
</p>

<h3 align="center">Opening the raw .pptx in PowerPoint is the fastest way to see this project's real capability ceiling. Check out the example decks below.</h3>

<table>
  <tr>
    <td align="center" width="33%">
      <img src="docs/assets/screenshots/preview_pritzker_2026.png" alt="Editorial magazine — Pritzker 2026 architecture review" /><br/>
      <sub><b>Editorial Magazine</b> — architecture photography, calm typographic grid</sub>
    </td>
    <td align="center" width="33%">
      <img src="docs/assets/screenshots/preview_global_ai_capital.png" alt="Data journalism — Global AI Capital 2026" /><br/>
      <sub><b>Data Journalism</b> — Bloomberg-style dark dashboard, chart-driven</sub>
    </td>
    <td align="center" width="33%">
      <img src="docs/assets/screenshots/preview_swiss_grid.png" alt="Swiss typographic grid — Grid Systems primer" /><br/>
      <sub><b>Swiss Grid</b> — strict modular grid, restrained type, red-accent</sub>
    </td>
  </tr>
  <tr>
    <td align="center" width="33%">
      <img src="docs/assets/screenshots/preview_glassmorphism_demo.png" alt="Glassmorphism SaaS — AI Agent engineering demo" /><br/>
      <sub><b>Glassmorphism SaaS</b> — translucent layers, gradient depth, product UI</sub>
    </td>
    <td align="center" width="33%">
      <img src="docs/assets/screenshots/preview_sugar_rush_memphis.png" alt="Memphis pop — Sugar Rush festival" /><br/>
      <sub><b>Memphis Pop</b> — bold primaries, geometric patterns, playful energy</sub>
    </td>
    <td align="center" width="33%">
      <img src="docs/assets/screenshots/preview_indie_bookstore_zine.png" alt="Risograph zine — Indie bookstore guide" /><br/>
      <sub><b>Risograph Zine</b> — duotone print, hand-made bookstore-culture feel</sub>
    </td>
  </tr>
</table>

<p align="center">
  <sub><a href="./examples/"><code>examples/</code> directory</a> · <a href="./docs/why-deepppt.md">Why PPT Master?</a></sub>
</p>

---

Drop in your source material and get back a **real PowerPoint**: directly editable, with native slide transitions and entrance animations, speaker notes you can turn into audio narration, and the option to follow your own PPT template — a complete deck you can present as-is and keep editing. How to use each capability → [Getting Started](./docs/getting-started.md).

> **⚠️ PPT Master is a harness, not a complete agent.** `harness + model = agent` — the tool owns the workflow; the model sets the ceiling. To form a genuinely high-quality agent, use **Claude with a large context window (~1M tokens) + AI image generation (`gpt-image-2`)**. Other models can run the pipeline but cannot reach the same quality ceiling. If results disappoint, upgrade the model — don't blame the harness.

> **How it works** — PPT Master is a workflow (a "skill") that works inside AI IDEs like Claude Code, Cursor, VS Code + Copilot, or Codebuddy. You chat with the AI — "make a deck from this PDF" — and it follows the workflow to produce a real editable `.pptx` on your computer. No coding on your side; the IDE is just where the conversation happens.
>
> **What you'll do**: install Python, install an AI IDE, drop in your material.

> **Why it's shaped this way** — knowing how to use Python and AI agents will matter more and more. This project is meant to show how far you can go with just those two things. There's a learning curve if you're starting cold, but it's the curve worth climbing.

PPT Master is different:

- **Real PowerPoint** — if a file can't be opened and edited in PowerPoint, it shouldn't be called a PPT. Every element PPT Master outputs is directly clickable and editable
- **Transparent, predictable cost** — the tool is free and open source; the only cost is your AI model usage. As AI tools move to usage-based billing, you pay exactly what you consume — no separate PPT subscription added on top
- **Data stays local** — your files shouldn't have to be uploaded to someone else's server just to make a presentation. Apart from AI model communication, the entire pipeline runs on your machine
- **No platform lock-in** — your workflow shouldn't be held hostage by any single company. Works with Claude Code, Cursor, VS Code Copilot, and more; supports Claude, GPT, Gemini, Kimi, and other models

AI presentation tools roughly fall into four categories. PPT Master only does the last one:

| Category | Output | Editable element-by-element in PowerPoint? |
|---|---|:---:|
| Template fill-in | PPTX built from a fixed template | Partially — limited by the template |
| Image-based | One large image per slide, packed into PPTX | ❌ each slide is a picture |
| HTML presentation | Web-based deck | ❌ not a PPTX |
| **Native editable (PPT Master)** | **Real DrawingML shapes, text boxes, charts** | ✅ click any element to edit |

---

## Quick Start

### 1. Prerequisites

**You only need Python.** Everything else is installed via `pip install -r requirements.txt`.

| Dependency | Required? | What it does |
|------------|:---------:|--------------|
| [Python](https://www.python.org/downloads/) 3.10+ | ✅ **Yes** | Core runtime — the only thing you actually need to install |

> **TL;DR** — Install Python, run `pip install -r requirements.txt`, and you're ready to generate presentations.

<details open>
<summary><strong>Windows</strong> — see the dedicated step-by-step guide ⚠️</summary>

Windows requires a few extra steps (PATH setup, execution policy, etc.). We wrote a **step-by-step guide** specifically for Windows users:

**📖 [Windows Installation Guide](./docs/windows-installation.md)** — from zero to a working presentation in 10 minutes.

Quick version: download Python from [python.org](https://www.python.org/downloads/) → **check "Add to PATH"** during install → `pip install -r requirements.txt` → done.
</details>

<details>
<summary><strong>macOS / Linux</strong> — install and go</summary>

```bash
# macOS
brew install python
pip install -r requirements.txt

# Ubuntu / Debian
sudo apt install python3 python3-pip
pip install -r requirements.txt
```
</details>

<details>
<summary><strong>Edge-case fallback</strong> — 99% of users don't need this</summary>

**Pandoc** — only needed for legacy document formats: `.doc`, `.odt`, `.rtf`, `.tex`, `.rst`, `.org`, or `.typ`. `.docx`, `.html`, `.epub`, `.ipynb` are handled natively by Python — no pandoc required.

```bash
# macOS
brew install pandoc

# Ubuntu / Debian
sudo apt install pandoc
```
</details>

### 2. Pick an Agent

PPT Master runs in **any tool with agent capability** — read/write files, execute commands, and sustain multi-turn conversation.

| Type | Examples | Notes |
|---|---|---|
| **IDE-native agent** | • VS Code architecture ([VS Code](https://code.visualstudio.com/) itself, plus forks & derivatives): [Cursor](https://cursor.sh/), Trae, Codebuddy IDE, [Windsurf](https://codeium.com/windsurf), Void, etc.<br>• Other architectures: [Zed](https://zed.dev/), etc. | Editor with a built-in agent |
| **IDE plugin / extension** | [GitHub Copilot](https://github.com/features/copilot), [Claude Code](https://claude.ai/code) (VS Code / JetBrains extension), [Cline](https://cline.bot/), [Continue](https://continue.dev/), Roo Code, etc. | Installed inside hosts like VS Code or JetBrains |
| **CLI agent** | [Claude Code](https://claude.ai/code) CLI, [Codex CLI](https://github.com/openai/codex), [Aider](https://aider.chat/), Gemini CLI, etc. | Runs in the terminal; suits scripting, remote, or server use |

> **Model recommendation**: prefer **Claude Opus / Sonnet** with a large context window and `gpt-image-2` for images — see the note above for why.

### 3. Set Up

**Option A — Download ZIP** (no Git required): get the source code from the project repository and unzip.

**Option B — Git clone** (requires [Git](https://git-scm.com/downloads) installed):

```bash
git clone <repository-url>
cd deepppt
```

Then install dependencies:

```bash
pip install -r requirements.txt
```

To update later (Option A / B): `python3 skills/deepppt/scripts/update_repo.py`

> **Option C — Skill marketplace**: the repo ships `.claude-plugin/marketplace.json`, so it can be installed through the [Claude Code plugin marketplace](https://code.claude.com/docs/en/plugin-marketplaces) ecosystem:
>
> ```bash
> # Cross-agent CLI (Claude Code, Cursor, Codex, etc.)
> npx skills add <repository-path>
>
> # Or inside Claude Code
> /plugin marketplace add <repository-path>
> /plugin install deepppt@deepppt
> ```
>
> Both install paths above only fetch the skill files (not the full repo); you still need to `pip install -r requirements.txt` from the installed location for the post-processing scripts to run.

### 4. Create

**Provide source materials (recommended):** Place your PDF, DOCX, images, or other files in the `projects/` directory, then tell the AI chat panel which files to use. The quickest way to get the path: right-click the file in your file manager or IDE sidebar → **Copy Path** (or **Copy Relative Path**) and paste it directly into the chat.

```
You: Please create a PPT from projects/q3-report/sources/report.pdf
```

**Paste content directly:** You can also paste text content straight into the chat window and the AI will generate a PPT from it.

```
You: Please turn the following into a PPT: [paste your content here...]
```

Either way, the AI will first confirm the design spec:

```
AI:  Sure. Let's confirm the design spec:
     [Template] B) Free design
     [Format]   PPT 16:9
     [Pages]    8-10 pages
     ...
```

The AI handles everything — content analysis, visual design, SVG generation, and PPTX export.

> **Output:** Native-shapes `.pptx` (directly editable) saved to `exports/<name>_<timestamp>.pptx`. A copy of `svg_output/` is always snapshotted to `backup/<timestamp>/svg_output/` for re-export / archival. Pass `--svg-snapshot` to additionally emit an SVG-image preview pptx alongside the native pptx in `exports/` (see [FAQ](./docs/faq.md)). Requires Office 2016+.

> **AI lost context?** Ask it to read `skills/deepppt/SKILL.md`.

> **Something went wrong?** Check the **[FAQ](./docs/faq.md)** — it covers model selection, layout issues, export problems, and more. Continuously updated from real user reports.

### 5. Image Acquisition (Optional)

Two paths for non-user images, mixable per row in the same deck:

For API-backed features, put credentials in `.env`. Clone installs can use `cp .env.example .env`; skill marketplace installs should use a persistent user config:

```bash
mkdir -p ~/.deepppt
cp /path/to/installed/deepppt/.env.example ~/.deepppt/.env
```

PPT Master reads the current process environment first, then the first `.env` found in this order: current working directory, skill directory (e.g. `~/.agents/skills/deepppt/.env`), clone repo root, `~/.deepppt/.env`.

**A) AI generation** — `image_gen.py`. Set `IMAGE_BACKEND` plus the provider's `*_API_KEY` (`OPENAI_API_KEY`, `GEMINI_API_KEY`, etc.), and the pipeline calls it automatically. Run `python3 skills/deepppt/scripts/image_gen.py --list-backends` for the full backend list. `gpt-image-2` is currently the best default.

**B) Web image search** — `image_search.py`. **Zero-config works**, but configure `PEXELS_API_KEY` / `PIXABAY_API_KEY` (both free) for higher-quality results. Without keys, search uses Openverse / Wikimedia Commons only; this is useful as a fallback, but image quality can be uneven because many results are ordinary user uploads. With keys, the default provider chain also appends Pexels / Pixabay, which materially improves modern stock photography, people, workplace, lifestyle, and illustration coverage. The default is quality-first: CC0, Public Domain, Pexels / Pixabay no-attribution licenses, CC BY, and CC BY-SA are considered together, and Executor adds a small inline credit whenever the selected image requires attribution. Use `--strict-no-attribution` only when a slide cannot tolerate any credit line. For high-impact covers, product shots, portraits, and branded scenes, prefer this order: user-provided high-resolution assets / AI generation > web search with Pexels / Pixabay keys > zero-config web search.

> Full reference: [`image-generator.md`](./skills/deepppt/references/image-generator.md) (AI) · [`image-searcher.md`](./skills/deepppt/references/image-searcher.md) (web).

---

## Documentation

| | Document | Description |
|---|----------|-------------|
| 📘 | [Getting Started](./docs/getting-started.md) | First deck in 3 steps, plus how to use templates, live preview, animations, narration, voice cloning (**new users start here**) |
| 🆚 | [Why PPT Master](./docs/why-deepppt.md) | How it compares to Gamma, Copilot, and other AI tools |
| 🪟 | [Windows Installation](./docs/windows-installation.md) | Step-by-step setup guide for Windows users |
| 📖 | [SKILL.md](./skills/deepppt/SKILL.md) | Core workflow and rules |
| 📐 | [Canvas Formats](./skills/deepppt/references/canvas-formats.md) | PPT 16:9, Xiaohongshu, WeChat, and 10+ formats |
| 🛠️ | [Scripts & Tools](./skills/deepppt/scripts/README.md) | All scripts and commands |
| 💼 | [Examples](./examples/README.md) | All example projects |
| 🏗️ | [Technical Design](./docs/technical-design.md) | Architecture, design philosophy, why SVG |
| ❓ | [FAQ](./docs/faq.md) | Model selection, cost, layout troubleshooting, custom templates |

---

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for how to get involved.

## License

[MIT](LICENSE)

## Acknowledgments

[SVG Repo](https://www.svgrepo.com/) · [Tabler Icons](https://github.com/tabler/tabler-icons) · [Simple Icons](https://github.com/simple-icons/simple-icons) · [Phosphor Icons](https://github.com/phosphor-icons/core) · [Robin Williams](https://en.wikipedia.org/wiki/Robin_Williams_(author)) (CRAP principles)

---

MIT licensed.
