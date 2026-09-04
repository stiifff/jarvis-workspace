# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Qué es este proyecto
Dashboard web local para orquestar múltiples agentes de IA (Claude Code, Codex, Gemini, etc.) trabajando en paralelo sobre proyectos de código. Corre en localhost:3000. El orquestador central corre con la SUSCRIPCIÓN de Claude (`claude -p` headless, `core/orq_cli.py`) para interpretar órdenes en lenguaje natural y coordinar agentes vía tmux sessions — cero tokens de API pagos. **Todos los agentes trabajan directo sobre la rama principal del proyecto** (en este repo, `master`; no hay worktrees, ramas feature ni merge): coordinan leyendo el `CLAUDE.md` del proyecto y editando archivos disjuntos; la defensa anti-conflicto es Agents Live (`.jarvis/LIVE.md`).

> **Este archivo se carga en CADA sesión de CADA agente — mantenelo de ALTURA.** Acá van reglas accionables + el mapa de arquitectura. El "por qué" histórico y el detalle fino (selectores, clases CSS, changelogs con fecha) NO van acá: viven en la memoria compartida `.jarvis/memory/` (los `[[punteros]]` apuntan ahí) y en el `AGENTS.md` de cada sección. Antes de engordar este archivo, preguntate si la info no calza mejor en una memoria.

## Forma de trabajo (pedido del usuario, 2026-06-10)
Ejecutá los pedidos **DIRECTAMENTE**: sin spec, sin design doc, sin plan en
`docs/` (NO usar brainstorming/writing-plans de superpowers salvo que el usuario
lo pida explícitamente esa vez — esta instrucción tiene prioridad sobre esas
skills). Los archivos de spec acumulan basura en el repo y consumen contexto.
El diseño y los trade-offs los resolvés vos de la mejor manera; preguntar al
usuario está bien SOLO cuando la decisión es genuinamente suya (comportamiento
visible, elección de producto). La calidad no se negocia: TDD, correr TODA la
suite y verificar antes de dar por terminado siguen siendo obligatorios.

## Commits (al terminar tu tarea — pedido del usuario, 2026-06-16)
Cuando terminás tu tarea, **commiteá SOLO TUS archivos** (los que tocaste para
esa tarea), explícitos: `git add <ruta1> <ruta2> && git commit -m "..."`.
**NUNCA `git add -A` ni `git commit -am`**: todos los agentes comparten el mismo
árbol de trabajo sobre `main`, así que `git status` muestra los cambios de TODOS
mezclados — barrerlos con `-A`/`-am` te lleva puesto el trabajo a medio hacer de
otros agentes que todavía no terminaron. Si al commitear ves archivos que no son
tuyos, dejalos afuera (son de otro, que lo commitee él).
- **Mensaje en Conventional Commits** (`feat:` / `fix:` / `refactor:`, con scope):
  el popup de "Actualización disponible" arma las novedades a partir del subject
  del commit (`plotspace/routers/system.py`). Evitá `chore:` / `wip` para cosas que
  el usuario debería ver listadas (esos tipos se filtran como ruido). Sin commit,
  el popup cae al texto genérico "Mejoras y arreglos varios".
- **NO hace falta (ni corresponde) `git push`**: el server auto-pushea `master`
  a origin al detectar tu commit (`fe_watch`, flag `AUTO_PUSH`) — así el backup
  en GitHub queda al día sin que nadie se acuerde.
- **Antes de editar un archivo que otro agente pudo tocar**, mirá su historial:
  `git log --oneline -- <archivo>` y `git show <commit>`. Si hay un commit reciente,
  entendé qué se hizo y por qué, y construí ENCIMA sin deshacerlo. Es la capa de
  "pasado" que complementa a Agents Live (`.jarvis/LIVE.md` = quién toca qué AHORA).
- **Commiteá TEMPRANO y CHICO — es tu defensa, no un riesgo.** En este árbol
  compartido lo único seguro es HEAD: el trabajo sin commitear puede ser barrido
  por un `add -A`/stash ajeno. Una unidad que compila y pasa tests se commitea YA
  (hay un paracaídas — snapshots del WIP cada 30 min en `refs/jarvis/wip/`, se
  recupera con `git show <ref>:<ruta>` — pero no es excusa para acumular).
- **La forma FÁCIL de commitear bien:** `python3 scripts/commit_propio.py -m "..."`
  — stagea solo TUS archivos (según LIVE.md) bajo un lock que evita la carrera
  stage↔commit con otros agentes. Rutas extra como argumentos.
- **Enforcement duro (candado de propiedad):** esta regla NO es solo disciplina —
  el hook `.githooks/pre-commit` corre `scripts/guard_propiedad.py`, que identifica
  al agente por su sesión tmux (`jarvis_<id>`) y BLOQUEA el commit si entre lo staged
  hay un archivo cuyo 🔒 dueño (o 🔖 reserva vigente) en `LIVE.md` es OTRO agente
  (salvo permiso «→ OK» suyo). Si te bloquea: stageá solo lo tuyo. Falso positivo
  legítimo (tenés OK del dueño): eximí SOLO ese archivo con
  `GUARD_OK="ruta.py" git commit -m "..."` — **NUNCA `--no-verify`** (apaga también
  el escáner de secretos). Falla abierto (sin tmux/LIVE.md).
- **¿Vas a editar un archivo clave sin dueño? RESERVALO antes** (la cola se forma
  antes del choque): `- @Vos -> @jarvis: RESERVA <archivo> — qué vas a hacer` en el
  MAILBOX (lease 15 min; ver el protocolo LIVE).

## Comandos de desarrollo

```bash
# Arrancar el servidor (desde ~/jarvis)
source venv/bin/activate
# --loop asyncio es OBLIGATORIO: uvloop (el default de uvicorn) sufre un stall
# periódico de ~400ms del event loop en este entorno (WSL2 + Py3.14) que se ve
# como cortes en el eco del tipeo de las terminales. Con asyncio puro: sin stall.
python3 -m uvicorn plotspace.main:app --host 0.0.0.0 --port 3000 --loop asyncio

# Instalar dependencias
pip install -r plotspace/requirements.txt

# Verificar cambios de BACKEND sin reiniciar (los AGENTES NO REINICIAN el server;
# la actualización la aplica el usuario con el banner "Actualizar ahora"):
python -m pytest plotspace/tests/ -q        # pytest importa el código de DISCO
python -c "import plotspace.main"          # smoke de arranque (lo mismo que el canary)
# scripts/reiniciar-server.sh es HERRAMIENTA DEL USUARIO (o de Jarvis mismo), no
# de agentes. Y NUNCA pkill -f uvicorn + relanzar.

# Frontend: NO hace falta reiniciar, pero SÍ bumpear el ?v=N del <script src>/<link> en el HTML.

# Tests (correr TODOS antes de dar por bueno un cambio; las suites Node son ~27 y crecen)
for t in $(find frontend -path '*__tests__*' -name '*.test.js' | sort); do node "$t" || break; done
python -m pytest plotspace/tests/ -q
```

No hay build step ni linter. Tests: suites Node puras (assert nativo, patrón UMD `_pure`) + pytest en `plotspace/tests/`. El frontend es HTML/CSS/JS vanilla servido directamente por FastAPI como archivos estáticos. Default bind `127.0.0.1`.

