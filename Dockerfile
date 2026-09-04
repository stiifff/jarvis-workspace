# syntax=docker/dockerfile:1

# ─────────────────────────────────────────────────────────────────────────────
# Jarvis Workspace — imagen Docker v1 (COMPLETA y funcional out-of-the-box).
#
# Incluye TODAS las deps de plotspace/requirements.txt, también las pesadas:
# openai-whisper + torch (STT) y playwright + chromium (browser remoto del Web
# Preview). El código las importa en runtime —voice.py/main.py precargan Whisper,
# remote_browser.py importa Playwright— y hoy crashea sin ellas, así que v1 las
# trae todas. Resultado: imagen grande (varios GB) pero que arranca y funciona
# sin pasos manuales.
#   TODO v2: capa opcional liviana (imports lazy + variante sin whisper/torch
#            ni chromium para quien solo quiere orquestar terminales).
# ─────────────────────────────────────────────────────────────────────────────

# Base: el proyecto corre Python 3.14 (host verificado: 3.14.4). python:3.14-slim
# existe en Docker Hub desde el release de 3.14 (oct-2025). Si en tu registro NO
# estuviera disponible, cambiá a `python:3.13-slim` — el código no usa nada
# exclusivo de 3.14 (pero torch/whisper SÍ necesitan wheels para esa versión;
# ver README → "Avisos del build").
FROM python:3.14-slim

# PYTHONUNBUFFERED es crítico acá: el TOKEN DE ACCESO se imprime en el arranque y
# el usuario lo necesita para entrar la primera vez — sin esto puede quedar
# atrapado en el buffer de stdout y no verse en `docker compose logs`.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive \
    # Explícito: la auth de los CLIs (claude/codex/…) y el .gitconfig se escriben
    # bajo $HOME; el volumen del HOME se monta en /root. Sin fijarlo, una herramienta
    # que lea $HOME vacío podría escribir en el cwd y perder la auth al reiniciar.
    HOME=/root \
    # Chromium de Playwright FUERA del HOME: el HOME del contenedor es un volumen
    # persistente (guarda la auth de los CLIs) y al montarlo SOMBREARÍA cualquier
    # browser instalado bajo ~/.cache. En /opt queda horneado en la imagen y el
    # runtime lo encuentra con esta misma variable.
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright

WORKDIR /app

# ─── 1. Deps de sistema (lo NO-chromium) ──────────────────────────────────────
# tmux        → sesiones de terminal persistentes (jarvis_<id>), el corazón del swarm
# git         → los agentes commitean en los repos del usuario
# ffmpeg      → REQUERIDO por Whisper STT: voice.py convierte y decodifica el audio
#               con ffmpeg; sin él, /api/voice devuelve 500
# curl, ca-certificates, gnupg → HTTPS + repo de NodeSource + healthcheck
# iproute2    → `ss` (los agentes chequean qué puertos están libres antes de levantar)
# procps      → ps/pkill que usan los scripts de mantenimiento
# Las libs de SISTEMA de Chromium NO se listan acá a propósito: las instala
# `playwright install --with-deps chromium` (paso 4), que es distro-aware. En
# Debian trixie esos paquetes llevan sufijo t64 (libasound2t64, libatk1.0-0t64,
# libnss3, libnspr4, libatspi2.0-0t64, libcups2t64, libgbm1, libxkbcommon0,
# libpango-1.0-0, libcairo2, libxcomposite1, libxdamage1, libxrandr2, libxfixes3,
# libxext6, libxcb1, libdrm2, libdbus-1-3…) y hardcodearlos rompería el build si
# el set de nombres cambia entre versiones de Debian. Playwright los resuelve solo.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tmux \
        git \
        ffmpeg \
        curl \
        ca-certificates \
        gnupg \
        iproute2 \
        procps \
    && rm -rf /var/lib/apt/lists/*

# ─── 2. Node.js LTS + npm + Claude Code CLI ────────────────────────────────────
# Los agentes corren CLIs de Node. Instalamos Node 22 LTS (NodeSource) y el CLI
# primario (Claude Code) global. El binario global vive en /usr/lib/node_modules
# (NO en el HOME) → sobrevive al volumen del HOME.
# Para AGREGAR otros CLIs (ver README → "Otros CLIs de agente"): sumá un
# `npm i -g ...` acá. Ejemplos:
#     npm i -g @openai/codex        # Codex
#     npm i -g @qwen-code/qwen-code # Qwen Code
#     npm i -g opencode-ai          # opencode
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g @anthropic-ai/claude-code \
    && npm cache clean --force

# ─── 3. Dependencias Python ────────────────────────────────────────────────────
# Se copia SOLO requirements.txt primero: así esta capa pesada se cachea y un
# cambio de código (paso 5) no la invalida.
COPY plotspace/requirements.txt /app/plotspace/requirements.txt

# torch primero desde el índice CPU de PyTorch: el `pip install torch` por defecto
# en Linux baja la build con CUDA (varios GB de libs de GPU INÚTILES en un
# contenedor sin GPU). Pre-instalar la build +cpu hace que openai-whisper la
# encuentre ya satisfecha y no arrastre la de CUDA. Si el índice CPU no tuviera
# la wheel para esta versión de Python, el `||` cae al índice default (build más
# pesada, pero el build NO falla).
RUN python -m pip install --upgrade pip \
    && ( pip install "torch" --index-url https://download.pytorch.org/whl/cpu \
         || pip install "torch" ) \
    && pip install -r /app/plotspace/requirements.txt

# ─── 4. Chromium para el browser remoto (Playwright) ───────────────────────────
# --with-deps instala el binario de chromium + TODAS sus libs de sistema de forma
# distro-aware (resuelve el lío de los paquetes t64 de Debian trixie). Se instala
# en PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright (fuera del HOME-volumen).
# `apt-get update` propio: las capas anteriores borraron /var/lib/apt/lists, y
# --with-deps hace `apt-get install` (necesita listas frescas para resolver).
RUN apt-get update \
    && playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

# ─── 5. Código de la app ───────────────────────────────────────────────────────
COPY . /app

# data/ es un volumen en runtime, PERO init_db() corre al IMPORTAR backend.main
# (antes del lifespan) y sqlite3 NO crea el directorio del archivo .db → si no
# existe, el import revienta con "unable to open database file". Garantizarlo:
RUN mkdir -p /app/data

# ─── 6. Git: identidad por defecto + safe.directory ────────────────────────────
# Los agentes commitean en los repos del usuario (montados en /proyectos). Sin
# identidad, `git commit` falla con "Author identity unknown". safe.directory='*'
# evita el "detected dubious ownership" que tira git cuando el bind-mount viene
# con un uid distinto al del contenedor. El usuario puede pisar la identidad por
# env/CLI dentro de su terminal. (Se escribe en /root/.gitconfig; en el primer
# arranque Docker copia /root al volumen del HOME, así que persiste.)
RUN git config --global user.name "Jarvis Agent" \
    && git config --global user.email "agent@jarvis.local" \
    && git config --global --add safe.directory '*'

EXPOSE 3000

# CMD FIJO con --loop asyncio: uvloop (el default de uvicorn[standard]) sufre un
# stall periódico del event loop en este stack, visible como cortes en el eco de
# las terminales. asyncio puro lo elimina — es requisito DURO del proyecto, NO
# cambiar a uvloop ni quitar el flag.
CMD ["python", "-m", "uvicorn", "plotspace.main:app", \
     "--host", "0.0.0.0", "--port", "3000", "--loop", "asyncio"]
