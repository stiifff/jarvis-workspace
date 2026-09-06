"""
Login web sin terminal — el «te abre directo la página de la IA» del flujo
«Agregar cuenta nueva».

Idea: el usuario NO ve ninguna terminal. El backend corre el comando de login del
CLI en un PTY OCULTO, captura la URL de autorización (la página web de la IA) y el
frontend la abre directo en el navegador. Según el CLI:
  - Claude: imprime la URL + un prompt «Paste code here». Tras autorizar, la IA
    le da un CÓDIGO al usuario; el usuario lo pega en Jarvis y lo escribimos al
    PTY (enviar_codigo) → Claude lo canjea y escribe la credencial.
  - Codex: imprime la URL con callback a localhost:1455 → al autorizar, el
    navegador pega solo en ese server local y Codex completa (sin código).

En ambos casos, cuando la credencial cambia, el watcher (cuenta_watch.py) detecta
la cuenta nueva y la guarda. El PTY se mantiene vivo entre iniciar() y el código/
callback (su proceso corre el server de callback); se cierra al terminar el watcher.

Tests: plotspace/tests/test_cli_login.py (parser con salida real + PTY con un fake).
"""
import asyncio
import os
import re
import select
import shutil

# ptyprocess se difiere al único punto que lo usa (el login interactivo por
# PTY oculto): importarlo arriba arrastraba pty/termios/fcntl a la cadena de
# routers entera.
try:
    import ptyprocess
except ImportError:                                # pragma: no cover - Windows
    ptyprocess = None

# URL: hasta el primer espacio/comilla/ESC. El rstrip saca puntuación de cola.
_URL_RE = re.compile(r'https?://[^\s\'"\x1b]+')

# Comando de login por CLI (corre en el PTY oculto y dispara el OAuth nativo).
# Codex usa el login por navegador (callback a localhost:1455): el usuario inicia
# sesión y la pestaña vuelve sola, SIN pegar ningún código. Si en WSL el callback
# no vuelve del navegador (resolución IPv6 de localhost), se arregla UNA vez por
# máquina con `netsh interface ipv6 set prefixpolicy ::ffff:0:0/96 60 4`.
# Antigravity (agy) pide elegir «Google OAuth» en un menú antes de imprimir la
# URL → _PREKEYS le manda ese Enter. Grok es device-flow puro: `grok login`
# imprime la URL (accounts.x.ai/oauth2/device?user_code=…) + el código para
# CONFIRMAR en el navegador (_device_code), abre el browser solo (cmd.exe /c
# start) y queda «Waiting for authorization…»; al aprobar escribe ~/.grok/
# auth.json (sin borrar el previo) y el watcher lo captura. Re-dispara el flujo
# aun con sesión activa → sirve para agregar una SEGUNDA cuenta.
# (Auditoría 2026-07-10 con probes reales en HOME sandbox, versiones:
#  claude 2.1.207 · codex 0.144.0 · agy 1.1.1 · qwen 0.19.8 · opencode 1.17.12
#  · grok 0.2.93. Cursor CLI 2026-09-02 verificada contra el bundle del
#  paquete: `agent login` imprime la URL del browserflow
#  (https://cursor.com/loginDeepControl?challenge=…&uuid=…), NO abre nada con
#  NO_OPEN_BROWSER=1, polea hasta que el usuario autoriza y recién ahí escribe
#  auth.json → el watcher lo captura. Sin prefiltro de "ya logueado": el flujo
#  re-dispara aun con sesión activa (sirve para la 2da cuenta).)
LOGIN_ARGV = {
    "claude":   ["claude", "auth", "login", "--claudeai"],
    "codex":    ["codex", "login"],
    "antigravity": ["agy", "auth", "login"],
    "grok":     ["grok", "login"],
    # El binario del PTY oculto es `cursor-agent` (legacy del curl-installer)
    # y no `agent`: en el PATH del server suele haber OTROS `agent` sueltos
    # (misma razón que la detección en core/clis.py).
    "cursor":   ["cursor-agent", "login"],
}

# CLIs cuyo login es un wizard interactivo con decisiones del usuario (proveedor,
# región, plan…) que NO se puede automatizar a ciegas desde un PTY oculto:
#   - qwen 0.19+: «Connect a Provider» → ModelStudio/región/plan (3 pasos).
#   - opencode: picker de proveedor + método (API key u OAuth según proveedor).
#   - pi (Earendil): el login es `/login` DENTRO del TUI (picker de proveedor →
#     método → OAuth con URL/device-code) — NO hay subcomando `pi login` (ver
#     dist 0.85.1: solo `pi auth check|print-api-key|print-bearer-token`).
# Para estos, el alta es MANUAL: el usuario corre el comando en una terminal
# (Jarvis se la puede abrir con el wizard andando — botón del modal de alta) y el
# watcher (cuenta_watch.vigilar_login) detecta la credencial nueva y la guarda sola.
LOGIN_MANUAL = {
    "qwen":     "qwen",
    "opencode": "opencode auth login",
    "pi":       "pi",
}

