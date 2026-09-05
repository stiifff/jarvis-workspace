"""Biblioteca de música local (V1 de la Radio) — core/musica_local.py.

Aísla el datadir en un tmp_path (datadir.DATA_DIR repunteado) y prueba:
listado recursivo, tags (mutagen mockeado) y fallback por nombre, filtro por
q, tope de archivos, traversal-safe en listar/archivo/portada y el guardado
de uploads. Los tests del endpoint /api/radio/local/* (router) se montan con
el TestClient. Cada test corre como script suelto (bloque __main__).
"""
import contextlib
import io
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest
from fastapi.testclient import TestClient

# Asegurar imports absolutos 'plotspace.*' al correr el test como script suelto.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from plotspace.core import musica_local as ml
from plotspace.core import datadir


@contextlib.contextmanager
def _biblioteca():
    """datadir aislado en un tmp_path; data/music con un árbol de prueba."""
    with tempfile.TemporaryDirectory() as d:
        prev = datadir.DATA_DIR
        datadir.DATA_DIR = d
        try:
            music = Path(d) / 'music'
            (music / 'Queen' / 'Greatest Hits').mkdir(parents=True)
            (music / 'Queen' / 'Greatest Hits' / 'Queen - Bicycle Race.mp3').write_bytes(b'x')
            (music / 'Queen' / 'Greatest Hits' / 'cover.jpg').write_bytes(b'img')
            (music / 'Queen' / 'Greatest Hits' / 'Queen - We Are the Champions.mp3').write_bytes(b'x')
            (music / 'Queen' / 'Queen - Bohemian Rhapsody.mp3').write_bytes(b'x')
            yield d
        finally:
            datadir.DATA_DIR = prev


@contextlib.contextmanager
def _datadir_vacio():
    with tempfile.TemporaryDirectory() as d:
        prev = datadir.DATA_DIR
        datadir.DATA_DIR = d
        try:
            yield d
        finally:
            datadir.DATA_DIR = prev


def _tupla_tags(mutagen_easy):
    """Fake de mutagen.File(path, easy=True) para el camino de tags."""
    class _Info:
        length = 123.45

    class _F:
        tags = mutagen_easy
        info = _Info()

    return _F


def test_listar_vacio():
    with _datadir_vacio():
        assert ml.listar() == []


def test_listar_nombres_sin_tags():
    with _biblioteca() as d:
        items = ml.listar()
        # Sin mutagen: se parsea 'Artista - Título' del nombre y el canal sale
        # del árbol de directorios (raíz/álbum).
        por_id = {it['id']: it for it in items}
        assert len(items) == 3
        r = por_id['Queen/Greatest Hits/Queen - Bicycle Race.mp3']
        assert r['titulo'] == 'Queen - Bicycle Race'
        assert r['canal'] == 'Queen/Greatest Hits'
        assert r['duracion'] == ''
        assert r['url'] == ('/api/radio/local/archivo?p=Queen%2FGreatest%20Hits%2F'
                            'Queen%20-%20Bicycle%20Race.mp3')
        assert r['thumb'] == ('/api/radio/local/thumb?p=Queen%2FGreatest%20Hits%2Fcover.jpg')
        raiz = por_id['Queen/Queen - Bohemian Rhapsody.mp3']
        assert raiz['canal'] == 'Queen'
        assert raiz['thumb'] == ''   # sin cover en su dir


def test_listar_tags_mutagen():
    """Con mutagen disponible: título 'Artista - Título' desde los tags, canal
    'artista/album' y duración m:ss desde info.length."""
    with _biblioteca(), \
            mock.patch.object(ml, '_MUTAGEN', True), \
            mock.patch.object(ml, '_archivo_mutagen',
                              lambda path, easy: _tupla_tags({'artist': ['The Band'],
                                                              'title': ['La Canción'],
                                                              'album': ['LP Uno']})):
        items = ml.listar()
        assert items, 'debe haber items'
        primero = items[0]
        assert primero['titulo'] == 'The Band - La Canción'
        assert primero['canal'] == 'The Band/LP Uno'
        assert primero['duracion'] == '2:03'   # 123.45s


