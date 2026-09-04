"""Búsqueda de YouTube de la Radio — server-side, sin API keys.

La página de resultados de YouTube llega entera por httpx: los videos viajan
en el JSON `var ytInitialData = {...}` embebido en el HTML. Las tandas
siguientes y los relacionados reales salen de youtubei/v1 (search / next), y
`filtrar_embebibles` descarta los que su dueño no deja reproducir embebidos.

Los parsers (`parsear_youtube`, `parsear_yt_mas`, `parsear_yt_relacionados`)
son puros y se testean offline en plotspace/tests/test_web_search.py. Consumidor:
el endpoint GET /api/orchestrator/preview/buscar (routers/orchestrator.py), que
alimenta la Radio (frontend/sections/radio/radio.js).

Hasta 2026-07-26 este módulo servía además la búsqueda WEB (DuckDuckGo
scrapeado con el Chromium headless de Playwright, porque DDG devuelve un
challenge de JS al fetch plano) y la de Twitch, para serp.html — el buscador
viejo del Web Preview. Las dos se eliminaron con él: buscar ahora es navegar a
Google/YouTube de verdad, así que acá no queda NADA que dependa de Playwright
ni del browser remoto. Si alguna vez vuelve una búsqueda web propia, hay que
volver a traer un Chromium: httpx solo no pasa el challenge.

SSRF: no aplica — el host destino es fijo (youtube.com); lo único que controla
el usuario es el término de búsqueda, URL-encodeado.
"""

import asyncio
import json
import re
from urllib.parse import quote_plus

import httpx


class BusquedaError(Exception):
    """La búsqueda no se pudo completar (timeout, formato nuevo de YouTube…)."""


# UA de browser real: el default de httpx/HeadlessChrome dispara challenges.
_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')

MAX_YT = 18

# ─── Parser puro: resultados de YouTube (ytInitialData) ───────────────────────

def _texto_yt(nodo):
    """Texto de un nodo de YouTube: {'runs':[{'text':…}]} o {'simpleText':…}."""
    if not isinstance(nodo, dict):
        return None
    if isinstance(nodo.get('simpleText'), str):
        return nodo['simpleText']
    runs = nodo.get('runs')
    if isinstance(runs, list) and runs:
        return ''.join(r.get('text', '') for r in runs if isinstance(r, dict)) or None
    return None


def _recorrer_yt(data):
    """Recorre una respuesta de YouTube (JSON ya parseado) y devuelve
    `(videoRenderers, tokens_de_continuacion)` en orden de documento."""
    videos, tokens = [], []

    def _caminar(nodo):
        if isinstance(nodo, dict):
            vr = nodo.get('videoRenderer')
            if isinstance(vr, dict) and vr.get('videoId'):
                videos.append(vr)
            cir = nodo.get('continuationItemRenderer')
            if isinstance(cir, dict):
                tok = (((cir.get('continuationEndpoint') or {})
                        .get('continuationCommand') or {}).get('token'))
                if isinstance(tok, str) and tok:
                    tokens.append(tok)
            for v in nodo.values():
                _caminar(v)
        elif isinstance(nodo, list):
            for v in nodo:
                _caminar(v)

    _caminar(data)
    return videos, tokens


def _videos_yt(videos, max_n):
    """videoRenderers → resultados normalizados, dedupeados por id."""
    out, vistos = [], set()
    for vr in videos:
        vid = vr['videoId']
        if vid in vistos:
            continue
        vistos.add(vid)
        thumbs = (vr.get('thumbnail') or {}).get('thumbnails') or []
        thumb = thumbs[-1].get('url') if thumbs and isinstance(thumbs[-1], dict) else None
        out.append({
            'id': vid,
            'url': f'https://www.youtube.com/watch?v={vid}',
            'titulo': _texto_yt(vr.get('title')),
            'canal': _texto_yt(vr.get('ownerText')) or _texto_yt(vr.get('longBylineText')),
            'duracion': _texto_yt(vr.get('lengthText')),
            'vistas': _texto_yt(vr.get('shortViewCountText')) or _texto_yt(vr.get('viewCountText')),
            'thumb': thumb,
        })
        if len(out) >= max_n:
            break
    return out


