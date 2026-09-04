"""
Watcher de alta de cuenta — el "detecta solo" del flujo «Agregar cuenta nueva».

Cuando el usuario toca «Agregar cuenta nueva» en Configuración → Cuentas, Jarvis
abre una terminal de login del CLI (claude auth login / codex login / …). Este
módulo hace polling de los archivos de credencial del HOME y, apenas aparece una
cuenta NUEVA, la guarda sola con cli_accounts.capturar_actual y avisa por WS.

Detección:
  - CLIs con email (claude/codex/qwen): cuenta nueva = email_actual cambió a uno
    que NO está guardado y es distinto al que había antes del login.
  - opencode (sin email único): por cambio de huella (mtime+size+hash) del
    archivo de credencial.

Antes del login se preserva la sesión activa (snapshot), porque el login pisa la
credencial GLOBAL que comparte todo el swarm de agentes.

Todo lo de cli_accounts es síncrono (toca disco) → se llama por asyncio.to_thread
para no bloquear el event loop. Tests: plotspace/tests/test_cuenta_watch.py.
"""
import asyncio
import hashlib
import os

from plotspace.core import cli_accounts as ca


def emails_conocidos(tipo):
    """Set de emails ya guardados para `tipo` (descarta None/'')."""
    return {c["email"] for c in ca.listar() if c["tipo"] == tipo and c["email"]}


def _archivos_principales(tipo):
    spec = ca._specs().get(tipo) or {}
    if spec.get("modo") == "claude":
        return [spec["cred_file"]]
    return spec.get("principales") or spec.get("files") or []


def _huella(tipo):
    """Huella (mtime+size+hash) de los archivos de credencial principales. Detecta
    cambios cuando no hay email (opencode) o como red de seguridad."""
    partes = []
    for p in _archivos_principales(tipo):
        try:
            st = os.stat(p)
            with open(p, "rb") as f:
                h = hashlib.sha256(f.read()).hexdigest()[:16]
            partes.append(f"{os.path.basename(p)}:{int(st.st_mtime)}:{st.st_size}:{h}")
        except OSError:
            partes.append(f"{os.path.basename(p)}:-")
    return "|".join(partes)


def preservar_sesion_actual(tipo):
    """Best-effort: deja la sesión activa ACTUAL guardada antes de que el login la
    pise (el login reescribe la credencial global del HOME). Espeja estado()/usar():
      - CASO A: la sesión ES un perfil guardado (mismo email) → refresca su snapshot.
      - CASO B: la sesión NO está guardada → la captura como perfil nuevo.
    """
    if not ca.esta_logueado(tipo):
        return
    em = ca.email_actual(tipo)
    perfiles = [c for c in ca.listar() if c["tipo"] == tipo]
    coincide = next((c for c in perfiles if c["email"] and c["email"] == em), None) if em else None
    if not em and not coincide:
        # CLIs sin email único (grok/opencode/antigravity): no hay identidad que
        # comparar, así que — igual que estado()/usar() — el HOME se asume del
        # perfil ACTIVO si lo hay. Sin este puente, cada «Conectar cuenta nueva»
        # con sesión activa capturaba OTRO perfil "Cuenta anterior" (duplicados).
        coincide = next((c for c in perfiles if c["activa"]), None)
    try:
        if coincide:
            ca.recapturar(coincide["id"])
        else:
            ca.capturar_actual(tipo, "Cuenta anterior")
    except (ca.NoLogueado, ca.TipoDesconocido, ca.PerfilNoEncontrado):
        pass


async def vigilar_login(tipo, conocidos, email_previo, huella_previa,
                        label="", timeout_s=300, intervalo=2.0):
    """Poll hasta detectar que el login terminó y guardar la cuenta. Devuelve el
    perfil (dict) o None si vence el timeout. Distingue tres casos al detectar que
    la credencial del HOME cambió (huella distinta a la previa) y hay sesión:
      - email NUEVO        → capturar_actual (perfil nuevo, queda activo)
      - email YA guardado  → re-login de esa cuenta: recapturar su snapshot (tokens
                             frescos) + activarla. Antes esto NO se detectaba y el
                             snapshot quedaba con los tokens viejos/muertos.
      - opencode (sin email) → capturar por cambio de huella.
    Un login = una cuenta (corta al primer match). No bloquea el event loop."""
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout_s
    while loop.time() < deadline:
        await asyncio.sleep(intervalo)
        if not await asyncio.to_thread(ca.esta_logueado, tipo):
            continue
        # ¿cambió la credencial desde antes del login? (si no, el login no terminó)
        if (await asyncio.to_thread(_huella, tipo)) == huella_previa:
            continue
        em = await asyncio.to_thread(ca.email_actual, tipo)
        if em:
            match = next((c for c in ca.listar()
                          if c["tipo"] == tipo and c["email"] == em), None)
            if match:
                # re-login de una cuenta ya guardada: snapshot fresco + activarla.
                try:
                    await asyncio.to_thread(ca.recapturar, match["id"])
                    return await asyncio.to_thread(ca.activar, match["id"])
                except (ca.NoLogueado, ca.TipoDesconocido, ca.PerfilNoEncontrado):
                    return None
            if em in conocidos or em == email_previo:
                continue  # cambió la huella pero el email no es accionable aún
        # email nuevo, u opencode (sin email) con huella ya cambiada → capturar
        try:
            return await asyncio.to_thread(ca.capturar_actual, tipo, label)
        except (ca.NoLogueado, ca.TipoDesconocido):
            return None
    return None


async def vigilar_login_codex_nuevo(conocidos, label="", timeout_s=300, intervalo=2.0):
    """Watcher del alta de cuenta CODEX nueva. A diferencia del genérico, polea el
    STAGING dir aislado (`_codex_login`, donde el login del PTY oculto deposita su
    auth.json fresco) en vez de ~/.codex — así el login NUNCA pisa el home de la
    cuenta activa. Al detectar la credencial:
      - email YA guardado  → adoptar esa cuenta (tokens frescos en su dir + activarla)
      - email NUEVO        → alta como perfil nuevo (dir aislado propio + activa)
    Instala en un dir de cuenta real y repunta el symlink _codex_active. One-shot
    (corta al primer match). No bloquea el event loop."""
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout_s
    while loop.time() < deadline:
        await asyncio.sleep(intervalo)
        if not await asyncio.to_thread(ca.codex_login_logueado):
            continue  # el login todavía no depositó la credencial en el staging
        em = await asyncio.to_thread(ca.codex_login_email)
        if em:
            match = next((c for c in ca.listar()
                          if c["tipo"] == "codex" and c["email"] == em), None)
            if match:
                # re-login de una cuenta ya guardada: instalar tokens frescos + activar
                try:
                    return await asyncio.to_thread(ca.adoptar_codex_login, match["id"])
                except (ca.NoLogueado, ca.TipoDesconocido, ca.PerfilNoEncontrado):
                    return None
        try:
            return await asyncio.to_thread(ca.capturar_codex_login, label)
        except (ca.NoLogueado, ca.TipoDesconocido):
            return None
    return None
