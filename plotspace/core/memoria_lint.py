"""
memoria_lint — salud determinista de la memoria compartida (.jarvis/memory/).

La memoria del proyecto no tenía validación: los wikilinks rotos eran
invisibles (el grafo de la UI solo dibuja edges hacia slugs existentes), las
memorias que citan archivos ya borrados envejecían en silencio y nadie
detectaba huérfanas. Este linter lo hace visible SIN gastar un token:
lo consume `GET /api/projects/{id}/memory/salud` (pestaña Memoria) y sirve
de verificador para la reparación de links.

Chequeos:
  - rotos:         [[wikilink]] hacia un slug que no existe en la carpeta
                   (incluye links-prosa: se normalizan igual que el router)
  - citas_muertas: rutas de archivo citadas en el cuerpo que ya no existen
                   en el proyecto (solo si su primer segmento SÍ existe como
                   directorio — así `src/x.js` de un ejemplo no es ruido)
  - huerfanas:     memorias sin ningún link entrante ni saliente
  - obsoletas:     memorias con `estado:` distinto de vigente (obsoleta/lapida)

Stdlib pura y sin imports de routers (la capa router la consume, no al revés).
"""
import os
import re
import unicodedata
from datetime import date

from plotspace.core import memoria_categorias as mcat

_WIKILINK_RE = re.compile(r'\[\[([^\]\n]+)\]\]')
_SLUG_LIMPIO = re.compile(r'[^a-z0-9]+')
# Tokenización compartida (la usa también memoria_recall para BM25 y
# memoria_endurecimiento para el matching motivo↔lección): tokens de 3+
# chars (incluye 'pty', 'wsl', 'oom'), minúsculas, sin palabras-función.
_TOKEN_RE = re.compile(r'[a-zá-úñ0-9]{3,}')
_STOP = {
    'que', 'los', 'las', 'una', 'unos', 'unas', 'del', 'con', 'por', 'para',
    'como', 'mas', 'pero', 'sus', 'este', 'esta', 'esto', 'esos', 'esas',
    'nada', 'todo', 'toda', 'todos', 'todas', 'ver', 'ser', 'son', 'hay',
    'muy', 'sin', 'sobre', 'entre', 'cuando', 'donde', 'porque', 'aunque',
    'desde', 'hasta', 'segun', 'tras', 'ante', 'bajo', 'cada', 'algo',
    'otro', 'otra', 'otros', 'otras', 'mismo', 'misma', 'ese', 'esa',
    'the', 'and', 'for', 'you', 'era', 'fue', 'sea',
}


def _tokens_sig(texto: str) -> set:
    return {t for t in _TOKEN_RE.findall((texto or '').lower()) if t not in _STOP}
_ESTADO_RE   = re.compile(r'^estado:\s*(\S+)', re.MULTILINE)
_FRONT_RE    = re.compile(r'^---\s*\n(.*?)\n---\s*\n?', re.DOTALL)
_TAGS_RE     = re.compile(r'^tags:\s*\[([^\]]*)\]', re.MULTILINE)
_TITULO_RE   = re.compile(r'^titulo:\s*(.+)$', re.MULTILINE)
_REEMP_RE    = re.compile(r'^reemplazada-por:\s*(\S+)', re.MULTILINE)
_CAT_RE      = re.compile(r'^categoria:\s*(\S+)', re.MULTILINE)
_FECHA_RE    = re.compile(r'^(?:creado|actualizado|fecha):\s*(\d{4}-\d{2}-\d{2})', re.MULTILINE)

# Contrato de admisión: una memoria floja confunde más de lo que aporta.
_MAX_LINEAS_CUERPO = 150      # más largo que esto = informe, no memoria
_MIN_TITULO = 12
# Patrón bitácora en título/slug: año-mes ("auditoría 2026-06-20"). La fecha
# de una memoria va en creado:/actualizado:, no en su identidad.
_FECHA_TITULO_RE = re.compile(r'20\d{2}-\d{2}')
# Duplicados: dos vigentes con esta similitud de Jaccard son la misma memoria
# escrita dos veces — reconciliar (fusionar en una, archivar la otra).
_DUP_UMBRAL = 0.5
# Cuarentena: vieja sin refresco ni uso registrado → re-verificar o archivar.
def _dias_cuarentena() -> int:
    try:
        return max(1, int(os.environ.get('MEMORIA_CUARENTENA_DIAS', '60')))
    except ValueError:
        return 60