def parsear_youtube_pagina(html, max_n=MAX_YT):
    """HTML de youtube.com/results → `{'resultados': [...], 'token': str|None}`.

    `token` es la continuación de la búsqueda: el "mostrar más" real de YouTube
    (los dots de continuación de la Radio). Se toma el ÚLTIMO del documento —
    los estantes/carruseles traen los suyos y el de la lista principal va al
    final. Levanta BusquedaError si el ytInitialData no está o no parsea.
    """
    m = re.search(r'var ytInitialData\s*=\s*(\{.*?\});</script>', html or '', re.DOTALL)
    if not m:
        raise BusquedaError('YouTube no devolvió resultados (challenge o formato nuevo)')
    try:
        data = json.loads(m.group(1))
    except ValueError as e:
        raise BusquedaError('no se pudo leer la respuesta de YouTube') from e
    videos, tokens = _recorrer_yt(data)
    return {'resultados': _videos_yt(videos, max_n), 'token': tokens[-1] if tokens else None}


def parsear_youtube(html, max_n=MAX_YT):
    """HTML de youtube.com/results → [{id, url, titulo, canal, duracion,
    vistas, thumb}]. Levanta BusquedaError si el JSON ytInitialData no está o
    no parsea (challenge/consent o cambio de formato). Puro: testeable offline.
    """
    return parsear_youtube_pagina(html, max_n)['resultados']


def parsear_yt_mas(data, max_n=MAX_YT):
    """Respuesta de youtubei/v1/search con `continuation` (la tanda siguiente)
    → `{'resultados': [...], 'token': str|None}`. Mismos videoRenderer que la
    página + el token de la tanda que sigue. Puro y tolerante a basura."""
    videos, tokens = _recorrer_yt(data)
    return {'resultados': _videos_yt(videos, max_n), 'token': tokens[-1] if tokens else None}


# ─── Búsquedas ────────────────────────────────────────────────────────────────

async def buscar_youtube_pagina(q, max_n=MAX_YT):
    """Busca `q` en YouTube parseando el ytInitialData de la página de
    resultados (httpx, sin browser) → {'resultados', 'token'}. El token es la
    continuación (más resultados de ESA búsqueda) para buscar_youtube_mas."""
    q = (q or '').strip()
    if not q:
        raise BusquedaError('consulta vacía')
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(8.0), follow_redirects=True,
            headers={'User-Agent': _UA, 'Accept-Language': 'es'},
            cookies={'CONSENT': 'YES+cb'},
        ) as client:
            resp = await client.get(
                'https://www.youtube.com/results?search_query=' + quote_plus(q))
            resp.raise_for_status()
    except httpx.HTTPError as e:
        raise BusquedaError('YouTube no respondió') from e
    return parsear_youtube_pagina(resp.text, max_n)


# Token de continuación: base64 url-safe (a veces con padding y ya
# url-decodificado). Se valida forma y largo — lo único que viaja del cliente.
_YT_TOKEN_RE = re.compile(r'^[A-Za-z0-9_\-=.%]{20,4000}$')


