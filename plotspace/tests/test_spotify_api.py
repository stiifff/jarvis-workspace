"""Spotify Web API (V2 de la Radio) — core/spotify_api.py.

Se testea SIN red: `_cliente()` se reemplaza por un client fake (httpx y los
parsers son la única capa de red). El datadir se aísla en un tmp_path y las
envs SPOTIFY_* se setean por mock. Cada test corre como script suelto.
"""
import asyncio
import base64
import hashlib
import os
import sys
import tempfile
import time
from contextlib import contextmanager
from unittest import mock

import pytest

# Asegurar imports absolutos 'plotspace.*' al correr el test como script suelto.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from plotspace.core import spotify_api as sp
from plotspace.core import datadir

CLIENT_ID = 'mi-client-id'
CLIENT_SECRET = 'mi-secret'


class _FakeResp:
    def __init__(self, status_code, data=None):
        self.status_code = status_code
        self._data = data

    def json(self):
        if self._data is None:
            raise ValueError('sin json')
        return self._data


class _FakeClient:
    """httpx.AsyncClient completo (get/post) con un handler sincrónico."""

    def __init__(self, handler, **kw):
        self._h = handler

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, **kw):
        return self._h('GET', url, kw)

    async def post(self, url, **kw):
        return self._h('POST', url, kw)


@contextmanager
def _entorno():
    """Env SPOTIFY_* seteadas + datadir aislado en un tmp_path."""
    with tempfile.TemporaryDirectory() as d:
        prev = datadir.DATA_DIR
        datadir.DATA_DIR = d
        try:
            with mock.patch.dict(os.environ, {
                'SPOTIFY_CLIENT_ID': CLIENT_ID,
                'SPOTIFY_CLIENT_SECRET': CLIENT_SECRET,
            }, clear=False):
                yield d
        finally:
            datadir.DATA_DIR = prev


def _fijar_net(handler):
    """Reemplaza httpx.AsyncClient por el fake (sin importar httpx real)."""
    return mock.patch.object(sp, '_cliente', lambda **kw: _FakeClient(handler, **kw))


def test_url_login_sin_client_id_es_vacio():
    with mock.patch.dict(os.environ, {}, clear=True), \
            mock.patch.object(sp, '_env_archivo', lambda: {}):
        assert sp.url_login('http://localhost:3000') == ''


def test_url_login_persiste_pkce_y_pkce_ok():
    from urllib.parse import unquote_plus
    with _entorno() as d:
        url = sp.url_login('http://localhost:3000/')
        assert url.startswith('https://accounts.spotify.com/authorize?')
        params = dict((k, unquote_plus(v)) for k, v in
                      (p.split('=', 1) for p in url.split('?', 1)[1].split('&')))
        assert params['client_id'] == CLIENT_ID
        assert params['response_type'] == 'code'
        assert params['redirect_uri'] == 'http://localhost:3000/api/radio/spotify/callback'
        assert params['code_challenge_method'] == 'S256'
        # El Web Playback SDK exige 'streaming' y la lectura de estado
        # (play/pausa/posición) usa 'user-read-playback-state'.
        assert 'streaming' in params['scope'].split()
        assert 'user-read-playback-state' in params['scope'].split()
        assert 'state' in params and len(params['state']) >= 20

        pend = sp.pendiente()
        assert pend and pend['state'] == params['state']
        # el challenge es bas64url(SHA256(verifier)) sin padding — PKCE S256 real
        esperado = base64.urlsafe_b64encode(
            hashlib.sha256(pend['verifier'].encode()).digest()).decode().rstrip('=')
        assert params['code_challenge'] == esperado
        assert len(pend['verifier']) >= 43        # mínimo RFC 7636
        # El pkce se guarda chmod 600
        modo = os.stat(os.path.join(d, 'spotify-pkce.json')).st_mode & 0o777
        assert modo == 0o600


def test_intercambiar_guarda_token():
    def handler(m, url, kw):
        assert url == 'https://accounts.spotify.com/api/token'
        assert kw['data']['grant_type'] == 'authorization_code'
        assert kw['data']['code_verifier'] == 'verificador-fake'
        assert kw['data']['client_id'] == CLIENT_ID
        assert kw['data']['redirect_uri'] == 'http://h/api/radio/spotify/callback'
        assert kw['data']['client_secret'] == CLIENT_SECRET
        return _FakeResp(200, {'access_token': 'AT-ABC', 'refresh_token': 'RT-1',
                               'expires_in': 3600, 'token_type': 'Bearer'})

    with _entorno() as d, _fijar_net(handler):
        r = asyncio.run(sp.intercambiar(
            'codigo', 'verificador-fake', 'http://h/api/radio/spotify/callback'))
        assert r['access_token'] == 'AT-ABC'

        tok = sp._leer_token()
        assert tok['access_token'] == 'AT-ABC'
        assert tok['refresh_token'] == 'RT-1'
        assert abs(tok['expires_at'] - (time.time() + 3540)) < 15
        modo = os.stat(os.path.join(d, 'spotify-token.json')).st_mode & 0o777
        assert modo == 0o600
        assert sp.token_valido()


