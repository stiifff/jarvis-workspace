"""Tests de las funciones puras de mobile_preview (sin tmux ni red)."""
import json
import os

import plotspace.routers.mobile_preview as mp
from plotspace.routers.mobile_preview import (
    _encontrar_app_expo,
    _es_proyecto_expo,
    _api_url_de_env,
    _cors_permite,
    _entrada_fresca,
    _ruta_app_expo_cached,
    _invalidar_cache_ruta,
    _escanear_panes_expo,
    _probar_url_expo,
    _puertos_candidatos,
    _puerto_de_url,
    _aplicar_patch_texto,
)


def _crear_proyecto(tmp_path, con_app_json=True, con_dep_expo=True,
                    config='app.json', con_package=True):
    if con_app_json:
        (tmp_path / config).write_text('{}', encoding='utf-8')
    if con_package:
        deps = {'expo': '~52.0.0'} if con_dep_expo else {'react': '18.0.0'}
        (tmp_path / 'package.json').write_text(
            json.dumps({'dependencies': deps}), encoding='utf-8')
    return str(tmp_path)


def test_es_expo_con_app_json_y_dep(tmp_path):
    assert _es_proyecto_expo(_crear_proyecto(tmp_path)) is True


def test_es_expo_con_app_config_js(tmp_path):
    assert _es_proyecto_expo(_crear_proyecto(tmp_path, config='app.config.js')) is True


def test_no_es_expo_sin_dep(tmp_path):
    assert _es_proyecto_expo(_crear_proyecto(tmp_path, con_dep_expo=False)) is False


def test_no_es_expo_sin_config(tmp_path):
    assert _es_proyecto_expo(_crear_proyecto(tmp_path, con_app_json=False)) is False


def test_no_es_expo_sin_package_json(tmp_path):
    assert _es_proyecto_expo(_crear_proyecto(tmp_path, con_package=False)) is False


def test_es_expo_dep_en_devdependencies(tmp_path):
    (tmp_path / 'app.json').write_text('{}', encoding='utf-8')
    (tmp_path / 'package.json').write_text(
        json.dumps({'devDependencies': {'expo': '~52.0.0'}}), encoding='utf-8')
    assert _es_proyecto_expo(str(tmp_path)) is True


def test_no_es_expo_package_json_roto(tmp_path):
    (tmp_path / 'app.json').write_text('{}', encoding='utf-8')
    (tmp_path / 'package.json').write_text('{esto no es json', encoding='utf-8')
    assert _es_proyecto_expo(str(tmp_path)) is False


def test_no_es_expo_ruta_inexistente():
    assert _es_proyecto_expo('/ruta/que/no/existe') is False
    assert _es_proyecto_expo('') is False


def test_no_es_expo_dependencies_no_dict(tmp_path):
    (tmp_path / 'app.json').write_text('{}', encoding='utf-8')
    (tmp_path / 'package.json').write_text(
        '{"dependencies": ["expo"]}', encoding='utf-8')
    assert _es_proyecto_expo(str(tmp_path)) is False


# ─── _encontrar_app_expo: la app puede vivir en una subcarpeta ────────────────

def test_encontrar_app_en_raiz(tmp_path):
    _crear_proyecto(tmp_path)
    assert _encontrar_app_expo(str(tmp_path)) == str(tmp_path)


def test_encontrar_app_en_subcarpeta(tmp_path):
    # Proyecto tipo "fintech test": la raíz no es Expo, la app vive en mobile/
    (tmp_path / 'backend').mkdir()
    sub = tmp_path / 'mobile'
    sub.mkdir()
    _crear_proyecto(sub)
    assert _encontrar_app_expo(str(tmp_path)) == str(sub)


def test_encontrar_app_anidada_dos_niveles(tmp_path):
    sub = tmp_path / 'apps' / 'movil'
    sub.mkdir(parents=True)
    _crear_proyecto(sub)
    assert _encontrar_app_expo(str(tmp_path)) == str(sub)


def test_encontrar_prefiere_la_raiz_sobre_subcarpetas(tmp_path):
    _crear_proyecto(tmp_path)
    sub = tmp_path / 'otra-app'
    sub.mkdir()
    _crear_proyecto(sub)
    assert _encontrar_app_expo(str(tmp_path)) == str(tmp_path)


