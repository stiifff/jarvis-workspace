"""Mobile Preview — muestra en vivo la app Expo del proyecto en un marco de teléfono.

El panel NO arranca Metro: DETECTA el dev server de Expo (Metro --web) que ya
corre en una terminal del proyecto y lo muestra en el iframe; si no hay ninguno,
espera. Así no se duplica el Metro del agente ni corre en una consola que el
agente no controla. Endpoints: /estado (¿es Expo?), /detectar (URL del Expo en
las terminales), /backend-status (CORS del backend de la app).
"""
import asyncio
import json
import os
import re
import subprocess
import time
from typing import Optional

from fastapi import APIRouter, Body, HTTPException

from plotspace.core.database import get_db

router = APIRouter(prefix='/api/mobile-preview', tags=['mobile-preview'])

_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[mGKHFJA-Z]')


# ─── Funciones puras (testeadas en tests/test_mobile_preview.py) ──────────────

def _entrada_fresca(ts: Optional[float], ahora: float, ttl: float) -> bool:
    """¿Una entrada timestampeada en `ts` sigue vigente a `ahora` con vida `ttl`?
    Base común de los caches TTL (ruta de la app) y del marcador in-flight de
    /iniciar. None → nunca fresca; el borde (ahora-ts == ttl) ya expiró."""
    return ts is not None and (ahora - ts) < ttl


def _deps_package_json(ruta: str) -> dict:
    """dependencies + devDependencies del package.json de la carpeta ({} si no
    hay package.json, está roto, o las deps no son dict)."""
    pkg_path = os.path.join(ruta, 'package.json')
    if not os.path.isfile(pkg_path):
        return {}
    try:
        with open(pkg_path, encoding='utf-8') as fh:
            pkg = json.load(fh)
        return {**pkg.get('dependencies', {}), **pkg.get('devDependencies', {})}
    except Exception:
        return {}


def _es_proyecto_expo(ruta: str) -> bool:
    """True si la carpeta tiene config de Expo + dependencia expo en package.json."""
    if not ruta or not os.path.isdir(ruta):
        return False
    tiene_config = any(
        os.path.isfile(os.path.join(ruta, f))
        for f in ('app.json', 'app.config.js', 'app.config.ts')
    )
    if not tiene_config:
        return False
    return 'expo' in _deps_package_json(ruta)


# Carpetas que nunca contienen la app del usuario: dependencias, builds, venvs.
_CARPETAS_IGNORADAS = {'node_modules', 'venv', '.venv', '__pycache__',
                       'dist', 'build', '.expo', '.next'}


def _encontrar_app_expo(ruta: str, max_depth: int = 4) -> Optional[str]:
    """Ruta de la carpeta con la app Expo dentro del proyecto, o None si no hay.

    La app puede no vivir en la raíz (ej: proyecto fintech-test con la app en
    mobile/). BFS por niveles: la raíz primero, después las subcarpetas más
    cercanas (orden alfabético para que el resultado sea determinista). Saltea
    ocultas (.git, .workspace) y _CARPETAS_IGNORADAS; max_depth acota el costo
    (esto corre en cada carga de proyecto, vía to_thread)."""
    if not ruta or not os.path.isdir(ruta):
        return None
    nivel = [ruta]
    for _ in range(max_depth + 1):
        siguiente = []
        for carpeta in nivel:
            if _es_proyecto_expo(carpeta):
                return carpeta
            try:
                entradas = sorted(os.scandir(carpeta), key=lambda e: e.name)
            except OSError:
                continue
            for ent in entradas:
                if not ent.is_dir(follow_symlinks=False):
                    continue
                if ent.name.startswith('.') or ent.name in _CARPETAS_IGNORADAS:
                    continue
                siguiente.append(ent.path)
        nivel = siguiente
        if not nivel:
            break
    return None


_ENV_API_RE = re.compile(
    r'^\s*EXPO_PUBLIC_API_URL\s*=\s*["\']?([^"\'\s#]+)', re.MULTILINE)


def _api_url_de_env(texto: str) -> Optional[str]:
    """EXPO_PUBLIC_API_URL del contenido de un .env (None si no está). Ignora
    líneas comentadas; tolera comillas y espacios alrededor del '='."""
    if not texto:
        return None
    m = _ENV_API_RE.search(texto)
    return m.group(1) if m else None


def _cors_permite(allow_origin: Optional[str], origen: str) -> bool:
    """¿El header Access-Control-Allow-Origin habilita a `origen`? El browser
    exige match exacto o '*'; sin header (allowlist que no conoce al origen,
    como cors() de Express fuera de la lista) bloquea."""
    return allow_origin == '*' or allow_origin == origen


# ─── Resolución de ruta del proyecto / app Expo ──────────────────────────────

def _ruta_proyecto(project_id: int) -> Optional[str]:
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT ruta FROM projects WHERE id = ?', (project_id,))
        row = cursor.fetchone()
        return row['ruta'] if row else None
    finally:
        conn.close()


# ─── Helpers sync agrupados (un solo hop de to_thread cada uno) ───────────────

def _ruta_app_expo(project_id: int) -> Optional[str]:
    """Carpeta de la app Expo del proyecto (raíz o subcarpeta, vía
    _encontrar_app_expo) o None si el proyecto no tiene app. Una sola pasada
    (sqlite + disco) para un to_thread."""
    ruta = _ruta_proyecto(project_id)
    return _encontrar_app_expo(ruta) if ruta else None


