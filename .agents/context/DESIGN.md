# DESIGN.md — Obsidian Glass

Canonical design system of Jarvis Workspace. Source of truth in code:
`frontend/shared/tokens.css` (645 lines) + `frontend/shared/base.css`.
This file describes what exists; **if they differ, tokens.css wins**.

## Theme

Dark by default (obsidian with violet tint), 24 hot-swappable themes via
`html[data-theme]`, 2 of them light (`papel`, `alba`). On top, a **tonality** filter
(hue −40…40°, saturation 50…150%, depth −3…3) that rewrites the OKLCH tokens inline in
`<html>`. Hard consequence: **no hardcoded hex, ever** — every color comes from
`var(--ob-*)`, or the light theme breaks legibility.

## Color

Everything in OKLCH. Strategy: **restrained** — tinted neutrals + one accent.

**Background planes** (deep to high): `--ob-bg-void` (canvas) → `--ob-bg-0` (app) →
`--ob-bg-1` (panel) → `--ob-bg-2` (card) → `--ob-bg-3` (hover) → `--ob-bg-4` (selection).
Separate: `--ob-bg-terminal`.

**Glass** (plane 2, with `backdrop-filter`, max 2 layers visible at a time):
`--ob-glass`, `--ob-glass-hi` (beveled edge), `--ob-glass-lo`.

**Lines**: `--ob-line-1` divider · `--ob-line-2` card border · `--ob-line-3` emphasis.

**Text**, 5 AA-calibrated levels: `--ob-fg-0` titles (~16:1) · `--ob-fg-1` body (~10:1) ·
`--ob-fg-2` secondary (~5.4:1, floor for normal text) · `--ob-fg-3` muted (4.5:1 up to bg-2)
· `--ob-fg-4` **only** disabled/placeholder.

**Single accent** (violet-indigo on default): `--ob-accent`, `--ob-accent-fg`,
`--ob-accent-dim`, blends `-08/-14/-24/-glow`, and `--ob-on-accent` for text on fills
(light-accent themes invert it to dark).

**Status signals — never decoration**: `--ob-run` (running/success) · `--ob-work`
(working/warning) · `--ob-err` (error) · `--ob-info` (info / voice listening).
`--ob-magenta` belongs to the Home aurora.

## Typography

- `--font-ui`: Inter → system-ui. Carries the whole UI.
- `--font-mono`: JetBrains Mono. Data, keys, paths, values.
- `--font-display`: Instrument Serif italic. **Retiring**: serif italic in app labels is the
  tell this product rejects. It stays for brand surfaces.

Fixed px scale (not fluid): 10 · 11 · 12 · 13 (base) · 15 · 18 · 22 · 28 · 40.
Line-height 1.2 / 1.4 / 1.6. Tracking `-0.01em` on titles, `0.12em` on small-caps.

## Spacing & shape

Grid of 4: 4 · 8 · 12 · 16 · 20 · 24 · 32.
Radii: 6 · 7 (button) · 8 · 12 · 16 · 999.
Shadows `--shadow-1/2/3` with a cool tint; `--shadow-pop` adds a line ring.

## Motion

- Durations: `--dur-1` 120ms (hover/color/focus) · `--dur-2` 180ms (menus, lifts) ·
  `--dur-3` 280ms (modal/panel) · `--dur-glow` 500ms (state change).
- Easings: `--ease-out` entries · `--ease-snap` menus/chips · `--ease-in-out` loops.
- Hard rule: **never animate the width of a panel containing xterm** (the canvas
  desyncs). Use `hidden`, and whoever changes sizes calls `relayoutAll()`.
- `prefers-reduced-motion` cancels entries and pulses.

## Z-index (semantic scale)

`--z-panel` 100 · `--z-dropdown` 500 · `--z-modal` 1000 · `--z-toast` 1100 · `--z-ptt` 1200.

## Components

Icons: own Lucide-style set, stroke 1.5, via `icon(nombre, tamaño)` from `shared/ui.js`
— **don't mix with other sets or emojis**. CLI logos: `window.cliLogo(tipo, size)`.
Shared primitives: `.ps-switch` (toggle), `.set-seg` (segmented), `toast()`,
`confirmar()`, `pedirTexto()`.

Terminal chrome "Glass Pro": faux-glass (translucent gradient + bevel + diagonal shine
in `::before`) — **never `backdrop-filter` over the xterm canvas**, it costs frames.
