"""
Tests: attach del PTY a tmux — desplazamiento, modo observador y muerte del PTY.

Quinta capa del bug [[tmux-size-clamping]]: cualquier página segunda del
workspace (típicamente el QA de Playwright de un agente) attacheaba con -d al
tamaño del viewport headless → desplazaba el attach del usuario y le
redimensionaba la ventana tmux. Encima, el WS del desplazado quedaba ABIERTO
(leer() cortaba en silencio): terminal congelada con canvas viejo, sin overlay,
mezclando anchos. Invariantes que fijan el fix (sin tmux real — se mockea):

1. El attach del dueño usa -d (recargar la pestaña desplaza al anterior).
2. El attach observador (?observer=1, QA) NO usa -d y va read-only,ignore-size:
   mira sin robar la sesión, sin tipear y sin participar del window-size latest.
3. PTY muerto (EOF: desplazado o sesión kill) → el WS se CIERRA (código 4000)
   para que el frontend muestre el overlay de reconexión al instante.
4. Un observador no pisa terminal_processes (la entrada es del dueño), y un
   dueño desplazado no borra la entrada del dueño nuevo al salir.
"""
import os
import sys

import pytest
import asyncio
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from starlette.websockets import WebSocketDisconnect, WebSocketState

import plotspace.routers.terminals as term

# Estos tests verifican el argv EXACTO de tmux: desde F5·2 el default es el
# termhost, así que hay que pedir ese motor explícitamente (ver conftest).
pytestmark = pytest.mark.usefixtures('motor_tmux')



# ─── helpers ──────────────────────────────────────────────────────────────────

class FakeWS:
    """WebSocket mínimo: receive_json bloquea hasta que alguien cierre."""
    def __init__(self):
        self.client_state = WebSocketState.CONNECTED
        self.close_code = None
        self._cerrado = asyncio.Event()

    async def receive_json(self):
        await self._cerrado.wait()
        raise WebSocketDisconnect(self.close_code or 1000)

    async def close(self, code=1000, reason=None):
        self.close_code = code
        self.client_state = WebSocketState.DISCONNECTED
        self._cerrado.set()

    async def send_text(self, txt):
        pass


class FakePty:
    """PTY falso respaldado por un pipe real (leer() usa add_reader sobre fd)."""
    def __init__(self, fd):
        self.fd = fd

    def write(self, data): pass
    def setwinsize(self, rows, cols): pass
    def terminate(self, force=False): pass


def _correr_sesion(ws, fake_pty, observer, al_arrancar=None):
    """Corre _sesion_tmux con ptyprocess y subprocess mockeados."""
    fake_mod = mock.Mock()
    fake_mod.PtyProcess.spawn.return_value = fake_pty

    async def go():
        with mock.patch.dict(sys.modules, {'ptyprocess': fake_mod}), \
             mock.patch.object(term.subprocess, 'run',
                               return_value=mock.Mock(returncode=0, stdout='', stderr='')):
            tarea = asyncio.create_task(term._sesion_tmux(
                ws, 999, '/tmp', '/tmp/test_term_attach.log',
                cols=100, rows=30, observer=observer,
            ))
            await asyncio.sleep(0.05)
            if al_arrancar:
                al_arrancar()
            await asyncio.wait_for(tarea, timeout=3)
    asyncio.run(go())
    return fake_mod


# ─── 1/2: argv del attach ─────────────────────────────────────────────────────

def test_cmd_attach_dueno_desplaza():
    """El dueño attachea con -d: un attach nuevo desplaza al anterior."""
    argv = term._cmd_attach('jarvis_999')
    assert '-d' in argv, f"el attach del dueño debe llevar -d. argv: {argv}"
    assert '-f' not in argv


def test_cmd_attach_observer_no_desplaza_ni_dimensiona():
    """El observador (QA) NO desplaza (sin -d) y va read-only + ignore-size:
    no puede tipear y NO cuenta para window-size latest (no achica la ventana
    del usuario al tamaño del viewport headless)."""
    argv = term._cmd_attach('jarvis_999', observer=True)
    assert '-d' not in argv, f"un observador jamás desplaza al dueño. argv: {argv}"
    i = argv.index('-f')
    flags = argv[i + 1]
    assert 'read-only' in flags and 'ignore-size' in flags, \
        f"faltan flags de observador. argv: {argv}"


# ─── 3: PTY muerto → cerrar el WS ────────────────────────────────────────────

