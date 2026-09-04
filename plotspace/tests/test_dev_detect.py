"""Tests de la lógica pura de detección de dev servers (plotspace/core/dev_detect.py).

Solo funciones puras: extracción/normalización de URLs del texto de un pane.
Nada de tmux ni red.
"""

import plotspace.core.dev_detect as dd
from plotspace.core.dev_detect import (
    extraer_urls_locales,
    normalizar_url_local,
    parsear_ss_listen,
    proyecto_de_cwd,
    puerto_de,
    puerto_excluido,
)


# ─── normalizar_url_local ──────────────────────────────────────────────────────

def test_normaliza_0000_a_localhost():
    assert normalizar_url_local('http://0.0.0.0:4321/') == 'http://localhost:4321/'


def test_normaliza_127_a_localhost():
    # El MISMO server por 127.0.0.1 y por localhost = una sola entrada/pestaña.
    assert normalizar_url_local('http://127.0.0.1:5541/') == 'http://localhost:5541/'
    assert normalizar_url_local('http://127.0.0.1:3000/static/x/') == 'http://localhost:3000/static/x/'
    assert normalizar_url_local('http://[::1]:5173') == 'http://localhost:5173'


def test_normaliza_no_toca_ip_en_path():
    # count=1: solo la autoridad, no una IP que aparezca en el path.
    assert normalizar_url_local('http://localhost:3000/x/127.0.0.1') == 'http://localhost:3000/x/127.0.0.1'


def test_extraer_urls_dedupea_alias_loopback():
    # Un pane que imprime el server por los dos alias → una sola URL canónica.
    texto = 'Local: http://localhost:5541/  Network: http://127.0.0.1:5541/'
    assert extraer_urls_locales(texto) == ['http://localhost:5541/']


def test_normaliza_puntuacion_final():
    # 'corriendo en http://localhost:8000.' (cierre de oración)
    assert normalizar_url_local('http://localhost:8000.') == 'http://localhost:8000'


def test_normaliza_vacio():
    assert normalizar_url_local('') is None
    assert normalizar_url_local(None) is None


def test_puerto_de():
    assert puerto_de('http://localhost:5173/') == 5173
    assert puerto_de('http://localhost') is None


# ─── extraer_urls_locales ──────────────────────────────────────────────────────

def test_vite_con_ansi():
    pane = (
        '\x1b[32m  VITE v5.2.0\x1b[0m  ready in 311 ms\n\n'
        '\x1b[32m  ➜\x1b[0m  \x1b[1mLocal\x1b[0m:   \x1b[36mhttp://localhost:5173/\x1b[0m\n'
        '  ➜  Network: use --host to expose\n'
    )
    assert extraer_urls_locales(pane) == ['http://localhost:5173/']


def test_uvicorn():
    pane = 'INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)\n'
    assert extraer_urls_locales(pane) == ['http://localhost:8000']


def test_normaliza_0000_en_extraccion():
    pane = 'Server listening on http://0.0.0.0:4321\n'
    assert extraer_urls_locales(pane) == ['http://localhost:4321']


def test_la_mas_reciente_primero():
    pane = (
        'arrancando viejo server http://localhost:5000\n'
        'ahora el bueno: http://localhost:5173/\n'
    )
    assert extraer_urls_locales(pane) == ['http://localhost:5173/', 'http://localhost:5000']


def test_dedup_conserva_una():
    pane = 'http://localhost:5173/\notra línea\nhttp://localhost:5173/\n'
    assert extraer_urls_locales(pane) == ['http://localhost:5173/']


def test_excluye_puerto_jarvis():
    # curl a la API de Jarvis / instrucciones que mencionan el dashboard
    pane = 'curl http://localhost:3000/api/projects → 200\n'
    assert extraer_urls_locales(pane) == []


def test_excluye_metro_solo_en_expo():
    pane = 'Metro waiting on http://localhost:8081\n'
    assert extraer_urls_locales(pane, es_expo=True) == []
    # en proyectos NO-Expo, :8081 es un server válido cualquiera
    assert extraer_urls_locales(pane, es_expo=False) == ['http://localhost:8081']


def test_requiere_esquema_y_puerto():
    # mención sin http:// o sin puerto NO dispara (anti falso-positivo)
    pane = 'abrí localhost:5173 en el browser\nvisitá http://localhost a secas\n'
    assert extraer_urls_locales(pane) == []


