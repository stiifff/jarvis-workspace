"""Spotify vía Web API (V2 de la Radio) — search público con token de USUARIO
(OAuth 2.0 Authorization Code + PKCE, sin secret requerido).

El flujo: el navegador va a /api/radio/spotify/login → el server le da la URL
de authorize (state + verifier persistidos en data/spotify-pkce.json, 0600),
Spotify vuelve a /api/radio/spotify/callback?code&state → el server
intercambia el code por access+refresh token (data/spotify-token.json, 0600) y
redirige a /workspace?spotify=ok|error. `buscar()` usa el access token del
usuario contra /v1/search. El playback (SDK del browser) lo hace otro agente:
acá NO hay token management de app, todo es la cuenta del usuario.

Credenciales: SPOTIFY_CLIENT_ID (requerido) + SPOTIFY_CLIENT_SECRET (opcional;
sin secret el PKCE es válido con el client_id a secas). Se leen del entorno
(plotspace/.env lo carga main.py con load_dotenv) y, como fallback, de
data/.env (la app instalada guarda ahí sus claves) — NUNCA se commitean.

Consumidor: routers/radio.py (/api/radio/spotify/*) y el endpoint
GET /api/orchestrator/preview/buscar?modo=spotify (routers/orchestrator.py).
"""

import asyncio
import base64
import hashlib
import json
import os
import secrets
import time
import weakref
from urllib.parse import urlencode

import httpx
from dotenv import dotenv_values

from plotspace.core.datadir import ruta_data

_AUTHORIZE_URL = 'https://accounts.spotify.com/authorize'
_TOKEN_URL = 'https://accounts.spotify.com/api/token'
_API_URL = 'https://api.spotify.com/v1/search'
_SCOPES = 'streaming user-read-playback-state'


class SpotifyError(Exception):
    """Spotify no se pudo: sin sesión, sin config, saturado, respuesta rara."""


# Un refresh a la vez (ambos pisan el archivo de token y un doble fetch de
# tracks en paralelo con el token venciéndose podría dejar estado
# inconsistente). Es un asyncio.Lock POR EVENT LOOP: un threading.Lock
# común bloquea el loop entero cuando dos corrutinas compiten en espera de
# un await (la primera cuelga porque la segunda no suelta el GIL del loop).
_locks_refresh = weakref.WeakKeyDictionary()


def _lock_refresh() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    lock = _locks_refresh.get(loop)
    if lock is None:
        lock = _locks_refresh[loop] = asyncio.Lock()
    return lock


def _env_archivo() -> dict:
    """Valores de data/.env (la app instalada guarda ahí sus claves; env del
    proceso manda). Vacío si no existe el archivo o no se puede leer."""
    try:
        return dotenv_values(ruta_data('.env'))
    except (OSError, ValueError):
        return {}


def client_id() -> str:
    v = os.environ.get('SPOTIFY_CLIENT_ID', '').strip()
    if v:
        return v
    return (_env_archivo().get('SPOTIFY_CLIENT_ID') or '').strip()


def client_secret() -> str:
    v = os.environ.get('SPOTIFY_CLIENT_SECRET', '').strip()
    if v:
        return v
    return (_env_archivo().get('SPOTIFY_CLIENT_SECRET') or '').strip()


# ─── Persistencia (data/, 0600) ──────────────────────────────────────────────

def _pkce_path() -> str:
    return ruta_data('spotify-pkce.json')


def _token_path() -> str:
    return ruta_data('spotify-token.json')


def _escribir(p: str, data: dict) -> None:
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f)
    os.replace(tmp, p)
    try:                       # credenciales: nunca world-readable
        os.chmod(p, 0o600)
    except OSError:
        pass                   # best-effort (DrvFs/Windows)