# Ruta relativa tipo `plotspace/core/x.py` (2+ segmentos, extensión de código/doc)
_PATH_RE = re.compile(
    r'(?<![\w/])([A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)+\.'
    r'(?:py|js|mjs|ts|css|html|md|sh|rs|json|yml|yaml|toml))\b')


def _slugificar(texto: str) -> str:
    """Misma normalización que el router de memoria: los links-prosa
    ([[gesto anti-slop]]) se convierten al slug que 'deberían' ser."""
    s = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode()
    return _SLUG_LIMPIO.sub('-', s.lower()).strip('-')


def _citas_muertas_de(cuerpo: str, project_path: str) -> list:
    """Rutas citadas que no existen. Heurística anti-ruido: solo cuenta si el
    PRIMER segmento existe como directorio del proyecto (una cita real a código
    borrado, no un path de ejemplo)."""
    muertas = []
    for ruta in sorted(set(_PATH_RE.findall(cuerpo))):
        if ruta.startswith(('http', '~', '/')):
            continue
        primer_dir = ruta.split('/', 1)[0]
        if not os.path.isdir(os.path.join(project_path, primer_dir)):
            continue
        if not os.path.exists(os.path.join(project_path, ruta)):
            muertas.append(ruta)
    return muertas


def _meta_de(src: str) -> dict:
    """Metadatos livianos del frontmatter para los chequeos de coherencia."""
    m = _FRONT_RE.match(src)
    front = m.group(1) if m else ''
    cuerpo = src[m.end():] if m else src
    me = _ESTADO_RE.search(front)
    mt = _TAGS_RE.search(front)
    mti = _TITULO_RE.search(front)
    mr = _REEMP_RE.search(front)
    mc = _CAT_RE.search(front)
    fechas = _FECHA_RE.findall(front)
    tags = [t.strip().lower() for t in mt.group(1).split(',') if t.strip()] if mt else []
    return {
        'estado': (me.group(1).strip().lower() if me else 'vigente'),
        'estado_explicito': bool(me),
        'tags': tags,
        'titulo': (mti.group(1).strip().strip('"\'') if mti else ''),
        'reemplazada_por': (mr.group(1).strip() if mr else ''),
        # categoría explícita del frontmatter (o '' → el caller la infiere con el slug)
        'categoria_raw': (mc.group(1).strip().lower() if mc and mcat.es_valida(mc.group(1).strip().lower())
                          else ''),
        'fecha': max(fechas) if fechas else '',
        'lineas_cuerpo': len([l for l in cuerpo.splitlines() if l.strip()]),
        'cuerpo': cuerpo,
    }