def test_ignora_urls_externas():
    pane = 'docs en https://docs.expo.dev/guides y http://192.168.0.5:8080/x\n'
    assert extraer_urls_locales(pane) == []


def test_url_con_path_corta_en_comilla_y_parentesis():
    pane = "abrí 'http://localhost:5173/app' (o http://127.0.0.1:8000/docs)\n"
    assert extraer_urls_locales(pane) == [
        'http://localhost:8000/docs',
        'http://localhost:5173/app',
    ]


def test_texto_vacio():
    assert extraer_urls_locales('') == []
    assert extraer_urls_locales(None) == []


# ─── Callbacks de login de CLIs (NO son dev servers) ───────────────────────────
# Codex/gemini levantan un server efímero de loopback para el callback de su login
# OAuth. No hay que anunciarlos: rompía el login (TCP-check) y amontonaba localhost
# inútiles en el Web Preview. Se excluyen por path y por contexto de la línea.

def test_es_callback_oauth_por_path():
    assert dd.es_callback_oauth('http://127.0.0.1:46111/oauth2callback?code=x') is True
    assert dd.es_callback_oauth('http://localhost:1455/auth/callback') is True
    assert dd.es_callback_oauth('http://127.0.0.1:8080/authcode') is True
    assert dd.es_callback_oauth('http://localhost:5173/') is False
    assert dd.es_callback_oauth('http://localhost:8000/docs') is False


def test_excluye_callback_oauth_en_extraccion():
    out = extraer_urls_locales('callback http://127.0.0.1:46111/oauth2callback?code=x')
    assert out == []


def test_excluye_url_pelada_de_login_por_contexto():
    # codex imprime la URL SIN path -> se caza por la línea ("login server")
    assert extraer_urls_locales('Starting local login server on http://localhost:1455.') == []
    assert extraer_urls_locales('Sign in: http://127.0.0.1:45691 esperando') == []


def test_dev_server_se_mantiene_aunque_haya_login_en_otra_linea():
    txt = 'Local: http://localhost:5173/\nStarting local login server on http://localhost:1455'
    out = extraer_urls_locales(txt)
    assert 'http://localhost:5173/' in out
    assert not any('1455' in u for u in out)


# ─── Reconocer el proceso dueño de un puerto de login (fuente PUERTO) ──────────
# El callback OAuth de un CLI (o su IDE-server) NO es un dev server: se excluye por
# la cmdline/exe del proceso DUEÑO del puerto. claude bindea un puerto EFÍMERO con
# cmdline pelada 'claude' → se discrimina por el exe (/share/claude/). Diseño y casos
# de la corrida del enjambre localhost-login-leak (firmas reales en vivo).

def test_login_cli_codex_por_cmdline():
    # codex: cmdline contiene el path del paquete + fallback codex/login
    cmd = '/home/user/.nvm/.../node_modules/@openai/codex/.../bin/codex login '
    assert dd._cmdline_o_exe_es_login_cli(cmd, '/home/user/.../bin/codex') is True


def test_login_cli_gemini_por_cmdline():
    assert dd._cmdline_o_exe_es_login_cli('node /x/@google/gemini-cli/dist/index.js', '') is True


def test_login_cli_opencode_por_cmdline():
    assert dd._cmdline_o_exe_es_login_cli(
        'opencode auth login', '/home/user/.nvm/.../node_modules/opencode-ai/bin/opencode.exe') is True


def test_login_cli_claude_nativo_por_exe():
    # cmdline PELADA 'claude' (un solo token) → solo el exe discrimina
    assert dd._cmdline_o_exe_es_login_cli('claude', '/home/user/.local/share/claude/versions/2.1.185') is True


def test_login_cli_claude_npm_por_cmdline():
    assert dd._cmdline_o_exe_es_login_cli('node /x/@anthropic-ai/claude-code/cli.js', 'node') is True


def test_login_cli_antigravity_por_exe():
    # agy: cmdline PELADA 'agy' (con o sin args) → se discrimina por el BASENAME
    # del exe. Bindea puertos loopback efímeros para su IPC interno, no dev servers.
    assert dd._cmdline_o_exe_es_login_cli('agy', '/home/user/.local/bin/agy') is True
    assert dd._cmdline_o_exe_es_login_cli(
        'agy --dangerously-skip-permissions', '/home/user/.local/bin/agy') is True


