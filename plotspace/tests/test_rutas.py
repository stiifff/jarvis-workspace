"""Tests de la forma canónica de rutas (`core/rutas.py`).

POR QUÉ IMPORTAN TANTO
======================
Con terminales de shells distintos sobre el mismo proyecto, el mismo archivo
tiene varios nombres. Todo el sistema de coordinación del enjambre identifica
archivos POR SU RUTA: si dos agentes lo llaman distinto, el candado de
propiedad no ve la colisión y **se pisan en silencio**.

No rompe nada visiblemente. Corrompe trabajo. Por eso cada caso de acá está
escrito como la pregunta que de verdad importa: *¿estos dos agentes están
hablando del mismo archivo?*
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plotspace.core import rutas


# ── traducción entre mundos ──────────────────────────────────────────────

def test_un_disco_de_windows_visto_desde_wsl():
    assert rutas.a_forma_wsl(r'C:\proyectos\app') == '/mnt/c/proyectos/app'
    assert rutas.a_forma_wsl('D:/otro/dir') == '/mnt/d/otro/dir'
    # Ya en forma de Unix, vuelve igual.
    assert rutas.a_forma_wsl('/home/user/app') == '/home/user/app'


def test_una_distro_vista_desde_windows():
    # Así ve Windows el sistema de archivos de una distro.
    assert rutas.a_forma_wsl(r'\\wsl.localhost\Ubuntu\home\user\app') == '/home/user/app'
    # Y el formato viejo de WSL, que sigue vivo en máquinas actualizadas.
    assert rutas.a_forma_wsl(r'\\wsl$\Ubuntu\home\user\app') == '/home/user/app'


def test_ida_y_vuelta_de_un_disco():
    original = r'C:\proyectos\app\src\index.js'
    assert rutas.a_forma_windows(rutas.a_forma_wsl(original)) == 'C:/proyectos/app/src/index.js'


def test_sin_saber_la_distro_no_se_inventa_una():
    # Traducir /home/user/x a Windows exige saber CUÁL distro. Inventar una
    # sería peor que no traducir: apuntaría a otra máquina.
    assert rutas.a_forma_windows('/home/user/x') == '/home/user/x'
    assert rutas.a_forma_windows('/home/user/x', distro='Ubuntu') == r'\\wsl.localhost\Ubuntu\home\user\x'


# ── LA pregunta: ¿es el mismo archivo? ───────────────────────────────────

def test_dos_agentes_en_shells_distintos_ven_el_mismo_archivo():
    """EL test de esta fase. Un agente en PowerShell y otro en WSL tocando el
    mismo archivo tienen que producir la MISMA clave, o el guard de propiedad
    los deja pisarse."""
    raiz = r'C:\proyectos\app'
    desde_powershell = rutas.canonica(r'C:\proyectos\app\src\index.js', raiz)
    desde_wsl = rutas.canonica('/mnt/c/proyectos/app/src/index.js', raiz)
    assert desde_powershell == desde_wsl == 'src/index.js', (desde_powershell, desde_wsl)


def test_un_proyecto_que_vive_en_la_distro():
    """El caso inverso: el proyecto está adentro de WSL y un agente lo mira
    desde Windows por la ruta UNC."""
    raiz = '/home/user/proyectos/app'
    desde_wsl = rutas.canonica('/home/user/proyectos/app/src/x.js', raiz)
    desde_windows = rutas.canonica(
        r'\\wsl.localhost\Ubuntu\home\user\proyectos\app\src\x.js', raiz)
    assert desde_wsl == desde_windows == 'src/x.js', (desde_wsl, desde_windows)


def test_relativa_y_absoluta_coinciden():
    # Una CLI imprime el path absoluto y otra el relativo — ya pasaba antes de
    # que existieran los shells mezclados.
    raiz = '/home/user/app'
    assert rutas.canonica('/home/user/app/plotspace/main.py', raiz) == 'plotspace/main.py'
    assert rutas.canonica('./plotspace/main.py', raiz) == 'plotspace/main.py'
    assert rutas.canonica('plotspace/main.py', raiz) == 'plotspace/main.py'


def test_separadores_de_windows_en_una_ruta_relativa():
    assert rutas.canonica(r'src\componentes\boton.js', '/home/user/app') == 'src/componentes/boton.js'


def test_la_raiz_misma_es_cadena_vacia():
    assert rutas.canonica('/home/user/app', '/home/user/app') == ''


# ── lo que NO debe pasar ─────────────────────────────────────────────────

def test_un_archivo_de_afuera_no_se_disfraza_de_adentro():
    """Un path fuera del proyecto tiene que quedar absoluto: colapsarlo a algo
    relativo lo haría chocar con un archivo homónimo de adentro."""
    c = rutas.canonica('/etc/hosts', '/home/user/app')
    assert c == '/etc/hosts'


def test_un_hermano_con_prefijo_parecido_no_entra():
    # /home/user/app-viejo NO está dentro de /home/user/app, aunque empiece
    # igual. Sin el chequeo del separador, `app-viejo/x.js` se reportaría como
    # `-viejo/x.js` dentro de app.
    c = rutas.canonica('/home/user/app-viejo/x.js', '/home/user/app')
    assert c == '/home/user/app-viejo/x.js', c


def test_las_rutas_unc_no_se_mutilan():
    # Convertir las dos barras invertidas iniciales rompería la identidad de
    # la ruta UNC.
    assert rutas.a_barras(r'\\servidor\share\x') == r'\\servidor\share\x'


def test_basura_no_explota():
    for basura in ('', None, '   ', '""'):
        assert rutas.canonica(basura, '/home/user/app') == ''
    assert rutas.canonica('x.js', None) == 'x.js'
    assert rutas.canonica('x.js', '') == 'x.js'


# ── propiedad: mayúsculas donde el sistema no distingue ──────────────────

def test_la_clave_de_propiedad_respeta_el_sistema_de_archivos(monkeypatch):
    """En Windows `Src\\Index.js` y `src/index.js` son EL MISMO archivo: si
    generan claves distintas, el mismo archivo termina con dos dueños. En
    Linux son archivos distintos y unificarlos sería el bug opuesto."""
    raiz = '/home/user/app'

    monkeypatch.setattr(rutas.os, 'name', 'nt')
    assert rutas.clave_propiedad('Src/Index.js', raiz) == rutas.clave_propiedad('src/index.js', raiz)

    monkeypatch.setattr(rutas.os, 'name', 'posix')
    assert rutas.clave_propiedad('Src/Index.js', raiz) != rutas.clave_propiedad('src/index.js', raiz)


if __name__ == '__main__':
    import pytest
    raise SystemExit(pytest.main([__file__, '-q']))
