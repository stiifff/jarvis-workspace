"""
Tests del watcher de alta de cuenta (plotspace/core/cuenta_watch.py).

Flujo "Agregar cuenta nueva": Jarvis abre una terminal de login del CLI; este
watcher hace polling de los archivos de credencial del HOME y, cuando aparece una
cuenta NUEVA (email distinto al previo y no guardado, o huella distinta para
opencode), la captura sola con cli_accounts.capturar_actual.

Aislamiento: monkeypatch de ca.HOME_DIR + SNAPSHOTS_DIR a tempdirs (nunca toca el
HOME real ni data/). fresh_db() para la metadata. Async via asyncio.run.
"""
import asyncio
import base64
import json
import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from plotspace.tests._harness import fresh_db
import plotspace.core.cli_accounts as ca
import plotspace.core.cuenta_watch as cw


def _setup(monkeypatch):
    fresh_db()
    home = tempfile.mkdtemp(prefix="jarvis_home_")
    snaps = tempfile.mkdtemp(prefix="jarvis_snaps_")
    monkeypatch.setattr(ca, "HOME_DIR", home)
    monkeypatch.setattr(ca, "SNAPSHOTS_DIR", snaps)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    return home, snaps


def _escribir(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(obj if isinstance(obj, str) else json.dumps(obj))


def _jwt(payload):
    seg = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"aaa.{seg}.bbb"


def _codex(home, email, acc):
    _escribir(os.path.join(home, ".codex", "auth.json"),
              {"tokens": {"id_token": _jwt({"email": email}), "account_id": acc}})


def _opencode(home, blob):
    _escribir(os.path.join(home, ".local", "share", "opencode", "auth.json"), blob)


# ── emails conocidos ────────────────────────────────────────────────────────

def test_emails_conocidos(monkeypatch):
    home, _ = _setup(monkeypatch)
    _codex(home, "a@x.com", "1")
    ca.capturar_actual("codex", "A")
    assert cw.emails_conocidos("codex") == {"a@x.com"}
    assert cw.emails_conocidos("claude") == set()


# ── preservar la sesión activa antes del login ──────────────────────────────

def test_preservar_caso_b_sesion_no_guardada(monkeypatch):
    # Sesión activa SIN perfil guardado -> preservar la captura para no perderla.
    home, _ = _setup(monkeypatch)
    _codex(home, "a@x.com", "1")
    assert not [p for p in ca.listar() if p["tipo"] == "codex"]
    cw.preservar_sesion_actual("codex")
    perfiles = [p for p in ca.listar() if p["tipo"] == "codex"]
    assert len(perfiles) == 1 and perfiles[0]["email"] == "a@x.com"


def test_preservar_codex_no_pisa_home_aislado(monkeypatch):
    # Codex usa home AISLADO por cuenta: preservar NO debe pisar el dir de la cuenta
    # con ~/.codex (eso clobbearía el token vigente del dir y dispararía la
    # revocación por reuso de OpenAI). El dir manda; solo no debe duplicar.
    home, snaps = _setup(monkeypatch)
    _codex(home, "a@x.com", "1")
    p = ca.capturar_actual("codex", "A")          # dir vacío -> poblado con "1"
    # ~/.codex queda con una sesión VIEJA; el dir aislado tiene el token vigente
    _codex(home, "a@x.com", "1-VIEJO-DEL-HOME")
    cw.preservar_sesion_actual("codex")
    assert len([c for c in ca.listar() if c["tipo"] == "codex"]) == 1   # no duplica
    snap = json.load(open(os.path.join(snaps, str(p["id"]), "auth.json"), encoding="utf-8"))
    assert snap["tokens"]["account_id"] == "1"    # NO pisado por ~/.codex


def test_preservar_sin_email_asume_el_perfil_activo(monkeypatch):
    # CLIs sin email único (grok/opencode/antigravity): con em=None el matcheo
    # por email nunca coincide, así que cada «Conectar cuenta nueva» con sesión
    # activa creaba OTRO perfil "Cuenta anterior" (duplicados infinitos). Igual
    # que estado(): si hay perfil ACTIVO del tipo, el HOME se asume suyo → se
    # refresca su snapshot en vez de capturar uno nuevo.
    home, snaps = _setup(monkeypatch)
    _escribir(os.path.join(home, ".grok", "auth.json"), {"token": "T1"})
    p = ca.capturar_actual("grok", "Personal")
    _escribir(os.path.join(home, ".grok", "auth.json"), {"token": "T1-refrescado"})
    cw.preservar_sesion_actual("grok")
    perfiles = [c for c in ca.listar() if c["tipo"] == "grok"]
    assert len(perfiles) == 1                      # NO nace "Cuenta anterior"
    snap = open(os.path.join(snaps, str(p["id"]), "auth.json"), encoding="utf-8").read()
    assert "T1-refrescado" in snap                 # snapshot refrescado, no viejo


def test_preservar_sin_email_sin_perfil_activo_captura(monkeypatch):
    # Sin email Y sin perfil guardado: el CASO B de siempre — capturar la sesión
    # como perfil nuevo para no perderla cuando el login la pise.
    home, _ = _setup(monkeypatch)
    _escribir(os.path.join(home, ".grok", "auth.json"), {"token": "T1"})
    cw.preservar_sesion_actual("grok")
    perfiles = [c for c in ca.listar() if c["tipo"] == "grok"]
    assert len(perfiles) == 1 and perfiles[0]["label"] == "Cuenta anterior"


# ── vigilar_login: detección de cuenta nueva ────────────────────────────────

def test_vigilar_detecta_cuenta_nueva_por_email(monkeypatch):
    home, _ = _setup(monkeypatch)
    _codex(home, "a@x.com", "1")
    ca.capturar_actual("codex", "A")          # A conocida y activa
    conocidos = cw.emails_conocidos("codex")
    huella = cw._huella("codex")

    async def run():
        async def loguear_b():
            await asyncio.sleep(0.25)
            _codex(home, "b@y.com", "2")        # el usuario entra con la cuenta B
        w = asyncio.create_task(cw.vigilar_login(
            "codex", conocidos, "a@x.com", huella, "Nueva", timeout_s=5, intervalo=0.1))
        await loguear_b()
        return await w

    perfil = asyncio.run(run())
    assert perfil is not None
    assert perfil["email"] == "b@y.com"
    assert perfil["label"] == "Nueva"
    # quedó guardada y activa
    activos = [c for c in ca.listar() if c["tipo"] == "codex" and c["activa"]]
    assert len(activos) == 1 and activos[0]["email"] == "b@y.com"


def test_vigilar_relogin_codex_detecta_sin_pisar_home(monkeypatch):
    # Re-login de una cuenta codex ya guardada: el watcher la detecta (mismo perfil,
    # queda activa, no duplica) PERO NO pisa su home aislado con ~/.codex — codex
    # rota su token en el dir (vía CODEX_HOME); clobbearlo dispararía la revocación.
    home, snaps = _setup(monkeypatch)
    _codex(home, "a@x.com", "1")
    p = ca.capturar_actual("codex", "A")
    conocidos = cw.emails_conocidos("codex")
    huella = cw._huella("codex")

    async def run():
        async def relogin_a():
            await asyncio.sleep(0.2)
            _codex(home, "a@x.com", "1-DESDE-HOME")   # cambia ~/.codex (sesión vieja)
        w = asyncio.create_task(cw.vigilar_login(
            "codex", conocidos, "a@x.com", huella, "X", timeout_s=3, intervalo=0.1))
        await relogin_a()
        return await w

    perfil = asyncio.run(run())
    assert perfil is not None and perfil["id"] == p["id"]   # mismo perfil
    assert perfil["activa"] is True
    assert len([c for c in ca.listar() if c["tipo"] == "codex"]) == 1   # no duplicó
    # el home aislado NO se pisó con ~/.codex (token del dir intacto)
    snap = json.load(open(os.path.join(snaps, str(p["id"]), "auth.json"), encoding="utf-8"))
    assert snap["tokens"]["account_id"] == "1"


def test_vigilar_codex_nuevo_detecta_y_da_de_alta(monkeypatch):
    # Alta de cuenta codex nueva: el watcher polea el STAGING dir aislado (donde el
    # login depositó la credencial) y, al detectarla, la da de alta en su propio dir
    # + repunta el symlink. NUNCA mira ~/.codex ni el dir de la cuenta activa.
    home, snaps = _setup(monkeypatch)
    _codex(home, "a@x.com", "1")
    pa = ca.capturar_actual("codex", "A")            # A guardada y activa
    dir_a = ca.codex_home(pa["id"])
    auth_a_antes = open(os.path.join(dir_a, "auth.json"), encoding="utf-8").read()
    conocidos = cw.emails_conocidos("codex")
    staging = ca.codex_login_home_nuevo()            # arranca vacío

    async def run():
        async def loguear_b():
            await asyncio.sleep(0.25)
            _escribir(os.path.join(staging, "auth.json"),
                      {"tokens": {"id_token": _jwt({"email": "b@y.com"}), "account_id": "2"}})
        w = asyncio.create_task(cw.vigilar_login_codex_nuevo(
            conocidos, "Nueva", timeout_s=5, intervalo=0.1))
        await loguear_b()
        return await w

    perfil = asyncio.run(run())
    assert perfil is not None and perfil["email"] == "b@y.com" and perfil["label"] == "Nueva"
    activos = [c for c in ca.listar() if c["tipo"] == "codex" and c["activa"]]
    assert len(activos) == 1 and activos[0]["email"] == "b@y.com"
    # la cuenta activa anterior (A) quedó intacta (el watcher no la tocó)
    assert open(os.path.join(dir_a, "auth.json"), encoding="utf-8").read() == auth_a_antes


def test_vigilar_codex_nuevo_relogin_de_guardada(monkeypatch):
    # Re-login de una cuenta codex YA guardada vía «agregar nueva»: el watcher la
    # adopta (mismo perfil, activa, tokens frescos del staging), sin duplicar.
    home, snaps = _setup(monkeypatch)
    _codex(home, "a@x.com", "1")
    pa = ca.capturar_actual("codex", "A")
    dir_a = ca.codex_home(pa["id"])
    conocidos = cw.emails_conocidos("codex")
    staging = ca.codex_login_home_nuevo()

    async def run():
        async def relogin_a():
            await asyncio.sleep(0.2)
            _escribir(os.path.join(staging, "auth.json"),
                      {"tokens": {"id_token": _jwt({"email": "a@x.com"}),
                                  "account_id": "1", "refresh_token": "rt-FRESCO"}})
        w = asyncio.create_task(cw.vigilar_login_codex_nuevo(
            conocidos, "X", timeout_s=3, intervalo=0.1))
        await relogin_a()
        return await w

    perfil = asyncio.run(run())
    assert perfil is not None and perfil["id"] == pa["id"]
    assert len([c for c in ca.listar() if c["tipo"] == "codex"]) == 1   # no duplicó
    assert json.load(open(os.path.join(dir_a, "auth.json")))["tokens"]["refresh_token"] == "rt-FRESCO"


def test_vigilar_timeout_sin_login(monkeypatch):
    _setup(monkeypatch)
    perfil = asyncio.run(cw.vigilar_login(
        "codex", set(), None, "", "X", timeout_s=0.4, intervalo=0.1))
    assert perfil is None


def test_vigilar_opencode_por_huella(monkeypatch):
    # opencode no tiene email -> detección por cambio de huella del auth.json.
    home, _ = _setup(monkeypatch)
    huella_previa = cw._huella("opencode")   # sin archivo aún

    async def run():
        async def loguear():
            await asyncio.sleep(0.25)
            _opencode(home, {"anthropic": {"type": "oauth", "access": "tok"}})
        w = asyncio.create_task(cw.vigilar_login(
            "opencode", set(), None, huella_previa, "OC", timeout_s=5, intervalo=0.1))
        await loguear()
        return await w

    perfil = asyncio.run(run())
    assert perfil is not None
    assert perfil["tipo"] == "opencode"


# ── endpoint /login/watch (TestClient; watcher stubeado) ────────────────────

def test_router_login_iniciar(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import plotspace.routers.cuentas as r
    import plotspace.core.cli_login as cl

    home, _ = _setup(monkeypatch)

    async def _fake_vigilar(*a, **k):
        return None
    async def _fake_iniciar(tipo, timeout_s=25):
        # Codex va por callback (sin código): iniciar() devuelve codigo=None.
        return "https://auth.openai.com/oauth/authorize?x=1", False, None
    monkeypatch.setattr(cw, "vigilar_login", _fake_vigilar)   # no correr 5 min
    monkeypatch.setattr(cw, "vigilar_login_codex_nuevo", _fake_vigilar)  # codex → watcher dedicado
    monkeypatch.setattr(cl, "iniciar", _fake_iniciar)         # no spawnear PTY real

    _codex(home, "a@x.com", "1")   # sesión activa SIN guardar
    app = FastAPI()
    app.include_router(r.router)
    client = TestClient(app)

    resp = client.post("/api/cuentas/login/iniciar", json={"tipo": "codex"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["url"].startswith("https://auth.openai.com/oauth/authorize")
    assert data["paste"] is False
    assert data["codigo"] is None             # codex va por callback, sin código
    assert data["email_previo"] == "a@x.com"
    # preservó la sesión activa (la guardó para no perderla al loguear otra)
    assert any(p["email"] == "a@x.com" for p in ca.listar())
    # tipo inválido -> 400
    assert client.post("/api/cuentas/login/iniciar", json={"tipo": "nope"}).status_code == 400


if __name__ == "__main__":
    import traceback

    class _MP:
        def __init__(self): self._u = []
        def setattr(self, o, n, v): self._u.append((o, n, getattr(o, n))); setattr(o, n, v)
        def delenv(self, n, raising=True):
            if n in os.environ: self._u.append(("env", n, os.environ.pop(n)))
        def undo(self):
            for o, n, v in reversed(self._u):
                if o == "env": os.environ[n] = v
                else: setattr(o, n, v)

    fallos = 0
    for nombre, fn in sorted(globals().items()):
        if nombre.startswith("test_") and callable(fn):
            mp = _MP()
            try:
                fn(mp); print("ok", nombre)
            except Exception:
                fallos += 1; print("FAIL", nombre); traceback.print_exc()
            finally:
                mp.undo()
    sys.exit(1 if fallos else 0)
