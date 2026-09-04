"""
Test: la status bar de tmux (la barra verde de abajo «[jarvis_<id>:claude] …
reloj») queda APAGADA por-sesión, no solo vía el global con guard.

El bug en vivo: `_aplicar_estilo_obsidian_tmux` apaga la barra con `set -g
status off` pero tiene un guard «una vez por proceso» (_ESTILO_OBSIDIAN_APLICADO).
Si el SERVER de tmux se reinicia mientras el proceso de Python sigue vivo, los
globales de tmux vuelven al default (`status on`) y el guard ya está en True →
la barra verde reaparece y nunca se vuelve a apagar. El fix: apagar `status`
POR SESIÓN (barato, garantizado, independiente del global y del guard) tanto al
crear la sesión como al reconciliar las sesiones vivas en el arranque.
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


def _setea_status_off(calls, sesion):
    return any(
        c[:2] == ["tmux", "set-option"] and sesion in c
        and "status" in c and "off" in c
        for c in calls
    )


def test_crear_sesion_apaga_status_bar():
    """Al crear la sesión se apaga la status bar POR SESIÓN (no se confía solo
    en el global, que un reinicio del server tmux resetea a `status on`)."""
    with mock.patch.object(term, "_sesion_tmux_existe", return_value=False), \
         mock.patch.object(_tb.TmuxBackend, "existe", return_value=False), \
         mock.patch.object(term.os.path, "isdir", return_value=True), \
         mock.patch.object(term, "_instalar_bindings_copy_mode"), \
         mock.patch.object(term, "_aplicar_estilo_obsidian_tmux"), \
         mock.patch.object(term.subprocess, "run") as m:
        m.return_value = mock.Mock(returncode=0, stderr="", stdout="")
        asyncio.run(term._crear_sesion_tmux(999, "/tmp/x"))

    calls = _run_calls(m)
    assert _setea_status_off(calls, "jarvis_999"), \
        f"no se apagó la status bar por-sesión al crear. Calls: {calls}"


def test_reconciliar_apaga_status_en_sesiones_vivas():
    """Al reconciliar en el arranque, toda sesión jarvis_* viva queda con la
    status bar apagada (cubre sesiones que sobrevivieron a un reinicio del
    server tmux con el global en `status on`)."""
    # DB sin terminales activas → el reconcile no recrea nada, solo sanea vivas.
    fake_conn = mock.Mock()
    fake_cursor = mock.Mock()
    fake_cursor.fetchall.return_value = []
    fake_conn.cursor.return_value = fake_cursor

    def _fake_run(args, **kw):
        a = list(args)
        if "list-sessions" in a:
            return mock.Mock(returncode=0, stdout="jarvis_790\njarvis_791\notra_x\n", stderr="")
        return mock.Mock(returncode=0, stdout="", stderr="")

    with mock.patch.object(term, "get_db", return_value=fake_conn), \
         mock.patch.object(term, "_aplicar_estilo_obsidian_tmux"), \
         mock.patch.object(term.subprocess, "run", side_effect=_fake_run) as m:
        asyncio.run(term.reconciliar_sesiones_tmux())

    calls = _run_calls(m)
    assert _setea_status_off(calls, "jarvis_790"), \
        f"no se apagó la status bar en jarvis_790. Calls: {calls}"
    assert _setea_status_off(calls, "jarvis_791"), \
        f"no se apagó la status bar en jarvis_791. Calls: {calls}"
    # Sesiones que no son de jarvis NO se tocan.
    assert not _setea_status_off(calls, "otra_x"), \
        f"no debería tocar sesiones ajenas (otra_x). Calls: {calls}"


if __name__ == "__main__":
    test_crear_sesion_apaga_status_bar()
    test_reconciliar_apaga_status_en_sesiones_vivas()
    print("OK")
