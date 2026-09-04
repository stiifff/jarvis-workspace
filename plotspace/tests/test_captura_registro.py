"""
Test: las señales de fricción que antes se evaporaban quedan REGISTRADAS.

Capa Captura del sistema de memoria (parte 2):
  - jarvis.log conserva DOS generaciones al rotar (.1 → .2) en vez de pisar .1
  - el canary de /api/system/restart deja el traceback en el audit trail
    (antes viajaba solo en el body del 409 y se perdía)
  - guard_propiedad registra cada commit bloqueado en data/jarvis.log
  - la purga de task_events retiene 5000 (corpus para las lecciones)
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plotspace.tests._harness import fresh_db
from plotspace.core.database import get_db


# ─── Rotación de jarvis.log: dos generaciones ────────────────────────────────

def test_rotacion_conserva_dos_generaciones():
    from plotspace.core import logs
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, 'jarvis.log')
        with open(path, 'w') as f:
            f.write('GEN1\n' * 10)
        with open(path + '.1', 'w') as f:
            f.write('GEN0\n')

        orig_path, orig_max = logs._LOG_PATH, logs._MAX_BYTES
        logs._LOG_PATH = path
        logs._MAX_BYTES = 10          # el archivo vivo ya lo supera → rota
        try:
            logs.evento('prueba_rotacion', dato='x')
        finally:
            logs._LOG_PATH, logs._MAX_BYTES = orig_path, orig_max

        assert 'GEN0' in open(path + '.2').read(), "la generación vieja debe correrse a .2, no pisarse"
        assert 'GEN1' in open(path + '.1').read()
        assert 'prueba_rotacion' in open(path).read()


# ─── Canary: el traceback queda en el audit trail ────────────────────────────

def test_canary_fallo_queda_en_el_log():
    import plotspace.routers.system as system
    from plotspace.core import logs

    registrados = []
    orig_canary, orig_evento = system._canary_import, logs.evento
    system._canary_import = lambda *a, **k: (False, 'ImportError: modulo_rompido')
    logs.evento = lambda tipo, nivel='info', **campos: registrados.append((tipo, nivel, campos))
    try:
        resp = system.restart()
    finally:
        system._canary_import = orig_canary
        logs.evento = orig_evento

    assert resp.status_code == 409
    assert any(t == 'canary_fallo' and n == 'error' and 'modulo_rompido' in str(c)
               for (t, n, c) in registrados), f"canary_fallo no registrado: {registrados}"


# ─── guard_propiedad: bloqueo con registro ───────────────────────────────────

def test_guard_registra_bloqueo():
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), 'scripts'))
    import guard_propiedad as guard

    with tempfile.TemporaryDirectory() as raiz:
        viol = [{'path': 'plotspace/x.py', 'dueno_tid': 3, 'dueno_nombre': 'Backend'}]
        # Aislar del entorno real: sin JARVIS_DATA_DIR cae a <raiz>/data
        env_prev = os.environ.pop('JARVIS_DATA_DIR', None)
        try:
            guard.registrar_bloqueo(raiz, 7, viol)
        finally:
            if env_prev is not None:
                os.environ['JARVIS_DATA_DIR'] = env_prev

        log = os.path.join(raiz, 'data', 'jarvis.log')
        assert os.path.exists(log), "el bloqueo debe dejar rastro en data/jarvis.log"
        rec = json.loads(open(log).read().strip().splitlines()[-1])
        assert rec['evento'] == 'guard_propiedad_bloqueo'
        assert rec['nivel'] == 'warn'
        assert rec['terminal_id'] == 7
        assert 'plotspace/x.py' in str(rec['archivos'])


def test_guard_registrar_nunca_rompe():
    import guard_propiedad as guard
    # raíz sin permisos de escritura → no debe levantar excepción (falla abierto)
    env_prev = os.environ.pop('JARVIS_DATA_DIR', None)
    try:
        guard.registrar_bloqueo('/proc/no-se-puede-escribir', 1,
                                [{'path': 'a', 'dueno_tid': 2, 'dueno_nombre': 'B'}])
    finally:
        if env_prev is not None:
            os.environ['JARVIS_DATA_DIR'] = env_prev


# ─── Retención de task_events: corpus para las lecciones ─────────────────────

def test_purga_task_events_retiene_5000_por_default():
    from plotspace.core.database import purgar_task_events
    fresh_db()
    conn = get_db()
    try:
        conn.execute("INSERT INTO projects (id, nombre, ruta, fecha_creacion, ultimo_acceso) "
                     "VALUES (1, 'p', '/tmp/p', '2026-07-10', '2026-07-10')")
        conn.executemany(
            "INSERT INTO task_events (terminal_id, project_id, event, timestamp) VALUES (1, 1, 'SENT', ?)",
            [(f'2026-07-10T10:00:{i:02d}',) for i in range(5200)])
        conn.commit()
    finally:
        conn.close()

    purgar_task_events()

    conn = get_db()
    try:
        n = conn.execute('SELECT COUNT(*) c FROM task_events').fetchone()['c']
    finally:
        conn.close()
    assert n == 5000, f"la purga default debe retener 5000 (quedaron {n})"


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
