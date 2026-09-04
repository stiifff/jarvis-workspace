# sections/editor/ — editor de archivos (Monaco)

Editor estilo IDE: árbol de archivos + Monaco. Espeja el patrón de `OrchestratorPanel`.

- **Archivos:** `editor.js`, `editor.css`
- **Servido en:** `/static/sections/editor/`
- **Global público (CONGELADO):** `window.JarvisEditor` —
  `abrirArchivo / cerrarTab / guardarActivo / estaAbierto /
  refrescarArbol / openPalette / openSearch / init / onProjectChanged`.
  Consumir SOLO eso desde otras secciones; no usar los internos.
- **Monaco:** se carga lazy desde CDN (cloudflare), no hay assets locales.

## Editor standalone (desde 2026-06 rediseño)
- **`GET /editor?project=N`** sirve `shell/editor-standalone.html` — página autónoma con el
  mismo pane del editor (mismos IDs que el dock interno). Útil para abrir el editor en una
  pestaña separada del navegador.
- El botón **`#jw-dock-external`** en el dock (visible solo cuando la pestaña activa es
  `editor`) navega a esta ruta en nueva pestaña.
- Si se modifica el pane del editor en `workspace.html`, replicar los cambios en
  `editor-standalone.html` (se mantiene como copia verbatim de IDs).

## Verificación
Smoke manual en `localhost:3000` (un agente headless no abre navegador): abrir un
archivo, editar, guardar (Ctrl+S), renombrar/borrar en el árbol, command palette.
Verificar también `localhost:3000/editor?project=<id>` en pestaña separada.
Subir `?v=N` de `editor.js`/`editor.css` en `shell/workspace.html` tras cada cambio.