## Stack fijo — no cambiar sin consultar
- **Backend**: Python + FastAPI + uvicorn
- **Frontend**: HTML + CSS + JS vanilla (sin frameworks, sin npm, sin node); xterm.js 5.3 vendoreado en `frontend/vendor/xterm/`
- **DB**: SQLite (`data/jarvis.db`, WAL); **12 tablas** (las que crea `init_db`): `projects`, `terminals`, `workflows`, `task_events`, `tasks` (kanban), `project_skills`, `project_notes`, `orquestador_historial`, `orquestador_uso`, `cli_accounts`, `mailbox_msgs`, `memoria_uso`. Las del Web Builder (`wb_*`, `web_pages`, `wb_chats`, `wb_chat_mensajes`) ya no se crean: si están en tu DB son restos de la sección eliminada.
- **Terminales**: tmux sessions persistentes (`jarvis_{terminal_id}`); attach WS por **tmux control-mode** con xterm.js como único emulador (ver sección tmux)
- **Orquestador**: motor **SUSCRIPCIÓN** (`ORQUESTADOR_MOTOR=suscripcion`, default): `claude -p` headless con la cuenta OAuth activa (`core/orq_cli.py` — `--safe-mode`, stream-json, `--json-schema`, tools de SOLO lectura Read/Glob/Grep con cwd=proyecto). Modelo default `sonnet` (`ORQUESTADOR_MODEL` lo pisa). `ORQUESTADOR_MOTOR=api` = vía de escape con `ANTHROPIC_API_KEY` + haiku. Además: chat multi-turno (historial real), bloque `[Mapa del proyecto]` (`core/repo_map.py`), action `enviar_prompt` a terminales vivas, reuso de libres en pasos (`terminal_id`) y **auto-intervención** en TASK_BLOCKED/ERROR. Ver [[orquestador-cerebro-v2]]
- **STT**: `STT_MOTOR=groq` (ACTIVO en este box) manda el dictado a whisper-large-v3-turbo en los LPUs de Groq (`core/stt_groq.py`; cero CPU/RAM local, ~1s, key en `plotspace/.env`, fallback automático al motor local si falla — ver [[stt-groq-motor]]). Motor local: parakeet-tdt-0.6b-v3 int8 (onnx-asr; `STT_MOTOR=whisper` vuelve a faster-whisper `small`), carga on-demand (el PTT manda `/api/voice/prewarm` al apretar — no-op con Groq) y se descarga sola tras ocio — NUNCA residente de gusto, ver [[whisper-on-demand-ram]] · [[deepwork-audio-transcripcion]]. **El modelo vive en un PROCESO worker** (`core/stt_proc.py`; `STT_WORKER=off` = in-proc viejo): onnxruntime retiene el GIL 5-20s al crear la sesión y cargarlo dentro del server congelaba el event loop entero — era el freeze de scroll post-"Actualizar ahora", ver [[stt-worker-gil-freeze]] · **TTS**: edge-tts `es-PY-TaniaNeural`
- **Entorno**: Windows + WSL (Ubuntu); sin file picker nativo; rutas como `/home/user/proyectos/mi-app`

## Arquitectura

> **La app nativa de Windows (Jarvis Workspace) y el motor Rust se ELIMINARON el
> 2026-08-06** por decisión del usuario: el workspace volvió a ser 100% Linux
> (Python + uvicorn + tmux, el modelo de siempre). No reintroduzcas `desktop/`,
> motores alternativos de terminal ni nada del circuito de builds del shell —
> si necesitás el detalle histórico está en git y en las memorias con
> `estado: lapida` (categoría `desktop`).

### Estructura de carpetas
- `plotspace/` — `main.py` (entrypoint), `core/` (dominio: database, events, auth, ssrf, mantenimiento, control_mode, agent_live, agent_watch, dev_detect, fe_watch, mailbox, puertos, pane_capture, logs; swarm: swarm_deck, swarm_watchdog, sentinel; cuentas: cli_accounts, cli_login, cuenta_watch; memoria: memoria_lint, memoria_recall, memoria_lecciones, memoria_categorias, memoria_global, memoria_endurecimiento), `routers/` (**15**, uno por sección), `tests/` (pytest + scripts `__main__`). Ver `plotspace/AGENTS.md`.
- `frontend/` — `index.html` (home, en `/`), `shell/` (workspace.html + workspace.js, el armazón), `shared/` (tokens.css + base.css + ui.js con `icon()/toast()/confirmar()` + i18n), `sections/<x>/` (cada sección con su .js + .css), `vendor/`. Ver `frontend/AGENTS.md` y el `AGENTS.md` de cada sección.
- Secciones: `home`, `terminals`, `panel` (dock + franja), `preview`, `settings`, `orchestrator`, `editor`, `tasks`, `review`, `mobile-preview`, `memory`.
- `data/` — estado local (gitignored). `.workspace/` es artefacto per-proyecto (gitignored): `STATE.md` (lo escribe Jarvis cada 10s, lo leen los agentes) + logs por terminal en `.workspace/logs/terminal_{id}_{nombre}.log` (útil para debuggear terminales).
- **Serving:** todo `frontend/` se monta en `/static`; el HTML referencia `/static/sections/<x>/...`.