def test_filtro_por_q():
    with _biblioteca():
        assert {it['id'] for it in ml.listar(filtro='bicycle')} == {
            'Queen/Greatest Hits/Queen - Bicycle Race.mp3'}
        # El filtro también matchea el canal (dir raíz/álbum)
        assert len(ml.listar(filtro='greatest')) == 2
        assert ml.listar(filtro='zzzinexistente') == []
        # Sin filtro → todo
        assert len(ml.listar()) == 3


def test_tope_de_archivos():
    with _biblioteca(), mock.patch.object(ml, 'MAX_ARCHIVOS', 2):
        assert len(ml.listar()) == 2


def test_listar_carpeta_traversal():
    with _biblioteca():
        with pytest.raises(ml.MusicaError):
            ml.listar('../')
        with pytest.raises(ml.MusicaError):
            ml.listar('/etc')
        with pytest.raises(ml.MusicaError):
            ml.listar('Queen/../../etc')
        with pytest.raises(ml.MusicaError):
            ml.listar('inexistente')


def test_listar_carpeta_valida():
    with _biblioteca():
        items = ml.listar('Queen/Greatest Hits')
        assert len(items) == 2


def test_archivo_resuelve_y_valida():
    with _biblioteca() as d:
        p = ml.archivo('Queen/Queen - Bohemian Rhapsody.mp3')
        assert os.path.isfile(p)
        assert p.startswith(str(Path(d) / 'music'))
        for mala in ('../x.mp3', '..\\x.mp3', '/etc/passwd', 'a/../../etc',
                     'Queen/x.txt', '3.mp3', 'Queen//Queens.mp3'):
            with pytest.raises(ml.MusicaError):
                ml.archivo(mala)
        with pytest.raises(ml.MusicaError):
            ml.archivo('Queen/inexistente.mp3')


def test_archivo_escapes_con_symlink():
    with _biblioteca() as d, tempfile.TemporaryDirectory() as fuera_dir:
        # Un symlink dentro de la biblioteca apuntando FUERA: resolve() lo
        # sigue y is_relative_to lo rechaza (por ruta ESCRITA, no por la file).
        fuera = Path(fuera_dir) / 'secret.mp3'
        fuera.write_bytes(b'x')
        os.symlink(str(fuera), str(Path(d) / 'music' / 'link-negro.mp3'))
        with pytest.raises(ml.MusicaError):
            ml.archivo('link-negro.mp3')
        link_dir = Path(d) / 'music' / 'direccion'
        os.makedirs(link_dir, exist_ok=True)
        os.symlink(fuera_dir, str(link_dir / 'fuera'))
        with pytest.raises(ml.MusicaError):
            ml.archivo('direccion/fuera/x.mp3')


def test_portada():
    with _biblioteca():
        p = ml.portada('Queen/Greatest Hits/cover.jpg')
        assert os.path.isfile(p)
        with pytest.raises(ml.MusicaError):
            ml.portada('Queen/Greatest Hits/portada-no.jpg')
        with pytest.raises(ml.MusicaError):
            ml.portada('../cover.jpg')


def test_guardar_upload():
    with _biblioteca() as d:
        assert ml.guardar('Mi Tema.mp3', b'0123') == 'Mi_Tema.mp3'
        guardado = Path(d) / 'music' / 'audio' / 'Mi_Tema.mp3'
        assert guardado.read_bytes() == b'0123'
        # Unicidad con sufijo
        assert ml.guardar('Mi Tema.mp3', b'4567') == 'Mi_Tema (1).mp3'
        # Extensiones fuera de la lista → error catalogable
        with pytest.raises(ml.MusicaError):
            ml.guardar('virus.exe', b'')
        # Nombres con separadores se sanean a su basename
        assert ml.guardar('uno/../dos.mp3', b'z') == 'dos.mp3'
        with pytest.raises(ml.MusicaError):
            ml.guardar('sin-extension', b'z')


