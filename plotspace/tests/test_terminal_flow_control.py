"""
Tests: flow control de punta a punta del stream PTY→WS→xterm.

Séptima capa del bug [[tmux-size-clamping]]: xterm.js 5.3 DESCARTA datos
(throw "write data discarded, use flow control to avoid losing data") cuando
su cola interna de write pasa 50MB (5e7). Esa cola se drena en slices de 12ms
encadenados con setTimeout(0), que Chrome estrangula en pestañas ocultas
(1 tick/seg al ocultarse; 1 tick/MINUTO tras 5 min — intensive throttling).
Los ws.onmessage NO se estrangulan: con agentes trabajando, los datos entran
a velocidad completa y solo se encolan → la cola cruza 50MB → se pierden
chunks arbitrarios (secuencias ANSI cortadas al medio) → el parser de xterm
queda desincronizado del modelo de tmux → letras rotas / contenido
multiplicado PERMANENTE (tmux manda diffs: nunca repinta lo que el browser
perdió) hasta el F5. Síntoma del usuario: "se rompe todo, se multiplica,
obligado a F5, casi siempre cuando un agente está por terminar" (= cuando
vuelve a la pestaña tras el aviso sonoro, después de tenerla tapada).

Invariantes que fijan el fix:
1. _FlujoWS: pendiente >= high frena; un ack que baja a <= low reanuda;
   sobre-ack (UTF-16 units del browser >= codepoints de Python) clampa en 0.
2. fc inactivo (cliente legacy sin &fc=1 en la URL del WS): jamás frena.
3. leer() end-to-end (pipe real): con fc activo el stream se FRENA en el
   watermark, el ack del browser lo reanuda y el EOF sigue cerrando con 4000.
4. ws_terminal acepta el query param fc (wiring FastAPI).
5. {'type':'refresh'} del browser → tmux refresh-client (auto-sanación al
   volver visible la pestaña: repinta TODO sin F5).
"""
import os
import sys

import pytest
import asyncio
import inspect
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from starlette.websockets import WebSocketDisconnect, WebSocketState

import plotspace.routers.terminals as term

# Estos tests verifican el argv EXACTO de tmux: desde F5·2 el default es el
# termhost, así que hay que pedir ese motor explícitamente (ver conftest).
pytestmark = pytest.mark.usefixtures('motor_tmux')



# ─── helpers ──────────────────────────────────────────────────────────────────

class FakeWSFlujo:
    """WebSocket falso con cola de mensajes entrantes (acks/refresh) y registro
    de lo enviado. close() desbloquea receive_json como en starlette."""
    def __init__(self):
        self.client_state = WebSocketState.CONNECTED
        self.close_code = None
        self.recibido = []
        self._cola = asyncio.Queue()

    def encolar(self, msg):
        self._cola.put_nowait(msg)

    async def receive_json(self):
        msg = await self._cola.get()
        if msg is None:
            raise WebSocketDisconnect(1000)
        return msg

    async def close(self, code=1000, reason=None):
        self.close_code = code
        self.client_state = WebSocketState.DISCONNECTED
        self._cola.put_nowait(None)

    async def send_text(self, txt):
        self.recibido.append(txt)


class FakePty:
    def __init__(self, fd):
        self.fd = fd
    def write(self, data): pass
    def setwinsize(self, rows, cols): pass
    def terminate(self, force=False): pass


def _correr_sesion_fc(ws, fd, escenario, fc=True, high=300, low=100):
    """Corre _sesion_tmux (ptyprocess/subprocess mockeados, watermarks chicos)
    y ejecuta `escenario(ws)` (corutina) en paralelo. Devuelve el mock de
    subprocess.run para asseverar sobre los comandos tmux."""
    fake_mod = mock.Mock()
    fake_mod.PtyProcess.spawn.return_value = FakePty(fd)
    # list-clients devuelve un tty fake (sino _refresh_clientes_sesion no refresca);
    # el resto de los comandos tmux devuelven vacío.
    def _fake_run(args, **kw):
        a = list(args)
        if 'list-clients' in a:
            return mock.Mock(returncode=0, stdout='/dev/pts/fake\n', stderr='')
        return mock.Mock(returncode=0, stdout='', stderr='')
    run_mock = mock.Mock(side_effect=_fake_run)

    async def go():
        with mock.patch.dict(sys.modules, {'ptyprocess': fake_mod}), \
             mock.patch.object(term.subprocess, 'run', run_mock), \
             mock.patch.object(term, 'FC_HIGH', high), \
             mock.patch.object(term, 'FC_LOW', low), \
             mock.patch.object(term, 'FC_HIGH_VISIBLE', high), \
             mock.patch.object(term, 'FC_LOW_VISIBLE', low):
            tarea = asyncio.create_task(term._sesion_tmux(
                ws, 998, '/tmp', '/tmp/test_term_fc.log',
                cols=100, rows=30, observer=False, fc=fc,
            ))
            await asyncio.sleep(0.05)
            await escenario(ws)
            await asyncio.wait_for(tarea, timeout=5)
    asyncio.run(go())
    return run_mock


