# plotspace/core/provenance.py
"""Provenance del enjambre — quién editó qué, con el dato REAL de la herramienta.

POR QUÉ EXISTE
--------------
`agent_live` deducía la propiedad de archivos parseando el pane tmux en busca de
`● Update(archivo)`. Claude Code 2.1.x dejó de imprimir eso: colapsa las
tool-calls en un resumen que ni siquiera nombra el archivo ("Making 1 scratchpad
edit +2, running 1 shell command"). Medido: 4,8 MB de log de dos agentes → CERO
operaciones detectadas. Con eso se murieron en silencio la propiedad, el guard
de commits, `commit_propio.py` y las alertas de conflicto.

La lección no es "arreglar el regex": el pane es una superficie de PRESENTACIÓN
que controla un tercero y cambia cada semana (5 versiones del CLI en 5 días). La
provenance pasa a leerse del CONTRATO de la herramienta, vía hook PostToolUse:
el payload trae `file_path` y el contenido exacto de la edición.

DEFENSA CONTRA EL MISMO ERROR
-----------------------------
`normalizar_payload` acepta TODAS las formas conocidas del payload
(`old_string`/`new_string`, `edits[].old_text/new_text`, `content`/`file_text`,
`new_source`) y, ante una forma desconocida, DEGRADA sin perder lo esencial:
registra igual la escritura del archivo con contenido vacío. Perder el detalle
del hunk es aceptable; perder la propiedad es lo que nos costó el subsistema.

QUÉ HABILITA
------------
  Fase 0 · propiedad y conflictos con dato real (agent_live.registrar_op_externa)
  Fase 1 · `commit_propio` por HUNK: el server sabe qué texto insertó cada agente
  Fase 2 · colisión por FUNCIONALIDAD: qué símbolos borró uno que otro referencia

La capa pura (normalizar/simbolos/…) no toca red, DB ni tmux: se testea sola.
"""
import json
import os
import re
import threading
import time
from collections import deque

# ─── Herramientas conocidas ───────────────────────────────────────────────────
# Se comparan en minúsculas: da igual si el CLI las renombra a 'edit_file'.
_ESCRITURA = ('edit', 'write', 'multiedit', 'notebookedit', 'update', 'create',
              'str_replace', 'replace', 'apply_patch')
_LECTURA   = ('read', 'notebookread', 'view')

# Claves donde puede venir la ruta, en orden de preferencia.
_CLAVES_PATH = ('file_path', 'notebook_path', 'filePath', 'path', 'target_file')
# Claves del contenido ANTERIOR / POSTERIOR de una edición.
_CLAVES_ANTES   = ('old_string', 'old_text', 'oldText', 'oldString', 'old_str', 'old_source')
_CLAVES_DESPUES = ('new_string', 'new_text', 'newText', 'newString', 'new_str', 'new_source',
                   'content', 'file_content', 'file_text', 'text')


def _clase_herramienta(tool_name):
    """'write' | 'read' | None. Tolera None, mayúsculas y nombres compuestos."""
    if not isinstance(tool_name, str):
        return None
    t = tool_name.strip().lower()
    if not t:
        return None
    if any(k in t for k in _ESCRITURA):
        return 'write'
    if any(k in t for k in _LECTURA):
        return 'read'
    return None


def _primera_clave(d, claves):
    for k in claves:
        v = d.get(k)
        if isinstance(v, str) and v:
            return v
    return ''


def limpiar_path(p):
    """'./a/b.py' → 'a/b.py', y los separadores de Windows a `/`. No resuelve
    absolutos ni traduce entre mundos: eso lo hace `rutas.canonica`, que
    conoce la raíz del proyecto y se aplica en el borde (routers/live.py)."""
    from plotspace.core import rutas
    return rutas.a_barras(rutas.limpiar(p))


