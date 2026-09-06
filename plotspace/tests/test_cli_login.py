"""
Tests del login web sin terminal (plotspace/core/cli_login.py).

Flujo «Agregar cuenta nueva» sin terminal: el backend corre el login del CLI en
un PTY OCULTO, captura la URL de autorización (la página de la IA) y el frontend
la abre directo en el navegador. Para los CLIs con flujo de "pegar código"
(Claude), el usuario pega el código en Jarvis y el backend lo escribe al PTY.

El parser de URL se testea con la salida REAL capturada de claude/codex. El PTY
se testea con un fake (bash) que imita el login — sin tocar credenciales reales.
"""
import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import plotspace.core.cli_login as cl


# Salidas REALES capturadas (probe seguro con config aislada) ────────────────
CLAUDE_OUT = (
    "Opening browser to sign in…\n"
    "If the browser didn't open, visit: https://claude.com/cai/oauth/authorize?"
    "code=true&client_id=9d1c250a&response_type=code&redirect_uri=https%3A%2F%2F"
    "platform.claude.com%2Foauth%2Fcode%2Fcallback&state=VAzqrd\n"
    "Paste code here if prompted > "
)
CODEX_OUT = (
    "Starting local login server on http://localhost:1455.\n"
    "If your browser did not open, navigate to this URL to authenticate:\n\n"
    "https://auth.openai.com/oauth/authorize?response_type=code&client_id=app_EMo&"
    "redirect_uri=http%3A%2F%2Flocalhost%3A1455%2Fauth%2Fcallback&state=dfdg\n"
)
# Salida REAL de `codex login --device-auth` (el flujo nuevo, sin callback).
CODEX_DEVICE_OUT = (
    "\nWelcome to Codex [v0.141.0]\n"
    "OpenAI's command-line coding agent\n\n"
    "Follow these steps to sign in with ChatGPT using device code authorization:\n\n"
    "1. Open this link in your browser and sign in to your account\n"
    "   https://auth.openai.com/codex/device\n\n"
    "2. Enter this one-time code (expires in 15 minutes)\n"
    "   1VZ5-14MVV\n\n"
    "Device codes are a common phishing target. Never share this code.\n"
)


# ── parser de URL de autorización ───────────────────────────────────────────

def test_url_authz_claude():
    url = cl._url_authz(CLAUDE_OUT)
    assert url.startswith("https://claude.com/cai/oauth/authorize?")
    assert url.endswith("state=VAzqrd")   # sin puntuación de cola, completa


def test_url_authz_codex_ignora_localhost():
    url = cl._url_authz(CODEX_OUT)
    # Devuelve la URL de authorize (la que abre el usuario), NO el server local
    # de callback http://localhost:1455 (aunque ese localhost aparezca dentro del
    # redirect_uri de la URL buena, que es legítimo).
    assert url.startswith("https://auth.openai.com/oauth/authorize?")
    assert not url.startswith("http://localhost")


def test_url_authz_sin_url():
    assert cl._url_authz("nada por aca\n") is None


def test_detecta_paste_code():
    assert cl._es_paste_code(CLAUDE_OUT) is True    # Claude pide pegar código
    assert cl._es_paste_code(CODEX_OUT) is False    # Codex usa callback


def test_codex_device_auth_url_y_codigo():
    # El flujo device-auth: la URL es la página de device (sin 'authorize' ni
    # localhost) y hay un código de un solo uso que el usuario ingresa ahí.
    url = cl._url_authz(CODEX_DEVICE_OUT)
    assert url == "https://auth.openai.com/codex/device"
    assert cl._device_code(CODEX_DEVICE_OUT) == "1VZ5-14MVV"
    assert cl._es_paste_code(CODEX_DEVICE_OUT) is False   # no se pega en el CLI
    # las URLs de callback (minúsculas) NO disparan un falso device-code
    assert cl._device_code(CODEX_OUT) is None
    assert cl._device_code(CLAUDE_OUT) is None


