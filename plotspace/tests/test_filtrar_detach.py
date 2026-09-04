# plotspace/tests/test_filtrar_detach.py
"""Tests del filtro del ruido '[detached (from session ...)]' que tmux
imprime al cliente pateado por un attach -d. Es cosmético: nunca debe
llegar a la card. Ver terminals.py:_filtrar_detach."""
from plotspace.routers.terminals import _filtrar_detach


def test_quita_linea_detach_sola():
    assert _filtrar_detach('[detached (from session jarvis_510)]\r\n') == ''


def test_quita_detach_sin_newline():
    assert _filtrar_detach('[detached (from session jarvis_42)]') == ''


def test_quita_detach_con_cr_previo():
    # tmux suele anteponer un \r
    assert _filtrar_detach('\r[detached (from session jarvis_7)]\r\n') == ''


def test_conserva_lo_de_alrededor():
    txt = 'foo\n[detached (from session jarvis_1)]\r\nbar\n'
    assert _filtrar_detach(txt) == 'foo\nbar\n'


def test_no_toca_output_normal():
    txt = '● Update(app.js)\n$ ls -la\nnpm run dev\n'
    assert _filtrar_detach(txt) == txt


def test_no_confunde_palabra_detached_en_prosa():
    # solo la línea EXACTA de tmux, no cualquier mención
    txt = 'the client detached from the network\n'
    assert _filtrar_detach(txt) == txt


def test_vacio_y_none():
    assert _filtrar_detach('') == ''
    assert _filtrar_detach(None) == ''


def test_multiples_detach_en_un_chunk():
    txt = ('[detached (from session jarvis_510)]\r\n'
           '[detached (from session jarvis_510)]\r\n')
    assert _filtrar_detach(txt) == ''
