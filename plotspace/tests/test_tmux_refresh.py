"""
Tests: el repintado de tmux apunta al CLIENTE (tty), no a la sesión.

Bug encontrado 2026-06-23: `tmux refresh-client -t <target>` toma un CLIENTE
(el tty), NO una sesión. El backend llamaba `refresh-client -t jarvis_<id>`
(nombre de sesión) → en tmux 3.6 falla con 'can't find client' y se tragaba en
silencio (capture_output). Resultado: el AUTO-SANADO de garble (volver visible
la pestaña / re-attachear / resize) NUNCA repintaba → la terminal quedaba rota
hasta el F5. El fix enumera los clientes reales de la sesión y refresca cada uno.
"""
import os
import sys

import pytest
import asyncio
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import plotspace.routers.terminals as term

# Estos tests verifican el argv EXACTO de tmux: desde F5·2 el default es el
# termhost, así que hay que pedir ese motor explícitamente (ver conftest).
pytestmark = pytest.mark.usefixtures('motor_tmux')



def _correr(session, stdout_clients):
    """Corre _refresh_clientes_sesion con subprocess mockeado; devuelve la lista
    de comandos refresh-client ejecutados."""
    refreshes = []

    def fake_run(args, **kw):
        a = list(args)
        if 'list-clients' in a:
            return mock.Mock(returncode=0, stdout=stdout_clients, stderr='')
        if 'refresh-client' in a:
            refreshes.append(a)
        return mock.Mock(returncode=0, stdout='', stderr='')

    async def go():
        with mock.patch.object(term.subprocess, 'run', side_effect=fake_run):
            await term._refresh_clientes_sesion(session)
    asyncio.run(go())
    return refreshes


def test_refresh_apunta_a_cada_tty_no_a_la_sesion():
    refreshes = _correr('jarvis_42', '/dev/pts/14\n/dev/pts/20\n')
    # un refresh por CADA cliente, targeteando su TTY
    assert ['tmux', 'refresh-client', '-t', '/dev/pts/14'] in refreshes
    assert ['tmux', 'refresh-client', '-t', '/dev/pts/20'] in refreshes
    assert len(refreshes) == 2
    # NUNCA con el nombre de sesión (el bug que rompía el auto-sanado)
    assert not any('jarvis_42' in r for r in refreshes)


def test_refresh_sin_clientes_no_rompe():
    refreshes = _correr('jarvis_42', '')   # sesión sin clientes attachados
    assert refreshes == []


def test_refresh_un_solo_cliente():
    refreshes = _correr('jarvis_99', '/dev/pts/3\n')
    assert refreshes == [['tmux', 'refresh-client', '-t', '/dev/pts/3']]


if __name__ == '__main__':
    test_refresh_apunta_a_cada_tty_no_a_la_sesion()
    test_refresh_sin_clientes_no_rompe()
    test_refresh_un_solo_cliente()
    print('OK')
