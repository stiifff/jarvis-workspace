<div align="center">

# Jarvis Workspace

A local cockpit for several AI coding agents, in parallel, on your machine.

[![License](https://img.shields.io/badge/license-MIT-22c55e.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.11+-3b82f6.svg)
![BYOK](https://img.shields.io/badge/model-BYOK-8b5cf6.svg)

</div>

You open a project. Jarvis gives you a grid of live terminals. Claude Code, Codex, OpenCode, Qwen, Antigravity, Grok Build, or a shell — each in its own pane, all on the same branch. You bring the accounts. Jarvis only orchestrates.

**Linux** is native. **Windows** runs the engine in [WSL2](docs/install/windows.md). **macOS** is the [same install as Linux](docs/install/macos.md).

---

### Start here

The empty workspace. One project, nothing running yet. New terminal, talk to Jarvis, or open the editor.

<p align="center">
  <img src="docs/images/workspace.png" alt="Empty Jarvis workspace — What are we building today?" width="920">
</p>

### Launch a swarm

Pick agents, how many, and a layout. Seven Claude Codes, a mix, or one shell. They land in a live grid.

<p align="center">
  <img src="docs/images/new-terminal.png" alt="New terminal — pick Claude, Codex, Grok, layout, launch" width="920">
</p>

### Your accounts, not ours

⚙ → **Accounts**. Several logins per CLI, switch without logging in again. Native sessions (Grok, Claude, …) show up even if you never clicked Connect. Rate-limit? It rotates.

<p align="center">
  <img src="docs/images/accounts.png" alt="Settings → Accounts — Claude, Codex, Antigravity switchboard" width="920">
</p>

### Make it yours

⚙ → **Appearance**. 24 themes, tint, language, scale. The bench at the top is the live workspace.

<p align="center">
  <img src="docs/images/appearance.png" alt="Settings → Appearance — 24 themes, tint, scale" width="920">
</p>

Also in the dock: web preview, editor, tasks, per-agent diff review. Hold your voice key to dictate (Groq’s free Whisper API).

---

## Install

[Linux](docs/install/linux.md) · [macOS](docs/install/macos.md) · [Windows](docs/install/windows.md)

```bash
git clone https://github.com/stiifff/jarvis-workspace
cd jarvis-workspace
sudo apt install -y python3 python3-venv python3-pip tmux git curl   # Debian / Ubuntu / WSL

python3 -m venv venv && source venv/bin/activate
pip install -r plotspace/requirements.txt
pip install -e .
jarvis
```

Paste the first-boot token (`data/jarvis_token.txt`) at `http://localhost:3000`.

Need **Python 3.11+**, **tmux**, **git**, and the CLIs you actually run. On WSL clone **inside Linux** (`~/jarvis-workspace`), not `/mnt/c`.

Docker: `cp .env.example .env && docker compose up -d --build` — large first build, still experimental.

## Use

| | |
|---|---|
| **Ctrl+T** | New project |
| **Ctrl+\\** | New terminals |
| **⚙** | Accounts, appearance, voice |
| **Ctrl+P** | Dock |

Also: `Ctrl+B` strip · `Ctrl+E` editor · `Ctrl+J` Jarvis chat · `Ctrl+1…9` jump to a project. Port **3000** is Jarvis — put dev servers on 5000–5999 or 8081–8999.

## Tests

```bash
source venv/bin/activate
python -m pytest
node frontend/sections/**/__tests__/*.test.js
```

Vanilla HTML/CSS/JS, no npm. PRs: [`CONTRIBUTING.md`](CONTRIBUTING.md). Keep secrets out of git (`data/`, `.env`).

## License

[MIT](LICENSE) © 2026 Jarvis Workspace contributors