### UI del workspace ("Panel Único", desde 2026-06)
Detalle visual completo: [[arquitectura-panel-unico]] · [[rediseno-violeta-2026-06]]. Acá, lo estable + las reglas:
- **Franja de proyectos de 185px** (`#jw-strip`, Ctrl+B la oculta) con el botón **Nuevo workspace** `.sb-new-ghost` (el viejo `#jw-strip-new` ya no existe). **Barra de 40px** (`#jw-bar`): izquierda chip de versión + semáforo; centro breadcrumb; derecha `#terminals-reset-btn` · `#btn-quick-terminal` · separador · ⚙ `#jw-gear` · ▣ `#jw-dock-toggle`. (El toggle de sonido vive en ⚙→Voz, ya no en la barra; el menú de localhost vivos `#jw-localhosts-btn` se mudó a la toolbar del Web Preview — salió de esta barra 2026-07-09.)
- **24 temas** (`frontend/shared/themes.js`, default `violeta`; incluye 2 CLAROS — `papel`, `alba`) aplicados vía `html[data-theme]`, overrides en `tokens.css`, + **filtro de Tonalidad** (matiz/saturación/profundidad — overrides OKLCH inline vía `JarvisThemes.setTinte`, persiste en `jarvis.tinte`). **REGLA DE ORO: NUNCA hardcodear hex — siempre `var(--ob-*)`** (con temas claros, un color oscuro fijo = texto ilegible). Logos de CLIs: `window.cliLogo(tipo, size)` (`shared/icons/`). Ver [[configuracion-rediseno-2026-07]].
- **Escala de la app** (⚙→Apariencia→escala, 70–150%): `shared/escala.js` pone `zoom` en `<html>` y escala TODO (incluida la letra de las terminales, que refitean y avisan a tmux). **REGLA: las unidades de viewport NO se ajustan por zoom** — todo alto/ancho de pantalla va por `var(--jw-vh, 100vh)` / `var(--jw-vw, 100vw)` (definidas en `tokens.css`), nunca `vh`/`vw` pelados; y lo que deba adaptarse al ancho útil se hace con *container queries*, no con media queries. Ver [[escala-app-zoom-viewport]].
- **i18n ES⇆EN** (`shared/i18n.js` + `i18n-dict.js`, selector en ⚙→Apariencia): los textos nuevos del frontend entran al diccionario. Ver [[i18n-idioma]].
- **Dock derecho único** (`window.JarvisDock`, `sections/panel/panel.js`): pestañas preview · jarvis · editor · tasks · review · mobile (solo proyectos Expo; detecta el Metro que levantó el agente, NO lo arranca). Default 320px / MIN 300, splitter, maximizar solo editor/preview, badges de no-visto, persistencia por proyecto. El render usa `hidden` — **NUNCA animar width** (regla xterm).
- **Cards de terminal** (`workspace.js`): chrome **"Glass Pro"** (píldora faux-glass — gradiente translúcido + bisel + brillo diagonal en `::before`; NUNCA `backdrop-filter` sobre el canvas de xterm). Logo de CLI con **halo de estado** (idle sin halo · thinking/watching verde · error rojo — hookeado a `:has(.t-status-*)`, reemplaza al pip). ✕ elimina, maximizar por card. `.t-name` lleva el **título vivo** del pane (qué hace el agente); el **nombre real** de la terminal vive en el `title` (hover) del logo, no en un renglón aparte — respetá `t-name-live`/`dataset.nombre`. **El logo NUNCA se oculta al achicarse** (identidad + estado); en cards angostas se suelta primero el grip y después el nombre (`t-narrow` <250px · `t-xnarrow` <150px). (El botón/modal Historial + `Ctrl+Shift+H` + el endpoint `/history` se removieron 2026-07-05.)
- **El mouse APUNTA la terminal** (`shell/voice-target.js` + `shell/foco-hover.js`, cableados en `workspace.js`): tener el cursor sobre una card ya la hace destino del dictado, y tras un dwell de 200ms le pasa también el foco del teclado (escribís y mandás Enter sin clickear). Guardas que NO hay que romper: el destino de la voz se **congela** al empezar a grabar (`_activeVoiceSession`), el foco nunca se le roba a un campo de texto en uso, y hay gracia de 800ms mientras tipeás en otra terminal. Ver [[voz-destino-por-hover]] · [[foco-teclado-por-hover]].
- **Layout de terminales** (`sections/terminals/terminal-layout.js`): modos **mosaico** (default) ⇄ **libre/vertical** (drag + resize por 4 esquinas), mínimo 280×160px por card, fuente fija 13px. El canvas xterm SIEMPRE sigue a su card (único freeze bajo 60×40px); quien cambia tamaños dispara `TerminalLayout.relayoutAll()` / `JarvisEditor.relayout()`. Ver [[terminales-modo-libre]].
- **Web Preview** (`sections/preview/`): pestañas múltiples (máx 8, persistidas por proyecto). Todo va en iframe, y la embebibilidad se chequea server-side (`GET /api/orchestrator/preview/probe?url=`) para caer a la pantalla "el sitio bloqueó el embebido" con "Abrir en pestaña". **Buscar = navegar al buscador REAL** (`urlBusqueda`): texto suelto → Google, `yt …` → YouTube, y los accesos directos del estado vacío llevan a sus homes. El **menú de "Localhost activos"** (`#jw-localhosts-btn`, `dev-servers.js`) vive en su toolbar (`.wp-bar`): botón con contador que abre el popover de dev servers vivos (se oculta con 0). El SERP casero (`serp.html`, DuckDuckGo/YouTube scrapeados) y el **browser remoto** (Chromium server-side + screencast CDP) se ELIMINARON el 2026-07-26 — no los reintroduzcas. Ver [[preview-pestanas]] · [[preview-busqueda-serp]].
- **Auto-detección de dev servers** (`core/dev_detect.py`, poller 2s): raspa los panes tmux Y escanea puertos LISTEN (atribución por proceso), con TCP-check anti falso-positivo; WS `dev_server_detectado`/`dev_server_caido`; excluye :3000 (Jarvis) y :8081 (Metro). Alimenta el menú `#jw-localhosts-btn` (en la toolbar del Web Preview) — **ojo: su ✕ MATA el proceso del puerto** ([[preview-pill-cierra-server]]). Ver [[dev-server-autodetect]].
- **Conciencia ambiental del swarm**: `core/agent_watch.py` (poller 1s) detecta "trabajaba y se quedó quieto" sin keywords → WS `agente_termino`/`agente_espera`/`agente_trabajando` (sonidos, toggle `sonidoTareas`) + **aura** en la card no activa (`sections/terminals/terminal-aura.js`). Ver [[agent-watch-sonidos]] · [[aura-notificacion-cards]].
- **Configuración** (⚙, overlay full-screen): voz-PTT / atajos / apariencia (tema + idioma) / cuentas / skills&plugins / memoria / workflows.
- **Creación unificada:** el **Nuevo workspace** de la franja o **Ctrl+T** abre el modal "Agregar proyecto" (modos Crear/Abrir + explorador de carpetas + grid de CLIs + distribución, **12 cupos** `MAX_TERMINALES`; lógica pura en `sections/panel/launcher-state.js`). **Ctrl+\\** abre el picker de terminal rápida (**6 opciones**: claude/codex/opencode/qwen/antigravity/shell). Ver [[launcher-templates-y-grid]].
- **Atajos:** Ctrl+B franja · Ctrl+T nuevo proyecto · Ctrl+\\ terminal rápida · Ctrl+P dock (palette de archivo si el editor está a la vista; Ctrl+Shift+P palette de comandos) · Ctrl+E editor · Ctrl+J jarvis · Ctrl+K buscar proyecto · Ctrl+1…9 saltar al proyecto N · Esc cierra/des-maximiza. PTT de voz configurable (default: mantener AltLeft).
- **Editor standalone:** `GET /editor?project=N` (`#jw-dock-external`, solo en la pestaña editor).

### Orquestación del swarm — subsistemas
- **Watchdog del swarm** (`core/swarm_watchdog`, cada 20s, umbral 180s, `WATCHDOG=off`): red de seguridad que rescata `TASK_*` perdidos re-capturando el scrollback completo y emite `paso_estancado`/`paso_rescatado`; se apoya en el `iniciado_ts` que sella `orchestrator.py`. (La **UI del Command Deck** —panel Ctrl+Shift+K + `routers/deck.py` + `core/swarm_deck.py`— se removió 2026-07-06: no se usaba; la conciencia ambiental del swarm cubre el "cuándo terminó/espera". Ver [[command-deck-watchdog]] · [[features-que-no-usa]].)
- **Sentinel** (`core/sentinel.py`, cada 2s, `SENTINEL=off`): cierre de paso por archivo `.jarvis/signals/terminal_<id>.json` (`{estado, motivo, memorias_usadas}`, one-shot) — fuente **PRIMARIA** del cierre; el parseo de `TASK_*` del pane queda como fallback. El `motivo` de un BLOCKED/ERROR se **persiste** (columna en `task_events` + paso del workflow + broadcasts): es la materia prima de las lecciones. Ver [[sentinel-cierre-estructurado]].
- **Memoria del enjambre — capas activas** (detalle: [[sistema-memoria-v2]]): `core/memoria_recall.py` inyecta las memorias relevantes al prompt de cada paso Y al planning del orquestador (señales deterministas cero API: rutas, tags, **BM25** sobre cuerpos, categoría, uso histórico) · `core/memoria_lint.py` + `GET /api/projects/{id}/memory/salud` (links rotos, citas muertas, huérfanas, contrato de admisión, choques lápida-vs-vigente, cuarentena, candidatas a guard, salud por categoría) · `core/memoria_categorias.py` (10 cuadros canónicos; INDEX agrupado) · `core/memoria_lecciones.py` (patrón wb_gusto: destila motivos → ≤20 reglas en `lecciones-del-enjambre.md`, inyectadas SIEMPRE entre markers `JARVIS_LECCIONES_*`) · `core/memoria_global.py` (semilla de entorno para proyectos nuevos) · `core/memoria_endurecimiento.py` (reincidencia de lecciones → candidatas a guard determinista). Estados del frontmatter: `vigente|obsoleta|lapida|archivo`; el protocolo trae la jerarquía de autoridad (código > CLAUDE.md > lápida > más-nueva > verificá). El janitor (30 min) regenera INDEX, destila lecciones y evalúa reincidencias.
- **Cuentas de CLIs** (`core/cli_accounts.py` + `cli_login.py` + `cuenta_watch.py`, ⚙→Cuentas): varias cuentas por CLI (**claude/codex/grok/qwen/opencode/antigravity**) y switch al instante sin re-loguear. Secretos 0600 en `data/cli-accounts/<id>/` (nunca en DB ni git); Codex usa homes aislados (`CODEX_HOME` + symlink) para no gatillar la revocación de OpenAI. **Auto-rotación** (`AUTO_ROTACION`, default ON): agent_watch detecta la firma de rate-limit en el pane y rota solo a la próxima cuenta sana (WS `cuenta_rotada`/`limite_sin_cuenta`, cooldown 10 min); el switch manual convive. Ver [[cuentas-codex-oauth-rotacion]] · [[auto-rotacion-cuentas]].
- **Identidad de coordinación:** los nombres de terminal son ÚNICOS por proyecto (`resolver_nombre_unico`, terminals.py) — el mailbox 1-a-1 y los dueños de Agents Live dependen de eso. Ver [[nombres-de-terminal-unicos]].

