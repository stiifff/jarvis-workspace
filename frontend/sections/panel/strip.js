'use strict';
// Lógica pura del toggle de la franja. La parte DOM/localStorage vive en
// workspace.js (toggleStrip). Acá solo la transición de estado, testeable.
(function (global) {
  const pure = {
    nextStripHidden(current, action) {
      if (action === 'toggle') return !current;
      if (action === 'show')   return false;
      if (action === 'hide')   return true;
      return current;
    },
  };
  global.JarvisStrip = pure;
  if (typeof module !== 'undefined' && module.exports) module.exports = pure;
})(typeof window !== 'undefined' ? window : globalThis);
