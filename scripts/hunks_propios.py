#!/usr/bin/env python3
"""Filtrado de un `git diff -U0` para quedarse SOLO con los hunks propios.

POR QUÉ
-------
Todos los agentes trabajan sobre la misma rama y el mismo working tree, así que
`git add <archivo>` no significa "lo mío": arrastra el archivo ENTERO con el
trabajo sin commitear del otro adentro. Ya pasó, y quedó documentado en el
MAILBOX del proyecto: un agente filtró sus hunks por NÚMERO DE LÍNEA («los míos
están arriba de la 4400») y se llevó puesta una función ajena que vivía en la
5739, porque las zonas están intercaladas, no en bloques por agente.

La conclusión a la que llegaron a los golpes es la correcta: filtrar por
CONTENIDO y con `-U0` (hunks mínimos; con -U3 se pega la línea del vecino). Lo
que faltaba era el DATO — saber qué texto escribió cada uno. Eso ahora lo tiene
el libro de provenance (`plotspace/core/provenance.py`), alimentado por el hook
del CLI.

INVARIANTE DE ORO
-----------------
Ante la duda, el hunk NO es mío. Dejar afuera un cambio propio cuesta un segundo
commit; llevarse uno ajeno le borra el trabajo a otro agente.

Stdlib pura (como guard_propiedad.py): los hooks y el script de commit tienen
que andar aunque el venv no esté activado.
"""
import re

# Líneas demasiado comunes para atribuir un hunk a nadie: aparecen en el diff
# de cualquiera. Sin esto, un hunk que solo cierra una llave se lo lleva el
# primero que pase.
_TRIVIALES = {'', '}', '{', '};', ')', '(', '),', '];', '[', ']', ',', ';',
              '*/', '/*', '"""', "'''", 'return', 'pass', 'else:', 'else {',
              '});', '})', '>', '<div>', '</div>'}
_LARGO_MIN = 8          # menos que esto no identifica a nadie

_RE_HUNK = re.compile(r'^@@ ', re.MULTILINE)


def _significativa(linea: str) -> bool:
    s = linea.strip()
    return len(s) >= _LARGO_MIN and s not in _TRIVIALES


def partir_diff(diff_texto):
    """(cabecera, [hunk, ...]). La cabecera son las líneas `diff --git`/`---`/
    `+++`/`index` que git necesita para saber a qué archivo aplicar."""
    texto = diff_texto or ''
    if not texto:
        return '', []
    pos = [m.start() for m in _RE_HUNK.finditer(texto)]
    if not pos:
        return texto, []
    cabecera = texto[:pos[0]]
    hunks = []
    for i, inicio in enumerate(pos):
        fin = pos[i + 1] if i + 1 < len(pos) else len(texto)
        hunks.append(texto[inicio:fin])
    return cabecera, hunks


def _lineas(hunk: str, signo: str):
    otro = '-' if signo == '+' else '+'
    out = []
    for linea in (hunk or '').splitlines()[1:]:      # [0] es el `@@ ... @@`
        if not linea.startswith(signo):
            continue
        if linea.startswith(signo * 3) or linea.startswith(otro * 3):
            continue                                 # '+++ b/x' / '--- a/x'
        out.append(linea[1:].strip())
    return out


def lineas_agregadas(hunk):
    return _lineas(hunk, '+')


def lineas_quitadas(hunk):
    return _lineas(hunk, '-')


def _aparece(linea: str, fragmentos) -> bool:
    """¿Esta línea está adentro de algún fragmento que escribió el agente?
    Se compara SIN indentación: el CLI reporta el texto tal cual lo insertó, y
    un reformateo posterior no debe romper la atribución."""
    objetivo = linea.strip()
    if not objetivo:
        return False
    for f in fragmentos or ():
        if not f:
            continue
        if objetivo in f:
            return True
        # comparación línea a línea, tolerante a indentación
        if any(objetivo == l.strip() for l in str(f).splitlines()):
            return True
    return False


def hunk_es_mio(hunk, fragmentos_mios, fragmentos_ajenos=()) -> bool:
    """¿Este hunk lo produje YO? Requiere evidencia positiva y ausencia de
    evidencia ajena — un hunk mezclado se deja afuera a propósito."""
    agregadas = [l for l in lineas_agregadas(hunk) if _significativa(l)]
    quitadas = [l for l in lineas_quitadas(hunk) if _significativa(l)]
    candidatas = agregadas or quitadas          # un hunk que solo borra vale
    if not candidatas:
        return False
    if any(_aparece(l, fragmentos_ajenos) for l in candidatas):
        return False                            # ambiguo o directamente ajeno
    return any(_aparece(l, fragmentos_mios) for l in candidatas)


def filtrar_parche(diff_texto, fragmentos_mios, fragmentos_ajenos=()):
    """Parche aplicable con `git apply --cached --unidiff-zero` que contiene
    SOLO mis hunks, o None si no hay ninguno."""
    cabecera, hunks = partir_diff(diff_texto)
    mios = [h for h in hunks if hunk_es_mio(h, fragmentos_mios, fragmentos_ajenos)]
    if not mios:
        return None
    parche = cabecera + ''.join(mios)
    return parche if parche.endswith('\n') else parche + '\n'
