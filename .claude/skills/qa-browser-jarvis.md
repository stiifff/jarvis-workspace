---
name: qa-browser-jarvis
description: How to verify Jarvis Workspace in a real browser (Playwright) and run all its tests. Use it before closing any frontend change.
---

# Browser QA for Jarvis Workspace

## Server
- Runs on `http://localhost:3000`. Check if it's alive BEFORE starting another:
  `curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/` → 200 = alive, use it and DON'T kill it.
- If you touched **backend** (Python): **DO NOT RESTART THE SERVER.** uvicorn runs WITHOUT
  --reload on purpose: the update is applied by the USER from the "Update now" banner in the UI
  (with a startup canary + automatic VERSION bump). Verify your change WITHOUT restarting:
  1. `python -m pytest plotspace/tests/ -q` — pytest imports the code from DISK
     (your change runs there, the server isn't needed).
  2. `python -c "import plotspace.main"` — startup smoke: catches SyntaxError,
     broken imports and missing deps (same as the updater canary checks).
  3. If you really need the live HTTP surface: ephemeral instance on a free port in 5000-5999
     (port rule), and kill it when done.
  **FORBIDDEN: `pkill -f uvicorn` + relaunch manually**, and likewise
  `scripts/reiniciar-server.sh` (it's a user tool, not an agent one).
- If you touched **frontend**: no restart needed — but DO bump the `?v=N` of the file
  in `workspace.html` (or `index.html`); monotonic rule: current value + 1.

## Playwright
- `playwright` lives in the venv. If Chromium can't launch, install the missing system
  libraries (e.g. `libnss3` on Debian/Ubuntu family) — the smoke test skips itself when
  Chromium is unavailable.
- In headless, WebGL goes through SwiftShader: low FPS during drags is an environment
  artifact, not real jank — verify the width follows the cursor synchronously.
- **MANDATORY observer mode when opening the workspace**: add `&qa=1` to the URL
  (`http://localhost:3000/workspace?id=N&qa=1`). With that flag terminals attach
  read-only + ignore-size (no `-d`): your page does NOT steal the user's attach, does NOT
  resize the tmux window to your headless viewport and cannot type. Without the flag, EVERY
  navigation of yours steals the session from the user and leaves terminals frozen / with
  shredded scrollback (the fifth layer of the tmux size-clamping note). If your QA needs to
  type in a terminal, don't do it through the browser: `tmux send-keys` directly.

## Tests (run ALL before declaring a change good)
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
And `node --check <file>` for every JS touched.

## Key workspace selectors (post violet redesign)
- Project strip: `#jw-strip` (Ctrl+B toggles `body.jw-strip-off`)
  - `.sb-new-ghost` — the "New workspace" button that opens the Add-project modal (`#modal-new-terminal`)
- Top bar: `#jw-bar` · dock toggle `#jw-dock-toggle` · gear `#jw-gear`
  - Center: breadcrumb `<nav class="gh-crumb-center">` "Jarvis Workspace › project"
  - **`#btn-new-terminal` does NOT exist** (removed in the redesign)
- Dock: `#jw-dock` + `.jw-tab[data-tab=preview|jarvis|editor|tasks|review|mobile]`
  + `.jw-pane[data-pane=...]` · splitter `#jw-dock-splitter` · maximize `#jw-dock-max` (editor/preview only)
  · open editor standalone `#jw-dock-external` (editor tab only)
- Quick picker: `Ctrl+\\` → `.qp-overlay`; rows `.qp-row`
- Themes: `html[data-theme=<name>]` (default violet = no attribute); change via `JarvisThemes.aplicar('<name>')`
- JS API in console: `JarvisDock.open/setTab/notify/isOpen/activeTab`, `WebPreview.setUrl/detectar`, `JarvisSettings.open`, `JarvisThemes.aplicar/actual`
- Golden rule: 0 red errors in console at the end of any walkthrough (warnings OK).