# ── Falsos positivos: un dev server REAL en un proyecto con nombre de CLI NO cae ──
def test_no_excluye_dev_server_en_proyecto_claude():
    # un proyecto llamado 'claude-x' corriendo vite: cmdline tiene 'claude-x' pero
    # NO '/share/claude/' ni '@anthropic-ai/claude-code'; exe es 'node'
    assert dd._cmdline_o_exe_es_login_cli(
        'node /home/user/proyectos/claude-x/node_modules/.bin/vite', 'node') is False


def test_no_excluye_dev_server_en_proyecto_opencode():
    # 'opencode-y' contiene 'opencode' pero NO 'opencode-ai' (nombre del paquete)
    assert dd._cmdline_o_exe_es_login_cli(
        'node /home/user/proyectos/opencode-y/server.js', 'node') is False


def test_no_excluye_dev_server_en_proyecto_qwen():
    assert dd._cmdline_o_exe_es_login_cli(
        'node /home/user/proyectos/qwen-app/vite', 'node') is False


def test_no_excluye_dev_server_en_proyecto_agy():
    # un proyecto 'agy-proj' corriendo vite: el path contiene '/agy' pero el
    # BASENAME del exe es 'node', no 'agy' → NO cae (guarda contra el substring).
    assert dd._cmdline_o_exe_es_login_cli(
        'node /home/user/proyectos/agy-proj/node_modules/.bin/vite', 'node') is False


def test_proceso_es_login_cli_falla_abierto():
    # sin pid o pid inexistente → False (no rompe en entornos sin /proc)
    assert dd._proceso_es_login_cli(None) is False
    assert dd._proceso_es_login_cli(0) is False
    assert dd._proceso_es_login_cli(2_000_000_000) is False


# ── es_callback_oauth: el path '/callback' pelado (claude/opencode-OAuth) AHORA cae ──
def test_callback_pelado_excluido():
    assert dd.es_callback_oauth('http://127.0.0.1:45921/callback') is True
    assert dd.es_callback_oauth('http://127.0.0.1:45921/callback?code=x') is True
    assert dd.es_callback_oauth('http://localhost:1234/api/callback') is True


def test_callback_pelado_no_rompe_dev_servers():
    # /callback-handler y /callbacks NO son callbacks de login
    assert dd.es_callback_oauth('http://localhost:5173/callback-handler') is False
    assert dd.es_callback_oauth('http://localhost:5173/callbacks') is False
    assert dd.es_callback_oauth('http://localhost:8000/docs') is False
    assert dd.es_callback_oauth('http://localhost:5173/') is False


# ─── Estado multi-URL (varios dev servers por proyecto) ────────────────────────
# El registro rastrea TODOS los localhost vivos de cada proyecto (un agente
# puede levantar 3, o varios agentes uno cada uno) → el front los abre como
# pestañas. Tests del estado puro (sin tmux ni red).

def _reset_estado():
    dd._detectados.clear()
    dd._descartadas.clear()


def test_estado_vacio():
    _reset_estado()
    assert dd.url_detectada(1) is None
    assert dd.urls_detectadas(1) == []


def test_varios_servers_por_proyecto():
    _reset_estado()
    dd._detectados[1] = {
        'http://localhost:5173/': {'terminal_id': 10, 'terminal_nombre': 'Front'},
        'http://localhost:8000/': {'terminal_id': 10, 'terminal_nombre': 'Front'},
    }
    # urls_detectadas devuelve TODAS, en orden de detección
    assert dd.urls_detectadas(1) == ['http://localhost:5173/', 'http://localhost:8000/']
    # url_detectada (el pill es single) = la más reciente (la última insertada)
    assert dd.url_detectada(1) == 'http://localhost:8000/'


def test_descartar_una_especifica():
    _reset_estado()
    dd._detectados[1] = {
        'http://localhost:5173/': {'terminal_id': 1, 'terminal_nombre': 'A'},
        'http://localhost:8000/': {'terminal_id': 1, 'terminal_nombre': 'A'},
    }
    assert dd.descartar(1, 'http://localhost:5173/') == 'http://localhost:5173/'
    # la otra sigue rastreada; la descartada queda en _descartadas
    assert dd.urls_detectadas(1) == ['http://localhost:8000/']
    assert 'http://localhost:5173/' in dd._descartadas.get(1, set())


