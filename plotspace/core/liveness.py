# plotspace/core/liveness.py
"""Liveness del enjambre — distinguir un agente vivo de un cadáver que figura vivo.

EL AGUJERO
----------
`terminals.activa` solo baja con la ✕ explícita del usuario (o el close del
orquestador). Si el CLI se muere ADENTRO del pane —crash, `/exit`, rate-limit—
la fila queda `activa = 1` para siempre, y el reconcile del arranque hasta le
resucita la sesión. Para el resto del enjambre ese muerto es indistinguible de
un agente idle, y eso envenena TODO lo que decide en base a "quién está":

  · le respetan el territorio (TTL de 30 min) y le piden permiso al vacío;
  · el guard de propiedad bloquea commits en nombre de un fantasma;
  · el mailbox le tipea el digest adentro de un bash;
  · y le esperan commits que ya nadie va a hacer — que es como el trabajo sin
    commitear de un muerto se queda huérfano en el árbol.

DOS MUERTES DISTINTAS
---------------------
  'caido'       la sesión tmux vive pero el pane cayó al SHELL → el CLI salió.
  'sin_sesion'  no hay sesión tmux para esa terminal activa.

COSTO
-----
Un solo `tmux list-panes -a` para TODO el enjambre (antes era un
`display-message` por terminal idle, en un box donde los forks de tmux ya son un
problema medido de CPU). El resultado se cachea: la muerte de un agente puede
tardar unos segundos en notarse y no pasa absolutamente nada.

DOCTRINA: FALLA ABIERTA. Sin dato NO se declara muerto a nadie. Enterrar a un
agente vivo es mucho peor que tardar en enterrar a uno muerto: le liberaríamos
el territorio y otro le pisaría el trabajo en curso.
"""
import subprocess
import time
from plotspace.core.terminal_backend import backend

TTL_S = 6                  # no forkear tmux más seguido que esto

# Un pane de un CLI de IA que está mostrando un SHELL = el CLI salió. Ojo: una
# terminal de tipo shell/manual ES un bash legítimamente, y marcarla caída sería
# un falso positivo permanente.
_TIPOS_CLI_IA = {'claude', 'codex', 'gemini', 'qwen', 'opencode', 'antigravity',
                 'grok'}
_SHELLS = {'bash', 'sh', 'zsh', 'fish', 'dash', 'ash'}

MUERTOS = ('caido', 'sin_sesion')


def vivo(estado) -> bool:
    """¿Este estado corresponde a un agente con el que todavía se puede contar?"""
    return estado not in MUERTOS


def resolver(fase, tipo_ia, pane_cmd, hay_sesion) -> str:
    """'trabajando' | 'idle' | 'caido' | 'sin_sesion'. Puro.

    `hay_sesion=False` solo se toma en serio cuando el snapshot de tmux se pudo
    leer (el caller pasa hay_sesion=True cuando no tiene dato — ver `estados`)."""
    if fase == 'trabajando':
        return 'trabajando'          # está produciendo: no hay nada que discutir
    if not hay_sesion:
        return 'sin_sesion'
    tipo = (tipo_ia or '').strip().lower()
    pane = (pane_cmd or '').strip().lower().lstrip('-')
    if tipo in _TIPOS_CLI_IA and pane and pane in _SHELLS:
        return 'caido'
    return 'idle'


def parsear_panes(salida) -> dict:
    """Salida de `tmux list-panes -a -F '#{session_name}\\t#{pane_current_command}'`
    → {terminal_id: comando}. Se queda con el PRIMER pane de cada sesión (el del
    CLI). Ignora todo lo que no sea una sesión `jarvis_<n>`."""
    out = {}
    for linea in (salida or '').splitlines():
        if '\t' not in linea:
            continue
        sesion, _, cmd = linea.partition('\t')
        sesion = sesion.strip()
        if not sesion.startswith('jarvis_'):
            continue
        try:
            tid = int(sesion[len('jarvis_'):])
        except ValueError:
            continue
        out.setdefault(tid, cmd.strip())
    return out


def estados(terminales, fases, panes, permitir_sin_sesion=True) -> dict:
    """{tid: estado} para una lista de terminales activas.

    `panes` = lo que devolvió `parsear_panes`, o None si el fork de tmux falló.
    Con None NADIE se declara muerto (falla abierta).

    `permitir_sin_sesion=False` desactiva SOLO el veredicto 'sin_sesion' (la
    ausencia pasa a leerse como 'idle'). Lo usa el caller durante el arranque:
    entre que el server levanta y que `reconciliar_sesiones_tmux` recrea las
    sesiones, TODAS las terminales están legítimamente sin sesión, y darlas por
    muertas ahí liberaría territorio y dejaría commitear encima de agentes que
    en dos segundos vuelven a estar vivos. El veredicto 'caido' no se toca:
    ese requiere una sesión viva con el pane en un shell, así que no tiene ese
    falso positivo."""
    sin_dato = panes is None
    panes = panes or {}
    out = {}
    for t in terminales or ():
        if not isinstance(t, dict) or t.get('id') is None:
            continue
        tid = t['id']
        hay_sesion = True if (sin_dato or not permitir_sin_sesion) else (tid in panes)
        out[tid] = resolver(fases.get(tid) if fases else None,
                            t.get('tipo_ia'), panes.get(tid, ''), hay_sesion)
    return out


# ─── Capa impura: el fork cacheado ────────────────────────────────────────────

_cache: dict = {'ts': 0.0, 'panes': None}


def panes_ahora(ahora=None, forzar=False):
    """Snapshot de los panes de tmux (cacheado TTL_S). None si no se pudo leer —
    y ese None es la señal de "no sé", que hace que nadie se declare muerto."""
    ahora = time.monotonic() if ahora is None else ahora
    if not forzar and (ahora - _cache['ts']) < TTL_S:
        return _cache['panes']
    try:
        # Por el motor: en Windows no hay tmux, y acá un None mal puesto marca
        # caído a todo el enjambre (ver `comandos_vivos`).
        crudo = backend().comandos_vivos()
        panes = None if crudo is None else parsear_panes(
            '\n'.join(f'{k}\t{v}' for k, v in crudo.items()))
    except Exception:
        panes = None
    _cache['ts'] = ahora
    _cache['panes'] = panes
    return panes


def _reconcile_terminado() -> bool:
    """¿El reconcile del arranque ya recreó las sesiones tmux? Mientras no, la
    ausencia de sesión no significa nada (ver `estados`)."""
    try:
        from plotspace.routers import terminals
        return terminals.reconcile_listo.is_set()
    except Exception:
        return False          # ante la duda, NO declarar muertos por ausencia


def estados_ahora(terminales, fases) -> dict:
    """{tid: estado} con el snapshot vivo de tmux.

    'sin_sesion' se habilita solo si (a) el reconcile del arranque terminó y
    (b) tmux reportó al menos UNA sesión de Jarvis. Sin (b), lo más probable no
    es que se hayan muerto todos los agentes a la vez sino que tmux se reinició
    o todavía no levantó — y ahí no hay que enterrar a nadie."""
    panes = panes_ahora()
    return estados(terminales, fases, panes,
                   permitir_sin_sesion=bool(panes) and _reconcile_terminado())


def reset():
    """Solo para tests."""
    _cache['ts'] = 0.0
    _cache['panes'] = None
