# plotspace/tests/test_mailbox_reentrega.py
"""El historial del mailbox NO se puede re-entregar. Pasó de verdad.

EL INCIDENTE (2026-07-25, medido en este repo)
---------------------------------------------
Al reiniciar el server para aplicar un update, el watcher volvió a leer
`.jarvis/MAILBOX.md` desde un offset desfasado y **re-registró ~108 líneas
históricas como mensajes nuevos**. Peor: resolvió los destinatarios contra las
terminales de HOY, así que 7 mensajes de sagas del 21-22 de julio aterrizaron en
el inbox de un agente que no tenía nada que ver — porque su terminal reusaba el
nombre «Claude Code #4» de julio.

LA LECCIÓN
----------
El offset en bytes era el ÚNICO candado contra la re-entrega, y un offset es un
dato frágil: se puede perder, quedar viejo o desincronizarse si alguien edita el
archivo. Un canal de mensajes no puede apoyar su corrección en eso.

Ahora el offset es solo una OPTIMIZACIÓN (no releer lo mismo) y la corrección la
da la identidad del mensaje: una línea idéntica que ya se registró no vuelve a
entrar. La vía autoritativa (`jv msg`, que registra él mismo) NO pasa por este
filtro: ahí el usuario puede querer repetir el mismo texto a propósito.
"""
import asyncio

import pytest

from plotspace.core import database as db


@pytest.fixture(autouse=True)
def db_temporal(tmp_path, monkeypatch):
    """DB propia por test (no tocar la del workspace vivo)."""
    ruta = str(tmp_path / 'test.db')
    monkeypatch.setattr(db, 'DB_PATH', ruta)
    db.init_db()
    yield


def _registrar(msg='hola', de='A', para='B', tid=2):
    return db.registrar_mensaje_mailbox(7, de, para, msg, tid, 'normal')


# ─── El filtro de identidad ───────────────────────────────────────────────────

def test_un_mensaje_identico_ya_registrado_se_reconoce():
    _registrar()
    assert db.mensaje_ya_registrado(7, 'A', 'B', 'hola') is True


def test_un_mensaje_nuevo_no_se_confunde_con_uno_viejo():
    _registrar()
    assert db.mensaje_ya_registrado(7, 'A', 'B', 'otra cosa') is False
    assert db.mensaje_ya_registrado(7, 'A', 'C', 'hola') is False
    assert db.mensaje_ya_registrado(7, 'X', 'B', 'hola') is False


def test_el_mismo_texto_en_otro_proyecto_no_cuenta():
    _registrar()
    assert db.mensaje_ya_registrado(99, 'A', 'B', 'hola') is False


def test_reconoce_tambien_los_que_quedaron_sin_destino():
    """Los 36 `@jarvis` del historial son justamente los que más se repetían."""
    db.registrar_mensaje_mailbox(7, 'A', 'jarvis', 'che', None, 'normal')
    assert db.mensaje_ya_registrado(7, 'A', 'jarvis', 'che') is True


# ─── El watcher no re-registra el historial ───────────────────────────────────

def test_el_watcher_ignora_una_linea_que_ya_habia_procesado(monkeypatch):
    """El escenario exacto del incidente: el offset se fue al pasado y el
    watcher relee líneas que ya estaban en la tabla."""
    from plotspace.core import mailbox
    monkeypatch.setattr(mailbox, '_terminales_de',
                        lambda pid: [{'id': 2, 'nombre': 'B', 'tipo_ia': 'claude'}])

    asyncio.run(mailbox._entregar(7, 'A', 'B', 'mensaje historico'))
    asyncio.run(mailbox._entregar(7, 'A', 'B', 'mensaje historico'))   # relectura

    filas = db.mensajes_pendientes_mailbox(7)
    assert len(filas) == 1, 'la relectura duplicó el mensaje'


def test_el_watcher_si_registra_mensajes_realmente_distintos(monkeypatch):
    from plotspace.core import mailbox
    monkeypatch.setattr(mailbox, '_terminales_de',
                        lambda pid: [{'id': 2, 'nombre': 'B', 'tipo_ia': 'claude'}])
    asyncio.run(mailbox._entregar(7, 'A', 'B', 'uno'))
    asyncio.run(mailbox._entregar(7, 'A', 'B', 'dos'))
    assert len(db.mensajes_pendientes_mailbox(7)) == 2


def test_un_mensaje_ya_entregado_no_revive_al_releerse(monkeypatch):
    """El daño real del incidente: mensajes YA leídos volvieron a 'pendiente' y
    se le re-entregaron a un agente nuevo que reusaba el nombre."""
    from plotspace.core import mailbox
    monkeypatch.setattr(mailbox, '_terminales_de',
                        lambda pid: [{'id': 2, 'nombre': 'B', 'tipo_ia': 'claude'}])
    asyncio.run(mailbox._entregar(7, 'A', 'B', 'viejo'))
    db.marcar_mensajes_entregados([m['id'] for m in db.mensajes_pendientes_mailbox(7)])
    assert db.mensajes_pendientes_mailbox(7) == []

    asyncio.run(mailbox._entregar(7, 'A', 'B', 'viejo'))          # relectura
    assert db.mensajes_pendientes_mailbox(7) == [], 'un mensaje ya leído revivió'


# ─── La vía autoritativa (`jv msg`) NO se filtra ──────────────────────────────

def test_jv_msg_puede_repetir_el_mismo_texto_a_proposito():
    """`jv msg` registra él mismo, con acuse al que escribe: si manda dos veces
    el mismo recordatorio, las dos tienen que llegar."""
    _registrar(msg='acordate del bump')
    _registrar(msg='acordate del bump')
    assert len(db.mensajes_pendientes_mailbox(7)) == 2
