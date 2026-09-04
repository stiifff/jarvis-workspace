"""
memoria_endurecimiento — la escalera error → regla → enforcement determinista.

El destilador (memoria_lecciones) ya convierte los motivos de fallo en reglas
de texto. Este módulo cierra el último escalón: si un motivo de fallo NUEVO
matchea una lección que ya existe, la lección 'reincide'. A las N reincidencias
la salud la marca 'candidata a guard determinista' — el camino que el proyecto
ya inventó solo (guard_propiedad.py, scan_secretos.py): una regla que se viola
igual N veces no alcanza como texto, hay que hornearla en un candado que ni el
LLM más distraído saltee.

El sistema PROPONE la promoción (queda en la salud de la memoria); convertirla
en guard es decisión del usuario. Determinista, cero API. La reincidencia se
persiste (data/memoria-endurecimiento.json) para acumular entre corridas del
janitor.
"""
import json
import os
import re

from plotspace.core.datadir import ruta_data
from plotspace.core.memoria_recall import _TOKEN_RE, _STOP

ESTADO_PATH = ruta_data('memoria-endurecimiento.json')
_UMBRAL_DEFAULT = 3          # reincidencias antes de proponer el guard
_SOLAPE_MIN = 3              # tokens significativos en común = match motivo↔lección


def _tokens_sig(texto: str) -> set:
    """Tokens significativos (sin stopwords) para el matching por solape."""
    return {t for t in _TOKEN_RE.findall((texto or '').lower()) if t not in _STOP}


def motivo_matchea(motivo: str, leccion_texto: str) -> bool:
    """Un motivo de fallo 'pega' con una lección si comparten suficientes
    tokens significativos (misma clase de problema). Simple y robusto: no
    necesita semántica fina, solo detectar que el fallo es del tema de la regla."""
    return len(_tokens_sig(motivo) & _tokens_sig(leccion_texto)) >= _SOLAPE_MIN


def contar_reincidencias(lecciones: list, motivos: list) -> dict:
    """{slug → cuántos motivos matchean esa lección}. lecciones = [{slug, texto}]."""
    cuenta = {}
    for m in motivos:
        for lec in lecciones:
            if motivo_matchea(m, lec['texto']):
                cuenta[lec['slug']] = cuenta.get(lec['slug'], 0) + 1
    return cuenta


# ─── Fuentes: lecciones del proyecto + estado persistido ─────────────────────

_FRONT_RE = re.compile(r'^---\s*\n(.*?)\n---\s*\n?', re.DOTALL)
_TAGS_RE  = re.compile(r'^tags:\s*\[([^\]]*)\]', re.MULTILINE)


def lecciones_del_proyecto(project_path: str) -> list:
    """Memorias con tag 'leccion' → [{slug, texto}] (título + cuerpo)."""
    d = os.path.join(project_path, '.jarvis', 'memory')
    out = []
    try:
        nombres = sorted(os.listdir(d))
    except OSError:
        return out
    for nombre in nombres:
        if not nombre.endswith('.md') or nombre == 'INDEX.md':
            continue
        try:
            with open(os.path.join(d, nombre), encoding='utf-8', errors='replace') as f:
                src = f.read()
        except OSError:
            continue
        m = _FRONT_RE.match(src)
        front = m.group(1) if m else ''
        mt = _TAGS_RE.search(front)
        tags = [t.strip().lower() for t in mt.group(1).split(',')] if mt else []
        if 'leccion' not in tags:
            continue
        cuerpo = src[m.end():] if m else src
        out.append({'slug': nombre[:-3], 'texto': cuerpo})
    return out


