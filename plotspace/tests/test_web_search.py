"""Tests de la búsqueda de YouTube de la Radio (plotspace/core/web_search.py).

Solo la lógica pura (parsers y validación del endpoint): nada de red. Los
fixtures replican la forma real de la página de resultados de YouTube
(ytInitialData) y de youtubei/v1 (search / next).

Los tests de los parsers de DuckDuckGo y Twitch se fueron con el buscador viejo
del Web Preview (serp.html), eliminado el 2026-07-26 junto a buscar_web /
buscar_twitch.
"""

import asyncio
import json

import pytest

from plotspace.core.web_search import (
    BusquedaError,
    parsear_youtube,
    parsear_yt_relacionados,
)


# ─── parsear_youtube ───────────────────────────────────────────────────────────

def _pagina_youtube(videos, extra=''):
    """Arma un HTML mínimo con la forma real: var ytInitialData = {...};"""
    contents = [{'videoRenderer': v} for v in videos]
    data = {
        'contents': {'twoColumnSearchResultsRenderer': {'primaryContents': {
            'sectionListRenderer': {'contents': [
                {'itemSectionRenderer': {'contents': contents}},
            ]},
        }}},
    }
    return (f'<html><body>{extra}<script>'
            f'var ytInitialData = {json.dumps(data)};</script></body></html>')


def _video(vid='abc123', titulo='Lofi beats', canal='Canal X', dur='1:02:03'):
    return {
        'videoId': vid,
        'title': {'runs': [{'text': titulo}]},
        'ownerText': {'runs': [{'text': canal}]},
        'lengthText': {'simpleText': dur},
        'shortViewCountText': {'simpleText': '1,2 M de vistas'},
        'thumbnail': {'thumbnails': [
            {'url': 'https://i.ytimg.com/vi/abc123/default.jpg'},
            {'url': 'https://i.ytimg.com/vi/abc123/hqdefault.jpg'},
        ]},
    }


def test_youtube_extrae_video_completo():
    res = parsear_youtube(_pagina_youtube([_video()]))
    assert res == [{
        'id': 'abc123',
        'url': 'https://www.youtube.com/watch?v=abc123',
        'titulo': 'Lofi beats',
        'canal': 'Canal X',
        'duracion': '1:02:03',
        'vistas': '1,2 M de vistas',
        'thumb': 'https://i.ytimg.com/vi/abc123/hqdefault.jpg',  # la más grande
    }]


def test_youtube_tolera_campos_faltantes():
    v = {'videoId': 'x1', 'title': {'runs': [{'text': 'Sin nada más'}]}}
    res = parsear_youtube(_pagina_youtube([v]))
    assert res[0]['id'] == 'x1'
    assert res[0]['canal'] is None
    assert res[0]['duracion'] is None
    assert res[0]['thumb'] is None


def test_youtube_dedupea_y_respeta_max():
    videos = [_video(vid='dup')] * 3 + [_video(vid=f'v{i}') for i in range(30)]
    res = parsear_youtube(_pagina_youtube(videos), max_n=10)
    assert len(res) == 10
    assert res[0]['id'] == 'dup'
    assert res[1]['id'] == 'v0'


def test_youtube_ignora_renderers_sin_videoid():
    res = parsear_youtube(_pagina_youtube([{'title': {'runs': [{'text': 'roto'}]}}]))
    assert res == []


def test_youtube_sin_ytinitialdata_levanta():
    with pytest.raises(BusquedaError):
        parsear_youtube('<html><body>challenge</body></html>')


def test_youtube_json_roto_levanta():
    with pytest.raises(BusquedaError):
        parsear_youtube('<script>var ytInitialData = {"a": rotisimo};</script>')


# ─── Continuación de la búsqueda: "mostrar más" (los dots de la Radio) ────────
# La página de resultados trae, al final de la lista, un continuationItemRenderer
# con el token de la SIGUIENTE tanda; ese token se manda a youtubei/v1/search y
# la respuesta llega como appendContinuationItemsAction (mismos videoRenderer +
# el token de la tanda que sigue). Verificado contra YouTube real 2026-07-20.

def _cont(token):
    return {'continuationItemRenderer': {
        'continuationEndpoint': {'continuationCommand': {'token': token}}}}