### Otros módulos backend
- `core/pane_capture.py` — captura COMPARTIDA de panes tmux con cache TTL 0.8s (120 líneas); deduplica el `tmux capture-pane` de agent_watch/agent_live/dev_detect. El monitor de keywords de `terminals.py` queda APARTE a propósito (no tocar su captura).
- `core/logs.py` — audit trail del swarm en JSON-lines (`data/jarvis.log`, rota a 5MB). `core/mantenimiento.py` — janitor: purga `.workspace/logs` cada 30 min + `task_events` viejos en boot.
- Routers sin sección propia en el frontend: `voice.py` (STT vía proceso worker `core/stt_proc.py` — serializado, una inferencia a la vez — + TTS edge-tts + `/api/voice/translate`), `plugins.py` (plugins/skills por proyecto, tabla `project_skills`), `live.py` (snapshot de Agents Live), `projects_files.py` (backend del editor Monaco).

### Cómo se trabaja de verdad acá (y qué NO se usa)

**El camino real: el usuario abre terminales y les pega la tarea.** Todo lo que
protege al enjambre cuelga de la TERMINAL, no de ningún workflow, así que
funciona siempre: provenance por hook, territorio, commit por hunk, avisos de
colisión y el CLI `jv` ([[provenance-por-hook]] · [[territorio-por-nombre]] ·
[[cli-jv-enjambre]]).

**El motor de workflows existe, está sano y NO se usa.** Cero corridas en la
vida de esta DB. Si algún día se llama, el flujo es:
```
Browser → POST /api/orchestrator/chat  (vía OPCIONAL, hoy sin uso)
  → el orquestador genera JSON {message, actions, workflow?}
  → ejecutar_workflow() crea terminales + sesiones tmux
  → cada paso arranca con su territorio reclamado y recibe su tarea como PASTE
  → cierre del paso: sentinel-file (primario) o keyword TASK_* (fallback)
  → paso final: REVIEWER (arranca cuando ninguno sigue en marcha, aunque haya
    pasos bloqueados) → workflow_done por WS
```
No construyas encima de esta vía asumiendo que corre: no corre. Lo que sí corre
es todo lo de arriba.

### WebSocket events (emitidos por el broadcaster de `plotspace/core/events.py`)
`hola` (handshake, trae `boot_id`) · `task_event` · `workflow_update` · `orquestador_mensaje` · `workflow_done` (único con TTS) · `agente_termino/espera/trabajando` + `cuenta_rotada`/`limite_sin_cuenta` (agent_watch) · `dev_server_detectado/caido` · `paso_estancado/rescatado` · `conflicto_archivo`/`live_update`/`permiso_*` (Agents Live) · `mailbox_aviso` · `cuentas_update`/`cuenta_agregada`/`cuenta_watch_timeout` · `tasks_update` · `wb_pulido` · `frontend_actualizado`/`codigo_commiteado` (fe_watch). La lista crece — grep `broadcaster.broadcast(`. Cualquier módulo backend puede suscribirse a TODO con `broadcaster.escuchar(cb)`.

### Startup (`plotspace/main.py`, lifespan)
Whisper se precarga en executor → `reconciliar_sesiones_tmux()` → `reanudar_workflows()` → purga de task_events → pollers asyncio: STATE.md 10s · mailbox · dev_detect 2s · agent_watch 1s · agent_live 2s · fe_watch 2s · watchdog 20s · sentinel 2s · purga de logs 30 min.

### Updater in-app y versionado automático (`routers/system.py` + `sections/panel/updater.js`)
- **`hay_update` = hay COMMIT nuevo desde el boot** (HEAD se movió). Ediciones sin commitear NO lo prenden. Banner "Actualizar ahora" abajo de la franja; **NO se oculta por agentes trabajando** (`agentes_trabajando` de `/version` es informativo, scope = proyecto Jarvis). Ver [[updater-gate-scope]].
- **Quién actualiza: EL USUARIO** (click) o Jarvis mismo — los agentes verifican con pytest + import smoke y NO reinician el server. Ver [[reinicio-server-sin-robar-terminal]].
- **Versionado automático** (`VERSION`, formato `x.x.xx`): patch +1 por update; si TODOS los commits nuevos son `fix:` → hotfix (4º segmento). **Canary:** `/api/system/restart` importa `backend.main` en un subproceso ANTES del `os.execv`; si el código nuevo no arranca responde 409 (modal con traceback) y el server viejo sigue intacto; con canary OK → bump + re-exec in-place (mismo PID).
- **fe_watch** (`core/fe_watch.py`): el browser se recarga solo al reiniciar el server (cambia el `boot_id`) o al editar `frontend/**` (reload retenido mientras haya agentes trabajando); un commit nuevo emite `codigo_commiteado` → re-chequeo del banner. Si el server quedó en uvloop aparece el banner "Optimizar tipeo" (reinicia con `--loop asyncio`).

### Circular import: `orchestrator.py` ↔ `terminals.py`
El monitor de keywords en `terminals.py` necesita llamar a `orchestrator.py` y viceversa. **Solución**: lazy imports dentro del cuerpo de la función:
```python
from plotspace.routers.orchestrator import procesar_task_event_interno
```

## Reglas críticas de implementación

**subprocess.run vs asyncio para tmux/git:**
`asyncio.create_subprocess_exec` con `tmux new-session -d` cuelga indefinidamente (hereda FDs y `communicate()` no retorna). **Usar siempre `subprocess.run` síncrono para los comandos tmux y git de control.** Única excepción: `_capture_tmux_output()` en `terminals.py` (polling largo, cede el event loop).

**Keyword detection (falsos positivos):**
El monitor distingue el TASK_DONE que Jarvis envió como instrucción del TASK_DONE real del agente con 3 capas: `_ANSI_RE` (limpia ANSI) → `_KW_SOLO_RE` (`^[^a-zA-Z]*TASK_DONE[^a-zA-Z]*$`, sin letras alrededor) → baseline al inicio del monitor (ignora el historial previo del pane). El sentinel-file es hoy la fuente primaria del cierre; esto sigue como fallback. Ver [[protocolo-task-done]].