def test_encontrar_sin_app_devuelve_none(tmp_path):
    (tmp_path / 'src').mkdir()
    (tmp_path / 'README.md').write_text('hola', encoding='utf-8')
    assert _encontrar_app_expo(str(tmp_path)) is None


def test_encontrar_ignora_node_modules_y_ocultas(tmp_path):
    # Un paquete con pinta de Expo adentro de node_modules o .git NO cuenta.
    for carpeta in ('node_modules/expo-app', '.git/fake'):
        sub = tmp_path / carpeta
        sub.mkdir(parents=True)
        _crear_proyecto(sub)
    assert _encontrar_app_expo(str(tmp_path)) is None


def test_encontrar_respeta_profundidad_maxima(tmp_path):
    sub = tmp_path / 'a' / 'b' / 'c' / 'd' / 'e'
    sub.mkdir(parents=True)
    _crear_proyecto(sub)
    assert _encontrar_app_expo(str(tmp_path), max_depth=2) is None
    assert _encontrar_app_expo(str(tmp_path), max_depth=5) == str(sub)


def test_encontrar_ruta_inexistente_devuelve_none():
    assert _encontrar_app_expo('/ruta/que/no/existe') is None
    assert _encontrar_app_expo('') is None
    assert _encontrar_app_expo(None) is None


# ─── _api_url_de_env: EXPO_PUBLIC_API_URL del .env de la app ──────────────────

def test_api_url_de_env_la_extrae():
    env = ('# Mobile dev env\n\n'
           'EXPO_PUBLIC_API_URL=https://testapp-n8m8.onrender.com/api/v1\n'
           'EXPO_PUBLIC_APP_NAME=RemesasPY\n')
    assert _api_url_de_env(env) == 'https://testapp-n8m8.onrender.com/api/v1'


def test_api_url_de_env_con_comillas_y_espacios():
    assert _api_url_de_env('EXPO_PUBLIC_API_URL = "http://10.0.0.5:4000" \n') == 'http://10.0.0.5:4000'


def test_api_url_de_env_ignora_comentarios_y_ausente():
    assert _api_url_de_env('# EXPO_PUBLIC_API_URL=https://comentada.com\n') is None
    assert _api_url_de_env('OTRA_VAR=1\n') is None
    assert _api_url_de_env('') is None
    assert _api_url_de_env(None) is None


# ─── _cors_permite: ¿la respuesta del preflight habilita al origen? ───────────

def test_cors_permite_origen_exacto_o_wildcard():
    assert _cors_permite('http://localhost:8218', 'http://localhost:8218') is True
    assert _cors_permite('*', 'http://localhost:8218') is True


def test_cors_no_permite_sin_header_u_otro_origen():
    assert _cors_permite(None, 'http://localhost:8218') is False
    assert _cors_permite('', 'http://localhost:8218') is False
    assert _cors_permite('https://app.midominio.com', 'http://localhost:8218') is False


def _api_ngrok(*tunnels):
    return {'tunnels': [
        {'public_url': u, 'config': {'addr': f'http://localhost:{p}'}}
        for u, p in tunnels]}


# ─── _entrada_fresca (TTL genérico de caches y marcadores) ────────────────────

def test_entrada_fresca_dentro_de_ttl():
    assert _entrada_fresca(100.0, ahora=159.0, ttl=60) is True


def test_entrada_fresca_justo_en_el_borde_ya_expiro():
    # ahora - ts == ttl → expirada (estricto <).
    assert _entrada_fresca(100.0, ahora=160.0, ttl=60) is False


def test_entrada_fresca_expirada():
    assert _entrada_fresca(100.0, ahora=200.0, ttl=60) is False


def test_entrada_fresca_none_nunca_es_fresca():
    assert _entrada_fresca(None, ahora=100.0, ttl=60) is False


# ─── _ruta_app_expo_cached (cache TTL del BFS de disco) ───────────────────────

