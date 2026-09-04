"""
Tests: commit-propio (scripts/commit_propio.py) — lógica pura.

El commit sin miedo del árbol compartido: stagea SOLO lo que el tracking en
vivo (LIVE.md) te vio escribir, bajo lock. Acá se testea la selección; el
lock/commit son wiring de git.
"""
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'scripts'))
import commit_propio as cp


LIVE = """# LIVE — qué está haciendo cada agente (auto-generado, NO editar)
Actualizado: 2026-07-19 03:00:00

## Backend (claude, terminal 100) — 🟢 trabajando
- `plotspace/core/database.py` — write ×3 (hace 1m) 🔒 dueño
- `plotspace/routers/system.py` — write ×1 (hace 5m)

## Frontend (claude, terminal 200) — ⚪ idle
- `frontend/shell/workspace.js` — write ×2 (hace 5m) 🔒 dueño

## Permisos
- ⏳ Frontend pidió PERMISO sobre `plotspace/core/database.py` (dueño: Backend) — hace 1m
"""


def test_archivos_de_mi_seccion_todos_no_solo_lockeados():
    mios = cp.archivos_de_mi_seccion(LIVE, 100)
    assert mios == ['plotspace/core/database.py', 'plotspace/routers/system.py']
    assert cp.archivos_de_mi_seccion(LIVE, 200) == ['frontend/shell/workspace.js']
    assert cp.archivos_de_mi_seccion(LIVE, 999) == []


def test_elegir_staged_interseca_sucios_con_mios():
    dirty = ['plotspace/core/database.py', 'frontend/shell/workspace.js', 'otro.py']
    staged = cp.elegir_staged(dirty, ['plotspace/core/database.py'], [])
    assert staged == ['plotspace/core/database.py'], 'ni lo ajeno ni lo no-trackeado'


def test_elegir_staged_extras_explicitos():
    staged = cp.elegir_staged(['a.py'], [], ['b.py', 'a.py'])
    assert staged == ['b.py', 'a.py']


# ─── Stage por HUNK (provenance) ──────────────────────────────────────────────
# `git add <archivo>` no es "lo mío" en este árbol: es el archivo ENTERO, con el
# trabajo sin commitear del otro adentro. Ya se llevó puesta una función ajena.
# Con la provenance real se decide por archivo cómo stagear.

def test_candidatos_cruza_sucios_con_provenance():
    assert cp.elegir_candidatos(
        dirty=['a.py', 'b.py', 'c.py'], archivos_prov=['a.py', 'c.py'],
        mios_live=[], extras=[]) == ['a.py', 'c.py']


def test_candidatos_suma_los_de_live_md():
    """LIVE.md sigue valiendo como respaldo: si el hook no vio algo pero el
    tracking sí, no se pierde."""
    assert cp.elegir_candidatos(dirty=['a.py', 'b.py'], archivos_prov=['a.py'],
                                mios_live=['b.py'], extras=[]) == ['a.py', 'b.py']


def test_candidatos_suma_extras_aunque_no_esten_sucios():
    assert 'nuevo.py' in cp.elegir_candidatos(dirty=[], archivos_prov=[],
                                              mios_live=[], extras=['nuevo.py'])


def test_candidatos_no_duplica():
    assert cp.elegir_candidatos(dirty=['a.py'], archivos_prov=['a.py'],
                                mios_live=['a.py'], extras=['a.py']) == ['a.py']


def test_candidatos_ignora_sucios_ajenos():
    assert cp.elegir_candidatos(dirty=['mio.py', 'del_otro.py'],
                                archivos_prov=['mio.py'], mios_live=[],
                                extras=[]) == ['mio.py']


def test_archivo_solo_mio_va_completo():
    assert cp.clasificar_archivos(['a.py'], untracked=set(), ajenos={},
                                  extras=set()) == {'a.py': 'archivo'}


def test_archivo_compartido_va_por_hunk():
    assert cp.clasificar_archivos(['a.py'], untracked=set(),
                                  ajenos={'a.py': ['texto del otro']},
                                  extras=set()) == {'a.py': 'hunk'}


