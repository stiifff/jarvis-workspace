"""Tests del comando `jarvis` (`plotspace/cli.py`).

Es la puerta de entrada para quien instala con `pipx install .` —
el camino más corto hasta tener la app andando, sin instalador ni firma.

Lo que protegen estos tests es una decisión de SEGURIDAD y una de percepción:
el default no puede exponer a la red una app que ejecuta comandos arbitrarios,
y el browser no puede abrirse antes de que el motor conteste.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plotspace import cli


def test_el_comando_se_llama_jarvis():
    assert cli.construir_parser().prog == 'jarvis'


def test_el_default_escucha_SOLO_en_la_maquina():
    """Un default en 0.0.0.0 expondría a toda la red local una app que abre
    terminales y ejecuta lo que sea. Quien quiera eso, lo pide explícito."""
    a = cli.construir_parser().parse_args([])
    assert a.host == '127.0.0.1', a.host


def test_se_puede_exponer_a_la_lan_a_propósito():
    a = cli.construir_parser().parse_args(['--host', '0.0.0.0'])
    assert a.host == '0.0.0.0'


def test_el_puerto_sale_del_entorno_si_esta(monkeypatch):
    # El shell de escritorio elige un puerto libre y lo pasa así.
    monkeypatch.setenv('JARVIS_PORT', '4321')
    import importlib
    importlib.reload(cli)
    assert cli.construir_parser().parse_args([]).puerto == 4321
    monkeypatch.delenv('JARVIS_PORT')
    importlib.reload(cli)


def test_hay_manera_de_no_abrir_el_browser():
    # Para correrlo en un servidor, o en un contenedor sin escritorio.
    assert cli.construir_parser().parse_args(['--sin-browser']).sin_browser is True


def test_el_browser_espera_a_que_el_motor_conteste(monkeypatch):
    """Abrirlo antes muestra una pantalla de error y hace creer que la app está
    rota: el arranque en frío tarda unos segundos (DB, reconcile, pollers)."""
    intentos = {'n': 0}
    abierto = []

    def _urlopen(url, timeout=None):
        intentos['n'] += 1
        if intentos['n'] < 3:
            raise OSError('todavía no')
        return object()

    monkeypatch.setattr(cli.webbrowser, 'open', lambda u: abierto.append(u))
    monkeypatch.setattr(cli.time, 'sleep', lambda s: None)
    import urllib.request
    monkeypatch.setattr(urllib.request, 'urlopen', _urlopen)

    cli._abrir_cuando_responda('http://127.0.0.1:3000')
    assert abierto == ['http://127.0.0.1:3000'], abierto
    assert intentos['n'] == 3, 'no reintentó'


def test_si_el_motor_nunca_contesta_no_queda_colgado(monkeypatch, capsys):
    monkeypatch.setattr(cli.webbrowser, 'open',
                        lambda u: (_ for _ in ()).throw(AssertionError('no debía abrir')))
    monkeypatch.setattr(cli.time, 'sleep', lambda s: None)
    import urllib.request
    monkeypatch.setattr(urllib.request, 'urlopen',
                        lambda *a, **kw: (_ for _ in ()).throw(OSError('nunca')))
    cli._abrir_cuando_responda('http://127.0.0.1:3000', espera=0.05)
    assert 'a mano' in capsys.readouterr().out


def test_la_raiz_contiene_el_producto():
    raiz = cli._raiz()
    assert os.path.isdir(os.path.join(raiz, 'backend'))
    assert os.path.isdir(os.path.join(raiz, 'frontend'))


if __name__ == '__main__':
    import pytest
    raise SystemExit(pytest.main([__file__, '-q']))
