# plotspace/tests/test_swarm_grupos.py
"""Grupos del enjambre: qué terminales están trabajando sobre la MISMA superficie.

Es el cimiento del panel: el ícono de la card se prende cuando esta terminal
entra en un grupo, y el overlay muestra ese grupo. Si tres agentes convergen en
un archivo, el grupo es de TRES — no tres pares sueltos.

Dos criterios de diseño que salen de lo medido:
  · Compartir archivo NO es un conflicto (dos ediciones en zonas distintas
    conviven perfecto). El grupo es informativo; la ALERTA es otra cosa.
  · El id del grupo tiene que ser ESTABLE entre consultas, o la UI parpadea.
"""
from plotspace.core.swarm_grupos import (
    detectar_grupos, superficie_de, VENTANA_S,
)


def _ed(tid, nombre, path, ts, antes='', despues='', op='write'):
    return {'tid': tid, 'nombre': nombre, 'path': path, 'ts': ts, 'op': op,
            'antes': antes, 'despues': despues, 'pid': 7, 'sobrescritura': False}


AHORA = 10_000.0


# ─── Formación de grupos ──────────────────────────────────────────────────────

def test_dos_agentes_en_el_mismo_archivo_forman_grupo():
    g = detectar_grupos([_ed(1, 'A', 'builder.js', AHORA - 10),
                         _ed(2, 'B', 'builder.js', AHORA - 5)], AHORA)
    assert len(g) == 1
    assert {m['tid'] for m in g[0]['miembros']} == {1, 2}
    assert g[0]['archivos'] == ['builder.js']


def test_TRES_agentes_en_el_mismo_archivo_son_UN_grupo_de_tres():
    """Lo que pidió el usuario: si convergen tres, se ven los tres juntos."""
    g = detectar_grupos([_ed(1, 'A', 'x.js', AHORA - 30),
                         _ed(2, 'B', 'x.js', AHORA - 20),
                         _ed(3, 'C', 'x.js', AHORA - 10)], AHORA)
    assert len(g) == 1
    assert {m['tid'] for m in g[0]['miembros']} == {1, 2, 3}


def test_cadena_de_solapamiento_es_un_solo_grupo():
    """A y B comparten x.js; B y C comparten y.js → los tres están enredados."""
    g = detectar_grupos([_ed(1, 'A', 'x.js', AHORA - 30),
                         _ed(2, 'B', 'x.js', AHORA - 25),
                         _ed(2, 'B', 'y.js', AHORA - 20),
                         _ed(3, 'C', 'y.js', AHORA - 10)], AHORA)
    assert len(g) == 1
    assert {m['tid'] for m in g[0]['miembros']} == {1, 2, 3}


def test_agentes_en_archivos_distintos_no_forman_grupo():
    assert detectar_grupos([_ed(1, 'A', 'a.js', AHORA - 10),
                            _ed(2, 'B', 'b.js', AHORA - 10)], AHORA) == []


def test_un_agente_solo_no_es_grupo():
    assert detectar_grupos([_ed(1, 'A', 'a.js', AHORA - 10),
                            _ed(1, 'A', 'b.js', AHORA - 5)], AHORA) == []


def test_dos_grupos_separados_conviven():
    g = detectar_grupos([_ed(1, 'A', 'x.js', AHORA - 10), _ed(2, 'B', 'x.js', AHORA - 9),
                         _ed(3, 'C', 'y.js', AHORA - 8), _ed(4, 'D', 'y.js', AHORA - 7)],
                        AHORA)
    assert len(g) == 2
    assert {frozenset(m['tid'] for m in x['miembros']) for x in g} == {
        frozenset({1, 2}), frozenset({3, 4})}


# ─── Ventana de tiempo ────────────────────────────────────────────────────────

def test_lo_viejo_no_cuenta():
    """Alguien que tocó ese archivo hace dos horas no está 'trabajando con vos'."""
    assert detectar_grupos([_ed(1, 'A', 'x.js', AHORA - VENTANA_S - 100),
                            _ed(2, 'B', 'x.js', AHORA - 10)], AHORA) == []