def _pagina_con_token(videos, token):
    contents = [{'videoRenderer': v} for v in videos]
    data = {'contents': {'twoColumnSearchResultsRenderer': {'primaryContents': {
        'sectionListRenderer': {'contents': [
            {'itemSectionRenderer': {'contents': contents}},
            _cont(token),
        ]}}}}}
    return f'<html><body><script>var ytInitialData = {json.dumps(data)};</script></body></html>'


def _respuesta_continuacion(videos, token=None):
    items = [{'videoRenderer': v} for v in videos]
    if token:
        items.append(_cont(token))
    return {'onResponseReceivedCommands': [
        {'appendContinuationItemsAction': {'continuationItems': items}}]}


def test_youtube_pagina_devuelve_resultados_y_token():
    from plotspace.core.web_search import parsear_youtube_pagina
    out = parsear_youtube_pagina(_pagina_con_token([_video(vid='v1')], 'TOKEN_PAG2'))
    assert out['token'] == 'TOKEN_PAG2'
    assert [r['id'] for r in out['resultados']] == ['v1']


def test_youtube_pagina_sin_token_no_rompe():
    from plotspace.core.web_search import parsear_youtube_pagina
    out = parsear_youtube_pagina(_pagina_youtube([_video(vid='v1')]))
    assert out['token'] is None and len(out['resultados']) == 1


def test_youtube_pagina_toma_el_ULTIMO_token_de_la_pagina():
    """Los carruseles/estantes traen sus propias continuaciones; la de la lista
    principal (la que da 'más resultados') es la última del documento."""
    from plotspace.core.web_search import parsear_youtube_pagina
    data = {'contents': [_cont('TOKEN_ESTANTE'),
                         {'itemSectionRenderer': {'contents': [{'videoRenderer': _video()}]}},
                         _cont('TOKEN_LISTA')]}
    html = f'<script>var ytInitialData = {json.dumps(data)};</script>'
    assert parsear_youtube_pagina(html)['token'] == 'TOKEN_LISTA'


def test_youtube_mas_parsea_la_tanda_siguiente_con_su_token():
    from plotspace.core.web_search import parsear_yt_mas
    out = parsear_yt_mas(_respuesta_continuacion(
        [_video(vid='v2'), _video(vid='v3')], token='TOKEN_PAG3'))
    assert [r['id'] for r in out['resultados']] == ['v2', 'v3']
    assert out['token'] == 'TOKEN_PAG3'


def test_youtube_mas_sin_token_final_y_tolera_basura():
    from plotspace.core.web_search import parsear_yt_mas
    out = parsear_yt_mas(_respuesta_continuacion([_video(vid='v9')]))
    assert out['token'] is None and out['resultados'][0]['id'] == 'v9'
    assert parsear_yt_mas({}) == {'resultados': [], 'token': None}
    assert parsear_yt_mas(None) == {'resultados': [], 'token': None}


def test_youtube_mas_respeta_max_n():
    from plotspace.core.web_search import parsear_yt_mas
    out = parsear_yt_mas(_respuesta_continuacion(
        [_video(vid=f'v{i}') for i in range(30)]), max_n=6)
    assert len(out['resultados']) == 6


def test_buscar_youtube_mas_valida_el_token():
    from plotspace.core.web_search import buscar_youtube_mas
    for malo in ('', '   ', 'x', 'token con espacios', 'a' * 5000, 'tok<script>'):
        with pytest.raises(BusquedaError):
            asyncio.run(buscar_youtube_mas(malo))


# ─── parsear_yt_relacionados (respuesta de youtubei/v1/next) ──────────────────
# Los relacionados REALES de un video (la Radio los usa como continuaciones):
# el fixture replica la forma verificada 2026-07-11 — playerOverlayAutoplayRenderer
# (el video que YouTube autoplayearía, SIN duración ni thumb) + la pared de
# endScreenVideoRenderer (12 sugeridos, con duración/vistas/thumb).

def _autoplay(vid='next1', titulo='Tema Siguiente', canal='Canal X'):
    return {'videoId': vid, 'videoTitle': {'simpleText': titulo},
            'byline': {'runs': [{'text': canal}]},
            'shortViewCountText': {'simpleText': '66 M de vistas'}}


def _endscreen(vid='sug1', titulo='Sugerido', canal='Canal Y', dur='6:17'):
    return {'videoId': vid, 'title': {'simpleText': titulo},
            'shortBylineText': {'runs': [{'text': canal}]},
            'lengthText': {'simpleText': dur},
            'shortViewCountText': {'simpleText': '1,2 M de vistas'},
            'thumbnail': {'thumbnails': [
                {'url': f'https://i.ytimg.com/vi/{vid}/default.jpg'},
                {'url': f'https://i.ytimg.com/vi/{vid}/hqdefault.jpg'},
            ]}}