def normalizar_payload(tool_name, tool_input):
    """Payload de un hook → [{'op','path','antes','despues'}] (op: write|read).

    Defensivo por diseño: cualquier basura devuelve [] y una forma DESCONOCIDA
    de contenido igual registra la escritura (antes/despues vacíos)."""
    clase = _clase_herramienta(tool_name)
    if clase is None or not isinstance(tool_input, dict):
        return []
    path = limpiar_path(_primera_clave(tool_input, _CLAVES_PATH))
    if not path:
        return []
    if clase == 'read':
        return [{'op': 'read', 'path': path, 'antes': '', 'despues': ''}]

    edits = tool_input.get('edits')
    if isinstance(edits, list) and edits:
        ops = []
        for e in edits:
            if not isinstance(e, dict):
                continue
            ops.append({'op': 'write', 'path': path,
                        'antes':   _primera_clave(e, _CLAVES_ANTES),
                        'despues': _primera_clave(e, _CLAVES_DESPUES)})
        return ops or [{'op': 'write', 'path': path, 'antes': '', 'despues': ''}]

    return [{'op': 'write', 'path': path,
             'antes':   _primera_clave(tool_input, _CLAVES_ANTES),
             'despues': _primera_clave(tool_input, _CLAVES_DESPUES)}]


def es_sobrescritura_total(tool_name, tool_input) -> bool:
    """¿Esta operación REEMPLAZA el archivo entero? Es la única que destruye
    trabajo ajeno en silencio (probado: un Write con contexto viejo borra el
    cambio del otro agente sin un solo aviso). Un Edit por zona NO destruye:
    dos agentes editando zonas distintas del mismo archivo conviven bien."""
    if not isinstance(tool_name, str):
        return False
    t = tool_name.strip().lower()
    return ('write' in t or 'create' in t) and 'edit' not in t


# ─── Símbolos: qué DEFINE un texto (base de la colisión por funcionalidad) ────
# El caso real que motiva esto: un agente borró el nodo `bw-cfg-uso-top` y eso
# rompió el `aplicarIdioma()` de OTRO agente, que lo referenciaba. Archivos
# distintos, cero conflicto de path, y lo encontraron de casualidad.

_ID_RE    = re.compile(r'\bid\s*=\s*["\']([^"\']+)["\']')
_CLASS_RE = re.compile(r'\bclass(?:Name)?\s*=\s*["\']([^"\']+)["\']')
_DATA_RE  = re.compile(r'(data-[a-zA-Z][\w-]*)')
# Selector CSS/JS. Dos filtros, los dos aprendidos de falsos positivos reales:
#   · el '.'/'#' NO puede venir pegado a una palabra → `document.querySelector`
#     no cuenta, pero `$('.mi-clase')` sí;
#   · y NO puede estar seguido de '(' → `(x or '').strip()` es una LLAMADA A
#     MÉTODO, no una clase. Sin esto, editar código Python normal hacía que el
#     agente se auto-reclamara territorio sobre `strip`, `join` y `append`, y
#     que el detector avisara "borraste `strip`, que usa otro agente". Un aviso
#     falso es peor que ninguno: entrena a ignorar los de verdad.
_SEL_RE   = re.compile(r'(?<![\w-])[.#]([a-zA-Z][\w-]*)(?!\s*\()')
_DECL_RE  = re.compile(r'\b(?:function|def|class|const|let|var|interface|type)\s+'
                       r'([A-Za-z_$][\w$]*)')

_MIN_LARGO = 4
_HEX_RE = re.compile(r'[0-9a-fA-F]{3,8}\Z')
# Un símbolo que existe en TODOS los archivos del mundo no identifica el
# territorio de nadie. Visto en vivo: escribir una clase de test auto-reclamaba
# `__init__`, y con eso otro agente que refactorizara el `__init__` de SU clase
# quedaba bloqueado por el guard en nombre del primero.
_DUNDER_RE = re.compile(r'\A__\w+__\Z')
_UNIVERSALES = {'main', 'setup', 'teardown', 'init'}
_RUIDO = {
    'true', 'false', 'null', 'none', 'this', 'self', 'return', 'import', 'from',
    'type', 'name', 'value', 'data', 'text', 'href', 'http', 'https', 'span',
    'div', 'body', 'html', 'head', 'main', 'item', 'list', 'container', 'wrapper',
    'active', 'hidden', 'open', 'close', 'show', 'hide', 'left', 'right', 'top',
    'bottom', 'center', 'small', 'large', 'error', 'warn', 'info', 'debug',
    'test', 'tests', 'else', 'elif', 'while', 'async', 'await', 'then', 'catch',
}


