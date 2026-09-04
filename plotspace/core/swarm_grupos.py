# plotspace/core/swarm_grupos.py
"""Grupos del enjambre — qué terminales están trabajando sobre la MISMA superficie.

Es el cimiento del panel de visibilidad: el ícono de una card se prende cuando
esa terminal entra en un grupo, y el overlay muestra el grupo COMPLETO. Si tres
agentes convergen en un archivo, el grupo es de tres — no tres pares sueltos
(pedido explícito del usuario).

CRITERIOS, que salen de lo medido
---------------------------------
· Compartir archivo NO es un conflicto: dos ediciones en zonas distintas del
  mismo archivo conviven perfecto. El grupo es INFORMATIVO ("estos están
  trabajando juntos acá"); la alerta roja es otra cosa (una colisión real).
· Se enredan por ARCHIVO o por SÍMBOLO. Lo segundo es lo que caza el caso que
  el path nunca vio: uno define `.bw-cfg-uso-top` en el HTML y otro lo
  referencia desde el JS — archivos distintos, misma superficie.
· Solo cuentan las ESCRITURAS. Leer el mismo archivo no es trabajar juntos.
· Los temporales de cada agente (rutas fuera del proyecto) no son superficie
  compartida: se filtran (visto en producción, con scratchpads colándose).
· El id del grupo es ESTABLE entre consultas, o la UI parpadea y el overlay
  abierto pierde su grupo.
"""
import time

from plotspace.core.provenance import simbolos

# Ventana de "están trabajando juntos AHORA". Alguien que tocó ese archivo hace
# dos horas no está trabajando con vos.
VENTANA_S = 1800          # 30 min
MIN_MIEMBROS = 2


def _es_del_proyecto(path: str) -> bool:
    """Los paths ya vienen relativizados contra la ruta del proyecto
    (agent_live.relativo_al_proyecto): lo que sigue siendo absoluto vive AFUERA
    — scratchpads, /tmp, home — y no es superficie compartida."""
    return bool(path) and not path.startswith('/')


def superficie_de(ediciones) -> dict:
    """{archivos, simbolos} que toca un conjunto de ediciones."""
    archivos, simbs = set(), set()
    for e in ediciones or ():
        if e.get('op') != 'write':
            continue
        if _es_del_proyecto(e.get('path')):
            archivos.add(e['path'])
        simbs |= simbolos(e.get('despues') or '')
        simbs |= simbolos(e.get('antes') or '')
    return {'archivos': archivos, 'simbolos': simbs}


def _componentes(nodos, aristas):
    """Componentes conexas (union-find chico). Es lo que hace que tres agentes
    encadenados sean UN grupo de tres y no tres pares."""
    padre = {n: n for n in nodos}

    def buscar(x):
        while padre[x] != x:
            padre[x] = padre[padre[x]]
            x = padre[x]
        return x

    for a, b in aristas:
        ra, rb = buscar(a), buscar(b)
        if ra != rb:
            padre[ra] = rb

    grupos = {}
    for n in nodos:
        grupos.setdefault(buscar(n), set()).add(n)
    return [g for g in grupos.values() if len(g) >= MIN_MIEMBROS]


def detectar_grupos(ediciones, ahora=None, ventana_s=VENTANA_S) -> list:
    """[{id, miembros, archivos, simbolos, desde_ts, ultima_ts}] — quién está
    enredado con quién, ahora mismo. Puro: recibe el libro de ediciones."""
    ahora = time.time() if ahora is None else ahora
    recientes = [e for e in (ediciones or ())
                 if e.get('op') == 'write' and (ahora - e.get('ts', 0)) <= ventana_s]
    if not recientes:
        return []

    por_tid = {}
    nombres = {}
    for e in recientes:
        por_tid.setdefault(e['tid'], []).append(e)
        nombres[e['tid']] = e.get('nombre') or f"terminal {e['tid']}"

    superficies = {tid: superficie_de(eds) for tid, eds in por_tid.items()}

    aristas, compartido = [], {}
    tids = sorted(superficies)
    for i, a in enumerate(tids):
        for b in tids[i + 1:]:
            arch = superficies[a]['archivos'] & superficies[b]['archivos']
            simb = superficies[a]['simbolos'] & superficies[b]['simbolos']
            if arch or simb:
                aristas.append((a, b))
                compartido[(a, b)] = (arch, simb)

    salida = []
    for miembros in _componentes(tids, aristas):
        eds = [e for t in miembros for e in por_tid[t]]
        arch, simb = set(), set()
        for (a, b), (ar, si) in compartido.items():
            if a in miembros and b in miembros:
                arch |= ar
                simb |= si
        ordenados = sorted(miembros)
        salida.append({
            # Estable y sin depender del orden de llegada: la UI no parpadea y
            # un overlay abierto sigue apuntando al mismo grupo.
            'id': 'g' + '-'.join(str(t) for t in ordenados),
            'miembros': [{'tid': t, 'nombre': nombres[t]} for t in ordenados],
            'archivos': sorted(arch),
            'simbolos': sorted(simb),
            'desde_ts': min(e['ts'] for e in eds),
            'ultima_ts': max(e['ts'] for e in eds),
        })
    salida.sort(key=lambda g: -g['ultima_ts'])
    return salida


