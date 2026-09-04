'use strict';
// Detección del bloque de input (lo que el usuario está tipeando) en el buffer
// de una terminal, para el gesto Ctrl+A → seleccionar input → copiar/borrar.
// Lógica PURA (sin xterm ni DOM) para poder testearla en node, igual que
// terminal-layout.js. La consume terminal.js (_armarSeleccionInput).
//
// Modelo de entrada:
//   lineas    = [{ text, isWrapped }]  filas del buffer en orden (ventana)
//   cursorRow = índice (dentro de lineas) de la fila donde está el cursor
//   tipo      = tipo de terminal ('manual' = bash; resto = TUIs de agente)
//
// El cursor SIEMPRE vive dentro del input (la TUI lo posiciona ahí), así que
// el bloque se ancla buscando desde el cursor: hacia arriba hasta el glifo de
// prompt (❯ Claude, › Codex, > Gemini/Qwen) y hacia abajo por continuaciones.

// Glifo de prompt al inicio de la fila (con o sin texto después)
const PROMPT_RE = /^\s*[❯›>](?:\s|$)/;
// Filas de marco/separador de las TUIs (bordes de caja, separadores).
// Incluye ┃ (U+2503, borde izquierdo de OpenCode) además del │ fino (U+2502).
const BORDE_RE = /^\s*[─╭╰│╮╯═┃]/;
// Tope de filas a escanear hacia arriba buscando el ancla del prompt
const MAX_SCAN = 40;

function detectarBloqueInput(lineas, cursorRow, tipo) {
  if (!Array.isArray(lineas) || lineas.length === 0) return null;
  const last = lineas.length - 1;
  const cur = Math.max(0, Math.min(cursorRow, last));

  // 1) Subir a través de filas envueltas (línea lógica larga que wrapeó).
  let start = cur;
  while (start > 0 && lineas[start].isWrapped) start--;

  if (tipo === 'manual') {
    // bash: la línea lógica del cursor, incluyendo sus wraps hacia abajo.
    let end = cur;
    while (end < last && lineas[end + 1].isWrapped) end++;
    return { start, end };
  }

  // 2) TUIs: subir hasta la fila ancla con glifo de prompt. Un borde de caja
  //    en el camino significa que nos fuimos del bloque de input: fallback a
  //    lo que ya teníamos (la línea lógica del cursor).
  if (!PROMPT_RE.test(lineas[start].text)) {
    for (let r = start - 1, n = 0; r >= 0 && n < MAX_SCAN; r--, n++) {
      const t = lineas[r].text;
      if (BORDE_RE.test(t)) break;
      if (PROMPT_RE.test(t)) {
        // Anti falso-ancla: el output del agente puede tener líneas que
        // empiezan con > (citas markdown). Solo aceptamos el ancla si TODAS
        // las filas entre ella y el punto de partida parecen continuación
        // de input (wrap o sangría de 2) — en el input real siempre lo son.
        let contiguo = true;
        for (let k = r + 1; k <= start; k++) {
          if (!(lineas[k].isWrapped || /^\s{2}\S/.test(lineas[k].text))) { contiguo = false; break; }
        }
        if (contiguo) start = r;
        break;
      }
    }
  }

  // 3) Bajar por continuaciones del input: filas envueltas (wrap) o líneas
  //    nuevas del multilínea (sangría de 2 espacios en Claude Code). Un borde
  //    o una fila no-continuación cortan el bloque.
  let end = cur;
  for (let r = cur + 1; r <= last; r++) {
    const t = lineas[r].text;
    if (BORDE_RE.test(t)) break;
    if (lineas[r].isWrapped || /^\s{2}\S/.test(t)) { end = r; continue; }
    break;
  }
  return { start, end };
}

// Extrae el texto "limpio" del bloque para copiar: pela el glifo de prompt
// (TUI) o el prompt de bash (heurístico hasta '$ '/'# '), quita la sangría de
// continuación, y une: filas wrapeadas sin salto, líneas lógicas con \n.
function extraerTextoInput(lineas, bloque, tipo) {
  if (!bloque) return '';
  const partes = [];
  for (let r = bloque.start; r <= bloque.end; r++) {
    let t = lineas[r].text;
    if (r === bloque.start) {
      t = tipo === 'manual'
        ? t.replace(/^.*?[$#]\s/, '')
        : t.replace(PROMPT_RE, '');
    } else if (!lineas[r].isWrapped) {
      t = t.replace(/^\s{2}/, '');
    }
    if (lineas[r].isWrapped && partes.length) partes[partes.length - 1] += t;
    else partes.push(t);
  }
  return partes.join('\n').replace(/\s+$/, '');
}

const TerminalInputBlock = { detectarBloqueInput, extraerTextoInput };
if (typeof module !== 'undefined' && module.exports) module.exports = TerminalInputBlock;
if (typeof window !== 'undefined') window.TerminalInputBlock = TerminalInputBlock;