def _stub_clock(monkeypatch, valor):
    """Reemplaza time.monotonic en el módulo por un reloj controlable.
    Devuelve una lista de 1 elemento que el test puede mutar para avanzar."""
    caja = [valor]
    monkeypatch.setattr(mp.time, 'monotonic', lambda: caja[0])
    return caja


def test_ruta_app_expo_cacheada_evita_segundo_bfs(monkeypatch):
    llamadas = []
    monkeypatch.setattr(mp, '_cache_ruta_app', {}, raising=False)
    monkeypatch.setattr(mp, '_ruta_app_expo',
                        lambda pid: (llamadas.append(pid), '/fake/app')[1])
    _stub_clock(monkeypatch, 1000.0)
    assert _ruta_app_expo_cached(7) == '/fake/app'
    assert _ruta_app_expo_cached(7) == '/fake/app'
    assert llamadas == [7]  # el BFS de disco corrió UNA sola vez


def test_ruta_app_expo_cache_distingue_proyectos(monkeypatch):
    monkeypatch.setattr(mp, '_cache_ruta_app', {}, raising=False)
    monkeypatch.setattr(mp, '_ruta_app_expo', lambda pid: f'/app/{pid}')
    _stub_clock(monkeypatch, 1000.0)
    assert _ruta_app_expo_cached(1) == '/app/1'
    assert _ruta_app_expo_cached(2) == '/app/2'


def test_ruta_app_expo_cache_expira_y_rescannea(monkeypatch):
    llamadas = []
    monkeypatch.setattr(mp, '_cache_ruta_app', {}, raising=False)
    monkeypatch.setattr(mp, '_ruta_app_expo',
                        lambda pid: (llamadas.append(pid), '/fake/app')[1])
    reloj = _stub_clock(monkeypatch, 1000.0)
    _ruta_app_expo_cached(7)
    reloj[0] = 1000.0 + mp._CACHE_RUTA_TTL + 1  # más allá del TTL
    _ruta_app_expo_cached(7)
    assert llamadas == [7, 7]  # re-escaneó tras expirar


def test_ruta_app_expo_cachea_none(monkeypatch):
    # Un proyecto sin app Expo (None) también se cachea: no re-escanear disco
    # cada 3s en proyectos que nunca van a tener app.
    llamadas = []
    monkeypatch.setattr(mp, '_cache_ruta_app', {}, raising=False)
    monkeypatch.setattr(mp, '_ruta_app_expo',
                        lambda pid: (llamadas.append(pid), None)[1])
    _stub_clock(monkeypatch, 1000.0)
    assert _ruta_app_expo_cached(9) is None
    assert _ruta_app_expo_cached(9) is None
    assert llamadas == [9]


def test_invalidar_cache_ruta_fuerza_rescan(monkeypatch):
    llamadas = []
    monkeypatch.setattr(mp, '_cache_ruta_app', {}, raising=False)
    monkeypatch.setattr(mp, '_ruta_app_expo',
                        lambda pid: (llamadas.append(pid), '/fake/app')[1])
    _stub_clock(monkeypatch, 1000.0)
    _ruta_app_expo_cached(7)
    _invalidar_cache_ruta(7)
    _ruta_app_expo_cached(7)
    assert llamadas == [7, 7]


# ─── Detección del Expo en las terminales (el panel NO arranca Metro) ─────────

def test_escanear_panes_detecta_web():
    # Pane con la URL del dev server web de Expo; el probe la marca 'web'.
    panes = ['› Web is waiting on http://localhost:8081\nMetro v0.81']
    res = _escanear_panes_expo(panes, lambda u: 'web')
    assert res == {'url': 'http://localhost:8081/', 'web': True, 'nativo': False}


def test_escanear_panes_solo_metro_nativo():
    # Metro corriendo pero sin --web → el probe responde 'metro' (no HTML).
    panes = ['Metro waiting on http://localhost:8081']
    res = _escanear_panes_expo(panes, lambda u: 'metro')
    assert res == {'url': None, 'web': False, 'nativo': True}


def test_escanear_panes_sin_servidor():
    res = _escanear_panes_expo(['compilando…\nsin urls', ''], lambda u: None)
    assert res == {'url': None, 'web': False, 'nativo': False}