# project_id → (timestamp_monotonic, ruta_o_None). Cache del BFS de disco de
# _ruta_app_expo: /estado lo invoca en cada carga de proyecto, reconexión de WS
# y polling de respaldo cada 3s — sin cache eran hasta ~20 BFS de profundidad 4
# por minuto contra el filesystem. Mismo patrón (TTL 60s) que
# dev_detect._proyecto_es_expo.
_cache_ruta_app: dict = {}
_CACHE_RUTA_TTL = 60


def _ruta_app_expo_cached(project_id: int) -> Optional[str]:
    """_ruta_app_expo con cache TTL de 60s (incluso el resultado None — un
    proyecto sin app no se re-escanea cada 3s). Envuelve _ruta_app_expo SIN
    reemplazarla (los tests la monkeypatchean directo)."""
    ahora = time.monotonic()
    cacheado = _cache_ruta_app.get(project_id)
    if cacheado is not None and _entrada_fresca(cacheado[0], ahora, _CACHE_RUTA_TTL):
        return cacheado[1]
    ruta = _ruta_app_expo(project_id)
    _cache_ruta_app[project_id] = (ahora, ruta)
    return ruta


def _invalidar_cache_ruta(project_id: int):
    """Olvida la ruta cacheada del proyecto (al detener el preview o borrar el
    proyecto): la próxima consulta re-escanea el disco."""
    _cache_ruta_app.pop(project_id, None)


# ─── Editar el CÓDIGO REAL desde el inspector de Mobile Studio ────────────────
# El inspector del panel manda (archivo, línea, texto viejo, texto nuevo): la
# línea/archivo salen de la instrumentación __source de React (Babel la agrega en
# dev a cada elemento JSX). Acá reemplazamos SOLO ese literal de texto simple en
# el archivo fuente; Metro hace hot-reload solo. Diseño: es a prueba de balas —
# nunca toca código/JSX/expresiones, solo texto plano, y valida el path dentro
# del proyecto. Ver [[mobile-studio-rediseno]].

_SRC_EXT = ('.tsx', '.ts', '.jsx', '.js')
_MAX_TEXTO = 500
# chars que delatan código/JSX/expresión: si aparecen en el viejo o el nuevo,
# no es "texto simple" y no lo tocamos (evita corromper el archivo).
_PROHIBIDOS = ('{', '}', '<', '>', '`', '\n', '\r')


def _aplicar_patch_texto(app_dir: str, rel_file, line, old, new) -> dict:
    """Reemplaza UN literal de texto simple en un archivo fuente del proyecto,
    ubicado por (archivo, línea) de __source. Devuelve {ok, file, line, ...} o
    {ok:False, error}. No lanza: todos los fallos vuelven como error legible."""
    if not isinstance(rel_file, str) or not rel_file.strip():
        return {'ok': False, 'error': 'archivo inválido'}
    if not isinstance(old, str) or not isinstance(new, str):
        return {'ok': False, 'error': 'texto inválido'}
    if not old.strip():
        return {'ok': False, 'error': 'texto original vacío'}
    if old == new:
        return {'ok': False, 'error': 'sin cambios'}
    if len(new) > _MAX_TEXTO:
        return {'ok': False, 'error': 'texto demasiado largo'}
    if any(c in old for c in _PROHIBIDOS) or any(c in new for c in _PROHIBIDOS):
        return {'ok': False, 'error': 'solo se editan textos simples (no código)'}

    base = os.path.realpath(app_dir)
    full = os.path.realpath(os.path.join(base, rel_file))
    if full != base and not full.startswith(base + os.sep):
        return {'ok': False, 'error': 'ruta fuera del proyecto'}
    if os.path.splitext(full)[1].lower() not in _SRC_EXT:
        return {'ok': False, 'error': 'tipo de archivo no editable'}
    if not os.path.isfile(full):
        return {'ok': False, 'error': 'archivo no encontrado'}
    try:
        with open(full, 'r', encoding='utf-8') as f:
            lineas = f.readlines()
    except (OSError, UnicodeDecodeError):
        return {'ok': False, 'error': 'no pude leer el archivo'}
    n = len(lineas)
    if n == 0:
        return {'ok': False, 'error': 'archivo vacío'}

    # buscar la línea: la indicada primero, luego ±1..±3 (la instrumentación a
    # veces apunta a la línea de apertura del elemento, no a la del texto).
    base_i = (line - 1) if isinstance(line, int) and line > 0 else 0
    orden = [base_i] + [base_i + d for d in (1, -1, 2, -2, 3, -3)]
    idx = next((i for i in orden if 0 <= i < n and old in lineas[i]), None)
    if idx is None:
        return {'ok': False, 'error': 'no encontré ese texto cerca de la línea indicada'}
    if lineas[idx].count(old) != 1:
        return {'ok': False, 'error': 'texto ambiguo en la línea (aparece más de una vez)'}

    linea_txt = lineas[idx]
    pos = linea_txt.find(old)
    # si el literal está entre comillas y el texto nuevo trae esa misma comilla,
    # rompería la cadena → lo frenamos (en vez de escapar a ciegas).
    antes = linea_txt[pos - 1] if pos > 0 else ''
    if antes in ('"', "'") and antes in new:
        return {'ok': False, 'error': 'el texto nuevo rompería las comillas del literal'}
    lineas[idx] = linea_txt[:pos] + new + linea_txt[pos + len(old):]

    tmp = full + '.jarvis-tmp'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            f.writelines(lineas)
        os.replace(tmp, full)
    except OSError:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        return {'ok': False, 'error': 'no pude escribir el archivo'}
    return {'ok': True, 'file': rel_file, 'line': idx + 1, 'old': old, 'new': new}


