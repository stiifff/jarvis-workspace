# plotspace/tests/test_territorio.py
"""Territorio: que la colisión NO llegue a pasar, en vez de avisarla después.

EL PRINCIPIO
Un territorio se reclama por NOMBRE (un símbolo, un archivo, una carpeta),
nunca por número de línea. Las líneas se mueven: apenas alguien inserta diez
líneas arriba, el rango del otro quedó mal — y en este repo eso ya costó una
función borrada (un agente filtró sus cambios por «línea >= 4400» y se llevó
puesta una que vivía en la 5739).

LA TENSIÓN QUE RESUELVE ESTE DISEÑO
Auto-reclamar el ARCHIVO que tocás sería fatal: está medido que dos agentes
editando zonas distintas del mismo archivo conviven perfecto, así que bloquear
por archivo reintroduce el ruido que hizo que el 32% del tráfico entre agentes
fuera pedir permisos. Entonces:

  · lo que se auto-reclama al escribir son los SÍMBOLOS, no el archivo;
  · se BLOQUEA solo lo que destruye: borrar/renombrar un símbolo ajeno, o
    escribir dentro de una ruta que otro reclamó EXPLÍCITAMENTE;
  · referenciar un símbolo ajeno (llamar a su función) NO se bloquea — sería el
    falso positivo más molesto posible;
  · lo que nadie reclamó se concede solo, al instante, sin preguntar. Sin esa
    ampliación automática la prevención se vuelve una cárcel.
"""
import pytest

from plotspace.core import territorio


@pytest.fixture(autouse=True)
def limpio():
    territorio.reset()
    yield
    territorio.reset()


# ─── Reclamo explícito ────────────────────────────────────────────────────────

def test_reclamar_lo_libre_se_concede():
    r = territorio.reclamar(7, 1, 'A', ['aplicarIdioma', 'builder.js'])
    assert r['otorgados'] == ['aplicarIdioma', 'builder.js']
    assert r['ocupados'] == []


def test_reclamar_lo_ajeno_no_se_concede():
    territorio.reclamar(7, 1, 'A', ['aplicarIdioma'])
    r = territorio.reclamar(7, 2, 'B', ['aplicarIdioma', 'otraCosa'])
    assert r['otorgados'] == ['otraCosa']
    assert r['ocupados'] == [{'patron': 'aplicarIdioma', 'de': 'A'}]


def test_re_reclamar_lo_propio_renueva():
    territorio.reclamar(7, 1, 'A', ['x.js'], ts=1000)
    r = territorio.reclamar(7, 1, 'A', ['x.js'], ts=2000)
    assert r['otorgados'] == ['x.js']
    assert territorio.duenio(7, 'x.js', ahora=2001)['ts'] == 2000


def test_el_reclamo_vence():
    territorio.reclamar(7, 1, 'A', ['x.js'], ts=1000)
    assert territorio.duenio(7, 'x.js', ahora=1000 + territorio.TTL_S - 1) is not None
    assert territorio.duenio(7, 'x.js', ahora=1000 + territorio.TTL_S + 1) is None


def test_vencido_lo_puede_tomar_otro():
    territorio.reclamar(7, 1, 'A', ['x.js'], ts=1000)
    r = territorio.reclamar(7, 2, 'B', ['x.js'], ts=1000 + territorio.TTL_S + 1)
    assert r['otorgados'] == ['x.js']


def test_proyectos_distintos_no_comparten_territorio():
    territorio.reclamar(7, 1, 'A', ['x.js'])
    assert territorio.reclamar(8, 2, 'B', ['x.js'])['otorgados'] == ['x.js']


def test_reclamos_basura_no_rompen():
    r = territorio.reclamar(7, 1, 'A', ['', '   ', None, 'valido'])
    assert r['otorgados'] == ['valido']
    assert territorio.reclamar(7, 1, 'A', None)['otorgados'] == []


# ─── Chequeo previo: qué se BLOQUEA ───────────────────────────────────────────

def _chequear(tid, path, antes='', despues=''):
    return territorio.chequear(7, tid, path, antes, despues)


def test_borrar_un_simbolo_ajeno_se_BLOQUEA():
    """El caso real del Builder, ahora prevenido: el #3 va a borrar el nodo que
    el #2 reclamó. Antes se avisaba DESPUÉS de romperlo."""
    territorio.reclamar(7, 2, 'Claude Code #2', ['bw-cfg-uso-top'])
    r = _chequear(3, 'index.html',
                  antes='<div class="bw-cfg-uso-top">x</div>', despues='')
    assert r is not None
    assert 'bw-cfg-uso-top' in r['motivo']
    assert r['dueno'] == 'Claude Code #2'