def test_router_listar_y_archivo():
    """Endpoint /local/listar (shape {items,error}) y /local/archivo (404 JSON
    en errores, FileResponse con Cache-Control en éxito)."""
    from fastapi import FastAPI
    from plotspace.routers import radio

    with _biblioteca():
        app = FastAPI()
        app.include_router(radio.router)
        client = TestClient(app)

        r = client.get('/api/radio/local/listar')
        assert r.status_code == 200
        body = r.json()
        assert body['error'] is None and len(body['items']) == 3
        # La Radio lee data.resultados (_filas): ambas claves van juntas
        assert body['resultados'] == body['items']

        r = client.get('/api/radio/local/listar?carpeta=../')
        assert r.status_code == 200
        assert r.json()['items'] == [] and r.json()['error']

        r = client.get('/api/radio/local/archivo?p=Queen/Queen%20-%20Bohemian%20Rhapsody.mp3')
        assert r.status_code == 200
        assert r.headers['content-type'].startswith('audio/mpeg')
        assert r.headers['cache-control'] == 'public, max-age=3600'

        r = client.get('/api/radio/local/archivo?p=../x.mp3')
        assert r.status_code == 404 and 'error' in r.json()

        r = client.get('/api/radio/local/thumb?p=Queen/Greatest%20Hits/cover.jpg')
        assert r.status_code == 200
        assert r.headers['content-type'].startswith('image/jpeg')

        r = client.post('/api/radio/local/subir', files={
            'files': ('demo song.mp3', io.BytesIO(b'datos'), 'audio/mpeg')})
        assert r.status_code == 200
        assert 'demo_song.mp3' in r.json()['archivos']
        # La Radio sube con el campo multipart `archivos` — ambos aceptados
        r = client.post('/api/radio/local/subir', files={
            'archivos': ('otro.wav', io.BytesIO(b'wav'), 'audio/wav')})
        assert r.status_code == 200
        assert 'otro.wav' in r.json()['archivos']
        # El archivo subido aparece en el listado
        r = client.get('/api/radio/local/listar')
        assert any('demo_song.mp3' in it['id'] for it in r.json()['items'])


def test_orchestrator_modo_local():
    """preview/buscar?modo=local traduce items (sin vistas) y errores de la
    biblioteca al shape de la Radio, sin tocar los modos yt. Sin q → todo."""
    import asyncio
    from plotspace.routers.orchestrator import preview_buscar

    def _listar(carpeta, filtro):
        return [{'id': 'a/b.mp3', 'titulo': 'Q - T', 'canal': 'Q',
                 'duracion': '1:00', 'thumb': '', 'url': '/api/radio/local/archivo?p=a%2Fb.mp3'}]

    with mock.patch.object(ml, 'listar', _listar):
        r = asyncio.run(preview_buscar(q='t', modo='local'))
        assert r['error'] is None and r['token'] is None
        assert r['resultados'] == [{'id': 'a/b.mp3',
                                    'url': '/api/radio/local/archivo?p=a%2Fb.mp3',
                                    'titulo': 'Q - T', 'canal': 'Q',
                                    'duracion': '1:00', 'thumb': ''}]
        # modo=local sin q → lista todo (el filtro es opcional; no es 400)
        r = asyncio.run(preview_buscar(q='', modo='local'))
        assert r['error'] is None and r['resultados'][0]['id'] == 'a/b.mp3'

    # Error catalogable → mismo shape que BusquedaError
    def _reventar(carpeta, filtro):
        raise ml.MusicaError('carpeta inexistente')

    with mock.patch.object(ml, 'listar', _reventar):
        r = asyncio.run(preview_buscar(q='t', modo='local'))
        assert r['resultados'] == [] and r['error'] == 'carpeta inexistente'


def test_formato_duracion():
    assert ml._formato_duracion(None) == ''
    assert ml._formato_duracion(0) == ''
    assert ml._formato_duracion(74.6) == '1:15'
    assert ml._formato_duracion(3661) == '61:01'


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
