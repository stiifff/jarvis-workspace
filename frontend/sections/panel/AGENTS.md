# sections/panel/ — dock + project strip

The single right dock (`window.JarvisDock`) and the side project strip.

- **Files:**
  - `panel.js` — dock engine: tabs, splitter, maximize, badges, persistence.
    Exposes `window.JarvisDock` with `open/close/setTab/notify/isOpen/activeTab`
    (+ `revealTab` — programmatic jump that opens a tab WITHOUT persisting base
    or creating per-agent override; used by card-maximize to show the agent's
    localhost).
    The `#jw-dock-external` button (visible only on the editor tab) opens the
    standalone editor in a new tab (`GET /editor?project=N`).
  - `panel.css` — dock styles.
  - `strip.js` — project strip logic (`#jw-strip`, 185px, "WORKSPACES").
    Handles: active project selection, inline rename (double-click), project `⋯`
    menu (includes rename and remove), `#jw-strip-new` button (new project).
  - `launcher-state.js` — **pure** logic of the New-project modal.
    Exposes `window.JarvisLauncherState` with `CLI_LABELS`, `MAX_TERMINALES`,
    `clampContador`, `loteDesdeContadores`, `etiquetaCrear`. Tested in Node.
  - `__tests__/panel-state.test.js` — Node test of the dock's pure logic.
  - `__tests__/strip.test.js` — Node test of the strip logic.
  - `__tests__/launcher-state.test.js` — Node test of the launcher logic.
- **Served at:** `/static/sections/panel/`

## Creating new projects (flow from the panel)
The strip **+** (`#jw-strip-new`) or Ctrl+T triggers the New-project modal. Pure
counter/validation logic lives in `launcher-state.js` (`JarvisLauncherState`); the render and
the POST to `/api/projects` are done by `workspace.js`. Ctrl+\\ opens the quick picker
(`QuickPicker`), which lives in `sections/terminals/quick-picker.js` — don't duplicate logic there.

## Verification
- Pure logic: `node frontend/sections/panel/__tests__/panel-state.test.js`
  and `node frontend/sections/panel/__tests__/strip.test.js`
  and `node frontend/sections/panel/__tests__/launcher-state.test.js`
- DOM: smoke on `localhost:3000` (open/close dock, switch tabs, resize splitter,
  maximize editor/preview, open new-project modal, rename project).
- Bump `?v=N` of `panel.js`/`.css` in `shell/workspace.html` after each change.
