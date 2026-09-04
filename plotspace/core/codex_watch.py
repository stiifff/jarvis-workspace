# plotspace/core/codex_watch.py
"""Poller que tailea los rollouts de Codex → provenance del enjambre.

Codex edita con `apply_patch`, FUERA del gate de los hooks PostToolUse (que solo
cubren la herramienta shell), y `notify` es por-turno sin rutas: no hay hook útil
como el de Claude (hooks_cli) o el plugin de opencode (cli_adapters). PERO Codex
escribe cada edición en el rollout JSONL de la sesión — append-only — como un
evento `patch_apply_end` con ruta absoluta + unified_diff. Este poller lo TAILEA
y manda cada edición por el MISMO `swarm_op` que usan Claude y opencode → así un
agente Codex deja de ser fantasma (propiedad, colisiones, territorio, LIVE.md y
la animación del Swarm funcionan igual que para un Claude).

CORRELACIÓN rollout↔terminal (el desafío): Codex no deja fijar el session-id al
arrancar, y varios Codex pueden compartir CODEX_HOME (por cuenta) y hasta cwd. Se
empareja por cwd (el SessionMeta trae el cwd del proyecto) + cercanía temporal
(el rollout arranca ~cuando se creó la terminal), one-to-one. Cuando dos Codex
del MISMO proyecto son ambiguos, gana el más cercano en el tiempo — best-effort,
pero infinitamente mejor que la invisibilidad total de antes.

El parser vive aparte (codex_rollout.py). Acá va el poller (glob de homes,
correlación, tail incremental, despacho). Estado en memoria: muere con el server
(baseline en la primera vista → no reprocesa el historial). Apagable: CODEX_WATCH=off.

Caveat: `--ephemeral` de Codex apaga el rollout — los agentes de Jarvis no lo usan.
"""
import asyncio
import glob
import os

from plotspace.core import codex_rollout as cr
from plotspace.core.database import get_db

INTERVALO_S = 4
CODEX_WATCH_ENV = 'CODEX_WATCH'


# ─── Pura: correlación rollout↔terminal ──────────────────────────────────────

def asignar_rollouts(rollouts, terminales):
    """{rollout_path: tid}. Empareja por cwd; desempata por cercanía temporal
    (|rollout.ts - terminal.creada_ts|); one-to-one (cada rollout a un terminal,
    cada terminal a su sesión ACTUAL — la más cercana a su creación). Puro."""
    pares = []
    for r in rollouts or ():
        rc, rp, rts = r.get('cwd'), r.get('path'), r.get('ts') or 0
        if not rc or not rp:
            continue
        for t in terminales or ():
            if t.get('cwd') == rc:
                pares.append((abs(rts - (t.get('creada_ts') or 0)), rp, t['tid']))
    pares.sort(key=lambda x: x[0])
    asign, usados = {}, set()
    for _, rp, tid in pares:
        if rp in asign or tid in usados:
            continue
        asign[rp] = tid
        usados.add(tid)
    return asign


def ops_nuevas_de_rollout(path, offset):
    """(ops, nuevo_offset). ops = [(ruta, antes, despues, sobrescritura)] de los
    patch_apply_end nuevos desde `offset` (bytes). Lee SOLO líneas completas (hasta
    el último '\\n'); binario + errors='replace' — una línea a medias o un seek a
    mitad de un char multibyte no rompe el ciclo (misma lección que el mailbox)."""
    try:
        with open(path, 'rb') as f:
            f.seek(offset)
            data = f.read()
    except OSError:
        return [], offset
    fin = data.rfind(b'\n')
    if fin < 0:
        return [], offset
    completo = data[:fin + 1]
    ops = []
    for linea in completo.decode('utf-8', errors='replace').splitlines():
        ch = cr.patch_changes(cr.parse_linea(linea))
        if not ch:
            continue
        for o in cr.changes_a_ops(ch):
            ops.append((o['path'], o['antes'], o['despues'], o['sobrescritura']))
    return ops, offset + len(completo)


# ─── Estado del poller (en memoria, muere con el server — por diseño) ─────────

_offsets = {}       # rollout_path -> bytes ya procesados
_meta_cache = {}    # rollout_path -> {'cwd','id','ts'} (SessionMeta: se lee UNA vez)