def test_escanear_panes_prefiere_web_sobre_metro():
    # Pane 1 tiene un Metro nativo; pane 2 el web → gana el web.
    panes = ['Metro on http://localhost:8081',
             'Web is waiting on http://localhost:8082']
    probar = lambda u: 'web' if '8082' in u else 'metro'
    res = _escanear_panes_expo(panes, probar)
    assert res['url'] == 'http://localhost:8082/' and res['web'] is True


def test_escanear_panes_ignora_jarvis_3000():
    # El :3000 (Jarvis) lo excluye extraer_urls_locales → el probe nunca se llama.
    llamadas = []
    _escanear_panes_expo(['corriendo en http://localhost:3000/'],
                         lambda u: llamadas.append(u) or 'web')
    assert llamadas == []


def test_probar_url_expo_clasifica(monkeypatch):
    import urllib.request

    class _Resp:
        def __init__(self, ctype, body):
            self.headers = {'Content-Type': ctype}
            self._b = body.encode()
        def read(self, n=-1): return self._b
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake(resp):
        monkeypatch.setattr(urllib.request, 'urlopen', lambda *a, **k: resp)

    fake(_Resp('text/html; charset=utf-8', '<!DOCTYPE html><html></html>'))
    assert _probar_url_expo('http://localhost:8081/') == 'web'

    fake(_Resp('application/json', '{"name":"main"}'))
    assert _probar_url_expo('http://localhost:8081/') == 'metro'

    # HTML detectado por el cuerpo aunque el content-type no lo diga
    fake(_Resp('text/plain', 'preludio <html lang="en">'))
    assert _probar_url_expo('http://localhost:8081/') == 'web'

    def boom(*a, **k): raise OSError('connection refused')
    monkeypatch.setattr(urllib.request, 'urlopen', boom)
    assert _probar_url_expo('http://localhost:9999/') is None


# ─── _puertos_candidatos: saca el puerto del Expo aunque solo haya túnel ──────

def test_puertos_desde_http_local():
    assert _puertos_candidatos('Web is waiting on http://localhost:8081') == [8081]


def test_puertos_desde_tunnel_exp_direct():
    # Caso real: con --tunnel el pane solo muestra exp://…-PORT.exp.direct
    txt = '> Metro waiting on exp://example-8081.exp.direct\n> scan QR'
    assert _puertos_candidatos(txt) == [8081]


def test_puertos_desde_exp_lan():
    assert _puertos_candidatos('exp://192.168.0.10:8082') == [8082]


def test_puertos_excluye_jarvis_3000():
    assert _puertos_candidatos('corriendo en http://localhost:3000/') == []


def test_puertos_excluye_inspector_ngrok_4040():
    # Con --tunnel el inspector de ngrok (http://localhost:4040) sirve HTML; no
    # debe confundirse con el web de Expo. Solo queda el 8081 real.
    txt = ('Web is waiting on http://localhost:8081\n'
           'ngrok web interface http://localhost:4040')
    assert _puertos_candidatos(txt) == [8081]


def test_puertos_mas_reciente_primero():
    # 8207 (viejo, arriba) y 8081 (repetido, más abajo/reciente) → 8081 primero.
    txt = ('exp://x-8207.exp.direct\nalgo\n'
           'exp://x-8081.exp.direct\nmás\nexp://x-8081.exp.direct')
    assert _puertos_candidatos(txt) == [8081, 8207]


def test_escanear_detecta_web_por_tunnel():
    # El pane solo tiene el túnel; igual hay que detectar el :8081 y sondearlo.
    panes = ['Metro waiting on exp://example-8081.exp.direct']
    res = _escanear_panes_expo(panes, lambda u: 'web' if '8081' in u else None)
    assert res == {'url': 'http://localhost:8081/', 'web': True, 'nativo': False}


def test_puerto_de_url():
    assert _puerto_de_url('http://localhost:8081/') == 8081
    assert _puerto_de_url('http://localhost:8082') == 8082
    assert _puerto_de_url('http://localhost/') is None


