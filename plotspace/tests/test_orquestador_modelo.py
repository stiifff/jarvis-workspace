"""
Test: modelo del orquestador configurable + pricing por modelo.

El modelo estaba hardcodeado en las DOS llamadas a la API y el pricing en un
par de constantes de haiku: al cambiar de modelo había que tocar tres lugares
y el costo quedaba mal en silencio. Ahora `ORQUESTADOR_MODEL` (env var,
default claude-haiku-4-5) es la fuente única y `_costo_usd` resuelve el
pricing según el modelo activo (fallback: pricing de haiku).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plotspace.routers.orchestrator import (
    ORQUESTADOR_MODEL,
    _costo_usd,
    _precios_de,
)


def test_default_segun_motor():
    # Sin env vars: motor suscripción (default) → sonnet (el costo por token
    # desapareció); con ORQUESTADOR_MOTOR=api el default vuelve a haiku.
    if not os.environ.get('ORQUESTADOR_MODEL') and not os.environ.get('ORQUESTADOR_MOTOR'):
        assert ORQUESTADOR_MODEL == 'sonnet'


def test_precios_por_modelo_conocido():
    assert _precios_de('claude-haiku-4-5') == (1.00, 5.00)
    assert _precios_de('claude-sonnet-5') == (3.00, 15.00)
    assert _precios_de('claude-opus-4-8') == (5.00, 25.00)


def test_precios_modelo_desconocido_cae_a_haiku():
    assert _precios_de('claude-inventado-9') == (1.00, 5.00)


def test_costo_usd_usa_el_modelo():
    # 1M input + 1M output en haiku = $6.00
    assert _costo_usd(1_000_000, 1_000_000, modelo='claude-haiku-4-5') == 6.00
    # y en sonnet-5 = $18.00
    assert _costo_usd(1_000_000, 1_000_000, modelo='claude-sonnet-5') == 18.00
    # sin modelo explícito usa ORQUESTADOR_MODEL (no crashea)
    assert _costo_usd(0, 0) == 0.0
