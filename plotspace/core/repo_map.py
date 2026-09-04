"""
repo_map — el orquestador ve la forma del proyecto antes de planificar.

El gap que cierra: el orquestador inventaba el campo `archivos` de cada paso
sin haber visto jamás el árbol del proyecto (los ejemplos del system prompt
eran su única "idea" de estructura). Este módulo genera un mapa determinista
del repo — dirs anotados con conteo de archivos por extensión, stack detectado
por marcadores (requirements.txt, package.json, ...) y el propósito de cada
carpeta sacado de su AGENTS.md — que `_preparar_contexto_chat` inyecta como
bloque [Mapa del proyecto]. Cero API, cero tokens extra de razonamiento:
"mejorá el diseño" pasa de adivinar rutas a elegir carpetas REALES.

Cache por TTL (el chat es a ritmo humano; re-escanear cada mensaje sería
gratis igual, pero el TTL protege contra proyectos gigantes en HDD).
"""
import os
import time
from collections import Counter

# Dirs que son SIEMPRE ruido para un mapa (deps, artefactos de build, cachés).
# Los ocultos (.git, .cache, .workspace, ...) se podan por el prefijo '.'.
_DIRS_RUIDO = {'node_modules', '__pycache__', 'venv', 'dist', 'build',
               'coverage', 'target'}

# Marcadores de stack en la raíz → etiqueta legible.
_MARCADORES = [
    ('requirements.txt', 'Python'),
    ('pyproject.toml',   'Python'),
    ('package.json',     'Node/JS'),
    ('Cargo.toml',       'Rust'),
    ('go.mod',           'Go'),
    ('composer.json',    'PHP'),
    ('Gemfile',          'Ruby'),
    ('pom.xml',          'Java'),
]

TTL_S = 60.0
_cache: dict = {}   # project_path → (ts, texto)


def _stack(root: str) -> str:
    """'Python (requirements.txt) + Node/JS (package.json)' o ''."""
    partes, vistos = [], set()
    for archivo, nombre in _MARCADORES:
        if nombre not in vistos and os.path.exists(os.path.join(root, archivo)):
            vistos.add(nombre)
            partes.append(f'{nombre} ({archivo})')
    return ' + '.join(partes)


def _proposito(dir_path: str) -> str:
    """Primera línea del AGENTS.md del dir ('' si no hay): la fuente canónica
    de "qué vive acá". Si trae '<ruta> — <propósito>', se queda el propósito."""
    try:
        with open(os.path.join(dir_path, 'AGENTS.md'), encoding='utf-8',
                  errors='replace') as f:
            linea = f.readline().strip()
    except OSError:
        return ''
    linea = linea.lstrip('#').strip()
    if '—' in linea:
        linea = linea.split('—', 1)[1].strip()
    return linea[:80]


def _resumen_archivos(dir_path: str) -> str:
    """'3 .py, 2 .js' (top 2 extensiones, no recursivo; '' sin archivos)."""
    conteo = Counter()
    try:
        with os.scandir(dir_path) as it:
            for e in it:
                if e.is_file(follow_symlinks=False):
                    ext = os.path.splitext(e.name)[1] or 'sin-ext'
                    conteo[ext] += 1
    except OSError:
        return ''
    if not conteo:
        return ''
    top = conteo.most_common(2)
    partes = [f'{n} {ext}' for ext, n in top]
    resto = sum(conteo.values()) - sum(n for _, n in top)
    if resto:
        partes.append(f'+{resto}')
    return ', '.join(partes)


def generar_mapa(project_path: str, max_niveles: int = 3,
                 max_lineas: int = 60) -> str:
    """Mapa de texto del proyecto: línea de stack + árbol de dirs anotado.
    Determinista (orden alfabético). '' si la ruta no existe. Si el árbol
    excede `max_lineas`, corta con un marcador explícito — nunca en silencio."""
    if not project_path or not os.path.isdir(project_path):
        return ''

    encabezado = []
    stack = _stack(project_path)
    if stack:
        encabezado.append(f'Stack: {stack}')

    cuerpo = []

    def caminar(ruta: str, nivel: int):
        if nivel > max_niveles:
            return
        try:
            with os.scandir(ruta) as it:
                subdirs = sorted(
                    (e.name for e in it
                     if e.is_dir(follow_symlinks=False)
                     and not e.name.startswith('.')
                     and e.name not in _DIRS_RUIDO),
                )
        except OSError:
            return
        for nombre in subdirs:
            sub = os.path.join(ruta, nombre)
            linea = f"{'  ' * (nivel - 1)}{nombre}/"
            resumen = _resumen_archivos(sub)
            if resumen:
                linea += f' ({resumen})'
            prop = _proposito(sub)
            if prop:
                linea += f' — {prop}'
            cuerpo.append(linea)
            caminar(sub, nivel + 1)

    caminar(project_path, 1)

    total = len(encabezado) + len(cuerpo)
    if total > max_lineas:
        recorte = max(max_lineas - len(encabezado) - 1, 0)
        omitidas = len(cuerpo) - recorte
        cuerpo = cuerpo[:recorte] + [f'… (+{omitidas} carpetas más)']
    return '\n'.join(encabezado + cuerpo)


def bloque_mapa(project_path: str, ahora: float = None) -> str:
    """generar_mapa con cache por TTL. El hit NO refresca el timestamp
    (el snapshot expira a los TTL_S de generado, pase lo que pase)."""
    if ahora is None:
        ahora = time.time()
    hit = _cache.get(project_path)
    if hit and (ahora - hit[0]) < TTL_S:
        return hit[1]
    texto = generar_mapa(project_path)
    _cache[project_path] = (ahora, texto)
    return texto