# ─── Descubrir/ubicar textos editables en el código fuente ───────────────────
# Base del inspector de Mobile Studio: en vez de leer los internals frágiles de
# React en vivo, escaneamos el fuente y sacamos el copy de UI editable (con la
# misma heurística del mockup: copy ≠ dato dinámico). Cada texto queda atado a su
# (archivo, línea) EXACTA → editarlo con _aplicar_patch_texto es preciso. Todo
# esto es puro y testeable sin app corriendo. Ver [[mobile-studio-rediseno]].

_SRC_EXT_JSX = ('.tsx', '.jsx')   # solo JSX para descubrir copy de UI (no lógica .ts)
_EXCLUIR_DIRS = {'node_modules', '.git', '.expo', '.expo-shared', 'ios', 'android',
                 'build', 'dist', '.next', 'coverage', '__tests__', '.jarvis',
                 '.vscode', 'assets', 'web-build'}
_MAX_ARCHIVOS_SCAN = 500
_MAX_TEXTOS = 400

# Datos que NO se editan (se autocompletan / vienen de la cuenta / son técnicos):
_RE_TIENE_DIGITO = re.compile(r'\d')
_RE_EMAIL_URL = re.compile(r'@|https?://|www\.')
_RE_FECHA_HORA = re.compile(
    r'\b(hoy|ayer|mañana|manana|hrs?|hs|min|seg|am|pm|lun|mar|mié|mie|jue|vie|'
    r'sáb|sab|dom|ene|feb|abr|jun|jul|ago|sep|oct|nov|dic)\b', re.I)
_RE_TIENE_LETRA = re.compile(r'[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]')
# Una sola palabra que SÍ es copy (capitalizada tipo "Perfil", "Inicio", "Día"):
_RE_PALABRA_COPY = re.compile(r'^[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]+$')


def _es_texto_dinamico(t: str) -> bool:
    """¿Es un dato que se completa solo (no se edita)? Mismo criterio que el
    inspector del mockup: dígitos, email/URL, o palabras de fecha/hora."""
    if not t:
        return False
    if _RE_TIENE_DIGITO.search(t):
        return True
    if _RE_EMAIL_URL.search(t):
        return True
    if _RE_FECHA_HORA.search(t):
        return True
    return False


def _es_texto_editable(t: str) -> bool:
    """¿`t` es copy de UI editable (y no un token técnico/dato)? Conservador: ante
    la duda, NO lo ofrece (mejor perder una cadena que ofrecer código como si
    fuera texto). El patch es exacto igual."""
    if not isinstance(t, str):
        return False
    t = t.strip()
    if len(t) < 2 or len(t) > 120:
        return False
    if not _RE_TIENE_LETRA.search(t):
        return False
    if _es_texto_dinamico(t):
        return False
    # paths, urls, imports, colores, handles → fuera
    if '/' in t or '\\' in t or t[0] in '#@.':
        return False
    if any(c in t for c in _PROHIBIDOS):
        return False
    # una sola palabra: solo si parece copy capitalizado (rechaza row/center/flexStart)
    if ' ' not in t and not _RE_PALABRA_COPY.match(t):
        return False
    return True


def _iter_archivos_fuente(app_dir: str, extensiones=_SRC_EXT):
    """Camina el proyecto (sin node_modules/.git/ios/android/…) y entrega rutas
    absolutas de archivos fuente, con tope de cantidad."""
    base = os.path.realpath(app_dir)
    n = 0
    for raiz, dirs, files in os.walk(base):
        dirs[:] = sorted(d for d in dirs
                         if d not in _EXCLUIR_DIRS and not d.startswith('.'))
        for f in sorted(files):
            if os.path.splitext(f)[1].lower() in extensiones:
                yield os.path.join(raiz, f)
                n += 1
                if n >= _MAX_ARCHIVOS_SCAN:
                    return


# Texto JSX entre tags (>Hola<) y literales de cadena ("Hola" / 'Hola'):
_RE_JSX_TEXTO = re.compile(r'>([^<>{}\n]+)<')
_RE_CADENA = re.compile(r'"([^"\\\n]{2,120})"' + r"|'([^'\\\n]{2,120})'")


def _extraer_textos_de_linea(linea: str):
    """Candidatos de copy de UI en una línea: texto JSX + literales de cadena."""
    vistos = []
    for m in _RE_JSX_TEXTO.finditer(linea):
        vistos.append(m.group(1).strip())
    for m in _RE_CADENA.finditer(linea):
        vistos.append((m.group(1) if m.group(1) is not None else m.group(2)).strip())
    return vistos


def _localizar_texto(app_dir: str, texto):
    """Ubica un texto de UI en el fuente: devuelve [{file, line}] con TODAS las
    ocurrencias (excluyendo node_modules/…). El front decide: 1 sola → editar
    directo; varias → desambiguar. No aplica heurística (el texto ya lo eligió el
    usuario al tocarlo); solo lo busca."""
    if not isinstance(texto, str) or not texto.strip():
        return []
    texto = texto.strip()
    base = os.path.realpath(app_dir)
    matches = []
    for full in _iter_archivos_fuente(app_dir):
        try:
            with open(full, 'r', encoding='utf-8') as f:
                for i, linea in enumerate(f, 1):
                    if texto in linea:
                        rel = os.path.relpath(full, base)
                        matches.append({'file': rel, 'line': i})
                        if len(matches) >= 50:
                            return matches
        except (OSError, UnicodeDecodeError):
            continue
    return matches