def _next_data(autoplay=None, endscreen=()):
    """Arma una respuesta de youtubei/v1/next con los renderers anidados donde
    los deja YouTube (autoplay bajo playerOverlays, endscreen bajo endscreen)."""
    return {
        'playerOverlays': {'playerOverlayRenderer': {'autoplay': {
            'playerOverlayAutoplayRenderer': autoplay} if autoplay else {}}},
        'endscreen': {'endscreenRenderer': {'elements': [
            {'endscreenElementRenderer': {'endScreenVideoRenderer': e}}
            for e in endscreen]}},
    }


def test_relacionados_autoplay_primero_y_endscreen_despues():
    data = _next_data(autoplay=_autoplay(), endscreen=[_endscreen()])
    res = parsear_yt_relacionados(data)
    assert [r['id'] for r in res] == ['next1', 'sug1']
    assert res[0]['titulo'] == 'Tema Siguiente'
    assert res[0]['canal'] == 'Canal X'
    assert res[0]['url'] == 'https://www.youtube.com/watch?v=next1'
    assert res[1] == {
        'id': 'sug1', 'url': 'https://www.youtube.com/watch?v=sug1',
        'titulo': 'Sugerido', 'canal': 'Canal Y', 'duracion': '6:17',
        'vistas': '1,2 M de vistas',
        'thumb': 'https://i.ytimg.com/vi/sug1/hqdefault.jpg',  # la más grande
    }


def test_relacionados_autoplay_duplicado_se_completa_con_el_endscreen():
    # El video del autoplay suele repetirse en el endscreen: queda UNA entrada
    # (primera posición) con la duración/thumb que el autoplay no trae.
    data = _next_data(autoplay=_autoplay(vid='dup'),
                      endscreen=[_endscreen(vid='dup', dur='4:05'), _endscreen(vid='otro')])
    res = parsear_yt_relacionados(data)
    assert [r['id'] for r in res] == ['dup', 'otro']
    assert res[0]['titulo'] == 'Tema Siguiente'      # gana el del autoplay
    assert res[0]['duracion'] == '4:05'              # completado por el endscreen
    assert res[0]['thumb'] == 'https://i.ytimg.com/vi/dup/hqdefault.jpg'


def test_relacionados_respeta_max_y_tolera_basura():
    data = _next_data(endscreen=[_endscreen(vid=f'v{i}') for i in range(15)])
    assert len(parsear_yt_relacionados(data, max_n=5)) == 5
    assert parsear_yt_relacionados({}) == []
    assert parsear_yt_relacionados(None) == []
    assert parsear_yt_relacionados({'endscreen': {'x': [{'endScreenVideoRenderer': {}}]}}) == []


def test_relacionados_youtube_valida_el_id():
    from plotspace.core.web_search import relacionados_youtube
    for malo in ('', '   ', 'javascript:x', 'a b c', 'x' * 30):
        with pytest.raises(BusquedaError):
            asyncio.run(relacionados_youtube(malo))


# ─── endpoint /preview/buscar (validación + ruteo por modo) ───────────────────

def test_endpoint_valida_parametros(monkeypatch):
    from fastapi import HTTPException
    from plotspace.routers.orchestrator import preview_buscar

    # 'web' y 'twitch' eran modos VÁLIDOS hasta 2026-07-26 (buscador viejo);
    # ahora el endpoint es exclusivamente de YouTube y deben dar 400.
    for kwargs in ({'q': ''}, {'q': '   '}, {'q': 'x' * 201}, {'q': 'ok', 'modo': 'bing'},
                   {'q': 'ok', 'modo': 'web'}, {'q': 'ok', 'modo': 'twitch'}):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(preview_buscar(**kwargs))
        assert exc.value.status_code == 400