def test_token_valido_sin_token():
    with _entorno():
        assert not sp.token_valido()
        with pytest.raises(sp.SpotifyError) as exc:
            asyncio.run(sp.buscar('queen'))
        assert 'Sin sesión de Spotify' in str(exc.value)


def test_intercambiar_falla_sin_json():
    def handler(m, url, kw):
        return _FakeResp(400)          # code inválido → Spotify responde error
    with _entorno(), _fijar_net(handler):
        with pytest.raises(sp.SpotifyError):
            asyncio.run(sp.intercambiar(
                'malo', 'v', 'http://h/api/radio/spotify/callback'))
        assert not sp.token_valido()


def test_buscar_sin_configuracion():
    with mock.patch.dict(os.environ, {}, clear=True), \
            mock.patch.object(sp, '_env_archivo', lambda: {}):
        with pytest.raises(sp.SpotifyError) as exc:
            asyncio.run(sp.buscar('queen'))
        assert 'SPOTIFY_CLIENT_ID' in str(exc.value)


def test_client_id_desde_data_env():
    """El env manda; si falta, cae a data/.env (la app instalada)."""
    with tempfile.TemporaryDirectory() as d:
        prev = datadir.DATA_DIR
        datadir.DATA_DIR = d
        try:
            with open(os.path.join(d, '.env'), 'w', encoding='utf-8') as f:
                f.write(f'SPOTIFY_CLIENT_ID={CLIENT_ID}\n'
                        f'SPOTIFY_CLIENT_SECRET={CLIENT_SECRET}\n')
            with mock.patch.dict(os.environ, {}, clear=True):
                assert sp.client_id() == CLIENT_ID
                assert sp.client_secret() == CLIENT_SECRET
                # env manda sobre data/.env
                with mock.patch.dict(os.environ, {'SPOTIFY_CLIENT_ID': 'otro'}):
                    assert sp.client_id() == 'otro'
        finally:
            datadir.DATA_DIR = prev


def test_callback_state_invalido_no_intercambia():
    """state malo → redirect error y el code NO se canjea (sin POST a token)."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from plotspace.routers import radio

    llamadas = []

    def handler(m, url, kw):
        llamadas.append(url)
        raise AssertionError('no debe intercambiar con state inválido')

    with _entorno() as d, _fijar_net(handler):
        app = FastAPI()
        app.include_router(radio.router)
        client = TestClient(app)
        sp.url_login('http://testserver')        # deja un pendiente con OTRO state
        r = client.get('/api/radio/spotify/callback?code=CODIGO_MALO&state=otro',
                       follow_redirects=False)
        assert r.status_code == 307
        assert '/workspace?spotify=error' in r.headers['location']
        assert llamadas == []
        assert sp._leer_token() is None


def test_callback_replay_o_state_viejo():
    """Callback sin state (o con state perso por un login viejo) → error."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from plotspace.routers import radio

    with _entorno():
        app = FastAPI()
        app.include_router(radio.router)
        client = TestClient(app)
        r = client.get('/api/radio/spotify/callback?code=X',
                       follow_redirects=False)
        assert r.status_code == 307
        assert 'spotify=error' in r.headers['location']


def test_buscar_mapea_tracks():
    with _entorno() as d:
        sp._guardar_token({'access_token': 'AT-OK',
                           'refresh_token': 'RT-1',
                           'expires_at': time.time() + 3600})
        track = {
            'id': 'abc123', 'name': 'Bicycle Race',
            'artists': [{'name': 'Queen'}, {'name': 'Feat'}],
            'duration_ms': 185000,
            'album': {'images': [{'url': 'big'}, {'url': 'mid'}]},
            'external_urls': {'spotify': 'https://open.spotify.com/track/abc123'},
        }

        def handler(m, url, kw):
            assert url == 'https://api.spotify.com/v1/search'
            assert kw['headers']['Authorization'] == 'Bearer AT-OK'
            assert kw['params']['type'] == 'track' and kw['params']['limit'] == 25
            assert kw['params']['q'] == 'queen'
            return _FakeResp(200, {'tracks': {'items': [track]}})

        with _fijar_net(handler):
            r = asyncio.run(sp.buscar('  queen '))
        assert r[0] == {
            'id': 'spotify:track:abc123',
            'url': 'https://open.spotify.com/track/abc123',
            'titulo': 'Bicycle Race - Queen, Feat',
            'canal': 'Queen, Feat',
            'duracion': '3:05',
            'thumb': 'mid',          # album.images[1]
        }
        assert r[0]['id'].startswith('spotify:track:')