**TTS:** mutex `ttsActivo` en `workspace.js`; voz solo en 3 momentos (bienvenida, workflow aceptado, workflow terminado).

**Cache busting:** al cambiar JS o CSS, incrementar `?v=N` en los `<script src>` y `<link rel>` del HTML.

**Paths:** usar siempre `os.path.join()`. La `ANTHROPIC_API_KEY` se excluye del entorno PTY de las terminales para que los agentes usen sus propias credenciales.

## Sistema de workflows (vía OPCIONAL — hoy sin uso)

> Esta sección describe una vía que **no se está usando**: cero workflows en la
> vida de esta DB, y su única puerta de entrada es el chat del orquestador, que
> el usuario no abre. Está sana y testeada de punta a punta por si algún día se
> quiere; no es el flujo normal y no hace falta leerla para trabajar acá.

El orquestador genera este JSON cuando detecta una tarea compleja:
```json
{
  "message": "texto confirmación",
  "actions": [{"type": "none"}],
  "workflow": {
    "nombre": "Nombre del workflow",
    "objetivo": "descripción",
    "pasos": [
      {
        "agente": "Claude Code #1",
        "ia_type": "claude",
        "rol": "builder",
        "tarea": "instrucciones...",
        "depende_de": null,
        "archivos": ["src/x.js"]
      }
    ]
  }
}
```
`rol`: `"scout"` = paso 0 opcional que solo explora y deja memorias; `"builder"` = default. `depende_de: null` = arranca ya (el paralelismo es implícito). `archivos` = propiedad exclusiva del paso (se inyecta al prompt del agente). El engine suma a cada tarea la `instruccion_cierre` del sentinel y agrega un paso **Reviewer** al final de todo workflow (corre `git diff`, arregla menores y puede frenar el cierre con TASK_BLOCKED).

**Coordinación:** `TASK_DONE` → avanza | `TASK_BLOCKED` → pausa y avisa | `TASK_ERROR` → intenta reasignar el paso a otro agente libre; si no hay, pausa. El **Reviewer** arranca cuando ningún otro paso sigue en marcha — terminados, no necesariamente exitosos: un workflow que termina mal es justo el que más necesita que alguien mire el diff (antes exigía `done` de todos y un solo bloqueado lo dejaba colgado para siempre).

**Al completar:** NO hay merge ni auto-commit del engine — commitean los agentes/Reviewer; el orquestador avisa (`workflow_done`) y lanza el preview si el proyecto tiene frontend.

**Guard contra terminales duplicadas:** con `workflow` presente, las actions `spawn_terminal` se ignoran (`ejecutar_workflow()` crea sus propias terminales).

## tmux / motor de terminales

- Sesión por terminal: `jarvis_{terminal_id}`. Crear: `subprocess.run(['tmux','new-session','-d',...])` + `mouse on`, `focus-events off`, `window-size latest`, `status off` (y `CODEX_HOME` de la cuenta activa si es Codex).
- **Motor de terminales: tmux, ÚNICO** (desde 2026-08-06, se fue con la app de Windows): **tmux control-mode** con **xterm.js como único emulador**. La selección vive SOLO en `terminal_backend.backend()` — hoy devuelve siempre `TmuxBackend`; la indirección queda como costura de tests (`set_backend`) y cualquier gate deriva de ahí ([[motor-seleccion-un-solo-punto]]). Ver [[motor-un-emulador]]. Las sesiones SOBREVIVEN al reinicio del server (tmux es de otro proceso). (La oferta de reanudar —cierre WS 4409— y el subsistema de shells elegibles se ELIMINARON el 2026-08-08: solo aplicaban a los motores efímeros de la era Windows.)
- ✕ de la card = único punto de eliminación en la UI: `DELETE /api/terminals/{id}` → `teardown_terminal()` (kill tmux + `activa=0`), reusado por el orquestador (`close_terminal`/`close_all`) y el borrado de proyecto. El "desconectar sin matar" sigue interno para el cambio de proyecto.
- **QA con browser: SIEMPRE `?qa=1`** (modo observador read-only que no roba ni redimensiona el attach del usuario).

## Navegación entre proyectos

Sin recargar la página: desconectar los WS de terminales → `history.pushState` → `cargarProyecto()`. Al cambiar de proyecto se notifica `onProjectChanged(projectId)` a JarvisEditor, TerminalLayout, JarvisTasks, JarvisMemory, JarvisReview y JarvisDock (este último restaura el estado/pestaña persistidos del proyecto destino).

## Candado anti-fuga de secretos

API keys / tokens (Anthropic, MCPs, cualquier proveedor) JAMÁS van al repo. `scripts/scan_secretos.py` (stdlib pura) detecta formatos de proveedores **y los valores reales** de los secretos locales (token, `.env`, snapshots de `data/cli-accounts/`); lo corren los hooks versionados de `.githooks/`: pre-commit (staged) y pre-push (TODO el rango saliente — caza también lo commiteado con `--no-verify`). Activación post-clone: `bash scripts/setup-hooks.sh`. NUNCA esquivarlos con secretos reales. En los tests, los secretos falsos se arman por concatenación (`'sk-ant-' + ...`) para no auto-dispararlos. Ver [[candado-anti-fuga-secretos]].

## Variables de entorno

`plotspace/.env` — `ANTHROPIC_API_KEY` (nunca commitear este archivo). Flags (default entre paréntesis):
- **Swarm:** `WATCHDOG` (on) · `SENTINEL` (on) · `AUTO_ROTACION` (on) · `MAILBOX_ENTREGA_TERMINAL` (off) · `ORQUESTADOR_MOTOR` (`suscripcion` — el chat orquestador corre con claude -p y la cuenta OAuth activa, $0 de API; `api` = vía de escape con key) · `ORQUESTADOR_MODEL` (`sonnet` en suscripción / `claude-haiku-4-5` en api) · `ORQ_AUTO_INTERVENCION` (on — ante TASK_BLOCKED/ERROR sin salida el orquestador se llama solo y re-instruye; 1 vez por paso, tope 6/h; solo en motor suscripción) · `ORQ_CLI_TIMEOUT` (240 s de pared por llamada del orquestador) · `MEMORIA_LECCIONES` (on — destilador de lecciones; `MEMORIA_LECCIONES_MODEL` `claude-haiku-4-5` · `MEMORIA_LECCIONES_UMBRAL` 6) · `MEMORIA_CUARENTENA_DIAS` (60 — memoria vigente sin refresco ni uso → cuarentena en la salud)
- **Terminales:** `TERMINALES_ARRANQUE` (`shell` — al crear una terminal de IA el pane nace como shell de WSL a la vista y el CLI se tipea corto (`claude`) al aparecer el prompt; `limpio` = el CLI arranca como programa del pane, sin verse nada. Workflows, reanudaciones y qwen SIEMPRE van en limpio — ver [[arranque-visible-terminales]])
- **Voz:** `STT_WORKER` (`on` — el modelo STT carga y corre en un PROCESO worker con nice(5), `core/stt_proc.py`; `off` = in-proc viejo, que congela el event loop 5-20s por el GIL de onnxruntime al crear la sesión — ver [[stt-worker-gil-freeze]]) · `STT_MOTOR` (`parakeet` default de código; en este box va `groq` = whisper-large-v3-turbo remoto en Groq, cero CPU local, fallback a parakeet — requiere `GROQ_API_KEY`; `whisper` = vía de escape) · `GROQ_API_KEY` (key del free tier de Groq — SOLO en `plotspace/.env`, jamás al repo) · `GROQ_STT_MODEL` (`whisper-large-v3-turbo`; `whisper-large-v3` = más calidad, más lento) · `WHISPER_MODEL` (`small` — NO `turbo`: 3,2 GB de RAM y ~48s por dictado en esta CPU) · `WHISPER_COMPUTE` (`float32` — int8 de CTranslate2 es MÁS lento en esta CPU sin VNNI; el int8 de onnx/parakeet NO sufre eso) · `WHISPER_PRELOAD` (`off`; `on` = precarga residente en startup como antes) · `WHISPER_IDLE_UNLOAD` (`600` s de ocio antes de descargar el modelo/matar el worker — aplica al motor activo; `0`/`off` no descarga)
- **Infra:** `JARVIS_ALLOWED_HOSTS` · `JARVIS_HOST` / `JARVIS_PORT` · `AUTO_PUSH` (on — fe_watch pushea `master` a origin al detectar commits; es el backup automático, NO pushees a mano)