def _leer_json(p: str) -> dict | None:
    try:
        with open(p, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _leer_token() -> dict | None:
    return _leer_json(_token_path())


def _guardar_token(tok: dict) -> None:
    _escribir(_token_path(), tok)


# ─── PKCE: URL de login y canje del code ─────────────────────────────────────

def url_login(base_url: str) -> str:
    """URL de authorize con PKCE S256. Persiste verifier+state en
    data/spotify-pkce.json (0600). '' si SPOTIFY_CLIENT_ID no está seteado."""
    cid = client_id()
    if not cid:
        return ''
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    state = secrets.token_urlsafe(32)
    _escribir(_pkce_path(), {
        'verifier': verifier, 'state': state, 'creado': time.time(),
    })
    redirect_uri = f'{base_url.rstrip("/")}/api/radio/spotify/callback'
    return _AUTHORIZE_URL + '?' + urlencode({
        'client_id': cid,
        'response_type': 'code',
        'redirect_uri': redirect_uri,
        'scope': _SCOPES,
        'code_challenge': challenge,
        'code_challenge_method': 'S256',
        'state': state,
    })


def pendiente() -> dict | None:
    """Estado PKCE vigente ({state, verifier}) o None si no hay login en curso."""
    return _leer_json(_pkce_path())


async def intercambiar(code: str, verifier: str, redirect_uri: str) -> dict:
    """Canjea `code` por token (authorization_code + PKCE; sin secret basta el
    client_id). Guarda {access_token, refresh_token, expires_at} y devuelve la
    respuesta cruda. Levanta SpotifyError si Spotify no acepta el canje."""
    cid = client_id()
    if not cid:
        raise SpotifyError('Spotify no está configurado (SPOTIFY_CLIENT_ID)')
    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': redirect_uri,
        'client_id': cid,
        'code_verifier': verifier,
    }
    sec = client_secret()
    if sec:
        data['client_secret'] = sec
    try:
        async with _cliente() as client:
            resp = await client.post(_TOKEN_URL, data=data)
    except httpx.HTTPError:
        raise SpotifyError('Spotify no respondió') from None
    data_resp = _json_o_error(resp, error_401='No se pudo validar la sesión de Spotify')
    if not data_resp.get('access_token'):
        raise SpotifyError('No se pudo validar la sesión de Spotify')
    _guardar_token({
        'access_token': data_resp['access_token'],
        'refresh_token': data_resp.get('refresh_token') or '',
        'expires_at': time.time() + int(data_resp.get('expires_in', 3600)) - 60,
    })
    return data_resp


# ─── Sesión / refresh ────────────────────────────────────────────────────────

def token_valido() -> bool:
    """Hay access_token no vencido (con 30s de margen)? No hace refresh."""
    t = _leer_token()
    return bool(t and t.get('access_token')
                and t.get('expires_at', 0) > time.time() + 30)


async def refresh() -> dict:
    """Refresca con el refresh_token guardado (lock asyncio: 1 a la vez y con
    re-chequeo — si otro esperó y ya refrescó, NO pisa con un segundo POST).
    Devuelve el token vigente; SpotifyError si no hay sesión válida."""
    async with _lock_refresh():
        t = _leer_token() or {}
        if t.get('expires_at', 0) > time.time() + 30:
            return t          # otro refrescó mientras esperábamos: usar el suyo
        ref = (t.get('refresh_token') or '').strip()
        if not ref:
            raise SpotifyError('Sin sesión de Spotify — iniciá sesión en ⚙ → Radio')
        cid = client_id()
        if not cid:
            raise SpotifyError('Spotify no está configurado (SPOTIFY_CLIENT_ID)')
        data = {'grant_type': 'refresh_token', 'refresh_token': ref,
                'client_id': cid}
        sec = client_secret()
        if sec:
            data['client_secret'] = sec
        try:
            async with _cliente() as client:
                resp = await client.post(_TOKEN_URL, data=data)
        except httpx.HTTPError:
            raise SpotifyError('Spotify no respondió') from None
        if resp.status_code in (400, 401):
            raise SpotifyError('Sin sesión de Spotify — iniciá sesión en ⚙ → Radio')
        data_resp = _json_o_error(
            resp, error_401='Sin sesión de Spotify — iniciá sesión en ⚙ → Radio')
        nuevo = {
            'access_token': data_resp.get('access_token', ''),
            'refresh_token': data_resp.get('refresh_token') or ref,
            'expires_at': time.time() + int(data_resp.get('expires_in', 3600)) - 60,
        }
        _guardar_token(nuevo)
        return nuevo