def _escanear_textos_editables(app_dir: str):
    """Lista el copy de UI editable del proyecto: [{text, file, line}] dedup por
    texto (primera aparición gana). Es el 'árbol de textos' del inspector."""
    base = os.path.realpath(app_dir)
    fuera = {}          # texto → {text, file, line}
    for full in _iter_archivos_fuente(app_dir, _SRC_EXT_JSX):
        try:
            with open(full, 'r', encoding='utf-8') as f:
                lineas = f.readlines()
        except (OSError, UnicodeDecodeError):
            continue
        rel = os.path.relpath(full, base)
        for i, linea in enumerate(lineas, 1):
            for cand in _extraer_textos_de_linea(linea):
                if cand in fuera or not _es_texto_editable(cand):
                    continue
                fuera[cand] = {'text': cand, 'file': rel, 'line': i}
                if len(fuera) >= _MAX_TEXTOS:
                    return list(fuera.values())
    return list(fuera.values())


# ─── Estado del backend de la app (efectos — un OPTIONS cubre todo) ───────────

_ENV_FILES = ('.env', '.env.local', '.env.development')


def _backend_status_sync(project_id: int) -> dict:
    """¿La app tiene backend configurado, responde, y permite al preview (CORS)?

    Lee EXPO_PUBLIC_API_URL del .env de la app y hace UN preflight OPTIONS con
    el Origin del preview: cualquier respuesta HTTP (404 incluido) = backend
    vivo; el header Access-Control-Allow-Origin dice si el iframe va a poder
    llamarlo (el celular nativo no tiene CORS — esto afecta solo al preview
    embebido). Bloqueante: llamar vía to_thread."""
    ruta = _ruta_app_expo(project_id)
    api_url = None
    if ruta:
        for f in _ENV_FILES:
            p = os.path.join(ruta, f)
            if os.path.isfile(p):
                try:
                    with open(p, encoding='utf-8') as fh:
                        api_url = _api_url_de_env(fh.read())
                except OSError:
                    pass
            if api_url:
                break
    if not api_url:
        return {'configurado': False}

    puerto = _ultimo_puerto.get(project_id)   # puerto web del Expo detectado (origen del iframe)
    origen = f'http://localhost:{puerto}' if puerto else None

    # SSRF: api_url sale del .env de la app (lo controla el repo/agente). Sin
    # guard, un EXPO_PUBLIC_API_URL=http://169.254.169.254/... o file://... haría
    # que el server probee destinos internos. Misma blocklist que el probe y el
    # browser remoto. Ya corremos en un thread (to_thread) → llamada directa.
    from plotspace.core import ssrf
    ok_ssrf, motivo_ssrf = ssrf.url_destino_segura(api_url)
    if not ok_ssrf:
        return {
            'configurado': True,
            'api_url': api_url,
            'origen': origen,
            'alcanzable': False,
            'bloqueado': f'destino no permitido ({motivo_ssrf})',
        }

    import urllib.error
    import urllib.request

    class _SinRedirect(urllib.request.HTTPRedirectHandler):
        # No seguir 30x: un host público validado podría redirigir a 169.254.169.254
        # u otro interno (SSRF por redirect). El 3xx se trata como "vivo" igual.
        def redirect_request(self, *a, **k):
            return None

    _opener = urllib.request.build_opener(_SinRedirect)
    alcanzable, allow = False, None
    try:
        req = urllib.request.Request(api_url, method='OPTIONS', headers={
            'Origin': origen or 'http://localhost',
            'Access-Control-Request-Method': 'GET',
        })
        with _opener.open(req, timeout=10) as r:
            alcanzable = True
            allow = r.headers.get('Access-Control-Allow-Origin')
    except urllib.error.HTTPError as e:
        alcanzable = True  # respondió: el server está vivo aunque sea 4xx/5xx
        allow = e.headers.get('Access-Control-Allow-Origin')
    except Exception:
        alcanzable = False

    return {
        'configurado': True,
        'api_url': api_url,
        'origen': origen,
        'alcanzable': alcanzable,
        'cors_ok': _cors_permite(allow, origen) if (alcanzable and origen) else None,
    }


# ─── Detección del Expo que YA corre en una terminal (el panel NO lo arranca) ──
# Antes el panel lanzaba su propio `expo start --web --tunnel` en una sesión de
# servicio jarvis_mpreview_* → dos Metro sobre la misma carpeta + consola fuera
# del control del agente. Ahora NO arranca nada: detecta el dev server de Expo
# que ya corre en una terminal del proyecto y lo muestra; si no hay, espera.

def _capturar_pane_terminal(tid: int) -> str:
    # -600: la URL del Expo se imprime UNA vez al arrancar; si el agente sigue
    # tirando output (un prompt largo) se va del scrollback y dejábamos de
    # detectar aunque el server siguiera vivo. Ventana amplia + puerto recordado.
    from plotspace.core.terminal_backend import backend
    return backend().capturar(tid, lineas=600) or ''


def _probar_url_expo(url: str, timeout: float = 2.0) -> Optional[str]:
    """Sondea `url`: 'web' si sirve HTML (bundle web de Expo / dev server web),
    'metro' si responde pero no es HTML (Metro nativo sin --web), None si no
    responde. Solo localhost del propio equipo → sin guard SSRF."""
    import urllib.request
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            ctype = (r.headers.get('Content-Type') or '').lower()
            cuerpo = r.read(2048).decode('utf-8', 'replace').lower()
    except Exception:
        return None
    if 'text/html' in ctype or '<!doctype html' in cuerpo or '<html' in cuerpo:
        return 'web'
    return 'metro'


