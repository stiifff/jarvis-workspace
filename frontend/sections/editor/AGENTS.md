# sections/editor/ — file editor (Monaco)

IDE-style editor: file tree + Monaco. Mirrors the pattern of `OrchestratorPanel`.

- **Files:** `editor.js`, `editor.css`
- **Served at:** `/static/sections/editor/`
- **Public global (FROZEN):** `window.JarvisEditor` —
  `abrirArchivo / cerrarTab / guardarActivo / estaAbierto /
  refrescarArbol / openPalette / openSearch / init / onProjectChanged`.
  Consume ONLY that from other sections; don't reach into internals.
- **Monaco:** loaded lazy from CDN (cloudflare), no local assets.

## Standalone editor
- **`GET /editor?project=N`** serves `shell/editor-standalone.html` — standalone page with the
  same editor pane (same IDs as the internal dock). Useful to open the editor in a separate tab.
- The **`#jw-dock-external`** button in the dock (visible only when the active tab is
  `editor`) navigates to this route in a new tab.
- If the editor pane in `workspace.html` changes, replicate the changes in
  `editor-standalone.html` (it's kept as a verbatim copy of IDs).

## Verification
Manual smoke on `localhost:3000` (a headless agent doesn't open a browser): open a
file, edit, save (Ctrl+S), rename/delete in the tree, command palette.
Also verify `localhost:3000/editor?project=<id>` in a separate tab.
Bump `?v=N` of `editor.js`/`editor.css` in `shell/workspace.html` after each change.