def grupo_de_terminal(grupos, terminal_id):
    """El grupo al que pertenece una terminal, o None. Lo usa el ícono de la card."""
    for g in grupos or ():
        if any(m['tid'] == terminal_id for m in g['miembros']):
            return g
    return None


# ─── Detalle de un grupo: lo que se ve al abrir el overlay ───────────────────

MAX_TIMELINE = 200


def _epoch(iso):
    """ISO de la DB → epoch. 0 si no se puede (nunca romper la línea de tiempo)."""
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(iso)).timestamp()
    except (ValueError, TypeError):
        return 0.0


def linea_de_tiempo(ediciones, mensajes, colisiones, miembros_tid,
                    tope=MAX_TIMELINE) -> list:
    """Los tres flujos entrelazados en un solo eje temporal: quién escribió qué,
    qué se dijeron y dónde chocaron. Es lo que hace posible ver el baile.

    Puro: no toca DB ni red."""
    eventos = []
    for e in ediciones or ():
        if e.get('tid') not in miembros_tid or e.get('op') != 'write':
            continue
        eventos.append({
            'tipo': 'edicion', 'ts': e.get('ts', 0), 'tid': e.get('tid'),
            'nombre': e.get('nombre') or '', 'path': e.get('path') or '',
            'sobrescritura': bool(e.get('sobrescritura')),
            'simbolos': sorted(simbolos(e.get('despues') or ''))[:6],
        })
    for m in mensajes or ():
        eventos.append({
            'tipo': 'mensaje', 'ts': _epoch(m.get('timestamp')),
            'de': m.get('de') or '', 'para': m.get('para') or '',
            'texto': (m.get('msg') or '')[:600],
        })
    for c in colisiones or ():
        eventos.append({
            'tipo': 'colision', 'ts': c.get('ts', 0), 'tid': c.get('tid'),
            'nombre': c.get('nombre') or '', 'simbolo': c.get('simbolo'),
            'path': c.get('path') or '',
            'contra_nombre': c.get('contra_nombre') or '',
            'contra_path': c.get('contra_path') or '',
        })
    eventos.sort(key=lambda e: e['ts'])
    return eventos[-tope:]


def _mensajes_entre(project_id, nombres, desde_ts):
    """Los mensajes que se cruzaron los miembros del grupo. Es lo que hoy el
    usuario NO ve en ningún lado: viven en un .md que solo leen los agentes."""
    from plotspace.core.database import get_db
    if not nombres:
        return []
    conn = get_db()
    try:
        filas = conn.execute(
            'SELECT de, para, msg, timestamp FROM mailbox_msgs '
            'WHERE project_id = ? ORDER BY id DESC LIMIT 200', (project_id,)).fetchall()
    finally:
        conn.close()
    bajos = {n.strip().lower() for n in nombres}
    out = []
    for f in filas:
        d = dict(f)
        if (d['de'] or '').strip().lower() in bajos and \
                (d['para'] or '').strip().lower() in bajos:
            if _epoch(d['timestamp']) >= desde_ts:
                out.append(d)
    return out


def detalle(project_id, grupo_id, ahora=None):
    """Todo lo que muestra el overlay de un grupo. None si el grupo ya no existe
    (los agentes se desengancharon o pasó la ventana)."""
    from plotspace.core import provenance
    ahora = time.time() if ahora is None else ahora
    eds = provenance.ediciones(pid=project_id)
    grupos = detectar_grupos(eds, ahora)
    grupo = next((g for g in grupos if g['id'] == grupo_id), None)
    if not grupo:
        return None
    tids = {m['tid'] for m in grupo['miembros']}
    nombres = [m['nombre'] for m in grupo['miembros']]
    cols = provenance.colisiones(pid=project_id, tids=tids,
                                 desde_ts=grupo['desde_ts'])
    msgs = _mensajes_entre(project_id, nombres, grupo['desde_ts'])
    return {
        **grupo,
        'agentes': resumen_por_miembro(eds, grupo['miembros']),
        'timeline': linea_de_tiempo(eds, msgs, cols, tids),
        'colisiones': cols,
        'mensajes': msgs,
    }


def resumen_por_miembro(ediciones, miembros) -> list:
    """Por agente: cuántas escrituras, en qué archivos y desde cuándo. Es el
    encabezado del overlay — quién es quién en este enredo."""
    out = []
    for m in miembros or ():
        eds = [e for e in (ediciones or ())
               if e.get('tid') == m['tid'] and e.get('op') == 'write']
        archivos = sorted({e['path'] for e in eds if _es_del_proyecto(e.get('path'))})
        out.append({
            'tid': m['tid'], 'nombre': m['nombre'],
            'escrituras': len(eds), 'archivos': archivos,
            'ultima_ts': max((e['ts'] for e in eds), default=0),
        })
    return out