def test_endpoint_rutea_por_modo(monkeypatch):
    from plotspace.core import web_search
    from plotspace.routers.orchestrator import preview_buscar

    async def _yt(q, max_n=18):
        return {'resultados': [{'id': 'v', 'titulo': f'yt:{q}'}], 'token': None}

    async def _rel(video_id, max_n=18):
        return [{'id': 'r', 'titulo': f'rel:{video_id}'}]

    async def _ident(rs):
        return rs   # el filtro de embebibles se testea aparte; acá se prueba el RUTEO

    monkeypatch.setattr(web_search, 'buscar_youtube_pagina', _yt)
    monkeypatch.setattr(web_search, 'relacionados_youtube', _rel)
    monkeypatch.setattr(web_search, 'filtrar_embebibles', _ident)

    r = asyncio.run(preview_buscar(q='lofi', modo='yt'))
    assert r['error'] is None
    assert r['resultados'][0]['titulo'] == 'yt:lofi'
    r = asyncio.run(preview_buscar(q='abc123def45', modo='ytrel'))
    assert r['resultados'][0]['titulo'] == 'rel:abc123def45'


def test_endpoint_yt_devuelve_el_token_de_continuacion(monkeypatch):
    """modo=yt viaja con el token de "mostrar más" para que la Radio pueda
    pedir la tanda siguiente sin re-buscar."""
    from plotspace.core import web_search
    from plotspace.routers.orchestrator import preview_buscar

    async def _pag(q, max_n=18):
        return {'resultados': [{'id': 'v1', 'titulo': f'yt:{q}'}], 'token': 'TOK2'}

    async def _ident(rs):
        return rs

    monkeypatch.setattr(web_search, 'buscar_youtube_pagina', _pag)
    monkeypatch.setattr(web_search, 'filtrar_embebibles', _ident)
    r = asyncio.run(preview_buscar(q='michael jackson', modo='yt'))
    assert r['resultados'][0]['id'] == 'v1' and r['token'] == 'TOK2'


def test_endpoint_ytmas_continua_con_el_token(monkeypatch):
    from plotspace.core import web_search
    from plotspace.routers.orchestrator import preview_buscar

    vistos = {}

    async def _mas(token, max_n=18):
        vistos['token'] = token
        return {'resultados': [{'id': 'v2'}], 'token': 'TOK3'}

    async def _ident(rs):
        return rs

    monkeypatch.setattr(web_search, 'buscar_youtube_mas', _mas)
    monkeypatch.setattr(web_search, 'filtrar_embebibles', _ident)
    r = asyncio.run(preview_buscar(modo='ytmas', token='TOK2'))
    assert vistos['token'] == 'TOK2'
    assert r['resultados'][0]['id'] == 'v2' and r['token'] == 'TOK3'


def test_endpoint_ytmas_exige_token_y_lo_acota():
    from fastapi import HTTPException
    from plotspace.routers.orchestrator import preview_buscar

    for kwargs in ({'modo': 'ytmas'}, {'modo': 'ytmas', 'token': '  '},
                   {'modo': 'ytmas', 'token': 'x' * 4001}):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(preview_buscar(**kwargs))
        assert exc.value.status_code == 400


def test_endpoint_convierte_busquedaerror_en_error_legible(monkeypatch):
    from plotspace.core import web_search
    from plotspace.routers.orchestrator import preview_buscar

    async def _explota(q, max_n=18):
        raise BusquedaError('la búsqueda no respondió')

    monkeypatch.setattr(web_search, 'buscar_youtube_pagina', _explota)
    r = asyncio.run(preview_buscar(q='gatos', modo='yt'))
    assert r['resultados'] == []
    assert 'no respondió' in r['error']


# ─── Filtro "solo embebibles" (parte pura) ───────────────────────────────────

def test_filtro_embebibles_conserva_y_descarta():
    from plotspace.core.web_search import aplicar_filtro_embebibles
    videos = [
        {'id': 'a', 'titulo': 'embebible'},
        {'id': 'b', 'titulo': 'bloqueado por VEVO'},
        {'id': 'c', 'titulo': 'sin veredicto (red)'},
        {'titulo': 'sin id'},
    ]
    out = aplicar_filtro_embebibles(videos, {'a': True, 'b': False})
    # 'b' afuera; 'c' (sin veredicto) y el sin-id se CONSERVAN (no sobre-filtrar)
    assert [v['titulo'] for v in out] == ['embebible', 'sin veredicto (red)', 'sin id']


def test_filtro_embebibles_bordes():
    from plotspace.core.web_search import aplicar_filtro_embebibles
    assert aplicar_filtro_embebibles([], {}) == []
    assert aplicar_filtro_embebibles(None, {}) == []
    todos_bloqueados = [{'id': 'x'}, {'id': 'y'}]
    assert aplicar_filtro_embebibles(todos_bloqueados, {'x': False, 'y': False}) == []