def _aceptable(tok: str) -> bool:
    if len(tok) < _MIN_LARGO:
        return False
    if tok.lower() in _RUIDO or tok.lower() in _UNIVERSALES:
        return False
    if _DUNDER_RE.match(tok):       # __init__, __call__, __repr__…
        return False
    if _HEX_RE.match(tok):          # colores #ffffff y compañía
        return False
    return True


def simbolos(texto) -> set:
    """Identificadores REFERENCIABLES que aparecen en un texto: ids y clases de
    HTML, selectores CSS/JS, atributos data-*, y nombres declarados en JS/TS/
    Python. Filtra ruido (tokens cortos, palabras comunes, colores hex).

    No pretende ser un parser: es una señal barata y determinista, sin LLM."""
    if not texto or not isinstance(texto, str):
        return set()
    out = set()
    for m in _ID_RE.finditer(texto):
        out.add(m.group(1).strip())
    for m in _CLASS_RE.finditer(texto):
        out.update(m.group(1).split())
    for rx in (_DATA_RE, _SEL_RE, _DECL_RE):
        for m in rx.finditer(texto):
            out.add(m.group(1))
    return {t for t in (s.strip() for s in out) if _aceptable(t)}


def simbolos_perdidos(antes, despues) -> set:
    """Símbolos que estaban en `antes` y NO están en `despues`: lo que esta
    edición borró o renombró. Es la señal que dispara el chequeo de colisión —
    si otro agente referencia alguno, hay que avisarles a los dos AHORA."""
    return simbolos(antes) - simbolos(despues)


# ─── Colisión por FUNCIONALIDAD (no por path) ─────────────────────────────────
# El caso real: un agente borró los nodos de la cuenta falsa del Builder y eso
# rompió el `aplicarIdioma()` de OTRO, que apuntaba a `.bw-cfg-uso-top span`.
# Tareas distintas, misma superficie. Lo encontraron de casualidad, y la
# propiedad por archivo no habría ayudado (el que borró era el dueño legítimo).
#
# Regla de aviso, invertida respecto de la anterior:
#   · mismo archivo, zonas distintas   → NO avisar (está medido que conviven)
#   · símbolo que uno borra y otro usa → AVISAR, aunque sean archivos distintos

MAX_COLISIONES = 6          # tope de avisos por edición: el ruido mata la señal


def colisiones_por_simbolos(perdidos, ediciones_ajenas, tid_propio=None):
    """[{simbolo, tid, nombre, path}] — de los símbolos que ESTA edición borró,
    cuáles aparecen en texto que escribió OTRO agente.

    Una entrada por (símbolo, agente): aunque el otro lo use diez veces, se
    avisa una sola vez."""
    if not perdidos:
        return []
    vistos = set()
    out = []
    for e in ediciones_ajenas or ():
        if e.get('op') != 'write' or e.get('tid') == tid_propio:
            continue
        texto = (e.get('despues') or '') + '\n' + (e.get('antes') or '')
        if not texto.strip():
            continue
        for s in perdidos:
            clave = (s, e['tid'])
            if clave in vistos or s not in texto:
                continue
            vistos.add(clave)
            out.append({'simbolo': s, 'tid': e['tid'],
                        'nombre': e.get('nombre') or f"terminal {e['tid']}",
                        'path': e.get('path') or ''})
            if len(out) >= MAX_COLISIONES:
                return out
    return out


MAX_COLISIONES_LIBRO = 300
_colisiones: deque = deque(maxlen=MAX_COLISIONES_LIBRO)


def registrar_colision(pid, tid, nombre, path, colisiones, ts=None):
    """Deja constancia de una colisión para que el panel pueda mostrarla.
    Antes solo existía como aviso efímero al agente y como línea de log."""
    t = time.time() if ts is None else ts
    with _lock:
        for c in colisiones or ():
            _colisiones.append({'pid': pid, 'tid': tid, 'nombre': nombre or '',
                                'path': path, 'ts': t, 'simbolo': c.get('simbolo'),
                                'contra_tid': c.get('tid'),
                                'contra_nombre': c.get('nombre'),
                                'contra_path': c.get('path')})


