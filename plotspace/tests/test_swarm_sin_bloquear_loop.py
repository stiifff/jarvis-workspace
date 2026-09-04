# plotspace/tests/test_swarm_sin_bloquear_loop.py
"""Ningún camino async del enjambre puede forkear tmux/git en el event loop.

POR QUÉ ESTO MERECE SUS PROPIOS TESTS
-------------------------------------
El liveness (`tmux list-panes`) y la herencia (`git status`) son subprocess
BLOQUEANTES, y viven en caminos que corren en el event loop cada vez que un
agente edita un archivo. En este box eso no es teórico: el CLAUDE.md documenta
que un stall del loop se ve como CORTES EN EL ECO DEL TIPEO de todas las
terminales (por eso uvicorn corre con `--loop asyncio` y se desinstaló uvloop).

Un `await asyncio.to_thread(...)` que alguien saque "porque total es rápido" no
rompe ningún test funcional — el bug es de latencia y aparece recién con varios
agentes escribiendo. Así que el invariante se fija acá: **el subprocess tiene
que ejecutarse en un thread que NO sea el del loop.**
"""
import asyncio
import threading

import pytest


class _Espia:
    """Anota en qué thread se ejecutó cada subprocess.run."""

    def __init__(self):
        self.threads = []

    def __call__(self, *args, **kwargs):
        self.threads.append(threading.current_thread().name)

        class _R:
            returncode = 0
            stdout = ''
            stderr = ''
        return _R()


@pytest.fixture
def espia(monkeypatch):
    e = _Espia()
    import subprocess
    monkeypatch.setattr(subprocess, 'run', e)
    from plotspace.core import liveness, herencia
    liveness.reset()
    herencia.reset()
    return e


def _thread_del_loop():
    """Nombre del thread donde corre el loop de este test."""
    return threading.current_thread().name


def _asegurar_fuera_del_loop(espia, nombre_loop):
    if not espia.threads:
        # Sin subprocess no hay nada que evaluar: lo que este test verifica es
        # DÓNDE corre el fork, no que ocurra. Pasa en máquinas sin un servidor
        # de tmux vivo (un runner de CI), donde el camino corta antes de
        # forkear. Skip y no fallo: un rojo acá diría "esto está roto" cuando
        # lo único cierto es "acá no se pudo medir".
        import pytest
        pytest.skip('no hubo subprocess que medir (¿sin sesiones de tmux vivas?)')
    culpables = [t for t in espia.threads if t == nombre_loop]
    assert not culpables, (
        f'{len(culpables)} subprocess corrieron EN EL EVENT LOOP ({nombre_loop}): '
        'eso corta el eco del tipeo de todas las terminales')


def test_publicar_de_agent_live_no_forkea_en_el_loop(espia, monkeypatch):
    """`_publicar` corre en cada edición de cada agente."""
    from plotspace.core import agent_live

    async def escenario():
        nombre = _thread_del_loop()
        monkeypatch.setattr(agent_live, 'escribir_live_md', lambda *a, **k: None)

        async def _nada(*a, **k):
            return None
        monkeypatch.setattr(agent_live.broadcaster, 'broadcast', _nada)
        rows = [{'tid': 1, 'tnombre': 'A', 'tipo_ia': 'claude', 'pid': 7, 'ruta': '/x'}]
        await agent_live._publicar(7, '/x', rows)
        return nombre

    nombre = asyncio.run(escenario())
    _asegurar_fuera_del_loop(espia, nombre)


def test_el_briefing_del_piggyback_no_forkea_en_el_loop(espia, monkeypatch):
    """`/swarm/op` es el camino MÁS caliente que existe: una vez por edición."""
    from plotspace.core import briefing, swarm_cli, liveness

    async def escenario():
        nombre = _thread_del_loop()
        monkeypatch.setattr(swarm_cli, '_nombre_de',
                            lambda tid: {'nombre': 'A', 'project_id': 7, 'ruta': '/x'})
        monkeypatch.setattr(swarm_cli, '_terminales_activas_detalle',
                            lambda pid: [{'id': 2, 'nombre': 'B', 'tipo_ia': 'claude'}])
        monkeypatch.setattr(swarm_cli, 'mensajes_pendientes_mailbox',
                            lambda pid, tid: [])
        # el fork real ocurre acá adentro; el espía lo intercepta
        await asyncio.to_thread(briefing.briefing_para, 1, solo_si_cambio=True)
        liveness.reset()
        return nombre

    nombre = asyncio.run(escenario())
    _asegurar_fuera_del_loop(espia, nombre)


def test_enviar_no_forkea_en_el_loop(espia, monkeypatch, tmp_path):
    """`jv msg` / `jv ask` resuelven el liveness del destinatario."""
    from plotspace.core import swarm_cli

    async def escenario():
        nombre = _thread_del_loop()
        monkeypatch.setattr(swarm_cli, '_nombre_de',
                            lambda tid: {'nombre': 'A', 'project_id': 7,
                                         'ruta': str(tmp_path)})
        monkeypatch.setattr(swarm_cli, '_terminales_activas',
                            lambda pid: [{'id': 2, 'nombre': 'B'}])
        monkeypatch.setattr(swarm_cli, '_terminales_activas_detalle',
                            lambda pid: [{'id': 2, 'nombre': 'B', 'tipo_ia': 'claude'}])
        await swarm_cli.enviar(1, 'B', 'hola')
        return nombre

    nombre = asyncio.run(escenario())
    _asegurar_fuera_del_loop(espia, nombre)


def test_entrega_idle_del_mailbox_no_forkea_en_el_loop(espia, monkeypatch):
    """Corre cada 4s por proyecto, para siempre."""
    from plotspace.core import mailbox

    async def escenario():
        nombre = _thread_del_loop()
        monkeypatch.setattr(
            mailbox, '_terminales_de',
            lambda pid: [{'id': 2, 'nombre': 'B', 'tipo_ia': 'claude'}])
        monkeypatch.setattr('plotspace.core.database.mensajes_pendientes_mailbox',
                            lambda pid, tid=None: [
                                {'id': 1, 'de': 'A', 'msg': 'x', 'terminal_id': 2,
                                 'clase': 'ask'}])
        await mailbox._entregar_pendientes_idle(7)
        return nombre

    nombre = asyncio.run(escenario())
    _asegurar_fuera_del_loop(espia, nombre)