def _homes_codex():
    """Dirs CODEX_HOME a vigilar: el default ~/.codex + el home de la cuenta codex
    ACTIVA (Jarvis lanza cada Codex con CODEX_HOME = home de la cuenta activa)."""
    homes = set()
    d = os.path.join(os.path.expanduser('~'), '.codex')
    if os.path.isdir(d):
        homes.add(d)
    try:
        from plotspace.core import cli_accounts
        activo = cli_accounts.codex_home_activo()
        if activo and os.path.isdir(activo):
            homes.add(activo)
    except Exception:
        pass
    return homes


def _meta_de(path):
    """{'cwd','id','ts'} del SessionMeta (línea 0), cacheado por path. None si aún
    no se puede leer (rollout recién creado sin su meta)."""
    if path in _meta_cache:
        return _meta_cache[path]
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            l0 = f.readline()
    except OSError:
        return None
    m = cr.session_meta(cr.parse_linea(l0))
    if not m or not m.get('cwd'):
        return None
    try:
        ts = os.path.getmtime(path)
    except OSError:
        ts = 0.0
    _meta_cache[path] = {'cwd': m.get('cwd'), 'id': m.get('id'), 'ts': ts}
    return _meta_cache[path]


def _terminales_codex():
    """[{'tid','cwd','creada_ts'}] de las terminales codex activas (DB síncrona)."""
    from datetime import datetime
    conn = get_db()
    try:
        filas = conn.execute(
            "SELECT t.id AS tid, p.ruta AS cwd, t.fecha_creacion AS creada "
            "FROM terminals t JOIN projects p ON p.id = t.project_id "
            "WHERE t.activa = 1 AND t.tipo_ia = 'codex'").fetchall()
    finally:
        conn.close()
    out = []
    for f in filas:
        try:
            ts = datetime.fromisoformat(str(f['creada'])).timestamp()
        except (ValueError, TypeError):
            ts = 0.0
        out.append({'tid': f['tid'], 'cwd': f['cwd'], 'creada_ts': ts})
    return out


def _rollouts_bajo(homes):
    """[{'path','cwd','ts'}] de los rollouts bajo esos homes con SessionMeta leíble."""
    out = []
    for h in homes:
        for path in glob.glob(os.path.join(h, 'sessions', '**', 'rollout-*.jsonl'),
                              recursive=True):
            m = _meta_de(path)
            if m:
                out.append({'path': path, 'cwd': m['cwd'], 'ts': m['ts']})
    return out


async def _procesar(path, tid):
    """Manda las ediciones nuevas de `path` por swarm_op (paridad total). Baseline
    en la PRIMERA vista: registra el tamaño actual como offset y NO reprocesa el
    historial — solo lo que se agregue de ahí en más."""
    if path not in _offsets:
        try:
            _offsets[path] = os.path.getsize(path)
        except OSError:
            _offsets[path] = 0
        return
    ops, nuevo = ops_nuevas_de_rollout(path, _offsets[path])
    _offsets[path] = nuevo
    if not ops:
        return
    from plotspace.routers import live
    for ruta, antes, despues, _sobre in ops:
        try:
            await live.swarm_op(live.HookOp(
                terminal_id=tid, tool_name='apply_patch',
                tool_input={'file_path': ruta, 'old_string': antes, 'new_string': despues}))
        except Exception as e:
            print(f'[codex-watch] op de terminal {tid} falló: {e}')


async def _ciclo():
    terminales = await asyncio.to_thread(_terminales_codex)
    if not terminales:
        return                                  # sin Codex activo: nada que tailear
    rollouts = await asyncio.to_thread(_rollouts_bajo, _homes_codex())
    asign = asignar_rollouts(rollouts, terminales)
    for path in list(_offsets):                 # olvida offsets de rollouts sin asignar
        if path not in asign:
            _offsets.pop(path, None)
    for path, tid in asign.items():
        await _procesar(path, tid)


async def poller_codex():
    """Background task: nunca crashea el servidor (patrón agent_watch/STATE.md)."""
    if os.getenv(CODEX_WATCH_ENV, 'on').strip().lower() == 'off':
        print('[codex-watch] desactivado (CODEX_WATCH=off)')
        return
    while True:
        await asyncio.sleep(INTERVALO_S)
        try:
            await _ciclo()
        except Exception as e:
            print(f'[codex-watch] error en ciclo: {e}')


def reset():
    """Solo para tests."""
    _offsets.clear()
    _meta_cache.clear()