@pytest.mark.skipif(os.name == 'nt', reason='ejercita el motor tmux, que en Windows no existe')
def test_pty_eof_cierra_websocket():
    """Si el PTY muere (attach -d ajeno nos desplazó / sesión kill), el WS se
    cierra activamente. Antes quedaba abierto: terminal congelada en silencio
    con el canvas viejo, sin overlay, hasta que un resize posterior explotara.

    Solo-Unix: corre `_sesion_tmux` con un `os.pipe()` de verdad, y el motor
    tmux no es el de Windows (allá manda el termhost, con su propio test de
    cierre en `test_conpty_backend.py`)."""
    r, w = os.pipe()
    ws = FakeWS()
    try:
        _correr_sesion(ws, FakePty(r), observer=False,
                       al_arrancar=lambda: os.close(w))
        assert ws.close_code == 4000, \
            f"PTY EOF debe cerrar el WS con 4000 (overlay inmediato), cerró: {ws.close_code}"
    finally:
        try: os.close(r)
        except OSError: pass


# ─── 4: terminal_processes es del dueño ──────────────────────────────────────

def test_observer_no_pisa_terminal_processes():
    """La entrada de terminal_processes es del attach del DUEÑO (la usa
    teardown_terminal). Un observador no la pisa ni la borra al salir."""
    centinela = {'process': object(), 'type': 'pty'}
    term.terminal_processes[999] = centinela
    r, w = os.pipe()
    ws = FakeWS()
    try:
        fake_mod = _correr_sesion(ws, FakePty(r), observer=True,
                                  al_arrancar=lambda: os.close(w))
        assert term.terminal_processes.get(999) is centinela, \
            "el observador pisó/borró la entrada del dueño en terminal_processes"
        argv = fake_mod.PtyProcess.spawn.call_args.args[0]
        assert argv == term._cmd_attach('jarvis_999', observer=True)
    finally:
        term.terminal_processes.pop(999, None)
        try: os.close(r)
        except OSError: pass


def test_dueno_desplazado_no_borra_entrada_del_nuevo():
    """Si un dueño nuevo ya registró SU proceso (recarga de pestaña), el dueño
    viejo al morir no debe hacer pop de esa entrada ajena."""
    r, w = os.pipe()
    ws = FakeWS()
    proceso_nuevo = {'process': object(), 'type': 'pty'}

    def desplazar():
        # Simula que un attach nuevo pisó la entrada ANTES de que muera el viejo
        term.terminal_processes[999] = proceso_nuevo
        os.close(w)

    try:
        _correr_sesion(ws, FakePty(r), observer=False, al_arrancar=desplazar)
        assert term.terminal_processes.get(999) is proceso_nuevo, \
            "el dueño desplazado borró la entrada del dueño nuevo"
    finally:
        term.terminal_processes.pop(999, None)
        try: os.close(r)
        except OSError: pass


# ─── _EscritorPTY: paste grande no rompe la terminal (write no-bloqueante) ────
# Bug: el fd del master quedó NO bloqueante (leer() lo setea para add_reader); un
# paste de >~8KB en UN proceso.write tiraba BlockingIOError → caía al except ancho
# del receive-loop → terminate() → tmux detacheado + paste PERDIDO. El writer
# drenado encola el remanente y lo vuelca con add_writer, simétrico a leer().

class _FakeLoop:
    """Registra el callback de add_writer (lo que el loop real invoca al haber
    espacio en el fd). cb=None ⇔ no hay drenado armado."""
    def __init__(self):
        self.cb = None
        self.fd = None

    def add_writer(self, fd, cb):
        self.fd = fd
        self.cb = cb

    def remove_writer(self, fd):
        self.cb = None


class _Sink:
    """Sumidero de capacidad fija para inyectar como _write. Acepta hasta `chunk`
    bytes por llamada; chunk<=0 simula EAGAIN (buffer lleno); open=False simula
    fd muerto (OSError)."""
    def __init__(self, chunk):
        self.data = bytearray()
        self.chunk = chunk
        self.open = True

    def write(self, fd, b):
        if not self.open:
            raise OSError(9, 'bad fd')
        if self.chunk <= 0:
            raise BlockingIOError()
        n = min(self.chunk, len(b))
        self.data.extend(bytes(b[:n]))
        return n


def test_escritor_pty_chico_va_directo():
    # Tipeo normal (bytes chicos): se escribe completo al instante, sin encolar
    # ni armar add_writer → el path de tecla queda intacto.
    sink = _Sink(chunk=4096); loop = _FakeLoop()
    esc = term._EscritorPTY(7, loop, _write=sink.write)
    esc.escribir(b'ls -la\r')
    assert bytes(sink.data) == b'ls -la\r'
    assert loop.cb is None