def test_descartar_sin_url_saca_la_mas_reciente():
    _reset_estado()
    dd._detectados[1] = {
        'http://localhost:5173/': {'terminal_id': 1, 'terminal_nombre': 'A'},
        'http://localhost:8000/': {'terminal_id': 1, 'terminal_nombre': 'A'},
    }
    assert dd.descartar(1) == 'http://localhost:8000/'
    assert dd.urls_detectadas(1) == ['http://localhost:5173/']


def test_descartar_ultima_limpia_el_proyecto():
    _reset_estado()
    dd._detectados[1] = {'http://localhost:5173/': {'terminal_id': 1, 'terminal_nombre': 'A'}}
    assert dd.descartar(1, 'http://localhost:5173/') == 'http://localhost:5173/'
    assert 1 not in dd._detectados
    assert dd.url_detectada(1) is None


def test_descartar_proyecto_sin_nada():
    _reset_estado()
    assert dd.descartar(1) is None
    assert dd.descartar(1, 'http://localhost:9999/') is None


def test_servers_detectados_detalle():
    _reset_estado()
    dd._detectados[1] = {
        'http://localhost:5173/': {'terminal_id': 10, 'terminal_nombre': 'Front'},
        'http://localhost:8000/': {'terminal_id': 11, 'terminal_nombre': 'API'},
    }
    assert dd.servers_detectados(1) == [
        {'url': 'http://localhost:5173/', 'terminal_id': 10, 'terminal_nombre': 'Front', 'tipo': 'server'},
        {'url': 'http://localhost:8000/', 'terminal_id': 11, 'terminal_nombre': 'API', 'tipo': 'server'},
    ]
    assert dd.servers_detectados(2) == []


# ─── Fuente 2: detección por puertos LISTEN (funciones puras) ──────────────────

def test_puerto_excluido():
    assert puerto_excluido(3000) is True            # Jarvis, siempre
    assert puerto_excluido(3000, es_expo=True) is True
    assert puerto_excluido(8081, es_expo=True) is True   # Metro, solo Expo
    assert puerto_excluido(8081, es_expo=False) is False  # cualquier server fuera de Expo
    assert puerto_excluido(5173) is False
    assert puerto_excluido(None) is False


def test_parsear_ss_con_pid():
    # Salida típica de `ss -tlnpH` (un http.server de un agente).
    texto = (
        'LISTEN 0      5             0.0.0.0:5050      0.0.0.0:*    '
        'users:(("python3",pid=3412044,fd=3))\n'
    )
    assert parsear_ss_listen(texto) == [{'port': 5050, 'pid': 3412044}]


def test_parsear_ss_varias_lineas_y_dns_sin_pid():
    texto = (
        'LISTEN 0 5   0.0.0.0:5050  0.0.0.0:*  users:(("python3",pid=3412044,fd=3))\n'
        'LISTEN 0 5   127.0.0.1:8121 0.0.0.0:* users:(("python3",pid=3674429,fd=3))\n'
        'LISTEN 0 4096 127.0.0.53%lo:53 0.0.0.0:*\n'   # resolver DNS del sistema: sin proceso
    )
    res = parsear_ss_listen(texto)
    assert {'port': 5050, 'pid': 3412044} in res
    assert {'port': 8121, 'pid': 3674429} in res
    # el resolver DNS entra con pid=None → el caller lo descarta (no atribuible)
    assert {'port': 53, 'pid': None} in res


def test_parsear_ss_ipv6():
    texto = 'LISTEN 0 128 [::]:8000 [::]:* users:(("uvicorn",pid=999,fd=7))\n'
    assert parsear_ss_listen(texto) == [{'port': 8000, 'pid': 999}]


def test_parsear_ss_vacio_y_basura():
    assert parsear_ss_listen('') == []
    assert parsear_ss_listen(None) == []
    assert parsear_ss_listen('línea basura sin sentido\n') == []


def test_proyecto_de_cwd_match_simple():
    proyectos = [{'id': 17, 'ruta': '/home/user/jarvis'}]
    assert proyecto_de_cwd('/home/user/jarvis/redesigns/chat-ideas', proyectos) == 17
    assert proyecto_de_cwd('/home/user/jarvis', proyectos) == 17   # exacto


