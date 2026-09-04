# JARVIS_DATA_DIR — el directorio de datos sale del repo cuando la app lo pide.
#
# Modo app (shell de escritorio): el shell setea JARVIS_DATA_DIR y TODO el
# estado local (DB, token, logs, snapshots de cuentas, perfil de browser,
# páginas del Web Builder) vive ahí. Sin la env var, el comportamiento es el
# histórico: <repo>/data. Regla que fijan estos tests: ningún módulo construye
# rutas a data/ a mano — siempre backend.core.datadir.ruta_data(...).

import importlib
import os
from contextlib import contextmanager

import plotspace.core.datadir as datadir

_REPO_DATA = os.path.abspath(
    os.path.join(os.path.dirname(datadir.__file__), '..', '..', 'data')
)


@contextmanager
def _env_datadir(valor):
    """Setea/borra JARVIS_DATA_DIR, recarga datadir, y SIEMPRE restaura al
    salir (env + reload) para no contaminar al resto de la suite."""
    previo = os.environ.get('JARVIS_DATA_DIR')
    try:
        if valor is None:
            os.environ.pop('JARVIS_DATA_DIR', None)
        else:
            os.environ['JARVIS_DATA_DIR'] = valor
        yield importlib.reload(datadir)
    finally:
        if previo is None:
            os.environ.pop('JARVIS_DATA_DIR', None)
        else:
            os.environ['JARVIS_DATA_DIR'] = previo
        importlib.reload(datadir)


def test_default_es_data_del_repo():
    with _env_datadir(None) as dd:
        assert os.path.realpath(dd.DATA_DIR) == os.path.realpath(_REPO_DATA)


def test_env_var_redirige_y_crea_el_directorio(tmp_path):
    destino = tmp_path / 'app-data'
    assert not destino.exists()
    with _env_datadir(str(destino)) as dd:
        assert os.path.realpath(dd.DATA_DIR) == os.path.realpath(str(destino))
        assert destino.is_dir()   # lo crea solo: una app instalada arranca en frío


def test_env_vacia_o_blanca_cae_al_default():
    with _env_datadir('   ') as dd:
        assert os.path.realpath(dd.DATA_DIR) == os.path.realpath(_REPO_DATA)


def test_expande_usuario(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path))
    with _env_datadir(os.path.join('~', 'mis-datos')) as dd:
        assert dd.DATA_DIR == str(tmp_path / 'mis-datos')


def test_ruta_data_une_segmentos(tmp_path):
    with _env_datadir(str(tmp_path)) as dd:
        assert dd.ruta_data('jarvis.db') == str(tmp_path / 'jarvis.db')
        assert dd.ruta_data('cli-accounts', 'acc1') == str(
            tmp_path / 'cli-accounts' / 'acc1')


def test_consumidores_siguen_el_data_dir(tmp_path):
    """Los módulos que persisten estado calculan sus rutas vía datadir."""
    import plotspace.core.database as database
    import plotspace.core.logs as logs
    import plotspace.core.cli_accounts as cli_accounts
    mods = [database, logs, cli_accounts]
    try:
        with _env_datadir(str(tmp_path)):
            for m in mods:
                importlib.reload(m)
            assert database.DB_PATH == str(tmp_path / 'jarvis.db')
            assert logs._LOG_PATH == str(tmp_path / 'jarvis.log')
            assert cli_accounts.SNAPSHOTS_DIR == str(tmp_path / 'cli-accounts')
    finally:
        # env ya restaurado por _env_datadir → volver los módulos al default
        for m in mods:
            importlib.reload(m)


def test_upload_dir_usa_el_tempdir_del_sistema(tmp_path):
    """UPLOAD_DIR deriva de tempfile.gettempdir() (portable), no de '/tmp'
    hardcodeado. En Linux es idéntico (/tmp); en mac/Windows apunta al temp
    real del sistema."""
    import tempfile as _tf

    import plotspace.routers.terminals as terminals
    previo = _tf.tempdir
    try:
        _tf.tempdir = str(tmp_path)
        t2 = importlib.reload(terminals)
        assert t2.UPLOAD_DIR == str(tmp_path / 'jarvis_uploads')
    finally:
        _tf.tempdir = previo
        importlib.reload(terminals)


def test_guard_del_editor_protege_el_data_activo(tmp_path):
    """projects_files bloquea servir archivos del data dir ACTIVO (no solo el
    del repo): el token/DB no deben poder leerse desde el editor aunque los
    datos vivan fuera del repo."""
    import plotspace.routers.projects_files as pf
    try:
        with _env_datadir(str(tmp_path)):
            pf2 = importlib.reload(pf)
            secreto = tmp_path / 'jarvis.db'
            secreto.write_text('no-servible')
            assert not pf2._es_servible(str(secreto))
            # y el data/ del repo sigue bloqueado como siempre
            assert not pf2._es_servible(os.path.join(_REPO_DATA, 'jarvis.db'))
    finally:
        importlib.reload(pf)