def test_escritor_pty_paste_grande_se_drena_completo_en_orden():
    # Paste que excede la capacidad por llamada: escribe lo que entra, encola el
    # resto y lo drena con add_writer SIN perder ni reordenar.
    sink = _Sink(chunk=4); loop = _FakeLoop()
    esc = term._EscritorPTY(7, loop, _write=sink.write)
    data = bytes(range(256)) * 40       # 10240 bytes
    esc.escribir(data)
    assert loop.cb is not None          # quedó remanente → drenado armado
    guard = 0
    while loop.cb is not None and guard < 100000:
        loop.cb(); guard += 1           # cada tick vuelca otros `chunk` bytes
    assert bytes(sink.data) == data     # completo y EN ORDEN
    assert loop.cb is None              # se desarmó al vaciarse


def test_escritor_pty_eagain_no_pierde():
    # El fd dice EAGAIN (lleno) y luego acepta: el dato llega completo igual.
    sink = _Sink(chunk=0); loop = _FakeLoop()
    esc = term._EscritorPTY(7, loop, _write=sink.write)
    esc.escribir(b'hola mundo')
    assert bytes(sink.data) == b''      # nada entró todavía (EAGAIN)
    assert loop.cb is not None
    sink.chunk = 3                      # el fd vuelve a aceptar
    guard = 0
    while loop.cb is not None and guard < 1000:
        loop.cb(); guard += 1
    assert bytes(sink.data) == b'hola mundo'


def test_escritor_pty_fifo_input_durante_drenado():
    # Tipear MIENTRAS se drena un paste: el input nuevo se APPENDEA (FIFO), no se
    # adelanta → jamás se interleavea con el paste a medio escribir.
    sink = _Sink(chunk=4); loop = _FakeLoop()
    esc = term._EscritorPTY(7, loop, _write=sink.write)
    esc.escribir(b'AAAAAAAA')            # 4 entran, 4 quedan encolados
    esc.escribir(b'BBB')                 # llega durante el drenado → va al final
    guard = 0
    while loop.cb is not None and guard < 1000:
        loop.cb(); guard += 1
    assert bytes(sink.data) == b'AAAAAAAABBB'


def test_escritor_pty_fd_muerto_no_explota():
    # fd muerto (OSError): no propaga (antes detachaba tmux), descarta y no arma.
    sink = _Sink(chunk=4); sink.open = False; loop = _FakeLoop()
    esc = term._EscritorPTY(7, loop, _write=sink.write)
    esc.escribir(b'algo')                # no debe levantar
    assert loop.cb is None


def test_escritor_pty_cerrar_saca_el_writer():
    sink = _Sink(chunk=0); loop = _FakeLoop()
    esc = term._EscritorPTY(7, loop, _write=sink.write)
    esc.escribir(b'pendiente')
    assert loop.cb is not None
    esc.cerrar()
    assert loop.cb is None


# ─── _filtrar_detach: guard de substring (no correr el regex sobre cada chunk) ─

def test_filtrar_detach_guard_byte_identico():
    # Sin la marca 'detached' el chunk vuelve byte-idéntico (el guard salta el
    # regex .sub sobre cada chunk de 64KB del flood — ~30× más barato).
    limpio = 'una línea normal de output\r\n' * 100
    assert term._filtrar_detach(limpio) == limpio
    # Con la marca, la saca igual que siempre.
    sucio = 'antes\r[detached (from session jarvis_510)]\r\ndespués'
    assert term._filtrar_detach(sucio) == 'antesdespués'
    assert term._filtrar_detach('') == ''


if __name__ == "__main__":
    test_cmd_attach_dueno_desplaza()
    test_cmd_attach_observer_no_desplaza_ni_dimensiona()
    test_pty_eof_cierra_websocket()
    test_observer_no_pisa_terminal_processes()
    test_dueno_desplazado_no_borra_entrada_del_nuevo()
    test_escritor_pty_chico_va_directo()
    test_escritor_pty_paste_grande_se_drena_completo_en_orden()
    test_escritor_pty_eagain_no_pierde()
    test_escritor_pty_fifo_input_durante_drenado()
    test_escritor_pty_fd_muerto_no_explota()
    test_escritor_pty_cerrar_saca_el_writer()
    test_filtrar_detach_guard_byte_identico()
    print("OK")
