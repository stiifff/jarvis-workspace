<div align="center">

# Jarvis Workspace

**A local web cockpit for orchestrating several AI coding agents in parallel.**

![License](https://img.shields.io/badge/license-MIT-22c55e.svg)
![Python](https://img.shields.io/badge/python-3.11+-3b82f6.svg)
![Backend](https://img.shields.io/badge/backend-FastAPI-009688.svg)
![Frontend](https://img.shields.io/badge/frontend-vanilla%20JS-eab308.svg)
![BYOK](https://img.shields.io/badge/model-BYOK-8b5cf6.svg)

</div>

Jarvis Workspace runs on `localhost:3000` and lets you launch, watch, and coordinate
**multiple agent CLIs** (Claude Code, Codex, Qwen Code, opencode…) at the same time on
your projects — each in its own terminal, all on the same branch. It's **BYOK**
(*bring your own keys*): the agents run on **your own accounts/subscriptions** for each
CLI — Jarvis orchestrates them, it doesn't pay for the inference on your behalf.

> Built for Windows + WSL (Ubuntu), but it runs on any Linux. Architecture details:
> [`CLAUDE.md`](CLAUDE.md).

## ✨ What it does

- **Terminal grid** — multiple persistent tmux sessions in a grid, each with its own
  agent; resizable, with history and live status.
- **Multi-CLI swarm** — claude / codex / qwen / opencode in parallel, coordinated on a
  single branch (no worktrees, no merge hell).
- **Agent coordination** — an *Agents Live* layer (`.jarvis/LIVE.md`: who is touching
  which file + ownership), a 1-to-1 *Mailbox* between agents, and a pre-commit ownership
  lock that keeps two agents from stepping on each other.
- **Multi-account + auto-rotation** — link several accounts per CLI and switch the
  active one instantly; when one hits its rate limit, Jarvis auto-rotates to a healthy
  account of the same CLI (configurable, on by default).
- **Right-hand dock** — Web Preview (with dev-server auto-detection and a remote
  browser), Monaco editor, tasks (kanban), and **per-agent** diff review.
- **Voice (PTT)** — push-to-talk dictation (STT via local Whisper) + TTS.
- **Natural-language orchestrator** — a chat that interprets commands and builds
  multi-agent workflows (optional; uses the Anthropic API).

## Requirements

- **Linux / WSL (Ubuntu).**
- **Python 3.11+** (tested on 3.14), **tmux**, and **git**.
- The **CLIs** you want to use (Claude Code, Codex, etc.) installed and logged in with
  **your** accounts (auth is linked from the UI).
- *(Optional)* an **Anthropic API key** — only for the orchestrator chat and the Web
  Builder; the rest of the product doesn't need it.

## Installation

### Option A — Docker (recommended)

A complete, ready-to-run image (ships with tmux, git, ffmpeg, Node + Claude Code CLI,
Whisper, and Chromium). You install nothing on the host beyond Docker.

```bash
cp .env.example .env          # set PROYECTOS_DIR (where your code lives)
docker compose up -d --build  # first run is slow (downloads torch + chromium)
docker compose logs -f        # grab the ACCESS TOKEN it prints on startup
```

Open `http://localhost:3000` and paste the token the first time (it's stored in an
httpOnly cookie). State (DB + token) is created automatically on first boot. With Docker
Desktop the port mapping works even on WSL (it handles the port forwarding).

> The Docker setup is statically verified (base image, torch wheel, and dependencies
> confirmed); a full end-to-end `docker build` on a machine with Docker is still pending.
> If a system step fails, the sensitive spots are commented in the `Dockerfile`.

### Option B — Native (Linux / WSL)

```bash
# 1. Virtualenv + dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r plotspace/requirements.txt

# 2. Chromium for the Web Preview remote browser (Playwright)
playwright install chromium

# 3. (optional) API key for the orchestrator
echo 'ANTHROPIC_API_KEY=sk-ant-...' > plotspace/.env   # never committed

# 4. Enable the anti-secret guard (pre-commit that blocks token/.env/keys)
bash scripts/setup-hooks.sh

# 5. Run
python3 -m uvicorn plotspace.main:app --host 0.0.0.0 --port 3000 --loop asyncio
```

It prints an **access token** (also written to `data/jarvis_token.txt`). From your phone
or another machine on the LAN: `http://<IP>:3000/login?token=<token>`.

`bin/jarvis` (optional) registers the current folder as a project and opens the
workspace: `sudo ln -sf "$(pwd)/bin/jarvis" /usr/local/bin/jarvis && jarvis .`

## How to use it

1. **Create a project** — from the **+** in the left strip (or `Ctrl+T`): pick the path
   to your code, a workspace template, and which CLIs to launch.
2. **Work with the agents** — each CLI opens in its own terminal in the grid. You hand
   them tasks, watch them work live, and they coordinate with each other by reading the
   project's `CLAUDE.md` + the *Agents Live* layer.
3. **Link your accounts (BYOK)** — ⚙ → **Accounts** → link: the login opens in a terminal
   and saves itself. You can keep several accounts per CLI and switch between them; when
   one hits a rate limit, Jarvis auto-rotates to a healthy one (or you switch manually in
   one click).
4. **Use the dock** (▣ or `Ctrl+P`) — Web Preview (auto-detects your dev server), editor,
   tasks, and per-agent change review.
5. **Handy shortcuts** — `Ctrl+B` strip · `Ctrl+\` quick terminal · `Ctrl+Shift+K` swarm
   control tower · `Ctrl+J` Jarvis chat.

## How it works (in short)

- **Backend:** Python + FastAPI + uvicorn. **Frontend:** vanilla HTML/CSS/JS (no
  frameworks, no build). **DB:** SQLite. **Terminals:** tmux + ptyprocess.
- Agents work **directly on `main`**; the anti-conflict defense is the coordination layer
  (Agents Live + Mailbox + ownership lock).
- Full architecture map and rules: [`CLAUDE.md`](CLAUDE.md).

## Tests

```bash
source venv/bin/activate
python -m pytest                                  # backend (config in pytest.ini)
node frontend/sections/**/__tests__/*.test.js     # frontend (pure test suites)
```

The remote-browser smoke test is skipped if Chromium can't launch (missing system
libraries, e.g. `libnss3`).

## Maintenance

To clean up accumulated state (purges `task_events`, marks zombie workflows as `error`,
kills orphaned tmux sessions, prunes old logs, `VACUUM`):

```bash
curl -X POST -b "jarvis_token=$(cat data/jarvis_token.txt)" \
  http://localhost:3000/api/workspace/mantenimiento
```

## Contributing

PRs are welcome! See [`CONTRIBUTING.md`](CONTRIBUTING.md) for details. In short: **fork**,
work on a branch, and open a **pull request** describing the change. Before you send it:

- Run the tests (backend + frontend) and make sure they pass.
- Follow the style of the surrounding code (no frameworks on the front end, `var(--ob-*)`
  tokens in CSS, synchronous `subprocess.run` for tmux/git).
- Enable the hooks (`bash scripts/setup-hooks.sh`) — they block secrets from being
  committed by accident.

## Notes

- **No build step, no npm.** The front end is vanilla, served by FastAPI from `/static`.
  When you change front-end code, bump the `?v=N` on the `<script>`/`<link>`.
- **Port 3000 is reserved** for Jarvis — dev servers go to a different range
  (5000-5999 / 8081-8999).
- `data/` (DB, token, account secrets) and `plotspace/.env` are **gitignored**; the
  pre-commit hook blocks the commit if it detects a token, a `.env`, a private key, or an
  API-key pattern.

## License

[MIT](LICENSE) © 2026 Jarvis Workspace contributors