def test_proyecto_de_cwd_prefijo_mas_largo_gana():
    # un proyecto anidado dentro de otro: gana el de ruta más larga (más específico)
    proyectos = [
        {'id': 1, 'ruta': '/home/user/proyectos'},
        {'id': 2, 'ruta': '/home/user/proyectos/app'},
    ]
    assert proyecto_de_cwd('/home/user/proyectos/app/src', proyectos) == 2
    assert proyecto_de_cwd('/home/user/proyectos/otra', proyectos) == 1


def test_proyecto_de_cwd_sin_match():
    proyectos = [{'id': 17, 'ruta': '/home/user/jarvis'}]
    assert proyecto_de_cwd('/tmp/algo', proyectos) is None
    assert proyecto_de_cwd(None, proyectos) is None
    # prefijo parcial que NO es separador de path no cuenta (jarvis ≠ jarvis-otro)
    assert proyecto_de_cwd('/home/user/jarvis-otro/x', proyectos) is None


def test_puertos_ya_conocidos():
    _reset_estado()
    dd._detectados[1] = {'http://localhost:5173/app': {'terminal_id': 1, 'terminal_nombre': 'A'}}
    dd._descartadas[2] = {'http://localhost:9000'}
    assert dd._puertos_ya_conocidos() == {5173, 9000}
    _reset_estado()
    assert dd._puertos_ya_conocidos() == set()


# ─── Demos servidos por el PROPIO Jarvis (:3000/static/<dir>/…) ────────────────

def test_es_demo_jarvis_solo_static_no_app():
    from plotspace.core.dev_detect import es_demo_jarvis
    # Demos reales: carpetas bajo /static que NO son de la app
    assert es_demo_jarvis('http://localhost:3000/static/wb-redesigns/index.html')
    assert es_demo_jarvis('http://localhost:3000/static/sidebar-redesign/v2.html')
    assert es_demo_jarvis('http://localhost:3000/static/demo-landing/')
    # Superficie de la app: NO son demos
    assert not es_demo_jarvis('http://localhost:3000/static/shared/base.css')
    assert not es_demo_jarvis('http://localhost:3000/static/sections/preview/preview.js')
    assert not es_demo_jarvis('http://localhost:3000/static/shell/workspace.html')
    assert not es_demo_jarvis('http://localhost:3000/static/vendor/xterm/xterm.js')
    assert not es_demo_jarvis('http://localhost:3000/static/index.html')
    # Fuera de /static o fuera del 3000: no
    assert not es_demo_jarvis('http://localhost:3000/api/projects')
    assert not es_demo_jarvis('http://localhost:3000/workspace?id=1')
    assert not es_demo_jarvis('http://localhost:3000')
    assert not es_demo_jarvis('http://localhost:5173/static/demo/')
    assert not es_demo_jarvis('basura')


def test_extraer_demos_jarvis_del_pane():
    from plotspace.core.dev_detect import extraer_demos_jarvis
    texto = (
        'Servido el mockup en http://localhost:3000/static/wb-redesigns/index.html\n'
        'la API está en http://localhost:3000/api/health\n'
        'dev server: http://localhost:5173\n'
        'otra galería: http://localhost:3000/static/strip-redesigns/index.html.\n'
    )
    # Solo los demos del 3000, más reciente primero, sin la puntuación final
    assert extraer_demos_jarvis(texto) == [
        'http://localhost:3000/static/strip-redesigns/index.html',
        'http://localhost:3000/static/wb-redesigns/index.html',
    ]
    assert extraer_demos_jarvis('') == []


def test_extraer_urls_locales_sigue_excluyendo_3000():
    # Los demos NO se cuelan en la lista de dev servers (pipeline aparte).
    texto = 'http://localhost:3000/static/wb-redesigns/index.html y http://localhost:5173'
    assert extraer_urls_locales(texto) == ['http://localhost:5173']


