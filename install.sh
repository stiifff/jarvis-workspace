#!/usr/bin/env bash
# Jarvis Workspace — one-command install for Linux and macOS.
#
#   curl -fsSL https://raw.githubusercontent.com/celsiusm/jarvis-workspace/main/install.sh | bash
#
# Or, inside a clone:  ./install.sh
#
# Windows: use install.ps1 (it runs this script inside WSL).
#
# Installs the FULL app (plotspace/requirements.txt): terminals, voice, TTS,
# preview, Mobile Studio, the lot. It does not ship third-party agent CLIs
# (Claude, Codex, Grok, …) — those you install and link in ⚙ → Accounts.
set -euo pipefail

REPO_URL="${JARVIS_REPO_URL:-https://github.com/celsiusm/jarvis-workspace.git}"
DEST_DEFAULT="$HOME/jarvis-workspace"
MIN_PY="3.11"

DRY_RUN=0
NO_START=0
DEST="${JARVIS_DIR:-}"

usage() {
  cat <<'EOF'
install.sh — install Jarvis Workspace (Linux / macOS)

Usage:
  curl -fsSL https://raw.githubusercontent.com/celsiusm/jarvis-workspace/main/install.sh | bash
  ./install.sh
  ./install.sh --dir ~/jarvis-workspace --no-start

Windows: in PowerShell
  irm https://raw.githubusercontent.com/celsiusm/jarvis-workspace/main/install.ps1 | iex

Options:
  --dir PATH     Clone / use this directory (default: ~/jarvis-workspace)
  --no-start     Install only; don't launch the server
  --dry-run      Print the plan, change nothing
  -h, --help     This text

Needs Python 3.11+, tmux, git, curl, ffmpeg. On Windows the engine runs in WSL2.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir) DEST="${2:-}"; shift 2 ;;
    --no-start) NO_START=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

log() { printf '%s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '[dry-run] %s\n' "$*"
    return 0
  fi
  "$@"
}

en_wsl() {
  grep -qi microsoft /proc/version 2>/dev/null || grep -qi microsoft /proc/sys/kernel/osrelease 2>/dev/null
}

# ── Where to put the tree ────────────────────────────────────────────────
ROOT=""
_self="${BASH_SOURCE[0]:-}"
if [[ -n "$_self" && "$_self" != "bash" && "$_self" != "/dev/stdin" && -f "$_self" ]]; then
  _dir="$(cd "$(dirname "$_self")" && pwd)"
  if [[ -d "$_dir/plotspace" && -f "$_dir/plotspace/main.py" ]]; then
    ROOT="$_dir"
  fi
fi
if [[ -z "$ROOT" && -d ./plotspace && -f ./plotspace/main.py ]]; then
  ROOT="$(pwd)"
fi

if [[ -n "$ROOT" ]]; then
  DEST="$ROOT"
else
  DEST="${DEST:-$DEST_DEFAULT}"
fi

log "Jarvis Workspace → $DEST"

# ── OS packages ──────────────────────────────────────────────────────────
instalar_paquetes() {
  if command -v apt-get >/dev/null 2>&1; then
    local pkgs=(python3 python3-venv python3-pip tmux git curl ffmpeg ca-certificates)
    if [[ "$DRY_RUN" -eq 1 ]]; then
      log "[dry-run] apt-get install -y ${pkgs[*]}"
      return 0
    fi
    if command -v sudo >/dev/null 2>&1; then
      sudo apt-get update -y
      sudo apt-get install -y "${pkgs[@]}"
      sudo apt-get install -y python3.12 python3.12-venv 2>/dev/null || \
        sudo apt-get install -y python3.11 python3.11-venv 2>/dev/null || true
    else
      apt-get update -y
      apt-get install -y "${pkgs[@]}"
    fi
  elif command -v dnf >/dev/null 2>&1; then
    local pkgs=(python3 python3-pip python3-virtualenv tmux git curl ffmpeg)
    if [[ "$DRY_RUN" -eq 1 ]]; then
      log "[dry-run] dnf install -y ${pkgs[*]}"
      return 0
    fi
    if command -v sudo >/dev/null 2>&1; then sudo dnf install -y "${pkgs[@]}"; else dnf install -y "${pkgs[@]}"; fi
  elif command -v pacman >/dev/null 2>&1; then
    local pkgs=(python python-pip tmux git curl ffmpeg)
    if [[ "$DRY_RUN" -eq 1 ]]; then
      log "[dry-run] pacman -Sy --needed --noconfirm ${pkgs[*]}"
      return 0
    fi
    if command -v sudo >/dev/null 2>&1; then sudo pacman -Sy --needed --noconfirm "${pkgs[@]}"; else pacman -Sy --needed --noconfirm "${pkgs[@]}"; fi
  elif command -v brew >/dev/null 2>&1; then
    if [[ "$DRY_RUN" -eq 1 ]]; then
      log "[dry-run] brew install python@3.12 tmux git ffmpeg"
      return 0
    fi
    brew install python@3.12 tmux git ffmpeg
  else
    die "no package manager found (apt, dnf, pacman, brew). Install Python ${MIN_PY}+, tmux, git, curl, ffmpeg and re-run."
  fi
}

log "Installing system packages (python, tmux, git, curl, ffmpeg)…"
instalar_paquetes