def test_detectar_pegajoso_reusa_puerto_recordado(monkeypatch):
    # Una vez detectado :8081, lo sigue mostrando re-sondeando ese puerto aunque
    # el pane ya no tenga la URL (se fue del scrollback).
    monkeypatch.setattr(mp, '_ultimo_puerto', {7: 8081}, raising=False)
    monkeypatch.setattr(mp, '_probar_url_expo', lambda u, **k: 'web' if '8081' in u else None)
    # _capturar_pane_terminal no debería ni hace falta (corta en el paso 1):
    monkeypatch.setattr(mp, '_capturar_pane_terminal', lambda tid: (_ for _ in ()).throw(AssertionError('no debería escanear panes')))
    monkeypatch.setattr(mp, 'get_db', lambda: (_ for _ in ()).throw(AssertionError('no DB')))
    assert mp._detectar_expo_en_terminales(7) == {'url': 'http://localhost:8081/', 'web': True, 'nativo': False}


def test_detectar_olvida_puerto_muerto(monkeypatch):
    # El puerto recordado ya no sirve y no hay nada en los panes → se olvida.
    cache = {7: 8081}
    monkeypatch.setattr(mp, '_ultimo_puerto', cache, raising=False)
    monkeypatch.setattr(mp, '_probar_url_expo', lambda u, **k: None)  # nada responde
    monkeypatch.setattr(mp, '_capturar_pane_terminal', lambda tid: 'compilando…')

    class _Cur:
        def execute(self, *a): return self
        def fetchall(self): return []
    class _Conn:
        def cursor(self): return _Cur()
        def close(self): pass
    monkeypatch.setattr(mp, 'get_db', lambda: _Conn())
    res = mp._detectar_expo_en_terminales(7)
    assert res == {'url': None, 'web': False, 'nativo': False}
    assert 7 not in cache, 'el puerto muerto se olvidó'


# ─── Fallback a puertos default de Expo cuando el pane no tiene URL parseable ──
# (root cause real 2026-06-18: la URL se va del scrollback / queda wrapeada, y la
#  detección quedaba null aunque :8081 sirviera web).

def test_escanear_fallback_a_puertos_default():
    probar = lambda u, **k: 'web' if ':8081/' in u else None
    r = mp._escanear_panes_expo(['Web Bundled 200ms entry.js', 'ruido'],
                                probar, puertos_extra=[8081, 8082])
    assert r == {'url': 'http://localhost:8081/', 'web': True, 'nativo': False}

def test_escanear_pane_tiene_prioridad_sobre_default():
    probar = lambda u, **k: 'web'   # todo responde web
    r = mp._escanear_panes_expo(['http://localhost:5000/'], probar, puertos_extra=[8081])
    assert r['url'] == 'http://localhost:5000/'   # el del pane gana

def test_escanear_sin_extra_ni_panes():
    assert mp._escanear_panes_expo(['nada'], lambda u, **k: None) == \
        {'url': None, 'web': False, 'nativo': False}

def test_panes_muestran_expo():
    assert mp._panes_muestran_expo(['x Web Bundled 528ms node_modules/expo-router/entry.js']) is True
    assert mp._panes_muestran_expo(['Metro waiting on exp://abc-8081.exp.direct']) is True
    assert mp._panes_muestran_expo(['un dev server de vite en :5173']) is False
    assert mp._panes_muestran_expo(['']) is False
    assert mp._panes_muestran_expo([]) is False


# ─── _aplicar_patch_texto: editar el CÓDIGO REAL desde el inspector ───────────

def _tsx(tmp_path, contenido, nombre='App.tsx'):
    """Crea un archivo fuente dentro de un dir-app y devuelve (app_dir, rel)."""
    (tmp_path / nombre).write_text(contenido, encoding='utf-8')
    return str(tmp_path), nombre


def test_patch_reemplaza_jsx_text(tmp_path):
    app, rel = _tsx(tmp_path, '<Text>Buen día,</Text>\n')
    res = _aplicar_patch_texto(app, rel, 1, 'Buen día,', 'Buenas tardes,')
    assert res['ok'] is True
    assert (tmp_path / rel).read_text(encoding='utf-8') == '<Text>Buenas tardes,</Text>\n'


