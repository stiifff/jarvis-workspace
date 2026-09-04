"""Arranque canónico de Jarvis a prueba de olvidos: `python -m backend`.

Hornea `loop='asyncio'`. Motivo: uvicorn[standard] instala uvloop y lo elige por
default; en este entorno (WSL2 + Python 3.14) uvloop traba el event loop ~0.4-1s
de forma periódica bajo el workload subprocess/PTY → se congela el eco de TODAS
las terminales a la vez (el "corte de un segundo" del tipeo). Ver
backend.routers.system._comando_uvicorn para los números medidos.

Equivale a:
    uvicorn plotspace.main:app --host 0.0.0.0 --port 3000 --loop asyncio
pero sin depender de que nadie recuerde el flag (el footgun que dejaba el server
en uvloop). El re-exec del updater y el Dockerfile fuerzan el mismo loop.

Host/puerto se pueden override con JARVIS_HOST / JARVIS_PORT.
"""
import os

import uvicorn

if __name__ == '__main__':
    uvicorn.run(
        'plotspace.main:app',
        host=os.environ.get('JARVIS_HOST', '0.0.0.0'),
        port=int(os.environ.get('JARVIS_PORT', '3000')),
        loop='asyncio',
    )