# ── Sampler de colores (status bar adaptativa del Mobile Studio) ─────────────
# El iframe de Metro es cross-origin: el front NO puede leer los colores que la
# app pinta. Este endpoint sirve el HTML de la app DESDE el origen de Jarvis con
# un <base> hacia Metro (bundles/assets cargan directo de Metro, sin proxy
# completo — el HMR no importa: el sampler es one-shot y se descarta) más un
# script inyectado que muestrea el fondo RENDERIZADO arriba/abajo y lo reporta
# por postMessage → los íconos de la status bar y el home indicator del preview
# se adaptan al fondo real de la app, como en el aparato físico.

_SAMPLER_URL_RE = re.compile(r'^http://(?:localhost|127\.0\.0\.1):(\d{2,5})$', re.I)


def _url_sampler_valida(url: str) -> bool:
    """SOLO el origen (sin path) de un dev server local; nunca Jarvis (:3000)
    ni el inspector de ngrok (:4040). Tolera la barra final: /detectar entrega
    la URL como `http://localhost:8081/` y rechazarla dejaba el sampler en 400
    silencioso (bug real 2026-07-11)."""
    m = _SAMPLER_URL_RE.match((url or '').strip().rstrip('/'))
    if not m:
        return False
    return int(m.group(1)) not in PUERTOS_IGNORADOS


def _ruta_sampler_valida(ruta: str) -> bool:
    return (bool(ruta) and ruta.startswith('/') and not ruta.startswith('//')
            and '..' not in ruta and '\\' not in ruta and len(ruta) <= 512)


def _inyectar_sampler(html: str, base_url: str) -> str:
    """Inyecta al comienzo del <head>: PRIMERO el script del sampler (su src
    relativo debe resolver contra Jarvis) y DESPUÉS el <base> hacia Metro (que
    re-apunta toda URL relativa posterior: bundle, assets, fetch del bundle).
    Sin <head>, prepende (el browser lo tolera)."""
    inj = ('<script src="/static/sections/mobile-preview/sampler.js?v=9"></script>'
           f'<base href="{base_url}/">')
    out, n = re.subn(r'<head([^>]*)>', lambda m: f'<head{m.group(1)}>{inj}', html, count=1, flags=re.I)
    return out if n else inj + html


@router.get('/{project_id}/sampler')
async def sampler_colores(project_id: int, url: str, ruta: str = '/'):
    """HTML de la app instrumentado para muestrear colores (iframe oculto del
    Mobile Studio). `url` = origen del dev server detectado; `ruta` = ruta
    actual de la app. El guard es estricto: solo orígenes locales."""
    if not _url_sampler_valida(url):
        raise HTTPException(status_code=400, detail='URL no permitida (solo dev servers locales)')
    url = url.strip().rstrip('/')   # normalizar: url + ruta sin doble barra
    if not _ruta_sampler_valida(ruta):
        ruta = '/'

    def _traer():
        import urllib.request
        req = urllib.request.Request(url + ruta, headers={'Accept': 'text/html'})
        with urllib.request.urlopen(req, timeout=6) as r:
            return r.read(2_000_000).decode('utf-8', 'replace')

    try:
        html = await asyncio.to_thread(_traer)
    except Exception:
        raise HTTPException(status_code=502, detail='El dev server no respondió')
    from fastapi.responses import HTMLResponse
    return HTMLResponse(_inyectar_sampler(html, url), headers={'Cache-Control': 'no-store'})


_ASSET_ORIGEN_RE = re.compile(r'^(http://(?:localhost|127\.0\.0\.1):(\d{2,5}))(?=/|$)', re.I)


def _url_asset_valida(u: str):
    """Origen local extraído de una URL ABSOLUTA de asset del dev server.
    Devuelve el origen validado o None (hosts remotos / puertos vedados)."""
    m = _ASSET_ORIGEN_RE.match((u or '').strip())
    if not m:
        return None
    if int(m.group(2)) in PUERTOS_IGNORADOS:
        return None
    return m.group(1)


@router.get('/{project_id}/asset')
async def asset_proxy(project_id: int, u: str):
    """Proxy same-origin de assets del dev server — FUENTES sobre todo: las
    @font-face del espejo instrumentado apuntan a Metro y el browser exige
    CORS para fuentes cross-origin; Metro no manda ACAO → la app caía a serif
    (bug real 2026-07-11, Outfit de @expo-google-fonts). Servidas desde Jarvis
    son same-origin y cargan. Guard: solo dev servers locales."""
    if not _url_asset_valida(u):
        raise HTTPException(status_code=400, detail='URL no permitida (solo dev servers locales)')

    def _traer_asset():
        import urllib.request
        req = urllib.request.Request(u, headers={'Accept': '*/*'})
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read(25_000_000), (r.headers.get('Content-Type') or 'application/octet-stream')

    try:
        cuerpo, ctype = await asyncio.to_thread(_traer_asset)
    except Exception:
        raise HTTPException(status_code=502, detail='El dev server no respondió')
    from fastapi import Response
    return Response(content=cuerpo, media_type=ctype,
                    headers={'Cache-Control': 'public, max-age=3600'})