def colisiones(pid=None, tids=None, desde_ts=None) -> list:
    """Colisiones registradas, filtrables. Copia."""
    with _lock:
        datos = list(_colisiones)
    out = []
    for c in datos:
        if pid is not None and c['pid'] != pid:
            continue
        if tids is not None and c['tid'] not in tids and c['contra_tid'] not in tids:
            continue
        if desde_ts is not None and c['ts'] < desde_ts:
            continue
        out.append(dict(c))
    return out


def texto_aviso_colision(colisiones) -> str:
    """El aviso que se le inyecta al agente EN EL MOMENTO (va por el hook, en el
    resultado de su propia herramienta). Tiene que decir qué rompió y a quién
    avisarle: un aviso que no dice qué hacer es ruido."""
    if not colisiones:
        return ''
    lineas = ['⚠ COLISIÓN DE SUPERFICIE — acabás de borrar o renombrar algo que '
              'otro agente está usando:']
    for c in colisiones:
        lineas.append(f"  · `{c['simbolo']}` lo usa {c['nombre']} en "
                      f"`{c['path']}`")
    lineas.append('Si fue a propósito, avisale por .jarvis/MAILBOX.md AHORA '
                  '(antes de que se entere rompiéndose). Si no, revertí esa '
                  'parte o adaptá su uso.')
    return '\n'.join(lineas)


# ─── Libro mayor de ediciones (estado en memoria, muere con el server) ────────
# Acotado a propósito: es telemetría viva de coordinación, no un histórico.

MAX_EDICIONES = 4000
_lock = threading.Lock()
_ediciones: deque = deque(maxlen=MAX_EDICIONES)


def registrar(pid, tid, nombre, path, op, antes='', despues='',
              sobrescritura=False, ts=None):
    """Suma una edición al libro. Devuelve el registro creado."""
    rec = {'pid': pid, 'tid': tid, 'nombre': nombre or '', 'path': path,
           'op': op, 'antes': antes or '', 'despues': despues or '',
           'sobrescritura': bool(sobrescritura),
           'ts': time.time() if ts is None else ts}
    with _lock:
        _ediciones.append(rec)
    return rec


def ediciones(pid=None, tid=None, path=None, desde_ts=None, solo_write=True):
    """Consulta del libro con filtros. Copia — el caller no muta el estado."""
    with _lock:
        datos = list(_ediciones)
    out = []
    for r in datos:
        if solo_write and r['op'] != 'write':
            continue
        if pid is not None and r['pid'] != pid:
            continue
        if tid is not None and r['tid'] != tid:
            continue
        if path is not None and r['path'] != path:
            continue
        if desde_ts is not None and r['ts'] < desde_ts:
            continue
        out.append(dict(r))
    return out


def ultimo_escritor(pid, path, excluir_tid=None, ventana_s=None):
    """Último agente (≠ excluir_tid) que escribió `path`, o None. Base de la
    guarda de sobrescritura: "vas a reescribir entero un archivo que el #1 tocó
    hace 3 minutos"."""
    ahora = time.time()
    mejor = None
    for r in ediciones(pid=pid, path=path):
        if excluir_tid is not None and r['tid'] == excluir_tid:
            continue
        if ventana_s is not None and (ahora - r['ts']) > ventana_s:
            continue
        if mejor is None or r['ts'] > mejor['ts']:
            mejor = r
    return mejor


def purgar_terminal(tid):
    """Olvida las ediciones de una terminal eliminada (patrón agent_live)."""
    with _lock:
        vivas = [r for r in _ediciones if r['tid'] != tid]
        _ediciones.clear()
        _ediciones.extend(vivas)


# ─── Canario: que esto NO se muera en silencio otra vez ───────────────────────
# El sistema anterior se rompió y nadie se enteró: los tests usaban fixtures con
# el formato viejo (verdes) mientras producción detectaba cero. Acá la señal es
# el payload REAL que llega del CLI, así que un cambio de contrato se canta en
# la primera edición.

