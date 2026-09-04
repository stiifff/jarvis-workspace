# PRODUCT.md — Jarvis Workspace

## Register

**product** — app UI. Design SERVES the task. (The OSS landing site under `sitio/` is the
only brand surface; treat it separately.)

## What it is

Dashboard local (localhost:3000) para orquestar varios agentes de IA (Claude Code, Codex,
Gemini, Qwen…) trabajando **en paralelo** sobre el mismo repo. Terminales tmux persistentes
embebidas en xterm.js, un orquestador que reparte tareas, memoria compartida entre agentes,
preview web/móvil, editor. Es una **cabina**, no un IDE: el usuario mira varios agentes
trabajar a la vez y los conduce.

## Who uses it

Un solo operador (el dueño del repo), horas seguidas, de noche, pantalla grande, cuarto a
media luz, con 4-12 terminales vivas a la vista. Contexto: alta densidad de información en
movimiento, atención repartida. La UI compite con las terminales por la atención — cuando el
usuario mira la UI es porque quiere una respuesta rápida y volver.

## Jobs to be done

- Ver de un vistazo qué está haciendo cada agente y cuál se trabó.
- Cambiar de proyecto / abrir terminales sin perder el hilo.
- Configurar el entorno (voz, atajos, tema, cuentas de CLI, plugins) sin frenar el trabajo.
- Consultar y curar la memoria compartida que hace que los agentes no repitan errores.

## Personality

Instrumento. Preciso, silencioso, oscuro, con señales de vida (glow de estado, aura) que
sólo aparecen cuando significan algo. Cero decoración huérfana. Debe sentirse caro, como
hardware de estudio: material real (vidrio, obsidiana), no ilustración.

## Anti-references

- El panel de settings genérico de macOS / VS Code / Linear: nav lateral + filas idénticas
  con toggle a la derecha, la misma plantilla para todo. **Es exactamente lo que el usuario
  rechazó.**
- Dashboards SaaS con métricas gigantes y gradientes.
- Serif italic display como único gesto de "diseño" sobre una UI por lo demás genérica.
- Tarjetas anidadas y grids de tarjetas idénticas.

## Strategic design principles

1. **Cada dominio dicta su forma.** Un teclado se dibuja como teclado, 24 temas como
   espectro, la memoria como consola. La plantilla de fila genérica es el enemigo.
2. **Densidad honesta.** Nada de pantallas 95% vacías; si una sección no tiene qué mostrar,
   está mal encuadrada.
3. **El color es señal, nunca decoración.** El acento marca lo activo/lo seleccionado.
4. **Nunca hardcodear color.** 24 temas + filtro de tinte: todo sale de `var(--ob-*)`.
5. **El rendimiento es diseño.** El vidrio no puede costar frames sobre el canvas de xterm.

## Accessibility

Objetivo AA. Texto normal ≥4.5:1 (los tokens `--ob-fg-*` ya están calibrados por nivel),
foco visible siempre, todo alcanzable por teclado, `prefers-reduced-motion` respetado.
Bilingüe ES⇆EN (`shared/i18n.js`): los textos nuevos entran al diccionario.