def _total_recibido(ws):
    return sum(len(t) for t in ws.recibido)


# ─── 1/2: la clase _FlujoWS ───────────────────────────────────────────────────

def test_flujo_frena_en_high_y_reanuda_en_low():
    async def go():
        f = term._FlujoWS(activo=True, high=300, low=100)
        f.enviado(200)
        assert f.pendiente == 200
        await asyncio.wait_for(f.esperar_capacidad(), 1)   # < high: no frena
        f.enviado(200)                                     # 400 >= 300: frena
        assert not f._hay_capacidad.is_set()
        f.ack(250)                                         # 150 > low: sigue frenado
        assert not f._hay_capacidad.is_set()
        f.ack(100)                                         # 50 <= low: reanuda
        assert f._hay_capacidad.is_set()
        await asyncio.wait_for(f.esperar_capacidad(), 1)
    asyncio.run(go())


def test_flujo_inactivo_nunca_frena():
    """Cliente legacy (JS viejo cacheado, sin &fc=1): comportamiento de siempre."""
    async def go():
        f = term._FlujoWS(activo=False, high=10, low=5)
        f.enviado(10_000)
        assert f.pendiente == 0                            # ni contabiliza
        await asyncio.wait_for(f.esperar_capacidad(), 1)   # jamás bloquea
    asyncio.run(go())


def test_flujo_ack_clampa_en_cero_y_descarta_basura():
    """El browser cuenta UTF-16 units (>= codepoints de Python): el sobre-ack
    clampa en 0 en vez de irse a negativo. Acks basura no rompen la cuenta."""
    f = term._FlujoWS(activo=True, high=300, low=100)
    f.enviado(50)
    f.ack(9999)
    assert f.pendiente == 0
    f.ack('no-numero')
    f.ack(-5)
    f.ack(None)
    assert f.pendiente == 0


# ─── 1.bis: watermark adaptativo por visibilidad ─────────────────────────────

def test_flujo_visible_amplia_el_watermark():
    """Pestaña visible: el browser parsea a full y ackea rápido → watermark
    AMPLIO (el eco del tipeo no queda atrapado detrás del flood). Oculta:
    watermark ajustado (rAF frenado → proteger la cola de 50MB de xterm)."""
    f = term._FlujoWS(activo=True, visible=False)
    assert f.high == term.FC_HIGH and f.low == term.FC_LOW            # oculta: ajustado
    f.set_visible(True)
    assert f.high == term.FC_HIGH_VISIBLE and f.low == term.FC_LOW_VISIBLE  # visible: amplio
    assert term.FC_HIGH_VISIBLE > term.FC_HIGH                        # amplio es de verdad más grande


def test_flujo_default_es_visible():
    """Default VISIBLE = modo rápido: el caso común es el usuario mirando. Así el
    eco fluye aunque el frontend NO reporte visibilidad (JS viejo cacheado tras un
    update sin hard-reload). El frontend nuevo manda visible=false al ocultar."""
    f = term._FlujoWS(activo=True)
    assert f.high == term.FC_HIGH_VISIBLE and f.low == term.FC_LOW_VISIBLE


def test_flujo_set_visible_reevalua_el_gate():
    """Cambiar de visible↔oculto re-evalúa el gate con el watermark nuevo."""
    async def go():
        f = term._FlujoWS(activo=True, visible=True)   # high = FC_HIGH_VISIBLE (amplio)
        f.enviado(term.FC_HIGH + 50_000)               # supera el watermark OCULTO, no el visible
        assert f._hay_capacidad.is_set()               # visible: hay capacidad, no frena
        f.set_visible(False)                           # ahora el watermark es el ajustado
        assert not f._hay_capacidad.is_set()           # lo pendiente ya lo supera → frena
        f.set_visible(True)                            # vuelve a visible
        assert f._hay_capacidad.is_set()               # < amplio → reanuda
    asyncio.run(go())


def test_flujo_high_low_explicitos_ignoran_visibilidad():
    """high/low explícitos (tests/custom) son FIJOS: la visibilidad no los toca.
    Esto preserva el comportamiento de los tests de watermark chico."""
    f = term._FlujoWS(activo=True, high=300, low=100, visible=True)
    assert f.high == 300 and f.low == 100
    f.set_visible(False)
    assert f.high == 300 and f.low == 100


