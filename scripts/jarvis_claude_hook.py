#!/usr/bin/env python3
# SessionStart hook de Claude Code para Jarvis.
#
# claude rota su transcript (nuevo <uuid>.jsonl) cada vez que la conversación se
# compacta o se continúa. Si Jarvis guardó el uuid INICIAL, al reanudar con
# --resume trae contexto viejo/parcial. Este hook, que claude dispara en CADA
# arranque (startup/resume/clear), le avisa a Jarvis el session-id VIVO para que
# terminals.session_uuid apunte siempre al transcript actual — así al reabrir la
# app la terminal vuelve con TODA la conversación.
#
# Claude pasa un JSON por stdin: {session_id, transcript_path, cwd, source, ...}.
# El hook solo actúa si corre dentro de una terminal de Jarvis (JARVIS_TERMINAL_ID
# en el env, que Jarvis setea en la sesión tmux). Best-effort ABSOLUTO: cualquier
# error se traga en silencio — un hook nunca debe romper el arranque de claude.
import json
import os
import sys


def main() -> None:
    tid = os.environ.get("JARVIS_TERMINAL_ID")
    if not tid:
        return  # claude normal fuera de Jarvis → no-op
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return
    session_id = (payload or {}).get("session_id")
    if not session_id:
        return

    puerto = os.environ.get("JARVIS_PORT", "3000")

    try:
        import urllib.request
        req = urllib.request.Request(
            f"http://127.0.0.1:{puerto}/api/terminals/{tid}/session-uuid",
            data=json.dumps({"session_uuid": session_id}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=2).read()
    except Exception:
        pass  # el motor puede estar reiniciando; el próximo arranque reintenta


if __name__ == "__main__":
    main()
