"""Backup automático de data/jarvis.db (post-incidente 2026-07-03).

El rmtree del incidente se llevó data/jarvis.db y fue lo ÚNICO irrecuperable:
su única copia vivía DENTRO del árbol borrado. `respaldar_db` snapshotea la DB
(sqlite backup API, consistente aún con WAL) a un directorio FUERA del repo,
con rotación, y espejo best-effort en /mnt/d (sobrevive al vhdx de WSL).
"""
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from plotspace.core.mantenimiento import (  # noqa: E402
    _BACKUP_DIR,
    backups_a_purgar,
    respaldar_db,
)

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


def _db_de_prueba(dir_):
    """Crea una DB sqlite mínima con una fila conocida."""
    path = os.path.join(dir_, 'jarvis.db')
    conn = sqlite3.connect(path)
    conn.execute('CREATE TABLE projects (id INTEGER PRIMARY KEY, nombre TEXT)')
    conn.execute("INSERT INTO projects (nombre) VALUES ('demo')")
    conn.commit()
    conn.close()
    return path


def test_backup_dir_default_fuera_del_repo():
    # La razón de ser del backup: si vive dentro del repo, el rmtree del
    # incidente se lo lleva junto con el original.
    assert not _BACKUP_DIR.startswith(_REPO_ROOT + os.sep)
    assert _BACKUP_DIR != _REPO_ROOT


def test_backups_a_purgar_rotacion():
    nombres = [f'jarvis-2026010{d}-000000.db' for d in range(1, 10)]  # 9 backups
    viejos = backups_a_purgar(nombres, max_copias=5)
    assert viejos == [f'jarvis-2026010{d}-000000.db' for d in range(1, 5)]
    assert backups_a_purgar(nombres, max_copias=20) == []


def test_backups_a_purgar_ignora_archivos_ajenos():
    nombres = ['jarvis-20260101-000000.db', 'notas.txt', 'jarvis.db', '.gitkeep']
    assert backups_a_purgar(nombres, max_copias=1) == []


def test_respaldar_db_crea_copia_consistente():
    with tempfile.TemporaryDirectory() as tmp:
        db = _db_de_prueba(tmp)
        destino = os.path.join(tmp, 'backups')
        r = respaldar_db(db_path=db, destino_dir=destino, espejo_dir=None)
        assert r['backup'] and os.path.isfile(r['backup'])
        conn = sqlite3.connect(r['backup'])
        fila = conn.execute('SELECT nombre FROM projects').fetchone()
        conn.close()
        assert fila == ('demo',)


def test_respaldar_db_rota_los_viejos():
    with tempfile.TemporaryDirectory() as tmp:
        db = _db_de_prueba(tmp)
        destino = os.path.join(tmp, 'backups')
        os.makedirs(destino)
        for d in range(1, 8):  # 7 backups pre-existentes, más viejos que el nuevo
            with open(os.path.join(destino, f'jarvis-2020010{d}-000000.db'), 'w') as f:
                f.write('x')
        r = respaldar_db(db_path=db, destino_dir=destino, max_copias=5, espejo_dir=None)
        quedan = sorted(n for n in os.listdir(destino) if n.startswith('jarvis-'))
        assert len(quedan) == 5
        assert os.path.basename(r['backup']) in quedan
        assert 'jarvis-20200101-000000.db' not in quedan


def test_respaldar_db_espejo_best_effort():
    with tempfile.TemporaryDirectory() as tmp:
        db = _db_de_prueba(tmp)
        destino = os.path.join(tmp, 'backups')
        espejo = os.path.join(tmp, 'espejo')
        os.makedirs(espejo)
        r = respaldar_db(db_path=db, destino_dir=destino, espejo_dir=espejo)
        assert r['espejo'] and os.path.isfile(r['espejo'])
        # Espejo inexistente (D: desmontado) NO rompe el backup primario.
        r2 = respaldar_db(db_path=db, destino_dir=destino,
                          espejo_dir=os.path.join(tmp, 'no-existe', 'sub'))
        assert r2['backup'] and r2['espejo'] is None


def test_espejo_configurable_por_env():
    """JARVIS_BACKUP_ESPEJO redirige el espejo (modo app / otras máquinas).
    Vacío = espejo DESACTIVADO a propósito (una app instalada en otra PC no
    tiene /mnt/d). Sin la env var, el default histórico no cambia."""
    import importlib

    import plotspace.core.mantenimiento as mant
    previo = os.environ.get('JARVIS_BACKUP_ESPEJO')
    try:
        os.environ['JARVIS_BACKUP_ESPEJO'] = '/otra/ruta/espejo'
        assert importlib.reload(mant)._BACKUP_ESPEJO == '/otra/ruta/espejo'
        os.environ['JARVIS_BACKUP_ESPEJO'] = ''
        assert importlib.reload(mant)._BACKUP_ESPEJO == ''
        os.environ.pop('JARVIS_BACKUP_ESPEJO', None)
        assert importlib.reload(mant)._BACKUP_ESPEJO == '/mnt/d/jarvis-backups'
    finally:
        if previo is None:
            os.environ.pop('JARVIS_BACKUP_ESPEJO', None)
        else:
            os.environ['JARVIS_BACKUP_ESPEJO'] = previo
        importlib.reload(mant)


def test_respaldar_db_sin_db_no_explota():
    with tempfile.TemporaryDirectory() as tmp:
        r = respaldar_db(db_path=os.path.join(tmp, 'nope.db'),
                         destino_dir=os.path.join(tmp, 'backups'), espejo_dir=None)
        assert r['backup'] is None


if __name__ == '__main__':
    fns = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
    for fn in fns:
        fn()
        print(f'OK {fn.__name__}')
    print(f'{len(fns)} tests OK')
