# DESIGN.md — Obsidian Glass

Sistema de diseño canónico de Jarvis Workspace. Fuente de verdad en código:
`frontend/shared/tokens.css` (645 líneas) + `frontend/shared/base.css`.
Este archivo describe lo que existe; **si difieren, manda tokens.css**.

## Theme

Oscuro por defecto (obsidiana con tinte violeta), 24 temas intercambiables en caliente vía
`html[data-theme]`, de los cuales 2 son claros (`papel`, `alba`). Encima, un filtro de
**tonalidad** (matiz −40…40°, saturación 50…150%, profundidad −3…3) que reescribe los tokens
OKLCH inline en `<html>`. Consecuencia dura: **ningún hex hardcodeado, nunca** — todo color
sale de `var(--ob-*)`, o el tema claro rompe la legibilidad.

## Color

Todo en OKLCH. Estrategia: **restrained** — neutrales tintados + un acento.

**Planos de fondo** (de profundo a alto): `--ob-bg-void` (lienzo) → `--ob-bg-0` (app) →
`--ob-bg-1` (panel) → `--ob-bg-2` (card) → `--ob-bg-3` (hover) → `--ob-bg-4` (selección).
Separado: `--ob-bg-terminal`.

**Vidrio** (plano 2, con `backdrop-filter`, máximo 2 capas visibles a la vez):
`--ob-glass`, `--ob-glass-hi` (canto biselado), `--ob-glass-lo`.

**Líneas**: `--ob-line-1` divisor · `--ob-line-2` borde de card · `--ob-line-3` énfasis.

**Texto**, 5 niveles calibrados AA: `--ob-fg-0` títulos (~16:1) · `--ob-fg-1` cuerpo (~10:1) ·
`--ob-fg-2` secundario (~5.4:1, piso para texto normal) · `--ob-fg-3` muted (4.5:1 hasta bg-2)
· `--ob-fg-4` **sólo** disabled/placeholder.

**Acento único** (violeta-índigo en el default): `--ob-accent`, `--ob-accent-fg`,
`--ob-accent-dim`, mezclas `-08/-14/-24/-glow`, y `--ob-on-accent` para texto sobre relleno
(los temas de acento claro lo invierten a oscuro).

**Señales de estado — jamás decoración**: `--ob-run` (corriendo/éxito) · `--ob-work`
(trabajando/warning) · `--ob-err` (error) · `--ob-info` (info / voz escuchando).
`--ob-magenta` es de la aurora de Home.

## Typography

- `--font-ui`: Inter → system-ui. Carga toda la UI.
- `--font-mono`: JetBrains Mono. Datos, teclas, rutas, valores.
- `--font-display`: Instrument Serif italic. **En retirada**: el rediseño de Configuración
  (2026-07-19) lo saca de la UI de producto — italic serif en labels de app es el tell que el
  usuario rechazó. Queda para el sitio de marca.

Escala fija en px (no fluida): 10 · 11 · 12 · 13 (base) · 15 · 18 · 22 · 28 · 40.
Line-height 1.2 / 1.4 / 1.6. Tracking `-0.01em` en títulos, `0.12em` en versalitas.

## Spacing & shape

Grid de 4: 4 · 8 · 12 · 16 · 20 · 24 · 32.
Radios: 6 · 7 (botón) · 8 · 12 · 16 · 999.
Sombras `--shadow-1/2/3` con tinte frío; `--shadow-pop` suma un anillo de línea.

## Motion

- Duraciones: `--dur-1` 120ms (hover/color/foco) · `--dur-2` 180ms (menús, lift) ·
  `--dur-3` 280ms (modal/panel) · `--dur-glow` 500ms (cambio de estado).
- Easing: `--ease-out` entradas · `--ease-snap` menús/chips · `--ease-in-out` loops.
- Regla dura: **nunca animar el ancho de un panel que contenga xterm** (el canvas se
  desincroniza). Se usa `hidden`, y quien cambia tamaños llama a `relayoutAll()`.
- `prefers-reduced-motion` anula entradas y pulsos.

## Z-index (escala semántica)

`--z-panel` 100 · `--z-dropdown` 500 · `--z-modal` 1000 · `--z-toast` 1100 · `--z-ptt` 1200.

## Components

Íconos: set propio estilo Lucide, stroke 1.5, vía `icon(nombre, tamaño)` de `shared/ui.js`
— **no mezclar con otro set ni con emojis**. Logos de CLI: `window.cliLogo(tipo, size)`.
Primitivas compartidas: `.ps-switch` (toggle), `.set-seg` (segmentado), `toast()`,
`confirmar()`, `pedirTexto()`.

Chrome de terminal "Glass Pro": faux-glass (gradiente translúcido + bisel + brillo diagonal
en `::before`) — **jamás `backdrop-filter` sobre el canvas de xterm**, cuesta frames.