def test_visible_message_amplia_el_watermark_en_la_sesion():
    """{'type':'visible','v':true} del browser ensancha el watermark de la sesión:
    un backlog que CON la pestaña oculta frenaría, con la visible fluye."""
    r, w = os.pipe()
    ws = FakeWSFlujo()

    async def escenario(ws):
        ws.encolar({'type': 'visible', 'v': True})     # el browser dice "estoy visible"
        await asyncio.sleep(0.05)
        os.write(w, b'a' * 400)                          # 400 > 300 (oculto) pero < 10000 (visible)
        await asyncio.sleep(0.15)
        assert _total_recibido(ws) == 400, \
            "con la pestaña visible el watermark amplio no frenó: el eco fluye bajo flood"
        os.close(w)

    fake_mod = mock.Mock()
    fake_mod.PtyProcess.spawn.return_value = FakePty(r)
    run_mock = mock.Mock(return_value=mock.Mock(returncode=0, stdout='', stderr=''))

    async def go():
        with mock.patch.dict(sys.modules, {'ptyprocess': fake_mod}), \
             mock.patch.object(term.subprocess, 'run', run_mock), \
             mock.patch.object(term, 'FC_HIGH', 300), \
             mock.patch.object(term, 'FC_LOW', 100), \
             mock.patch.object(term, 'FC_HIGH_VISIBLE', 10000), \
             mock.patch.object(term, 'FC_LOW_VISIBLE', 5000):
            tarea = asyncio.create_task(term._sesion_tmux(
                ws, 996, '/tmp', '/tmp/test_term_vis.log',
                cols=100, rows=30, observer=False, fc=True,
            ))
            await asyncio.sleep(0.05)
            await escenario(ws)
            await asyncio.wait_for(tarea, timeout=5)
    try:
        asyncio.run(go())
    finally:
        try: os.close(r)
        except OSError: pass


# ─── 3: leer() end-to-end — frena en el watermark, el ack reanuda ────────────

def test_leer_frena_en_watermark_y_ack_reanuda():
    r, w = os.pipe()
    ws = FakeWSFlujo()

    async def escenario(ws):
        os.write(w, b'a' * 200)
        await asyncio.sleep(0.1)
        assert _total_recibido(ws) == 200          # 200 < 300: fluye
        os.write(w, b'b' * 200)
        await asyncio.sleep(0.1)
        assert _total_recibido(ws) == 400          # 400 >= 300: frenado
        os.write(w, b'c' * 200)
        await asyncio.sleep(0.2)
        assert _total_recibido(ws) == 400, \
            "leer() siguió leyendo con el watermark cruzado (sin backpressure)"
        ws.encolar({'type': 'ack', 'bytes': 400})  # el browser procesó todo
        await asyncio.sleep(0.2)
        assert _total_recibido(ws) == 600, \
            "el ack no reanudó la lectura del PTY"
        os.close(w)                                # EOF → cierra el WS

    try:
        _correr_sesion_fc(ws, r, escenario)
        assert ws.close_code == 4000               # el contrato EOF sigue vivo
    finally:
        try: os.close(r)
        except OSError: pass


def test_leer_sin_fc_no_frena():
    """fc=False (legacy): el stream nunca se detiene aunque nadie ackee."""
    r, w = os.pipe()
    ws = FakeWSFlujo()

    async def escenario(ws):
        for ch in (b'a', b'b', b'c'):
            os.write(w, ch * 200)
            await asyncio.sleep(0.08)
        assert _total_recibido(ws) == 600
        os.close(w)

    try:
        _correr_sesion_fc(ws, r, escenario, fc=False)
        assert ws.close_code == 4000
    finally:
        try: os.close(r)
        except OSError: pass


# ─── 4: wiring del endpoint ──────────────────────────────────────────────────

def test_ws_terminal_acepta_query_param_fc():
    params = inspect.signature(term.ws_terminal).parameters
    assert 'fc' in params, "ws_terminal debe aceptar el query param fc"


# ─── 5: refresh a pedido (auto-sanación al volver visible) ───────────────────

def test_refresh_dispara_refresh_client():
    r, w = os.pipe()
    ws = FakeWSFlujo()

    def _refreshes(run_mock):
        return [c for c in run_mock.call_args_list
                if c.args and 'refresh-client' in c.args[0]]

    async def escenario(ws):
        ws.encolar({'type': 'refresh'})
        await asyncio.sleep(0.15)
        os.close(w)

    try:
        run_mock = _correr_sesion_fc(ws, r, escenario)
        # 1 refresh-client del attach + 1 del mensaje {'type':'refresh'}
        assert len(_refreshes(run_mock)) >= 2, \
            f"el refresh del browser no llegó a tmux: {run_mock.call_args_list}"
    finally:
        try: os.close(r)
        except OSError: pass


if __name__ == "__main__":
    test_flujo_frena_en_high_y_reanuda_en_low()
    test_flujo_inactivo_nunca_frena()
    test_flujo_ack_clampa_en_cero_y_descarta_basura()
    test_flujo_visible_amplia_el_watermark()
    test_flujo_default_es_visible()
    test_flujo_set_visible_reevalua_el_gate()
    test_flujo_high_low_explicitos_ignoran_visibilidad()
    test_visible_message_amplia_el_watermark_en_la_sesion()
    test_leer_frena_en_watermark_y_ack_reanuda()
    test_leer_sin_fc_no_frena()
    test_ws_terminal_acepta_query_param_fc()
    test_refresh_dispara_refresh_client()
    print("OK")
