"""
Tests: stream UTF-8 del PTY — caracteres multibyte partidos entre chunks.

Sexta capa del bug [[tmux-size-clamping]]: os.read() corta en límites de
BYTES, no de caracteres. Un redraw grande del TUI (>64KB, pantalla ancha con
colores) parte un carácter multibyte ('✶', '·', '╭', '↓'…) entre dos chunks;
decodificar cada chunk suelto con errors='replace' metía '�' de ancho distinto
al carácter real → columnas corridas, y como tmux manda diffs contra SU modelo
de pantalla, la basura persistía VARIOS SEGUNDOS (hasta el próximo repintado
de la zona). Síntoma del usuario: línea del spinner duplicada con texto
entreverado, caja del input partida, se cura sola.

Invariantes que fijan el fix (decoder UTF-8 incremental por conexión):
1. Un multibyte partido entre dos os.read se re-une (cero '�').
2. Bytes genuinamente inválidos siguen saliendo como '�' (no explotan).
3. leer() end-to-end (pipe real): texto con '✶' partido llega ENTERO al WS.
"""
import os
import sys

import pytest
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import plotspace.routers.terminals as term
from plotspace.tests.test_terminal_attach import FakeWS, FakePty, _correr_sesion

# Estos tests verifican el argv EXACTO de tmux: desde F5·2 el default es el
# termhost, así que hay que pedir ese motor explícitamente (ver conftest).
pytestmark = pytest.mark.usefixtures('motor_tmux')



# ─── 1/2: el decoder incremental ──────────────────────────────────────────────

def test_decoder_junta_multibyte_partido():
    """'✶' (3 bytes) partido en dos feeds sale entero, sin '�'."""
    d = term._nuevo_decoder_utf8()
    raw = '✶ Billowing… (1m 24s · ↓ 4.2k tokens)'.encode('utf-8')
    corte = raw.index('·'.encode('utf-8')) + 1   # a mitad del '·' (2 bytes)
    salida = d.decode(raw[:corte]) + d.decode(raw[corte:])
    assert salida == '✶ Billowing… (1m 24s · ↓ 4.2k tokens)'
    assert '�' not in salida


def test_decoder_byte_invalido_sigue_reemplazando():
    """Basura real (no-UTF-8) no explota: sale como '�' y el stream sigue."""
    d = term._nuevo_decoder_utf8()
    salida = d.decode(b'ok\xff') + d.decode('✶'.encode('utf-8'))
    assert salida == 'ok�✶'


def test_decoder_es_stateful_no_global():
    """Cada conexión necesita SU decoder: el buffer interno no se comparte."""
    d1, d2 = term._nuevo_decoder_utf8(), term._nuevo_decoder_utf8()
    raw = '✶'.encode('utf-8')
    assert d1.decode(raw[:1]) == ''          # incompleto: bufferea
    assert d2.decode(raw) == '✶'             # d2 no se contamina con d1
    assert d1.decode(raw[1:]) == '✶'


# ─── 3: end-to-end por leer() (pipe real, dos os.read separados) ─────────────

def test_leer_no_rompe_utf8_partido_entre_chunks():
    """Un redraw que parte '✶' entre dos chunks del PTY llega ENTERO al WS."""

    class WSRecorder(FakeWS):
        def __init__(self):
            super().__init__()
            self.recibido = []

        async def send_text(self, txt):
            self.recibido.append(txt)

    raw = '╭─ ✶ Billowing… · ↓ 4.2k ─╮'.encode('utf-8')
    corte = raw.index('✶'.encode('utf-8')) + 1   # a mitad del '✶'

    r, w = os.pipe()
    ws = WSRecorder()

    def escribir_en_dos_tandas():
        def _go():
            os.write(w, raw[:corte])
            time.sleep(0.15)                  # fuerza DOS os.read separados
            os.write(w, raw[corte:])
            time.sleep(0.15)
            os.close(w)                       # EOF → termina leer()
        threading.Thread(target=_go, daemon=True).start()

    try:
        _correr_sesion(ws, FakePty(r), observer=False,
                       al_arrancar=escribir_en_dos_tandas)
        texto = ''.join(ws.recibido)
        assert '✶' in texto and '�' not in texto, \
            f"el multibyte partido se corrompió: {texto!r}"
        assert texto == '╭─ ✶ Billowing… · ↓ 4.2k ─╮'
    finally:
        try: os.close(r)
        except OSError: pass
