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
CLI — Jarvis Workspace orchestrates them, it doesn't pay for the inference on your behalf.

> Engine is Linux (**tmux**). On Windows use **WSL2 Ubuntu** or Docker Desktop — see
> [`docs/install/windows.md`](docs/install/windows.md). Architecture details:
> [`CLAUDE.md`](CLAUDE.md).

## ✨ What it does

- **Terminal grid** — multiple persistent tmux sessions in a grid, each with its own
  agent; resizable, with live status.
- **Multi-CLI swarm** — claude / codex / qwen / opencode in parallel, coordinated on a
  single branch (no worktrees, no merge hell).
- **Agent coordination** — an *Agents Live* layer (`.jarvis/LIVE.md`: who is touching
  which file + ownership), a 1-to-1 *Mailbox* between agents, and a pre-commit ownership
  lock that keeps two agents from stepping on each other.
- **Multi-account + auto-rotation** — link several accounts per CLI and switch the
  active one instantly; when one hits its rate limit, Jarvis auto-rotates to a healthy
  account of the same CLI (configurable, on by default).
- **Right-hand dock** — Web Preview (iframe + dev-server auto-detection), Monaco editor,
  tasks (kanban), and **per-agent** diff review.
- **Voice (PTT)** — push-to-talk dictation (STT via Groq or local model) + TTS.
- **Natural-language orchestrator** — optional chat that interprets commands and can
  build multi-agent workflows (needs an Anthropic API key only for that path).

## Requirements

- **Linux**, **WSL2 Ubuntu**, or **macOS** (same native install). Windows users: the
  engine runs *inside* WSL2 or Docker — there is no native Windows `.exe` installer yet.
- **Python 3.11+** (tested on 3.14), **tmux**, and **git**.
- The **CLIs** you want to use (Claude Code, Codex, etc.) installed and logged in with
  **your** accounts (auth is linked from the UI).
- *(Optional)* an **Anthropic API key** — only for the orchestrator chat; the rest of
  the product is BYOK and does not need it.

## Installation

Platform notes: [Linux](docs/install/linux.md) · [macOS](docs/install/macos.md) ·
[Windows (WSL2 / Docker)](docs/install/windows.md).

### Option A — Native (recommended — this is the path that works day to day)

```bash
git clone https://github.com/stiifff/jarvis-workspace
cd jarvis-workspace

# system deps (Debian/Ubuntu/WSL example)
sudo apt install -y python3 python3-venv python3-pip tmux git curl

python3 -m venv venv
source venv/bin/activate
pip install -r plotspace/requirements.txt
pip install -e .                  # provides the `jarvis` command

# optional: anti-secret guard (blocks token/.env/keys from commits)
bash scripts/setup-hooks.sh

# optional: API key only for orchestrator-chat extras
# echo 'ANTHROPIC_API_KEY=sk-ant-...' > plotspace/.env   # never committed

jarvis
# until `pip install -e .` succeeds you can also run:
# python3 -m uvicorn plotspace.main:app --host 0.0.0.0 --port 3000 --loop asyncio
```

It prints an **access token** (also written to `data/jarvis_token.txt`, or under
`JARVIS_DATA_DIR` if set). Open `http://localhost:3000` and paste it once (stored in an
httpOnly cookie). From another machine on the LAN:
`http://<IP>:3000/login?token=<token>` (only if you bound `--host 0.0.0.0`).

**Windows:** do the clone + venv **inside WSL2**, not on `/mnt/c`. Then either open the
URL from your Windows browser or use `scripts/abrir-jarvis-app.bat` /
`scripts/compilar-lanzador-windows.sh`. Full walkthrough:
[`docs/install/windows.md`](docs/install/windows.md).

### Option B — Docker

```bash
cp .env.example .env          # set PROYECTOS_DIR (host folder with your code)
docker compose up -d --build  # first build is slow and large
docker compose logs -f        # grab the ACCESS TOKEN it prints on startup
```

Open `http://localhost:3000` and paste the token. State (DB + token) lands in `./data`.
Inside the container your projects appear under `/proyectos` — use those paths in the UI.
With Docker Desktop, port `3000` is published to Windows as well.

> Compose + Dockerfile are maintained in-repo, but a full end-to-end `docker build` on a
> clean machine is **still pending verification**. Do not treat Docker as the primary
> install path until you've confirmed the image builds on your box. Sensitive steps are
> commented in the `Dockerfile`.

## How to use Jarvis Workspace

1. **Create a project** — from **Nuevo workspace** in the left strip (or `Ctrl+T`): pick
   the path to your code, a workspace template, and which CLIs to launch.
2. **Work with the agents** — each CLI opens in its own terminal in the grid. You hand
   them tasks, watch them work live, and they coordinate by reading the project's
   `CLAUDE.md` + the *Agents Live* layer.
3. **Link your accounts (BYOK)** — ⚙ → **Cuentas** → link: the login opens in a terminal
   and saves itself. You can keep several accounts per CLI and switch between them; when
   one hits a rate limit, Jarvis auto-rotates to a healthy one (or you switch manually in
   one click).
4. **Use the dock** (▣ or `Ctrl+P`) — Web Preview (auto-detects your dev server), editor,
   tasks, and per-agent change review.
5. **Handy shortcuts** — `Ctrl+B` strip · `Ctrl+\` quick terminal · `Ctrl+E` editor ·
   `Ctrl+J` Jarvis chat · `Ctrl+1…9` jump to project N.

## How it works (in short)

- **Backend:** Python + FastAPI + uvicorn. **Frontend:** vanilla HTML/CSS/JS (no
  frameworks, no build). **DB:** SQLite. **Terminals:** tmux (control-mode) + xterm.js.
- Agents work **directly on `main`**; the anti-conflict defense is the coordination layer
  (Agents Live + Mailbox + ownership lock).
- Full architecture map and rules: [`CLAUDE.md`](CLAUDE.md).

## Tests

```bash
source venv/bin/activate
python -m pytest                                  # backend (config in pytest.ini)
node frontend/sections/**/__tests__/*.test.js     # frontend (pure test suites)
```

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