def test_lecturas_no_forman_grupo():
    """Leer el mismo archivo no es trabajar juntos: solo las escrituras enredan."""
    assert detectar_grupos([_ed(1, 'A', 'x.js', AHORA - 10, op='read'),
                            _ed(2, 'B', 'x.js', AHORA - 5)], AHORA) == []


# ─── Superficie compartida por SÍMBOLO (archivos distintos) ──────────────────

def test_simbolo_compartido_en_archivos_DISTINTOS_forma_grupo():
    """El caso real: uno define el nodo, otro lo referencia desde otro archivo.
    Están trabajando juntos aunque no compartan una sola ruta."""
    g = detectar_grupos([
        _ed(1, 'A', 'index.html', AHORA - 20,
            despues='<div class="bw-cfg-uso-top">x</div>'),
        _ed(2, 'B', 'builder.js', AHORA - 10,
            despues="$('.bw-cfg-uso-top span').textContent = t")], AHORA)
    assert len(g) == 1
    assert 'bw-cfg-uso-top' in g[0]['simbolos']
    assert set(g[0]['archivos']) == set()      # no comparten ruta, comparten símbolo


def test_simbolo_trivial_no_enreda():
    """Un símbolo demasiado común no es evidencia de trabajar juntos."""
    g = detectar_grupos([_ed(1, 'A', 'a.js', AHORA - 20, despues='class="item"'),
                         _ed(2, 'B', 'b.js', AHORA - 10, despues='class="item"')], AHORA)
    assert g == []


# ─── Ruido: rutas de fuera del proyecto ───────────────────────────────────────

def test_scratchpad_de_cada_agente_no_forma_grupo():
    """Los temporales de cada agente viven fuera del proyecto y no son
    superficie compartida (detectado en producción: rutas /tmp/... colándose)."""
    assert detectar_grupos([
        _ed(1, 'A', '/tmp/claude-1000/x/scratchpad/a.sql', AHORA - 10),
        _ed(2, 'B', '/tmp/claude-1000/x/scratchpad/a.sql', AHORA - 5)], AHORA) == []


# ─── Estabilidad e info del grupo ─────────────────────────────────────────────

def test_id_del_grupo_es_estable():
    """Si el id cambiara entre consultas, la UI parpadearía y el overlay abierto
    perdería su grupo."""
    eds = [_ed(1, 'A', 'x.js', AHORA - 10), _ed(2, 'B', 'x.js', AHORA - 5)]
    assert detectar_grupos(eds, AHORA)[0]['id'] == detectar_grupos(eds, AHORA + 1)[0]['id']


def test_id_no_depende_del_orden_de_llegada():
    a = detectar_grupos([_ed(1, 'A', 'x.js', AHORA - 10), _ed(2, 'B', 'x.js', AHORA - 5)], AHORA)
    b = detectar_grupos([_ed(2, 'B', 'x.js', AHORA - 5), _ed(1, 'A', 'x.js', AHORA - 10)], AHORA)
    assert a[0]['id'] == b[0]['id']


def test_grupo_trae_cuando_arranco_y_la_ultima_actividad():
    g = detectar_grupos([_ed(1, 'A', 'x.js', AHORA - 100),
                         _ed(2, 'B', 'x.js', AHORA - 5)], AHORA)[0]
    assert g['desde_ts'] == AHORA - 100
    assert g['ultima_ts'] == AHORA - 5


def test_miembros_traen_nombre_para_la_UI():
    g = detectar_grupos([_ed(1, 'Claude Code #1', 'x.js', AHORA - 10),
                         _ed(2, 'Claude Code #2', 'x.js', AHORA - 5)], AHORA)[0]
    assert {m['nombre'] for m in g['miembros']} == {'Claude Code #1', 'Claude Code #2'}


def test_grupos_ordenados_por_actividad_reciente():
    g = detectar_grupos([_ed(1, 'A', 'x.js', AHORA - 500), _ed(2, 'B', 'x.js', AHORA - 400),
                         _ed(3, 'C', 'y.js', AHORA - 20), _ed(4, 'D', 'y.js', AHORA - 10)],
                        AHORA)
    assert g[0]['archivos'] == ['y.js']      # el más activo primero


# ─── superficie_de: qué toca un agente (para el overlay) ─────────────────────