def _leer_estado(estado_path=None) -> dict:
    try:
        with open(estado_path or ESTADO_PATH, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _guardar_estado(estado: dict, estado_path=None):
    path = estado_path or ESTADO_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(estado, f)


def evaluar(project_path: str, motivos: list, umbral: int = None,
            estado_path: str = None) -> dict:
    """Acumula las reincidencias de los motivos nuevos sobre las lecciones del
    proyecto y devuelve {'reincidencias': {...}, 'candidatas': [{slug, veces}]}.
    Persiste el acumulado (se llama en cada pasada del janitor)."""
    umbral = umbral or _UMBRAL_DEFAULT
    lecciones = lecciones_del_proyecto(project_path)
    nuevas = contar_reincidencias(lecciones, motivos)
    estado = _leer_estado(estado_path)
    slugs_vivos = {l['slug'] for l in lecciones}
    # HIGH-WATER MARK: el janitor pasa la MISMA ventana de motivos cada corrida,
    # así que sumar inflaría el contador. Guardamos el máximo histórico de
    # reincidencias vistas — idempotente sobre la ventana, nunca baja.
    for slug, n in nuevas.items():
        estado[slug] = max(estado.get(slug, 0), n)
    estado = {s: v for s, v in estado.items() if s in slugs_vivos}
    _guardar_estado(estado, estado_path)
    candidatas = sorted(
        ({'slug': s, 'veces': v} for s, v in estado.items() if v >= umbral),
        key=lambda c: -c['veces'])
    return {'reincidencias': estado, 'candidatas': candidatas}


def candidatas_actuales(umbral: int = None, estado_path: str = None) -> list:
    """Candidatas a guard SIN re-evaluar (lee el estado persistido) — para la
    salud de la memoria, que no debe recalcular ni escribir."""
    umbral = umbral or _UMBRAL_DEFAULT
    estado = _leer_estado(estado_path)
    return sorted(({'slug': s, 'veces': v} for s, v in estado.items() if v >= umbral),
                  key=lambda c: -c['veces'])


# ─── Fuentes de motivos + pasada del janitor ─────────────────────────────────

def motivos_recientes(project_id: int, limite: int = 200) -> list:
    """Motivos de fallo del proyecto: TASK_BLOCKED/ERROR (task_events.motivo) +
    señales del audit trail (canary_fallo, guard_propiedad_bloqueo, firma de
    rate-limit). La materia prima de la reincidencia."""
    motivos = []
    try:
        from plotspace.core.database import get_db
        conn = get_db()
        try:
            filas = conn.execute(
                "SELECT motivo FROM task_events WHERE project_id = ? AND motivo IS NOT NULL "
                "AND motivo != '' AND event IN ('TASK_BLOCKED','TASK_ERROR') "
                "ORDER BY id DESC LIMIT ?", (project_id, limite)).fetchall()
            motivos += [f['motivo'] for f in filas]
        finally:
            conn.close()
    except Exception:
        pass
    try:
        from plotspace.core import logs
        for ev in logs.leer_recientes(limite):
            t = ev.get('evento')
            if t == 'canary_fallo':
                motivos.append(str(ev.get('detalle', '')))
            elif t == 'guard_propiedad_bloqueo':
                motivos.append('guard de propiedad bloqueó commit de archivos ajenos: '
                               + ' '.join(ev.get('archivos') or []))
            elif t in ('task_event',) and ev.get('motivo'):
                motivos.append(str(ev['motivo']))
    except Exception:
        pass
    return [m for m in motivos if m and m.strip()]


def pasada_janitor(umbral: int = None) -> dict:
    """Evalúa reincidencias en cada proyecto con memoria (llamado por el
    poller de mantenimiento). Nunca levanta."""
    resumen = {'proyectos': 0, 'candidatas': 0}
    try:
        from plotspace.core.database import get_db
        conn = get_db()
        try:
            proyectos = [(r['id'], r['ruta']) for r in
                         conn.execute('SELECT id, ruta FROM projects').fetchall()]
        finally:
            conn.close()
    except Exception:
        return resumen
    for pid, ruta in proyectos:
        if not os.path.isdir(os.path.join(ruta or '', '.jarvis', 'memory')):
            continue
        try:
            motivos = motivos_recientes(pid)
            if not motivos:
                continue
            r = evaluar(ruta, motivos, umbral=umbral)
            resumen['proyectos'] += 1
            resumen['candidatas'] += len(r['candidatas'])
        except Exception as e:
            print(f'[endurecimiento] proyecto {pid} falló: {e}')
    return resumen