async def buscar_youtube_mas(token, max_n=MAX_YT):
    """Tanda SIGUIENTE de una búsqueda de YouTube (youtubei/v1/search con el
    `continuation` que trajo la tanda anterior) → {'resultados', 'token'}.
    Es el "mostrar más" real: resultados nuevos de la MISMA consulta, sin
    repetir los ya vistos."""
    tok = (token or '').strip()
    if not _YT_TOKEN_RE.match(tok):
        raise BusquedaError('token de continuación inválido')
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(8.0),
            headers={'User-Agent': _UA, 'Accept-Language': 'es'},
            cookies={'CONSENT': 'YES+cb'},
        ) as client:
            resp = await client.post(
                'https://www.youtube.com/youtubei/v1/search',
                json={'continuation': tok,
                      'context': {'client': {'clientName': 'WEB',
                                             'clientVersion': '2.20250101.00.00'}}})
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        raise BusquedaError('YouTube no respondió') from e
    except ValueError as e:
        raise BusquedaError('no se pudo leer la respuesta de YouTube') from e
    return parsear_yt_mas(data, max_n)


# ─── Relacionados REALES de un video (youtubei/v1/next) ──────────────────────
# Las continuaciones de la Radio. Antes se simulaban buscando el nombre del
# canal del track: esa búsqueda devuelve los mismos hits del artista bajo OTROS
# ids de video (official/en vivo/re-upload), el dedupe por id no los ve y la
# misma canción volvía a sonar a las 2-3 pistas. youtubei/v1/next entrega lo
# que YouTube encadenaría de verdad: el video del autoplay + la pantalla final.

def parsear_yt_relacionados(data, max_n=MAX_YT):
    """Respuesta de youtubei/v1/next → [{id, url, titulo, canal, duracion,
    vistas, thumb}]: primero el video que el autoplay de YouTube encadenaría
    (playerOverlayAutoplayRenderer) y después la pared de sugeridos del final
    (endScreenVideoRenderer). El del autoplay no trae duración/thumb y suele
    repetirse en el endscreen: se fusionan en una entrada. Puro y tolerante a
    basura (devuelve [])."""
    autoplay, endscreen = [], []

    def _caminar(nodo):
        if isinstance(nodo, dict):
            a = nodo.get('playerOverlayAutoplayRenderer')
            if isinstance(a, dict) and a.get('videoId'):
                autoplay.append(a)
            e = nodo.get('endScreenVideoRenderer')
            if isinstance(e, dict) and e.get('videoId'):
                endscreen.append(e)
            for v in nodo.values():
                _caminar(v)
        elif isinstance(nodo, list):
            for v in nodo:
                _caminar(v)

    _caminar(data)

    out, por_id = [], {}

    def _sumar(vid, titulo, canal, duracion, vistas, thumb):
        prev = por_id.get(vid)
        if prev is not None:   # repetido → completar lo que le faltaba
            for k, v in (('titulo', titulo), ('canal', canal), ('duracion', duracion),
                         ('vistas', vistas), ('thumb', thumb)):
                if not prev[k] and v:
                    prev[k] = v
            return
        item = {'id': vid, 'url': f'https://www.youtube.com/watch?v={vid}',
                'titulo': titulo, 'canal': canal, 'duracion': duracion,
                'vistas': vistas, 'thumb': thumb}
        por_id[vid] = item
        out.append(item)

    for a in autoplay:
        _sumar(a['videoId'], _texto_yt(a.get('videoTitle')), _texto_yt(a.get('byline')),
               None, _texto_yt(a.get('shortViewCountText')), None)
    for e in endscreen:
        thumbs = (e.get('thumbnail') or {}).get('thumbnails') or []
        thumb = thumbs[-1].get('url') if thumbs and isinstance(thumbs[-1], dict) else None
        _sumar(e['videoId'], _texto_yt(e.get('title')), _texto_yt(e.get('shortBylineText')),
               _texto_yt(e.get('lengthText')), _texto_yt(e.get('shortViewCountText')), thumb)
    return out[:max_n]


_YT_VIDEO_ID_RE = re.compile(r'^[A-Za-z0-9_-]{6,20}$')


