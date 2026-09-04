# JARVIS — Autenticación por token de acceso.
# El server escucha en 0.0.0.0 (necesario para abrir Jarvis desde el celular/
# otra PC de la LAN), pero las terminales son shells: sin un candado,
# cualquiera en la red local tendría ejecución de comandos en esta máquina.
#
# Modelo: un token único autogenerado, persistido en data/jarvis_token.txt
# (gitignored junto con data/). El browser lo presenta UNA vez (POST
# /api/auth/login o GET /login?token=...) y queda en una cookie httpOnly.
# - HTTP:      middleware en main.py exige la cookie para /api/*
# - WebSocket: cada endpoint WS valida la cookie antes de aceptar
#   (el middleware http de Starlette NO corre para websockets)

import os
import secrets
import ipaddress
from urllib.parse import urlsplit

from plotspace.core.datadir import ruta_data

_TOKEN: str | None = None

_TOKEN_PATH = ruta_data('jarvis_token.txt')

COOKIE_NAME = 'jarvis_token'

# Rutas HTTP que NO requieren token (el shell estático no es sensible;
# sin API ni WS no se puede hacer nada con él). /api/health es un ping que no
# expone nada sensible — el launcher/monitoreo lo cura sin tener el token.
RUTAS_ABIERTAS = ('/api/auth/login', '/api/health', '/api/system/ready')

# Prefijos que NO exigen cookie porque llevan su PROPIO gate. HOY NO HAY
# NINGUNO: el único era el preview del Web Builder, que se eliminó por completo
# el 2026-07-25. Se deja el mecanismo —no la excepción— porque el gate propio es
# la forma correcta de abrir una ruta puntual, y volver a inventarlo desde cero
# es cómo se cuelan los agujeros. Ver [[web-builder-eliminado]].
PREFIJOS_ABIERTOS: tuple = ()


def ruta_abierta(path: str) -> bool:
    """¿Esta ruta pasa el middleware sin cookie? (exactas + prefijos con gate propio)"""
    return path in RUTAS_ABIERTAS or path.startswith(PREFIJOS_ABIERTOS)


def _proteger_token_file() -> None:
    """Restringe el token a 0600 (solo el dueño). El token da shell remota; un
    644 heredado lo deja legible por cualquier usuario/proceso local de la
    máquina. Best-effort: en DrvFs (montaje Windows en WSL) chmod puede no
    aplicar, y eso no es fatal."""
    try:
        os.chmod(_TOKEN_PATH, 0o600)
    except OSError:
        pass


def obtener_token() -> str:
    """Token de acceso: env JARVIS_TOKEN > archivo persistido > autogenerar."""
    global _TOKEN
    if _TOKEN:
        return _TOKEN

    env = os.environ.get('JARVIS_TOKEN', '').strip()
    if env:
        _TOKEN = env
        return _TOKEN

    try:
        with open(_TOKEN_PATH, encoding='utf-8') as f:
            guardado = f.read().strip()
        if guardado:
            _TOKEN = guardado
            _proteger_token_file()   # corrige perms heredados (644 → 600)
            return _TOKEN
    except FileNotFoundError:
        pass

    _TOKEN = secrets.token_urlsafe(24)
    os.makedirs(os.path.dirname(_TOKEN_PATH), exist_ok=True)
    # Crear con 0600 desde el vamos: no debe quedar world-readable ni un
    # instante (umask podría no alcanzar para garantizarlo).
    fd = os.open(_TOKEN_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(_TOKEN + '\n')
    _proteger_token_file()
    return _TOKEN


def token_valido(candidato: str | None) -> bool:
    if not candidato:
        return False
    return secrets.compare_digest(candidato, obtener_token())


def cookie_valida(cookies: dict) -> bool:
    return token_valido(cookies.get(COOKIE_NAME))


# ─── Anti DNS-rebinding / CSWSH (defensa en profundidad) ─────────────────────
# El token-gate por cookie es el candado principal, pero una web maliciosa
# abierta en el mismo browser puede intentar dos cosas:
#   1. DNS-rebinding: resolver un dominio que controla → 127.0.0.1 y pegarle
#      a la API con el Host de ese dominio.
#   2. CSWSH: abrir un WebSocket cross-origin a ws://localhost:3000.
# Ambos ataques viajan SIEMPRE con un nombre de dominio (en Host u Origin).
# El acceso legítimo (mismo localhost, o la IP de LAN desde el celular) viaja
# con localhost o una IP cruda. Por eso alcanza con exigir "host local o IP".

def _hostname_de(valor: str) -> str:
    """Extrae el hostname de un 'host:port', una URL o un Origin.
    urlsplit normaliza IPv6 (`[::1]`) y separa el puerto."""
    v = (valor or '').strip()
    if '://' not in v:
        v = 'http://' + v
    try:
        return (urlsplit(v).hostname or '').lower()
    except ValueError:
        return ''


# Hosts no-browser siempre permitidos. `testserver` es el Host por defecto del
# TestClient de Starlette/httpx; NO es un vector de rebinding (los browsers no
# pueden forjar el header Host vía fetch — solo lo manda un cliente no-browser),
# así que permitirlo no abre nada y evita romper los tests de integración.
_HOSTS_SEGUROS = frozenset({'localhost', 'testserver'})


def _es_host_local(hostname: str) -> bool:
    """True si es `localhost`/host de test seguro o una IP literal (loopback o
    LAN). Rechaza nombres de dominio: ese es el vector de rebinding/sitios
    externos."""
    if not hostname:
        return False
    if hostname in _HOSTS_SEGUROS:
        return True
    try:
        ipaddress.ip_address(hostname)
        return True
    except ValueError:
        return False


def host_permitido(host_header: str | None, extra=()) -> bool:
    """Valida el header Host (anti DNS-rebinding). Acepta localhost e IPs
    —incluida la IP de LAN para abrir Jarvis desde el celular— y cualquier
    host extra configurado (env JARVIS_ALLOWED_HOSTS). Header ausente = nada
    que rechazar (no se puede hacer rebinding sin Host) → permitido."""
    if not host_header:
        return True
    hostname = _hostname_de(host_header)
    if hostname and hostname in {h.lower() for h in extra}:
        return True
    return _es_host_local(hostname)


def origen_permitido(origin_header: str | None, extra=()) -> bool:
    """Valida el header Origin de un upgrade WebSocket (anti CSWSH). Origin
    ausente = cliente no-browser o navegación same-origin → permitido. `null`
    (sandbox/data:) → rechazado. Resto: solo localhost/IP o host extra."""
    if not origin_header:
        return True
    if origin_header == 'null':
        return False
    hostname = _hostname_de(origin_header)
    if hostname and hostname in {h.lower() for h in extra}:
        return True
    return _es_host_local(hostname)


def hosts_extra() -> tuple:
    """Allowlist opcional de hosts/orígenes por nombre (ej. un dominio .local
    en /etc/hosts), separada por comas en env JARVIS_ALLOWED_HOSTS."""
    crudo = os.environ.get('JARVIS_ALLOWED_HOSTS', '').strip()
    return tuple(h.strip().lower() for h in crudo.split(',') if h.strip())


def imprimir_banner():
    token = obtener_token()
    print('┌──────────────────────────────────────────────────────────────┐')
    print('│  JARVIS — token de acceso (pedido una sola vez por browser)  │')
    print(f'│  {token}  │')
    print('│  Cambiarlo: borrar data/jarvis_token.txt o setear JARVIS_TOKEN │')
    print('└──────────────────────────────────────────────────────────────┘')