_raros: dict = {'n': 0, 'ultimo': ''}


def formato_sospechoso(tool_name, tool_input):
    """Motivo (str) si este payload huele a contrato cambiado, o None.

    Dispara cuando la herramienta ES de escritura pero el payload no entrega lo
    que debería: sin ruta (ciegos) o sin contenido reconocible (perdemos el
    hunk). Herramientas que no tocan archivos (Bash, Grep) nunca son
    sospechosas — no serían falsos positivos, serían ruido."""
    if _clase_herramienta(tool_name) != 'write':
        return None
    if not isinstance(tool_input, dict):
        return f'payload de {tool_name} no es un objeto'
    if not _primera_clave(tool_input, _CLAVES_PATH):
        return (f'{tool_name} sin ruta reconocible '
                f'(claves recibidas: {sorted(tool_input)[:8]})')
    # Se mira la PRESENCIA de la clave, no que tenga texto: una edición que
    # borra trae `new_string: ""` de forma perfectamente legítima, y exigir
    # contenido la marcaba como formato raro (falso positivo detectado en la
    # prueba end-to-end). El canario tiene que cantar solo cuando el CONTRATO
    # cambió, nunca cuando el agente borró algo.
    def _tiene_clave(d):
        return any(k in d for k in _CLAVES_DESPUES + _CLAVES_ANTES)

    edits = tool_input.get('edits')
    if isinstance(edits, list) and edits:
        if any(isinstance(e, dict) and _tiene_clave(e) for e in edits):
            return None
    elif _tiene_clave(tool_input):
        return None
    return (f'{tool_name} sin contenido reconocible '
            f'(claves recibidas: {sorted(tool_input)[:8]})')


def contar_formato_raro(tool_name, motivo):
    """Registra una sospecha de drift del contrato (la lee `salud`)."""
    with _lock:
        _raros['n'] += 1
        _raros['ultimo'] = f'{tool_name}: {motivo}'


# Path de aviso de colisión, OBSERVABLE (2a): cada /swarm/op que emite un
# aviso_texto no vacío se cuenta acá. No es un canario automático del contrato de
# SALIDA del hook —si el CLI deja de surfacear additionalContext no es observable
# desde el server— pero hace el path DIAGNOSTICABLE en vez de invisible. Y la
# víctima ya no depende de él: se entera por la animación del Swarm (WS).
_avisos_colision: dict = {'n': 0, 'ultimo_ts': None}


def contar_aviso_colision(ts=None):
    """Suma un aviso de colisión emitido (lo lee `salud`)."""
    with _lock:
        _avisos_colision['n'] += 1
        _avisos_colision['ultimo_ts'] = time.time() if ts is None else ts


def salud() -> dict:
    """¿La provenance está viva AHORA? Lo que un humano necesita para saber si
    el enjambre está protegido o si volvió a quedar ciego."""
    with _lock:
        datos = [r for r in _ediciones if r['op'] == 'write']
        raros = dict(_raros)
        avisos = dict(_avisos_colision)
    return {
        'ops': len(datos),
        'muda': not datos,
        'ultima_op_ts': max((r['ts'] for r in datos), default=None),
        'archivos': len({r['path'] for r in datos}),
        'agentes': len({r['tid'] for r in datos}),
        'formatos_raros': raros['n'],
        'ultimo_formato_raro': raros['ultimo'],
        'avisos_colision_emitidos': avisos['n'],
        'ultimo_aviso_colision_ts': avisos['ultimo_ts'],
    }


def reset():
    """Solo para tests."""
    with _lock:
        _ediciones.clear()
        _colisiones.clear()
        _raros.update({'n': 0, 'ultimo': ''})
        _avisos_colision.update({'n': 0, 'ultimo_ts': None})


# ─── Snapshot: que el libro sobreviva al re-exec del updater ─────────────────
#
# "Actualizar ahora" reemplaza el proceso (os.execv, mismo PID): la memoria se va
# entera. Sin esto, cada update dejaba al enjambre CIEGO — los íconos de vínculo
# de todas las cards se apagaban de golpe y el overlay se quedaba sin nada que
# mostrar, aunque los agentes vinieran escribiendo el mismo archivo hacía diez
# minutos. Es la telemetría viva de la coordinación: se guarda acotada por
# ventana y por tamaño, y ni guardar ni cargar pueden romper nada (el reinicio y
# el arranque mandan sobre esto).

