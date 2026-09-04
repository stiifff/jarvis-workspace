"""
Test: higiene del system prompt del orquestador (Etapa 6 del rework).

El prompt le MENTÍA al modelo sobre el sistema real: decía que el orquestador
commitea (falso: commitean los agentes/Reviewer), que el tope es 7 terminales
(es MAX_TERMINALES=12), ofrecía solo 4 CLIs (el producto corre 7+manual) y
obligaba a repetir el protocolo de cierre en cada tarea (duplicado con el
sentinel del engine). Estos tests fijan que el drift no vuelva.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plotspace.routers.orchestrator import (
    MAX_TERMINALES,
    SYSTEM_PROMPT,
    _tarea_engine_para_terminal,
)


# ─── El prompt dice la verdad sobre el sistema ───────────────────────────────

def test_tope_de_terminales_es_el_real():
    assert str(MAX_TERMINALES) in SYSTEM_PROMPT
    assert 'Máximo 7 terminales' not in SYSTEM_PROMPT


def test_no_dice_que_el_orquestador_commitea():
    # El engine NO commitea: commitean los agentes y el Reviewer.
    assert 'vos commiteás' not in SYSTEM_PROMPT
    assert 'commitean' in SYSTEM_PROMPT


def test_clis_completos():
    for cli in ('opencode', 'qwen', 'antigravity'):
        assert cli in SYSTEM_PROMPT, f'falta {cli} en el prompt'


# ─── Nuevas capacidades documentadas ─────────────────────────────────────────

def test_documenta_enviar_prompt_y_reuso():
    assert 'enviar_prompt' in SYSTEM_PROMPT
    assert 'terminal_id' in SYSTEM_PROMPT


def test_documenta_mapa_del_proyecto():
    assert '[Mapa del proyecto]' in SYSTEM_PROMPT


# ─── El cierre es del ENGINE, no del LLM (fuente única) ──────────────────────

def test_prompt_no_exige_cierre_literal():
    assert 'CIERRE LITERAL' not in SYSTEM_PROMPT


def test_engine_agrega_protocolo_de_cierre():
    tarea = _tarea_engine_para_terminal({'tarea': 'hacer X', 'archivos': []}, 42)
    assert 'TASK_DONE' in tarea
    assert 'TASK_BLOCKED' in tarea
    assert '.jarvis/signals/terminal_42.json' in tarea


def test_engine_no_duplica_cierre_si_la_tarea_ya_lo_trae():
    tarea = _tarea_engine_para_terminal(
        {'tarea': 'revisá todo. VEREDICTO: escribí TASK_DONE o TASK_BLOCKED.',
         'archivos': [], 'rol': 'reviewer'}, 42)
    assert tarea.count('PROTOCOLO DE CIERRE') == 0
    # el sentinel-file va igual (es otra capa, no el protocolo del pane)
    assert '.jarvis/signals/terminal_42.json' in tarea


# ─── Los ejemplos no sesgan con la estructura de Jarvis ──────────────────────

def test_ejemplos_sin_estructura_de_jarvis():
    assert 'frontend/sections/' not in SYSTEM_PROMPT
