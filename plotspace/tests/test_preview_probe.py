"""
Tests de la función pura _es_embebible (orchestrator.py): decide si una página
puede embeberse en un <iframe> a partir SOLO de sus headers de respuesta.

Sin red: se le pasan dicts de headers a mano. Corre con:
    source venv/bin/activate && python -m pytest plotspace/tests/test_preview_probe.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plotspace.routers.orchestrator import _es_embebible


def test_xfo_deny_no_embebible():
    embebible, motivo = _es_embebible({'X-Frame-Options': 'DENY'})
    assert embebible is False
    assert motivo  # hay un motivo explicativo


def test_xfo_sameorigin_no_embebible():
    embebible, motivo = _es_embebible({'X-Frame-Options': 'SAMEORIGIN'})
    assert embebible is False
    assert motivo


def test_csp_frame_ancestors_none_no_embebible():
    embebible, motivo = _es_embebible(
        {'Content-Security-Policy': "default-src 'self'; frame-ancestors 'none'"}
    )
    assert embebible is False
    assert motivo


def test_csp_frame_ancestors_wildcard_embebible():
    embebible, motivo = _es_embebible(
        {'Content-Security-Policy': 'frame-ancestors *'}
    )
    assert embebible is True
    assert motivo is None


def test_csp_frame_ancestors_localhost_wildcard_embebible():
    # Twitch refleja el parent en el CSP: `frame-ancestors http://localhost:*
    # https://localhost:*`. Jarvis corre en http://localhost:3000 → SÍ está
    # permitido (localhost con puerto comodín). Antes se marcaba no-embebible
    # y caía al browser remoto de gusto.
    embebible, motivo = _es_embebible(
        {'Content-Security-Policy': 'frame-ancestors http://localhost:* https://localhost:*'}
    )
    assert embebible is True, motivo
    assert motivo is None


def test_csp_frame_ancestors_localhost_puerto_exacto_embebible():
    embebible, _ = _es_embebible(
        {'Content-Security-Policy': 'frame-ancestors http://localhost:3000'}
    )
    assert embebible is True


def test_csp_frame_ancestors_localhost_sin_puerto_no_embebible():
    # `http://localhost` sin puerto = puerto default 80, NO el 3000 de Jarvis.
    embebible, _ = _es_embebible(
        {'Content-Security-Policy': 'frame-ancestors http://localhost'}
    )
    assert embebible is False


def test_csp_frame_ancestors_otro_host_no_embebible():
    embebible, _ = _es_embebible(
        {'Content-Security-Policy': "frame-ancestors https://*.twitch.tv 'self'"}
    )
    assert embebible is False


def test_csp_sin_frame_ancestors_embebible():
    # CSP presente pero sin la directiva de framing: no restringe el embebido.
    embebible, motivo = _es_embebible(
        {'Content-Security-Policy': "default-src 'self'; script-src 'self'"}
    )
    assert embebible is True
    assert motivo is None


def test_sin_headers_embebible():
    embebible, motivo = _es_embebible({})
    assert embebible is True
    assert motivo is None


def test_case_insensitive_header_names():
    # Los servers escriben los headers con mayúsculas variadas.
    embebible, _ = _es_embebible({'x-frame-options': 'deny'})
    assert embebible is False
    embebible, _ = _es_embebible({'CONTENT-SECURITY-POLICY': "frame-ancestors 'none'"})
    assert embebible is False


def test_probe_url_interna_marca_interna():
    # El endpoint marca las URLs bloqueadas por SSRF con `interna: True` —
    # el front decide con eso NO auto-abrir el modo remoto (que también las
    # rechazaría). Sin red: la IP link-local se rechaza antes de todo fetch.
    import asyncio
    from plotspace.routers.orchestrator import probe_embebibilidad
    r = asyncio.run(probe_embebibilidad('http://169.254.169.254/latest'))
    assert r['embebible'] is False
    assert r.get('interna') is True