RUTA_SNAPSHOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'data', 'swarm-provenance.json')
# Más viejo que esto ya no arma ningún grupo (la ventana de convergencia es de
# 30 min): guardarlo sería resucitar vínculos muertos al arrancar.
VENTANA_SNAPSHOT_S = 3600
# Un Write manda el archivo ENTERO en `despues`: sin techo, 4000 ediciones son
# cientos de MB. Se conserva lo más NUEVO, que es lo que arma los grupos de hoy.
MAX_BYTES_SNAPSHOT = 8 * 1024 * 1024


def _recientes(datos, ahora, ventana_s):
    return [r for r in datos if (ahora - r.get('ts', 0)) <= ventana_s]


def _acotar(registros, tope_bytes):
    """Los más nuevos que entren en el presupuesto, en orden cronológico."""
    elegidos, usados = [], 0
    for r in reversed(registros):
        peso = len(json.dumps(r, ensure_ascii=False))
        if usados + peso > tope_bytes and elegidos:
            break
        elegidos.append(r)
        usados += peso
    elegidos.reverse()
    return elegidos


def guardar_snapshot(ruta=None, ahora=None) -> int:
    """Vuelca el libro a disco. Devuelve cuántas ediciones guardó (0 si falló).

    Best-effort SIEMPRE: lo llama `_reexec()` justo antes del execv, y un error
    acá jamás puede frenar una actualización."""
    ruta = ruta or RUTA_SNAPSHOT
    ahora = time.time() if ahora is None else ahora
    try:
        with _lock:
            eds = list(_ediciones)
            cols = list(_colisiones)
        eds = _acotar(_recientes(eds, ahora, VENTANA_SNAPSHOT_S), MAX_BYTES_SNAPSHOT)
        cols = _recientes(cols, ahora, VENTANA_SNAPSHOT_S)
        # Guardar NADA no puede borrar lo que había: un arranque sin escrituras
        # todavía, o un reinicio encadenado, dejarían el snapshot bueno en cero.
        # Es el mismo error que una vez borró el Builder entero (un estado vacío
        # tratado como estado válido).
        if not eds and not cols:
            return 0
        tmp = ruta + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump({'v': 1, 'ts': ahora, 'ediciones': eds, 'colisiones': cols},
                      f, ensure_ascii=False)
        os.replace(tmp, ruta)          # atómico: nunca se lee un archivo a medias
        return len(eds)
    except Exception as e:
        print(f'[provenance] snapshot no guardado: {e}')
        return 0


def cargar_snapshot(ruta=None, ahora=None) -> int:
    """Repuebla el libro al arrancar. Devuelve cuántas ediciones cargó.

    Falla ABIERTA (0) ante cualquier cosa rara: sin archivo, con basura o con
    otra forma. El arranque del server no se negocia por telemetría."""
    ruta = ruta or RUTA_SNAPSHOT
    ahora = time.time() if ahora is None else ahora
    try:
        with _lock:
            if _ediciones or _colisiones:
                return 0               # libro vivo: no duplicar
        with open(ruta, encoding='utf-8') as f:
            datos = json.load(f)
        if not isinstance(datos, dict):
            return 0
        eds = datos.get('ediciones')
        cols = datos.get('colisiones')
        eds = _recientes(eds, ahora, VENTANA_SNAPSHOT_S) if isinstance(eds, list) else []
        cols = _recientes(cols, ahora, VENTANA_SNAPSHOT_S) if isinstance(cols, list) else []
        eds = [r for r in eds if isinstance(r, dict) and r.get('tid') is not None]
        cols = [r for r in cols if isinstance(r, dict)]
        with _lock:
            _ediciones.extend(eds)
            _colisiones.extend(cols)
        return len(eds)
    except FileNotFoundError:
        return 0
    except Exception as e:
        print(f'[provenance] snapshot no leído ({ruta}): {e}')
        return 0
