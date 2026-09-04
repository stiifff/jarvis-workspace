"""
Test: fix del tmux size-clamping por clientes zombie (síntoma "puntitos").

El bug: `tmux resize-window -x -y` pone la ventana en `window-size manual`, lo
que la clava chica y anula el global `latest`; con un segundo cliente más chico
attacheado (pestaña vieja / ptyprocess huérfano de un reinicio) tmux dimensiona
al menor y rellena el sobrante con '·'. Estos tests fijan los invariantes del
fix sin requerir un tmux real (se mockea subprocess.run).
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


def test_crear_sesion_setea_window_size_latest():
    """Al crear la sesión se setea window-size latest por-sesión (no se confía
    en el global, porque cualquier resize-window lo volvería manual)."""
    with mock.patch.object(term, "_sesion_tmux_existe", return_value=False), \
         mock.patch.object(_tb.TmuxBackend, "existe", return_value=False), \
         mock.patch.object(term.os.path, "isdir", return_value=True), \
         mock.patch.object(term, "_instalar_bindings_copy_mode"), \
         mock.patch.object(term, "_aplicar_estilo_obsidian_tmux"), \
         mock.patch.object(term.subprocess, "run") as m:
        m.return_value = mock.Mock(returncode=0, stderr="", stdout="")
        asyncio.run(term._crear_sesion_tmux(999, "/tmp/x"))

    calls = _run_calls(m)
    assert any(
        c[:2] == ["tmux", "set-option"] and "window-size" in c and "latest" in c
        and "jarvis_999" in c
        for c in calls
    ), f"no se seteó window-size latest en la sesión. Calls: {calls}"


def test_tmux_resize_no_usa_resize_window():
    """_tmux_resize NUNCA debe llamar resize-window (forzaría window-size manual
    y reintroduciría el clamping). Solo refresh-client para repintar."""
    # list-clients devuelve un tty fake (sino _refresh_clientes_sesion no refresca);
    # el resto de comandos tmux devuelven vacío.
    def _fake_run(args, **kw):
        a = list(args)
        if "list-clients" in a:
            return mock.Mock(returncode=0, stdout="/dev/pts/7\n", stderr="")
        return mock.Mock(returncode=0, stdout="", stderr="")
    with mock.patch.object(term.subprocess, "run", side_effect=_fake_run) as m:
        asyncio.run(term._tmux_resize(999, 200, 50))

    calls = _run_calls(m)
    assert not any("resize-window" in c for c in calls), \
        f"_tmux_resize usó resize-window (rompe el fix). Calls: {calls}"
    assert any("refresh-client" in c for c in calls), \
        f"_tmux_resize debería refrescar el cliente (por tty). Calls: {calls}"


def test_tmux_resize_ignora_tamanos_degenerados():
    """Tamaños sub-legibles no disparan ningún comando tmux."""
    with mock.patch.object(term.subprocess, "run") as m:
        asyncio.run(term._tmux_resize(999, 10, 3))
    assert m.call_count == 0


if __name__ == "__main__":
    test_crear_sesion_setea_window_size_latest()
    test_tmux_resize_no_usa_resize_window()
    test_tmux_resize_ignora_tamanos_degenerados()
    print("OK")