# Teclas previas por CLI: (frase que espera en pantalla → tecla a mandar). agy
# muestra «Select login method: > 1. Google OAuth» y necesita UN Enter para
# disparar el OAuth e imprimir la URL.
_PREKEYS = {
    "antigravity": [("select login method", "\r")],
}

# Timeout de captura de URL por CLI (segundos). El default contempla arranques
# fríos lentos bajo carga del swarm; agy además pasa por su menú.
_TIMEOUTS = {"antigravity": 50}
TIMEOUT_DEFAULT = 35

# Sesiones de login vivas (un PTY por tipo, esperando el código/callback).
_sesiones: dict = {}


def _limpiar(s):
    """Saca códigos ANSI/OSC para poder parsear la URL de la salida del CLI."""
    s = re.sub(r'\x1b\[[0-9;?]*[A-Za-z]', '', s)
    s = re.sub(r'\x1b\][0-9];[^\x07]*\x07', '', s)
    return s


def _desenvolver(texto):
    """Re-une las líneas que un TUI partió por ancho de pantalla (agy renderiza
    la URL envuelta: línea cortada + continuación con sangría). Pega una línea
    con la siguiente cuando el corte es UN solo salto seguido de espacios —
    un párrafo nuevo (línea en blanco de por medio) NO se pega."""
    return re.sub(r'(?<!\n)\r?\n[ \t]+(?=\S)', '', texto)


def _url_authz(texto):
    """La URL de AUTORIZACIÓN de la salida del login (la que abre el usuario).
    Descarta el server local de callback (localhost:1455 de codex). None si no hay."""
    plano = _desenvolver(_limpiar(texto))
    cand = [u.rstrip('.,)>…') for u in _URL_RE.findall(plano)]
    authz = [u for u in cand if 'authorize' in u.lower() or '/oauth2/auth' in u.lower()]
    if authz:
        return authz[0]
    externas = [u for u in cand if 'localhost' not in u and '127.0.0.1' not in u]
    if externas:
        return externas[0]
    return cand[0] if cand else None


def _es_paste_code(texto):
    """¿El CLI pide pegar un código (vs callback automático)? claude dice
    «Paste code here…»; agy dice «paste the authorization code below»."""
    t = _limpiar(texto).lower()
    return 'paste code' in t or 'authorization code below' in t


# Código de un solo uso del flujo device-auth: 4 + 4-8 alfanuméricos en MAYÚS con
# guion (ej. "1VZ5-14MVV"). En mayúsculas a propósito → no matchea state/UUID de
# las URLs de callback (que van en minúsculas).
_CODE_RE = re.compile(r'\b[A-Z0-9]{4}-[A-Z0-9]{4,8}\b')


def _device_code(texto):
    """El código de verificación del device-auth (codex login --device-auth): el
    usuario lo ingresa en la página de login. None si el CLI no usa device-code."""
    m = _CODE_RE.search(_limpiar(texto))
    return m.group(0) if m else None


def _nvm_bin_dir():
    """Dir `bin` del Node de WSL (node + codex/qwen/opencode/grok del nvm).
    Delega en el helper de routers/terminals.py (misma lógica, testeada allá).
    Lazy import — patrón del repo para dependencias core↔routers; terminals no
    importa este módulo, así que no hay ciclo. None si no hay nvm."""
    try:
        from plotspace.routers.terminals import _nvm_bin_dir as _helper
        return _helper()
    except Exception:
        return None


def _cursor_bin_dir():
    """Dir donde el curl-installer de Cursor CLI deja sus symlinks (agent /
    cursor-agent): ~/.local/bin. El PATH del server suele no traerlo."""
    try:
        from plotspace.core import cli_accounts as _ca
        return os.path.join(_ca.HOME_DIR, ".local", "bin")
    except Exception:
        return os.path.join(os.path.expanduser("~"), ".local", "bin")


def _env():
    env = os.environ.copy()
    env.pop('ANTHROPIC_API_KEY', None)
    # Que el CLI NO abra un browser propio VÍA esas vars (la URL igual se
    # devuelve al frontend; en WSL los CLIs abren el navegador de Windows por
    # cmd.exe/xdg-open→wslview, que no dependen de BROWSER/DISPLAY).
    env.pop('BROWSER', None)
    env.pop('DISPLAY', None)
    # El server puede correr con un PATH SIN el bin del Node de WSL (arrancado
    # fuera de una shell interactiva — pasó con el uvicorn vivo 2026-07-10): ahí
    # `codex`/`grok`/`qwen`/`opencode` resuelven al shim de Windows (`exec: node:
    # not found`) y el login muere sin URL → 502 "No se pudo obtener la página".
    # Mismo gotcha que el auto-lanzamiento de terminales (terminals.
    # _prefijo_path_wsl / memoria codex-wsl-path-node): se antepone el bin.
    nvm = _nvm_bin_dir()
    path = env.get('PATH', '')
    if nvm and nvm not in path.split(os.pathsep):
        env['PATH'] = nvm + os.pathsep + path if path else nvm
    return env


