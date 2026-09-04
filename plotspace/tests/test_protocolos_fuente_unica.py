# Los textos del protocolo tienen UNA sola fuente, y los dos motores la leen.
#
# Estos textos son las instrucciones que recibe cada agente en cada sesión.
# Mientras vivieron como constantes de Python, el motor Rust no podía inyectar
# lo mismo sin copiarlas — y dos copias de un texto largo se separan sin que
# nadie lo note. El día que se separen, cada agente recibe instrucciones
# distintas según qué motor le armó la sesión, y eso no se ve como un bug: se ve
# como agentes que "no siguen las reglas".

import os

from plotspace import protocolos
from plotspace.core import agent_live, mailbox, puertos
from plotspace.core import memoria_categorias as mcat
from plotspace.routers import memory

DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'protocolos')

BLOQUES = [
    ('memoria', memory.PROTOCOLO,     memory.PROTOCOLO_MARKER_START,     memory.PROTOCOLO_MARKER_END),
    ('mailbox', mailbox.PROTOCOLO,    mailbox.PROTOCOLO_MARKER_START,    mailbox.PROTOCOLO_MARKER_END),
    ('puertos', puertos.PROTOCOLO,    puertos.PROTOCOLO_MARKER_START,    puertos.PROTOCOLO_MARKER_END),
    ('live',    agent_live.PROTOCOLO, agent_live.PROTOCOLO_MARKER_START, agent_live.PROTOCOLO_MARKER_END),
]


def test_cada_protocolo_sale_de_su_archivo():
    """El texto que usa Python es EXACTAMENTE el del archivo compartido."""
    for nombre, texto, _, _ in BLOQUES:
        crudo = protocolos.leer(nombre)
        if nombre == 'memoria':
            crudo = protocolos.memoria(mcat.bloque_protocolo())
        assert texto == crudo, f'{nombre}: el texto en memoria difiere del archivo'


def test_los_markers_viajan_dentro_del_texto():
    """Quien inyecta busca los markers para reemplazar el bloque sin tocar el
    resto del archivo. Si el texto no los trae, la inyección deja de ser
    idempotente y cada arranque agrega otra copia del protocolo."""
    for nombre, texto, inicio, fin in BLOQUES:
        assert texto.startswith(inicio), f'{nombre}: no empieza con su marker'
        assert texto.rstrip().endswith(fin), f'{nombre}: no termina con su marker'


def test_la_lista_de_categorias_no_esta_escrita_a_mano():
    """Las categorías salen de memoria_categorias —que es quien las valida—, no
    del texto. Escritas a mano se desincronizan con la lista real y el agente
    elige una categoría que el lint después marca como inválida."""
    crudo = protocolos.leer('memoria')
    assert '{CATEGORIAS}' in crudo
    assert mcat.bloque_protocolo() in protocolos.memoria(mcat.bloque_protocolo())


def test_los_archivos_existen_y_no_estan_vacios():
    """Son parte del producto, no un caché: si faltan, los agentes arrancan sin
    protocolo y el enjambre pierde la coordinación entera."""
    for nombre, _, _, _ in BLOQUES:
        ruta = os.path.join(DIR, f'{nombre}.md')
        assert os.path.isfile(ruta), f'falta {ruta}'
        assert os.path.getsize(ruta) > 200, f'{ruta} está sospechosamente vacío'


if __name__ == '__main__':
    test_cada_protocolo_sale_de_su_archivo()
    test_los_markers_viajan_dentro_del_texto()
    test_la_lista_de_categorias_no_esta_escrita_a_mano()
    test_los_archivos_existen_y_no_estan_vacios()
    print('ok')