def test_demo_vivo_por_disco(tmp_path):
    from plotspace.core.dev_detect import demo_vivo
    base = str(tmp_path)
    (tmp_path / 'galeria').mkdir()
    (tmp_path / 'galeria' / 'index.html').write_text('<h1>demo</h1>')
    # archivo directo
    assert demo_vivo('http://localhost:3000/static/galeria/index.html', base=base)
    # URL de carpeta (con y sin barra) → vale por su index.html
    assert demo_vivo('http://localhost:3000/static/galeria/', base=base)
    assert demo_vivo('http://localhost:3000/static/galeria', base=base)
    # query string no molesta
    assert demo_vivo('http://localhost:3000/static/galeria/index.html?v=3', base=base)
    # borrado → muerto
    assert not demo_vivo('http://localhost:3000/static/no-existe/index.html', base=base)
    # traversal NUNCA sale de frontend/
    assert not demo_vivo('http://localhost:3000/static/../../../etc/passwd', base=base)


def test_servers_detectados_expone_tipo():
    _reset_estado()
    dd._detectados[7] = {
        'http://localhost:5173': {'terminal_id': 1, 'terminal_nombre': 'A'},
        'http://localhost:3000/static/wb-redesigns/index.html':
            {'terminal_id': 2, 'terminal_nombre': 'B', 'tipo': 'demo'},
    }
    tipos = {s['url']: s['tipo'] for s in dd.servers_detectados(7)}
    assert tipos['http://localhost:5173'] == 'server'
    assert tipos['http://localhost:3000/static/wb-redesigns/index.html'] == 'demo'
    _reset_estado()


def test_ciclo_anuncia_y_oculta_demo(monkeypatch, tmp_path):
    """Integración del poller con el pipeline de demos: anuncia con tipo=demo,
    el descarte lo oculta mientras el archivo exista, y borrar el archivo
    libera el descarte (un demo nuevo en la misma URL vuelve a anunciarse)."""
    import asyncio

    _reset_estado()
    (tmp_path / 'mockup').mkdir()
    (tmp_path / 'mockup' / 'index.html').write_text('<h1>v1</h1>')
    url = 'http://localhost:3000/static/mockup/index.html'

    monkeypatch.setattr(dd, '_FRONTEND_DIR', str(tmp_path))
    monkeypatch.setattr(dd, '_rows_activas',
                        lambda: [{'tid': 5, 'tnombre': 'Diseño', 'pid': 9, 'ruta': '/x'}])
    monkeypatch.setattr(dd, '_puertos_listen', lambda: set())
    monkeypatch.setattr(dd, '_proyecto_es_expo', lambda ruta: False)

    async def _cap(tid):
        return f'mirá el mockup en {url}'
    monkeypatch.setattr(dd, '_capture_pane', _cap)

    eventos = []

    async def _bc(pid, msg):
        eventos.append((pid, msg))
    monkeypatch.setattr(dd.broadcaster, 'broadcast', _bc)

    # 1. Aparece en el pane → se anuncia como demo
    asyncio.run(dd._ciclo())
    assert dd.servers_detectados(9) == [{
        'url': url, 'terminal_id': 5, 'terminal_nombre': 'Diseño', 'tipo': 'demo'}]
    assert eventos and eventos[0][1]['type'] == 'dev_server_detectado'
    assert eventos[0][1]['tipo'] == 'demo'

    # 2. El usuario lo oculta (✕): no se re-anuncia aunque el pane lo siga mostrando
    dd.descartar(9, url)
    eventos.clear()
    asyncio.run(dd._ciclo())
    assert dd.servers_detectados(9) == []
    assert eventos == []

    # 3. Borran los archivos del demo → el descarte se libera; un demo NUEVO
    #    en la misma URL vuelve a anunciarse cuando reaparece en disco
    (tmp_path / 'mockup' / 'index.html').unlink()
    asyncio.run(dd._ciclo())
    (tmp_path / 'mockup' / 'index.html').write_text('<h1>v2</h1>')
    asyncio.run(dd._ciclo())
    assert dd.servers_detectados(9) and dd.servers_detectados(9)[0]['tipo'] == 'demo'

    # 4. Y si el demo desaparece de disco estando anunciado → dev_server_caido
    eventos.clear()
    (tmp_path / 'mockup' / 'index.html').unlink()
    asyncio.run(dd._ciclo())
    assert dd.servers_detectados(9) == []
    assert any(m['type'] == 'dev_server_caido' for _, m in eventos)
    _reset_estado()


# ─── extraer_candidatos_pane + buscar_url_de_terminal (salto del preview) ──────