def test_mapear_track_robusto():
    r = sp.mapear_track({'id': 'x', 'name': 'Nada', 'duration_ms': None})
    assert r['titulo'] == 'Nada' and r['duracion'] == ''
    assert r['url'] == 'https://open.spotify.com/track/x'
    assert r['id'] == 'spotify:track:x'
    r2 = sp.mapear_track({'id': 'y'})
    assert r2['titulo'] == '' and r2['canal'] == '' and r2['thumb'] is None


def test_buscar_401_sin_sesion():
    with _entorno() as d:
        sp._guardar_token({'access_token': 'AT-VENCIDO',
                           'refresh_token': 'RT-1',
                           'expires_at': time.time() + 3600})
        with _fijar_net(lambda m, url, kw: _FakeResp(401)):
            with pytest.raises(sp.SpotifyError) as exc:
                asyncio.run(sp.buscar('q'))
        assert 'Sin sesión de Spotify' in str(exc.value)


def test_buscar_rate_429_y_403():
    with _entorno() as d:
        sp._guardar_token({'access_token': 'AT-OK', 'refresh_token': 'RT-1',
                           'expires_at': time.time() + 3600})
        for code in (429, 403):
            with _fijar_net(lambda m, url, kw, c=code: _FakeResp(c)):
                with pytest.raises(sp.SpotifyError) as exc:
                    asyncio.run(sp.buscar('q'))
            assert 'saturado' in str(exc.value)


def test_refresh_al_vencer():
    """Token vencido + refresh_token → buscar() refresca y repite la query."""
    with _entorno() as d:
        sp._guardar_token({'access_token': 'AT-VIEJO',
                           'refresh_token': 'RT-1',
                           'expires_at': time.time() - 10})
        llamadas = []

        def handler(m, url, kw):
            llamadas.append(url)
            if url == 'https://accounts.spotify.com/api/token':
                assert kw['data']['grant_type'] == 'refresh_token'
                assert kw['data']['refresh_token'] == 'RT-1'
                return _FakeResp(200, {'access_token': 'AT-NUEVO', 'expires_in': 3600})
            assert kw['headers']['Authorization'] == 'Bearer AT-NUEVO'
            return _FakeResp(200, {'tracks': {'items': [{'id': 'z', 'name': 'Z'}]}})

        with _fijar_net(handler):
            r = asyncio.run(sp.buscar('q'))
        assert 'api/token' in llamadas[0]          # primero refrescó…
        assert 'v1/search' in llamadas[-1]         # …después buscó
        assert r and r[0]['id'] == 'spotify:track:z'
        tok = sp._leer_token()
        assert tok['access_token'] == 'AT-NUEVO'
        assert tok['refresh_token'] == 'RT-1'      # Spotify no lo repite: se conserva


def test_refresh_sin_refresh_token():
    with _entorno() as d:
        sp._guardar_token({'access_token': 'AT-VIEJO', 'refresh_token': '',
                           'expires_at': time.time() - 10})
        with pytest.raises(sp.SpotifyError) as exc:
            asyncio.run(sp.buscar('q'))
        assert 'Sin sesión de Spotify' in str(exc.value)


def test_refresh_concurrente_una_sola_llamada():
    """Dos refreshes en paralelo: el lock asyncio serializa y el segundo NO
    pisa con un POST doble (re-chequea el token ya refrescado)."""
    with _entorno() as d:
        sp._guardar_token({'access_token': 'AT-VIEJO', 'refresh_token': 'RT-1',
                           'expires_at': time.time() - 10})
        posts = []

        def handler(m, url, kw):
            posts.append(url)
            time.sleep(0.05)     # mantener el primer POST en vuelo
            return _FakeResp(200, {'access_token': 'AT-NUEVO',
                                   'refresh_token': 'RT-2', 'expires_in': 3600})

        async def doble_refresh():
            return await asyncio.gather(sp.refresh(), sp.refresh())

        with _fijar_net(handler):
            r1, r2 = asyncio.run(doble_refresh())
        assert len(posts) == 1                          # un solo POST a token
        assert r1['access_token'] == 'AT-NUEVO'
        assert r2['access_token'] == 'AT-NUEVO'         # el 2º usó el que ya se refrescó
        tok = sp._leer_token()
        assert tok['refresh_token'] == 'RT-2'


