"""
Tests: telemetría de uso de memorias en DB (tabla memoria_uso).

El feedback del recall vivía en el audit trail (data/jarvis.log): rota a 5MB,
horizonte de 500 eventos, y de un solo bit ("dijo que la leyó"). Esta capa lo
persiste en SQLite CRUZADO con el resultado del paso (done/blocked/error) —
la señal que casi ningún sistema de memoria tiene: una memoria que aparece en
pasos que terminan bien sube en el ranking; una que solo aparece en fallos no.

Invariantes:
1. registrar_uso_memorias persiste (project, terminal, slug, resultado).
2. conteo_uso_memorias(resultado='done') cuenta SOLO lecturas exitosas.
3. memoria_recall.usos_registrados usa la DB (pasos done) como fuente primaria.
4. La purga acota la tabla (no crece sin techo).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plotspace.tests._harness import fresh_db
from plotspace.core import database as db


def test_registrar_y_contar_por_resultado():
    fresh_db()
    db.registrar_uso_memorias(1, 10, ['flow-control', 'regla-de-puertos'], 'done')
    db.registrar_uso_memorias(1, 11, ['flow-control'], 'done')
    db.registrar_uso_memorias(1, 12, ['memoria-sospechosa'], 'blocked')
    done = db.conteo_uso_memorias(resultado='done')
    assert done == {'flow-control': 2, 'regla-de-puertos': 1}
    todos = db.conteo_uso_memorias()
    assert todos['memoria-sospechosa'] == 1


def test_registrar_vacio_es_noop():
    fresh_db()
    db.registrar_uso_memorias(1, 10, [], 'done')
    assert db.conteo_uso_memorias() == {}


def test_recall_usa_db_como_fuente_primaria():
    from plotspace.core.memoria_recall import usos_registrados
    fresh_db()
    db.registrar_uso_memorias(1, 10, ['leida-en-exito'], 'done')
    db.registrar_uso_memorias(1, 11, ['leida-en-fallo'], 'blocked')
    usos = usos_registrados()
    assert usos.get('leida-en-exito') == 1
    assert 'leida-en-fallo' not in usos, 'solo los pasos done suben el ranking'


def test_slugs_usados_exime_cualquier_resultado():
    # para la cuarentena, leer es leer: una memoria leída (aunque el paso haya
    # fallado) está viva y no debe archivarse
    from plotspace.routers.memory import _slugs_usados
    fresh_db()
    db.registrar_uso_memorias(1, 10, ['leida-en-fallo'], 'blocked')
    assert 'leida-en-fallo' in _slugs_usados()


def test_purga_acota_memoria_uso():
    fresh_db()
    for i in range(30):
        db.registrar_uso_memorias(1, 10, [f'slug-{i}'], 'done')
    db.purgar_task_events(keep=5000)          # purga ambas tablas de telemetría
    conn = db.get_db()
    try:
        n = conn.execute('SELECT COUNT(*) c FROM memoria_uso').fetchone()['c']
    finally:
        conn.close()
    assert n == 30                             # bajo el techo: no borra nada
    db._purgar_memoria_uso(keep=10)
    conn = db.get_db()
    try:
        n = conn.execute('SELECT COUNT(*) c FROM memoria_uso').fetchone()['c']
        ultimo = conn.execute('SELECT slug FROM memoria_uso ORDER BY id DESC LIMIT 1').fetchone()['slug']
    finally:
        conn.close()
    assert n == 10 and ultimo == 'slug-29', 'retiene las más nuevas'


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


# ─── Altímetro: inyectadas vs leídas ─────────────────────────────────────────

def test_inyectada_no_cuenta_como_lectura():
    fresh_db()
    db.registrar_uso_memorias(1, 10, ['sugerida'], 'inyectada')
    db.registrar_uso_memorias(1, 11, ['leida'], 'done')
    assert 'sugerida' not in db.conteo_uso_memorias(excluir='inyectada')
    assert 'leida' in db.conteo_uso_memorias(excluir='inyectada')
    # y no exime de la cuarentena (solo el cierre de un agente es lectura)
    from plotspace.routers.memory import _slugs_usados
    assert 'sugerida' not in _slugs_usados()
    assert 'leida' in _slugs_usados()


def test_metricas_altimetro():
    fresh_db()
    db.registrar_uso_memorias(1, 10, ['a', 'b'], 'inyectada')
    db.registrar_uso_memorias(1, 10, ['a'], 'done')
    db.registrar_uso_memorias(1, 11, ['c'], 'blocked')
    m = db.metricas_memoria_uso(dias=7)
    assert m['inyecciones'] == 2
    assert m['lecturas'] == 2
    assert m['lecturas_en_done'] == 1
    assert m['tasa_lectura'] == 0.5      # de {a,b} inyectadas, se leyó a


def test_bloque_relevantes_registra_inyeccion():
    import tempfile
    from plotspace.core.memoria_recall import bloque_relevantes
    fresh_db()
    with tempfile.TemporaryDirectory() as d:
        conn = db.get_db()
        try:
            conn.execute("INSERT INTO projects (id, nombre, ruta, fecha_creacion, ultimo_acceso) "
                         "VALUES (7, 'p', ?, '2026-07-19', '2026-07-19')", (d,))
            conn.commit()
        finally:
            conn.close()
        mdir = os.path.join(d, '.jarvis', 'memory')
        os.makedirs(mdir)
        with open(os.path.join(mdir, 'flow-control.md'), 'w') as f:
            f.write("---\ntitulo: Flow control de websockets\ntags: [terminales]\n"
                    "creado: 2026-07-01\nestado: vigente\n---\n\n"
                    "Detalle de `plotspace/core/flow.py`.\n")
        b = bloque_relevantes(d, ['plotspace/core/flow.py'], 'tocar el flow control',
                              terminal_id=8)
        assert 'flow-control' in b
        conteo = db.conteo_uso_memorias(resultado='inyectada')
        assert conteo.get('flow-control') == 1
