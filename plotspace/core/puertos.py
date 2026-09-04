# JARVIS — Protocolo de puertos para agentes.
# Regla del workspace inyectada en el CLAUDE.md de cada proyecto (mismo
# patrón de markers idempotente que mailbox/memoria): el puerto 3000 es
# de Jarvis Workspace y NINGÚN agente puede levantar nada ahí; antes de
# levantar cualquier servidor hay que mirar qué puertos ya están ocupados.

import os
import re
import signal
import subprocess
from plotspace import protocolos

# Puerto de Jarvis Workspace: jamás se mata (rompería el dashboard que orquesta).
PUERTO_JARVIS = 3000

PROTOCOLO_MARKER_START = '<!-- JARVIS_PUERTOS_START -->'
PROTOCOLO_MARKER_END   = '<!-- JARVIS_PUERTOS_END -->'

# El TEXTO vive en `plotspace/protocolos/puertos.md` — ver ese paquete.
PROTOCOLO = protocolos.leer('puertos')


def asegurar_protocolo_puertos(project_path: str):
    """Inyecta/actualiza el protocolo de puertos en el CLAUDE.md del
    proyecto (mismo patrón de markers que skills/memoria/mailbox).
    Idempotente: re-genera el bloque entre markers en cada llamada."""
    claude_md = os.path.join(project_path, 'CLAUDE.md')
    try:
        contenido = ''
        if os.path.exists(claude_md):
            with open(claude_md, encoding='utf-8') as f:
                contenido = f.read()
        if PROTOCOLO_MARKER_START in contenido:
            inicio = contenido.index(PROTOCOLO_MARKER_START)
            fin    = contenido.index(PROTOCOLO_MARKER_END) + len(PROTOCOLO_MARKER_END)
            nuevo  = contenido[:inicio] + PROTOCOLO + contenido[fin:]
        else:
            sep   = '' if (not contenido or contenido.endswith('\n\n')) else ('\n' if contenido.endswith('\n') else '\n\n')
            nuevo = contenido + sep + PROTOCOLO + '\n'
        if nuevo != contenido:
            with open(claude_md, 'w', encoding='utf-8') as f:
                f.write(nuevo)
            print(f'[puertos] Protocolo inyectado en {claude_md}')
    except Exception as e:
        print(f'[puertos] No pude inyectar el protocolo: {e}')


# ─── Matar el server de un puerto (lo usa el ✕ del pill de preview) ───────────
#
# El ✕ del pill "● preview · :PUERTO" CIERRA el server de ese puerto (pedido del
# usuario 2026-06-18). Guard duro: NUNCA el 3000 (Jarvis) ni el propio PID.

def parse_pids_puerto(salida_ss: str, port) -> set:
    """PIDs que ESCUCHAN en `port`, parseados de la salida de `ss -tlnp`. Puro
    (testeable sin red). Usa word-boundary para que :5050 no matchee :50500."""
    try:
        port = int(port)
    except (TypeError, ValueError):
        return set()
    pat = re.compile(r':%d\b' % port)
    pids = set()
    for linea in (salida_ss or '').splitlines():
        if not pat.search(linea):
            continue
        pids.update(int(m) for m in re.findall(r'pid=(\d+)', linea))
    return pids


def pids_en_puerto(port) -> set:
    """PIDs escuchando en `port`.

    Vía psutil (multiplataforma: el mismo código sirve en Linux, macOS y
    Windows, donde `ss` directamente no existe). `ss -tlnp` queda de respaldo
    para el caso de que psutil no esté instalado o el kernel no deje leer las
    conexiones — no vale la pena romper el ✕ del preview por eso."""
    try:
        port = int(port)
    except (TypeError, ValueError):
        return set()
    try:
        import psutil
        pids = set()
        for c in psutil.net_connections(kind='inet'):
            if c.status == psutil.CONN_LISTEN and c.laddr and c.laddr.port == port and c.pid:
                pids.add(c.pid)
        return pids
    except Exception:
        pass
    try:
        r = subprocess.run(['ss', '-tlnp'], capture_output=True, text=True, timeout=4)
        return parse_pids_puerto(r.stdout, port)
    except Exception:
        return set()


def matar_puerto(port) -> dict:
    """Termina (SIGTERM) el/los proceso(s) que escuchan en `port`.
    NUNCA mata el 3000 (Jarvis) ni el propio proceso. Devuelve
    {'ok': bool, 'pids': [...], 'motivo': str}."""
    try:
        port = int(port)
    except (TypeError, ValueError):
        return {'ok': False, 'pids': [], 'motivo': 'puerto inválido'}
    if port == PUERTO_JARVIS:
        return {'ok': False, 'pids': [], 'motivo': 'es el puerto de Jarvis (3000), no se mata'}
    pids = pids_en_puerto(port)
    if not pids:
        return {'ok': False, 'pids': [], 'motivo': 'no hay ningún proceso escuchando ahí'}
    muertos = []
    yo = os.getpid()
    for pid in pids:
        if pid == yo:
            continue   # jamás el propio uvicorn de Jarvis
        try:
            os.kill(pid, signal.SIGTERM)
            muertos.append(pid)
        except Exception:
            pass
    return {'ok': bool(muertos), 'pids': muertos,
            'motivo': '' if muertos else 'no pude terminar el proceso'}
