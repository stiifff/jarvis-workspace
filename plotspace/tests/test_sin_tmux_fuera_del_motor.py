"""tmux solo puede invocarse desde el motor de tmux.

POR QUÉ ESTE TEST EXISTE
=======================
La app de Windows trae su propio motor de terminales (el termhost, ConPTY) y
**en Windows no existe el binario `tmux`**. Cualquier módulo que lo llame
directo, en vez de pasar por `backend()`, se rompe ahí: con suerte falla en
silencio y la feature queda muerta sin explicación (los pollers capturan la
salida y siguen), con menos suerte tira FileNotFoundError.

Y es una regresión BARATA de cometer: escribir `subprocess.run(['tmux', ...])`
es más corto que buscar el método del backend, funciona perfecto en la máquina
de desarrollo —que es Linux— y no lo nota nadie hasta que alguien abre la app
en Windows.

LA REGLA
========
`tmux` se invoca ÚNICAMENTE desde los módulos que IMPLEMENTAN el motor tmux.
El resto del motor pide las cosas por la interfaz (`backend()`), que en Windows
resuelve al termhost y en Linux a tmux.

Si este test te frena: no agregues tu módulo a la lista de abajo. Buscá el
método que corresponde en `core/terminal_backend.py` — capturar, enviar_texto,
listar_sesiones, estado_pane, matar_sesion_por_nombre… están casi todos.
"""
import ast
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Los ÚNICOS que pueden hablar tmux: son la implementación del motor tmux.
# Esta lista no crece. Si tu módulo necesita algo de una terminal, lo pide por
# `backend()` — que es justamente lo que hace que la app de Windows funcione.
IMPLEMENTAN_TMUX = {
    os.path.join('core', 'terminal_backend.py'),   # TmuxBackend
    os.path.join('core', 'control_mode.py'),       # attach por tmux control-mode
}

LLAMADAS = {'run', 'Popen', 'call', 'check_output', 'check_call',
            'create_subprocess_exec'}

# Marcador para el caso legítimo que no vive en un módulo de tmux: un camino
# que el propio código ya desvía cuando el motor no es tmux (p.ej. el attach,
# que con ConPTY entra por `_sesion_conpty` y nunca llega acá).
#
# Se exime la LLAMADA, no el archivo. Eximir `terminals.py` entero habría
# dejado pasar el monitor de keywords, que sí se rompía en Windows.
MARCA = 'motor-tmux:'
LINEAS_DE_MARCA = 8   # cuántas líneas antes de la llamada se busca


def _invoca_tmux(nodo):
    """¿Este nodo es una llamada a subprocess con 'tmux' como argv[0]?

    Se mira el AST y no el texto: así un comentario que menciona tmux, o un
    string suelto en una docstring, no cuenta — solo la invocación real.
    """
    if not isinstance(nodo, ast.Call):
        return False
    fn = nodo.func
    nombre = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, 'id', None)
    if nombre not in LLAMADAS:
        return False
    for arg in list(nodo.args) + [kw.value for kw in nodo.keywords]:
        # subprocess.run(['tmux', ...])
        if isinstance(arg, (ast.List, ast.Tuple)) and arg.elts:
            p = arg.elts[0]
            if isinstance(p, ast.Constant) and p.value == 'tmux':
                return True
        # create_subprocess_exec('tmux', ...)
        if isinstance(arg, ast.Constant) and arg.value == 'tmux':
            return True
    return False


def _modulos():
    for base, _, archivos in os.walk(RAIZ):
        if 'tests' in base.split(os.sep) or '__pycache__' in base:
            continue
        for a in archivos:
            if a.endswith('.py'):
                ruta = os.path.join(base, a)
                yield os.path.relpath(ruta, RAIZ), ruta


def _eximida(lineas, lineno):
    """¿La llamada de `lineno` lleva la marca `motor-tmux:` justo arriba?"""
    desde = max(0, lineno - 1 - LINEAS_DE_MARCA)
    return any(MARCA in l for l in lineas[desde:lineno])


def test_solo_el_motor_de_tmux_invoca_tmux():
    culpables = []
    for rel, ruta in _modulos():
        if rel in IMPLEMENTAN_TMUX:
            continue
        with open(ruta, encoding='utf-8') as f:
            fuente = f.read()
        arbol = ast.parse(fuente, filename=ruta)
        lineas = fuente.splitlines()
        for nodo in ast.walk(arbol):
            if _invoca_tmux(nodo) and not _eximida(lineas, nodo.lineno):
                culpables.append(f'{rel}:{nodo.lineno}')

    assert not culpables, (
        'Estos módulos llaman a tmux directo y por lo tanto NO funcionan en la '
        'app de Windows. Pedilo por backend() en vez de por subprocess:\n  '
        + '\n  '.join(culpables)
    )


def test_el_guard_detecta_de_verdad():
    # Un guard que no puede fallar no protege nada: se verifica contra código
    # que SÍ invoca tmux, en las dos formas que aparecen en el repo.
    for src in ("subprocess.run(['tmux', 'ls'])",
                "await asyncio.create_subprocess_exec('tmux', 'ls')"):
        arbol = ast.parse(src)
        assert any(_invoca_tmux(n) for n in ast.walk(arbol)), src


def test_la_marca_exime_la_llamada_no_el_archivo():
    # La exención tiene que ser por LLAMADA. Si eximiera el archivo, marcar el
    # attach de terminals.py habría tapado también el monitor de keywords —
    # que sí se rompía en Windows y que este guard encontró.
    fuente = (
        "# motor-tmux: este camino no corre con ConPTY\n"
        "subprocess.run(['tmux', 'display'])\n"
        "subprocess.run(['tmux', 'kill-session'])\n"
    )
    lineas = fuente.splitlines()
    arbol = ast.parse(fuente)
    calls = [n for n in ast.walk(arbol) if _invoca_tmux(n)]
    assert len(calls) == 2
    assert _eximida(lineas, calls[0].lineno), 'la marcada tenía que pasar'

    # La segunda está 2 líneas después de la marca — dentro de la ventana. Lo
    # que NO puede pasar es una llamada MUY lejos de la marca.
    lejos = "# motor-tmux: ok\n" + "x = 1\n" * 20 + "subprocess.run(['tmux','ls'])\n"
    ls = lejos.splitlines()
    c = [n for n in ast.walk(ast.parse(lejos)) if _invoca_tmux(n)][0]
    assert not _eximida(ls, c.lineno), 'una marca lejana no puede eximir'


def test_el_guard_no_se_dispara_por_mencionar_tmux():
    # Un comentario, una docstring o un string suelto no son una invocación.
    for src in ("x = 'tmux'", "def f():\n    '''usa tmux'''\n    return 1",
                "subprocess.run(['ls', 'tmux'])"):
        arbol = ast.parse(src)
        assert not any(_invoca_tmux(n) for n in ast.walk(arbol)), src
