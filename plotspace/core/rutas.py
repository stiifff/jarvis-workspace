"""La forma ÚNICA con la que el enjambre identifica un archivo.

EL PROBLEMA QUE RESUELVE
========================
Con terminales de shells distintos sobre el mismo proyecto, el mismo archivo
tiene varios nombres:

    PowerShell   C:\\proyectos\\app\\src\\index.js
    WSL          /mnt/c/proyectos/app/src/index.js
    y desde Windows, un proyecto que vive adentro de WSL:
                 \\\\wsl.localhost\\Ubuntu\\home\\user\\app\\src\\index.js

Todo el sistema de coordinación —territorio, provenance, el candado de
propiedad, LIVE.md, el mailbox— identifica archivos POR SU RUTA. Si un agente
en PowerShell reclama uno y otro en WSL reclama el mismo con otro nombre, el
guard no ve la colisión y **se pisan en silencio**. Es la falla más cara de
todo el port: no rompe nada visiblemente, corrompe trabajo.

LA REGLA
========
Una sola forma canónica —ruta relativa al proyecto, con `/`— y la traducción
**en el borde**: al lanzar la terminal y al recibir el reporte del hook. Nunca
en el medio. Si alguien traduce a mitad de camino, vuelven las dos claves.
"""
import os
import re
from typing import Optional

# /mnt/c/... ⇄ C:\...  — el montaje de los discos de Windows dentro de WSL.
_MNT_RE = re.compile(r'^/mnt/([a-zA-Z])(/|$)')
# C:\... o C:/...
_UNIDAD_RE = re.compile(r'^([a-zA-Z]):[\\/]')
# \\wsl.localhost\<distro>\...  o el viejo \\wsl$\<distro>\...  — cómo ve
# Windows el sistema de archivos de una distro.
_UNC_WSL_RE = re.compile(r'^\\\\wsl(?:\.localhost|\$)\\([^\\]+)\\?(.*)$', re.IGNORECASE)


def limpiar(p: str) -> str:
    """Saca comillas, espacios y el `./` inicial. No traduce nada."""
    p = (p or '').strip().strip('"\'')
    while p.startswith('./'):
        p = p[2:]
    return p


def a_barras(p: str) -> str:
    """Separadores a `/`. Las rutas UNC (`\\\\wsl.localhost\\...`) se dejan como
    están: su prefijo de dos barras invertidas ES parte de su identidad y
    convertirlo la rompe."""
    if p.startswith('\\\\'):
        return p
    return p.replace('\\', '/')


def a_forma_wsl(p: str) -> str:
    """La misma ruta vista desde adentro de una distro.

    `C:\\x\\y` → `/mnt/c/x/y` · `\\\\wsl.localhost\\Ubuntu\\home\\u` → `/home/u`
    Lo que ya es de Unix vuelve igual.
    """
    p = limpiar(p)
    m = _UNC_WSL_RE.match(p)
    if m:
        resto = m.group(2).replace('\\', '/')
        return '/' + resto.lstrip('/')
    m = _UNIDAD_RE.match(p)
    if m:
        resto = p[3:].replace('\\', '/')
        return f'/mnt/{m.group(1).lower()}/' + resto.lstrip('/')
    return a_barras(p)


def a_forma_windows(p: str, distro: Optional[str] = None) -> str:
    """La misma ruta vista desde Windows.

    `/mnt/c/x/y` → `C:/x/y`. Una ruta de la distro (`/home/u/x`) solo se puede
    expresar si sabemos CUÁL distro: sin ese dato se devuelve igual, porque
    inventar una sería peor que no traducir.
    """
    p = limpiar(p)
    m = _MNT_RE.match(p)
    if m:
        resto = p[len(f'/mnt/{m.group(1)}'):].lstrip('/')
        return f'{m.group(1).upper()}:/' + resto
    if p.startswith('/') and distro:
        return f'\\\\wsl.localhost\\{distro}' + p.replace('/', '\\')
    return a_barras(p)


def _relativizar(path: str, raiz: str) -> Optional[str]:
    """`path` relativo a `raiz`, o None si no cae adentro. Case-insensitive
    solo donde el sistema de archivos lo es (Windows): en Linux `Foo.js` y
    `foo.js` SON archivos distintos y tratarlos como uno sería un bug."""
    if not raiz:
        return None
    base = raiz.rstrip('/').rstrip('\\')
    if not base:
        return None
    if os.name == 'nt':
        if path.lower() == base.lower():
            return ''
        if path.lower().startswith(base.lower() + '/'):
            return path[len(base) + 1:]
        return None
    if path == base:
        return ''
    if path.startswith(base + '/'):
        return path[len(base) + 1:]
    return None


def canonica(path: str, raiz_proyecto: Optional[str] = None,
             distro: Optional[str] = None) -> str:
    """La clave con la que el enjambre identifica este archivo.

    Relativa al proyecto cuando cae adentro (que es el caso normal y el que
    hace que dos agentes en shells distintos coincidan); si no, la ruta
    normalizada con `/`. Se prueban las dos formas —Windows y WSL— contra la
    raíz, porque el reporte puede venir de cualquiera de los dos mundos y la
    raíz está escrita en uno solo.
    """
    p = limpiar(path)
    if not p:
        return ''
    if raiz_proyecto:
        raiz = limpiar(raiz_proyecto)
        for candidato, base in (
            (a_barras(p),            a_barras(raiz)),
            (a_forma_wsl(p),         a_forma_wsl(raiz)),
            (a_forma_windows(p, distro), a_forma_windows(raiz, distro)),
        ):
            rel = _relativizar(candidato, base)
            if rel is not None:
                return rel
    # Fuera del proyecto (o sin raíz conocida): normalizada, sin inventar nada.
    return a_barras(p)


def clave_propiedad(path: str, raiz_proyecto: Optional[str] = None) -> str:
    """La clave para comparar PROPIEDAD entre agentes.

    Igual que `canonica`, pero en minúsculas donde el sistema de archivos no
    distingue mayúsculas (Windows). Sin esto, un agente que reporta
    `Src\\Index.js` y otro que reporta `src/index.js` se pisarían sin que el
    guard viera la colisión — el mismo archivo con dos dueños.
    """
    c = canonica(path, raiz_proyecto)
    return c.lower() if os.name == 'nt' else c
