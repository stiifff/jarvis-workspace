"""
Test: repo_map — el orquestador ve la forma del proyecto (Etapa 2 del rework).

Antes el orquestador planificaba CIEGO: inventaba el campo `archivos` de cada
paso sin haber visto jamás el árbol del proyecto. `repo_map.generar_mapa`
produce un mapa determinista (dirs anotados con conteos por extensión, stack
detectado por marcadores, propósito desde AGENTS.md) que se inyecta al
contexto del chat. Cero API, cacheado por TTL.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plotspace.core import repo_map


def _proyecto_de_prueba():
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, 'plotspace', 'routers'))
    os.makedirs(os.path.join(d, 'plotspace', 'core'))
    os.makedirs(os.path.join(d, 'frontend', 'sections', 'chat'))
    os.makedirs(os.path.join(d, 'node_modules', 'lodash'))
    os.makedirs(os.path.join(d, '.git', 'objects'))
    open(os.path.join(d, 'requirements.txt'), 'w').close()
    for n in ('main.py', 'auth.py'):
        open(os.path.join(d, 'plotspace', n), 'w').close()
    for n in ('users.py', 'items.py', 'health.py'):
        open(os.path.join(d, 'plotspace', 'routers', n), 'w').close()
    open(os.path.join(d, 'plotspace', 'core', 'db.py'), 'w').close()
    open(os.path.join(d, 'frontend', 'index.html'), 'w').close()
    open(os.path.join(d, 'frontend', 'sections', 'chat', 'chat.js'), 'w').close()
    open(os.path.join(d, 'frontend', 'sections', 'chat', 'chat.css'), 'w').close()
    return d


# ─── Árbol + conteos ─────────────────────────────────────────────────────────

def test_arbol_con_conteos_por_extension():
    d = _proyecto_de_prueba()
    mapa = repo_map.generar_mapa(d)
    assert 'plotspace/' in mapa
    assert 'routers/' in mapa and '3 .py' in mapa
    assert 'frontend/' in mapa
    # el conteo de un dir es NO recursivo (plotspace/ tiene 2 .py propios)
    linea_backend = next(l for l in mapa.splitlines() if l.strip().startswith('plotspace/'))
    assert '2 .py' in linea_backend


def test_poda_ruido():
    d = _proyecto_de_prueba()
    mapa = repo_map.generar_mapa(d)
    assert 'node_modules' not in mapa
    assert '.git' not in mapa


def test_stack_detectado():
    d = _proyecto_de_prueba()
    mapa = repo_map.generar_mapa(d)
    assert 'Python' in mapa
    open(os.path.join(d, 'package.json'), 'w').close()
    assert 'Node' in repo_map.generar_mapa(d)


def test_max_niveles():
    d = _proyecto_de_prueba()
    mapa = repo_map.generar_mapa(d, max_niveles=1)
    assert 'plotspace/' in mapa
    assert 'routers/' not in mapa          # nivel 2 afuera


def test_tope_de_lineas_sin_truncado_silencioso():
    d = tempfile.mkdtemp()
    for i in range(40):
        os.makedirs(os.path.join(d, f'modulo_{i:02d}'))
    mapa = repo_map.generar_mapa(d, max_lineas=10)
    assert len(mapa.splitlines()) <= 11    # 10 + el marcador
    assert 'más' in mapa                   # "… (+N carpetas más)" — nunca truncar en silencio


def test_ruta_inexistente_devuelve_vacio():
    assert repo_map.generar_mapa('/no/existe/jamas') == ''
    assert repo_map.bloque_mapa('/no/existe/jamas') == ''


# ─── Propósito desde AGENTS.md ───────────────────────────────────────────────

def test_proposito_desde_agents_md():
    d = _proyecto_de_prueba()
    with open(os.path.join(d, 'plotspace', 'AGENTS.md'), 'w') as f:
        f.write('# plotspace/ — FastAPI + core del swarm\n\nblah blah\n')
    mapa = repo_map.generar_mapa(d)
    assert 'FastAPI + core del swarm' in mapa


# ─── Cache por TTL ───────────────────────────────────────────────────────────

def test_cache_respeta_ttl():
    d = _proyecto_de_prueba()
    m1 = repo_map.bloque_mapa(d, ahora=1000.0)
    # cambia el árbol: dentro del TTL sigue sirviendo el snapshot viejo
    os.makedirs(os.path.join(d, 'carpeta_nueva'))
    m2 = repo_map.bloque_mapa(d, ahora=1030.0)
    assert m2 == m1
    assert 'carpeta_nueva' not in m2
    # vencido el TTL, re-escanea
    m3 = repo_map.bloque_mapa(d, ahora=1000.0 + repo_map.TTL_S + 1)
    assert 'carpeta_nueva' in m3
