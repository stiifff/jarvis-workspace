"""Tests de qué entra en el instalador (`packaging/armar_bundle.py`).

POR QUÉ IMPORTA CADA REGLA
==========================
El objetivo es un instalador de ~150 MB. Los tres errores que lo arruinan, en
orden de gravedad:

1. **Meter de más.** `frontend/` acumuló galerías, mockups y prototipos de
   diseño; el venv tiene 780 MB de Playwright + Chromium y 400 MB de modelos de
   voz. Sin filtrar, el instalador pasa de 150 MB a 1,3 GB — y la mayoría de la
   gente nunca usa el browser remoto ni el dictado local.
2. **Dejar afuera algo que hace falta.** Un archivo que falta no se nota al
   empaquetar: se nota cuando alguien instala la app y no arranca.
3. **Filtrar por nombre y llevarse algo legítimo.** Excluir "tests" es correcto;
   excluir un directorio del producto que se llame parecido, no.
"""
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'packaging'))

import armar_bundle as ab


# ── lo que NO va ─────────────────────────────────────────────────────────

def test_la_suite_de_tests_no_viaja():
    """A quien instala la app no le sirve para nada, y son cientos de archivos."""
    assert ab.debe_copiarse('plotspace/tests/test_terminals.py') is False
    assert ab.debe_copiarse('frontend/sections/panel/__tests__/updater.test.js') is False


def test_los_prototipos_del_frontend_no_viajan():
    """Galerías y mockups: valiosos en el repo, basura en un instalador."""
    assert ab.debe_copiarse('frontend/preview-settings/index.html') is False
    assert ab.debe_copiarse('frontend/radio-studio/app.js') is False
    assert ab.debe_copiarse('frontend/terminal-chrome-redesign/index.html') is False


def test_las_cachés_y_los_datos_no_viajan():
    assert ab.debe_copiarse('plotspace/core/__pycache__/x.pyc') is False
    assert ab.debe_copiarse('plotspace/core/database.pyc') is False
    assert ab.debe_copiarse('scripts/algo.log') is False
    # Una DB dentro del bundle sería el estado de OTRA persona.
    assert ab.debe_copiarse('plotspace/x.db') is False


def test_los_extras_pesados_quedan_afuera():
    """780 MB de Playwright y 400 MB de modelos de voz. Se bajan si el usuario
    prende la función que los necesita."""
    for pesado in ('playwright', 'onnxruntime-1.20', 'ctranslate2', 'faster_whisper',
                   'onnx_asr'):
        assert ab.es_extra(pesado) is True, pesado


def test_las_dependencias_base_no_son_extras():
    """Si estas se filtraran, el instalador saldría liviano y roto."""
    for base in ('fastapi', 'uvicorn', 'httpx', 'anthropic', 'psutil', 'websockets'):
        assert ab.es_extra(base) is False, base


# ── lo que SÍ va ─────────────────────────────────────────────────────────

def test_el_producto_viaja_entero():
    for necesario in (
        'plotspace/main.py',
        'plotspace/core/terminal_backend.py',
        'plotspace/routers/terminals.py',
        'frontend/index.html',                       # la home, archivo suelto
        'frontend/shell/workspace.js',
        'frontend/sections/terminals/quick-picker.js',
        'frontend/shared/base.css',
        'frontend/vendor/xterm/xterm.js',            # el emulador, sin él no hay terminal
        'scripts/jarvis_ops_hook.py',                # la provenance del enjambre
    ):
        assert ab.debe_copiarse(necesario) is True, necesario


def test_un_directorio_que_se_llama_parecido_no_se_filtra():
    """Excluir 'tests' es correcto; llevarse puesto algo del producto que se
    llame parecido, no. El filtro es por componente exacto de la ruta."""
    assert ab.debe_copiarse('plotspace/core/testeador.py') is True
    assert ab.debe_copiarse('frontend/sections/shared/protests.js') is True


def test_es_de_la_app_distingue_producto_de_prototipo():
    assert ab.es_de_la_app('frontend/sections/home/home.js') is True
    assert ab.es_de_la_app('frontend/shared/ui.js') is True
    assert ab.es_de_la_app('frontend/index.html') is True
    assert ab.es_de_la_app('frontend/preview-nave/index.html') is False
    # Lo que no es del frontend no lo decide esta regla.
    assert ab.es_de_la_app('plotspace/main.py') is True


if __name__ == '__main__':
    import pytest
    raise SystemExit(pytest.main([__file__, '-q']))