def test_patch_reemplaza_literal_entre_comillas(tmp_path):
    app, rel = _tsx(tmp_path, 'const t = "Calorías";\n')
    res = _aplicar_patch_texto(app, rel, 1, 'Calorías', 'Kcal')
    assert res['ok'] is True
    assert 'const t = "Kcal";' in (tmp_path / rel).read_text(encoding='utf-8')


def test_patch_busca_en_lineas_cercanas(tmp_path):
    # __source a veces apunta a la línea de apertura del elemento
    app, rel = _tsx(tmp_path, '<Text\n  style={s}>\n  Hola\n</Text>\n')
    res = _aplicar_patch_texto(app, rel, 1, 'Hola', 'Chau')  # línea real es la 3
    assert res['ok'] is True
    assert 'Chau' in (tmp_path / rel).read_text(encoding='utf-8')


def test_patch_no_edita_codigo(tmp_path):
    # el "texto" tiene llaves → es una expresión, no un literal simple
    app, rel = _tsx(tmp_path, '<Text>{user.name}</Text>\n')
    res = _aplicar_patch_texto(app, rel, 1, '{user.name}', 'Pepe')
    assert res['ok'] is False


def test_patch_no_edita_si_new_trae_jsx(tmp_path):
    app, rel = _tsx(tmp_path, '<Text>Hola</Text>\n')
    res = _aplicar_patch_texto(app, rel, 1, 'Hola', '<b>Hola</b>')
    assert res['ok'] is False
    assert (tmp_path / rel).read_text(encoding='utf-8') == '<Text>Hola</Text>\n'


def test_patch_texto_ambiguo_en_la_linea(tmp_path):
    app, rel = _tsx(tmp_path, '<View>Hola Hola</View>\n')
    res = _aplicar_patch_texto(app, rel, 1, 'Hola', 'Chau')
    assert res['ok'] is False
    assert 'ambiguo' in res['error']


def test_patch_no_encuentra_texto(tmp_path):
    app, rel = _tsx(tmp_path, '<Text>Hola</Text>\n')
    res = _aplicar_patch_texto(app, rel, 1, 'Adiós', 'Chau')
    assert res['ok'] is False


def test_patch_rechaza_ruta_fuera_del_proyecto(tmp_path):
    (tmp_path / 'App.tsx').write_text('<Text>Hola</Text>\n', encoding='utf-8')
    res = _aplicar_patch_texto(str(tmp_path), '../secretos.tsx', 1, 'Hola', 'Chau')
    assert res['ok'] is False
    assert 'proyecto' in res['error']


def test_patch_rechaza_extension_no_fuente(tmp_path):
    (tmp_path / 'notas.txt').write_text('Hola\n', encoding='utf-8')
    res = _aplicar_patch_texto(str(tmp_path), 'notas.txt', 1, 'Hola', 'Chau')
    assert res['ok'] is False


def test_patch_rechaza_new_que_rompe_comillas(tmp_path):
    app, rel = _tsx(tmp_path, "const t = 'de Ana';\n")
    res = _aplicar_patch_texto(app, rel, 1, 'de Ana', "d'Ana")
    assert res['ok'] is False
    assert 'comillas' in res['error']


def test_patch_sin_cambios_es_noop(tmp_path):
    app, rel = _tsx(tmp_path, '<Text>Hola</Text>\n')
    res = _aplicar_patch_texto(app, rel, 1, 'Hola', 'Hola')
    assert res['ok'] is False


def test_patch_fileName_absoluto_dentro_del_proyecto(tmp_path):
    # __source.fileName suele ser absoluto; debe resolver igual si está adentro
    app, rel = _tsx(tmp_path, '<Text>Hola</Text>\n')
    absoluto = os.path.join(app, rel)
    res = _aplicar_patch_texto(app, absoluto, 1, 'Hola', 'Chau')
    assert res['ok'] is True
    assert 'Chau' in (tmp_path / rel).read_text(encoding='utf-8')


# ─── Heurística de textos editables (copy de UI vs dato/técnico) ──────────────

from plotspace.routers.mobile_preview import (
    _es_texto_dinamico, _es_texto_editable, _extraer_textos_de_linea,
    _localizar_texto, _escanear_textos_editables,
)


