<!-- JARVIS_MEMORY_START -->
## 🧠 Memoria compartida del proyecto (Jarvis)

Este proyecto tiene una memoria compartida entre TODOS los agentes en
`.jarvis/memory/`. **Antes de empezar cualquier tarea**: buscá en
`.jarvis/memory/INDEX.md` las memorias que tocan tu tarea y abrilas. NO
leas el INDEX entero (pesa ~7K tokens y crece): GREPEALO por tus temas —
`grep -i "terminal\|xterm" .jarvis/memory/INDEX.md` — o leé solo la
sección de tu categoría (está agrupado; cada línea trae título, #tags y
fecha). Leerlo completo vale solo para una tarea transversal.

Cuando descubras algo que otro agente debería saber (decisión de
arquitectura, gotcha, convención, bug recurrente, cómo se corre algo),
**guardalo inmediatamente**:

1. Creá `.jarvis/memory/<slug-en-kebab-case>.md` con este formato exacto:

   ```markdown
   ---
   titulo: Título corto y específico (SIN fecha — no es una bitácora)
   tags: [tema1, tema2]
   categoria: <una de la lista de abajo>
   resumen: el hecho en UNA línea — es lo que el recall inyecta al prompt de los demás
   creado: YYYY-MM-DD
   actualizado: YYYY-MM-DD
   autor: tu nombre de agente
   estado: vigente
   ---

   Contenido conciso. Vinculá memorias relacionadas con [[slug-de-otra]].
   ```

   CATEGORÍAS (elegí UNA — es el cuadro temático donde vive la memoria):
   `terminales` (Terminales & tmux) · `ui` (UI · Workspace) · `swarm` (Backend & Swarm) · `diseno` (Diseño & Craft) · `preview` (Web Preview & Radio) · `cuentas` (Cuentas & CLIs) · `voz` (Voz & Audio) · `desktop` (Desktop) · `entorno` (Entorno · WSL & Git) · `producto` (Producto & Roadmap). Si dudás, Jarvis la infiere por los tags;
   una memoria que no cae en ninguna queda marcada `sin-clasificar` en la salud.

2. El INDEX (`.jarvis/memory/INDEX.md`) lo regenera Jarvis solo, AGRUPADO por
   categoría y enriquecido — no lo edites a mano.

REGLAS DE ORO (el pre-commit las hace cumplir — guard_memoria bloquea
frontmatter incompleto, informes de 150+ líneas y títulos con fecha):
- **Una memoria = UN hecho accionable** (~10-60 líneas). Un informe gigante
  ahoga el contexto de quien lo abre: destilá la conclusión y punto.
- **RECONCILIÁ antes de crear**: buscá en el INDEX si ya existe una memoria
  del tema. Si existe, ACTUALIZÁ ESA (sumá tu hallazgo, bumpeá `actualizado:`)
  — dos memorias del mismo tema confunden más que ninguna. Crear una nueva es
  la opción SOLO cuando el hecho es genuinamente nuevo.
- **Si un feature/código se eliminó**, NO borres su memoria: marcá
  `estado: lapida` y decí qué lo reemplaza (evita que alguien lo
  reintroduzca). Memoria vieja que no podés verificar: `estado: obsoleta`.
- **Linkeá SOLO slugs de esta carpeta** — nada de memorias personales de tu
  CLI (esos links nacen rotos para el resto del enjambre).
- **Escribí una lección** (`tags: [leccion]`) cuando un error —tuyo o ajeno—
  se pueda prevenir con una regla corta: qué pasó, por qué, cómo evitarlo.
- Las memorias son del PROYECTO, no tuyas: escribí para que cualquier agente
  futuro entienda sin contexto previo.

JERARQUÍA DE AUTORIDAD (cuando dos fuentes chocan, resolvé en este orden):
1. El **código actual** manda sobre cualquier memoria.
2. El **CLAUDE.md/AGENTS.md** manda sobre las memorias.
3. Una **lápida** (`estado: lapida`) manda sobre una vigente en su tema.
4. La **más actualizada** manda sobre la más vieja.
5. Si sigue ambiguo: **verificá contra el código — no adivines.**
Y si una memoria **te mintió** (describe algo que ya no es así), corregirla o
marcarla `estado: obsoleta` es PARTE de tu tarea — el choque que esquivás se
lo come el próximo agente.