def test_superficie_de_junta_archivos_y_simbolos():
    s = superficie_de([_ed(1, 'A', 'a.js', AHORA - 10, despues='function miFuncion(){}')])
    assert 'a.js' in s['archivos']
    assert 'miFuncion' in s['simbolos']


def test_superficie_vacia_no_rompe():
    assert superficie_de([]) == {'archivos': set(), 'simbolos': set()}


# ─── Detalle del grupo: lo que se ve al abrir el overlay ─────────────────────

from plotspace.core.swarm_grupos import linea_de_tiempo, resumen_por_miembro  # noqa: E402


def test_linea_de_tiempo_entrelaza_los_tres_flujos():
    """Ediciones, mensajes y colisiones en UN solo eje: es lo que deja ver el
    baile entre los agentes. El mensaje viene con timestamp ISO (así lo guarda
    la DB) y tiene que ordenarse contra los epoch de las ediciones."""
    from datetime import datetime
    t_msg = datetime.fromisoformat('2026-07-22T12:00:00').timestamp()
    ev = linea_de_tiempo(
        ediciones=[_ed(1, 'A', 'x.js', t_msg - 100,
                       despues='function unaFuncion(){}')],
        mensajes=[{'de': 'A', 'para': 'B', 'msg': 'toco la zona de arriba',
                   'timestamp': '2026-07-22T12:00:00'}],
        colisiones=[{'ts': t_msg + 100, 'tid': 2, 'nombre': 'B',
                     'simbolo': 'unaFuncion', 'path': 'y.js',
                     'contra_nombre': 'A', 'contra_path': 'x.js'}],
        miembros_tid={1, 2})
    assert [e['tipo'] for e in ev] == ['edicion', 'mensaje', 'colision']
    assert ev[0]['simbolos'] == ['unaFuncion']
    assert [e['ts'] for e in ev] == sorted(e['ts'] for e in ev)


def test_linea_de_tiempo_ignora_a_los_de_afuera():
    ev = linea_de_tiempo([_ed(9, 'Ajeno', 'x.js', 100)], [], [], miembros_tid={1, 2})
    assert ev == []


def test_linea_de_tiempo_ignora_lecturas():
    ev = linea_de_tiempo([_ed(1, 'A', 'x.js', 100, op='read')], [], [], {1})
    assert ev == []


def test_linea_de_tiempo_marca_la_sobrescritura():
    e = dict(_ed(1, 'A', 'x.js', 100), sobrescritura=True)
    assert linea_de_tiempo([e], [], [], {1})[0]['sobrescritura'] is True


def test_linea_de_tiempo_acotada():
    muchas = [_ed(1, 'A', f'{i}.js', 100 + i) for i in range(500)]
    ev = linea_de_tiempo(muchas, [], [], {1})
    assert len(ev) == 200
    assert ev[-1]['ts'] == 599          # se queda con lo MÁS RECIENTE


def test_timestamp_invalido_no_rompe():
    ev = linea_de_tiempo([], [{'de': 'A', 'para': 'B', 'msg': 'x',
                               'timestamp': 'no-es-fecha'}], [], {1})
    assert len(ev) == 1 and ev[0]['ts'] == 0.0


def test_resumen_por_miembro():
    r = resumen_por_miembro(
        [_ed(1, 'A', 'x.js', 100), _ed(1, 'A', 'x.js', 200), _ed(2, 'B', 'y.js', 150)],
        [{'tid': 1, 'nombre': 'A'}, {'tid': 2, 'nombre': 'B'}])
    assert r[0] == {'tid': 1, 'nombre': 'A', 'escrituras': 2,
                    'archivos': ['x.js'], 'ultima_ts': 200}
    assert r[1]['escrituras'] == 1


def test_resumen_no_lista_temporales_de_afuera():
    r = resumen_por_miembro([_ed(1, 'A', '/tmp/x/scratch.sql', 100)],
                            [{'tid': 1, 'nombre': 'A'}])
    assert r[0]['archivos'] == [] and r[0]['escrituras'] == 1


if __name__ == '__main__':
    import sys
    import pytest
    sys.exit(pytest.main([__file__, '-q']))
