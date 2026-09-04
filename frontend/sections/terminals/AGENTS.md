# sections/terminals/ — grilla de terminales

Render de las terminales (xterm.js) + motor de layout tipo dashboard.

- **Archivos:**
  - `terminal.js` — render/attach de terminales vía WebSocket + xterm. El chrome de
    cada card lo genera `workspace.js` (logo CLI decorativo + maximizar + ✕); sin
    footer (el `t-footer` con label CLI + uptime se eliminó 2026-06) y sin menú ⋯
    (el de ajustes/cambio de shell se fue con el subsistema de shells de la era
    Windows, 2026-08-08 — la IA se elige al crear la terminal).
    Selección con mouse SIEMPRE local (drag/doble/triple click; copia con Ctrl+C,
    SIN copy-on-select) vía 3 parches de instancia a xterm 5.3 — ver memoria
    [[seleccion-mouse-en-terminales]] antes de tocar nada de mouse/selección.
    Handle de QA: `window.terminalesXterm` (Map terminalId → {term, ws, ...}).
  - `terminal-layout.js` — motor de **mosaico auto-tile**. **Módulo UMD**: lógica
    pura sin DOM (testeable en Node) + motor DOM que se instala solo en el navegador.
    Espeja el patrón `window.JarvisEditor` → expone `window.TerminalLayout`.
    - Modelo: **grilla por fracciones** `{ rows: [ { hFrac, cells: [ {id, wFrac} ] } ] }`
      que SIEMPRE llena el contenedor. Al agregar/quitar re-tilea en grilla
      balanceada (`cols=ceil(√N)`, última fila estira; máx 9). Resize = divisor de
      paneles (la vecina se achica/crece, no se mueve). Drag = intercambia celdas.
  - `quick-picker.js` — picker de terminal rápida (`.qp-overlay`). Expone
    `window.QuickPicker` con `abrir()`, `cerrar()`, `init()`. Se abre con Ctrl+\\
    (binding configurable como `jarvis.control.quick-terminal`). Muestra 6 CLIs con sus
    logos (`window.cliLogo`); crea la terminal elegida vía `POST /api/terminals`.
  - `terminal-paste.js` — **módulo UMD puro**: decisiones del paste (Ctrl+V):
    texto gana sobre imagen; imagen → subir a `/upload-image` y pegar la ruta
    (jamás `\x16`: obligaba a la CLI a leer el clipboard de Windows vía interop
    WSL/powershell, 3.5s+ → "Pasting..." eterno; `\x16` es solo fallback si la
    subida falla). Ver memoria [[gotcha-ctrl-v-xterm-paste]].
  - `terminal-flow.js` — **módulo UMD puro**: contador de acks del flow control
    PTY→WS→xterm (séptima capa de [[tmux-size-clamping]]). El browser confirma
    bytes YA PARSEADOS (callback de `term.write` → `{'type':'ack','bytes':N}`)
    y el backend frena la lectura del PTY con >1MB sin confirmar — así la cola
    de xterm jamás llega a los 50MB donde TIRA datos en pestañas ocultas
    (corrupción visual permanente hasta F5). terminal.js solo declara `&fc=1`
    en la URL del WS si este módulo cargó.
  - `__tests__/terminal-layout.test.js` — test Node (`require('../terminal-layout.js')`).
  - `__tests__/quick-picker.test.js` — test Node de la lógica pura del picker.
  - `__tests__/terminal-flow.test.js` — test Node del contador de acks.
- **Servido en:** `/static/sections/terminals/`
- **Estilos:** hoy varios estilos de terminal viven en `shared/base.css`
  (entrelazados con reglas compartidas y `@media`); no se separaron para no romper
  la cascada ni chocar con la branch `feature/terminal-layout`.

## Verificación
- Lógica pura: `node frontend/sections/terminals/__tests__/terminal-layout.test.js`
  y `node frontend/sections/terminals/__tests__/quick-picker.test.js`
- DOM: smoke manual en `localhost:3000` (abrir/mover/redimensionar terminales, Ctrl+\\).
- Subir `?v=N` de `terminal.js` en `shell/workspace.html` tras cada cambio.