async def relacionados_youtube(video_id, max_n=MAX_YT):
    """Relacionados reales del video `video_id` vía youtubei/v1/next (httpx,
    sin API key; mismo contexto WEB que _chequear_embebible). Devuelve la
    lista de parsear_yt_relacionados; BusquedaError si el id no tiene forma
    de id de YouTube o la red falló."""
    vid = (video_id or '').strip()
    if not _YT_VIDEO_ID_RE.match(vid):
        raise BusquedaError('id de video inválido')
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(8.0),
            headers={'User-Agent': _UA, 'Accept-Language': 'es'},
            cookies={'CONSENT': 'YES+cb'},
        ) as client:
            resp = await client.post(
                'https://www.youtube.com/youtubei/v1/next',
                json={'videoId': vid,
                      'context': {'client': {'clientName': 'WEB',
                                             'clientVersion': '2.20250101.00.00'}}})
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        raise BusquedaError('YouTube no respondió') from e
    except ValueError as e:
        raise BusquedaError('no se pudo leer la respuesta de YouTube') from e
    return parsear_yt_relacionados(data, max_n)


# ─── Filtro "solo embebibles" (la Radio reproduce INLINE) ────────────────────
# La búsqueda de YouTube no dice si un video se puede reproducir embebido; mucha
# música (VEVO/sellos) lo tiene BLOQUEADO por su dueño y en la Radio quedaba
# muda / salteando. Chequeo por video contra youtubei/v1/player
# (playabilityStatus.playableInEmbed), concurrente y CACHEADO por id.

_EMBED_CACHE: dict = {}          # video_id → bool (la embebibilidad casi no cambia)
_EMBED_CACHE_MAX = 4000

def aplicar_filtro_embebibles(resultados, embebible_por_id):
    """Parte PURA del filtro: conserva los resultados cuyo id es embebible.
    Sin id o sin veredicto (falló el chequeo) → se CONSERVA (no sobre-filtrar:
    mejor un tema que salte a una lista vaciada por un error de red)."""
    return [r for r in (resultados or [])
            if not r.get('id') or embebible_por_id.get(r['id'], True)]


async def _chequear_embebible(client, video_id):
    """True si YouTube declara el video reproducible EMBEBIDO. Ante cualquier
    duda (red, formato raro) devuelve True — el onError del player queda como
    red de seguridad en el cliente."""
    if video_id in _EMBED_CACHE:
        return _EMBED_CACHE[video_id]
    try:
        resp = await client.post(
            'https://www.youtube.com/youtubei/v1/player',
            json={'videoId': video_id,
                  'context': {'client': {'clientName': 'WEB',
                                         'clientVersion': '2.20250101.00.00'}}})
        ps = (resp.json() or {}).get('playabilityStatus') or {}
        # SOLO el veto explícito filtra (playableInEmbed: false = el dueño
        # bloquea la reproducción embebida). El status NO alcanza: los streams
        # en vivo reportan UNPLAYABLE con playableInEmbed: true en este
        # endpoint (verificado 2026-07-08). Lo demás lo cubre el onError.
        ok = ps.get('playableInEmbed') is not False
    except Exception:
        return True   # sin veredicto: no cachear ni filtrar
    if len(_EMBED_CACHE) >= _EMBED_CACHE_MAX:
        _EMBED_CACHE.clear()
    _EMBED_CACHE[video_id] = ok
    return ok


async def filtrar_embebibles(resultados):
    """Deja SOLO los videos reproducibles embebidos ("inline"). Chequeos
    concurrentes (uno por id no cacheado); si el lote entero falla, devuelve la
    lista original intacta."""
    ids = [r['id'] for r in (resultados or []) if r.get('id')]
    if not ids:
        return resultados or []
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(6.0),
            headers={'User-Agent': _UA, 'Accept-Language': 'es'},
            cookies={'CONSENT': 'YES+cb'},
        ) as client:
            veredictos = await asyncio.gather(
                *(_chequear_embebible(client, vid) for vid in ids))
    except Exception:
        return resultados
    return aplicar_filtro_embebibles(resultados, dict(zip(ids, veredictos)))
