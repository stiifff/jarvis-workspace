# plotspace/core/codex_rollout.py
"""Parser del rollout JSONL de Codex — provenance de un CLI que NO tiene hook útil.

POR QUÉ EXISTE
--------------
Codex edita con la herramienta `apply_patch`, que NO pasa por el gate de los
hooks `PostToolUse` (esos cubren solo la herramienta shell). Y `notify` es
por-turno, sin rutas. Así que la provenance de Codex no puede venir por hook como
la de Claude (core/hooks_cli.py) o la de opencode (plugin). PERO Codex escribe
CADA edición en el rollout de la sesión —`$CODEX_HOME/sessions/YYYY/MM/DD/
rollout-<ISO>-<uuid>.jsonl`, append-only— como un evento `patch_apply_end` con la
ruta ABSOLUTA y el `unified_diff`. La vía robusta es TAILEAR ese archivo.

Este módulo es solo el PARSER (puro, sin red/DB/tmux): el poller que tailea y
correlaciona rollout↔terminal vive en core/codex_watch.py. Formato verificado
contra rollouts reales en disco (codex-cli 0.144.0):

  línea 0  → {"type":"session_meta","payload":{"id":<uuid>,"cwd":<proyecto>,...}}
  edición  → {"type":"event_msg","payload":{"type":"patch_apply_end","success":true,
              "changes":{<ruta_abs>:{"type":"add|update|delete","unified_diff":...}}}}

Caveat operativo: el flag `--ephemeral` de Codex DESACTIVA el rollout — los
agentes Codex de Jarvis no deben correr con él (Jarvis los lanza sin ese flag).
"""
import json


def parse_linea(linea):
    """Una línea del rollout JSONL → dict, o None si no parsea / no es objeto."""
    try:
        o = json.loads(linea)
    except Exception:
        return None
    return o if isinstance(o, dict) else None


def session_meta(o):
    """Si `o` es el `session_meta` (línea 0), devuelve {id, cwd}; si no, None.
    `id` es el uuid de la sesión (== el del nombre del rollout) y `cwd` el
    proyecto — la base de la correlación rollout↔terminal."""
    if not isinstance(o, dict) or o.get('type') != 'session_meta':
        return None
    p = o.get('payload')
    if not isinstance(p, dict):
        return None
    return {'id': p.get('id'), 'cwd': p.get('cwd')}


def patch_changes(o):
    """Si `o` es un `patch_apply_end` EXITOSO, devuelve su dict `changes`
    ({ruta_abs: {type, unified_diff}}); si no (otra línea, o una edición que
    falló → no cambió nada), None."""
    if not isinstance(o, dict):
        return None
    p = o.get('payload')
    if not isinstance(p, dict) or p.get('type') != 'patch_apply_end':
        return None
    if p.get('success') is False:
        return None
    ch = p.get('changes')
    return ch if isinstance(ch, dict) else None


def diff_antes_despues(unified_diff):
    """(antes, despues) de un `unified_diff`: el lado viejo (contexto + líneas
    borradas) y el nuevo (contexto + líneas agregadas), sin el prefijo. Es lo que
    necesita la detección de símbolos (`simbolos_perdidos(antes, despues)`): un
    símbolo que estaba y se fue aparece solo en las líneas '-' → en antes y no en
    despues. Las cabeceras de hunk (`@@`, `---`, `+++`) se descartan."""
    antes, despues = [], []
    for l in (unified_diff or '').splitlines():
        if l.startswith('@@') or l.startswith('---') or l.startswith('+++'):
            continue
        if l.startswith('-'):
            antes.append(l[1:])
        elif l.startswith('+'):
            despues.append(l[1:])
        else:
            c = l[1:] if l.startswith(' ') else l      # contexto (o línea vacía)
            antes.append(c)
            despues.append(c)
    return '\n'.join(antes), '\n'.join(despues)


def changes_a_ops(changes):
    """El `changes` de un `patch_apply_end` → [{op, path, antes, despues,
    sobrescritura}], la forma que consume agent_live.registrar_op_externa.
      add    → archivo nuevo (todo el contenido va a despues, sobrescritura=True)
      update → edición por zona (antes/despues del diff)
      delete → borrado (todo el contenido va a antes → sus símbolos se pierden)."""
    ops = []
    for path, info in (changes or {}).items():
        if not isinstance(info, dict) or not path:
            continue
        antes, despues = diff_antes_despues(info.get('unified_diff'))
        ops.append({'op': 'write', 'path': path, 'antes': antes, 'despues': despues,
                    'sobrescritura': info.get('type') == 'add'})
    return ops
