"""
Test: categorías canónicas de la memoria compartida.

La parte de datos de la idea de 'cuadros por tema': cada memoria pertenece a
UNA categoría (~10 fijas). El campo `categoria:` es explícito; si falta, se
auto-clasifica por tags/slug, y lo que no matchea queda 'sin-clasificar' (el
lint lo marca). El INDEX se agrupa por categoría y el recall gana una señal.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plotspace.core import memoria_categorias as cat


# ─── Taxonomía ───────────────────────────────────────────────────────────────

def test_categorias_canonicas_completas():
    ids = {c['id'] for c in cat.CATEGORIAS}
    for esperada in ('terminales', 'ui', 'swarm', 'diseno', 'preview',
                     'cuentas', 'voz', 'desktop', 'entorno', 'producto'):
        assert esperada in ids
    # nombre legible por id + orden estable
    assert cat.NOMBRE['terminales']
    assert cat.ORDEN[0] and len(cat.ORDEN) == len(cat.CATEGORIAS)


def test_es_categoria_valida():
    assert cat.es_valida('terminales')
    assert cat.es_valida('sin-clasificar')      # el fallback siempre vale
    assert not cat.es_valida('inventada')


# ─── Auto-clasificación (fallback determinista) ──────────────────────────────

def test_clasifica_por_tags():
    assert cat.clasificar(['terminales', 'tmux'], 'x') == 'terminales'
    assert cat.clasificar(['diseno', 'impeccable'], 'x') == 'diseno'
    assert cat.clasificar(['voz', 'stt'], 'x') == 'voz'


def test_clasifica_por_slug_cuando_no_hay_tags():
    assert cat.clasificar([], 'preview-pestanas') == 'preview'
    assert cat.clasificar([], 'cuentas-codex-oauth') == 'cuentas'


def test_sin_match_es_sin_clasificar():
    assert cat.clasificar(['banana'], 'algo-random-xyz') == 'sin-clasificar'


def test_gana_la_de_mas_coincidencias():
    # 'frontend' + 'css' + 'ui' pesan a ui aunque haya un tag suelto de otra
    assert cat.clasificar(['frontend', 'css', 'ui', 'tmux'], 'x') == 'ui'


if __name__ == '__main__':
    import traceback
    fallos = 0
    for nombre, fn in sorted(globals().items()):
        if nombre.startswith('test_') and callable(fn):
            try:
                fn(); print(f'ok  {nombre}')
            except Exception:
                fallos += 1; print(f'FAIL {nombre}'); traceback.print_exc()
    sys.exit(1 if fallos else 0)