def lint_memorias(project_path: str, hoy: str = None, usados: set = None) -> dict:
    """Corre todos los chequeos sobre la memoria compartida del proyecto.

    `hoy` (YYYY-MM-DD) y `usados` (slugs con uso registrado en el audit trail)
    alimentan la cuarentena; por default hoy=fecha actual y usados=∅."""
    d = os.path.join(project_path, '.jarvis', 'memory')
    out = {'total': 0, 'rotos': [], 'citas_muertas': [], 'huerfanas': [],
           'obsoletas': [], 'archivadas': 0, 'contrato': [], 'incoherencias': [],
           'choques': [], 'cuarentena': [], 'duplicados': [], 'por_categoria': {}}
    if not os.path.isdir(d):
        return out

    fuentes = {}
    for nombre in sorted(os.listdir(d)):
        if not nombre.endswith('.md') or nombre == 'INDEX.md':
            continue
        try:
            with open(os.path.join(d, nombre), encoding='utf-8', errors='replace') as f:
                fuentes[nombre[:-3]] = f.read()
        except OSError:
            continue

    out['total'] = len(fuentes)
    metas, rutas_por_slug = {}, {}
    con_link = set()          # slugs con al menos un link (in o out)
    # rollup de salud por categoría (solo memorias vigentes)
    cats = {}
    def _cat(cid):
        return cats.setdefault(cid, {'total': 0, 'rotos': 0, 'citas_muertas': 0,
                                     'huerfanas': 0, 'contrato': 0})

    for slug, src in fuentes.items():
        meta = _meta_de(src)
        # categoría final: explícita, o inferida por tags+slug (como el parser)
        meta['categoria'] = meta['categoria_raw'] or mcat.clasificar(meta['tags'], slug)
        metas[slug] = meta
        destinos = {_slugificar(x) for x in _WIKILINK_RE.findall(src)}
        destinos.discard(slug)
        if destinos:
            con_link.add(slug)
        rotos_slug = 0
        for destino in sorted(destinos):
            if destino in fuentes:
                con_link.add(destino)
            else:
                out['rotos'].append({'slug': slug, 'destino': destino})
                rotos_slug += 1

        muertas = _citas_muertas_de(src, project_path)
        for ruta in muertas:
            out['citas_muertas'].append({'slug': slug, 'ruta': ruta})
        rutas_por_slug[slug] = set(_PATH_RE.findall(src))

        if meta['estado'] == 'archivo':
            out['archivadas'] += 1
            continue     # lo archivado no entra en el rollup ni en el contrato
        if meta['estado'] != 'vigente':
            out['obsoletas'].append(slug)

        # rollup por categoría (vigentes + obsoletas/lápidas en circulación)
        c = _cat(meta['categoria'])
        c['total'] += 1
        c['rotos'] += rotos_slug
        c['citas_muertas'] += len(muertas)

        # Contrato de admisión (solo vigentes: lo archivado ya está curado)
        if meta['estado'] == 'vigente':
            faltas = []
            if not meta['tags']:
                faltas.append('sin-tags')
            if len(meta['titulo']) < _MIN_TITULO:
                faltas.append('titulo-vago')
            if meta['lineas_cuerpo'] > _MAX_LINEAS_CUERPO:
                faltas.append(f'demasiado-largo ({meta["lineas_cuerpo"]} líneas — ¿informe?)')
            if not meta['fecha']:
                faltas.append('sin-fecha')
            if meta['categoria'] == mcat.SIN_CLASIFICAR:
                faltas.append('sin-clasificar (poné categoria:)')
            if not meta['estado_explicito']:
                faltas.append('sin-estado (vigente|obsoleta|lapida|archivo)')
            if _FECHA_TITULO_RE.search(meta['titulo']) or _FECHA_TITULO_RE.search(slug):
                faltas.append('titulo-con-fecha (¿bitácora? la fecha va en creado:)')
            if faltas:
                out['contrato'].append({'slug': slug, 'faltas': faltas})
                c['contrato'] += 1

        # Canonicidad: una vigente que dice estar reemplazada es incoherente
        if meta['estado'] == 'vigente' and meta['reemplazada_por']:
            out['incoherencias'].append({
                'slug': slug,
                'motivo': f"vigente pero marcada reemplazada-por {meta['reemplazada_por']} "
                          "— archivala o quitá el campo"})

    out['huerfanas'] = sorted(set(fuentes) - con_link)
    for slug in out['huerfanas']:
        m = metas.get(slug)
        if m and m['estado'] != 'archivo' and m['categoria'] in cats:
            cats[m['categoria']]['huerfanas'] += 1

    # Choques estructurales: una VIGENTE que pisa la zona de una LÁPIDA
    # (misma ruta citada) probablemente recomienda algo que se eliminó.
    # Anti-ruido: las rutas-hub (citadas por muchas memorias, ej. main.py)
    # no son señal — compartirlas es lo normal del corpus.
    frecuencia = {}
    for rutas in rutas_por_slug.values():
        for r_ in rutas:
            frecuencia[r_] = frecuencia.get(r_, 0) + 1
    lapidas = [s for s, m in metas.items() if m['estado'] == 'lapida']
    vigentes = [s for s, m in metas.items() if m['estado'] == 'vigente']
    for lap in lapidas:
        for vig in vigentes:
            compartidas = {r_ for r_ in rutas_por_slug[lap] & rutas_por_slug[vig]
                           if frecuencia.get(r_, 0) <= 2}
            if compartidas:
                out['choques'].append({'a': lap, 'b': vig,
                                       'senal': f'ruta compartida: {sorted(compartidas)[0]}'})

    # Duplicados: dos VIGENTES casi iguales = la misma memoria escrita dos
    # veces (reconciliación al escribir que no pasó). Jaccard sobre tokens
    # significativos de título+cuerpo; O(N²) sobre vigentes — trivial a esta
    # escala. Un par ya declarado con reemplazada-por no es duplicado.
    toks_vig = {s: _tokens_sig(metas[s]['titulo'] + ' ' + metas[s]['cuerpo'])
                for s in vigentes}
    for i, a in enumerate(vigentes):
        for b in vigentes[i + 1:]:
            if metas[a]['reemplazada_por'] == b or metas[b]['reemplazada_por'] == a:
                continue
            ta, tb = toks_vig[a], toks_vig[b]
            union = len(ta | tb)
            if not union:
                continue
            sim = len(ta & tb) / union
            if sim >= _DUP_UMBRAL:
                out['duplicados'].append({'a': a, 'b': b, 'similitud': round(sim, 2)})
    out['duplicados'].sort(key=lambda p: -p['similitud'])
    del out['duplicados'][20:]

    # Cuarentena (propone, no ejecuta): vigente vieja, sin refresco ni uso
    usados = usados or set()
    try:
        ref = date.fromisoformat(hoy) if hoy else date.today()
    except ValueError:
        ref = date.today()
    umbral = _dias_cuarentena()
    for slug in vigentes:
        f = metas[slug]['fecha']
        if not f or slug in usados:
            continue
        try:
            edad = (ref - date.fromisoformat(f)).days
        except ValueError:
            continue
        if edad > umbral:
            out['cuarentena'].append(slug)
    out['cuarentena'].sort()

    # salud por categoría, en el orden canónico + nombre legible
    out['por_categoria'] = {
        cid: {'nombre': mcat.NOMBRE.get(cid, cid), **cats[cid]}
        for cid in (mcat.ORDEN + [mcat.SIN_CLASIFICAR]) if cid in cats
    }
    return out


