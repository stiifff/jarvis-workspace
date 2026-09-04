"""La salida del motor, a prueba de la consola de Windows.

POR QUÉ EXISTE
==============
La consola de Windows usa la codepage del sistema (cp1252 en español), no
UTF-8. Cualquier `print` con un carácter fuera de ASCII —una tilde, una flecha,
un ✓, los caracteres de dibujo de caja del banner— levanta UnicodeEncodeError.

Y cuando eso pasa DENTRO del lifespan de FastAPI, no queda en un mensaje feo:
aborta el arranque entero. El 2026-07-27 el motor nativo moría así, antes de
escuchar el puerto, y la app se quedaba en «Esperando al motor…» sin ninguna
pista — porque su stderr iba a null.

Se arregla en la salida, una vez, y no en el texto de cada mensaje: escribir
todo en ASCII pelado es una disciplina que nadie sostiene, y el día que alguien
ponga una tilde en un `print` el servidor no tiene que caerse por eso.
"""
import sys


def asegurar_utf8(*streams) -> None:
    """Pone las salidas en UTF-8 con `errors='replace'`.

    `replace` y no `strict`: si algo no se puede representar, que salga un `?`
    — un carácter perdido en un log jamás justifica tumbar el proceso.

    Tolera todo lo que puede venir: None (proceso sin consola, como pythonw),
    streams sustituidos que no tienen `reconfigure` (el de pytest), y los que
    ya hablan UTF-8, que no se tocan.
    """
    for s in streams:
        if s is None:
            continue
        try:
            if (getattr(s, 'encoding', '') or '').lower().replace('-', '') == 'utf8':
                continue
            s.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            # Sin reconfigure o sin permiso: seguir. Esto es una mejora de la
            # salida, nunca un motivo para que el motor no arranque.
            pass


def asegurar_salida_estandar() -> None:
    """Protege stdout y stderr del proceso."""
    asegurar_utf8(sys.stdout, sys.stderr)
