# frontend/ — mapa para agentes

Frontend vanilla (HTML/CSS/JS, sin frameworks ni build). Organizado **por sección**:
todo lo de una sección vive en su carpeta, con su `.js` y `.css` juntos.

```
frontend/
├── index.html          # home, servido en GET /
├── shell/              # armazón del workspace (NO es una sección)
│   ├── workspace.html  # servido en GET /workspace
│   └── workspace.js    # "pegamento": arranca todo, WebSockets, navegación, TTS
├── shared/
│   ├── tokens.css      # ★ SISTEMA DE DISEÑO canónico (--ob-*) + utilidades — ver abajo
│   ├── ui.js           # ★ icon() / toast() / confirmar() / pedirTexto() / cliLogo() globales
│   ├── themes.js       # ★ sistema de temas (html[data-theme], localStorage jarvis.theme)
│   ├── icons/          # logos de CLIs vendoreados (lobehub 1.91.0): claude, codex, gemini…
│   ├── base.css        # reset, layout base + estilos del shell/terminales
│   └── __tests__/themes.test.js  # suite Node para lógica pura de temas
└── sections/
    ├── home/           # landing (home.js + home.css)
    ├── terminals/      # grilla de terminales (terminal.js, terminal-layout.js)
    ├── orchestrator/   # panel del orquestador (orchestrator.js + .css)
    ├── editor/         # editor de archivos Monaco (editor.js + .css)
    └── mobile-preview/ # preview Expo en marco de teléfono
```

## Serving (importante)
Todo `frontend/` se monta en `/static`. Una sección se sirve bajo
`/static/sections/<nombre>/<archivo>`. Al cambiar JS o CSS, **subir el `?v=N`**
de su `<link>`/`<script>` en `shell/workspace.html` (o `index.html` para home).

## Sistema de diseño "Obsidian Glass" (OBLIGATORIO)

`shared/tokens.css` es la ÚNICA fuente de verdad de tokens. Dirección completa:
`docs/redesign/PLAN_REDISENO_UI.md`. Reglas duras:

- **Colores**: SIEMPRE `var(--ob-*)` (oklch). Nunca hex/oklch literales de chrome.
  Los nombres legacy (`--bg-app`, `--sb-*`, `--hc-*`, `--violet`…) son alias de
  compatibilidad — no usarlos en código nuevo.
- **El color es SEÑAL, no decoración**: violeta = vida/acento (agente pensando,
  foco, CTA); verde/ámbar/rojo = SOLO estados; cian = info/voz; **magenta =
  de la aurora de Home**. El glow nace de un borde de 1px o texto, jamás
  de rellenar bloques.
- **Texto**: piso `--ob-fg-2` para texto normal (AA). `--ob-fg-3` solo íconos y
  labels grandes; `--ob-fg-4` solo disabled/placeholder.
- **Tipografía**: `--font-ui` (Inter) UI · `--font-display` (Instrument Serif,
  SOLO italic ≥20px) momentos editoriales · `--font-mono` (JetBrains Mono) datos;
  labels técnicos en mono UPPERCASE + `--ls-caps`. Tamaños SOLO de la escala
  `--text-*`.
- **Performance (hay xterm.js en vivo)**: `backdrop-filter` SOLO en plano-2
  (modales, menús flotantes, header) y máx 2 visibles; PROHIBIDO en contenedores
  de terminales. Animaciones infinitas SOLO transform/opacity/box-shadow.
  No animar width/height de paneles.
- **Prohibido**: emojis como íconos (usar `icon()` de shared/ui.js), `alert()`/
  `confirm()`/`prompt()` nativos (usar `toast()`/`confirmar()`/`pedirTexto()`),
  fuentes sci-fi, scanlines, clip-path en contenedores con scroll.
- **Utilidades**: `.ob-glass` (vidrio plano-2), `.ob-edge` (borde-gradiente
  plano-1), `.ob-pip[data-state]` (estado que respira), `.skeleton`,
  `.ob-spinner`, `.ob-label`; motion con `--dur-1/2/3` + `--ease-out/snap`.

## Temas y logos (desde 2026-06 rediseño violeta)

- **`shared/themes.js`** expone `window.JarvisThemes` con `aplicar(nombre)`, `actual()`,
  `init()`, `TEMAS` (array de 7), `normalizarTema`. `DEFAULT_TEMA = 'violeta'`. El tema se
  escribe en `html[data-theme=<nombre>]`; el default violeta NO pone atributo. Testeado en
  `shared/__tests__/themes.test.js`.
- **`shared/icons/`** — SVGs de CLIs (lobehub 1.91.0): `claude-color.svg`, `codex-color.svg`,
  `gemini-color.svg`, `opencode.svg`, `qwen-color.svg`, etc. Agregar nuevos CLIs aquí.
- **`window.cliLogo(tipo, size)`** en `shared/ui.js` — helper que devuelve `<img>` del logo
  correspondiente (o fallback texto si no existe). Usarlo en cualquier lugar que muestre el
  tipo de CLI (cards, launcher, picker rápido).
- **Acento/fondos**: SOLO via `var(--ob-*)` en `tokens.css`, incluyendo los overrides de tema
  bajo `[data-theme=<nombre>]`. Nunca hardcodear hex en secciones nuevas.

## Reglas
- No introducir frameworks, npm ni node como dependencia de runtime.
- Cada sección expone un global y consume solo la superficie pública de las otras
  (ver el `AGENTS.md` de cada carpeta). No tocar internals de otra sección.
- `workspace.js` (shell) cablea las secciones entre sí; es el único que conoce a todas.
