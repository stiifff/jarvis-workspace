"""
Test: títulos vivos de terminales (resumen corto de qué hace cada agente).

Claude Code (y toda CLI que publique OSC title) escribe en el título del pane
de tmux un resumen corto de su tarea actual ("✳ Fix layout bug when…"). El
backend lo expone ya LIMPIO para que la card lo muestre en lugar del nombre:
sin glyph de spinner, sin título genérico (hostname = la CLI no publica nada),
y acotado en largo SIN puntos suspensivos (pedido del usuario: corto y punto).
Una sola pasada de tmux para todas las sesiones (no un subprocess por terminal).
"""
import os
import sys

import pytest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import plotspace.routers.terminals as term

# Estos tests verifican el argv EXACTO de tmux: desde F5·2 el default es el
# termhost, así que hay que pedir ese motor explícitamente (ver conftest).
pytestmark = pytest.mark.usefixtures('motor_tmux')



# ── _limpiar_titulo: glyph fuera, genéricos a None, cap sin "…" ──────────────

def test_limpiar_titulo_saca_glyph_spinner():
    # Claude Code prefija ✳ (idle) o chars braille (spinner) — el pip de estado
    # de la card ya comunica eso; acá solo queremos el texto.
    assert term._limpiar_titulo('✳ Remove terminal output', 'HOST') == 'Remove terminal output'
    assert term._limpiar_titulo('⠐ Fix layout bug', 'HOST') == 'Fix layout bug'
    assert term._limpiar_titulo('⠂ Algo en español: menú', 'HOST') == 'Algo en español: menú'


def test_limpiar_titulo_genericos_devuelven_none():
    # Título == hostname → la CLI no publicó nada (default de tmux/shell).
    assert term._limpiar_titulo('HOST', 'HOST') is None
    assert term._limpiar_titulo('host', 'HOST') is None          # case-insensitive
    assert term._limpiar_titulo('', 'HOST') is None
    assert term._limpiar_titulo('   ', 'HOST') is None
    assert term._limpiar_titulo('✳ ', 'HOST') is None            # glyph solo, sin texto


def test_limpiar_titulo_cap_sin_puntos_suspensivos():
    largo = 'Implementar el sistema completo de notificaciones push con websockets y reintentos'
    out = term._limpiar_titulo(largo, 'HOST')
    assert len(out) <= 60
    assert not out.endswith('…') and not out.endswith('...')
    assert not out.endswith(' ')                  # corte limpio en palabra
    assert largo.startswith(out)                  # es un prefijo real, sin inventos


def test_limpiar_titulo_corto_pasa_tal_cual():
    assert term._limpiar_titulo('Fix bug', 'HOST') == 'Fix bug'


# ── _titulos_vivos_tmux: una pasada, solo sesiones jarvis_{id} numéricas ─────

def test_titulos_vivos_parsea_una_sola_pasada():
    salida = (
        'jarvis_471\t✳ Remove terminal output\n'
        'jarvis_472\t⠐ Fix layout bug when resizing menus in terminals\n'
        'jarvis_473\tHOST\n'                       # CLI sin título → genérico
        'jarvis_mpreview_18\tnpx expo start\n'     # no es terminal de card → fuera
        'otra_sesion\tlo que sea\n'                # ajena a jarvis → fuera
    )
    with mock.patch.object(term.subprocess, 'run') as m, \
         mock.patch.object(term, '_hostname', return_value='HOST'):
        m.return_value = mock.Mock(returncode=0, stdout=salida, stderr='')
        titulos = term._titulos_vivos_tmux()

    assert titulos == {
        471: 'Remove terminal output',
        472: 'Fix layout bug when resizing menus in terminals',
        473: None,
    }
    # UNA sola invocación a tmux para todas las sesiones
    assert m.call_count == 1
    argv = m.call_args.args[0]
    assert argv[:2] == ['tmux', 'list-panes'] and '-a' in argv


def test_titulos_vivos_tmux_caido_devuelve_vacio():
    with mock.patch.object(term.subprocess, 'run') as m:
        m.return_value = mock.Mock(returncode=1, stdout='', stderr='no server')
        assert term._titulos_vivos_tmux() == {}
