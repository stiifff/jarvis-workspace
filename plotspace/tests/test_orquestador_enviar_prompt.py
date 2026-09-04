"""
Test: enviar_prompt + reuso de terminales + estado vivo (Etapa 3 del rework).

El agujero que cierra: el orquestador VEÍA las terminales abiertas pero no
tenía manos — ninguna action permitía mandarle un prompt a una existente, y
los workflows spawneaban SIEMPRE terminales nuevas (la instrucción "reusá
terminales" del prompt era letra muerta). Acá se fija el contrato de:
  - la action `enviar_prompt` en el tool schema + su guarda pura
  - `_terminal_reusable` (pasos de workflow con terminal_id opcional)
  - `_formatear_estado_core` (estado vivo de agent_watch + dueños de agent_live)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plotspace.routers.orchestrator import (
    RESPONDER_TOOL,
    _formatear_estado_core,
    _terminal_reusable,
    _validar_enviar_prompt,
)


# ─── Contrato del tool schema ────────────────────────────────────────────────

def _props_action():
    return RESPONDER_TOOL['input_schema']['properties']['actions']['items']['properties']


def test_schema_incluye_enviar_prompt():
    assert 'enviar_prompt' in _props_action()['type']['enum']
    assert 'prompt' in _props_action()


def test_schema_paso_acepta_terminal_id():
    paso = (RESPONDER_TOOL['input_schema']['properties']['workflow']
            ['properties']['pasos']['items']['properties'])
    assert 'terminal_id' in paso


# ─── Guarda de enviar_prompt ─────────────────────────────────────────────────

ACTIVAS = {10, 11, 12}


def test_envio_valido():
    tid, motivo = _validar_enviar_prompt(
        {'type': 'enviar_prompt', 'terminal_id': 11, 'prompt': 'mejorá el diseño'},
        ACTIVAS, ocupadas=set())
    assert tid == 11 and motivo is None


def test_envio_terminal_id_como_string_numerico():
    tid, motivo = _validar_enviar_prompt(
        {'terminal_id': '12', 'prompt': 'x'}, ACTIVAS, set())
    assert tid == 12 and motivo is None


def test_envio_sin_terminal_id():
    tid, motivo = _validar_enviar_prompt({'prompt': 'x'}, ACTIVAS, set())
    assert tid is None and motivo


def test_envio_sin_prompt():
    tid, motivo = _validar_enviar_prompt({'terminal_id': 11}, ACTIVAS, set())
    assert tid is None and 'prompt' in motivo


def test_envio_a_terminal_inexistente():
    tid, motivo = _validar_enviar_prompt(
        {'terminal_id': 99, 'prompt': 'x'}, ACTIVAS, set())
    assert tid is None and '99' in motivo


def test_envio_a_terminal_ocupada_en_workflow():
    tid, motivo = _validar_enviar_prompt(
        {'terminal_id': 11, 'prompt': 'x'}, ACTIVAS, ocupadas={11})
    assert tid is None and 'ocupada' in motivo


# ─── Reuso de terminales en pasos de workflow ────────────────────────────────

def test_reusable_libre():
    assert _terminal_reusable(11, ACTIVAS, ocupadas=set(), reclamadas=set())


def test_no_reusable():
    assert not _terminal_reusable(None, ACTIVAS, set(), set())
    assert not _terminal_reusable(99, ACTIVAS, set(), set())          # no activa
    assert not _terminal_reusable(11, ACTIVAS, {11}, set())           # ocupada
    assert not _terminal_reusable(11, ACTIVAS, set(), {11})           # ya reclamada por otro paso
    assert not _terminal_reusable('11', ACTIVAS, set(), set())        # tipo raro: spawn normal


# ─── Estado enriquecido (núcleo puro) ────────────────────────────────────────

def _terminales():
    return [
        {'id': 10, 'nombre': 'Backend', 'tipo_ia': 'claude'},
        {'id': 11, 'nombre': 'Claude Code #2', 'tipo_ia': 'claude'},
    ]


def test_estado_muestra_fase_viva():
    txt = _formatear_estado_core(_terminales(), {}, fases={10: 'trabajando', 11: 'idle'})
    linea10 = next(l for l in txt.splitlines() if 'ID 10' in l)
    linea11 = next(l for l in txt.splitlines() if 'ID 11' in l)
    assert 'trabajando' in linea10
    assert 'quieta' in linea11


def test_estado_muestra_rol_de_workflow_y_libre():
    mapa = {10: {'workflow': 'Notas', 'agente': 'Backend', 'estado': 'running'}}
    txt = _formatear_estado_core(_terminales(), mapa)
    assert "rol 'Backend' del workflow 'Notas' (running)" in txt
    assert 'libre' in next(l for l in txt.splitlines() if 'ID 11' in l)


def test_estado_muestra_duenos_con_tope():
    duenos = {10: ['a.py', 'b.py', 'c.py', 'd.py', 'e.py']}
    txt = _formatear_estado_core(_terminales(), {}, duenos=duenos)
    linea10 = next(l for l in txt.splitlines() if 'ID 10' in l)
    assert 'dueña de: a.py, b.py, c.py (+2 más)' in linea10
    assert 'dueña' not in next(l for l in txt.splitlines() if 'ID 11' in l)


def test_estado_sin_terminales():
    assert _formatear_estado_core([], {}) == 'No hay terminales activas.'
