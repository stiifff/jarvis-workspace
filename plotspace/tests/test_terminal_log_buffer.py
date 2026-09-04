"""
Tests: el log del PTY se escribe FUERA del event loop, batcheado.

Causa raíz del lag de tipeo en terminales (deep work 2026-06-23): el read loop
del WS de attach llamaba `_append_log` SÍNCRONO por CADA chunk de `os.read`
(cientos/seg mientras un agente escupe output) → cada `open/write/close` corría
en el único event loop de asyncio → micro-stalls en ráfaga que congelaban TODOS
los WebSockets a la vez (el eco de la tecla del usuario y la entrega de la voz
sufrían los mismos stalls).

El fix separa dos cosas:
1. `_escribir_log(log_file, data)` — el I/O síncrono (rotación + write). Se invoca
   SIEMPRE vía `asyncio.to_thread` o en el cierre del WS, nunca directo en el loop.
2. `_LogWriter` — acumula los chunks en memoria con su timestamp y los vuelca
   batcheados (cada `_LOG_FLUSH_S` o al pasar `_LOG_FLUSH_BYTES`).

Invariantes que fija el fix:
- `_escribir_log` escribe el contenido y respeta la rotación a `.1` en MAX_LOG_BYTES.
- `_LogWriter.append` acumula; `flush()` vuelca y vacía el buffer.
- En una sesión real, N chunks chicos del PTY se escriben en UNA sola pasada a
  disco (batch), no N veces — esa es la prueba de que el write salió del hot path.
"""
import os
import sys

import pytest
import asyncio
import tempfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # para importar el módulo hermano

import plotspace.routers.terminals as term
from test_terminal_flow_control import FakeWSFlujo, FakePty

# Estos tests verifican el argv EXACTO de tmux: desde F5·2 el default es el
# termhost, así que hay que pedir ese motor explícitamente (ver conftest).
pytestmark = pytest.mark.usefixtures('motor_tmux')



# ─── 1: _escribir_log (I/O síncrono, rotación) ───────────────────────────────

def test_escribir_log_escribe_contenido():
    with tempfile.TemporaryDirectory() as d:
        log = os.path.join(d, 't.log')
        term._escribir_log(log, 'hola mundo')
        with open(log) as f:
            assert f.read() == 'hola mundo'


def test_escribir_log_appendea_no_pisa():
    with tempfile.TemporaryDirectory() as d:
        log = os.path.join(d, 't.log')
        term._escribir_log(log, 'aaa')
        term._escribir_log(log, 'bbb')
        with open(log) as f:
            assert f.read() == 'aaabbb'


def test_escribir_log_rota_al_pasar_el_tope():
    with tempfile.TemporaryDirectory() as d:
        log = os.path.join(d, 't.log')
        with mock.patch.object(term, 'MAX_LOG_BYTES', 10):
            term._escribir_log(log, 'x' * 20)   # ahora pesa 20 > 10
            term._escribir_log(log, 'NUEVO')    # el próximo write rota y arranca limpio
        assert os.path.exists(log + '.1'), 'no rotó a .1'
        with open(log) as f:
            assert f.read() == 'NUEVO'
        with open(log + '.1') as f:
            assert f.read() == 'x' * 20


# ─── 2: _LogWriter (buffer en memoria) ───────────────────────────────────────

def test_logwriter_acumula_con_timestamp():
    w = term._LogWriter('/tmp/no-se-escribe.log')
    w.append('hola')
    w.append('chau')
    assert w.bytes_pendientes > 0
    data = w._tomar()
    # cada chunk lleva su prefijo [HH:MM:SS] y su texto
    assert 'hola' in data and 'chau' in data
    assert data.count('hola') == 1 and data.count('chau') == 1
    # tras tomar, el buffer queda vacío
    assert w.bytes_pendientes == 0
    assert w._tomar() == ''


def test_logwriter_flush_escribe_y_limpia():
    with tempfile.TemporaryDirectory() as d:
        log = os.path.join(d, 't.log')
        w = term._LogWriter(log)
        w.append('uno')
        w.append('dos')

        async def go():
            await w.flush()
        asyncio.run(go())

        with open(log) as f:
            contenido = f.read()
        assert 'uno' in contenido and 'dos' in contenido
        assert w.bytes_pendientes == 0
        # flush sobre buffer vacío no rompe ni escribe basura
        asyncio.run(_call(w.flush))


async def _call(coro_fn):
    await coro_fn()


# ─── 3: integración — la sesión batchea los writes del PTY ───────────────────

def _correr_sesion_log(ws, fd, escenario, log_file):
    """Corre _sesion_tmux con ptyprocess/subprocess mockeados y _LOG_FLUSH_S
    grande (sin flush periódico durante el test) — así todos los chunks se
    acumulan y se vuelcan en UNA pasada al cerrar. Espía `_escribir_log`."""
    fake_mod = mock.Mock()
    fake_mod.PtyProcess.spawn.return_value = FakePty(fd)
    run_mock = mock.Mock(return_value=mock.Mock(returncode=0, stdout='', stderr=''))
    escrituras = []
    real_escribir = term._escribir_log

    def spy(lf, data):
        escrituras.append(data)
        return real_escribir(lf, data)

    async def go():
        with mock.patch.dict(sys.modules, {'ptyprocess': fake_mod}), \
             mock.patch.object(term.subprocess, 'run', run_mock), \
             mock.patch.object(term, '_LOG_FLUSH_S', 100.0), \
             mock.patch.object(term, '_escribir_log', spy):
            tarea = asyncio.create_task(term._sesion_tmux(
                ws, 997, '/tmp', log_file,
                cols=100, rows=30, observer=False, fc=True,
            ))
            await asyncio.sleep(0.05)
            await escenario(ws)
            await asyncio.wait_for(tarea, timeout=5)
    asyncio.run(go())
    return escrituras


def test_sesion_batchea_writes_de_log():
    r, w = os.pipe()
    ws = FakeWSFlujo()
    with tempfile.TemporaryDirectory() as d:
        log = os.path.join(d, 'term.log')

        async def escenario(ws):
            # 5 chunks chicos separados (como el eco de tecleo / output goteado)
            for ch in (b'a', b'b', b'c', b'd', b'e'):
                os.write(w, ch * 10)
                await asyncio.sleep(0.03)
            os.close(w)   # EOF → cierra el WS, dispara el flush final

        try:
            escrituras = _correr_sesion_log(ws, r, escenario, log)
        finally:
            try: os.close(r)
            except OSError: pass

        # PRUEBA DEL FIX: 5 chunks del PTY → UNA sola escritura a disco (batch),
        # no 5. Antes (síncrono por chunk) habría 5 writes en el event loop.
        assert len(escrituras) == 1, \
            f'el log no se batcheó: {len(escrituras)} writes (esperaba 1)'
        # y el contenido está completo
        with open(log) as f:
            contenido = f.read()
        for ch in ('aaa', 'bbb', 'ccc', 'ddd', 'eee'):
            assert ch in contenido, f'falta {ch} en el log'


if __name__ == "__main__":
    test_escribir_log_escribe_contenido()
    test_escribir_log_appendea_no_pisa()
    test_escribir_log_rota_al_pasar_el_tope()
    test_logwriter_acumula_con_timestamp()
    test_logwriter_flush_escribe_y_limpia()
    test_sesion_batchea_writes_de_log()
    print("OK")
