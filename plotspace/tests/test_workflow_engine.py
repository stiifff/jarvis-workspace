"""
Test: motor de workflows — funciones puras de gating/terminación.

Eran puras y deterministas pero NINGÚN test las cubría (gap Critical de la
review). Acá se fija su contrato: qué pasos están listos para arrancar
(incluida la compuerta del reviewer y la resolución de dependencias) y cuándo
un workflow se considera terminado.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plotspace.routers.orchestrator import (
    _dep_indice,
    _pasos_listos_para_arrancar,
    _workflow_terminado,
    _progreso_workflow,
)


# ─── _dep_indice ─────────────────────────────────────────────────────────────

def test_dep_indice_parsea_paso_n():
    assert _dep_indice('paso_0') == 0
    assert _dep_indice('paso_2') == 2
    assert _dep_indice('paso_10') == 10


def test_dep_indice_null_o_no_parseable():
    assert _dep_indice(None) is None
    assert _dep_indice('') is None
    assert _dep_indice('ninguno') is None
    assert _dep_indice('paso_x') is None


# ─── _workflow_terminado ─────────────────────────────────────────────────────

def test_terminado_todos_done():
    assert _workflow_terminado([{'estado': 'done'}, {'estado': 'done'}])


def test_terminado_cuenta_blocked_y_error_como_terminales():
    assert _workflow_terminado([{'estado': 'done'}, {'estado': 'blocked'}, {'estado': 'error'}])


def test_no_terminado_si_hay_pending_o_running():
    assert not _workflow_terminado([{'estado': 'done'}, {'estado': 'pending'}])
    assert not _workflow_terminado([{'estado': 'running'}])


def test_terminado_lista_vacia():
    assert _workflow_terminado([])  # all() de vacío = True


# ─── _progreso_workflow ──────────────────────────────────────────────────────

def test_progreso_cuenta_done():
    assert _progreso_workflow([{'estado': 'done'}, {'estado': 'pending'}, {'estado': 'done'}]) == 2
    assert _progreso_workflow([{'estado': 'pending'}]) == 0


# ─── _pasos_listos_para_arrancar ─────────────────────────────────────────────

def test_listo_pending_sin_dependencia():
    pasos = [{'estado': 'pending', 'depende_de': None}]
    assert _pasos_listos_para_arrancar(pasos) == [0]


def test_no_listo_si_ya_running_o_done():
    pasos = [{'estado': 'running', 'depende_de': None},
             {'estado': 'done', 'depende_de': None}]
    assert _pasos_listos_para_arrancar(pasos) == []


def test_dependencia_resuelta_vs_pendiente():
    # paso 1 depende del índice 0
    pendiente = [{'estado': 'running', 'depende_de': None},
                 {'estado': 'pending', 'depende_de': 'paso_0'}]
    assert _pasos_listos_para_arrancar(pendiente) == []   # dep aún no done

    resuelta = [{'estado': 'done', 'depende_de': None},
                {'estado': 'pending', 'depende_de': 'paso_0'}]
    assert _pasos_listos_para_arrancar(resuelta) == [1]   # dep done → listo


def test_reviewer_espera_a_todos_los_demas():
    # El reviewer NO arranca mientras quede trabajo a medias
    a_medias = [{'estado': 'done'},
                {'estado': 'running'},
                {'estado': 'pending', 'rol': 'reviewer'}]
    assert 2 not in _pasos_listos_para_arrancar(a_medias)

    todo_listo = [{'estado': 'done'},
                  {'estado': 'done'},
                  {'estado': 'pending', 'rol': 'reviewer'}]
    assert _pasos_listos_para_arrancar(todo_listo) == [2]


def test_varios_listos_en_paralelo():
    pasos = [{'estado': 'pending', 'depende_de': None},
             {'estado': 'pending', 'depende_de': None}]
    assert _pasos_listos_para_arrancar(pasos) == [0, 1]


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
