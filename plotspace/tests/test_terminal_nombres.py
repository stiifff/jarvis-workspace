"""
Test: unicidad de nombres de terminal (plotspace/routers/terminals.py).

El nombre de la terminal es la IDENTIDAD de coordinación del agente: el
mailbox 1-a-1 resuelve destinatarios por nombre, y Agents Live registra
dueños y permisos por nombre. Dos terminales activas con el mismo nombre
(visto en producción 2026-06-10: "Claude Code #3" ×2 y "Claude Code #4" ×3
en el proyecto 17) vuelven ambigua TODA la coordinación.

Causa raíz del duplicado: la numeración por CONTEO de activas
(`numero = count_actual + i + 1` en orchestrator._spawn_terminales) reusa
números al borrar terminales; y los POST/PATCH de terminals.py aceptaban
cualquier nombre del cliente sin chequear.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plotspace.routers.terminals import resolver_nombre_unico


def test_nombre_libre_queda_igual():
    assert resolver_nombre_unico(['Backend', 'Frontend'], 'Docs') == 'Docs'
    assert resolver_nombre_unico([], 'Claude Code #1') == 'Claude Code #1'


def test_colision_simple_numera_desde_2():
    assert resolver_nombre_unico(['Backend'], 'Backend') == 'Backend #2'


def test_colision_numerada_sigue_del_maximo():
    activos = ['Claude Code #3', 'Claude Code #4']
    # pedir "#3" de nuevo NO reusa el hueco #1/#2: un número muerto puede
    # seguir citado en el MAILBOX — siempre máximo usado + 1.
    assert resolver_nombre_unico(activos, 'Claude Code #3') == 'Claude Code #5'


def test_colision_base_con_numerados_existentes():
    activos = ['Claude Code', 'Claude Code #7']
    assert resolver_nombre_unico(activos, 'Claude Code') == 'Claude Code #8'


def test_case_insensitive():
    # el mailbox matchea case-insensitive: "backend" y "Backend" son la
    # misma identidad → chocan.
    assert resolver_nombre_unico(['Backend'], 'backend') == 'backend #2'


def test_numerado_libre_queda_igual():
    assert resolver_nombre_unico(['Claude Code #3'], 'Claude Code #7') == 'Claude Code #7'


def test_lote_secuencial_no_se_pisa():
    # patrón de uso en los endpoints: la lista de activos crece con cada
    # creación del mismo lote.
    activos = ['Claude Code #1']
    creados = []
    for _ in range(3):
        nombre = resolver_nombre_unico(activos, 'Claude Code #1')
        creados.append(nombre)
        activos.append(nombre)
    assert creados == ['Claude Code #2', 'Claude Code #3', 'Claude Code #4']
    assert len(set(n.lower() for n in activos)) == len(activos)