def test_callback_ok_intercambia_y_guarda():
    """state válido → POST authorization_code → token guardado + redirect ok."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from plotspace.routers import radio

    def handler(m, url, kw):
        assert url == 'https://accounts.spotify.com/api/token'
        assert kw['data']['grant_type'] == 'authorization_code'
        assert kw['data']['code'] == 'CODE-OK'
        return _FakeResp(200, {'access_token': 'AT-OK', 'refresh_token': 'RT-ON',
                               'expires_in': 3600})

    with _entorno() as d, _fijar_net(handler):
        app = FastAPI()
        app.include_router(radio.router)
        client = TestClient(app)

        # el login previo deja el state+verifier en data/spotify-pkce.json
        r = client.get('/api/radio/spotify/login')
        assert r.status_code == 200 and r.json()['url']
        pend = sp.pendiente()

        r = client.get('/api/radio/spotify/callback',
                       params={'code': 'CODE-OK', 'state': pend['state']},
                       follow_redirects=False)
        assert r.status_code == 307
        assert '/workspace?spotify=ok' in r.headers['location']
        tok = sp._leer_token()
        assert tok and tok['access_token'] == 'AT-OK'


def test_login_sin_client_id_error_limpio():
    """/login 200 con {url:'', error} y /estado {configurado:False} — sin 500."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from plotspace.routers import radio

    with tempfile.TemporaryDirectory() as d:
        prev = datadir.DATA_DIR
        datadir.DATA_DIR = d
        try:
            with mock.patch.dict(os.environ, {}, clear=True):
                app = FastAPI()
                app.include_router(radio.router)
                client = TestClient(app)
                r = client.get('/api/radio/spotify/login')
                assert r.status_code == 200
                assert r.json() == {'url': '', 'error': 'Spotify no está configurado (SPOTIFY_CLIENT_ID)'}
                r = client.get('/api/radio/spotify/estado')
                assert r.status_code == 200
                assert r.json() == {'configurado': False, 'sesion': False}
        finally:
            datadir.DATA_DIR = prev


def test_token_para_sdk():
    """GET /spotify/token del router: {access_token, expires_in} con sesión,
    refresca si venció; 401 sin sesión."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from plotspace.routers import radio

    with _entorno() as d:
        app = FastAPI()
        app.include_router(radio.router)
        client = TestClient(app)

        # Sin sesión → 401 con el mensaje amable
        r = client.get('/api/radio/spotify/token')
        assert r.status_code == 401
        assert 'Sin sesión de Spotify' in r.json()['detail']

        # Con sesión vigente → access_token + expires_in (mínimo 60)
        sp._guardar_token({'access_token': 'AT-OK', 'refresh_token': 'RT-1',
                           'expires_at': time.time() + 500})
        r = client.get('/api/radio/spotify/token')
        assert r.status_code == 200
        d = r.json()
        assert d['access_token'] == 'AT-OK'
        assert d['expires_in'] >= 60 and d['expires_in'] <= 500

        # Vencido → refresh automático y token nuevo
        def handler(m, url, kw):
            assert 'api/token' in url
            return _FakeResp(200, {'access_token': 'AT-2', 'expires_in': 3600})
        with _fijar_net(handler):
            sp._guardar_token({'access_token': 'AT-VIEJO', 'refresh_token': 'RT-1',
                               'expires_at': time.time() - 10})
            r = client.get('/api/radio/spotify/token')
            assert r.status_code == 200 and r.json()['access_token'] == 'AT-2'


def test_estado_endpoint():
    """GET /spotify/estado: {configurado, sesion} sin login y con login."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from plotspace.routers import radio

    with _entorno() as d:
        app = FastAPI()
        app.include_router(radio.router)
        client = TestClient(app)
        r = client.get('/api/radio/spotify/estado')
        assert r.json() == {'configurado': True, 'sesion': False}
        sp._guardar_token({'access_token': 'AT-OK', 'refresh_token': 'RT-1',
                           'expires_at': time.time() + 3600})
        assert client.get('/api/radio/spotify/estado').json()['sesion'] is True


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
