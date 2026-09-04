"""Tests de la lógica PURA del watchdog de pasos colgados.

Sin tmux ni DB: el cruce de timestamps que decide si un paso es candidato a
'estancado', y la búsqueda del TASK_* perdido en el scrollback completo.
"""
import plotspace.core.swarm_watchdog as wd


# ─── buscar_keyword_perdido: rescate del TASK_* fuera de la ventana de 100 ────

def test_encuentra_task_done_solo_en_linea():
    assert wd.buscar_keyword_perdido('blah\n✅ TASK_DONE\n$ ') == 'TASK_DONE'


def test_ignora_instruccion_no_keyword():
    # "Cuando termines escribí TASK_DONE" NO es un cierre real (hay letras).
    txt = 'Cuando termines escribí TASK_DONE en una línea sola\n$ '
    assert wd.buscar_keyword_perdido(txt) is None


def test_devuelve_el_ultimo_keyword():
    # Si aparecen varios, gana el MÁS RECIENTE (escaneo desde el final).
    txt = 'TASK_BLOCKED falta algo\n...\nTASK_DONE\n'
    assert wd.buscar_keyword_perdido(txt) == 'TASK_DONE'


def test_blocked_y_error():
    assert wd.buscar_keyword_perdido('- TASK_BLOCKED -\n') == 'TASK_BLOCKED'
    assert wd.buscar_keyword_perdido('TASK_ERROR\n') == 'TASK_ERROR'


def test_limpia_ansi():
    assert wd.buscar_keyword_perdido('\x1b[32mTASK_DONE\x1b[0m\n') == 'TASK_DONE'


def test_vacio_es_none():
    assert wd.buscar_keyword_perdido('') is None
    assert wd.buscar_keyword_perdido(None) is None
    assert wd.buscar_keyword_perdido('solo output normal\n$ ') is None


# ─── edad_paso ────────────────────────────────────────────────────────────────

def test_edad_paso_con_iniciado_ts():
    assert wd.edad_paso({'iniciado_ts': 100.0}, ahora=160.0) == 60.0


def test_edad_paso_sin_iniciado_ts_es_none():
    assert wd.edad_paso({}, ahora=160.0) is None


# ─── paso_candidato_estancado ─────────────────────────────────────────────────

def _paso(estado='running', iniciado_ts=100.0):
    return {'estado': estado, 'iniciado_ts': iniciado_ts, 'terminal_id': 5}


def test_no_candidato_si_no_running():
    assert wd.paso_candidato_estancado(_paso(estado='done'), 400.0, 180, trabajando=False) is False


def test_no_candidato_sin_iniciado_ts():
    # Sin sello no se puede juzgar la edad → conservador, no flagear.
    assert wd.paso_candidato_estancado(_paso(iniciado_ts=None), 400.0, 180, trabajando=False) is False


def test_no_candidato_si_joven():
    assert wd.paso_candidato_estancado(_paso(), 200.0, 180, trabajando=False) is False  # edad 100 < 180


def test_no_candidato_si_trabajando():
    # Viejo pero produciendo output (agent_watch=trabajando) → solo lento, no colgado.
    assert wd.paso_candidato_estancado(_paso(), 400.0, 180, trabajando=True) is False


def test_candidato_viejo_y_quieto():
    # edad 300 >= 180, no trabajando → candidato a estancado.
    assert wd.paso_candidato_estancado(_paso(), 400.0, 180, trabajando=False) is True


# ─── _ciclo: flujo de decisión (rescate / aviso) con fakes inyectados ─────────

import asyncio
import time as _time
from plotspace.core import events
import plotspace.routers.terminals as _term


class _Rec:
    def __init__(self):
        self.eventos = []

    async def broadcast(self, pid, data):
        self.eventos.append((pid, data))


def _correr_ciclo(pasos, scrollback, trabajando=False, limpiar_avisados=True):
    """Corre wd._ciclo() con _workflows_running/scrollback/trabajando/broadcaster
    fakeados. Devuelve (eventos_broadcast, llamadas_a_procesar_keyword)."""
    rec = _Rec()
    kw_calls = []

    async def _fake_scroll(tid):
        return scrollback

    async def _fake_proc(tid, pid, kw):
        kw_calls.append((tid, pid, kw))

    orig = (wd._workflows_running, wd._capturar_scrollback, wd._esta_trabajando,
            events.broadcaster.broadcast, _term._procesar_keyword_evento,
            asyncio.to_thread)
    wd._workflows_running = lambda: [
        {'id': 'wf1', 'project_id': 7, 'nombre': 'X', 'pasos': pasos}]
    wd._capturar_scrollback = _fake_scroll
    wd._esta_trabajando = lambda tid: trabajando
    events.broadcaster.broadcast = rec.broadcast
    _term._procesar_keyword_evento = _fake_proc
    async def _direct_to_thread(fn, *args, **kwargs):
        return fn(*args, **kwargs)
    asyncio.to_thread = _direct_to_thread
    if limpiar_avisados:
        wd._avisados.clear()
    try:
        asyncio.run(wd._ciclo())
    finally:
        (wd._workflows_running, wd._capturar_scrollback, wd._esta_trabajando,
         events.broadcaster.broadcast, _term._procesar_keyword_evento,
         asyncio.to_thread) = orig
    return rec.eventos, kw_calls


def _paso_viejo(estado='running', tid=5):
    return {'agente': 'Backend', 'estado': estado, 'terminal_id': tid,
            'iniciado_ts': _time.time() - 1000}   # 1000s > umbral


def test_ciclo_rescata_task_done_perdido():
    # TASK_DONE en el scrollback (fuera de la ventana de 100) → se resuelve solo.
    eventos, kw_calls = _correr_ciclo([_paso_viejo()], 'mucho output...\n✅ TASK_DONE\n')
    assert kw_calls == [(5, 7, 'TASK_DONE')]        # se llamó al resolutor del monitor
    tipos = [d['type'] for _, d in eventos]
    assert 'paso_rescatado' in tipos
    assert 'paso_estancado' not in tipos            # rescatado → NO se molesta al humano


def test_ciclo_avisa_estancado_si_no_hay_keyword():
    # Agente murió / quedó en prompt: sin TASK_* en todo el scrollback → aviso.
    eventos, kw_calls = _correr_ciclo([_paso_viejo()], 'output normal\n$ ')
    assert kw_calls == []
    estancados = [d for _, d in eventos if d['type'] == 'paso_estancado']
    assert len(estancados) == 1
    assert estancados[0]['terminal_id'] == 5
    assert estancados[0]['workflow_id'] == 'wf1'
    assert estancados[0]['edad_seg'] >= 180


def test_ciclo_no_reemite_mismo_episodio():
    wd._avisados.clear()
    e1, _ = _correr_ciclo([_paso_viejo()], 'sin keyword\n$ ', limpiar_avisados=False)
    e2, _ = _correr_ciclo([_paso_viejo()], 'sin keyword\n$ ', limpiar_avisados=False)
    assert sum(1 for _, d in e1 if d['type'] == 'paso_estancado') == 1
    assert sum(1 for _, d in e2 if d['type'] == 'paso_estancado') == 0   # throttle


def test_ciclo_no_toca_paso_trabajando():
    # Viejo pero produciendo output → ni rescate ni aviso.
    eventos, kw_calls = _correr_ciclo([_paso_viejo()], 'cualquier cosa', trabajando=True)
    assert kw_calls == []
    assert eventos == []
