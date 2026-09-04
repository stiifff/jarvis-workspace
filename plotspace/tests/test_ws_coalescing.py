"""Coalescing de la cola WS del motor control (fix "parpadeo del cursor" +
overhead de mensajes, 2026-07-17).

Un redraw de claude (full-repaint por tecla) llega en 12-43 eventos %output;
el _enviador viejo hacía 1 send_text POR evento → el frame cruzaba al browser
partido (el cursor pintaba apagado entre mensajes = parpadeo) y bajo flood el
loop pagaba ~10× mensajes WS (y deflate por mensaje). `_juntar_cola` une lo
YA encolado (sin esperar nada nuevo — cero latencia agregada) hasta un tope,
y reporta el EOF (None) para que el _enviador cierre en el mismo punto en que
cerraba antes.
"""
import asyncio

from plotspace.routers.terminals import _COALESCE_MAX, _juntar_cola


def test_cola_vacia_devuelve_primero_identico():
    cola = asyncio.Queue()
    primero = b'eco'
    data, eof = _juntar_cola(cola, primero)
    assert data is primero
    assert eof is False


def test_junta_todo_lo_encolado_en_orden():
    cola = asyncio.Queue()
    for parte in (b'a', b'b', b'c'):
        cola.put_nowait(parte)
    assert _juntar_cola(cola, b'0') == (b'0abc', False)
    assert cola.qsize() == 0


def test_respeta_el_tope_y_deja_el_resto_encolado():
    cola = asyncio.Queue()
    grande = b'x' * 100_000
    for _ in range(5):
        cola.put_nowait(grande)
    data, eof = _juntar_cola(cola, grande, tope=256_000)
    # Junta hasta cruzar el tope (el chunk que lo cruza entra: ya salió de la
    # cola) y NO sigue drenando después.
    assert len(data) == 300_000
    assert eof is False
    assert cola.qsize() == 3


def test_none_eof_corta_la_union_y_se_reporta():
    cola = asyncio.Queue()
    cola.put_nowait(b'x')
    cola.put_nowait(None)
    cola.put_nowait(b'y')
    data, eof = _juntar_cola(cola, b'0')
    assert data == b'0x'
    assert eof is True
    # Lo posterior al EOF queda sin mandar — igual que antes del coalescing
    # (el _enviador retornaba en el None sin leer más).
    assert cola.get_nowait() == b'y'


def test_eof_inmediato_con_primero_solo():
    cola = asyncio.Queue()
    cola.put_nowait(None)
    data, eof = _juntar_cola(cola, b'solo')
    assert data == b'solo'
    assert eof is True


def test_tope_default_razonable():
    # Guard de sanidad: el tope existe y está en un rango que junta un redraw
    # entero (>=64KB) sin armar sends monstruosos (<=1MB).
    assert 64 * 1024 <= _COALESCE_MAX <= 1024 * 1024
