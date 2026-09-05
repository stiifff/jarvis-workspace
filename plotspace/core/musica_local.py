"""Biblioteca de música local de la Radio (V1).

La biblioteca vive en `data/music/` (redirigido por JARVIS_DATA_DIR vía
datadir.ruta_data). `listar()` recorre el árbol recursivamente (tope
MAX_ARCHIVOS) y arma items con el shape que consume la Radio; `archivo()` y
`portada()` resuelven rutas para servir archivos con seguridad de traversal.

Los tags se leen con `mutagen` SI está instalado (import opcional: si falta,
se parsea el nombre `Artista - Título.ext`). Nunca se agrega como dependencia
dura: sin mutagen la biblioteca funciona igual, con mejores nombres.

Consumidores: routers/radio.py (/api/radio/local/*) y el endpoint
GET /api/orchestrator/preview/buscar?modo=local (routers/orchestrator.py).
"""

import os
import re
from pathlib import Path
from urllib.parse import quote

from plotspace.core.datadir import ruta_data

# Extensiones de audio aceptadas (listar + archivo + subir).
AUDIO_EXTS = ('.mp3', '.m4a', '.ogg', '.opus', '.flac', '.wav')

# Portadas: si un cover existe en el MISMO dir del tema, la item lo lleva.
COVER_NOMBRES = ('cover.jpg', 'cover.png', 'folder.jpg', 'folder.png')

# Tope duro de archivos por recorre (evita listados infinitos en museos de
# 60k tracks; la Radio muestra paginas de a ~18; veracidad > exhaustividad).
MAX_ARCHIVOS = 2000

MEDIA_TYPES = {
    '.mp3': 'audio/mpeg',
    '.m4a': 'audio/mp4',
    '.ogg': 'audio/ogg',
    '.opus': 'audio/ogg',
    '.flac': 'audio/flac',
    '.wav': 'audio/wav',
}
IMAGEN_TYPES = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png'}

# Mutagen: el import es OPCIONAL (try/except). La lógica de tags vive detrás
# de `_leer_tags`; si mutagen no está, se parsea el nombre del archivo.
_MUTAGEN = False
_archivo_mutagen = None
try:
    from mutagen import File as _archivo_mutagen
    _MUTAGEN = True
except ImportError:   # pragma: no cover — depende del entorno
    pass


class MusicaError(Exception):
    """La biblioteca no se pudo listar/leer (ruta inválida, formatos, etc.)."""


def ruta_musica() -> str:
    """Raíz de la biblioteca: `<data_dir>/music` (datadir lo redirige)."""
    return ruta_data('music')


def _validar_rel(rel: str) -> str:
    """Valida un relpath de la biblioteca: relativo, sin `..`, sin abs."""
    r = (rel or '').strip().replace('\\', '/')
    if not r:
        raise MusicaError('ruta vacía')
    if r.startswith('/') or any(seg == '..' for seg in r.split('/')):
        raise MusicaError('ruta no permitida')
    return r


def _resolve_bajo(rel: str) -> Path:
    """`rel` resuelto y verificado como interno a la raíz de música
    (symlinks y `..` no escapan: Path.resolve + is_relative_to)."""
    base = Path(ruta_musica()).resolve()
    p = (base / _validar_rel(rel)).resolve()
    if not p.is_relative_to(base):
        raise MusicaError('ruta fuera de la biblioteca')
    return p


def archivo(relpath: str) -> str:
    """Camino absoluto de un archivo de audio de la biblioteca, verificado:
    ext de audio, resuelto DENTRO de ruta_musica()."""
    rel = _validar_rel(relpath)
    ext = os.path.splitext(rel)[1].lower()
    if ext not in AUDIO_EXTS:
        raise MusicaError(f'formato no soportado ({ext or "sin extensión"})')
    p = _resolve_bajo(rel)
    if not p.is_file():
        raise MusicaError('archivo inexistente')
    return str(p)


