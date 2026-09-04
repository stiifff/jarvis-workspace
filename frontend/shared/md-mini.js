// JARVIS — mini renderer de Markdown para el chat del Builder agéntico.
//
// El agente (claude real) escribe su prosa en markdown (**negrita**, `código`,
// listas, ## títulos, [links]). El chat lo streamea y lo tiene que mostrar
// lindo. No metemos una lib: esto es un renderer chico y seguro
// (escapa el HTML ANTES de transformar, así el `<!doctype html>` que el modelo
// menciona se ve literal y no ejecuta nada). La lógica es pura → se testea en
// Node (md-mini.test.js). Sin estado, sin DOM.
(function (global) {
  'use strict';

  // Centinela para proteger el código inline: un char de uso privado (PUA)
  // computado en runtime (fuente ASCII, no frágil) — imposible en texto real.
  var SENT = String.fromCharCode(0xE000);

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }

  // Inline sobre texto YA escapado: código > negrita > itálica > links.
  function inline(s) {
    var codes = [];
    s = s.replace(/`([^`]+)`/g, function (_, c) {
      codes.push(c); return SENT + (codes.length - 1) + SENT;
    });
    s = s.replace(/\*\*([^*]+?)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/(^|[^*])\*([^*\n]+?)\*(?!\*)/g, '$1<em>$2</em>');
    s = s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, function (m, t, u) {
      // solo http(s), relativo (/…) o ancla (#…) — nada de javascript:
      return /^(https?:\/\/|\/|#)/.test(u)
        ? '<a href="' + u + '" target="_blank" rel="noopener noreferrer">' + t + '</a>'
        : t;
    });
    s = s.replace(new RegExp(SENT + '(\\d+)' + SENT, 'g'), function (_, i) {
      return '<code>' + codes[+i] + '</code>';
    });
    return s;
  }

  var RE_H = /^(#{1,6})\s+(.*)$/;
  var RE_UL = /^\s*[-*]\s+/;
  var RE_OL = /^\s*\d+\.\s+/;
  var RE_BLANK = /^\s*$/;

  function esEspecial(l) { return RE_H.test(l) || RE_UL.test(l) || RE_OL.test(l); }

  function render(md) {
    var lines = esc(md).split('\n');
    var out = [];
    var i = 0;
    while (i < lines.length) {
      var line = lines[i];
      if (RE_BLANK.test(line)) { i++; continue; }
      var h = line.match(RE_H);
      if (h) {
        var lvl = Math.min(5, h[1].length + 2);   // # → h3, ## → h4, ### → h5
        out.push('<h' + lvl + '>' + inline(h[2]) + '</h' + lvl + '>');
        i++; continue;
      }
      if (RE_UL.test(line)) {
        var ul = [];
        while (i < lines.length && RE_UL.test(lines[i])) {
          ul.push('<li>' + inline(lines[i].replace(RE_UL, '')) + '</li>'); i++;
        }
        out.push('<ul>' + ul.join('') + '</ul>'); continue;
      }
      if (RE_OL.test(line)) {
        var ol = [];
        while (i < lines.length && RE_OL.test(lines[i])) {
          ol.push('<li>' + inline(lines[i].replace(RE_OL, '')) + '</li>'); i++;
        }
        out.push('<ol>' + ol.join('') + '</ol>'); continue;
      }
      var para = [];
      while (i < lines.length && !RE_BLANK.test(lines[i]) && !esEspecial(lines[i])) {
        para.push(inline(lines[i])); i++;
      }
      out.push('<p>' + para.join('<br>') + '</p>');
    }
    return out.join('');
  }

  var pure = { render: render, esc: esc, inline: inline };
  if (typeof module !== 'undefined' && module.exports) module.exports = pure;
  global.MdMini = pure;
})(typeof window !== 'undefined' ? window : globalThis);