def test_dinamico_detecta_datos():
    assert _es_texto_dinamico('642 kcal') is True       # dígitos
    assert _es_texto_dinamico('ana@mail.com') is True   # email
    assert _es_texto_dinamico('https://x.com') is True  # url
    assert _es_texto_dinamico('Hoy · 18 min') is True   # fecha/hora + dígito
    assert _es_texto_dinamico('Calorías') is False      # copy puro


def test_editable_acepta_copy_de_ui():
    assert _es_texto_editable('Buen día,') is True
    assert _es_texto_editable('Calorías') is True
    assert _es_texto_editable('Perfil') is True          # una palabra capitalizada
    assert _es_texto_editable('Iniciar sesión') is True


def test_editable_rechaza_datos_y_tecnico():
    assert _es_texto_editable('642') is False            # dato
    assert _es_texto_editable('camila@x.com') is False   # email
    assert _es_texto_editable('center') is False         # valor de estilo (1 palabra minúsc)
    assert _es_texto_editable('flexStart') is False      # identificador
    assert _es_texto_editable('#ff0066') is False        # color
    assert _es_texto_editable('./screens/Home') is False # path
    assert _es_texto_editable('react-native') is False   # tiene guion pero… (import-like)
    assert _es_texto_editable('a') is False              # muy corto
    assert _es_texto_editable('{user.name}') is False    # expresión


def test_extraer_textos_de_linea():
    ts = _extraer_textos_de_linea('<Text style={s}>Buen día,</Text>')
    assert 'Buen día,' in ts
    ts2 = _extraer_textos_de_linea('const t = "Calorías";')
    assert 'Calorías' in ts2


def _mk_app(tmp_path, archivos):
    for rel, contenido in archivos.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(contenido, encoding='utf-8')
    return str(tmp_path)


def test_localizar_texto_unico(tmp_path):
    app = _mk_app(tmp_path, {'App.tsx': '<Text>Bienvenido</Text>\n'})
    m = _localizar_texto(app, 'Bienvenido')
    assert len(m) == 1
    assert m[0]['file'] == 'App.tsx' and m[0]['line'] == 1


def test_localizar_texto_multiple(tmp_path):
    app = _mk_app(tmp_path, {
        'A.tsx': '<Text>Guardar</Text>\n',
        'B.tsx': 'x\n<Text>Guardar</Text>\n',
    })
    m = _localizar_texto(app, 'Guardar')
    assert len(m) == 2


def test_localizar_ignora_node_modules(tmp_path):
    app = _mk_app(tmp_path, {
        'App.tsx': '<Text>Hola</Text>\n',
        'node_modules/pkg/index.tsx': '<Text>Hola</Text>\n',
    })
    m = _localizar_texto(app, 'Hola')
    assert len(m) == 1  # el de node_modules NO cuenta


def test_escanear_textos_editables(tmp_path):
    app = _mk_app(tmp_path, {
        'Home.tsx': ('<View>\n  <Text>Buen día,</Text>\n'
                     '  <Text>642 kcal</Text>\n'         # dinámico → fuera
                     '  <Text>Calorías</Text>\n</View>\n'),
    })
    textos = _escanear_textos_editables(app)
    vals = {t['text'] for t in textos}
    assert 'Buen día,' in vals
    assert 'Calorías' in vals
    assert '642 kcal' not in vals           # dato dinámico excluido
    # cada uno con su línea correcta
    porlinea = {t['text']: t['line'] for t in textos}
    assert porlinea['Buen día,'] == 2
    assert porlinea['Calorías'] == 4


def test_escanear_dedup_por_texto(tmp_path):
    app = _mk_app(tmp_path, {
        'A.tsx': '<Text>Guardar</Text>\n',
        'B.tsx': '<Text>Guardar</Text>\n',
    })
    textos = _escanear_textos_editables(app)
    assert sum(1 for t in textos if t['text'] == 'Guardar') == 1  # dedup


def test_escanear_solo_jsx(tmp_path):
    # los .ts (lógica) no se escanean para copy de UI; solo .tsx/.jsx
    app = _mk_app(tmp_path, {'logica.ts': 'const msg = "Bienvenido";\n'})
    textos = _escanear_textos_editables(app)
    assert all(t['text'] != 'Bienvenido' for t in textos)