# Salida REAL de `agy auth login` (antigravity 1.0.16, probe en HOME sandbox):
# el TUI envuelve la URL por ancho de pantalla (continuaciones con sangría) y
# pide pegar el código de autorización EN el CLI.
AGY_OUT = (
    " Select login method:\n"
    " > 1. Google OAuth\n"
    "2. Use a Google Cloud project\n"
    "\n"
    " [Use arrow keys to navigate, Enter to select]Your browser should open automatically. If not:\n"
    "\n"
    " https://accounts.google.com/o/oauth2/auth?access_type=offline&client_id=1071006060591-tmhssin2h21lcre235vtolojh4g403ep\n"
    " .apps.googleusercontent.com&code_challenge=aBXYtVUcwCmM27zdeWpJBoeEQLe2mDkDa&code_challenge_method=S256&prompt=consent&r\n"
    " edirect_uri=https%3A%2F%2Fantigravity.google%2Foauth-callback&response_type=code&scope=openid&state=fdXLPZmbIFllmCCIsOEV2g\n"
    "\n"
    " If you aren't automatically redirected, paste the authorization code below:\n"
    "\n"
    " authorization code...\n"
)


def test_url_authz_agy_desenvuelve_la_url_partida():
    # El TUI de agy parte la URL en 3 líneas (sangría de continuación): el parser
    # la re-une COMPLETA — truncarla rompía el login (faltaba el redirect_uri).
    url = cl._url_authz(AGY_OUT)
    assert url.startswith("https://accounts.google.com/o/oauth2/auth?")
    assert ".apps.googleusercontent.com" in url                  # cruzó la 1ª línea
    assert "antigravity.google%2Foauth-callback" in url          # cruzó la 2ª línea
    assert url.endswith("state=fdXLPZmbIFllmCCIsOEV2g")          # completa, sin cola
    # el párrafo siguiente (línea en blanco de por medio) NO se pega a la URL
    assert "If" not in url


def test_agy_es_paste_code_y_sin_falso_device():
    # agy pide pegar el código EN el CLI («paste the authorization code below»).
    assert cl._es_paste_code(AGY_OUT) is True
    # Un run MAYÚS-guion casual en la URL (base64url) no debe leerse como
    # device-code cuando hay prompt de paste: el paste manda (ver _leer_url).
    con_falso = AGY_OUT.replace("code_challenge=aBXY", "code_challenge=WXYZ-1234&x=aBXY")
    assert cl._es_paste_code(con_falso) is True
    assert cl._device_code(con_falso) == "WXYZ-1234"   # el falso positivo EXISTE…
    # …por eso _leer_url lo anula cuando hay prompt de paste (paste manda).


def test_login_manual_qwen_opencode_y_pi():
    # qwen 0.19+ (wizard «Connect a Provider»: ModelStudio/región/plan), opencode
    # (picker de proveedor) y pi (login = `/login` dentro del TUI, NO existe un
    # subcomando `pi login` — verificado en el dist 0.85.1) NO se automatizan a
    # ciegas: van por alta MANUAL (comando en una terminal + watcher). Los CON
    # login web quedan en ARGV — grok salió del modo manual: `grok login` es un
    # device-flow automatizable (probe 2026-07-10, grok 0.2.93), y Cursor es un
    # browserflow con poll (ver CURSOR_OUT).
    assert set(cl.LOGIN_MANUAL) == {"qwen", "opencode", "pi"}
    assert not (set(cl.LOGIN_MANUAL) & set(cl.LOGIN_ARGV))
    assert set(cl.LOGIN_ARGV) == {"claude", "codex", "antigravity", "grok", "cursor"}
    assert cl.LOGIN_ARGV["grok"] == ["grok", "login"]
    assert cl.LOGIN_ARGV["cursor"] == ["cursor-agent", "login"]


# Salida REAL de `grok login` (grok 0.2.93, probe en HOME sandbox 2026-07-10):
# device-flow de x.ai — imprime la URL (con el user_code embebido) + el código
# para CONFIRMAR en el navegador, abre el browser solo (cmd.exe /c start en WSL)
# y queda esperando la aprobación; al aprobar escribe ~/.grok/auth.json y sale.
GROK_OUT = (
    "\nTo sign in, open this URL in your browser:\n\n"
    "  https://accounts.x.ai/oauth2/device?user_code=2R3K-7E7N\n\n"
    "Confirm this code in your browser:\n\n"
    "  2R3K-7E7N\n\n"
    "Only continue with a code you requested. Don't share it with anyone.\n\n"
    "Waiting for authorization...\n"
)


def test_grok_device_flow_url_y_codigo():
    url = cl._url_authz(GROK_OUT)
    assert url == "https://accounts.x.ai/oauth2/device?user_code=2R3K-7E7N"
    assert cl._device_code(GROK_OUT) == "2R3K-7E7N"
    assert cl._es_paste_code(GROK_OUT) is False   # se confirma en el browser, no se pega