<!-- JARVIS_SKILLS_START -->
## INSTRUCCIÓN OBLIGATORIA

Antes de responder cualquier pregunta sobre tu configuración, plugins activos, skills, o estado del proyecto:
1. Leer este archivo CLAUDE.md completo
2. Basar tu respuesta ÚNICAMENTE en lo que dice este archivo
3. NO usar memoria de conversaciones anteriores para esto

## Skills y plugins activos del proyecto

### 🔌 Plugins activos

- **ui-ux-pro-max**
- **superpowers**
- **static-analysis** — Static analysis toolkit with CodeQL, Semgrep, and SARIF parsing for security vulnerability detection
- **frontend-design** — Frontend design skill for UI/UX implementation
- **expo**
- **context7**

_Estado verificado al: 2026-08-08 16:05:01_

### 📋 Skills del proyecto

#### qa-browser-jarvis

Skill qa-browser-jarvis — ver `.claude/skills/qa-browser-jarvis.md` (cómo verificar en browser + correr los tests)

<!-- JARVIS_SKILLS_END -->

<!-- JARVIS_MEMORY_START -->
## 🧠 Memoria compartida del proyecto (Jarvis)

Este proyecto tiene una memoria compartida entre TODOS los agentes en
`.jarvis/memory/`. **Antes de empezar cualquier tarea**: buscá en
`.jarvis/memory/INDEX.md` las memorias que tocan tu tarea y abrilas. NO
leas el INDEX entero (pesa ~7K tokens y crece): GREPEALO por tus temas —
`grep -i "terminal\|xterm" .jarvis/memory/INDEX.md` — o leé solo la
sección de tu categoría (está agrupado; cada línea trae título, #tags y
fecha). Leerlo completo vale solo para una tarea transversal.

Cuando descubras algo que otro agente debería saber (decisión de
arquitectura, gotcha, convención, bug recurrente, cómo se corre algo),
**guardalo inmediatamente**:

1. Creá `.jarvis/memory/<slug-en-kebab-case>.md` con este formato exacto:

   ```markdown
   ---
   titulo: Título corto y específico (SIN fecha — no es una bitácora)
   tags: [tema1, tema2]
   categoria: <una de la lista de abajo>
   resumen: el hecho en UNA línea — es lo que el recall inyecta al prompt de los demás
   creado: YYYY-MM-DD
   actualizado: YYYY-MM-DD
   autor: tu nombre de agente
   estado: vigente
   ---

   Contenido conciso. Vinculá memorias relacionadas con [[slug-de-otra]].
   ```

   CATEGORÍAS (elegí UNA — es el cuadro temático donde vive la memoria):
   `terminales` (Terminales & tmux) · `ui` (UI · Workspace) · `swarm` (Backend & Swarm) · `diseno` (Diseño & Craft) · `preview` (Web Preview & Radio) · `cuentas` (Cuentas & CLIs) · `voz` (Voz & Audio) · `desktop` (Desktop) · `entorno` (Entorno · WSL & Git) · `producto` (Producto & Roadmap). Si dudás, Jarvis la infiere por los tags;
   una memoria que no cae en ninguna queda marcada `sin-clasificar` en la salud.

2. El INDEX (`.jarvis/memory/INDEX.md`) lo regenera Jarvis solo, AGRUPADO por
   categoría y enriquecido — no lo edites a mano.

REGLAS DE ORO (el pre-commit las hace cumplir — guard_memoria bloquea
frontmatter incompleto, informes de 150+ líneas y títulos con fecha):
- **Una memoria = UN hecho accionable** (~10-60 líneas). Un informe gigante
  ahoga el contexto de quien lo abre: destilá la conclusión y punto.
- **RECONCILIÁ antes de crear**: buscá en el INDEX si ya existe una memoria
  del tema. Si existe, ACTUALIZÁ ESA (sumá tu hallazgo, bumpeá `actualizado:`)
  — dos memorias del mismo tema confunden más que ninguna. Crear una nueva es
  la opción SOLO cuando el hecho es genuinamente nuevo.
- **Si un feature/código se eliminó**, NO borres su memoria: marcá
  `estado: lapida` y decí qué lo reemplaza (evita que alguien lo
  reintroduzca). Memoria vieja que no podés verificar: `estado: obsoleta`.
- **Linkeá SOLO slugs de esta carpeta** — nada de memorias personales de tu
  CLI (esos links nacen rotos para el resto del enjambre).
- **Escribí una lección** (`tags: [leccion]`) cuando un error —tuyo o ajeno—
  se pueda prevenir con una regla corta: qué pasó, por qué, cómo evitarlo.
- Las memorias son del PROYECTO, no tuyas: escribí para que cualquier agente
  futuro entienda sin contexto previo.

JERARQUÍA DE AUTORIDAD (cuando dos fuentes chocan, resolvé en este orden):
1. El **código actual** manda sobre cualquier memoria.
2. El **CLAUDE.md/AGENTS.md** manda sobre las memorias.
3. Una **lápida** (`estado: lapida`) manda sobre una vigente en su tema.
4. La **más actualizada** manda sobre la más vieja.
5. Si sigue ambiguo: **verificá contra el código — no adivines.**
Y si una memoria **te mintió** (describe algo que ya no es así), corregirla o
marcarla `estado: obsoleta` es PARTE de tu tarea — el choque que esquivás se
lo come el próximo agente.

CIERRE DE TAREA (con o sin workflow) — al terminar CUALQUIER tarea, señalá tu
cierre; es la telemetría con la que esta memoria aprende (qué sirvió, qué
falló). Ejecutá:

    TID=${JARVIS_TERMINAL_ID:-$(tmux display-message -p '#S' 2>/dev/null | sed 's/^jarvis_//')} && mkdir -p .jarvis/signals && printf '%s' '{"estado":"done","motivo":"","memorias_usadas":[]}' > .jarvis/signals/terminal_${TID}.json

En `memorias_usadas` listá los slugs de `.jarvis/memory/` que leíste y te
sirvieron ([] si ninguna). Si terminás `blocked`/`error`, el `motivo` es
OBLIGATORIO y concreto; en `done` es opcional (una línea con el enfoque
no-obvio que funcionó). En workflows el engine ya te da esta instrucción con
tu id — ahí no hace falta averiguarlo.
<!-- JARVIS_MEMORY_END -->

