# JARVIS — candado de Host / Origin (anti DNS-rebinding y CSWSH).
# No hay token de acceso: la app es local. El default escucha en 127.0.0.1;
# 0.0.0.0 es explícito. Lo que queda es no aceptar un Host/Origin de un
# dominio ajeno que apunte a esta máquina.

import os
import ipaddress
from urllib.parse import urlsplit


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
# pueden forjar el header Host vía fetch — solo lo manda un cliente no-browser).
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
    —incluida la IP de LAN— y cualquier host extra (env JARVIS_ALLOWED_HOSTS).
    Header ausente = nada que rechazar → permitido."""
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
    """Arranque: una línea, sin token. El dibujo de caja viejo tumba cp1252."""
    print('[jarvis] listo — abrí http://127.0.0.1:3000')