# Salida de `agent login` (Cursor CLI 2026.09.02, del bundle oficial): browserflow
# con challenge/verifier PKCE — imprime la URL del CLI (cursor.com/loginDeepControl)
# y QUEDA POLEANDO hasta que el usuario autoriza en el navegador; recién entonces
# escribe ~/.config/cursor/auth.json (el watcher lo captura). Con
# NO_OPEN_BROWSER=1 no abre browser ni imprime QR a menos que se pida ('q').
CURSOR_OUT = (
    "\nWaiting for browser authentication...\n"
    "Open a browser and navigate to this link: "
    "https://cursor.com/loginDeepControl?challenge=oP5mkDyfnmJ99M1OKL6V3-0-PYkkBt9LZ1dGj7j9VI4"
    "&uuid=39052162-8cf2-48c0-83b4-6e1ca195fb9c&mode=login&redirectTarget=cli\n\n"
    "Press q to show a QR code to log in from another device.\n\n"
)


def test_cursor_browserflow_url_y_modo():
    url = cl._url_authz(CURSOR_OUT)
    assert url.startswith("https://cursor.com/loginDeepControl?")
    assert "challenge=" in url and "uuid=" in url      # completa, sin cortar
    # es un poll del backend de Cursor, no se pide ni pega código en el PTY
    assert cl._es_paste_code(CURSOR_OUT) is False
    assert cl._device_code(CURSOR_OUT) is None


def test_spawn_cursor_no_browser_y_resuelve_local_bin(monkeypatch, tmp_path):
    # Cursor: el login corre con NO_OPEN_BROWSER=1 (nosotros capturamos la URL) y
    # el binario se resuelve contra ~/.local/bin (el dir del curl-installer), que
    # puede no estar en el PATH del server.
    import plotspace.core.cli_accounts as ca

    bindir = tmp_path / "localbin"
    bindir.mkdir()
    home = str(tmp_path / "home")
    monkeypatch.setattr(ca, "HOME_DIR", home)
    fake = bindir / "cursor-agent"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.setattr(cl, "_cursor_bin_dir", lambda: str(bindir))
    monkeypatch.setitem(os.environ, "PATH", "/usr/bin:/bin")

    capturado = {}

    class _FakeProc:
        def terminate(self, force=False):
            pass

    def _fake_spawn(argv, env=None, dimensions=None):
        capturado["argv"] = list(argv)
        capturado["env"] = dict(env or {})
        return _FakeProc()

    monkeypatch.setattr(cl.ptyprocess.PtyProcess, "spawn", staticmethod(_fake_spawn))
    proc = cl._spawn("cursor")
    assert proc is not None
    # resuelto del dir del curl-installer, con ruta absoluta
    assert capturado["argv"][0] == str(fake)
    assert capturado["env"].get("NO_OPEN_BROWSER") == "1"
    cl.cerrar("cursor")


def test_env_antepone_el_bin_de_nvm(monkeypatch):
    # El server puede correr con un PATH sin ~/.nvm/**/bin (arrancado fuera de una
    # shell interactiva — pasó con el uvicorn vivo 2026-07-10): ahí codex/grok/
    # qwen/opencode resuelven al shim de Windows (`exec: node: not found`) y el
    # login muere sin URL → 502 en /login/iniciar → "no se abre nada". _env()
    # antepone el bin del Node de WSL, mismo gotcha que el auto-lanzamiento de
    # terminales (terminals._prefijo_path_wsl / [[codex-wsl-path-node]]).
    monkeypatch.setattr(cl, "_nvm_bin_dir", lambda: "/fake/nvm/bin")
    monkeypatch.setitem(os.environ, "PATH", "/usr/bin:/bin")
    env = cl._env()
    assert env["PATH"].split(os.pathsep)[0] == "/fake/nvm/bin"
    assert env["PATH"].endswith("/usr/bin:/bin")
    # idempotente: si el bin ya está en el PATH, no se duplica
    monkeypatch.setitem(os.environ, "PATH", "/fake/nvm/bin:/usr/bin")
    assert cl._env()["PATH"].split(os.pathsep).count("/fake/nvm/bin") == 1


def test_env_sin_nvm_no_rompe(monkeypatch):
    # Entorno sin Node de nvm (p.ej. CI): _env() deja el PATH como está.
    monkeypatch.setattr(cl, "_nvm_bin_dir", lambda: None)
    monkeypatch.setitem(os.environ, "PATH", "/usr/bin")
    assert cl._env()["PATH"] == "/usr/bin"


