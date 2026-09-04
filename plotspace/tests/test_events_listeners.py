"""Tests del hook de listeners internos del EventBroadcaster (fase 2 Telegram)."""
import asyncio

from plotspace.core.events import EventBroadcaster


def test_listener_recibe_broadcast_global_sin_conexiones():
    b = EventBroadcaster()
    recibidos = []

    async def cb(data):
        recibidos.append(data)

    b.escuchar(cb)
    asyncio.run(b.broadcast_global({'type': 'x'}))
    assert recibidos == [{'type': 'x'}]


def test_listener_una_sola_vez_con_varios_proyectos():
    b = EventBroadcaster()

    class WSFake:
        async def send_json(self, d):
            raise RuntimeError('socket roto')

    b._conns = {1: [WSFake()], 2: [WSFake()], 3: [WSFake()]}
    recibidos = []

    async def cb(data):
        recibidos.append(data)

    b.escuchar(cb)
    asyncio.run(b.broadcast_global({'type': 'y'}))
    assert len(recibidos) == 1


def test_listener_roto_no_tira_el_broadcast():
    b = EventBroadcaster()

    async def malo(data):
        raise RuntimeError('bum')

    ok = []

    async def bueno(data):
        ok.append(data)

    b.escuchar(malo)
    b.escuchar(bueno)
    asyncio.run(b.broadcast(1, {'type': 'z'}))
    assert ok == [{'type': 'z'}]


def test_broadcast_por_proyecto_tambien_notifica():
    b = EventBroadcaster()
    tipos = []

    async def cb(data):
        tipos.append(data['type'])

    b.escuchar(cb)
    asyncio.run(b.broadcast(7, {'type': 'w'}))
    assert tipos == ['w']