<!-- JARVIS_MAILBOX_START -->
## 📬 Mailbox entre agentes (Jarvis)

Para avisarle algo a OTRO agente del workspace (cambiaste una interfaz
que usa, un bug en su área), agregá UNA línea al final de
`.jarvis/MAILBOX.md` con este formato exacto:

    - @TuNombre -> @NombreDelOtro: mensaje corto y accionable

El mailbox es 1-a-1: 1 línea = 1 destinatario CONCRETO, con el nombre
EXACTO de su terminal (tu nombre es el de tu tarea/terminal, ej
"Backend"). NO existe el broadcast: los mensajes a "todos" no le llegan
a nadie. Cero charla ociosa — nada de anunciar avances, agradecer ni
pedir que otros prueben: lo que quieras verificar, hacelo vos mismo en
tu terminal. Para leer, LEÉ tus mensajes con `.jarvis/jv inbox` — NUNCA
releas `.jarvis/MAILBOX.md` entero (llegó a pesar ~14K tokens; el inbox
te da solo lo tuyo, sin leído).
<!-- JARVIS_MAILBOX_END -->

<!-- JARVIS_PUERTOS_START -->
## 🔌 Regla de puertos (Jarvis)

El **puerto 3000 está PROHIBIDO**: ahí corre Jarvis Workspace (el dashboard
que te está orquestando). Levantar cualquier cosa en el 3000 lo rompe.

Antes de levantar CUALQUIER servidor (dev server, API, preview, http.server):

1. Mirá qué puertos ya están ocupados:

       ss -tlnp 2>/dev/null || lsof -iTCP -sTCP:LISTEN -P -n

2. Elegí un puerto LIBRE que no pise ninguno de los ocupados (para dev
   servers usá el rango 5000-5999 u 8081-8999 si está libre).
3. Pasale el puerto explícito al comando (`--port`, `-p`, `PORT=`); no
   confíes en el default de la herramienta.

NUNCA mates un proceso de un puerto que no levantaste vos: puede ser
Jarvis, otro agente o un preview en uso.
<!-- JARVIS_PUERTOS_END -->

<!-- JARVIS_LIVE_START -->
## 🔴 Coordinación del enjambre — `.jarvis/jv`

Trabajás con otros agentes sobre el MISMO árbol. No leas archivos de estado
para enterarte: preguntá cuando haga falta.

    .jarvis/jv estado      qué tocan los otros y qué te llegó
    .jarvis/jv inbox       tus mensajes nuevos (NO leas .jarvis/MAILBOX.md entero)
    .jarvis/jv msg "<agente>" "<texto>"    dejarle un aviso (NO lo interrumpe)
    .jarvis/jv ask "<agente>" "<pregunta>" preguntarle y ESPERAR la respuesta
    .jarvis/jv claim "<simbolo|archivo|carpeta>"   reservar TU zona
    .jarvis/jv commit -m "<mensaje>"       commitear SOLO lo tuyo, por hunk

Las reglas que sí importan:

1. **Reclamá tu zona antes de empezar**: `jv claim` sobre las funciones, ids o
   archivos que vas a tocar. Se reclama por NOMBRE, nunca por número de línea
   (las líneas se mueven). Lo que nadie reclamó se te concede al instante; si
   necesitás algo más sobre la marcha, también.
2. **Nunca reescribas un archivo entero** que no sea tuyo (`Write` sobre algo
   existente). Editá por zona: dos agentes en zonas distintas del mismo
   archivo conviven bien, pero una sobrescritura con tu copia vieja le borra
   el trabajo al otro sin dejar rastro. Jarvis te frena si pasa.
3. **No borres ni renombres lo que otro reclamó.** Jarvis te lo va a frenar
   antes de escribir, con el nombre del dueño. Si de verdad tiene que irse,
   avisale por `jv msg` y que lo adapte él — sacarlo de golpe le rompe el
   código sin que se entere. (Usar su función está perfecto; nadie te frena.)
4. **Commiteá con `jv commit`**: stagea solo lo tuyo, hunk por hunk. `git add`
   a secas se lleva el trabajo sin commitear del otro que vive en ese archivo.

5. **`msg` deja el aviso; `ask` es el que INTERRUMPE.** Un `jv msg` cae en el
   inbox del otro y se lo lleva cuando retome: **NO lo despierta** (si ya cerró
   su tarea, sigue tranquilo). Si necesitás que reaccione AHORA usá `jv ask`, y
   si le estás pasando trabajo empezá el mensaje con `HANDOFF` — esos dos sí lo
   despiertan. Se hizo así porque el 38% de los mensajes caía en agentes con la
   tarea ya cerrada y les quemaba un turno entero para nada.
   Y el destinatario es **otra terminal, por su nombre EXACTO**: escribirle a
   `@jarvis` o "al sistema" no le llega a NADIE (36 mensajes murieron así).

6. **Un agente 💀 caído no va a volver.** Si `jv estado` te lo marca así, su
   territorio ya está libre y el guard no te bloquea por sus archivos: no le
   pidas permiso ni lo esperes. Y si te aparece una **⚠ Herencia**, eso es
   trabajo sin commitear de alguien que se fue — nadie lo va a venir a buscar:
   si tocás uno de esos archivos, commitealo vos con un mensaje que diga qué es.

7. **Commiteá antes de cerrar tu tarea.** Trabajo real terminado que queda sin
   commitear en este árbol es trabajo que otro barre o hereda. Lo que NO se
   commitea: pruebas de localhost, mockups, capturas y artefactos de build —
   eso va al `.gitignore`, no a un commit.

8. **Tu tarea es TU tarea — no te empecines con la del otro.** Verificás TU
   trabajo; el ajeno solo si su dueño te lo pide o tu tarea depende de él, y
   UNA sola vez. Los acuses (OK/gracias/recibido/"verificado, todo bien") NO
   se contestan: cada mensaje le quema al otro un turno entero. Tope:
   2 mensajes tuyos por hilo con el mismo agente sobre el mismo tema — después
   decidís solo con lo que hay, y si el desacuerdo importa lo dejás en una
   memoria. (Medido acá: 74 mensajes entre DOS agentes en un feature, la
   mayoría re-verificaciones cruzadas y cortesía.)

9. **Jamás esperes el commit ajeno.** ¿Quedaron entrelazados sin commitear en
   el mismo archivo? `jv commit` stagea SOLO tus hunks (usa la provenance
   real): commiteá YA y seguí con lo tuyo. Pedir «commiteá primero y avisame»
   es esperar en promedio UNA HORA (la entrega idle del mailbox tarda eso)
   algo que la herramienta resuelve sola.

`.jarvis/LIVE.md` sigue existiendo (quién es dueño de qué, permisos y
reservas) por si querés el detalle, pero `jv estado` te da lo que necesitás.
<!-- JARVIS_LIVE_END -->

<!-- JARVIS_LECCIONES_START -->
## 📚 Lecciones del enjambre (siempre cargadas — de fallos y hallazgos reales)