def test_spawn_resuelve_el_binario_con_el_path_del_env(monkeypatch, tmp_path):
    # ptyprocess resuelve argv[0] con el PATH del PROCESO padre, NO con el del
    # env que le pasamos: con el PATH pelado del server, `codex` seguía cayendo
    # al shim de Windows aunque _env() ya trajera el bin del nvm adelante.
    # _spawn debe resolver argv[0] contra el PATH del env (ruta absoluta).
    bindir = tmp_path / "nvmbin"
    bindir.mkdir()
    fake = bindir / "fakecli"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.setattr(cl, "_nvm_bin_dir", lambda: str(bindir))
    monkeypatch.setitem(os.environ, "PATH", "/usr/bin:/bin")   # sin el bindir
    monkeypatch.setitem(cl.LOGIN_ARGV, "faketipo", ["fakecli", "login"])

    capturado = {}

    class _FakeProc:
        def terminate(self, force=False):
            pass

    def _fake_spawn(argv, env=None, dimensions=None):
        capturado["argv"] = list(argv)
        return _FakeProc()

    monkeypatch.setattr(cl.ptyprocess.PtyProcess, "spawn", staticmethod(_fake_spawn))
    assert cl._spawn("faketipo") is not None
    assert capturado["argv"][0] == str(fake)   # absoluto, del bin del nvm
    cl.cerrar("faketipo")


def test_prekeys_manda_enter_en_el_menu(monkeypatch):
    # agy imprime la URL recién DESPUÉS de un Enter en «Select login method» —
    # el prekey lo manda solo. El fake imita ese menú con un read.
    script = ('echo "Select login method:";'
              'read sel;'
              'echo "visit https://accounts.test/o/oauth2/auth?z=9";'
              'echo "paste the authorization code below:";'
              'read code')
    monkeypatch.setitem(cl.LOGIN_ARGV, "faketipo", ["bash", "-c", script])
    monkeypatch.setitem(cl._PREKEYS, "faketipo", [("select login method", "\r")])
    url, paste, codigo = asyncio.run(cl.iniciar("faketipo", timeout_s=8))
    assert url == "https://accounts.test/o/oauth2/auth?z=9"
    assert paste is True
    assert codigo is None
    cl.cerrar("faketipo")


# ── PTY real con un fake login (bash) ───────────────────────────────────────

def test_iniciar_captura_url_y_paste_de_un_fake(monkeypatch):
    # fake login: imprime una URL de authorize + el prompt de pegar código y
    # espera una línea (el código). Imita a `claude auth login`.
    script = ('echo "visit: https://login.test/oauth/authorize?x=1";'
              'echo "Paste code here >";'
              'read code; echo "got:$code" > "$FAKE_OUT"')
    monkeypatch.setitem(cl.LOGIN_ARGV, "faketipo", ["bash", "-c", script])

    url, paste, codigo = asyncio.run(cl.iniciar("faketipo", timeout_s=4))
    assert url == "https://login.test/oauth/authorize?x=1"
    assert paste is True
    assert codigo is None                    # este fake no usa device-code
    assert "faketipo" in cl._sesiones        # el PTY queda vivo esperando el código

    cl.cerrar("faketipo")
    assert "faketipo" not in cl._sesiones     # cerrar lo limpia


def test_enviar_codigo_escribe_al_pty(monkeypatch, tmp_path):
    out = tmp_path / "fake.out"
    script = ('echo "go: https://login.test/oauth/authorize?y=2";'
              'echo "Paste code here >";'
              f'read code; echo "got:$code" > "{out}"')
    monkeypatch.setitem(cl.LOGIN_ARGV, "faketipo", ["bash", "-c", script])

    url, _, _ = asyncio.run(cl.iniciar("faketipo", timeout_s=4))
    assert url.endswith("authorize?y=2")
    ok = asyncio.run(cl.enviar_codigo("faketipo", "MICODIGO"))
    assert ok is True
    # el fake escribe el código recibido a un archivo → confirma que llegó al PTY
    import time
    for _ in range(20):
        if out.exists() and "MICODIGO" in out.read_text():
            break
        time.sleep(0.1)
    assert out.exists() and "got:MICODIGO" in out.read_text()
    cl.cerrar("faketipo")


