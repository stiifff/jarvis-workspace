"""
Test: motor del orquestador — suscripción por default, API como vía de escape.

`ORQUESTADOR_MOTOR` decide el transport: 'suscripcion' (default — claude -p
headless con la cuenta OAuth activa, cero tokens de API pagos) o 'api' (el
camino viejo con ANTHROPIC_API_KEY, vía de escape). El system prompt en modo
CLI reemplaza la mecánica de la tool `responder` por salida JSON directa y
suma las instrucciones de exploración de solo lectura.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plotspace.routers.orchestrator import (
    ORQUESTADOR_MOTOR,
    SYSTEM_PROMPT,
    _modelo_default,
    _system_prompt_cli,
)


def test_motor_default_es_suscripcion():
    if not os.environ.get('ORQUESTADOR_MOTOR'):
        assert ORQUESTADOR_MOTOR == 'suscripcion'


def test_modelo_default_por_motor():
    # En suscripción el costo por token desaparece → sonnet de fábrica.
    assert _modelo_default('suscripcion') == 'sonnet'
    # La vía de escape API mantiene el haiku barato de siempre.
    assert _modelo_default('api') == 'claude-haiku-4-5'


def test_prompt_cli_sin_tool_responder():
    s = _system_prompt_cli()
    assert 'tool `responder`' not in s
    assert 'JSON' in s
    # el resto del prompt (mapa, enviar_prompt, tope real) sigue intacto
    assert '[Mapa del proyecto]' in s
    assert 'enviar_prompt' in s
    assert '__MAX_TERMINALES__' not in s


def test_prompt_cli_instruye_exploracion_solo_lectura():
    s = _system_prompt_cli()
    assert 'OJOS PROPIOS' in s
    assert 'Read' in s and 'Grep' in s
    # y el prompt base (modo API) NO la trae
    assert 'OJOS PROPIOS' not in SYSTEM_PROMPT