# ── Python 3.11+ ─────────────────────────────────────────────────────────
elegir_python() {
  local c ver
  for c in python3.12 python3.11 python3; do
    command -v "$c" >/dev/null 2>&1 || continue
    ver="$("$c" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || true)"
    [[ -z "$ver" ]] && continue
    if "$c" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 11) else 1)' 2>/dev/null; then
      printf '%s\n' "$c"
      return 0
    fi
  done
  return 1
}

if [[ "$DRY_RUN" -eq 1 ]]; then
  log "[dry-run] pick python >= ${MIN_PY}"
  PYTHON="python3"
else
  PYTHON="$(elegir_python)" || die "Python ${MIN_PY}+ is required. Install it and re-run."
  log "Python: $PYTHON ($("$PYTHON" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))'))"
fi

# ── Clone if this is curl | bash ─────────────────────────────────────────
if [[ -d "$DEST/plotspace" && -f "$DEST/plotspace/main.py" ]]; then
  log "Using existing tree at $DEST"
else
  command -v git >/dev/null 2>&1 || die "git is required to clone the repo"
  if [[ -d "$DEST" && -n "$(ls -A "$DEST" 2>/dev/null || true)" ]]; then
    die "$DEST exists and is not a Jarvis checkout. Pass --dir or move it aside."
  fi
  log "Cloning $REPO_URL → $DEST"
  run git clone --depth 1 "$REPO_URL" "$DEST"
fi

# ── venv + FULL requirements ─────────────────────────────────────────────
log "Creating venv and installing plotspace/requirements.txt (full app)…"
if [[ "$DRY_RUN" -eq 1 ]]; then
  log "[dry-run] $PYTHON -m venv $DEST/venv"
  log "[dry-run] pip install -U pip"
  log "[dry-run] pip install -r plotspace/requirements.txt"
  log "[dry-run] pip install -e ."
else
  "$PYTHON" -m venv "$DEST/venv"
  # shellcheck disable=SC1091
  source "$DEST/venv/bin/activate"
  pip install -U pip
  pip install -r "$DEST/plotspace/requirements.txt"
  pip install -e "$DEST"
fi

# ── ~/.local/bin/jarvis → venv entry point (NOT repo bin/jarvis) ─────────
WRAP="$HOME/.local/bin/jarvis"
log "Linking $WRAP → $DEST/venv/bin/jarvis"
if [[ "$DRY_RUN" -eq 1 ]]; then
  log "[dry-run] write wrapper $WRAP"
else
  mkdir -p "$HOME/.local/bin"
  cat > "$WRAP" <<EOF
#!/usr/bin/env bash
# Installed by Jarvis Workspace install.sh — runs the app (plotspace.cli).
exec "$DEST/venv/bin/jarvis" "\$@"
EOF
  chmod +x "$WRAP"
fi

if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
  _line='export PATH="$HOME/.local/bin:$PATH"  # jarvis-workspace'
  for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
    if [[ "$DRY_RUN" -eq 1 ]]; then
      log "[dry-run] ensure PATH in $rc"
      continue
    fi
    if [[ -f "$rc" ]] && grep -q 'jarvis-workspace' "$rc" 2>/dev/null; then
      continue
    fi
    if [[ -f "$rc" ]] || [[ "$rc" == "$HOME/.bashrc" ]]; then
      printf '\n%s\n' "$_line" >> "$rc"
      log "Added ~/.local/bin to PATH in $rc (open a new terminal, or: source $rc)"
    fi
  done
  export PATH="$HOME/.local/bin:$PATH"
fi

# ── Launch ───────────────────────────────────────────────────────────────
if [[ "$NO_START" -eq 1 ]]; then
  log "Installed. Start with:  jarvis"
  log "Then open http://127.0.0.1:3000"
  exit 0
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  log "[dry-run] start server and open http://127.0.0.1:3000"
  exit 0
fi

mkdir -p "$DEST/data"
if curl -s -o /dev/null --max-time 2 http://127.0.0.1:3000/api/health; then
  log "Already running at http://127.0.0.1:3000"
else
  log "Starting Jarvis…"
  if en_wsl && [[ -x "$DEST/scripts/reiniciar-server.sh" ]]; then
    # 0.0.0.0 so the Windows browser can reach the engine.
    bash "$DEST/scripts/reiniciar-server.sh"
  else
    # setsid: survive the shell that launched the installer (curl | bash).
    if command -v setsid >/dev/null 2>&1; then
      setsid nohup "$DEST/venv/bin/jarvis" --sin-browser >>"$DEST/data/uvicorn.log" 2>&1 </dev/null &
    else
      nohup "$DEST/venv/bin/jarvis" --sin-browser >>"$DEST/data/uvicorn.log" 2>&1 </dev/null &
    fi
    for _ in $(seq 1 90); do
      curl -s -o /dev/null --max-time 2 http://127.0.0.1:3000/api/health && break
      sleep 1
    done
  fi
fi

if curl -s -o /dev/null --max-time 2 http://127.0.0.1:3000/api/health; then
  log "Open http://127.0.0.1:3000"
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open http://127.0.0.1:3000 >/dev/null 2>&1 || true
  elif command -v open >/dev/null 2>&1; then
    open http://127.0.0.1:3000 >/dev/null 2>&1 || true
  fi
else
  log "Installed, but the server did not answer yet. Start it with:  jarvis"
  log "Logs: $DEST/data/uvicorn.log"
fi

log ""
log "Next: ⚙ → Accounts — install your agent CLIs (Claude, Codex, Grok, …) and link them."
log "Voice: the first-run dialog asks for a free Groq key (or local STT works without one)."
exit 0