def test_archivo_nuevo_va_completo_aunque_figure_compartido():
    """Un archivo sin trackear no tiene versión previa: el diff por hunk no
    aplica."""
    assert cp.clasificar_archivos(['n.py'], untracked={'n.py'},
                                  ajenos={'n.py': ['x']},
                                  extras=set()) == {'n.py': 'archivo'}


def test_extra_explicito_va_completo():
    """Si el agente lo pidió a mano, manda él (sabe algo que el tracking no vio)."""
    assert cp.clasificar_archivos(['a.py'], untracked=set(),
                                  ajenos={'a.py': ['otro']},
                                  extras={'a.py'}) == {'a.py': 'archivo'}


def test_varios_archivos_modos_mezclados():
    assert cp.clasificar_archivos(
        ['solo.py', 'compartido.js', 'nuevo.md'], untracked={'nuevo.md'},
        ajenos={'compartido.js': ['x']}, extras=set()) == {
            'solo.py': 'archivo', 'compartido.js': 'hunk', 'nuevo.md': 'archivo'}


# ─── Atribución: trailer Jarvis-Agent (recuperar de quién es un commit) ───────
# El autor git de TODOS los agentes es el mismo, así que git log no
# puede decir de qué agente es un commit. El trailer lo hace recuperable, sin
# tocar el autor (que el CI/popup esperan estable).

def test_nombre_de_agente_desde_live():
    assert cp.nombre_de_agente(LIVE, 100) == 'Backend'
    assert cp.nombre_de_agente(LIVE, 200) == 'Frontend'
    assert cp.nombre_de_agente(LIVE, 999) is None      # no está en LIVE.md


def test_trailer_atribucion_formato():
    assert cp.trailer_atribucion('Backend', 100) == 'Jarvis-Agent: Backend (tid 100)'


def test_trailer_atribucion_sin_nombre_usa_el_tid():
    """Si LIVE.md todavía no tenía mi encabezado, igual dejo el tid — un commit
    atribuible a 'terminal 42' es mejor que uno anónimo."""
    assert cp.trailer_atribucion(None, 42) == 'Jarvis-Agent: terminal 42 (tid 42)'


def test_trailer_atribucion_recorta_nombre_raro():
    """El nombre viaja a un trailer de una línea: nada de saltos que rompan el
    bloque de trailers."""
    t = cp.trailer_atribucion('Back\nend', 7)
    assert '\n' not in t and 'tid 7' in t


if __name__ == '__main__':
    import pytest
    raise SystemExit(pytest.main([__file__, '-q']))


# ── El lock funciona en los tres sistemas ────────────────────────────────
# `fcntl` es de Unix. Su import al tope hacía que este script —y este archivo
# de tests— ni se pudieran cargar en Windows, y eso abortaba la colección de
# la suite ENTERA. Lo cazó el CI en su primera corrida allá.

def test_el_lock_serializa_de_verdad(tmp_path):
    """Es lo que impide que dos agentes que commitean a la vez se lleven los
    archivos del otro: el índice de git es compartido."""
    ruta = tmp_path / 'lock'
    with open(ruta, 'w') as a:
        cp._tomar_lock(a)
        # El MISMO proceso con OTRO descriptor no debe poder tomarlo.
        with open(ruta, 'w') as b:
            try:
                cp._tomar_lock(b, espera=0.3)
                tomado = True
            except RuntimeError:
                tomado = False
    assert tomado is False, 'el lock no serializa: dos agentes commitearían a la vez'


def test_el_lock_se_libera_al_cerrar(tmp_path):
    ruta = tmp_path / 'lock2'
    with open(ruta, 'w') as a:
        cp._tomar_lock(a)
    # Cerrado el archivo, el siguiente lo toma sin esperar.
    with open(ruta, 'w') as b:
        cp._tomar_lock(b, espera=0.3)


def test_esperar_de_mas_avisa_en_vez_de_colgarse(tmp_path):
    """Un agente colgado no puede dejar a los demás esperando para siempre sin
    decir por qué."""
    import pytest
    ruta = tmp_path / 'lock3'
    with open(ruta, 'w') as a:
        cp._tomar_lock(a)
        with open(ruta, 'w') as b:
            with pytest.raises(RuntimeError, match='otro agente'):
                cp._tomar_lock(b, espera=0.2)
