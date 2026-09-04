# plotspace/tests/test_agent_live_ingesta.py
"""Ingesta de operaciones REALES en Agents Live (vía hook, no vía pane).

El parser de panes murió cuando el CLI pasó a resúmenes colapsados. Esta es la
vía de reemplazo: `aplicar_op` recibe la operación con el dato exacto de la
herramienta y mantiene el MISMO estado que mantenía el poller (archivos +
dueños), así que todo lo que cuelga de ahí (LIVE.md, guard de commits,
conflictos) revive sin cambiar de formato.

Pura: sin DB, sin tmux, sin red.
"""
from plotspace.core.agent_live import aplicar_op, dueno_vigente, PROPIEDAD_TTL_S


def _estado():
    return {}, {}


def test_write_crea_propiedad():
    archivos, duenos = _estado()
    path, res, dueno = aplicar_op(archivos, duenos, 7, 397, 'Claude Code #2',
                                  '/home/user/jarvis', 'write',
                                  'plotspace/core/x.py', ahora=1000.0)
    assert path == 'plotspace/core/x.py'
    assert res == 'nueva'
    assert dueno['tid'] == 397
    assert archivos[397]['plotspace/core/x.py']['writes'] == 1


def test_path_absoluto_se_normaliza_al_proyecto():
    """Una CLI puede reportar el path absoluto y otra el relativo: sin
    normalizar serían DOS dueños del mismo archivo y el conflicto no se vería."""
    archivos, duenos = _estado()
    path, _, _ = aplicar_op(archivos, duenos, 7, 397, 'A', '/home/user/jarvis',
                            'write', '/home/user/jarvis/plotspace/main.py', ahora=1.0)
    assert path == 'plotspace/main.py'


def test_segundo_agente_sobre_archivo_ajeno_es_conflicto():
    archivos, duenos = _estado()
    aplicar_op(archivos, duenos, 7, 397, 'A', '/p', 'write', 'a.js', ahora=1000.0)
    path, res, dueno = aplicar_op(archivos, duenos, 7, 396, 'B', '/p', 'write',
                                  'a.js', ahora=1001.0)
    assert res == 'conflicto'
    assert dueno['nombre'] == 'A'          # el dueño devuelto es el ORIGINAL


def test_mismo_agente_renueva_su_propiedad():
    archivos, duenos = _estado()
    aplicar_op(archivos, duenos, 7, 397, 'A', '/p', 'write', 'a.js', ahora=1000.0)
    _, res, dueno = aplicar_op(archivos, duenos, 7, 397, 'A', '/p', 'write',
                               'a.js', ahora=1500.0)
    assert res == 'propia'
    assert dueno['ultima'] == 1500.0


def test_propiedad_expira_y_el_otro_la_toma():
    archivos, duenos = _estado()
    aplicar_op(archivos, duenos, 7, 397, 'A', '/p', 'write', 'a.js', ahora=1000.0)
    _, res, dueno = aplicar_op(archivos, duenos, 7, 396, 'B', '/p', 'write',
                               'a.js', ahora=1000.0 + PROPIEDAD_TTL_S + 1)
    assert res == 'nueva'
    assert dueno['tid'] == 396


def test_read_no_crea_propiedad():
    archivos, duenos = _estado()
    path, res, dueno = aplicar_op(archivos, duenos, 7, 397, 'A', '/p', 'read',
                                  'a.js', ahora=1000.0)
    assert res == 'read'
    assert dueno is None
    assert duenos == {}
    assert archivos[397]['a.js']['reads'] == 1
    assert archivos[397]['a.js']['writes'] == 0


def test_dos_agentes_distintos_archivos_no_chocan():
    archivos, duenos = _estado()
    _, r1, _ = aplicar_op(archivos, duenos, 7, 397, 'A', '/p', 'write', 'a.js', ahora=1.0)
    _, r2, _ = aplicar_op(archivos, duenos, 7, 396, 'B', '/p', 'write', 'b.js', ahora=2.0)
    assert (r1, r2) == ('nueva', 'nueva')
    assert dueno_vigente(duenos[(7, 'a.js')], 3.0)
    assert dueno_vigente(duenos[(7, 'b.js')], 3.0)


def test_path_vacio_se_ignora():
    archivos, duenos = _estado()
    assert aplicar_op(archivos, duenos, 7, 397, 'A', '/p', 'write', '', ahora=1.0) == (
        '', None, None)
    assert archivos == {} and duenos == {}


def test_proyectos_distintos_no_comparten_propiedad():
    """La clave de propiedad es (project_id, path): el mismo nombre de archivo
    en dos proyectos son dos dueños distintos."""
    archivos, duenos = _estado()
    aplicar_op(archivos, duenos, 7, 397, 'A', '/p1', 'write', 'a.js', ahora=1.0)
    _, res, _ = aplicar_op(archivos, duenos, 8, 396, 'B', '/p2', 'write', 'a.js', ahora=2.0)
    assert res == 'nueva'


if __name__ == '__main__':
    import sys
    import pytest
    sys.exit(pytest.main([__file__, '-q']))
