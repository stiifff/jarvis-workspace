# PRODUCT.md — Jarvis Workspace

## Register

**product** — app UI. Design SERVES the task. (Treat brand surfaces separately.)

## What it is

Local dashboard (localhost:3000) for orchestrating several AI agents (Claude Code, Codex,
Gemini, Qwen…) working **in parallel** on the same repo. Persistent tmux terminals embedded
in xterm.js, an orchestrator that distributes tasks, shared memory between agents, web/mobile
preview, editor. It's a **cockpit**, not an IDE: the user watches several agents work
simultaneously and steers them.

## Who uses it

A small team (or a single power user) on long sessions: high density of moving information,
split attention. The UI competes with the terminals for attention — when the user looks at the
UI it's because they want a quick answer and to get back.

## Jobs to be done

- See at a glance what each agent is doing and which one is stuck.
- Switch projects / open terminals without losing the thread.
- Configure the environment (voice, shortcuts, theme, CLI accounts, plugins) without slowing down the work.
- Consult and curate the shared memory that keeps the agents from repeating mistakes.

## Personality

Instrument. Precise, quiet, dark, with signals of life (state glow, aura) that only appear
when they mean something. No orphan decoration. Should feel expensive, like studio hardware:
real material (glass, obsidian), not illustration.

## Anti-references

- The generic macOS / VS Code / Linear settings panel: side nav + identical rows
  with a toggle on the right, the same template for everything. **This is exactly what this
  product refuses to be.**
- SaaS dashboards with giant metrics and gradients.
- Serif italic display as the only "design" gesture on an otherwise generic UI.
- Nested cards and grids of identical cards.

## Strategic design principles

1. **Every domain dictates its shape.** A keyboard is drawn as a keyboard, 24 themes as
   a spectrum, memory as a console. The generic row template is the enemy.
2. **Honest density.** No 95% empty screens; if a section has nothing to show, it's framed wrong.
3. **Color is signal, never decoration.** The accent marks the active/selected.
4. **Never hardcode color.** 24 themes + tint filter: everything comes from `var(--ob-*)`.
5. **Performance is design.** Glass must not cost frames over the xterm canvas.

## Accessibility

AA target. Normal text ≥4.5:1 (the `--ob-fg-*` tokens are already calibrated by level),
visible focus always, everything reachable by keyboard, `prefers-reduced-motion` respected.
Bilingual ES⇆EN (`shared/i18n.js`): new texts go into the dictionary.