def test_candidatos_mezcla_servers_y_demos_mas_reciente_primero():
    texto = (
        'vite corriendo en http://localhost:5173\n'
        'y después el mockup: http://localhost:3000/static/mockup/index.html\n'
    )
    assert dd.extraer_candidatos_pane(texto) == [
        {'url': 'http://localhost:3000/static/mockup/index.html', 'tipo': 'demo'},
        {'url': 'http://localhost:5173', 'tipo': 'server'},
    ]


def test_candidatos_excluye_app_jarvis_y_oauth():
    texto = (
        'workspace: http://localhost:3000/workspace?id=7\n'
        'Starting local login server on http://localhost:1455/auth/callback\n'
    )
    assert dd.extraer_candidatos_pane(texto) == []


def test_buscar_url_de_terminal_snapshot():
    """Con snapshot vivo devuelve el MÁS RECIENTE de ESA terminal, sin tmux."""
    import asyncio
    _reset_estado()
    dd._detectados[9] = {
        'http://localhost:5173': {'terminal_id': 4, 'terminal_nombre': 'A'},
        'http://localhost:8000': {'terminal_id': 5, 'terminal_nombre': 'B'},
        'http://localhost:8100': {'terminal_id': 5, 'terminal_nombre': 'B'},
    }
    r = asyncio.run(dd.buscar_url_de_terminal(9, 5))
    assert r == {'url': 'http://localhost:8100', 'tipo': 'server'}
    _reset_estado()


def test_buscar_url_de_terminal_escanea_scrollback(monkeypatch, tmp_path):
    """Sin snapshot (server reiniciado / URL scrolleada fuera de la ventana del
    poller): escanea el scrollback COMPLETO, salta lo muerto, devuelve lo vivo
    y lo re-registra en _detectados para el menú y el próximo salto."""
    import asyncio
    _reset_estado()
    (tmp_path / 'mockup').mkdir()
    (tmp_path / 'mockup' / 'index.html').write_text('<h1>demo</h1>')
    demo = 'http://localhost:3000/static/mockup/'   # como la imprime el agente (sin index.html)

    monkeypatch.setattr(dd, '_FRONTEND_DIR', str(tmp_path))
    monkeypatch.setattr(dd, '_row_terminal',
                        lambda tid: {'tnombre': 'Diseño', 'pid': 9, 'ruta': '/x'})
    monkeypatch.setattr(dd, '_proyecto_es_expo', lambda ruta: False)

    async def _scroll(tid):
        return (f'mockup listo: {demo}\n'
                f'y un server que ya murió: http://localhost:5199\n')
    monkeypatch.setattr(dd, '_scrollback_completo', _scroll)

    async def _muerto(url, timeout=0.6):
        return False
    monkeypatch.setattr(dd, '_puerto_vivo', _muerto)

    r = asyncio.run(dd.buscar_url_de_terminal(9, 5))
    assert r == {'url': demo, 'tipo': 'demo'}
    assert dd.servers_detectados(9) == [{
        'url': demo, 'terminal_id': 5, 'terminal_nombre': 'Diseño', 'tipo': 'demo'}]
    _reset_estado()


def test_buscar_url_de_terminal_respeta_descartadas_y_proyecto(monkeypatch, tmp_path):
    import asyncio
    _reset_estado()
    (tmp_path / 'mockup').mkdir()
    (tmp_path / 'mockup' / 'index.html').write_text('x')
    demo = 'http://localhost:3000/static/mockup/'

    monkeypatch.setattr(dd, '_FRONTEND_DIR', str(tmp_path))
    monkeypatch.setattr(dd, '_proyecto_es_expo', lambda ruta: False)

    async def _scroll(tid):
        return f'demo: {demo}\n'
    monkeypatch.setattr(dd, '_scrollback_completo', _scroll)

    # La terminal es de OTRO proyecto → None (no se cruza atribución)
    monkeypatch.setattr(dd, '_row_terminal',
                        lambda tid: {'tnombre': 'X', 'pid': 8, 'ruta': '/x'})
    assert asyncio.run(dd.buscar_url_de_terminal(9, 5)) is None

    # El usuario ya descartó esa URL (✕) → no se la re-imponemos
    monkeypatch.setattr(dd, '_row_terminal',
                        lambda tid: {'tnombre': 'X', 'pid': 9, 'ruta': '/x'})
    dd._descartadas[9] = {demo}
    assert asyncio.run(dd.buscar_url_de_terminal(9, 5)) is None
    _reset_estado()