- Aisla el Builder en una subcarpeta obligatoria del proyecto; resolvé anchors en un único punto (wb_agent.project_dir) que redirige agente, preview y edición — evitá que el preview publique la raíz.
- Debugueá desajustes editor-preview capturando mutaciones persistidas (micro-arrastres, tokens HTML, glows) y verifica contra el motor real del editor, no solo el DOM final — la fidelidad requiere rastrear deltas en origen.
- Capturá selectores HTML con prefijos únicos o índices en vez de clases reutilizadas entre diálogos — querySelector($) retorna el primer match y rompe si el DOM se reordena.
- En operaciones destructivas (borrar, purgar), candadeá por RUTA (contiene, es, está adentro) no por sesión — un mismo recurso puede ser alcanzado desde múltiples llamadores.
- Separálos caminos de lectura (falla abierto, cachea) de los de escritura/borrado (falla cerrado, nunca cachees errores) — un hipo de DB en caché deja todo muerto hasta reiniciar; en shutdown/lifespan, verificá que no escribas vacios encima de datos existentes.
- Verificá gates y transiciones de estado con tests instrumentados (contadores, eventos) no con lecturas puntuales del DOM — latencias de carga estiran los tiempos y un snapshot tardío da falsos OK.
- Stagea hunks por zona lógica y blob-de-HEAD-más-tu-cambio en archivos de otros agentes — intercalaciones de trabajo ajeno requieren granularidad de contenido, no de línea, y conservá hechos técnicos en comentarios renovados.
- Resolvé destinos (voz, playlist, anclaje) una sola vez en el ciclo y cachea el resultado con invalidación explícita — null sin terminal o sin destino visible mata features silenciosas.
- Documentá caveat de mutación en el PUNTO EXACTO donde una regla o cacheo podría romperse en futuros cambios — evitá que fallos repetidos vuelvan a pasar por ignorancia de contexto previo.
- Probá cada capa end-to-end con un servidor aislado y agentes simulados antes de confiar en tests unitarios — encuentran bugs de orquestación que la cobertura por módulo nunca ve.
- Medí latencias reales en el entorno de ejecución, no estimes — importaciones pesadas, lookups de DNS y syscalls se comen decenas de ms que los profiles locales no capturan; en UIs escaladas (zoom, devicePixelRatio), mide también la traducción de coordenadas (pantalla ↔ CSS ↔ dispositivo) antes de confiar en reportes del navegador.
- En guards de captura, distinguí por BOTÓN (física del input) no solo por target — el cierre legítimo de UI puede disparar eventos que reabre la captura si confundís el origen.
- Para un síntoma único con causas múltiples, inyectá estado con APIs de testing (SwarmLink.aplicar()) e interceptá operaciones críticas (fetch, execv) con herramientas como Playwright — fuerza repro determinista sin tocar estado real.
- Rastreá fill-mode y transform retenida en ancestros CSS (animation-fill-mode: backwards vs both) — la herencia de animación puede pegar o desactivar propiedades visuales en descendientes sin señal en el DOM local.
- En layouts con zoom, viewport units (vh/vw) no escalan con CSS zoom — barre todo a custom properties (--jw-vh/--jw-vw) actualizadas en el handler de zoom y corre media queries DESPUÉS de medir.
- Al refit de grillas bajo zoom, fuerza dedupe y re-medición de clientWidth en dos pasadas desde el punto de escala — el cache de dimensiones y el gate de arrastre pueden saltearse si la primera pasada metió filas extras.
- En contenedores flex con SVG inline, declará aspect-ratio + max-height con custom properties — flex-basis sobre SVG no es un tamaño estable y max-height:100% no clampea sin explicitud del padre.
- Traducí coordenadas del mouse en dos espacios: pantalla (input raw) → CSS (zoom aplicado) → dispositivo (devicePixelRatio); aplica en getCoords, handlers de drag, highlight remoto y pan — un mismo evento viaja por rutas distintas según la fuente (xterm.getCoords vs getMouseReportCoords) — verifica AMBAS.
- Sincronizá flags de modo terminal (DECCKM, mouse privado, etc.) que tmux absorbe en pane flags con un poller vivo + seed simétrico al abrir, no solo al sembrar — %output no los viaja, deben refrescarse periódicamente contra la verdad del servidor.
- En módulos de resolución de destino (voz, playlist, anclaje), aislá la lógica pura en un archivo dedicado sin side-effects y resuelve una sola vez al ciclo; aplicá reintentos programados en operaciones que dependen de foco/hover/gracia de tipeo, especialmente tras transiciones bloqueantes (Enter, tecla de control).

Lecciones escritas por el enjambre (abrí la memoria antes de pisar su tema):
- el 2026-08-06 se borró TODO el mundo Windows (shell Tauri, motor Rust, termhost, ConPTY, publisher, Discord presence, CI del shell); el workspace es Python/uvicorn + tmux y no se reintroduce nada de e — .jarvis/memory/app-windows-eliminada.md
- Todo reload que recree terminales tras un restart espera /api/system/ready (reconcile_listo), nunca health/boot_id a secas — pero con salida fail-OPEN por salud sostenida y botón de escape: un gate ce — .jarvis/memory/update-reload-espera-reconcile.md
- El lanzador de Windows debe despertar la distro ANTES del comando, loguear fuera de /tmp (tmpfs), vigilar el motor después de arrancar y SOSTENER la distro con un cliente wsl.exe ancla — sin ancla WSL — .jarvis/memory/lanzador-windows-levanta-motor.md
- tmux ABSORBE DECCKM y mouse-tracking en flags de pane (no los reenvía por %output); un poller re-enuncia a xterm los cambios post-seed, sin él las flechas/el clic mueren en los menús del agente. — .jarvis/memory/modos-privados-sync-vivo.md
- memoria/mailbox/puertos/live salen de plotspace/protocolos/*.md y los DOS motores leen la misma fuente; duplicarlos hace que cada agente reciba instrucciones distintas según quién le armó la sesión — .jarvis/memory/protocolo-fuente-unica.md
- la foto que el motor manda al enganchar una card debe llevar los atributos (rows_formatted / capture-pane -e); en texto pelado la pantalla se pinta entera en el color por defecto hasta que el programa — .jarvis/memory/semilla-attach-con-colores.md
- el motor se elige en UN punto por motor (backend() en Python, terminales::motor::hospeda_en_tmux() en Rust); Windows = PTY adentro, Linux/macOS = tmux, y el default por sistema NO se deduce en otro la — .jarvis/memory/motor-seleccion-un-solo-punto.md
- WSL mirrored SÍ entrega los puertos nuevos a Windows — el bloqueo real era el firewall de Hyper-V en Block; y el NOMBRE localhost resuelve IPv6-first, usar 127.0.0.1 — .jarvis/memory/wsl-mirrored-puertos-firewall.md
- var(--token-que-no-existe) sin fallback invalida la declaración entera — el menú ⋯ salió transparente y sin contorno por pedir --ob-surface-2 / --ob-border / --ob-text, que nunca existieron. — .jarvis/memory/tokens-css-inexistentes-invalidan.md
- el listener de cierre-por-click-afuera corre en mousedown, ANTES del click del disparador — cierra y el click reabre, así que el segundo click en el botón parece no hacer nada. — .jarvis/memory/popover-toggle-mousedown-click.md
- medido 2026-08-02 — 74 mensajes entre DOS agentes (mayoría re-verificación cruzada y acuses), 34% del tráfico sin destino, entrega idle promedio 64 min; de ahí salen las reglas 8/9 del protocolo jv y  — .jarvis/memory/coordinacion-costo-medido.md
- Antes de apagar/borrar/matar un recurso compartido, el código tiene que SABER si fue él quien lo creó — si esa condición vive en la doc como "responsabilidad del llamador", tarde o temprano el llamado — .jarvis/memory/apagar-solo-lo-que-prendiste.md
<!-- JARVIS_LECCIONES_END -->