def portada(relpath: str) -> str:
    """Camino absoluto de una portada (cover.jpg/png) de la biblioteca."""
    rel = _validar_rel(relpath)
    nombre = os.path.basename(rel)
    ext = os.path.splitext(nombre)[1].lower()
    if nombre not in COVER_NOMBRES or ext not in IMAGEN_TYPES:
        raise MusicaError('portada no soportada')
    p = _resolve_bajo(rel)
    if not p.is_file():
        raise MusicaError('portada inexistente')
    return str(p)


# ─── Tags / nombres ──────────────────────────────────────────────────────────

def _primero(valor):
    """Mutagen easy devuelve listas de strings para title/artist/album."""
    if isinstance(valor, list):
        for v in valor:
            if isinstance(v, str) and v.strip():
                return v.strip()
        return None
    if isinstance(valor, str) and valor.strip():
        return valor.strip()
    return None


def _leer_tags(path: str) -> dict | None:
    """{artista, album, titulo, duracion} vía mutagen (easy=True) si está
    instalado; None si no hay tags o mutagen no se pudo importar."""
    if not _MUTAGEN:
        return None
    try:
        f = _archivo_mutagen(path, easy=True)
        if f is None:
            return None
        tags = (getattr(f, 'tags', None) or {}) if hasattr(f, 'tags') else {}
        info = getattr(f, 'info', None)
        duracion = getattr(info, 'length', None) if info is not None else None
        out = {
            'artista': _primero(tags.get('artist')),
            'album': _primero(tags.get('album')),
            'titulo': _primero(tags.get('title')),
            'duracion': duracion,
        }
        if not any(out.values()):
            return None
        return out
    except Exception:
        return None      # archivo corrupto/incompatible: fallback al nombre


_RE_PISTA = re.compile(r'^\d{1,3}[.\-_ ]\s*')


def _parsear_nombre(stem: str) -> tuple:
    """('Artista'|None, 'Título') desde el stem — el fallback sin mutagen.
    Solo arranca un artista si hay un separador ' - ' claro; un prefijo de
    número de pista se descarta porque es ruido, no un artista."""
    sin_pista = _RE_PISTA.sub('', stem)
    partes = sin_pista.split(' - ')
    if len(partes) >= 2 and partes[0].strip():
        artista = partes[0].strip()
        titulo = ' - '.join(p.strip() for p in partes[1:] if p.strip()) or sin_pista
        return artista, titulo
    return None, stem


def _formato_duracion(segundos) -> str:
    """'m:ss' a partir de segundos (Mutagen.info.length); '' si es inválido."""
    try:
        s = int(round(float(segundos)))
    except (TypeError, ValueError):
        return ''
    if s <= 0:
        return ''
    return f'{s // 60}:{s % 60:02d}'


def _cover_en(dirpath: str) -> str | None:
    for nombre in COVER_NOMBRES:
        if os.path.isfile(os.path.join(dirpath, nombre)):
            return nombre
    return None


def _item(rel: str, full: Path, raiz: Path) -> dict:
    """Item de la Radio desde un archivo: {id, titulo, canal, duracion,
    thumb, url}. thumb = cover del MISMO dir (si lo hay), url = servir por
    /api/radio/local/archivo (RUTA segura: el cliente no ve caminos)."""
    tags = _leer_tags(str(full))
    dirs = rel.split('/')[:-1]
    raiz_dir = dirs[0] if dirs else ''
    sub_dir = dirs[1] if len(dirs) > 1 else ''

    artista = tags.get('artista') if tags else None
    album = tags.get('album') if tags else None
    titulo_etiqueta = tags.get('titulo') if tags else None
    duracion = _formato_duracion(tags.get('duracion')) if tags else ''

    stem = full.stem
    if not artista and not titulo_etiqueta:
        artista_parseado, base = _parsear_nombre(stem)
        artista = artista_parseado
    else:
        base = titulo_etiqueta
    if not base:
        base = stem

    if artista and base:
        titulo = f'{artista} - {base}'
    else:
        titulo = artista or base

    if not artista:
        artista = raiz_dir
    if not album:
        album = sub_dir
    canal = '/'.join(x for x in (artista, album) if x)

    cover = _cover_en(os.path.dirname(str(full)))
    thumb = ''
    if cover:
        rel_cover = (Path(os.path.dirname(str(full))) / cover).relative_to(raiz).as_posix()
        thumb = f'/api/radio/local/thumb?p={quote(rel_cover, safe="")}'

    return {
        'id': rel,
        'titulo': titulo,
        'canal': canal,
        'duracion': duracion,
        'thumb': thumb,
        'url': f'/api/radio/local/archivo?p={quote(rel, safe="")}',
    }


