# sections/orchestrator/ — panel del orquestador

UI del chat con el orquestador (mensajes, estado, mic). La **lógica** de envío,
grabación y TTS la provee el shell (`workspace.js`) vía callbacks `window._orchOn*`.

- **Archivos:** `orchestrator.js`, `orchestrator.css`
- **Servido en:** `/static/sections/orchestrator/`
- **Global público:** `window.jarvisPanel` (la instancia del panel). El shell
  agrega mensajes y cambia estado vía la instancia directa
  (`jarvisPanel.addMessage(...)` / `jarvisPanel.setSphereState(state)`).
- **Consume del shell:** `window._orchOnSend`, `_orchOnMicHold`, `_orchOnMicRelease`,
  `_orchGetFiles`, `_orchOnHeaderAction` (los define `workspace.js`). No reimplementar
  acá la lógica de red/voz: solo UI.

## Chrome del orquestador (rediseño CONSTELACIÓN 2026-07-04)
Diseño elegido por el usuario entre 4 conceptos (galería `/static/preview-orquestador/`,
concepto D4). Jarvis es el **nodo central de una red neuronal viva** que reacciona a la voz.
- **Constelación** (`<canvas class="orch-net">`, fondo del panel): ~62 nodos de posición fija
  (PRNG determinista) unidos por aristas; el central late. Al escuchar, ondas radiales recorren
  la red y encienden nodos, y la red vira a cian. La reactividad a la voz REAL viene de
  `window._orchVoiceLevel` + `_orchVoiceBins` (0..64), que **publica `workspace.js`** desde el
  AnalyserNode del PTT (`_iniciarWaveform`). El rAF vive en `_initConstellation()`; respeta
  `prefers-reduced-motion` y se apaga si el panel está oculto (`clientWidth===0`).
- **Header**: la marca **Jarvis** (orbe + serif italic) va centrada y prominente ARRIBA. Sin chip
  de estado ("EN REPOSO"), sin botones de historial/nueva-sesión sueltos — esas acciones viven en
  el menú `⋯` (`onHeaderAction('new-thread'|'history'|'export'|'workflows'|'clear-history')`).
  El estado se comunica por el color de la constelación + el `.orch-orb` (`data-state` sobre
  `.orch-panel`: idle/listening/processing/responding). El **menú `⋯` y sus opciones** son
  **LIQUID GLASS** (2026-07-06): base OPACA `background-color` (NO `background-image` gradiente:
  con `backdrop-filter` no se pinta) + aurora + canto + gloss (`::before`) + bisel; item-hover =
  lozenge de vidrio líquido. **`.orch-panel > header` lleva `z-index:40`** para que el menú
  desplegado pinte SOBRE los mensajes/hero — antes lo tapaban (mismo `z-index:1` + más tarde en el
  DOM ganaban al `z-index:300` del menú, atrapado en el contexto del header). Ver
  [[orquestador-liquid-glass-menu-chips]].
- **Hero** (empty state, `.orch-empty`): eyebrow "Red de agentes" + saludo GIGANTE serif
  "¿Qué hacemos, señor?" que pisa la red + 3 quick actions **LIQUID GLASS** (`.orch-hero-chip`:
  translúcido de doble capa + gloss `::before` + bisel; hover = canto de acento + halo) (→ `onQuickReply`). El saludo escala
  con el ANCHO del panel (`container-type: inline-size` + `cqw`; `max-width` en `cqw`, NO en `%`
  —el `%` se ataba al padre encogido y lo partía). Al llegar el 1er mensaje se reemplaza por el
  chat (`_syncConv()` togglea `data-conv` → atenúa la red para legibilidad).
- **El saludo ES el hero, NO una burbuja** (`_isHeroState()`): `workspace.js` inyecta el saludo de
  bienvenida como un MENSAJE (`setMessages([{content:'¿Qué hacemos, señor?'}])` / `nuevoThread`). Un
  chat que es SOLO ese saludo se renderiza como el HERO (constelación brillante + saludo gigante),
  hasta que haya un turno REAL del usuario. Detecta por `id` `'welcome-*'` o por contenido (ES/EN).
  Sin esto el hero NO se veía nunca en la app real (siempre había el mensaje de bienvenida). El
  saludo del hero SÍ se traduce por idioma (es DOM normal, no burbuja con `data-i18n-skip`).
