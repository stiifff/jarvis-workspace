"""Radio — fuentes de música del server.

V1 (música local): la biblioteca vive en `data/music/`; la Radio la recorre y
sirve los archivos con un media_type correcto y cache amable. Toda ruta
relativa se valida contra `ruta_musica()` (traversal-safe, ver
core/musica_local.py).

V2 (Spotify): OAuth Authorization Code + PKCE contra la Web API con el token
del usuario. /spotify/login devuelve la URL de authorize; /spotify/callback
canjea el code y redirige al workspace. El playback (SDK) lo hace el front.

Errores "catalogables" siguen el patrón de BusquedaError (web_search.py): 200
con `{'error': texto}` cuando el cliente puede mostrarlos (listar, subir).
Los archivos servidos que no existen son 404 — un <audio src> roto no gana
nada con un JSON 200. Consumido por frontend/sections/radio/radio.js vía
GET /api/orchestrator/preview/buscar?modo=local|spotify.
"""

import asyncio
import os
import secrets

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from plotspace.core import musica_local as ml
from plotspace.core import spotify_api as sp

router = APIRouter(prefix="/api/radio", tags=["radio"])


def _base_url(request: Request) -> str:
    """Esquema+host del request (la redirect_uri de Spotify debe ser EXACTA
    la misma en authorize y callback: se deriva del mismo request)."""
    return f'{request.url.scheme}://{request.url.netloc}'


# ─── Música local ────────────────────────────────────────────────────────────

@router.get("/local/listar")
async def local_listar(carpeta: str = ''):
    """Items de la biblioteca local. `carpeta` es un subdir relativo ('' =
    raíz); si no existe o escapa de ruta_musica() → {'items': [], 'error'}.
    Se devuelve también `resultados` (los MISMOS items): la Radio consumía
    ese shape desde el primer día (_filas lee data.resultados) — ambas claves
    apuntan a la misma lista."""
    try:
        items = await asyncio.to_thread(ml.listar, carpeta)
        return {'items': items, 'resultados': items, 'error': None}
    except ml.MusicaError as e:
        return {'items': [], 'resultados': [], 'error': str(e)}


@router.get("/local/archivo")
async def local_archivo(p: str = ''):
    """Sirve un archivo de audio (FileResponse, cache 1h pública). Ruta
    traversal-safe: p se valida como relpath bajo la raíz de música."""
    try:
        ruta = await asyncio.to_thread(ml.archivo, p)
    except ml.MusicaError as e:
        return JSONResponse(status_code=404, content={'error': str(e)})
    ext = os.path.splitext(ruta)[1].lower()
    return FileResponse(
        ruta,
        media_type=ml.MEDIA_TYPES.get(ext, 'application/octet-stream'),
        headers={'Cache-Control': 'public, max-age=3600'},
    )


@router.get("/local/thumb")
async def local_thumb(p: str = ''):
    """Portada (cover.jpg/png) del MISMO dir de un tema — la `thumb` de las
    items locales la apunta acá (archivo() solo sirve audio)."""
    try:
        ruta = await asyncio.to_thread(ml.portada, p)
    except ml.MusicaError as e:
        return JSONResponse(status_code=404, content={'error': str(e)})
    ext = os.path.splitext(ruta)[1].lower()
    return FileResponse(
        ruta,
        media_type=ml.IMAGEN_TYPES.get(ext, 'application/octet-stream'),
        headers={'Cache-Control': 'public, max-age=3600'},
    )


@router.post("/local/subir")
async def local_subir(files: list[UploadFile] = File(default_factory=list),
                      archivos: list[UploadFile] = File(default_factory=list)):
    """Sube uno o varios archivos a data/music/audio/ (nombre saneado, único).
    Acepta el campo multipart `files` O `archivos` (la Radio usa `archivos`).
    Extensiones fuera de la lista de audio saltan como error catalogable."""
    recibidos = list(files or []) + list(archivos or [])
    if not recibidos:
        return {'error': 'no se recibieron archivos'}
    guardados = []
    for u in recibidos:
        try:
            contenido = await u.read()
            nombre = await asyncio.to_thread(ml.guardar, u.filename or '', contenido)
        except ml.MusicaError as e:
            return {'error': str(e)}
        guardados.append(nombre)
    return {'archivos': guardados}


# ─── Spotify (Web API, token de usuario) ─────────────────────────────────────

@router.get("/spotify/login")
async def spotify_login(request: Request):
    """URL de authorize (PKCE S256) o error si SPOTIFY_CLIENT_ID no está."""
    url = sp.url_login(_base_url(request))
    if not url:
        return {'url': '', 'error': 'Spotify no está configurado (SPOTIFY_CLIENT_ID)'}
    return {'url': url, 'error': None}


@router.get("/spotify/callback")
async def spotify_callback(request: Request, code: str = '', state: str = ''):
    """Spotify vuelve acá con code+state: se valida el state contra el
    persistido, se canjea por token y se redirige al workspace con el veredicto
    en la query (el front puede avisar sin leer el archivo de token)."""
    ok = False
    try:
        pend = sp.pendiente()
        if pend and pend.get('state') and secrets.compare_digest(pend['state'], state):
            await sp.intercambiar(
                code, pend.get('verifier', ''),
                _base_url(request) + '/api/radio/spotify/callback')
            ok = True
    except Exception:
        ok = False
    return RedirectResponse('/workspace?spotify=ok' if ok else '/workspace?spotify=error')


# ─── Estado (para la UI: ¿hay sesión de Spotify para buscar?) ────────────────

@router.get("/spotify/token")
async def spotify_token():
    """Token vigente para el Web Playback SDK (que corre en el browser):
    {access_token, expires_in} o 401 sin sesión. El cliente lo cachea con
    expires_in y lo re-pide al vencer — el backend refresca solo si está por
    expirar, así que el SDK siempre recibe uno usable."""
    try:
        return await sp.token_para_sdk()
    except sp.SpotifyError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.get("/spotify/estado")
async def spotify_estado():
    """{configurado: bool, sesion: bool} — la Radio usa esto para mostrar
    "iniciá sesión" en vez de un aviso de error genérico al buscar."""
    config = bool(sp.client_id())
    sesion = sp.token_valido() if config else False
    return {'configurado': config, 'sesion': sesion}
