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
   {CATEGORIAS}. Si dudás, Jarvis la infiere por los tags;
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