"""
Test: las sesiones tmux nuevas lanzan Claude Code en modo FULLSCREEN
(CLAUDE_CODE_NO_FLICKER=1) y ya NO fuerzan el inline.

Historia (para no repetirla): el inline forzado
(CLAUDE_CODE_DISABLE_ALTERNATE_SCREEN=1, 2026-07-02 a la mañana) daba
selección+scroll local nativos, pero re-expuso la física de las TUIs inline:
lo que cae al scrollback es INBORRABLE para la app, así que cada resize con
transcript largo re-imprimía TODO al ancho nuevo dejando la copia vieja
arriba — el "texto multiplicado y cortado al maximizar" del video del usuario
(2026-07-02 23:12). El fullscreen oficial (v2.1.89+, la "bala de plata"
3661136 que se llevó el revert masivo 4cabb53) contiene el transcript en
alt-screen: nada cae jamás al scrollback y la rueda scrollea el transcript
real de Claude. Trade-off aceptado por el usuario: el modal Historial ve
menos profundidad para claude. Escape hatch: JARVIS_CLAUDE_FULLSCREEN=off.

Se inyecta con `-e` en new-session (mismo mecanismo que CODEX_HOME): cubre
el auto-launch Y un `claude` tipeado a mano en una terminal Shell aunque el
server tmux ya existiera; las demás CLIs ignoran la var.
"""
import os
import sys

import pytest
import asyncio
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import plotspace.routers.terminals as term
# El chequeo de "¿ya existe la sesión?" lo hace ahora el motor
# (core/terminal_backend), no `term`: el mock de subprocess devuelve rc=0
# para todo, así que hay que decirle al motor que la sesión NO existe.
import plotspace.core.terminal_backend as _tb

# Estos tests verifican el argv EXACTO de tmux: desde F5·2 el default es el
# termhost, así que hay que pedir ese motor explícitamente (ver conftest).
pytestmark = pytest.mark.usefixtures('motor_tmux')



def _run_calls(mock_run):
    """Lista de argv de cada subprocess.run(['tmux', ...]) capturado."""
    calls = []
    for c in mock_run.call_args_list:
        argv = c.args[0] if c.args else c.kwargs.get("args")
        if isinstance(argv, (list, tuple)):
            calls.append(list(argv))
    return calls


def _new_session_argv(monkeyenv=None):
    with mock.patch.object(term, "_sesion_tmux_existe", return_value=False), \
         mock.patch.object(_tb.TmuxBackend, "existe", return_value=False), \
         mock.patch.object(term.os.path, "isdir", return_value=True), \
         mock.patch.object(term, "_instalar_bindings_copy_mode"), \
         mock.patch.object(term, "_aplicar_estilo_obsidian_tmux"), \
         mock.patch.object(term.subprocess, "run") as m:
        m.return_value = mock.Mock(returncode=0, stderr="", stdout="")
        asyncio.run(term._crear_sesion_tmux(999, "/tmp/x"))
    calls = _run_calls(m)
    new_sessions = [c for c in calls if c[:2] == ["tmux", "new-session"]]
    assert new_sessions, f"no hubo new-session. Calls: {calls}"
    return new_sessions[0]


def test_crear_sesion_claude_fullscreen():
    """new-session lleva -e CLAUDE_CODE_NO_FLICKER=1 y NO lleva más el viejo
    -e CLAUDE_CODE_DISABLE_ALTERNATE_SCREEN=1 (el inline forzado era la causa
    del texto multiplicado/cortado al redimensionar)."""
    os.environ.pop("JARVIS_CLAUDE_FULLSCREEN", None)
    ns = _new_session_argv()
    assert "CLAUDE_CODE_NO_FLICKER=1" in ns and \
        ns[ns.index("CLAUDE_CODE_NO_FLICKER=1") - 1] == "-e", \
        f"new-session sin -e CLAUDE_CODE_NO_FLICKER=1. Argv: {ns}"
    assert "CLAUDE_CODE_DISABLE_ALTERNATE_SCREEN=1" not in ns, \
        f"el inline forzado tiene que estar RETIRADO. Argv: {ns}"


def test_crear_sesion_fullscreen_escape_hatch():
    """JARVIS_CLAUDE_FULLSCREEN=off deja a claude con su default (sin -e)."""
    os.environ["JARVIS_CLAUDE_FULLSCREEN"] = "off"
    try:
        ns = _new_session_argv()
        assert "CLAUDE_CODE_NO_FLICKER=1" not in ns, f"Argv: {ns}"
    finally:
        os.environ.pop("JARVIS_CLAUDE_FULLSCREEN", None)


if __name__ == "__main__":
    test_crear_sesion_claude_fullscreen()
    test_crear_sesion_fullscreen_escape_hatch()
    print("OK")
