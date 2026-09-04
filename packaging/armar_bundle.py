#!/usr/bin/env python3
"""Arma el bundle que viaja adentro del instalador.

QUÉ ENTRA Y POR QUÉ
===================
El objetivo es un instalador de ~150 MB. La cuenta:

    motor (plotspace + frontend) .... ~18 MB   el producto
    dependencias base ............... ~60 MB   fastapi, uvicorn, httpx, anthropic
    termhost ........................  ~1 MB   el motor de terminales
    Python embebido ................. ~15 MB   lo pone el empaquetador del sistema
    Node ............................ ~60 MB   para instalar los CLIs (es MIT)

Lo que NO entra, aunque esté instalado en la máquina de desarrollo:

    playwright + chromium ........... ~780 MB  solo el browser remoto del Preview
    onnxruntime + modelos de voz .... ~400 MB  con STT_MOTOR=groq no hace falta
    ctranslate2 ..................... ~60 MB   la vía de escape del dictado

Esas tres son EXTRAS: se bajan si el usuario las pide. Meterlas por las dudas
convierte un instalador de 150 MB en uno de 1,3 GB, y la mayoría de la gente
nunca usa el browser remoto ni el dictado local.

Los CLIs de agente NO se bundlean nunca: son producto de otro, con su licencia
y su login. Ver core/clis.py.

    python3 packaging/armar_bundle.py --salida dist/bundle [--medir]
"""
import argparse
import os
import shutil
import sys

# La consola de Windows usa cp1252 y revienta al imprimir cualquier carácter
# fuera de ASCII (un ─, un ✓, una tilde). Forzar UTF-8 en la salida deja que el
# mismo script corra en los tres sistemas sin escribir en ASCII pelado.
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except (AttributeError, OSError):
    pass


RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Lo que se copia del repo. Rutas relativas a la raíz.
INCLUIR = ['plotspace', 'frontend', 'scripts']

# Lo que NO viaja aunque esté adentro de esas carpetas.
EXCLUIR_DIRS = {
    '__pycache__', '.pytest_cache', 'node_modules', '.git',
    'tests',        # la suite no le sirve a nadie en una instalación
    '__tests__',    # ídem del frontend
}

# Prototipos y galerías que viven en frontend/ pero no son la app. El criterio
# es el mismo que usa dev_detect para saber qué es la app y qué no.
DIRS_DE_LA_APP = {'sections', 'shared', 'shell', 'vendor'}

EXCLUIR_SUFIJOS = ('.pyc', '.pyo', '.log', '.db', '.db-wal', '.db-shm')

# Paquetes pesados que quedan AFUERA del bundle base. Se instalan aparte si el
# usuario prende la función que los necesita.
EXTRAS = {
    'playwright':    'browser remoto del Web Preview',
    'onnxruntime':   'dictado local (con Groq no hace falta)',
    'ctranslate2':   'dictado local, vía de escape',
    'faster_whisper': 'dictado local, vía de escape',
    'onnx_asr':      'dictado local',
}


def es_de_la_app(rel: str) -> bool:
    """¿Este archivo del frontend es LA APP o un prototipo?

    `frontend/` acumuló galerías, mockups y previews de diseño (medidos:
    cientos de MB). Son valiosos en el repo y basura en un instalador."""
    partes = rel.replace('\\', '/').split('/')
    if partes[0] != 'frontend' or len(partes) < 2:
        return True
    if len(partes) == 2:
        return True                       # archivo suelto en la raíz (index.html)
    return partes[1] in DIRS_DE_LA_APP


def debe_copiarse(rel: str) -> bool:
    """La regla completa, PURA: se testea sin tocar el disco."""
    partes = rel.replace('\\', '/').split('/')
    if any(p in EXCLUIR_DIRS for p in partes):
        return False
    if rel.endswith(EXCLUIR_SUFIJOS):
        return False
    return es_de_la_app(rel)


def es_extra(nombre_paquete: str) -> bool:
    """¿Este paquete instalado es un EXTRA que no va en el bundle base?"""
    base = nombre_paquete.split('-')[0].split('.')[0].lower()
    return any(base.startswith(e) for e in EXTRAS)


def copiar_motor(salida: str) -> int:
    """Copia el producto. Devuelve cuántos archivos."""
    n = 0
    for top in INCLUIR:
        origen = os.path.join(RAIZ, top)
        if not os.path.isdir(origen):
            continue
        for dirpath, dirnames, filenames in os.walk(origen):
            dirnames[:] = [d for d in dirnames if d not in EXCLUIR_DIRS]
            for f in filenames:
                abs_ = os.path.join(dirpath, f)
                rel = os.path.relpath(abs_, RAIZ)
                if not debe_copiarse(rel):
                    continue
                destino = os.path.join(salida, rel)
                os.makedirs(os.path.dirname(destino), exist_ok=True)
                shutil.copy2(abs_, destino)
                n += 1
    return n