# ── Sampler de colores (status bar adaptativa) ──────────────────────────────

def test_sampler_url_valida_solo_origen_local():
    from plotspace.routers.mobile_preview import _url_sampler_valida
    assert _url_sampler_valida('http://localhost:8081')
    assert _url_sampler_valida('http://127.0.0.1:5060')
    # /detectar entrega la URL con barra final — VÁLIDA (rechazarla dejaba el
    # sampler en 400 silencioso y las franjas negras para siempre, 2026-07-11)
    assert _url_sampler_valida('http://localhost:8081/')
    # con path/query real NO (debe ser el origen)
    assert not _url_sampler_valida('http://localhost:8081/x?y=1')
    # hosts remotos y esquemas raros NO
    assert not _url_sampler_valida('http://evil.com:8081')
    assert not _url_sampler_valida('https://localhost:8081')  # dev servers locales = http
    assert not _url_sampler_valida('file:///etc/passwd')
    assert not _url_sampler_valida('')
    assert not _url_sampler_valida(None)
    # puertos vedados: Jarvis y el inspector de ngrok
    assert not _url_sampler_valida('http://localhost:3000')
    assert not _url_sampler_valida('http://localhost:4040')


def test_sampler_ruta_valida():
    from plotspace.routers.mobile_preview import _ruta_sampler_valida
    assert _ruta_sampler_valida('/')
    assert _ruta_sampler_valida('/perfil?tab=2')
    assert not _ruta_sampler_valida('')
    assert not _ruta_sampler_valida('perfil')          # sin barra inicial
    assert not _ruta_sampler_valida('//evil.com/x')    # protocol-relative
    assert not _ruta_sampler_valida('/a/../../etc')    # traversal
    assert not _ruta_sampler_valida('/a\\b')
    assert not _ruta_sampler_valida('/' + 'a' * 600)   # larguísima


def test_sampler_inyecta_script_antes_del_base():
    from plotspace.routers.mobile_preview import _inyectar_sampler
    html = '<!doctype html><html><head><title>App</title></head><body></body></html>'
    out = _inyectar_sampler(html, 'http://localhost:8081')
    # base hacia Metro presente, y el script ANTES del base (su src relativo
    # debe resolver contra Jarvis, no contra Metro)
    assert '<base href="http://localhost:8081/">' in out
    i_script = out.index('sampler.js')
    i_base = out.index('<base ')
    assert i_script < i_base
    # queda al comienzo del head, antes del contenido original
    assert out.index('<base ') < out.index('<title>')


def test_sampler_inyecta_con_head_con_atributos_y_sin_head():
    from plotspace.routers.mobile_preview import _inyectar_sampler
    con_attr = _inyectar_sampler('<html><head lang="es"><title>x</title></head></html>', 'http://localhost:8081')
    assert '<head lang="es"><script' in con_attr
    sin_head = _inyectar_sampler('<div>hola</div>', 'http://127.0.0.1:5060')
    assert sin_head.startswith('<script')
    assert '<base href="http://127.0.0.1:5060/">' in sin_head
    assert sin_head.endswith('<div>hola</div>')


def test_asset_url_valida_solo_dev_servers_locales():
    from plotspace.routers.mobile_preview import _url_asset_valida
    # asset real de Metro (fuentes de @expo-google-fonts)
    assert _url_asset_valida('http://localhost:8081/assets/?unstable_path=x%2FOutfit.ttf') == 'http://localhost:8081'
    assert _url_asset_valida('http://127.0.0.1:5060/img.png') == 'http://127.0.0.1:5060'
    assert _url_asset_valida('http://localhost:8081') == 'http://localhost:8081'
    # vedados / inválidos
    assert _url_asset_valida('http://localhost:3000/etc') is None      # Jarvis
    assert _url_asset_valida('http://localhost:4040/x') is None        # ngrok
    assert _url_asset_valida('http://evil.com/x.ttf') is None
    assert _url_asset_valida('https://localhost:8081/x') is None       # dev server = http
    assert _url_asset_valida('http://localhost:8081evil.com/x') is None  # prefijo tramposo
    assert _url_asset_valida('') is None
    assert _url_asset_valida(None) is None
