"""Tests de la detección de CLIs de agente (`core/clis.py`).

POR QUÉ IMPORTA
===============
Hoy Jarvis da por hecho que los CLIs están: abre la terminal y tipea `claude`.
En la máquina de alguien que acaba de instalar la app, eso muestra una terminal
negra con `command not found` — y esa sería la primera impresión de todo
usuario nuevo.

La regla que estos tests protegen: **no se promete lo que no se puede
cumplir.** Antigravity no sale de npm, y sin Node no hay forma de instalar
nada: en esos casos la app informa en vez de ofrecer un botón muerto.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plotspace.core import clis


def _por_id(lista, cid):
    return next(c for c in lista if c['id'] == cid)


# ── detección ────────────────────────────────────────────────────────────

def test_detecta_lo_que_hay_en_el_sistema():
    detectados = clis.detectar(existe_local=lambda b, path=None: b == 'claude')
    assert _por_id(detectados, 'claude')['instalado'] is True
    assert _por_id(detectados, 'codex')['instalado'] is False


def test_una_sonda_rota_no_miente():
    """Si no se puede preguntar, la respuesta honesta es "no está": ofrecer
    instalarlo es recuperable; decir que está y que falle al abrir, no."""
    detectados = clis.detectar(
        existe_local=lambda b, path=None: (_ for _ in ()).throw(OSError('PATH roto')),
    )
    assert all(c['instalado'] is False for c in detectados)


def test_la_deteccion_real_no_explota():
    """Sin mocks, contra el sistema de verdad. NO se asume que haya ningún CLI
    instalado: en la máquina de desarrollo están todos y en un runner de CI no
    hay ninguno, y las dos respuestas son correctas. Lo que se verifica es que
    la detección conteste sin romperse, que es de lo que depende la pantalla de
    bienvenida."""
    detectados = clis.detectar()
    assert len(detectados) == len(clis.CATALOGO)
    for c in detectados:
        assert isinstance(c['instalado'], bool), c
        assert c['nombre'] and c['id']


# ── no prometer lo que no se puede cumplir ───────────────────────────────

def test_antigravity_se_detecta_pero_no_se_ofrece_instalar():
    """Es una app de escritorio de Google, no un paquete de npm. Un botón
    «Instalar» que no puede cumplir es peor que una línea que explique."""
    detectados = clis.detectar(existe_local=lambda b, path=None: False)
    assert _por_id(detectados, 'antigravity')['instalable'] is False
    assert _por_id(detectados, 'claude')['instalable'] is True
    assert clis.comando_instalar('antigravity') is None


def test_un_cli_desconocido_no_arma_un_comando():
    assert clis.comando_instalar('no-existe') is None
    assert clis.comando_instalar('') is None


# ── el comando de instalación ────────────────────────────────────────────

def test_instalar_en_el_sistema():
    cmd = clis.comando_instalar('claude')
    assert cmd == ['npm', 'install', '-g', '@anthropic-ai/claude-code'], cmd


def test_sin_node_no_se_promete_instalar_nada():
    assert clis.hay_node(existe_local=lambda b, path=None: False) is False
    assert clis.hay_node(existe_local=lambda b, path=None: b == 'npm') is True


# ── lo que consume la pantalla de bienvenida ─────────────────────────────

def test_el_estado_dice_si_es_un_primer_arranque():
    from unittest import mock
    with mock.patch.object(clis, 'detectar',
                           return_value=[{'id': 'claude', 'nombre': 'x',
                                          'instalado': False, 'instalable': True}]), \
         mock.patch.object(clis, 'hay_node', return_value=True):
        e = clis.estado()
    assert e['primer_arranque'] is True, 'sin ningún CLI, la app tiene algo que decir'

    with mock.patch.object(clis, 'detectar',
                           return_value=[{'id': 'claude', 'nombre': 'x',
                                          'instalado': True, 'instalable': True}]), \
         mock.patch.object(clis, 'hay_node', return_value=True):
        e = clis.estado()
    assert e['primer_arranque'] is False, 'con uno instalado ya se puede trabajar'


# ── instalación ──────────────────────────────────────────────────────────

class _R:
    def __init__(self, rc, out='', err=''):
        self.returncode, self.stdout, self.stderr = rc, out, err


def test_instalar_devuelve_el_error_tal_cual():
    """Quien ve esto acaba de instalar la app y no tiene nada más para
    orientarse: un "no se pudo" genérico lo deja sin salida."""
    r = clis.instalar('claude', correr=lambda *a, **kw: _R(1, '', 'EACCES: permission denied'))
    assert r['ok'] is False
    assert 'EACCES' in r['salida'], r


def test_instalar_ok():
    r = clis.instalar('codex', correr=lambda *a, **kw: _R(0, 'added 1 package'))
    assert r['ok'] is True and 'added 1 package' in r['salida']


def test_instalar_lo_que_no_se_instala():
    r = clis.instalar('antigravity')
    assert r['ok'] is False and 'no se instala' in r['salida']


def test_una_instalacion_colgada_no_queda_para_siempre():
    import subprocess as sp

    def _colgado(*a, **kw):
        raise sp.TimeoutExpired(cmd='npm', timeout=600)

    r = clis.instalar('claude', correr=_colgado)
    assert r['ok'] is False and 'tardó demasiado' in r['salida']


def test_la_salida_no_crece_sin_limite():
    # npm puede escupir megas de warnings; eso viaja por WS y va a la UI.
    r = clis.instalar('claude', correr=lambda *a, **kw: _R(0, 'x' * 50000))
    assert len(r['salida']) <= 2000


if __name__ == '__main__':
    import pytest
    raise SystemExit(pytest.main([__file__, '-q']))