- **Estado de voz del hero** (`_updateHeroVoice`, togglea `.orch-empty[data-voice]`): con el hero
  a la vista, al ESCUCHAR el saludo se reemplaza por "Te estoy escuchando…" + el transcript en
  vivo (lo lee del `$textarea`, donde `workspace.js` vuelca el STT parcial — NO toca el pipeline
  de voz); al PROCESAR → "Pensando". Reacciona a `setSphereState`. El eco del transcript corre en
  un rAF que se corta solo si el nodo se desconecta (hero → chat).
- **Telemetría** (`.orch-telemetry`, ABAJO, FUNDIDA con el composer como una sola base de instrumentos
  — sin border-top/backdrop propios): `● RED <nodos> · AGENTES <pasos> · COSTO $`, con micro-punto vivo
  (`.orch-tl-net-dot`) que late. El costo lo refresca `_refrescarUso()` (→ `#orch-tl-cost`); AGENTES =
  pasos pending/running.
- **Composer** (rediseño ELITE 2026-07-06 — SIN el rectángulo de foco): barra INTEGRADA a la superficie
  del panel, NO una caja/píldora encajonada. `.orch-input-box` flex row (iconos adjuntar/mención/slash ·
  `$textarea` · enviar) sin borde ni ring: el foco se marca con una **hairline de acento** que se enciende
  de centro→afuera (`.orch-input-box::after`, la firma de movimiento), NUNCA con un rectángulo alrededor.
  **CLAVE:** `.orch-textarea:focus` mata explícitamente el focus-ring GLOBAL de teclado (`shared/tokens.css`
  `:where(...textarea...):focus-visible` le dibuja un `box-shadow` rectangular = EL "rectángulo" que el
  usuario rechaza como AI slop). El campo NO muestra scrollbar (`scrollbar-width:none` + `::-webkit-scrollbar`):
  al crecer el texto hasta `max-height`, el scroll sigue al cursor SIN barra. SIN selector de idioma ni botón
  de mic (voz por PTT global). STT parcial cian itálico vía `.orch-textarea.live-transcript`. Grabando
  (`[data-recording]`) → la hairline vira a cian y respira (sin caja). Ver [[orquestador-composer-sin-rectangulo]].
- **i18n ES⇆EN**: todo el chrome se escribe en español y traduce vía `shared/i18n-dict.js`
  (el motor observa el DOM). El contenido dinámico del chat lleva `data-i18n-skip`.
- **Chat editorial** (rediseño ELITE 2026-07-06 — menos cajas): **Jarvis habla SIN burbuja-caja**
  (`background:none`, texto directo anclado por su ORBE-avatar glowing + `text-shadow` para legibilidad
  sobre la red, que baja a `.30` con `data-conv`). Usuario = píldora de vidrio violeta SUTIL SIN borde
  duro (bisel superior `inset`, no marco). Action-plan con borde en gradiente (padding-box/border-box).
  La razón: el usuario rechaza los rectángulos/cajas (AI slop) — el chat elimina las cajas donde puede.
- Al agregar lógica de estado, usar `setSphereState(state)` con los valores definidos.

## Responsive: panel lateral ↔ pantalla completa (2026-07-04)
`.orch-panel` es CONTENEDOR de consulta (`container-type:inline-size`): el layout
florece con el ANCHO DEL PANEL, no del viewport, así se adapta igual angosto o
fullscreen. Al tocar el chrome, respetá los tiers (`orchestrator.css`, sección
RESPONSIVE al final):
- **base (angosto, dock ~300-320px)**: chat compacto — es el estado por defecto, NO lo rompas.
- **≥600cqw**: la conversación se centra en una columna de lectura (los `.orch-messages > *`
  toman `max-width` + `margin-inline:auto`) y el composer se vuelve una barra centrada
  (sus hijos toman `max-width`). Sin esto, a full width las burbujas se estiran de punta a
  punta y el composer deja el placeholder a la izq / el botón al borde.
- **≥960cqw (fullscreen)**: editorial d4 pleno (más aire, input tipo pill).
- El saludo escala fluido `clamp(2.05rem … 5.4rem)` por `cqw` (antes topaba en 3.4rem).
- **Maximizable**: `panel.js` incluye `'jarvis'` en `MAXIMIZABLE` → el ⤢ "Pantalla completa"
  del dock aparece en el tab Jarvis y lo despliega a `fixed inset:0`. La constelación (canvas)
  se re-dimensiona sola vía ResizeObserver.

## Verificación
Smoke manual en `localhost:3000`: enviar mensaje, ver respuesta, estado del orbe en header,
mic. Subir `?v=N` de `orchestrator.js`/`.css` en `shell/workspace.html`.