def test_persistencia_sobrevive_reinicio(monkeypatch, tmp_path):
    """Un reinicio del server (update in-app) NO pierde la atribución
    server→terminal: el estado va a disco y se recarga al boot (el ciclo de
    liveness purga solo lo que ya murió). Clave para agentes TUI (alt-screen):
    su scrollback no retiene la URL, así que el re-scan no puede recuperarla."""
    _reset_estado()
    monkeypatch.setattr(dd, '_PERSIST_PATH', str(tmp_path / 'dev_servers.json'))
    monkeypatch.setattr(dd, '_persist_ultimo', None)
    dd._detectados[9] = {
        'http://localhost:5173': {'terminal_id': 5, 'terminal_nombre': 'A', 'tipo': 'server'},
        'http://localhost:3000/static/mockup/': {'terminal_id': 6, 'terminal_nombre': 'B', 'tipo': 'demo'},
    }
    dd._descartadas[9] = {'http://localhost:8000'}
    dd._persistir_estado()

    _reset_estado()           # "reinicio": estado en memoria perdido
    dd._cargar_estado()
    urls = [s['url'] for s in dd.servers_detectados(9)]
    assert urls == ['http://localhost:5173', 'http://localhost:3000/static/mockup/']
    assert dd.servers_detectados(9)[1]['tipo'] == 'demo'
    assert 'http://localhost:8000' in dd._descartadas[9]

    # archivo corrupto/ausente: carga silenciosa sin romper
    _reset_estado()
    (tmp_path / 'dev_servers.json').write_text('{basura')
    dd._cargar_estado()
    assert dd.servers_detectados(9) == []
    _reset_estado()


# ─── Detección de puertos multiplataforma (psutil, con respaldo) ──────────────
# `ss` y /proc son de Linux. Cuando el motor corra nativo en Windows o macOS no
# existen, y sin esto la detección de dev servers (el menú de localhost activos)
# se quedaría muda. psutil da lo mismo en los tres sistemas; los caminos viejos
# quedan de respaldo por si psutil no está instalado.

class _ConnFalsa:
    def __init__(self, port, pid, status='LISTEN'):
        self.laddr = type('A', (), {'port': port})()
        self.pid = pid
        self.status = status


def _psutil_falso(monkeypatch, conexiones):
    import sys, types
    mod = types.SimpleNamespace(
        CONN_LISTEN='LISTEN',
        net_connections=lambda kind=None: conexiones,
        Process=lambda pid: None,
    )
    monkeypatch.setitem(sys.modules, 'psutil', mod)


def test_puertos_listen_usa_psutil(monkeypatch):
    _psutil_falso(monkeypatch, [_ConnFalsa(5173, 10), _ConnFalsa(8000, 11),
                                _ConnFalsa(9999, 12, status='ESTABLISHED')])
    puertos = dd._puertos_listen()
    assert puertos == {5173, 8000}, puertos   # los no-LISTEN no cuentan


def test_puertos_listen_cae_al_lector_de_proc(monkeypatch):
    # Sin psutil (o con psutil roto) NO puede quedarse sin detectar nada en
    # Linux: el lector de /proc sigue ahí.
    import sys, types
    monkeypatch.setitem(sys.modules, 'psutil',
                        types.SimpleNamespace(
                            CONN_LISTEN='LISTEN',
                            net_connections=lambda kind=None: (_ for _ in ()).throw(
                                OSError('sin permisos'))))
    puertos = dd._puertos_listen()
    assert isinstance(puertos, set)   # no explota; devuelve lo que /proc diga


def test_listeners_dedupean_ipv4_e_ipv6(monkeypatch):
    # Un mismo dev server bindea :: y 0.0.0.0 → dos conexiones, un solo server.
    # Sin de-dupe, el menú de localhost mostraría la misma URL dos veces.
    _psutil_falso(monkeypatch, [_ConnFalsa(5173, 10), _ConnFalsa(5173, 10),
                                _ConnFalsa(5173, 99)])
    listeners = dd._ss_listeners()
    assert sorted((l['port'], l['pid']) for l in listeners) == [(5173, 10), (5173, 99)]