_PORT_HTTP_RE   = re.compile(r'https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0):(\d{2,5})', re.I)
_PORT_TUNNEL_RE = re.compile(r'exp://[A-Za-z0-9-]*?-(\d{2,5})\.exp\.direct', re.I)  # exp://x-8081.exp.direct
_PORT_LAN_RE    = re.compile(r'exp://[\d.]+:(\d{2,5})')                            # exp://192.168.0.10:8081

# Puertos que NUNCA son el dev server web de Expo → no mostrarlos en el iframe:
#   3000 = Jarvis Workspace (este backend).
#   4040 = inspector web de ngrok (lo levanta Expo con --tunnel). Sirve HTML, así
#          que si no se excluye el detector lo confunde con el web de Expo y muestra
#          el dashboard de ngrok en el preview en vez de la app.
PUERTOS_IGNORADOS = (3000, 4040)


def _puertos_candidatos(texto: str) -> list:
    """Puertos de un posible dev server de Expo en el texto de un pane, MÁS
    RECIENTE primero. Mira tanto `http://localhost:PORT` como las URLs de Expo
    `exp://…-PORT.exp.direct` (túnel) y `exp://IP:PORT` (LAN) — con `--tunnel` el
    pane NO imprime la URL http local, solo el túnel, así que el puerto hay que
    sacarlo de ahí. Excluye PUERTOS_IGNORADOS (Jarvis :3000, inspector ngrok :4040)."""
    limpio = _ANSI_RE.sub('', texto or '')
    pos = {}   # puerto → última posición de aparición (para ordenar por reciente)
    for rx in (_PORT_HTTP_RE, _PORT_TUNNEL_RE, _PORT_LAN_RE):
        for m in rx.finditer(limpio):
            try:
                p = int(m.group(1))
            except ValueError:
                continue
            if 1024 <= p <= 65535 and p not in PUERTOS_IGNORADOS:
                pos[p] = max(pos.get(p, -1), m.start())
    return [p for p, _ in sorted(pos.items(), key=lambda kv: kv[1], reverse=True)]


# Puertos web por defecto de Expo. Fallback cuando el pane YA NO tiene una URL
# parseable (se fue del scrollback, o quedó wrapeada/mangleada por el ancho de la
# terminal): Expo web sale en :8081 (Metro unificado, SDK 49+); si está tomado usa
# 8082/8083. 19006 es el viejo webpack dev server. Robusto: no depende del texto.
PUERTOS_EXPO_DEFAULT = [8081, 8082, 8083, 19006]

# Señales de que ESTE proyecto está corriendo Expo web (aunque no haya URL limpia).
# Gatea el fallback de puertos default → no le robamos el :8081 a otro proyecto.
_EXPO_MARCAS = ('expo', 'metro', 'exp://', '8081', 'web bundled', 'expo-router')


def _panes_muestran_expo(textos) -> bool:
    """¿Algún pane muestra actividad de Expo web? (marcas, no URL). Puro."""
    for t in textos:
        low = (t or '').lower()
        if any(m in low for m in _EXPO_MARCAS):
            return True
    return False


def _escanear_panes_expo(textos, probar, puertos_extra=()) -> dict:
    """Dado el texto de varios panes y `probar(url)→'web'|'metro'|None`, sondea
    `http://localhost:PORT` por cada puerto candidato (ver _puertos_candidatos) y
    devuelve el primer dev server WEB ({url, web:True}); si solo hay Metro nativo →
    {url:None, nativo:True}; si nada → {url:None}. `puertos_extra` se sondean al
    final como fallback (puertos default de Expo) — robusto cuando el pane ya no
    tiene una URL parseable. Los candidatos del pane tienen prioridad (atribución).
    Testeable (probar inyectable)."""
    candidatos = []
    for texto in textos:
        for puerto in _puertos_candidatos(texto):
            if puerto not in candidatos:
                candidatos.append(puerto)
    for puerto in puertos_extra:
        if puerto not in candidatos:
            candidatos.append(puerto)
    nativo = False
    for puerto in candidatos:
        url = f'http://localhost:{puerto}/'
        tipo = probar(url)
        if tipo == 'web':
            return {'url': url, 'web': True, 'nativo': False}
        if tipo == 'metro':
            nativo = True
    return {'url': None, 'web': False, 'nativo': nativo}


# project_id → último puerto web detectado. Hace la detección "pegajosa": una vez
# que encontramos el Expo, lo seguimos mostrando re-sondeando ese puerto, aunque
# su URL ya no esté en el scrollback del pane (el agente la empujó fuera). Solo se
# suelta cuando el puerto deja de servir HTML.
_ultimo_puerto: dict = {}


def _puerto_de_url(url: str) -> Optional[int]:
    try:
        return int(url.rstrip('/').rsplit(':', 1)[1])
    except (ValueError, IndexError):
        return None


