# sections/settings/ — pantalla de configuración

Overlay full-screen que cubre el workspace cuando el usuario toca ⚙ (`#jw-gear`).
Rediseño **"Liquid Glass · Datasheet"** (2026-07-19), que reemplaza al
"Observatorio": aquel había cambiado el *tema* sobre la misma estructura genérica
(nav lateral + filas idénticas con toggle); este cambia la **estructura**.

- **Archivos:** `settings.js`, `settings.css`
- **Servido en:** `/static/sections/settings/`
- **Global público:** `window.JarvisSettings` con `init(pid)`, `onProjectChanged(pid)`,
  `open(seccion?)`, `close()`, `isOpen()`, `refrescar(seccion?)` y
  `onCuentaAgregada(data)`. Invocar solo vía esta API.
- **Prototipo de referencia:** `frontend/preview-settings/` (sirve en
  `/static/preview-settings/`) — ahí está el detalle de las decisiones de diseño
  y **qué no reintroducir**.

## Anatomía

Una **sola losa de vidrio** (`.sx-slab`, marco ANCLADO de 1120×790: no cambia de
tamaño entre secciones) con el rail lateral y el cuerpo unidos por una línea de
pelo. El cuerpo es una **ficha técnica**: cada bloque (`.sx-blk`) se anuncia con
su **banda** (`.sx-blk-l`: rótulo mono + pista + regla hasta el canto) y después
el contenido ocupa TODO el ancho. Cero tarjetas anidadas, cero grid de tarjetas
idénticas.

La banda es **sticky**: al scrollear queda pegada arriba y `settings.js` le pone
`.fija` (mide contra el techo del scrollport en un rAF), que enciende la repisa
y sube el rótulo a `--ob-fg-0` — el "estás acá" de la sección. El flag
`{ wide: true }` de `blk()` ya no hace nada (era para romper la canaleta lateral
que se eliminó en 2026-07-22); no hace falta pasarlo en bloques nuevos.

| Sección | id | Forma |
|---|---|---|
| Voz | `voz` | La tecla como objeto físico (keycap) + ruta de la señal + dictado y avisos |
| Teclado | `atajos` | **Mapa de teclado real**: lo iluminado está ocupado, click para reasignar |
| Apariencia | `apariencia` | Banco de pruebas vivo + los 24 temas como **espectro** + tonalidad + idioma |
| Cuentas | `cuentas` | **Conmutador**: un CLI por fila, sus cuentas como botones de un selector |
| Extensiones | `skills` | Rack denso (markup `.ps-*` heredado, re-vestido) |
| Memoria | `memoria` | **Consola**: pulso, altímetro, cuadros por categoría, recientes, lecciones |
| Workflows | `workflows` | Línea de tiempo con el track de pasos |

El rail muestra el **valor vivo** de cada sección (la tecla, el tema, cuántas
cuentas / plugins / memorias / workflows) — se ve la configuración sin entrar.
Los cuatro que dependen del server los trae `_cargarResumen()` al abrir.

## Reglas duras

- **Máximo DOS capas con `backdrop-filter`** (velo + losa). Lo de adentro es
  faux-glass con gradientes.
- **El vidrio ELEVA, no hunde**: las superficies salen del escalón de card
  (`--ob-bg-2/3`, tokens locales `--sx-slab-*`, `--sx-well`), **nunca de
  `--ob-bg-void`** — en los temas más oscuros (tinta L≈9%, neón) eso dejaba un
  pozo negro y leer cansaba.
- **`--ob-fg-4` es solo disabled/placeholder**: ningún texto de esta pantalla
  baja de `--ob-fg-3`.
- **Nada de color hardcodeado** (24 temas + filtro de tonalidad).
- **Nada de `animation-fill-mode: forwards`/`both` en los ancestros de la banda**:
  un transform retenido (aunque sea la matriz identidad) le rompe el
  `position: sticky` a lo de adentro. Por eso `.sx-in > *` usa `backwards`.
- **El espectro de temas no anima layout al pasar el mouse**: hover =
  previsualizar en el banco (variables `--bk-*` inline; NO tocar el `data-theme`
  del documento, eso cambiaría el tema de verdad); el despliegue (`flex-grow`) es
  la respuesta al **click**. `contain: layout paint style` encierra el recálculo.
- **Fuera el serif italic display** de la UI de producto.

## Puentes con el motor real (no renombrar)

- El keycap de Voz y los botones de reasignar **son `.set-keybind[data-id]`**: el
  motor de captura de `workspace.js` los busca por esa clase y les reescribe el
  `innerHTML` mientras captura (`.settings-keybind-listening` / `-hint`). El valor
  va en `.settings-kbd`.
- Extensiones conserva el markup `.ps-*` que cablea `window.JarvisSkills.montar()`;
  se re-viste por CSS, no se reescribe.
- El modal de alta de cuenta (`.cta-alta-*`) mantiene su DOM y sus **4 flujos**
  (manual, device-code, pegar código, callback) + el aborto al cerrar.
- Esc cede a los sub-modales (`#modal-skill-md`, `.cta-alta-overlay`,
  `.ob-confirm-overlay`) y al buscador con texto.

## i18n

Los textos nuevos viven en `shared/i18n-dict.js` (bloque "Configuración ·
rediseño Liquid Glass"). Todo string nuevo de esta pantalla entra ahí o el modo
inglés queda mezclado.

## Verificación

Smoke en `localhost:3000` con `?qa=1` (observador): abrir con ⚙, recorrer las 7
secciones, buscar un ajuste y verificar el salto+pulso, cambiar tema y tonalidad
(que `--ob-accent` computado cambie y persista), reasignar un atajo. **No tocar
"Usar" de una cuenta en QA: cambia la cuenta activa del CLI de verdad.** Subir el
`?v=N` de `settings.js`/`.css` (y de `i18n-dict.js` si se tocó) en
`shell/workspace.html`. Tests: todas las suites de `frontend/**/__tests__` +
`python -m pytest backend/tests/`.
