"""El `._pth` del Python embebido de Windows.

QUÉ SE ROMPIÓ (2026-07-27)
==========================
La app instalada abría el splash y se quedaba en «Esperando al motor… (60s)».
El motor arrancaba y moría al instante con:

    ModuleNotFoundError: No module named 'plotspace'

El Python EMBEDDABLE de Windows no usa el `sys.path` normal: lo define un
archivo `pythonXY._pth` al lado del ejecutable, y **sus rutas son relativas a
la carpeta de ese ejecutable**, no al directorio de trabajo. El empaquetador
escribía `lib`, que resolvía a `motor/python/lib` — inexistente — y nunca
ponía `motor/` en el path, que es donde vive el paquete `plotspace`.

Nada de esto se veía: el shell lanza el motor con stdout y stderr en null, así
que el traceback moría ahí y la única señal era el contador subiendo.

Por eso el contenido del `._pth` se calcula en código y se testea acá, en vez
de armarse con `echo` sueltos dentro del YAML del workflow — donde no hay
manera de que un test lo mire.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'packaging'))

from armar_bundle import lineas_pth, resolver_pth


def test_el_paquete_de_la_app_queda_importable():
    # El fallo real: sin `..` en el path, el embeddable no ve `motor/plotspace`
    # y el motor muere con ModuleNotFoundError antes de escuchar el puerto.
    destinos = resolver_pth(lineas_pth(), python_home='C:/app/motor/python')
    assert 'C:/app/motor' in destinos, destinos


def test_las_dependencias_quedan_importables():
    # uvicorn, fastapi y las otras 35 viven en motor/lib.
    destinos = resolver_pth(lineas_pth(), python_home='C:/app/motor/python')
    assert 'C:/app/motor/lib' in destinos, destinos


def test_ninguna_ruta_apunta_adentro_de_python():
    # El bug exacto: `lib` a secas resolvía a motor/python/lib, que no existe.
    # Ninguna entrada nuestra puede quedar bajo la carpeta del intérprete.
    destinos = resolver_pth(lineas_pth(), python_home='C:/app/motor/python')
    nuestras = [d for d in destinos if d.endswith(('/motor', '/lib'))]
    assert nuestras, 'no quedó ninguna ruta de la app'
    for d in nuestras:
        assert not d.startswith('C:/app/motor/python/'), d


def test_conserva_el_zip_de_la_stdlib():
    # Sin el .zip no hay biblioteca estándar: el intérprete no arranca.
    assert any(l.strip().endswith('.zip') for l in lineas_pth()), lineas_pth()


def test_habilita_site():
    # Sin `import site` el embeddable ignora todo lo que no esté en el ._pth,
    # incluidos los .pth que dejan algunos paquetes al instalarse.
    assert 'import site' in [l.strip() for l in lineas_pth()]
