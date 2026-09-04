"""
Test: validación de Host (anti DNS-rebinding) y Origin (anti CSWSH) de auth.py.

El token-gate por cookie es el candado principal, pero una web maliciosa abierta
en el mismo browser puede intentar DNS-rebinding (Host de un dominio que controla)
o abrir un WebSocket cross-origin. Ambos ataques viajan con un nombre de dominio;
el acceso legítimo viaja con localhost o una IP cruda (incluida la IP de LAN del
celular). host_permitido/origen_permitido encapsulan esa regla.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plotspace.core.auth import host_permitido, origen_permitido


# ─── host_permitido (header Host) ────────────────────────────────────────────

def test_host_localhost_ok():
    assert host_permitido('localhost:3000')
    assert host_permitido('localhost')


def test_host_loopback_y_lan_ok():
    assert host_permitido('127.0.0.1:3000')
    assert host_permitido('192.168.1.42:3000')   # IP de LAN (celular)
    assert host_permitido('10.0.0.5')
    assert host_permitido('[::1]:3000')           # IPv6 loopback


def test_host_dominio_externo_rechazado():
    # Vector de DNS-rebinding: un dominio que el atacante resuelve a 127.0.0.1
    assert not host_permitido('jarvis.attacker.com:3000')
    assert not host_permitido('evil.com')
    assert not host_permitido('rebind.local')     # .local también es dominio


def test_host_ausente_permitido():
    # Sin Host no se puede hacer rebinding → nada que rechazar
    assert host_permitido(None)
    assert host_permitido('')


def test_host_extra_allowlist():
    # Escape hatch para un dominio local configurado (JARVIS_ALLOWED_HOSTS)
    assert host_permitido('mi-jarvis.local:3000', extra=('mi-jarvis.local',))
    assert not host_permitido('mi-jarvis.local:3000', extra=('otro.local',))


# ─── origen_permitido (header Origin de un WS) ───────────────────────────────

def test_origin_local_ok():
    assert origen_permitido('http://localhost:3000')
    assert origen_permitido('http://127.0.0.1:3000')
    assert origen_permitido('http://192.168.1.42:3000')


def test_origin_externo_rechazado():
    assert not origen_permitido('http://evil.com')
    assert not origen_permitido('https://phishing.example')


def test_origin_ausente_permitido():
    # Cliente no-browser o navegación same-origin no manda Origin
    assert origen_permitido(None)
    assert origen_permitido('')


def test_origin_null_rechazado():
    # Origin 'null' = sandbox/data:/file: → no es la app legítima
    assert not origen_permitido('null')


def test_origin_extra_allowlist():
    assert origen_permitido('http://mi-jarvis.local:3000', extra=('mi-jarvis.local',))


if __name__ == '__main__':
    # Patrón del proyecto: correr como script además de pytest
    import traceback
    fallos = 0
    for nombre, fn in sorted(globals().items()):
        if nombre.startswith('test_') and callable(fn):
            try:
                fn()
                print(f'ok  {nombre}')
            except Exception:
                fallos += 1
                print(f'FAIL {nombre}')
                traceback.print_exc()
    sys.exit(1 if fallos else 0)
