"""Fase 8: fast-path event-driven del monitor de keywords (despertar vía asyncio.Event).
La detección canónica (capture+diff+_linea_es_keyword) NO cambia — eso lo cubre
test_keyword_detection.py. Acá solo el mecanismo de wake-up (aditivo, no-op si falla)."""
import asyncio
from plotspace.routers import terminals as t


def test_solicitar_chequeo_noop_sin_event():
    # sin Event registrado (monitor no corriendo) → no-op, NO crashea
    t._monitor_wakeups.pop(99991, None)
    t.solicitar_chequeo_inmediato(99991)   # no debe lanzar


def test_solicitar_chequeo_despierta_el_loop():
    async def main():
        ev = asyncio.Event()
        t._monitor_wakeups[99992] = ev
        assert not ev.is_set()
        t.solicitar_chequeo_inmediato(99992)
        assert ev.is_set()
        # el wait del loop resuelve inmediato cuando está set (vs esperar timeout=2.0)
        await asyncio.wait_for(ev.wait(), timeout=0.1)
        t._monitor_wakeups.pop(99992, None)
    asyncio.run(main())


def test_agent_watch_resuelve_el_import_del_fastpath():
    # agent_watch hace un lazy import de esta función; debe resolver y ser callable
    from plotspace.routers.terminals import solicitar_chequeo_inmediato
    assert callable(solicitar_chequeo_inmediato)


def test_timeout_es_la_red_de_seguridad():
    # si NADIE despierta el Event, wait_for cae por timeout (el loop avanza igual = peor caso de hoy)
    async def main():
        ev = asyncio.Event()
        try:
            await asyncio.wait_for(ev.wait(), timeout=0.05)
            raise AssertionError("no debería resolver: nadie lo despertó")
        except asyncio.TimeoutError:
            pass   # correcto: el monitor avanzaría por timeout
    asyncio.run(main())


if __name__ == "__main__":
    test_solicitar_chequeo_noop_sin_event(); print("  OK noop")
    test_solicitar_chequeo_despierta_el_loop(); print("  OK despierta")
    test_agent_watch_resuelve_el_import_del_fastpath(); print("  OK import")
    test_timeout_es_la_red_de_seguridad(); print("  OK timeout")
    print("test_fastpath_monitor: TODOS OK")