def copiar_termhost(salida: str) -> bool:
    """El motor de terminales, si está compilado."""
    nombre = 'plotspace-termhost.exe' if os.name == 'nt' else 'plotspace-termhost'
    origen = os.path.join(RAIZ, 'desktop', 'termhost', 'target', 'release', nombre)
    if not os.path.exists(origen):
        return False
    destino_dir = os.path.join(salida, 'bin')
    os.makedirs(destino_dir, exist_ok=True)
    shutil.copy2(origen, os.path.join(destino_dir, nombre))
    return True


# ─── El `._pth` del Python embebido de Windows ───────────────────────────────
#
# El embeddable NO usa el sys.path normal: lo define este archivo, que vive al
# lado del python.exe. Y sus rutas son relativas a ESA carpeta
# (`motor/python/`), no al directorio de trabajo — por eso van con `..`.
#
# El 2026-07-27 esto se escribía con `echo lib >> …._pth` dentro del workflow.
# `lib` resolvía a `motor/python/lib`, que no existe, y `motor/` (donde vive el
# paquete `plotspace`) nunca entraba al path. La app abría el splash y se
# quedaba en «Esperando al motor…» mientras el motor moría con
# ModuleNotFoundError — invisible, porque el shell lo lanza con stdout y stderr
# en null.

def lineas_pth(zip_stdlib: str = 'python312.zip'):
    """Contenido del `pythonXY._pth`, en orden."""
    return [
        zip_stdlib,   # la biblioteca estándar
        '.',          # la carpeta del intérprete
        '..',         # motor/ → el paquete `plotspace`
        '..\\lib',    # motor/lib → uvicorn, fastapi y las demás
        '',
        'import site',
    ]


def resolver_pth(lineas, python_home: str):
    """A qué directorios apuntan esas líneas, dado dónde está el python.exe.

    Es la traducción que hace el intérprete al arrancar; tenerla acá permite
    verificar en un test que las rutas caen donde tienen que caer.
    """
    base = python_home.rstrip('/\\').replace('\\', '/')
    destinos = []
    for l in lineas:
        l = l.strip()
        if not l or l.startswith('#') or l.startswith('import '):
            continue
        partes = [p for p in l.replace('\\', '/').split('/') if p]
        acum = base.split('/')
        for p in partes:
            if p == '..':
                acum = acum[:-1]
            elif p != '.':
                acum.append(p)
        destinos.append('/'.join(acum))
    return destinos


def _mb(ruta: str) -> float:
    total = 0
    for dirpath, _, filenames in os.walk(ruta):
        for f in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, f))
            except OSError:
                pass
    return total / 1048576


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--salida', default=os.path.join(RAIZ, 'dist', 'bundle'))
    ap.add_argument('--medir', action='store_true',
                    help='reporta el peso de cada parte')
    ap.add_argument('--escribir-pth', metavar='RUTA',
                    help='escribe el ._pth del Python embebido y sale')
    args = ap.parse_args()

    if args.escribir_pth:
        # CRLF: es un archivo de Windows y lo lee el intérprete de Windows.
        with open(args.escribir_pth, 'w', newline='\r\n') as f:
            f.write('\n'.join(lineas_pth()) + '\n')
        print(f'._pth escrito en {args.escribir_pth}:')
        for d in resolver_pth(lineas_pth(),
                              os.path.dirname(os.path.abspath(args.escribir_pth))):
            print(f'  → {d}')
        return

    if os.path.exists(args.salida):
        shutil.rmtree(args.salida)
    os.makedirs(args.salida, exist_ok=True)

    n = copiar_motor(args.salida)
    hay_termhost = copiar_termhost(args.salida)
    print(f'motor: {n} archivos')
    print(f'termhost: {"incluido" if hay_termhost else "NO COMPILADO (falta cargo build --release)"}')

    if args.medir:
        print('\n── peso ──')
        for parte in ('plotspace', 'frontend', 'scripts', 'bin'):
            p = os.path.join(args.salida, parte)
            if os.path.isdir(p):
                print(f'  {parte:<12} {_mb(p):7.1f} MB')
        total = _mb(args.salida)
        print(f'  {"TOTAL":<12} {total:7.1f} MB')
        print('\n  faltan por sumar (los pone el empaquetador de cada sistema):')
        print('    Python embebido ~15 MB · dependencias base ~60 MB · Node ~60 MB')
        print(f'    → instalador estimado: ~{total + 135:.0f} MB')
        print('\n  extras que NO van (se bajan si el usuario los pide):')
        for nombre, para_que in EXTRAS.items():
            print(f'    {nombre:<16} {para_que}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
