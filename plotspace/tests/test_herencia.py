# plotspace/tests/test_herencia.py
"""Herencia: el trabajo sin commitear del agente que ya no está.

EL CASO REAL (24% del mailbox de este repo)
-------------------------------------------
Un agente edita `builder.js`, deja su parte sin commitear y su terminal se
cierra. Lo que pasaba después:

  · `_purgar_terminales` BORRABA su provenance → nadie sabía ya que esos hunks
    eran suyos;
  · `/swarm/fragmentos` dejaba de reportarlos como ajenos → `commit_propio`
    pasaba el archivo de modo 'hunk' a modo 'archivo completo';
  · y el próximo agente que commiteaba se llevaba el trabajo del muerto adentro
    de SU commit, con SU trailer `Jarvis-Agent`.

De ahí sale el "tal agente tiene commits que no hizo". La pieza que faltaba no
era un mensaje mejor: era que el trabajo huérfano estuviera DECLARADO.

REGLAS
------
  · Solo cuenta lo SUCIO: lo que ya está en HEAD no es herencia de nadie.
  · El dueño es el ÚLTIMO que escribió el archivo. Si después de que el muerto
    lo tocó vino un vivo, es del vivo — no hay herencia.
  · Sin provenance del archivo NO se adivina dueño: un huérfano mal atribuido es
    peor que uno sin atribuir.
"""
from plotspace.core import herencia


def _ed(tid, path, ts, nombre=None):
    return {'tid': tid, 'nombre': nombre or f'Agente #{tid}', 'path': path,
            'op': 'write', 'ts': ts}


# ─── Lo que SÍ es herencia ────────────────────────────────────────────────────

def test_archivo_sucio_de_un_muerto_es_herencia():
    r = herencia.calcular({'a.py'}, [_ed(1, 'a.py', 10)], vivos={2})
    assert r == [{'tid': 1, 'nombre': 'Agente #1', 'archivos': ['a.py']}]


def test_agrupa_todos_los_archivos_de_un_mismo_muerto():
    eds = [_ed(1, 'a.py', 10), _ed(1, 'b.py', 11)]
    r = herencia.calcular({'a.py', 'b.py'}, eds, vivos=set())
    assert r[0]['archivos'] == ['a.py', 'b.py']


def test_varios_muertos_salen_ordenados_y_separados():
    eds = [_ed(1, 'a.py', 10), _ed(2, 'b.py', 11)]
    r = herencia.calcular({'a.py', 'b.py'}, eds, vivos=set())
    assert [h['tid'] for h in r] == [1, 2]


# ─── Lo que NO es herencia ────────────────────────────────────────────────────

def test_lo_ya_commiteado_no_es_herencia():
    """El archivo no está sucio: su trabajo ya está en HEAD, no hay nada huérfano."""
    assert herencia.calcular(set(), [_ed(1, 'a.py', 10)], vivos=set()) == []


def test_lo_de_un_agente_vivo_no_es_herencia():
    assert herencia.calcular({'a.py'}, [_ed(1, 'a.py', 10)], vivos={1}) == []


def test_si_un_vivo_escribio_despues_el_archivo_es_del_vivo():
    """La herencia es del ÚLTIMO escritor: si el vivo pasó por encima, es suyo."""
    eds = [_ed(1, 'a.py', 10), _ed(2, 'a.py', 20)]
    assert herencia.calcular({'a.py'}, eds, vivos={2}) == []


def test_si_el_muerto_escribio_ultimo_sigue_siendo_herencia_suya():
    eds = [_ed(2, 'a.py', 10), _ed(1, 'a.py', 20)]
    r = herencia.calcular({'a.py'}, eds, vivos={2})
    assert [h['tid'] for h in r] == [1]


def test_los_artefactos_de_un_muerto_no_son_herencia_de_nadie():
    """Mandar a alguien a commitear un .exe de build o una captura de QA es peor
    que no decirle nada: es basura que además rompe el paracaídas del WIP."""
    eds = [_ed(1, 'desktop/dist/app.exe', 10), _ed(1, '.jarvis/qa-shots/x.png', 11)]
    sucios = {'desktop/dist/app.exe', '.jarvis/qa-shots/x.png'}
    assert herencia.calcular(sucios, eds, vivos=set()) == []


def test_un_mockup_abandonado_no_se_reclama():
    eds = [_ed(1, 'frontend/preview-cosa/index.html', 10)]
    assert herencia.calcular({'frontend/preview-cosa/index.html'}, eds,
                             vivos=set()) == []


def test_el_codigo_real_del_muerto_si_se_reclama_aunque_haya_artefactos():
    eds = [_ed(1, 'desktop/dist/app.exe', 10), _ed(1, 'plotspace/core/x.py', 11)]
    r = herencia.calcular({'desktop/dist/app.exe', 'plotspace/core/x.py'}, eds,
                          vivos=set())
    assert r == [{'tid': 1, 'nombre': 'Agente #1', 'archivos': ['plotspace/core/x.py']}]


def test_archivo_sucio_sin_provenance_no_se_atribuye_a_nadie():
    """No adivinar: un huérfano mal atribuido es peor que uno sin atribuir."""
    assert herencia.calcular({'misterio.py'}, [], vivos=set()) == []


def test_las_lecturas_no_generan_propiedad():
    eds = [{'tid': 1, 'nombre': 'A', 'path': 'a.py', 'op': 'read', 'ts': 10}]
    assert herencia.calcular({'a.py'}, eds, vivos=set()) == []


# ─── Robustez ─────────────────────────────────────────────────────────────────

def test_entradas_raras_no_explotan():
    for eds in (None, [None], [{}], [{'tid': None, 'path': 'a.py'}]):
        assert isinstance(herencia.calcular({'a.py'}, eds, vivos=set()), list)
    assert herencia.calcular(None, None, vivos=None) == []


def test_el_nombre_cae_al_tid_si_falta():
    eds = [{'tid': 7, 'path': 'a.py', 'op': 'write', 'ts': 1}]
    r = herencia.calcular({'a.py'}, eds, vivos=set())
    assert '7' in r[0]['nombre']


# ─── Lectura del árbol sucio ──────────────────────────────────────────────────

def test_parsea_el_porcelain_de_git():
    porcelain = ' M plotspace/x.py\n?? nuevo.txt\nA  staged.py\n'
    assert herencia.parsear_sucios(porcelain) == {
        'plotspace/x.py', 'nuevo.txt', 'staged.py'}


def test_el_porcelain_con_renombre_toma_el_destino():
    assert herencia.parsear_sucios('R  viejo.py -> nuevo.py\n') == {'nuevo.py'}


def test_el_porcelain_con_comillas_se_limpia():
    assert herencia.parsear_sucios(' M "con espacio.py"\n') == {'con espacio.py'}


def test_porcelain_vacio_o_basura():
    for basura in ('', None, 'x'):
        assert herencia.parsear_sucios(basura) == set()
