"""La salida del motor no puede matar al motor.

QUÉ PASÓ (2026-07-27)
=====================
La app nativa de Windows arrancaba el motor y moría antes de escuchar el
puerto. El traceback terminaba acá:

    File "plotspace/core/auth.py", line 177, in imprimir_banner
      print('┌────────────…────────┐')
    UnicodeEncodeError: 'charmap' codec can't encode characters…

La consola de Windows usa cp1252, que no tiene los caracteres de dibujo de
caja. El `print` del banner levantaba la excepción DENTRO del lifespan de
FastAPI, y eso aborta el arranque entero: «Application startup failed».

Un mensaje decorativo tumbando el servidor es desproporcionado por donde se lo
mire, y no es un problema de ese banner en particular: cualquier `print` con
una tilde, una flecha o un ✓ hace lo mismo. Por eso el arreglo es en la salida
—una vez, para todo el paquete— y no en el texto de cada mensaje.
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plotspace.core import consola


class _ConsolaWindows(io.TextIOBase):
    """Una salida cp1252, como la de una consola de Windows en español.

    Modela lo que importa: `write` codifica con la codificación VIGENTE y
    levanta si no puede — igual que la consola real — y `reconfigure` la
    cambia de verdad. Un fake que ignorara reconfigure haría imposible que
    ningún arreglo pasara el test, y estaría probando el fake, no el código.
    """

    def __init__(self):
        self.escrito = []
        self._enc = 'cp1252'
        self._errors = 'strict'

    @property
    def encoding(self):
        return self._enc

    def reconfigure(self, encoding=None, errors=None):
        if encoding:
            self._enc = encoding
        if errors:
            self._errors = errors

    def write(self, s):
        s.encode(self._enc, errors=self._errors)
        self.escrito.append(s)
        return len(s)


class _SinReconfigure:
    """Un stream viejo o sustituido (pytest usa uno) que no sabe reconfigurar."""
    encoding = 'cp1252'

    def write(self, s):
        return len(s)


def test_un_banner_con_dibujo_de_caja_no_tumba_el_arranque(monkeypatch):
    # El bug exacto: sin protección, este print aborta el lifespan de FastAPI y
    # el motor nunca llega a escuchar el puerto.
    from plotspace.core import auth
    monkeypatch.setattr(sys, 'stdout', _ConsolaWindows())
    monkeypatch.setenv('JARVIS_TOKEN', 'token-de-prueba')
    consola.asegurar_utf8(sys.stdout)
    auth.imprimir_banner()          # no debe levantar


def test_reconfigura_una_salida_que_no_habla_utf8():
    class Falsa:
        encoding = 'cp1252'
        def __init__(self): self.pedido = None
        def reconfigure(self, **kw): self.pedido = kw

    f = Falsa()
    consola.asegurar_utf8(f)
    assert f.pedido == {'encoding': 'utf-8', 'errors': 'replace'}


def test_no_toca_una_salida_que_ya_habla_utf8():
    class Falsa:
        encoding = 'utf-8'
        def __init__(self): self.pedido = None
        def reconfigure(self, **kw): self.pedido = kw

    f = Falsa()
    consola.asegurar_utf8(f)
    assert f.pedido is None, 'reconfiguró una salida que ya estaba bien'


def test_una_salida_sin_reconfigure_no_rompe():
    # pytest sustituye stdout por un stream propio; el arreglo no puede
    # depender de que el objeto tenga el método.
    consola.asegurar_utf8(_SinReconfigure())     # no debe levantar


def test_none_no_rompe():
    # En un proceso sin consola (pythonw, un servicio) sys.stdout es None.
    consola.asegurar_utf8(None)
