#!/usr/bin/env python3
"""
Candado de PROPIEDAD entre agentes (pedido del usuario, 2026-06-16).

La regla del CLAUDE.md «commiteá SOLO tus archivos» es disciplina blanda: un
agente puede no leerla, ser otro CLI (Codex/Gemini no leen CLAUDE.md) o, como
todo modelo, desviarse cada tanto. Este es el enforcement DURO, gemelo del
escáner de secretos:

  - El hook .githooks/pre-commit corre este script ANTES de cada commit.
  - El script identifica al agente que commitea por su sesión tmux
    (`jarvis_<terminal_id>`) y lee `.jarvis/LIVE.md`.
  - Si entre lo staged hay un archivo cuyo 🔒 dueño es OTRO agente (y no hay un
    permiso «→ OK» de ese dueño hacia mí sobre ese archivo) → BLOQUEA el commit.

Falla ABIERTO a propósito: sin tmux (lo commitea el usuario en su shell), sin
LIVE.md, o ante cualquier error, PERMITE. Un bug en el guard jamás debe brickear
los commits de todos los agentes; lo peor que pasa es volver al estado anterior
(la disciplina blanda). El escape para falsos positivos legítimos:
`git commit --no-verify`. Stdlib pura (como scan_secretos.py).
"""
import os
import re
import subprocess
import sys


# ── Parseo de LIVE.md (formato de plotspace/core/agent_live.py:generar_live_md) ──
# Encabezado de agente:  «## <nombre> (<tipo>, terminal <id>) — <estado>»
_RE_AGENTE = re.compile(r'^##\s+(.+?)\s+\([^)]*terminal\s+(\d+)\)')
# Línea de archivo:      «- `<path>` — write ×N (hace Xm)[ 🔒 dueño]»
_RE_PATH = re.compile(r'^-\s+`([^`]+)`')
# Línea de permiso:      «- <emoji> <pide> pidió PERMISO sobre `<archivo>` ... [→ OK/NO]»
_RE_PERMISO = re.compile(r'^-\s+\S+\s+(.+?)\s+pidió PERMISO sobre `([^`]+)`')
# Línea de reserva:      «- 🔖 `<path>` — <nombre> (hace Xm)»
_RE_RESERVA = re.compile(r'^-\s+🔖\s+`([^`]+)`\s+—\s+(.+?)\s+\(hace')


def parsear_reservas(texto):
    """[(nombre, path)] de la sección «## Reservas» del LIVE.md — el lease
    "voy a tocar X" del mailbox v2. Solo aparecen las vigentes (agent_live
    poda por TTL), así que acá no hay que calcular tiempos."""
    reservas = []
    en_reservas = False
    for linea in (texto or '').splitlines():
        if linea.startswith('## '):
            en_reservas = linea.startswith('## Reservas')
            continue
        if en_reservas:
            m = _RE_RESERVA.match(linea)
            if m:
                reservas.append((m.group(2).strip(), m.group(1).strip()))
    return reservas


def parsear_live(texto):
    """(agentes, permisos).
      agentes  = [{'tid': int, 'nombre': str, 'owned': [path, ...],
                   'muerto': bool}]   (owned = solo los 🔒)
      permisos = [(pide_nombre, archivo, estado)]  estado ∈ {ok, no, pendiente}

    `muerto` sale del 💀 del encabezado (agent_live._EMOJI_ESTADO): un agente
    cuyo CLI se cerró o cuya sesión tmux ya no existe. Un LIVE.md viejo sin esa
    marca deja a todos vivos — el comportamiento de antes."""
    agentes, permisos = [], []
    actual = None
    en_permisos = False
    for linea in (texto or '').splitlines():
        m = _RE_AGENTE.match(linea)
        if m:
            actual = {'nombre': m.group(1).strip(), 'tid': int(m.group(2)),
                      'owned': [], 'muerto': '💀' in linea}
            agentes.append(actual)
            en_permisos = False
            continue
        if linea.startswith('## '):                 # otra sección (p. ej. Permisos)
            en_permisos = linea.startswith('## Permisos')
            actual = None
            continue
        if en_permisos:
            mp = _RE_PERMISO.match(linea)
            if mp:
                if '→ OK' in linea:
                    estado = 'ok'
                elif '→ NO' in linea:
                    estado = 'no'
                else:
                    estado = 'pendiente'
                permisos.append((mp.group(1).strip(), mp.group(2).strip(), estado))
            continue
        if actual is not None and '🔒' in linea:
            mpath = _RE_PATH.match(linea)
            if mpath:
                actual['owned'].append(mpath.group(1))
    return agentes, permisos