def test_iniciar_tipo_sin_login_devuelve_none():
    url, paste, codigo = asyncio.run(cl.iniciar("inexistente", timeout_s=1))
    assert url is None and paste is False and codigo is None


def test_spawn_codex_usa_home_fresco_no_el_de_la_activa(monkeypatch, tmp_path):
    # BUG fix: el login de una cuenta codex NUEVA debe spawnearse con CODEX_HOME =
    # un staging dir AISLADO y FRESCO (`_codex_login`), JAMÁS el de la cuenta ACTIVA.
    # Loguear OTRA cuenta de OpenAI en el home de la activa reescribe su auth.json y
    # la revoca por reuso de refresh token. Acá verificamos el env del spawn.
    import plotspace.core.cli_accounts as ca
    from plotspace.tests._harness import fresh_db

    fresh_db()
    home = str(tmp_path / "home")
    os.makedirs(os.path.join(home, ".codex"))
    snaps = str(tmp_path / "snaps")
    monkeypatch.setattr(ca, "HOME_DIR", home)
    monkeypatch.setattr(ca, "SNAPSHOTS_DIR", snaps)
    monkeypatch.delenv("CODEX_HOME", raising=False)

    # cuenta A activa, con su dir aislado y su symlink estable
    with open(os.path.join(home, ".codex", "auth.json"), "w", encoding="utf-8") as f:
        f.write('{"tokens": {"account_id": "ACC-A"}}')
    pa = ca.capturar_actual("codex", "A")
    dir_a = ca.codex_home(pa["id"])
    activo = ca.codex_home_activo()              # symlink → A

    capturado = {}

    class _FakeProc:
        def terminate(self, force=False):
            pass

    def _fake_spawn(argv, env=None, dimensions=None):
        capturado["env"] = dict(env or {})
        return _FakeProc()

    monkeypatch.setattr(cl.ptyprocess.PtyProcess, "spawn", staticmethod(_fake_spawn))

    proc = cl._spawn("codex")
    assert proc is not None
    ch = capturado["env"].get("CODEX_HOME")
    assert ch is not None
    assert os.path.basename(ch) == "_codex_login"            # staging fresco, no un dir de cuenta
    assert os.path.realpath(ch) != os.path.realpath(dir_a)   # NO el dir de la activa
    assert os.path.realpath(ch) != os.path.realpath(activo)  # NO el symlink de la activa
    cl.cerrar("codex")


def _home_agy_logueado(tmp_path):
    """HOME con una sesión de agy 1.1.x (token JSON) — el estado real del usuario."""
    home = str(tmp_path / "home")
    d = os.path.join(home, ".gemini", "antigravity-cli")
    os.makedirs(d)
    tok = os.path.join(d, "antigravity-oauth-token")
    with open(tok, "w", encoding="utf-8") as f:
        f.write('{"access_token": "VIVO"}')
    os.utime(tok, (1_000_000, 1_000_000))
    return home, tok


class _ProcMudo:
    def terminate(self, force=False):
        pass


def test_spawn_agy_aparta_el_token_y_cerrar_lo_restaura(monkeypatch, tmp_path):
    """Con sesión activa, `agy auth login` se auto-re-loguea con el token cacheado
    y NUNCA imprime la URL (el menú «Select login method» solo aparece
    deslogueado) → 502 en producción. _spawn aparta el token con rename (mtime
    intacto) para que el login arranque como HOME fresco, y cerrar() lo devuelve
    IDÉNTICO si el login se abandona — misma huella → el watcher no captura un
    perfil fantasma."""
    import plotspace.core.cli_accounts as ca
    home, tok = _home_agy_logueado(tmp_path)
    st_antes = os.stat(tok)
    monkeypatch.setattr(ca, "HOME_DIR", home)
    monkeypatch.setattr(cl.ptyprocess.PtyProcess, "spawn",
                        staticmethod(lambda argv, env=None, dimensions=None: _ProcMudo()))

    assert cl._spawn("antigravity") is not None
    assert not os.path.exists(tok)                        # apartado → agy deslogueado
    assert os.path.isfile(tok + ".jarvis-prelogin")

    cl.cerrar("antigravity")                              # abandono → restaurar tal cual
    assert open(tok, encoding="utf-8").read() == '{"access_token": "VIVO"}'
    assert int(os.stat(tok).st_mtime) == int(st_antes.st_mtime)   # rename conserva mtime
    assert not os.path.exists(tok + ".jarvis-prelogin")