def listar(carpeta: str = '', filtro: str = '') -> list:
    """Items de la biblioteca (recursivo, tope MAX_ARCHIVOS).

    `carpeta` navega un subdirectorio relativo ('' = raíz); `filtro` filtra por
    substring (case-insensitive) en titulo/canal — sin filtro devuelve todo.
    El listado es bloqueante (I/O de disco + parseo de tags): correrlo en
    `asyncio.to_thread` desde el router."""
    sub = (carpeta or '').strip()
    if sub:
        sub = _validar_rel(sub)
    raiz = Path(ruta_musica()).resolve()
    inicio = (raiz / sub).resolve() if sub else raiz
    if not inicio.is_dir():
        if not sub:
            return []           # biblioteca vacía (data/music no existe aún)
        raise MusicaError('carpeta inexistente')

    filtro_bajo = filtro.strip().lower()
    out = []
    for dirpath, dirnames, filenames in os.walk(inicio):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith('.'))
        for nombre in sorted(filenames):
            ext = os.path.splitext(nombre)[1].lower()
            if ext not in AUDIO_EXTS:
                continue
            full = Path(dirpath) / nombre
            try:
                rel = full.relative_to(raiz).as_posix()
            except ValueError:
                continue
            item = _item(rel, full, raiz)
            if filtro_bajo:
                if filtro_bajo not in item['titulo'].lower() \
                        and filtro_bajo not in item['canal'].lower():
                    continue
            out.append(item)
            if len(out) >= MAX_ARCHIVOS:
                return out
    return out


# ─── Upload (POST /api/radio/local/subir) ────────────────────────────────────

def _saneado(nombre_bruto: str) -> str:
    """Nombre de archivo seguro: solo su basename, espacios/separadores → _."""
    nombre = os.path.basename((nombre_bruto or '').replace('\\', '/')).strip()
    nombre = re.sub(r'[^\w.\-()]', '_', nombre).strip(' ._')
    return nombre or 'audio'


def _unico(dirpath: str, nombre: str) -> str:
    """Nombre con sufijo de unicidad: 'tema.mp3' → 'tema (1).mp3'."""
    destino = os.path.join(dirpath, nombre)
    if not os.path.exists(destino):
        return destino
    stem, ext = os.path.splitext(nombre)
    i = 1
    while True:
        candidato = os.path.join(dirpath, f'{stem} ({i}){ext}')
        if not os.path.exists(candidato):
            return candidato
        i += 1


def guardar(nombre_bruto: str, contenido: bytes) -> str:
    """Guarda un archivo subido en `data/music/audio/` (nombre saneado y
    único). Devuelve el nombre final. Levanta MusicaError para contenido no
    aceptable: extensiones fuera de AUDIO_EXTS se rechazan."""
    ext = os.path.splitext(nombre_bruto or '')[1].lower()
    if ext not in AUDIO_EXTS:
        raise MusicaError(f'formato no admitido ({ext or "sin extensión"}) — '
                          f'solo {" ".join(AUDIO_EXTS)}')
    destino_dir = ruta_data('music', 'audio')
    os.makedirs(destino_dir, exist_ok=True)
    final = _unico(destino_dir, _saneado(nombre_bruto))
    with open(final, 'wb') as f:
        f.write(contenido)
    return os.path.basename(final)