# ── Antigravity: apartar el token durante el alta ───────────────────────────
# Con sesión activa, `agy auth login` NO muestra el menú «Select login method»:
# se auto-re-loguea con el token cacheado (y puede clavarse en el prompt de
# confianza del workspace) → nunca imprime la URL → 502. Se aparta el token con
# os.rename (mtime INTACTO) para que el login arranque como HOME fresco (menú →
# URL → paste). Si el login se abandona, cerrar() lo devuelve IDÉNTICO: misma
# huella (mtime+size+hash) → el watcher no captura un perfil fantasma. La sesión
# vieja además queda preservada como snapshot (el router llama a
# preservar_sesion_actual ANTES de iniciar). Sufijo propio y descriptivo para
# que un `ls` explique solo qué es.
_AGY_BAK = ".jarvis-prelogin"


def _agy_token():
    try:
        from plotspace.core import cli_accounts as _ca
        return _ca.antigravity_token_file()
    except Exception:
        return None


def _agy_apartar_token():
    tok = _agy_token()
    if not tok:
        return
    bak = tok + _AGY_BAK
    try:
        if os.path.isfile(bak) and not os.path.isfile(tok):
            os.rename(bak, tok)   # self-heal: un login previo interrumpido dejó el bak
        if os.path.isfile(tok):
            os.rename(tok, bak)
    except OSError:
        pass


def _agy_reponer_token():
    tok = _agy_token()
    if not tok:
        return
    bak = tok + _AGY_BAK
    try:
        if os.path.isfile(bak):
            if os.path.isfile(tok):
                os.remove(bak)        # login OK: manda el token NUEVO, chau backup
            else:
                os.rename(bak, tok)   # abandono: restaurar la sesión tal cual
    except OSError:
        pass


def cerrar(tipo):
    """Mata el PTY de login de `tipo` (si hay) y lo saca del registro. Para
    antigravity además resuelve el token apartado (reponer o descartar)."""
    proc = _sesiones.pop(tipo, None)
    if proc is not None:
        try:
            proc.terminate(force=True)
        except Exception:
            pass
    if tipo == "antigravity":
        _agy_reponer_token()


def _spawn(tipo):
    argv = LOGIN_ARGV.get(tipo)
    if not argv:
        return None
    cerrar(tipo)
    env = _env()
    # Copia antes de resolver: la resolución de cursor/ptyprocess reemplaza
    # argv[0] por una ruta absoluta y NO debe quedar pegada en LOGIN_ARGV.
    argv = list(argv)
    if tipo == "codex":
        # Alta de una cuenta codex NUEVA: el login va a un CODEX_HOME staging AISLADO
        # y FRESCO (`_codex_login`), NUNCA al de la cuenta activa. Reusar el home de la
        # activa era el bug: loguear OTRA cuenta de OpenAI ahí reescribía su auth.json
        # y la pisaba/revocaba (reuso de refresh token). El watcher (cuenta_watch.
        # vigilar_login_codex_nuevo) adopta este staging en un dir de cuenta propio al
        # detectar la credencial nueva, y repunta el symlink _codex_active.
        try:
            from plotspace.core import cli_accounts as _ca
            home = _ca.codex_login_home_nuevo()
            if home:
                env["CODEX_HOME"] = home
        except Exception:
            pass
    if tipo == "antigravity":
        # Ver _agy_apartar_token: sin esto, con sesión activa agy se auto-loguea
        # con el token cacheado y el menú/URL no aparecen nunca (502).
        _agy_apartar_token()
    if tipo == "cursor":
        # `agent login` abre un browser propio salvo NO_OPEN_BROWSER=1 — nosotros
        # capturamos la URL igual (el modal la abre en el navegador del usuario).
        env["NO_OPEN_BROWSER"] = "1"
        # El curl-installer deja los symlinks en ~/.local/bin, fuera del PATH del
        # server usual; se resuelve 'cursor-agent' (fallback 'agent') contra un
        # PATH extendido y se spawnae la ruta absoluta (mismo motivo que el nvm).
        bindir = _cursor_bin_dir()
        if bindir and bindir not in env["PATH"].split(os.pathsep):
            path_ext = env["PATH"] + os.pathsep + bindir
        else:
            path_ext = env["PATH"]
        for b in ("cursor-agent", "agent"):
            ruta = shutil.which(b, path=path_ext)
            if ruta:
                argv[0] = ruta
                break
    # ptyprocess resuelve argv[0] con el PATH del PROCESO (no el del env que le
    # pasamos): hay que resolverlo NOSOTROS contra el PATH extendido de _env()
    # (con el bin del nvm) y spawnear la ruta absoluta, o `codex`/`grok` caen al
    # shim de Windows cuando el server corre con un PATH pelado.
    resuelto = shutil.which(argv[0], path=env.get('PATH'))
    if resuelto:
        argv[0] = resuelto
    if ptyprocess is None:
        print('[cli-login] este sistema no tiene PTY de Unix: el login por '
              'terminal oculta no está disponible acá')
        return None
    try:
        # Ancho generoso: menos líneas envueltas en los TUIs (la URL de agy mide
        # ~600 chars; _desenvolver cubre lo que igual se parta).
        proc = ptyprocess.PtyProcess.spawn(argv, env=env, dimensions=(40, 200))
    except Exception:
        return None
    _sesiones[tipo] = proc
    return proc


