# sections/panel/ — dock + franja de proyectos

El dock derecho único (`window.JarvisDock`) y la franja de proyectos lateral.

- **Archivos:**
  - `panel.js` — motor del dock: pestañas, splitter, maximizar, badges, persistencia.
    Expone `window.JarvisDock` con `open/close/setTab/notify/isOpen/activeTab`
    (+ `revealTab` — salto programático que abre una pestaña SIN persistir base
    ni crear override por-agente; lo usa el maximizar-card para mostrar el
    localhost del agente).
    El botón `#jw-dock-external` (solo visible en pestaña editor) abre el editor
    standalone en nueva pestaña (`GET /editor?project=N`).
  - `panel.css` — estilos del dock.
  - `strip.js` — lógica de la franja de proyectos (`#jw-strip`, 185px, "WORKSPACES").
    Maneja: selección de proyecto activo, rename inline (doble-click), menú ⋯ por
    proyecto (incluye rename y quitar), botón `#jw-strip-new` (nuevo proyecto).
  - `launcher-state.js` — lógica **pura** del modal de Nuevo proyecto.
    Expone `window.JarvisLauncherState` con `CLI_LABELS`, `MAX_TERMINALES`,
    `clampContador`, `loteDesdeContadores`, `etiquetaCrear`. Testeado en Node.
  - `__tests__/panel-state.test.js` — test Node de la lógica pura del dock.
  - `__tests__/strip.test.js` — test Node de la lógica de la franja.
  - `__tests__/launcher-state.test.js` — test Node de la lógica del launcher.
- **Servido en:** `/static/sections/panel/`

## Creación de nuevos proyectos (flujo desde el panel)
El **+** de la franja (`#jw-strip-new`) o el atajo Ctrl+T disparan el modal de Nuevo
proyecto. La lógica pura de contadores y validación de terminales vive en
`launcher-state.js` (`JarvisLauncherState`); el render y el POST a `/api/projects` los
hace `workspace.js`. El atajo Ctrl+\\ abre el picker rápido (`QuickPicker`), que está
en `sections/terminals/quick-picker.js` — no duplicar lógica acá.

## Verificación
- Lógica pura: `node frontend/sections/panel/__tests__/panel-state.test.js`
  y `node frontend/sections/panel/__tests__/strip.test.js`
  y `node frontend/sections/panel/__tests__/launcher-state.test.js`
- DOM: smoke en `localhost:3000` (abrir/cerrar dock, cambiar pestañas, resize splitter,
  maximizar editor/preview, abrir modal nuevo proyecto, rename de proyecto).
- Subir `?v=N` de `panel.js`/`.css` en `shell/workspace.html` tras cada cambio.