def _detectar_expo_en_terminales(project_id: int) -> dict:
    """Detecta el Expo web del proyecto. Primero re-sondea el puerto recordado
    (sobrevive a que la URL salga del scrollback); si no, escanea los panes de las
    terminales activas. El panel NO arranca nada."""
    # 1. Puerto recordado: si sigue sirviendo HTML, mostralo (no depende del pane).
    #    Un puerto ignorado (p.ej. 4040 de ngrok) nunca debe quedar pegado acá.
    prev = _ultimo_puerto.get(project_id)
    if prev in PUERTOS_IGNORADOS:
        _ultimo_puerto.pop(project_id, None)
        prev = None
    if prev and _probar_url_expo(f'http://localhost:{prev}/') == 'web':
        return {'url': f'http://localhost:{prev}/', 'web': True, 'nativo': False}

    # 2. Escanear los panes en busca de un Expo web (URL todavía visible).
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute('SELECT id FROM terminals WHERE project_id = ? AND activa = 1',
                    (project_id,))
        tids = [row['id'] for row in cur.fetchall()]
    finally:
        conn.close()
    textos = [_capturar_pane_terminal(tid) for tid in tids]
    # Fallback a los puertos web por defecto de Expo SOLO si los panes muestran
    # actividad de Expo (así no le robamos el :8081 a otro proyecto). Esto rescata
    # el caso en que la URL ya no es parseable en el pane (se fue/quedó wrapeada).
    extra = PUERTOS_EXPO_DEFAULT if _panes_muestran_expo(textos) else ()
    res = _escanear_panes_expo(textos, _probar_url_expo, puertos_extra=extra)
    if res.get('web') and res.get('url'):
        p = _puerto_de_url(res['url'])
        if p:
            _ultimo_puerto[project_id] = p
    else:
        _ultimo_puerto.pop(project_id, None)   # ya no hay web → olvidar
    return res


# ─── Endpoints ─────────────────────────────────────────────────────────────────

@router.get('/{project_id}/estado')
async def estado_preview(project_id: int):
    """Solo informa si el proyecto es Expo (para mostrar/ocultar la pestaña). El
    panel YA NO arranca Metro: la URL la resuelve /detectar."""
    es_expo = await asyncio.to_thread(
        lambda: _ruta_app_expo_cached(project_id) is not None)
    return {'es_expo': es_expo}


@router.get('/{project_id}/detectar')
async def detectar_preview(project_id: int):
    """Detecta el Expo que ya corre en una terminal del proyecto. El panel NO
    arranca nada: muestra lo que está corriendo y, si no hay, el front espera."""
    es_expo = await asyncio.to_thread(
        lambda: _ruta_app_expo_cached(project_id) is not None)
    if not es_expo:
        return {'es_expo': False, 'url': None, 'web': False, 'nativo': False}
    res = await asyncio.to_thread(_detectar_expo_en_terminales, project_id)
    return {'es_expo': True, **res}


@router.get('/{project_id}/backend-status')
async def backend_status(project_id: int):
    """Estado del backend de la app para la franja del panel (ver
    _backend_status_sync)."""
    return await asyncio.to_thread(_backend_status_sync, project_id)


@router.post('/{project_id}/patch-text')
async def patch_text(project_id: int, payload: dict = Body(...)):
    """Mobile Studio — EDITA EL CÓDIGO REAL. El inspector manda el archivo+línea
    (de la instrumentación __source de React) y el texto viejo→nuevo; acá se
    reemplaza ese literal simple en el fuente del proyecto y Metro hot-reloadea
    solo. Solo textos planos (nunca código/JSX). Ver _aplicar_patch_texto."""
    app_dir = await asyncio.to_thread(_ruta_app_expo_cached, project_id)
    if not app_dir:
        raise HTTPException(status_code=404, detail='el proyecto no es una app Expo')
    try:
        linea = int(payload.get('line'))
    except (TypeError, ValueError):
        linea = 0
    res = await asyncio.to_thread(
        _aplicar_patch_texto, app_dir,
        payload.get('file'), linea, payload.get('old'), payload.get('new'))
    if not res.get('ok'):
        raise HTTPException(status_code=400, detail=res.get('error', 'no se pudo editar'))
    return res


@router.get('/{project_id}/textos')
async def textos_editables(project_id: int):
    """Mobile Studio — 'árbol de textos' del inspector: el copy de UI editable del
    proyecto, cada uno atado a su archivo+línea (ver _escanear_textos_editables)."""
    app_dir = await asyncio.to_thread(_ruta_app_expo_cached, project_id)
    if not app_dir:
        return {'es_expo': False, 'textos': []}
    textos = await asyncio.to_thread(_escanear_textos_editables, app_dir)
    return {'es_expo': True, 'textos': textos}


@router.post('/{project_id}/localizar-texto')
async def localizar_texto(project_id: int, payload: dict = Body(...)):
    """Mobile Studio — ubica en el fuente un texto que el usuario tocó en la app
    (para el click-en-vivo por CDP): devuelve las ocurrencias {file, line}. 1 sola
    → editable directo; varias → el front desambigua."""
    app_dir = await asyncio.to_thread(_ruta_app_expo_cached, project_id)
    if not app_dir:
        raise HTTPException(status_code=404, detail='el proyecto no es una app Expo')
    matches = await asyncio.to_thread(_localizar_texto, app_dir, payload.get('texto'))
    return {'matches': matches, 'unico': len(matches) == 1}


# ─── Notas del proyecto (papeles del lienzo) ──────────────────────────────────
# El Studio guarda notas pegadas al lienzo: credenciales de Expo/EAS, comandos,
# pendientes. Viven en data/jarvis.db (local, gitignoreado) — JAMÁS en el repo,
# así que el candado anti-fuga de secretos no las ve nunca. `secreta` solo
# significa "nace tapada en la UI": no es cifrado y no se promete como tal.

MAX_NOTAS = 40
_NOTA_COLORES = ('papel', 'ambar', 'violeta', 'verde', 'cian', 'rosa')
_NOTA_TITULO_MAX = 200
_NOTA_CUERPO_MAX = 20000