def _leer_url(proc, timeout_s, prekeys=None):
    """Lee el PTY hasta capturar la URL de autorización o vencer el timeout.
    `prekeys` = [(frase_lower, tecla)] pendientes: cuando la frase aparece en
    pantalla se manda la tecla (ej. el Enter del menú «Google OAuth» de agy).
    Devuelve (url, paste_code, device_code). Síncrono (corre vía asyncio.to_thread)."""
    import time
    buf = ''
    pendientes = list(prekeys or [])
    fin = time.monotonic() + timeout_s
    while time.monotonic() < fin:
        try:
            r, _, _ = select.select([proc.fd], [], [], 0.3)
        except (OSError, ValueError):
            break
        if not r:
            continue
        try:
            data = os.read(proc.fd, 4096)
        except OSError:
            break
        if not data:
            break
        buf += data.decode(errors='replace')
        if pendientes and pendientes[0][0] in _limpiar(buf).lower():
            try:
                proc.write(pendientes.pop(0)[1].encode())
            except Exception:
                pass
        url = _url_authz(buf)
        if url:
            # Drenar ~1s más: el prompt «Paste code» (Claude) o el código de
            # device-auth (Codex) suelen llegar en el burst posterior a la URL.
            extra_fin = time.monotonic() + 1.0
            while time.monotonic() < extra_fin:
                try:
                    r2, _, _ = select.select([proc.fd], [], [], 0.2)
                except (OSError, ValueError):
                    break
                if not r2:
                    if _device_code(buf) or _es_paste_code(buf):
                        break
                    continue
                try:
                    extra = os.read(proc.fd, 4096)
                except OSError:
                    break
                if not extra:
                    break
                buf += extra.decode(errors='replace')
                if _device_code(buf):
                    break
            # Si el CLI pide pegar el código EN él (claude/agy), NO es device-auth:
            # el paste manda — un run MAYÚS-guion casual dentro de la URL (agy,
            # base64url del code_challenge/state) no debe desviar el modal.
            paste = _es_paste_code(buf)
            return url, paste, (None if paste else _device_code(buf))
    return None, False, None


async def iniciar(tipo, timeout_s=None):
    """Spawnea el login del CLI en un PTY oculto y captura la URL de autorización.
    Devuelve (url, paste_code, device_code) — o (None, False, None) si no se pudo.
    `device_code` sale del flujo device-auth (Codex): el usuario lo ingresa en la
    página de login. El PTY queda VIVO (esperando el código/callback); se cierra
    con cerrar(tipo)."""
    proc = await asyncio.to_thread(_spawn, tipo)
    if proc is None:
        return None, False, None
    espera = timeout_s if timeout_s is not None else _TIMEOUTS.get(tipo, TIMEOUT_DEFAULT)
    url, paste, codigo = await asyncio.to_thread(
        _leer_url, proc, espera, _PREKEYS.get(tipo))
    if not url:
        cerrar(tipo)
    return url, paste, codigo


async def enviar_codigo(tipo, codigo):
    """Escribe el código de autorización (el que la IA le dio al usuario) al PTY
    de login. Devuelve True si había un login en curso para ese tipo. Se manda
    con \\r (Enter real): los TUIs en modo raw (agy) no reaccionan a \\n, y en
    modo canónico (claude) ICRNL lo traduce igual a newline."""
    proc = _sesiones.get(tipo)
    if proc is None:
        return False
    try:
        await asyncio.to_thread(proc.write, (str(codigo).strip() + "\r").encode())
        return True
    except Exception:
        return False
