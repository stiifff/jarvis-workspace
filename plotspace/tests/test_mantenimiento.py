"""
Test: detección de sesiones tmux huérfanas (plotspace/core/mantenimiento.py).

Una sesión jarvis_<n> es huérfana si no hay una terminal con ese id en la DB.
Las sesiones que no son de card (mobile preview, otros nombres) no matchean el
patrón y nunca se consideran huérfanas (no se las toca).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plotspace.core import mantenimiento
from plotspace.core.mantenimiento import (
    sesiones_huerfanas, logs_a_purgar, _tid_de_log, huerfanas_a_matar,
)

# Estos tests verifican el argv EXACTO de tmux: desde F5·2 el default es el
# termhost, así que hay que pedir ese motor explícitamente (ver conftest).
pytestmark = pytest.mark.usefixtures('motor_tmux')


def test_detecta_sesion_sin_terminal_en_db():
    sesiones = ['jarvis_1', 'jarvis_2', 'jarvis_99']
    assert sesiones_huerfanas(sesiones, {1, 2}) == ['jarvis_99']


def test_ninguna_huerfana_si_todas_estan_en_db():
    assert sesiones_huerfanas(['jarvis_3', 'jarvis_4'], {3, 4, 5}) == []


def test_ignora_sesiones_que_no_son_de_card():
    # mobile preview y cualquier sesión con otro formato NO se tocan
    sesiones = ['jarvis_mpreview_7', 'otra_cosa', 'jarvis_5']
    assert sesiones_huerfanas(sesiones, set()) == ['jarvis_5']


def test_db_vacia_todas_las_de_card_son_huerfanas():
    assert sesiones_huerfanas(['jarvis_8', 'jarvis_9'], set()) == ['jarvis_8', 'jarvis_9']


def test_tolera_espacios_y_vacios():
    assert sesiones_huerfanas([' jarvis_10 ', '', None], {1}) == ['jarvis_10']


# ─── Janitor de logs (.workspace/logs crecía sin techo: 790MB medidos) ────────

def test_tid_de_log_parsea_id():
    assert _tid_de_log('terminal_405_Claude_Code__2.log') == 405
    assert _tid_de_log('terminal_405_Claude.log.1') == 405   # el .1 rotado también
    assert _tid_de_log('otra_cosa.txt') is None


def test_logs_purga_terminales_inactivas():
    ahora = 1000.0
    archivos = [
        {'path': 'terminal_1_X.log',   'mtime': 999.0, 'tid': 1},  # activa+reciente → queda
        {'path': 'terminal_2_Y.log',   'mtime': 999.0, 'tid': 2},  # inactiva → borrar
        {'path': 'terminal_2_Y.log.1', 'mtime': 999.0, 'tid': 2},  # inactiva (.1) → borrar
    ]
    borrar = logs_a_purgar(archivos, {1}, ahora, max_edad_s=10 * 86400)
    assert set(borrar) == {'terminal_2_Y.log', 'terminal_2_Y.log.1'}


def test_logs_purga_viejas_aunque_la_terminal_siga_activa():
    ahora = 30 * 86400
    archivos = [{'path': 'terminal_1_X.log', 'mtime': 0.0, 'tid': 1}]  # activa pero 30d sin tocar
    assert logs_a_purgar(archivos, {1}, ahora, max_edad_s=7 * 86400) == ['terminal_1_X.log']


def test_logs_activa_y_reciente_no_se_toca():
    ahora = 1000.0
    archivos = [{'path': 'terminal_1_X.log', 'mtime': 999.0, 'tid': 1}]
    assert logs_a_purgar(archivos, {1}, ahora, max_edad_s=7 * 86400) == []


def test_logs_archivo_sin_tid_solo_se_borra_si_viejo():
    ahora = 30 * 86400
    archivos = [
        {'path': 'raro.log',     'mtime': ahora - 100, 'tid': None},  # sin tid, reciente → queda
        {'path': 'viejo.log',    'mtime': 0.0,         'tid': None},  # sin tid, viejo → borrar
    ]
    assert logs_a_purgar(archivos, set(), ahora, max_edad_s=7 * 86400) == ['viejo.log']


# ─── Guard anti kill-all (auditoría 2026-07-02, bomba #1) ─────────────────────
# Si el paso DB falló o no devolvió ids, ids_db queda vacío y TODA sesión
# jarvis_* parecería huérfana → sin el guard, un `database is locked` mataba
# el enjambre completo con el trabajo sin commitear adentro.

def test_guard_db_fallo_no_mata_nada():
    assert huerfanas_a_matar(['jarvis_9', 'jarvis_10'], {1}, db_ok=False) == []


def test_guard_sin_ids_no_mata_nada():
    # DB "ok" pero 0 ids: lista incompleta o instalación borrada — jamás matar.
    assert huerfanas_a_matar(['jarvis_9'], set(), db_ok=True) == []


def test_recheck_puntual_salva_terminal_recien_creada():
    # La terminal 9 no estaba en el snapshot pero SÍ está ahora (race de creación).
    assert huerfanas_a_matar(['jarvis_9'], {1}, db_ok=True,
                             existe_en_db=lambda tid: True) == []


def test_recheck_con_error_de_db_no_mata():
    def existe(tid):
        raise RuntimeError('db locked')
    assert huerfanas_a_matar(['jarvis_9'], {1}, db_ok=True, existe_en_db=existe) == []


def test_huerfana_real_se_mata():
    assert huerfanas_a_matar(['jarvis_1', 'jarvis_9'], {1}, db_ok=True,
                             existe_en_db=lambda tid: False) == ['jarvis_9']


# ─── ejecutar_mantenimiento: wiring del guard + timeouts ──────────────────────

class _FakeCur:
    def __init__(self, ids):
        self.ids = ids
        self._last = ''
        self.rowcount = 0

    def execute(self, sql, *a):
        self._last = sql
        return self

    def fetchone(self):
        return (0,)

    def fetchall(self):
        return [{'id': i} for i in self.ids]


class _FakeConn:
    def __init__(self, ids):
        self._cur = _FakeCur(ids)

    def cursor(self):
        return self._cur

    def execute(self, sql, *a):
        return self._cur.execute(sql, *a)

    def commit(self):
        pass

    def close(self):
        pass


class _RunRecorder:
    """Reemplazo de subprocess.run que registra llamadas y devuelve sesiones."""
    def __init__(self, sesiones):
        self.calls = []
        self._sesiones = sesiones

    def __call__(self, args, **kw):
        self.calls.append((list(args), kw))

        class R:
            returncode = 0
            stdout = '\n'.join(self._sesiones)
        return R()


def _con_mantenimiento_parcheado(get_db, sesiones, existe=None):
    """Corre ejecutar_mantenimiento con get_db/subprocess/purga parcheados.
    Devuelve (resumen, recorder)."""
    rec = _RunRecorder(sesiones)
    orig = (mantenimiento.get_db, mantenimiento.subprocess.run,
            mantenimiento.purgar_logs_viejos, mantenimiento._existe_terminal)
    mantenimiento.get_db = get_db
    mantenimiento.subprocess.run = rec
    mantenimiento.purgar_logs_viejos = lambda *a, **k: {'logs_borrados': 0,
                                                        'bytes_liberados': 0}
    if existe is not None:
        mantenimiento._existe_terminal = existe
    try:
        resumen = mantenimiento.ejecutar_mantenimiento()
    finally:
        (mantenimiento.get_db, mantenimiento.subprocess.run,
         mantenimiento.purgar_logs_viejos, mantenimiento._existe_terminal) = orig
    return resumen, rec


def test_ejecutar_db_fallida_saltea_tmux_entero():
    def get_db_roto():
        raise RuntimeError('database is locked')
    resumen, rec = _con_mantenimiento_parcheado(get_db_roto, ['jarvis_1', 'jarvis_2'])
    assert resumen['tmux_huerfanas_matadas'] == 0
    assert resumen.get('tmux_salteado') == 'db_fallo'
    # kill-session JAMÁS con info parcial de DB. (El janitor de huérfanos sí
    # puede listar sesiones incluso con DB rota: no depende de ella y no mata
    # sesiones — solo procesos CLIENTE attach nuestros con sesión inexistente.)
    assert not any('kill-session' in c[0] for c in rec.calls)


def test_ejecutar_sin_ids_saltea_tmux_entero():
    resumen, rec = _con_mantenimiento_parcheado(lambda: _FakeConn([]), ['jarvis_1'])
    assert resumen['tmux_huerfanas_matadas'] == 0
    assert resumen.get('tmux_salteado') == 'db_sin_ids'
    assert not any('kill-session' in c[0] for c in rec.calls)


def test_ejecutar_mata_huerfana_real_con_timeout():
    resumen, rec = _con_mantenimiento_parcheado(
        lambda: _FakeConn([1]), ['jarvis_1', 'jarvis_9'], existe=lambda tid: False)
    assert resumen['tmux_huerfanas_matadas'] == 1
    assert 'tmux_salteado' not in resumen
    kills = [c for c in rec.calls if 'kill-session' in c[0]]
    # `=jarvis_9`, no `jarvis_9`: el `=` es el target EXACTO de tmux. Sin él,
    # tmux resuelve por prefijo — matar "jarvis_9" cuando esa sesión ya no
    # existe se lleva puesta "jarvis_90", que sí está viva y con un agente
    # adentro. El janitor pasó a usar el motor (`matar_sesion_por_nombre`) y
    # con eso heredó esta guarda, que antes no tenía.
    assert len(kills) == 1 and '=jarvis_9' in kills[0][0], kills
    # Todos los tmux del paso llevan timeout (un tmux colgado no clava el thread).
    for args, kw in rec.calls:
        if args and args[0] == 'tmux':
            assert kw.get('timeout') == 5, (args, kw)


# ── Janitor de huérfanos (post-mortem segfault tmux 2026-07-02) ──────────────

def test_parsear_etime_formatos():
    assert mantenimiento.parsear_etime('05:33') == 5 * 60 + 33
    assert mantenimiento.parsear_etime('21:08:56') == 21 * 3600 + 8 * 60 + 56
    assert mantenimiento.parsear_etime('1-12:10:58') == 86400 + 12 * 3600 + 10 * 60 + 58
    assert mantenimiento.parsear_etime('') == 0
    assert mantenimiento.parsear_etime('  00:07  ') == 7


def test_clientes_attach_muertos_solo_firma_exacta_y_sesion_inexistente():
    procesos = [
        (100, 'tmux attach-session -d -t jarvis_838'),   # sesión muerta → matar
        (101, 'tmux attach-session -d -t jarvis_929'),   # sesión viva → NO
        (102, 'tmux -C attach-session -t jarvis_838'),   # control-mode: otra firma → NO
        (103, 'vim tmux attach-session -d -t jarvis_9 x'),  # args con cola → NO (firma anclada)
        (104, 'grep tmux'),                               # cualquier otra cosa → NO
    ]
    assert mantenimiento.clientes_attach_muertos(procesos, ['jarvis_929']) == [100]
    # Sin sesiones vivas (server tmux muerto): TODOS los attach nuestros son basura.
    assert mantenimiento.clientes_attach_muertos(procesos, []) == [100, 101]


def test_huerfanos_pesados_detecta_la_firma_del_desastre_jest():
    jest = {'pid': 565514, 'ppid': 1, 'etime_s': 21 * 3600, 'cpu': 8.0,
            'args': 'node /home/user/proyectos/Derlis-APP/node_modules/.bin/jest src'}
    joven = dict(jest, pid=2, etime_s=120)                    # recién nacido → NO
    liviano = dict(jest, pid=3, cpu=0.5)                      # sin CPU → NO
    con_padre = dict(jest, pid=4, ppid=878)                   # hijo de uvicorn → NO
    ajeno = dict(jest, pid=5, args='node /usr/lib/algo.js')   # fuera de proyectos → NO
    out = mantenimiento.huerfanos_pesados([jest, joven, liviano, con_padre, ajeno])
    assert [p['pid'] for p in out] == [565514]


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
