"""
memoria_categorias — la taxonomía canónica de la memoria compartida.

Cada memoria pertenece a UNA categoría (~10 fijas, curadas): así el INDEX se
agrupa por tema (un agente de terminales escanea SU sección, no 130 líneas
planas), el recall gana una señal, y la salud se reporta por cuadro. El campo
`categoria:` del frontmatter es la fuente de verdad; si falta, `clasificar()`
la infiere por tags/slug (determinista, cero API) y lo que no matchea queda
'sin-clasificar' para que el lint lo marque.

Módulo compartido: lo usan el router (parser + INDEX), el recall (señal) y el
protocolo (lista para los agentes). Stdlib pura, sin imports de routers.
"""

# id → (nombre legible, keywords que la disparan en tags/slug)
# La LISTA vive en `plotspace/protocolos/categorias.json`, no acá: el motor Rust
# clasifica y arma el INDEX con las mismas categorías, y dos copias de una lista
# de keywords se separan sin que nadie lo note — el día que se separen, la misma
# memoria cae en una categoría distinta según qué motor la leyó.
def _cargar():
    import json
    import os
    ruta = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'protocolos', 'categorias.json')
    with open(ruta, encoding='utf-8') as f:
        return [{'id': c['id'], 'nombre': c['nombre'], 'keywords': set(c['keywords'])}
                for c in json.load(f)]


CATEGORIAS = _cargar()

SIN_CLASIFICAR = 'sin-clasificar'

NOMBRE = {c['id']: c['nombre'] for c in CATEGORIAS}
NOMBRE[SIN_CLASIFICAR] = 'Sin clasificar'
ORDEN = [c['id'] for c in CATEGORIAS]
_IDS_VALIDOS = set(ORDEN) | {SIN_CLASIFICAR}


def es_valida(cid: str) -> bool:
    return cid in _IDS_VALIDOS


def clasificar(tags, slug: str) -> str:
    """Infiere la categoría por tags + tokens del slug (fallback determinista
    cuando el frontmatter no trae `categoria:`). 'sin-clasificar' si no matchea
    ninguna — el lint lo marca para que un humano/agente la fije."""
    toks = {str(t).strip().lower() for t in (tags or []) if str(t).strip()}
    toks |= {p for p in (slug or '').lower().split('-') if p}
    mejor, score = SIN_CLASIFICAR, 0
    for c in CATEGORIAS:
        s = len(toks & c['keywords'])
        if s > score:
            mejor, score = c['id'], s
    return mejor


def bloque_protocolo() -> str:
    """Lista para el protocolo del CLAUDE.md: las categorías que el agente
    puede poner en `categoria:`."""
    items = ' · '.join(f"`{c['id']}` ({c['nombre']})" for c in CATEGORIAS)
    return items