def test_renombrar_un_simbolo_ajeno_se_BLOQUEA():
    territorio.reclamar(7, 2, 'B', ['aplicarIdioma'])
    r = _chequear(3, 'builder.js', antes='function aplicarIdioma() {}',
                  despues='function aplicarLenguaje() {}')
    assert r is not None and 'aplicarIdioma' in r['motivo']


def test_REFERENCIAR_un_simbolo_ajeno_NO_se_bloquea():
    """Llamar a la función del otro es trabajo normal. Bloquear esto sería el
    falso positivo más molesto posible."""
    territorio.reclamar(7, 2, 'B', ['aplicarIdioma'])
    assert _chequear(3, 'otro.js', antes='', despues='aplicarIdioma()') is None


def test_editar_OTRA_zona_del_mismo_archivo_NO_se_bloquea():
    """Lo medido: dos ediciones en zonas distintas del mismo archivo conviven
    perfecto. Bloquear acá es exactamente el ruido que se quiere evitar."""
    territorio.reclamar(7, 2, 'B', ['aplicarIdioma'])
    assert _chequear(3, 'builder.js', antes='const scrollbar = true;',
                     despues='const scrollbar = false;') is None


def test_escribir_dentro_de_una_RUTA_reclamada_se_BLOQUEA():
    """Reclamar una ruta es una declaración fuerte y deliberada: ahí sí manda."""
    territorio.reclamar(7, 2, 'B', ['plotspace/core/mailbox.py'])
    r = _chequear(3, 'plotspace/core/mailbox.py', antes='x', despues='y')
    assert r is not None and r['dueno'] == 'B'


def test_reclamar_una_CARPETA_cubre_lo_de_adentro():
    territorio.reclamar(7, 2, 'B', ['plotspace/core/'])
    assert _chequear(3, 'plotspace/core/x.py', antes='a', despues='b') is not None
    assert _chequear(3, 'plotspace/routers/x.py', antes='a', despues='b') is None


def test_mi_propio_territorio_no_me_bloquea():
    territorio.reclamar(7, 3, 'C', ['aplicarIdioma', 'builder.js'])
    assert _chequear(3, 'builder.js', antes='function aplicarIdioma(){}',
                     despues='') is None


def test_un_reclamo_vencido_no_bloquea_a_nadie():
    territorio.reclamar(7, 2, 'B', ['x.js'], ts=1000)
    assert territorio.chequear(7, 3, 'x.js', 'a', 'b',
                               ahora=1000 + territorio.TTL_S + 1) is None


def test_sin_reclamos_no_se_bloquea_nada():
    assert _chequear(3, 'cualquier.js', antes='function loQueSea(){}', despues='') is None


# ─── Ampliación automática: lo libre se concede solo ─────────────────────────

def test_al_escribir_se_auto_reclaman_los_simbolos_DECLARADOS():
    territorio.registrar_escritura(7, 1, 'A', 'builder.js',
                                   despues='function nuevaCosa() {}')
    d = territorio.duenio(7, 'nuevaCosa')
    assert d is not None and d['tid'] == 1


def test_el_auto_reclamo_NO_toma_el_archivo_entero():
    """Si auto-reclamara el archivo, el segundo agente que toque otra zona
    quedaría bloqueado — justo lo que se demostró que NO hace falta."""
    territorio.registrar_escritura(7, 1, 'A', 'builder.js',
                                   despues='function unaCosa() {}')
    assert territorio.duenio(7, 'builder.js') is None
    assert territorio.chequear(7, 2, 'builder.js', 'otra zona', 'x') is None


def test_lo_auto_reclamado_por_otro_SI_protege():
    territorio.registrar_escritura(7, 1, 'A', 'builder.js',
                                   despues='function miFuncion() {}')
    r = territorio.chequear(7, 2, 'builder.js',
                            antes='function miFuncion() {}', despues='')
    assert r is not None and r['dueno'] == 'A'


def test_el_auto_reclamo_no_le_roba_a_un_dueño_explicito():
    territorio.reclamar(7, 1, 'A', ['comun'])
    territorio.registrar_escritura(7, 2, 'B', 'x.js', despues='class comun {}')
    assert territorio.duenio(7, 'comun')['tid'] == 1, 'el dueño original se conserva'