def _nota_campos(payload: dict, previa: Optional[dict] = None) -> dict:
    """Campos saneados de una nota a partir de lo que manda el front (PATCH
    parcial: lo que no viene, se hereda de `previa`). Función pura — testeada en
    tests/test_mobile_preview_notas.py."""
    base = {
        'titulo': '', 'cuerpo': '', 'secreta': 0, 'color': 'papel',
        'x': 0.0, 'y': 0.0, 'w': 320.0, 'h': 300.0,
    }
    if previa:
        for k in base:
            if k in previa and previa[k] is not None:
                base[k] = previa[k]
    payload = payload if isinstance(payload, dict) else {}

    def _num(v, defecto, minimo, maximo):
        try:
            v = float(v)
        except (TypeError, ValueError):
            return float(defecto)
        if v != v:                      # NaN
            return float(defecto)
        return max(minimo, min(maximo, v))

    out = dict(base)
    if 'titulo' in payload:
        out['titulo'] = str(payload.get('titulo') or '')[:_NOTA_TITULO_MAX]
    if 'cuerpo' in payload:
        out['cuerpo'] = str(payload.get('cuerpo') or '')[:_NOTA_CUERPO_MAX]
    if 'secreta' in payload:
        out['secreta'] = 1 if payload.get('secreta') else 0
    if 'color' in payload:
        color = str(payload.get('color') or '')
        out['color'] = color if color in _NOTA_COLORES else base['color']
    for campo, minimo, maximo in (('x', -50000, 50000), ('y', -50000, 50000),
                                  ('w', 220, 4000), ('h', 160, 4000)):
        if campo in payload:
            out[campo] = _num(payload.get(campo), base[campo], minimo, maximo)
        else:
            out[campo] = _num(base[campo], base[campo], minimo, maximo)
    out['titulo'] = str(out['titulo'])[:_NOTA_TITULO_MAX]
    out['cuerpo'] = str(out['cuerpo'])[:_NOTA_CUERPO_MAX]
    out['secreta'] = 1 if out['secreta'] else 0
    if out['color'] not in _NOTA_COLORES:
        out['color'] = 'papel'
    return out


def _notas_listar(project_id: int) -> list:
    conn = get_db()
    try:
        filas = conn.execute(
            'SELECT * FROM project_notes WHERE project_id = ? ORDER BY id',
            (project_id,)).fetchall()
        return [dict(f) for f in filas]
    finally:
        conn.close()


def _nota_una(conn, project_id: int, nota_id: int) -> Optional[dict]:
    fila = conn.execute(
        'SELECT * FROM project_notes WHERE id = ? AND project_id = ?',
        (nota_id, project_id)).fetchone()
    return dict(fila) if fila else None


@router.get('/{project_id}/notas')
async def listar_notas(project_id: int):
    """Notas del proyecto (las pinta el lienzo del Studio)."""
    return {'notas': await asyncio.to_thread(_notas_listar, project_id)}


@router.post('/{project_id}/notas', status_code=201)
async def crear_nota(project_id: int, payload: dict = Body(default={})):
    """Crea una nota. Devuelve la fila completa (el front necesita el id real)."""
    def _crear():
        from datetime import datetime
        conn = get_db()
        try:
            n = conn.execute('SELECT COUNT(*) c FROM project_notes WHERE project_id = ?',
                             (project_id,)).fetchone()['c']
            if n >= MAX_NOTAS:
                return None
            campos = _nota_campos(payload)
            ahora = datetime.now().isoformat()
            cur = conn.execute(
                '''INSERT INTO project_notes
                     (project_id, titulo, cuerpo, secreta, color, x, y, w, h, creado, actualizado)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (project_id, campos['titulo'], campos['cuerpo'], campos['secreta'],
                 campos['color'], campos['x'], campos['y'], campos['w'], campos['h'],
                 ahora, ahora))
            conn.commit()
            return _nota_una(conn, project_id, cur.lastrowid)
        finally:
            conn.close()

    nota = await asyncio.to_thread(_crear)
    if nota is None:
        raise HTTPException(status_code=409, detail=f'máximo {MAX_NOTAS} notas por proyecto')
    return nota


@router.put('/{project_id}/notas/{nota_id}')
async def actualizar_nota(project_id: int, nota_id: int, payload: dict = Body(...)):
    """Actualiza una nota (parcial: lo que no viene se conserva)."""
    def _actualizar():
        from datetime import datetime
        conn = get_db()
        try:
            previa = _nota_una(conn, project_id, nota_id)
            if not previa:
                return None
            c = _nota_campos(payload, previa)
            conn.execute(
                '''UPDATE project_notes
                     SET titulo = ?, cuerpo = ?, secreta = ?, color = ?,
                         x = ?, y = ?, w = ?, h = ?, actualizado = ?
                   WHERE id = ? AND project_id = ?''',
                (c['titulo'], c['cuerpo'], c['secreta'], c['color'],
                 c['x'], c['y'], c['w'], c['h'], datetime.now().isoformat(),
                 nota_id, project_id))
            conn.commit()
            return _nota_una(conn, project_id, nota_id)
        finally:
            conn.close()

    nota = await asyncio.to_thread(_actualizar)
    if nota is None:
        raise HTTPException(status_code=404, detail='nota inexistente')
    return nota


@router.delete('/{project_id}/notas/{nota_id}')
async def borrar_nota(project_id: int, nota_id: int):
    """Borra una nota del proyecto."""
    def _borrar():
        conn = get_db()
        try:
            cur = conn.execute('DELETE FROM project_notes WHERE id = ? AND project_id = ?',
                               (nota_id, project_id))
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()

    if not await asyncio.to_thread(_borrar):
        raise HTTPException(status_code=404, detail='nota inexistente')
    return {'ok': True}
