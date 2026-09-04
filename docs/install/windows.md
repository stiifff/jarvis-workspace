# Install on Windows

Jarvis Workspace is a **Linux** app (Python + uvicorn + **tmux**). On Windows
the engine runs inside **WSL2 Ubuntu** (recommended) or **Docker Desktop**.
There is no native Windows installer and no GitHub Releases `.exe` yet — the old
MSI / PowerShell-terminal app was removed.

You bring your own agent CLIs (Claude Code, Codex, etc.) and link them in
⚙ → **Cuentas** (BYOK). Jarvis orchestrates them; it does not ship or pay for
those models.

---

## Path A — WSL2 (recommended)

### 1. Install WSL2 + Ubuntu

In PowerShell (Admin):

```powershell
wsl --install
```

Reboot when Windows asks. Open **Ubuntu** from the Start menu and finish the
first-boot user setup.

### 2. Clone inside the Linux filesystem

**Important:** the clone must live under the Linux home (e.g. `~/…`), **not**
under `/mnt/c/...`. tmux + heavy I/O on NTFS is painful.

```bash
git clone https://github.com/stiifff/jarvis-workspace ~/jarvis-workspace
cd ~/jarvis-workspace

# The Windows .bat launcher looks for ~/jarvis — make a symlink once:
ln -s ~/jarvis-workspace ~/jarvis
```

### 3. System packages + Python venv

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip tmux git curl

python3 -m venv venv
source venv/bin/activate
pip install -r plotspace/requirements.txt

# Optional: install the `jarvis` CLI entry point
pip install -e .

# Optional: anti-secret git hooks
bash scripts/setup-hooks.sh
```

### 4. First start (from inside WSL)

```bash
source ~/jarvis/venv/bin/activate
jarvis
# until the CLI is installed:
# python3 -m uvicorn plotspace.main:app --host 0.0.0.0 --port 3000 --loop asyncio
```

On first boot the server prints an **access token** and also writes it to
`data/jarvis_token.txt` (under the repo, unless you set `JARVIS_DATA_DIR`).

### 5. Open it from Windows

Pick one:

- **Double-click launcher:** copy `scripts/abrir-jarvis-app.bat` to your Desktop.
  It warms WSL, starts the server if needed (`~/jarvis/scripts/reiniciar-server.sh`),
  and opens Chrome in app mode at `http://localhost:3000`.
- **Compiled shell (optional):** from WSL, run
  `bash scripts/compilar-lanzador-windows.sh`. That builds a thin WebView2
  window (`Jarvis.exe`) — not a native engine, just a desktop chrome around the
  same Linux server — and drops a shortcut on your Desktop.

Then open `http://localhost:3000`, paste the token from the WSL logs or
`data/jarvis_token.txt`, and continue.

> Health checks should use `http://127.0.0.1:3000` (the name `localhost` often
> resolves IPv6-first; WSL may only be listening on IPv4). The browser URL can
> stay `http://localhost:3000`.

### 6. Link your CLI accounts (BYOK)

In the UI: ⚙ → **Cuentas** → link Claude / Codex / etc. with **your** logins.
No API key is required for the main BYOK flow. An optional `ANTHROPIC_API_KEY`
in `plotspace/.env` is only for the orchestrator chat extras.

---

## Path B — Docker Desktop

Works if you prefer not to manage a venv inside WSL. You still need
[Docker Desktop](https://www.docker.com/products/docker-desktop/) with the WSL2
backend enabled.

```powershell
git clone https://github.com/stiifff/jarvis-workspace
cd jarvis-workspace
copy .env.example .env
```

Edit `.env` and set `PROYECTOS_DIR` to a **Windows path Docker can mount**, for
example:

```env
PROYECTOS_DIR=C:\Users\you\Projects
```

Inside the container that mount appears as `/proyectos` — when you create a
project in the UI, use container paths like `/proyectos/mi-app`.

```powershell
docker compose up -d --build
docker compose logs -f
```

Grab the access token from the logs (also persisted under `./data/`), then open
`http://localhost:3000`.

**Honesty check:** the first `docker compose build` is **slow and large**
(base image + Python deps; historically also heavy ML/browser layers in the
Dockerfile). The compose file and image layout are maintained in-repo, but a
full end-to-end `docker build` on a clean machine is **not claimed as verified**
here — if a system step fails, the sensitive spots are commented in the
`Dockerfile`.

---

## Where things live

| | WSL2 path | Docker |
|---|---|---|
| Code / engine | `~/jarvis-workspace` (symlink `~/jarvis`) | image + bind mounts |
| App data (DB, token, CLI account secrets) | `<repo>/data` by default, or `JARVIS_DATA_DIR` (e.g. `~/.local/share/jarvis`) | `./data` → `/app/data` |
| Your projects | anywhere under the Linux FS (prefer `~/proyectos`, not `/mnt/c`) | host folder from `PROYECTOS_DIR` → `/proyectos` |

## What you still need

- **Your agent CLIs** installed and logged in (Jarvis does not redistribute them).
- **tmux** and **git** (Path A installs them via apt; Path B ships them in the image).
- Optional: `GROQ_API_KEY` in `plotspace/.env` / `.env` if you want cloud STT for
  push-to-talk dictation.