def test_registrar_escritura_sin_simbolos_no_rompe():
    territorio.registrar_escritura(7, 1, 'A', 'x.txt', despues='texto suelto')
    assert territorio.reclamos(7) == [] or all(
        r['tid'] == 1 for r in territorio.reclamos(7))


# ─── Vista del territorio (la consume el panel y `jv estado`) ────────────────

def test_reclamos_lista_lo_vigente_con_su_dueño():
    territorio.reclamar(7, 1, 'A', ['x.js'])
    territorio.reclamar(7, 2, 'B', ['y.js'])
    r = territorio.reclamos(7)
    assert {(x['patron'], x['nombre']) for x in r} == {('x.js', 'A'), ('y.js', 'B')}


def test_reclamos_no_lista_lo_vencido():
    territorio.reclamar(7, 1, 'A', ['x.js'], ts=1000)
    assert territorio.reclamos(7, ahora=1000 + territorio.TTL_S + 1) == []


def test_soltar_libera_el_territorio():
    territorio.reclamar(7, 1, 'A', ['x.js'])
    territorio.soltar(7, 1, ['x.js'])
    assert territorio.duenio(7, 'x.js') is None


def test_soltar_no_toca_lo_ajeno():
    territorio.reclamar(7, 1, 'A', ['x.js'])
    territorio.soltar(7, 2, ['x.js'])
    assert territorio.duenio(7, 'x.js') is not None


def test_purgar_terminal_libera_todo_lo_suyo():
    territorio.reclamar(7, 1, 'A', ['x.js', 'y.js'])
    territorio.purgar_terminal(1)
    assert territorio.reclamos(7) == []


# ─── Snapshot: sobrevivir al re-exec del updater (2c) ─────────────────────────
# _reclamos vive en memoria y muere en cada 'Actualizar ahora' (os.execv). Sin
# snapshot, cada update borra el territorio de TODOS hasta que reescriban, y el
# guard de commits queda un rato sin dueños que defender.

def test_snapshot_ida_y_vuelta(tmp_path):
    territorio.reset()
    ruta = str(tmp_path / 'terr.json')
    territorio.reclamar(7, 1, 'Backend', ['aplicarIdioma', 'plotspace/core/'])
    assert territorio.guardar_snapshot(ruta) == 2
    territorio.reset()
    assert territorio.reclamos(7) == []             # se perdió (simula el re-exec)
    assert territorio.cargar_snapshot(ruta) == 2
    d = territorio.duenio(7, 'aplicarIdioma')
    assert d and d['tid'] == 1 and d['nombre'] == 'Backend'


def test_snapshot_no_guarda_vacio_para_no_pisar_uno_bueno(tmp_path):
    """Guardar NADA no puede borrar un snapshot bueno (el mismo error que una vez
    borró el Builder: un estado vacío tratado como válido)."""
    territorio.reset()
    ruta = str(tmp_path / 'terr.json')
    territorio.reclamar(7, 1, 'A', ['x.js'])
    territorio.guardar_snapshot(ruta)
    territorio.reset()
    assert territorio.guardar_snapshot(ruta) == 0    # vacío: no escribe
    assert territorio.cargar_snapshot(ruta) == 1     # el bueno sigue en disco


def test_snapshot_no_resucita_lo_vencido(tmp_path):
    import time
    territorio.reset()
    ruta = str(tmp_path / 'terr.json')
    territorio.reclamar(7, 1, 'A', ['x.js'], ts=time.time() - territorio.TTL_S - 10)
    assert territorio.guardar_snapshot(ruta) == 0    # un reclamo vencido no se guarda


def test_cargar_no_duplica_si_hay_estado_vivo(tmp_path):
    territorio.reset()
    ruta = str(tmp_path / 'terr.json')
    territorio.reclamar(7, 1, 'A', ['x.js'])
    territorio.guardar_snapshot(ruta)
    assert territorio.cargar_snapshot(ruta) == 0     # ya hay estado vivo: no pisa


def test_cargar_sin_archivo_es_0():
    territorio.reset()
    assert territorio.cargar_snapshot('/no/existe/terr.json') == 0


if __name__ == '__main__':
    import sys
    sys.exit(pytest.main([__file__, '-q']))
