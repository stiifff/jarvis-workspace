---
name: qa-browser-jarvis
description: Cómo verificar Jarvis Workspace en browser real (Playwright + token) y correr todos sus tests. Usala antes de dar por terminado cualquier cambio de frontend.
---

# QA en browser de Jarvis Workspace

## Server
- Corre en `http://localhost:3000`. Verificá si ya está vivo ANTES de levantar otro:
  `curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/` → 200 = vivo, usalo y NO lo mates.
- Si tocaste **backend** (Python): **NO REINICIES EL SERVER.** uvicorn corre SIN
  --reload a propósito: la actualización la aplica EL USUARIO desde el banner
  "Actualizar ahora" de la UI (con canary de arranque + bump automático de VERSION).
  Verificá tu cambio SIN reiniciar:
  1. `python -m pytest plotspace/tests/ -q` — pytest importa el código de DISCO
     (tu cambio corre ahí, no hace falta el server).
  2. `python -c "import plotspace.main"` — smoke de arranque: caza SyntaxError,
     imports rotos y deps faltantes (lo mismo que chequea el canary del updater).
  3. Si necesitás pegarle a la superficie HTTP real: instancia efímera en un
     puerto libre 5000-5999 (regla de puertos), y matala al terminar.
  **PROHIBIDO `pkill -f uvicorn` + relanzar a mano**, y también
  `scripts/reiniciar-server.sh` (es herramienta del usuario, no de agentes).
- Si tocaste **frontend**: NO hace falta reiniciar — pero SÍ bumpear el `?v=N` del archivo
  en `workspace.html` (o `index.html`); regla monotónica: valor actual + 1.

## Auth (token-gate)
- Token en `data/jarvis_token.txt`. Cookie: `jarvis_token=<token>`.
- curl: `curl -s -b "jarvis_token=$(cat data/jarvis_token.txt)" http://localhost:3000/api/projects`
- Playwright: setear la cookie en el contexto antes de navegar (domain `localhost`).

## Playwright en este entorno (WSL sin sudo)
- `playwright` ya está en el venv; chromium cacheado (`chromium-1148`).
- Faltan libs NSS del sistema → exportá `LD_LIBRARY_PATH=/tmp/nsslibs/extracted/usr/lib/x86_64-linux-gnu`
  (si /tmp se limpió: `apt-get download libnss3 && dpkg-deb -x *.deb /tmp/nsslibs/extracted`).
- En headless, WebGL va por SwiftShader: los FPS bajos durante drags son artefacto
  del entorno, no jank real — verificá que el width siga al cursor síncrono.
- **Modo observador OBLIGATORIO al abrir el workspace**: agregá `&qa=1` a la URL
  (`http://localhost:3000/workspace?id=N&qa=1`). Con ese flag las terminales se
  attachean read-only + ignore-size (sin `-d`): tu página NO desplaza el attach
  del usuario, NO le redimensiona la ventana tmux al tamaño de tu viewport
  headless y NO puede tipear. Sin el flag, CADA navegación tuya le roba la
  sesión al usuario y le deja las terminales congeladas / con el scrollback
  triturado (la "quinta capa" de [[tmux-size-clamping]]). Si tu QA necesita
  tipear en una terminal, no lo hagas por el browser: `tmux send-keys` directo.

## Tests (correr TODOS antes de dar por bueno un cambio)
```bash
node frontend/sections/panel/__tests__/panel-state.test.js
node frontend/sections/panel/__tests__/strip.test.js
node frontend/sections/panel/__tests__/launcher-state.test.js
node frontend/sections/terminals/__tests__/terminal-layout.test.js
node frontend/sections/terminals/__tests__/input-block.test.js
node frontend/sections/terminals/__tests__/quick-picker.test.js
node frontend/sections/terminals/__tests__/terminal-flow.test.js
node frontend/sections/preview/__tests__/preview-url.test.js
node frontend/shared/__tests__/themes.test.js
source venv/bin/activate && python -m pytest plotspace/tests/ -q
```
Y `node --check <archivo>` por cada JS tocado.

## Selectores clave del workspace (post rediseño violeta 2026-06)
- Franja proyectos: `#jw-strip` (Ctrl+B togglea `body.jw-strip-off`)
  - `.sb-new-ghost` — botón "Nuevo workspace" que abre el modal Agregar proyecto (`#modal-new-terminal`)
- Barra: `#jw-bar` · toggle dock `#jw-dock-toggle` · tuerquita `#jw-gear`
  - Centro: breadcrumb `<nav class="gh-crumb-center">` "Jarvis Workspace › proyecto"
  - **NO existe `#btn-new-terminal`** (eliminado en rediseño)
- Dock: `#jw-dock` + `.jw-tab[data-tab=preview|jarvis|editor|tasks|review|mobile]`
  + `.jw-pane[data-pane=...]` · splitter `#jw-dock-splitter` · maximizar `#jw-dock-max` (solo editor/preview)
  · abrir editor standalone `#jw-dock-external` (solo tab editor)
- Quick picker: `Ctrl+\\` → `.qp-overlay`; filas `.qp-row`
- Temas: `html[data-theme=<nombre>]` (default violeta = sin atributo); cambiar via `JarvisThemes.aplicar('<nombre>')`
- API JS en consola: `JarvisDock.open/setTab/notify/isOpen/activeTab`, `WebPreview.setUrl/detectar`, `JarvisSettings.open`, `JarvisThemes.aplicar/actual`
- Regla de oro: 0 errores rojos en consola al final de cualquier recorrido (warnings OK).