def test_cerrar_agy_con_login_exitoso_no_pisa_el_token_nuevo(monkeypatch, tmp_path):
    # Login OK: agy escribió el token de la cuenta NUEVA → cerrar() descarta el
    # backup en vez de pisar la sesión recién conectada con la vieja.
    import plotspace.core.cli_accounts as ca
    home, tok = _home_agy_logueado(tmp_path)
    monkeypatch.setattr(ca, "HOME_DIR", home)
    monkeypatch.setattr(cl.ptyprocess.PtyProcess, "spawn",
                        staticmethod(lambda argv, env=None, dimensions=None: _ProcMudo()))

    assert cl._spawn("antigravity") is not None
    with open(tok, "w", encoding="utf-8") as f:           # el login escribe el nuevo
        f.write('{"access_token": "NUEVO"}')
    cl.cerrar("antigravity")
    assert open(tok, encoding="utf-8").read() == '{"access_token": "NUEVO"}'
    assert not os.path.exists(tok + ".jarvis-prelogin")


def test_spawn_agy_self_heal_de_bak_huerfano(monkeypatch, tmp_path):
    # Un login interrumpido feo (crash/restart) puede dejar el .jarvis-prelogin
    # huérfano con el token adentro. El próximo _spawn lo repone antes de volver
    # a apartarlo — la sesión no se pierde para siempre.
    import plotspace.core.cli_accounts as ca
    home, tok = _home_agy_logueado(tmp_path)
    os.rename(tok, tok + ".jarvis-prelogin")              # estado huérfano
    monkeypatch.setattr(ca, "HOME_DIR", home)
    monkeypatch.setattr(cl.ptyprocess.PtyProcess, "spawn",
                        staticmethod(lambda argv, env=None, dimensions=None: _ProcMudo()))

    assert cl._spawn("antigravity") is not None
    cl.cerrar("antigravity")                              # abandono
    assert open(tok, encoding="utf-8").read() == '{"access_token": "VIVO"}'


def test_login_cancelar_corta_el_watcher():
    # El front cancela al cerrar el modal: el watcher se cancela YA (su handler
    # cierra el PTY y repone el token de agy) en vez de esperar 5 min.
    from plotspace.routers import cuentas as rc

    async def run():
        async def dormir():
            await asyncio.sleep(30)
        t = asyncio.get_event_loop().create_task(dormir())
        rc._watchers["faketipo"] = t
        r = await rc.login_cancelar(rc.CancelarLogin(tipo="faketipo"))
        for _ in range(3):
            await asyncio.sleep(0)
        return r, t.cancelled()

    r, cancelado = asyncio.run(run())
    assert r["ok"] is True and cancelado is True
    assert "faketipo" not in rc._watchers


def test_enviar_codigo_sin_sesion():
    assert asyncio.run(cl.enviar_codigo("nada", "x")) is False


if __name__ == "__main__":
    import traceback

    class _MP:
        def __init__(self): self._u = []
        def setitem(self, d, k, v):
            tiene = k in d
            self._u.append(("item", d, k, d.get(k), tiene))
            d[k] = v
        def setattr(self, obj, name, val):
            self._u.append(("attr", obj, name, getattr(obj, name), True))
            setattr(obj, name, val)
        def delenv(self, name, raising=True):
            if name in os.environ:
                self._u.append(("item", os.environ, name, os.environ.get(name), True))
                os.environ.pop(name, None)
        def undo(self):
            for entry in reversed(self._u):
                kind = entry[0]
                if kind == "item":
                    _, d, k, v, tiene = entry
                    if tiene: d[k] = v
                    else: d.pop(k, None)
                else:
                    _, obj, name, v, _t = entry
                    setattr(obj, name, v)

    fallos = 0
    for nombre, fn in sorted(globals().items()):
        if nombre.startswith("test_") and callable(fn):
            mp = _MP()
            import inspect
            kw = {}
            params = inspect.signature(fn).parameters
            if "monkeypatch" in params: kw["monkeypatch"] = mp
            if "tmp_path" in params:
                import tempfile, pathlib
                kw["tmp_path"] = pathlib.Path(tempfile.mkdtemp())
            try:
                fn(**kw); print("ok", nombre)
            except Exception:
                fallos += 1; print("FAIL", nombre); traceback.print_exc()
            finally:
                mp.undo()
    sys.exit(1 if fallos else 0)
