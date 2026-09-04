"""Garantía de tipeo fluido automático: el server NUNCA debe arrancar en uvloop.

uvloop (que arrastra `uvicorn[standard]`) sufre en este entorno (WSL2 + Py3.14)
un stall periódico del event loop de ~0.4-1s que corta el eco del tipeo de TODAS
las terminales a la vez. La cura no es el banner "Optimizar tipeo" + reiniciar a
mano: es que uvloop NO exista, así uvicorn cae SIEMPRE en asyncio, se arranque
como se arranque. Pedido del usuario (2026-07-03): que sea automático, sin botón.

Si estos tests fallan, alguien reinstaló `uvicorn[standard]` (trae uvloop):
sacalo de requirements.txt (dejar `uvicorn` a secas + websockets + httptools).
"""
import importlib.util
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))


def test_uvloop_no_instalado():
    assert importlib.util.find_spec('uvloop') is None, (
        "uvloop está instalado y va a cortar el tipeo. Reinstalá deps SIN el extra "
        "[standard] de uvicorn (es quien lo arrastra)."
    )


def test_arranque_auto_cae_en_asyncio():
    """El arranque 'auto' de uvicorn (lo que elige si te olvidás `--loop asyncio`)
    debe producir un event loop de asyncio puro, no uvloop."""
    try:
        from uvicorn.loops.auto import auto_loop_factory
    except ImportError:
        # La API interna de uvicorn cambió de nombre; la garantía real ya la cubre
        # test_uvloop_no_instalado (sin uvloop, 'auto' no tiene de dónde sacarlo).
        return
    loop = auto_loop_factory(use_subprocess=False)()
    try:
        assert 'uvloop' not in (type(loop).__module__ or ''), (
            f"el arranque auto cayó en {type(loop).__module__}"
        )
    finally:
        loop.close()


def test_detector_reporta_asyncio():
    """nombre_event_loop() (el que alimenta el banner) reporta 'asyncio' bajo un
    loop normal → el banner 'Optimizar tipeo' nunca se prende."""
    import asyncio
    from plotspace.routers.system import nombre_event_loop, loop_degradado
    loop = asyncio.new_event_loop()
    try:
        nombre = loop.run_until_complete(_devolver(nombre_event_loop))
        assert nombre == 'asyncio'
        assert loop_degradado(nombre) is False
    finally:
        loop.close()


async def _devolver(fn):
    return fn()


def main():
    test_uvloop_no_instalado()
    test_arranque_auto_cae_en_asyncio()
    test_detector_reporta_asyncio()
    print("OK")


if __name__ == "__main__":
    main()
