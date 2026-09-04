"""
Un browser AUTOMATIZADO (Playwright headless que los agentes usan para QA en
browser) NUNCA debe robarle el derecho de tamaño a la vista VIVA del usuario.

Sin esta red de seguridad, cada navegación de QA abierta SIN `?qa=1` se
registraba como DUEÑO no-observador y desplazaba al usuario: su WS cerraba con
4010 y aparecía el overlay "Esta terminal se está viendo en otra ventana" cada
vez que un agente sacaba un screenshot del workspace. El flag `?qa=1` sigue
siendo el mecanismo primario; esto es la defensa en profundidad para cuando el
agente se lo olvida. El browser real del usuario y la app de escritorio
(desktop app) NO llevan 'headless' en el User-Agent → conservan el
derecho a tamaño intacto. Ver [[tmux-size-clamping]] · [[qa-headless-observer-forzado]].
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plotspace.routers.terminals import _es_ua_automatizada, _forzar_observer

# UAs REALES medidos en este entorno (playwright chromium-1148 / chrome 131).
UA_HEADLESS_SHELL = ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                     '(KHTML, like Gecko) HeadlessChrome/131.0.6778.33 Safari/537.36')
UA_HEADLESS_FULL = ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) HeadlessChrome/131.0.0.0 Safari/537.36')
UA_CHROME_WIN = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                 '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
UA_WEBVIEW2 = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
               '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0')


def test_headless_es_automatizada():
    assert _es_ua_automatizada(UA_HEADLESS_SHELL) is True
    assert _es_ua_automatizada(UA_HEADLESS_FULL) is True


def test_browser_real_no_es_automatizada():
    # El browser del usuario (Chrome/Edge) y la app de escritorio (WebView2) NO.
    assert _es_ua_automatizada(UA_CHROME_WIN) is False
    assert _es_ua_automatizada(UA_WEBVIEW2) is False


def test_ua_ausente_no_es_automatizada():
    # Sin header no adivinamos automatización (mejor conservar el comportamiento).
    assert _es_ua_automatizada(None) is False
    assert _es_ua_automatizada('') is False


def test_headless_forzado_a_observer_aunque_falte_el_flag():
    # El agente se olvidó del ?qa=1 (observer=0): igual queda observer y NO desplaza.
    assert _forzar_observer(0, UA_HEADLESS_SHELL) is True
    assert _forzar_observer(0, UA_HEADLESS_FULL) is True


def test_flag_qa_explicito_sigue_haciendo_observer():
    assert _forzar_observer(1, UA_CHROME_WIN) is True
    assert _forzar_observer(1, UA_HEADLESS_SHELL) is True


def test_usuario_real_conserva_el_derecho_a_tamano():
    # Browser real / desktop sin qa=1 = DUEÑO de tamaño (comportamiento intacto).
    assert _forzar_observer(0, UA_CHROME_WIN) is False
    assert _forzar_observer(0, UA_WEBVIEW2) is False
    assert _forzar_observer(0, None) is False


if __name__ == '__main__':
    for _n, _f in sorted(globals().items()):
        if _n.startswith('test_') and callable(_f):
            _f()
            print(f'ok  {_n}')
    print('TODOS OK')
