"""Smoke del helper scripts/reiniciar-server.sh: existe, es ejecutable, su
sintaxis bash es válida y reinicia vía POST /api/system/restart (el re-exec
in-place que conserva el server en la terminal del usuario) — anti-regresión
al camino viejo de pkill + relanzar."""
import os
import subprocess

_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'scripts', 'reiniciar-server.sh',
)


def test_existe_y_es_ejecutable():
    assert os.path.isfile(_SCRIPT)
    assert os.access(_SCRIPT, os.X_OK)


def test_sintaxis_bash_valida():
    r = subprocess.run(['bash', '-n', _SCRIPT], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_usa_el_endpoint_de_restart_y_no_pkill():
    with open(_SCRIPT, encoding='utf-8') as f:
        contenido = f.read()
    assert '/api/system/restart' in contenido
    # pkill solo puede aparecer mencionado en comentarios, nunca como comando
    for linea in contenido.splitlines():
        codigo = linea.split('#', 1)[0]
        assert 'pkill' not in codigo, f'pkill como comando en: {linea!r}'


# ── El re-exec en Windows ────────────────────────────────────────────────
# `os.execv` en Windows no reemplaza el proceso: lanza uno nuevo y mata el
# viejo. El padre (el shell de escritorio que corre el motor como sidecar) ve
# morir a su hijo y puede darlo por caído. Por eso allá el relanzamiento es
# explícito y desprendido.

def test_en_unix_se_conserva_el_execv(monkeypatch):
    """El camino que funciona hace meses no se toca."""
    from plotspace.routers import system
    import inspect
    src = inspect.getsource(system._reexec)
    assert 'os.execv(sys.executable' in src