def auto_archivar(project_path: str, hoy: str = None, usados: set = None,
                  dias_extra: int = 30) -> list:
    """Salud que EJECUTA (solo lo reversible): una vigente más vieja que
    cuarentena+gracia, sin refresco NI uso registrado, pasa sola a
    `estado: archivo` (con marca `archivado-auto:`). Reversible con un
    edit; el que la buscaba la encuentra igual (el archivo queda).
    Devuelve los slugs archivados."""
    d = os.path.join(project_path, '.jarvis', 'memory')
    if not os.path.isdir(d):
        return []
    usados = usados or set()
    try:
        ref = date.fromisoformat(hoy) if hoy else date.today()
    except ValueError:
        ref = date.today()
    umbral = _dias_cuarentena() + max(0, dias_extra)
    archivadas = []
    for nombre in sorted(os.listdir(d)):
        if not nombre.endswith('.md') or nombre in ('INDEX.md', 'lecciones-del-enjambre.md'):
            continue
        slug = nombre[:-3]
        if slug in usados:
            continue
        path = os.path.join(d, nombre)
        try:
            with open(path, encoding='utf-8', errors='replace') as f:
                src = f.read()
        except OSError:
            continue
        meta = _meta_de(src)
        if meta['estado'] != 'vigente' or not meta['fecha']:
            continue
        try:
            edad = (ref - date.fromisoformat(meta['fecha'])).days
        except ValueError:
            continue
        if edad <= umbral:
            continue
        m = _FRONT_RE.match(src)
        if not m:
            continue
        front = m.group(1)
        if _ESTADO_RE.search(front):
            front_nuevo = _ESTADO_RE.sub('estado: archivo', front, count=1)
        else:
            front_nuevo = front + '\nestado: archivo'
        front_nuevo += f'\narchivado-auto: {ref.isoformat()} (cuarentena vencida sin uso)'
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(src[:m.start(1)] + front_nuevo + src[m.end(1):])
            archivadas.append(slug)
        except OSError:
            continue
    return archivadas


def similares(project_path: str, texto: str, k: int = 3, umbral: float = 0.35) -> list:
    """Slugs de memorias VIGENTES que ya cubren (parte de) este texto — la
    señal de reconciliación al escribir: si hay una similar, lo correcto es
    actualizarla, no crear otra. Containment del texto nuevo (|∩|/|nuevo|):
    a diferencia del Jaccard, no castiga que la memoria existente sea larga."""
    toks = _tokens_sig(texto)
    if not toks:
        return []
    d = os.path.join(project_path, '.jarvis', 'memory')
    if not os.path.isdir(d):
        return []
    puntuadas = []
    for nombre in sorted(os.listdir(d)):
        if not nombre.endswith('.md') or nombre == 'INDEX.md':
            continue
        try:
            with open(os.path.join(d, nombre), encoding='utf-8', errors='replace') as f:
                src = f.read()
        except OSError:
            continue
        meta = _meta_de(src)
        if meta['estado'] != 'vigente':
            continue
        cont = len(toks & _tokens_sig(meta['titulo'] + ' ' + meta['cuerpo'])) / len(toks)
        if cont >= umbral:
            puntuadas.append((cont, nombre[:-3]))
    puntuadas.sort(key=lambda x: (-x[0], x[1]))
    return [slug for _, slug in puntuadas[:k]]