def _quitar_prefijo_rel(p):
    return p[2:] if p.startswith('./') else p


def _match_archivo(a, b):
    """Espejo de agent_live._match_archivo: el dueño suele responder con el
    basename, así que 'frontend/shared/ui.js' matchea 'ui.js'."""
    a, b = _quitar_prefijo_rel(a), _quitar_prefijo_rel(b)
    return a == b or a.endswith('/' + b) or b.endswith('/' + a)


def _clave(p):
    r"""Cómo se comparan dos rutas para decidir PROPIEDAD.

    En Windows el sistema de archivos no distingue mayúsculas: `Src\Index.js`
    y `src/index.js` son EL MISMO archivo. Comparándolos como strings crudos,
    el mismo archivo termina con dos dueños y el candado no ve la colisión.
    En Linux son archivos distintos y unificarlos sería el bug opuesto — por
    eso la regla sigue al sistema, no al gusto. Gemelo de
    `plotspace/core/rutas.clave_propiedad` (acá no se importa: este script corre
    como hook de git, sin el paquete del backend en el path).
    """
    p = (p or '').replace('\\', '/')
    return p.lower() if os.name == 'nt' else p


def violaciones(staged, mi_tid, agentes, permisos, reservas=None):
    """Archivos staged cuyo dueño es OTRO agente — o con RESERVA vigente
    ajena — y para los que NO tengo un permiso ok.
    → [{'path', 'dueno_tid', 'dueno_nombre'}] (dueno_tid None si es reserva)."""
    dueno = {}                       # clave(path) -> (tid, nombre)
    mi_nombre = None
    for a in agentes:
        if a['tid'] == mi_tid:
            mi_nombre = a['nombre']
        # Un agente MUERTO no defiende nada: su CLI se cerró y los commits que
        # todos esperaban de él no van a llegar nunca. Dejarlo bloquear era
        # convertir su muerte en un candado permanente sobre archivos vivos.
        if a.get('muerto'):
            continue
        for p in a['owned']:
            dueno[_clave(p)] = (a['tid'], a['nombre'])
    mis_oks = [arch for (pide, arch, est) in permisos
               if est == 'ok' and mi_nombre is not None and pide == mi_nombre]
    out = []
    for f in staged:
        d = dueno.get(_clave(f))
        if d is None:
            # ¿reserva vigente de OTRO? ("voy a tocar X" del mailbox v2)
            r = next(((nom, path) for nom, path in (reservas or [])
                      if _match_archivo(path, f)), None)
            if r and (mi_nombre is None
                      or r[0].strip().lower() != mi_nombre.strip().lower()):
                d = (None, f'{r[0]} (reserva)')
        if not d or d[0] == mi_tid:
            continue
        if any(_match_archivo(arch, f) for arch in mis_oks):
            continue                 # el dueño me dio permiso sobre este archivo
        out.append({'path': f, 'dueno_tid': d[0], 'dueno_nombre': d[1]})
    return out


def filtrar_guard_ok(viol, ok_env):
    """Bypass SCOPED: GUARD_OK="ruta1,ruta2" exime SOLO esos archivos (con
    constancia). Reemplaza al --no-verify total, que además apagaba el escáner
    de secretos. Devuelve (violaciones_vigentes, eximidas)."""
    if not ok_env:
        return viol, []
    eximidas = [v for v in viol
                if any(_match_archivo(e, v['path']) for e in ok_env)]
    return [v for v in viol if v not in eximidas], eximidas