CIERRE DE TAREA (con o sin workflow) — al terminar CUALQUIER tarea, señalá tu
cierre; es la telemetría con la que esta memoria aprende (qué sirvió, qué
falló). Ejecutá:

    TID=${JARVIS_TERMINAL_ID:-$(tmux display-message -p '#S' 2>/dev/null | sed 's/^jarvis_//')} && mkdir -p .jarvis/signals && printf '%s' '{"estado":"done","motivo":"","memorias_usadas":[]}' > .jarvis/signals/terminal_${TID}.json

En `memorias_usadas` listá los slugs de `.jarvis/memory/` que leíste y te
sirvieron ([] si ninguna). Si terminás `blocked`/`error`, el `motivo` es
OBLIGATORIO y concreto; en `done` es opcional (una línea con el enfoque
no-obvio que funcionó). En workflows el engine ya te da esta instrucción con
tu id — ahí no hace falta averiguarlo.
<!-- JARVIS_MEMORY_END -->

<!-- JARVIS_LECCIONES_START -->
## 📚 Lecciones del enjambre (siempre cargadas — de fallos y hallazgos reales)

- Aisla el Builder en una subcarpeta obligatoria del proyecto; resolvé anchors en un único punto (wb_agent.project_dir) que redirige agente, preview y edición — evitá que el preview publique la raíz.
- Debugueá desajustes editor-preview capturando mutaciones persistidas (micro-arrastres, tokens HTML, glows) y verifica contra el motor real del editor, no solo el DOM final — la fidelidad requiere rastrear deltas en origen.
- Capturá selectores HTML con prefijos únicos o índices en vez de clases reutilizadas entre diálogos — querySelector($) retorna el primer match y rompe si el DOM se reordena.
- En operaciones destructivas (borrar, purgar), candadeá por RUTA (contiene, es, está adentro) no por sesión — un mismo recurso puede ser alcanzado desde múltiples llamadores.
- Separálos caminos de lectura (falla abierto, cachea) de los de escritura/borrado (falla cerrado, nunca cachees errores) — un hipo de DB en caché deja todo muerto hasta reiniciar; en shutdown/lifespan, verificá que no escribas vacios encima de datos existentes.
- Verificá gates y transiciones de estado con tests instrumentados (contadores, eventos) no con lecturas puntuales del DOM — latencias de carga estiran los tiempos y un snapshot tardío da falsos OK.
- Stagea hunks por zona lógica y blob-de-HEAD-más-tu-cambio en archivos de otros agentes — intercalaciones de trabajo ajeno requieren granularidad de contenido, no de línea, y conservá hechos técnicos en comentarios renovados.
- Resolvé destinos (voz, playlist, anclaje) una sola vez en el ciclo y cachea el resultado con invalidación explícita — null sin terminal o sin destino visible mata features silenciosas.
- Documentá caveat de mutación en el PUNTO EXACTO donde una regla o cacheo podría romperse en futuros cambios — evitá que fallos repetidos vuelvan a pasar por ignorancia de contexto previo.
- Probá cada capa end-to-end con un servidor aislado y agentes simulados antes de confiar en tests unitarios — encuentran bugs de orquestación que la cobertura por módulo nunca ve.
- Medí latencias reales en el entorno de ejecución, no estimes — importaciones pesadas, lookups de DNS y syscalls se comen decenas de ms que los profiles locales no capturan; en UIs escaladas (zoom, devicePixelRatio), mide también la traducción de coordenadas (pantalla ↔ CSS ↔ dispositivo) antes de confiar en reportes del navegador.
- En guards de captura, distinguí por BOTÓN (física del input) no solo por target — el cierre legítimo de UI puede disparar eventos que reabre la captura si confundís el origen.
- Para un síntoma único con causas múltiples, inyectá estado con APIs de testing (SwarmLink.aplicar()) e interceptá operaciones críticas (fetch, execv) con herramientas como Playwright — fuerza repro determinista sin tocar estado real.
- Rastreá fill-mode y transform retenida en ancestros CSS (animation-fill-mode: backwards vs both) — la herencia de animación puede pegar o desactivar propiedades visuales en descendientes sin señal en el DOM local.
- En layouts con zoom, viewport units (vh/vw) no escalan con CSS zoom — barre todo a custom properties (--jw-vh/--jw-vw) actualizadas en el handler de zoom y corre media queries DESPUÉS de medir.
- Al refit de grillas bajo zoom, fuerza dedupe y re-medición de clientWidth en dos pasadas desde el punto de escala — el cache de dimensiones y el gate de arrastre pueden saltearse si la primera pasada metió filas extras.
- En contenedores flex con SVG inline, declará aspect-ratio + max-height con custom properties — flex-basis sobre SVG no es un tamaño estable y max-height:100% no clampea sin explicitud del padre.
- Traducí coordenadas del mouse en dos espacios: pantalla (input raw) → CSS (zoom aplicado) → dispositivo (devicePixelRatio); aplica en getCoords, handlers de drag, highlight remoto y pan — un mismo evento viaja por rutas distintas según la fuente (xterm.getCoords vs getMouseReportCoords) — verifica AMBAS.
- Sincronizá flags de modo terminal (DECCKM, mouse privado, etc.) que tmux absorbe en pane flags con un poller vivo + seed simétrico al abrir, no solo al sembrar — %output no los viaja, deben refrescarse periódicamente contra la verdad del servidor.
- En módulos de resolución de destino (voz, playlist, anclaje), aislá la lógica pura en un archivo dedicado sin side-effects y resuelve una sola vez al ciclo; aplicá reintentos programados en operaciones que dependen de foco/hover/gracia de tipeo, especialmente tras transiciones bloqueantes (Enter, tecla de control).