# ─── Búsqueda ────────────────────────────────────────────────────────────────

def _json_o_error(resp, error_401='Spotify no respondió') -> dict:
    """resp.json() o SpotifyError con mensaje según el status."""
    if resp.status_code == 401:
        raise SpotifyError(error_401)
    if resp.status_code in (403, 429):
        raise SpotifyError('Spotify está saturado — intentá de nuevo en un momento')
    if resp.status_code != 200:
        raise SpotifyError(f'Spotify respondió {resp.status_code}')
    try:
        return resp.json()
    except ValueError:
        raise SpotifyError('no se pudo leer la respuesta de Spotify') from None


def _m_ss(msegundos) -> str:
    try:
        s = int(round(float(msegundos)) / 1000)
    except (TypeError, ValueError):
        return ''
    if s <= 0:
        return ''
    return f'{s // 60}:{s % 60:02d}'


def mapear_track(it: dict) -> dict:
    """Track de /v1/search → shape común de la Radio. Pura y testeable."""
    artistas = [a.get('name', '') for a in (it.get('artists') or [])
                if isinstance(a, dict)]
    nombre_artistas = ', '.join(a for a in artistas if a)
    nombre = (it.get('name') or '').strip()
    tid = str(it.get('id') or '')
    images = ((it.get('album') or {}).get('images') or [])
    thumb = None
    if len(images) > 1:
        thumb = images[1].get('url')
    elif images:
        thumb = images[0].get('url')
    return {
        'id': f'spotify:track:{tid}',
        'url': ((it.get('external_urls') or {}).get('spotify')
                or f'https://open.spotify.com/track/{tid}'),
        'titulo': ' - '.join(x for x in (nombre, nombre_artistas) if x) or nombre,
        'canal': nombre_artistas,
        'duracion': _m_ss(it.get('duration_ms')),
        'thumb': thumb,
    }


async def token_para_sdk() -> dict:
    """Token VIGENTE para el Web Playback SDK (corre en el browser): la sesión
    nunca sale del backend, pero el SDK lo necesita en el cliente.
    Refresca si está por vencer. SpotifyError si no hay sesión."""
    t = _leer_token() or {}
    if not t.get('access_token'):
        raise SpotifyError('Sin sesión de Spotify — iniciá sesión en ⚙ → Radio')
    if t.get('expires_at', 0) <= time.time() + 30 and t.get('refresh_token'):
        t = await refresh()
    if t.get('expires_at', 0) <= time.time():
        raise SpotifyError('Sin sesión de Spotify — iniciá sesión en ⚙ → Radio')
    return {'access_token': t['access_token'],
            'expires_in': max(60, int(t.get('expires_at', 0) - time.time()))}


def _cliente(**kw) -> httpx.AsyncClient:
    """Indirección para que los tests mockeen AsyncClient sin tocar httpx."""
    return httpx.AsyncClient(**kw)


async def buscar(q: str) -> list:
    """Búsqueda de tracks (limit 25) con el token del usuario. Refresca si
    venció. Devuelve items mapeados; SpotifyError si no hay sesión/config."""
    cid = client_id()
    if not cid:
        raise SpotifyError('Spotify no está configurado (SPOTIFY_CLIENT_ID)')
    t = _leer_token() or {}
    if not t.get('access_token'):
        raise SpotifyError('Sin sesión de Spotify — iniciá sesión en ⚙ → Radio')
    if t.get('expires_at', 0) <= time.time() + 30:
        t = await refresh()
    try:
        async with _cliente(timeout=httpx.Timeout(8.0)) as client:
            resp = await client.get(
                _API_URL,
                params={'type': 'track', 'limit': 25, 'q': (q or '').strip()},
                headers={'Authorization': f'Bearer {t["access_token"]}'})
    except httpx.HTTPError:
        raise SpotifyError('Spotify no respondió') from None
    data = _json_o_error(resp, error_401='Sin sesión de Spotify — iniciá sesión en ⚙ → Radio')
    items = ((data.get('tracks') or {}).get('items') or [])
    return [mapear_track(it) for it in items if isinstance(it, dict)]
