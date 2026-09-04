<div align="center">

# Jarvis Workspace

A local cockpit for running several AI coding agents in parallel.

[![License](https://img.shields.io/badge/license-MIT-22c55e.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.11+-3b82f6.svg)
![BYOK](https://img.shields.io/badge/model-BYOK-8b5cf6.svg)

<img src="docs/images/workspace.png" alt="Jarvis Workspace — empty project" width="920">

<img src="docs/images/new-terminal.png" alt="Launch a swarm of terminals" width="920">

</div>

Open `localhost:3000`. Each agent (Claude Code, Codex, OpenCode, Qwen, Antigravity, Grok Build, or a shell) gets its own terminal. They share one branch. You bring the accounts — Jarvis only orchestrates.

**Linux** is the native path. **Windows** runs the engine inside [WSL2](docs/install/windows.md) (or Docker). **macOS** follows [the same native install](docs/install/macos.md).

## Features

- **Terminal grid** — persistent tmux sessions, live status, layouts
- **Coordination** — who owns which file, 1-to-1 mailbox, pre-commit lock
- **Accounts** — several logins per CLI, auto-rotate on rate limit
- **Dock** — web preview, editor, tasks, per-agent diff review
- **Voice** — push-to-talk (optional Groq or local STT)

## Install

[Linux](docs/install/linux.md) · [macOS](docs/install/macos.md) · [Windows](docs/install/windows.md)

```bash
git clone https://github.com/stiifff/jarvis-workspace
cd jarvis-workspace
sudo apt install -y python3 python3-venv python3-pip tmux git curl   # Debian/Ubuntu/WSL

python3 -m venv venv && source venv/bin/activate
pip install -r plotspace/requirements.txt
pip install -e .
jarvis
```

Paste the access token printed on first boot (`data/jarvis_token.txt`) at `http://localhost:3000`.

You need **Python 3.11+**, **tmux**, **git**, and the CLIs you actually want to run. Clone **inside the Linux filesystem** on WSL (`~/jarvis-workspace`), not `/mnt/c`.

Docker: `cp .env.example .env && docker compose up -d --build` — first build is large; treat it as experimental.

## Use

1. **Ctrl+T** — add a project (path to your code)
2. **Ctrl+\\** — launch terminals (Claude, Codex, Grok, …)
3. **⚙ → Accounts** — link your own CLI logins (BYOK)
4. **Ctrl+P** — dock (preview, editor, review)

Shortcuts: `Ctrl+B` strip · `Ctrl+E` editor · `Ctrl+J` Jarvis chat · `Ctrl+1…9` project.

Port **3000** is Jarvis. Put dev servers on 5000–5999 or 8081–8999.

## Tests

```bash
source venv/bin/activate
python -m pytest
node frontend/sections/**/__tests__/*.test.js
```

Vanilla HTML/CSS/JS, no npm. PRs: [`CONTRIBUTING.md`](CONTRIBUTING.md). Secrets never go in git (`data/`, `.env`).

## License

[MIT](LICENSE) © 2026 Jarvis Workspace contributors
