"""El re-seed post-resize NO puede pintar una pantalla MÁS VACÍA de la que hay.

BUG REPRODUCIDO 2026-07-19 ("las terminales se cortan"): un agente hace una
pregunta con opciones + una caja ASCII, el usuario ve la pregunta CORTADA a la
mitad y el resto del pane en blanco.

Cadena real medida (tmux 3.6 + control mode + xterm.js vendoreado):

 1. La app pinta su frame completo (44 filas) y queda IDLE esperando respuesta.
 2. Llega un resize que ACHICA las filas (relayout, drag de una card, cambio de
    ventana, re-tiling del mosaico...). `refresh-client -C` lo aplica al toque.
 3. tmux RECORTA su copia del alt-screen y **no la restaura** al volver a
    crecer: medido 44→30→44 deja 12 filas de contenido y el resto vacío.
    xterm.js, en cambio, SÍ restaura (mantiene las líneas en su buffer).
 4. La app está muda (espera al usuario) → se cumple la precondición del
    watchdog (`debe_resembrar`: sin output + alt-screen).
 5. `_hacer_seed()` captura la copia MUTILADA de tmux y la pinta sobre la
    pantalla SANA de xterm con `\\x1b[?1049h\\x1b[H\\x1b[2J` + cuerpo.

Resultado: la "reparación" es la que rompe. Sin watchdog, el usuario habría
visto la pregunta entera.

INVARIANTE que arregla la clase entera: el watchdog SOLO corre cuando el pane
no emitió NADA desde el resize. Una app muda no puede haber cambiado su
pantalla — así que todo contenido que el capture PERDIÓ respecto del último
seed es un artefacto del recorte de tmux, no salida de la app. Pintarlo solo
puede destruir.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plotspace.core.control_mode import masa_capture, reseed_seguro


FRAME = (
    '\x1b[38;5;244m──────────────────────\x1b[39m\n'
    ' ☐ Estructura \n'
    '\n'
    '❯ 1. Consola / Mission Control    ┌────────────┐\n'
    '  2. Paleta de comandos           │ VOZ        │\n'
    '  3. Panel acoplado, sin velo     └────────────┘\n'
)


def test_masa_capture_ignora_color_y_blancos():
    """La masa es CONTENIDO real: las secuencias SGR de `capture-pane -e` no
    cuentan como texto (si no, una línea vacía coloreada parecería llena)."""
    assert masa_capture(FRAME) == 5
    assert masa_capture('') == 0
    assert masa_capture('\n\n\n') == 0
    # Línea con SOLO color + espacios = vacía.
    assert masa_capture('\x1b[38;5;244m   \x1b[39m\n') == 0
    assert masa_capture('\x1b[31mhola\x1b[0m\n') == 1


def test_reseed_no_pinta_pantalla_vacia_sobre_contenido_vivo():
    """El caso extremo medido (44→13→44): tmux queda con CERO líneas. Pintar
    eso borra la pantalla entera del usuario."""
    assert reseed_seguro('', masa_previa=23) is False
    assert reseed_seguro('\n\n\n\n', masa_previa=23) is False


def test_reseed_no_pinta_capture_recortado():
    """El caso de la captura del usuario (44→30→44): tmux conserva 12 filas de
    44 y pierde el resto. Como la app estuvo MUDA, esa pérdida es del recorte
    de tmux — no puede ser un repintado legítimo."""
    assert reseed_seguro(FRAME, masa_previa=23) is False


def test_reseed_procede_cuando_no_hay_perdida():
    """El caso que el watchdog SÍ tiene que arreglar: la app no repintó tras el
    SIGWINCH y el capture trae el mismo contenido que la última vez. Ahí el
    seed es la única forma de sacar a la card del crop/pad (fix S1 original)."""
    assert reseed_seguro(FRAME, masa_previa=5) is True
    assert reseed_seguro(FRAME, masa_previa=3) is True    # la app agregó líneas


def test_reseed_sin_referencia_procede_si_hay_contenido():
    """Sin baseline (primer seed de la conexión) no hay nada que proteger: se
    pinta igual. Pero un capture VACÍO nunca se pinta: no aporta nada y solo
    puede borrar."""
    assert reseed_seguro(FRAME, masa_previa=None) is True
    assert reseed_seguro('', masa_previa=None) is False