def registrar_bloqueo(raiz, mi_tid, viol):
    """Deja el bloqueo en data/jarvis.log (mismo formato JSON-lines que
    plotspace/core/logs.py) para que la señal de fricción no se evapore con el
    output del commit. Best-effort y stdlib pura: JAMÁS rompe el hook."""
    try:
        import json
        from datetime import datetime
        data_dir = os.environ.get('JARVIS_DATA_DIR', '').strip() or os.path.join(raiz, 'data')
        os.makedirs(data_dir, exist_ok=True)
        rec = {
            'ts': datetime.now().isoformat(timespec='seconds'),
            'nivel': 'warn',
            'evento': 'guard_propiedad_bloqueo',
            'terminal_id': mi_tid,
            'archivos': [v['path'] for v in viol],
            'duenos': sorted({v['dueno_nombre'] for v in viol}),
        }
        with open(os.path.join(data_dir, 'jarvis.log'), 'a', encoding='utf-8') as f:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    except Exception:
        pass


# ── Wiring con el entorno (git + tmux) ───────────────────────────────────────

def detectar_terminal_id():
    """El terminal_id del agente que commitea. None si no corre dentro de una
    terminal de Jarvis (p. ej. el usuario commiteando desde su propio shell).

    PRIMERO la variable de entorno, que Jarvis inyecta al crear la terminal y
    funciona con CUALQUIER motor. El nombre de sesión tmux queda de respaldo
    para las terminales creadas antes de que la variable existiera: cuando el
    motor sea ConPTY (Windows) no habrá sesión tmux que consultar, y este guard
    —que es el candado de propiedad del enjambre— no puede quedarse ciego.
    Mismo orden que `scripts/jv.py`."""
    tid = (os.environ.get('JARVIS_TERMINAL_ID') or '').strip()
    if tid.isdigit():
        return int(tid)
    try:
        r = subprocess.run(['tmux', 'display-message', '-p', '#{session_name}'],
                           capture_output=True, text=True, timeout=3)
        if r.returncode == 0:
            m = re.match(r'jarvis_(\d+)', r.stdout.strip())
            if m:
                return int(m.group(1))
    except Exception:
        pass
    return None


def _git(*args):
    try:
        r = subprocess.run(['git', *args], capture_output=True, text=True, timeout=10)
        return r.stdout if r.returncode == 0 else None
    except Exception:
        return None


def _staged():
    out = _git('diff', '--cached', '--name-only', '--diff-filter=ACMR') or ''
    return [l.strip() for l in out.splitlines() if l.strip()]


def main():
    try:
        mi_tid = detectar_terminal_id()
        if mi_tid is None:
            return 0                 # no es un agente identificable → permitir
        raiz = (_git('rev-parse', '--show-toplevel') or '').strip() or os.getcwd()
        try:
            with open(os.path.join(raiz, '.jarvis', 'LIVE.md'), encoding='utf-8') as f:
                texto = f.read()
        except OSError:
            return 0                 # sin LIVE.md → nada que proteger
        agentes, permisos = parsear_live(texto)
        viol = violaciones(_staged(), mi_tid, agentes, permisos,
                           reservas=parsear_reservas(texto))
        ok_env = [p.strip() for p in os.environ.get('GUARD_OK', '').split(',') if p.strip()]
        viol, eximidas = filtrar_guard_ok(viol, ok_env)
        for v in eximidas:
            print(f"[guard_propiedad] {v['path']} eximido por GUARD_OK "
                  f"(dueño: {v['dueno_nombre']}) — constancia")
        if not viol:
            return 0
        registrar_bloqueo(raiz, mi_tid, viol)
        print('✖ BLOQUEADO: estás por commitear archivos de OTRO agente (según .jarvis/LIVE.md):')
        for v in viol:
            term = f"terminal {v['dueno_tid']}" if v['dueno_tid'] is not None else 'reserva vigente'
            print(f"   • {v['path']} — 🔒 dueño: {v['dueno_nombre']} ({term})")
        print('')
        print('Commiteá SOLO tus archivos: `git add <tus rutas>` (NO `git add -A` / `git commit -am`).')
        print('Si el dueño te dio permiso y aun así se bloquea, eximí SOLO ese archivo:')
        print('  GUARD_OK="ruta/del/archivo.py" git commit -m "..."   (NO uses --no-verify:')
        print('  apaga también el escáner de secretos)')
        return 1
    except Exception as e:
        # Falla abierto: el guard nunca debe brickear los commits por un bug suyo.
        print(f'[guard_propiedad] aviso: chequeo omitido por error interno ({e})', file=sys.stderr)
        return 0


if __name__ == '__main__':
    sys.exit(main())