Lecciones escritas por el enjambre (abrí la memoria antes de pisar su tema):
- el 2026-08-06 se borró TODO el mundo Windows (shell Tauri, motor Rust, termhost, ConPTY, publisher, Discord presence, CI del shell); el workspace es Python/uvicorn + tmux y no se reintroduce nada de e — .jarvis/memory/app-windows-eliminada.md
- Todo reload que recree terminales tras un restart espera /api/system/ready (reconcile_listo), nunca health/boot_id a secas — pero con salida fail-OPEN por salud sostenida y botón de escape: un gate ce — .jarvis/memory/update-reload-espera-reconcile.md
- El lanzador de Windows debe despertar la distro ANTES del comando, loguear fuera de /tmp (tmpfs), vigilar el motor después de arrancar y SOSTENER la distro con un cliente wsl.exe ancla — sin ancla WSL — .jarvis/memory/lanzador-windows-levanta-motor.md
- tmux ABSORBE DECCKM y mouse-tracking en flags de pane (no los reenvía por %output); un poller re-enuncia a xterm los cambios post-seed, sin él las flechas/el clic mueren en los menús del agente. — .jarvis/memory/modos-privados-sync-vivo.md
- memoria/mailbox/puertos/live salen de plotspace/protocolos/*.md y los DOS motores leen la misma fuente; duplicarlos hace que cada agente reciba instrucciones distintas según quién le armó la sesión — .jarvis/memory/protocolo-fuente-unica.md
- la foto que el motor manda al enganchar una card debe llevar los atributos (rows_formatted / capture-pane -e); en texto pelado la pantalla se pinta entera en el color por defecto hasta que el programa — .jarvis/memory/semilla-attach-con-colores.md
- el motor se elige en UN punto por motor (backend() en Python, terminales::motor::hospeda_en_tmux() en Rust); Windows = PTY adentro, Linux/macOS = tmux, y el default por sistema NO se deduce en otro la — .jarvis/memory/motor-seleccion-un-solo-punto.md
- WSL mirrored SÍ entrega los puertos nuevos a Windows — el bloqueo real era el firewall de Hyper-V en Block; y el NOMBRE localhost resuelve IPv6-first, usar 127.0.0.1 — .jarvis/memory/wsl-mirrored-puertos-firewall.md
- var(--token-que-no-existe) sin fallback invalida la declaración entera — el menú ⋯ salió transparente y sin contorno por pedir --ob-surface-2 / --ob-border / --ob-text, que nunca existieron. — .jarvis/memory/tokens-css-inexistentes-invalidan.md
- el listener de cierre-por-click-afuera corre en mousedown, ANTES del click del disparador — cierra y el click reabre, así que el segundo click en el botón parece no hacer nada. — .jarvis/memory/popover-toggle-mousedown-click.md
- medido 2026-08-02 — 74 mensajes entre DOS agentes (mayoría re-verificación cruzada y acuses), 34% del tráfico sin destino, entrega idle promedio 64 min; de ahí salen las reglas 8/9 del protocolo jv y  — .jarvis/memory/coordinacion-costo-medido.md
- Antes de apagar/borrar/matar un recurso compartido, el código tiene que SABER si fue él quien lo creó — si esa condición vive en la doc como "responsabilidad del llamador", tarde o temprano el llamado — .jarvis/memory/apagar-solo-lo-que-prendiste.md
<!-- JARVIS_LECCIONES_END -->
