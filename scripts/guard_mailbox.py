#!/usr/bin/env python3
"""
Aviso de mailbox en el pre-commit — SOLO advierte, JAMÁS bloquea.

El momento del commit es donde un mensaje no leído duele: si otro agente te
avisó "cambié la interfaz que usás" y no lo viste, tu commit nace roto. El
server mantiene `.jarvis/mailbox-pendientes.json` (por terminal destino); este
script identifica al agente por su sesión tmux (mismo mecanismo que
guard_propiedad) y le imprime sus pendientes — con énfasis si un mensaje
menciona un archivo que está por commitear. Exit SIEMPRE 0 (es un aviso).
Stdlib pura.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guard_propiedad as gp


def avisos(msgs: list, staged: list) -> list:
    """Líneas de aviso para los mensajes pendientes. Un mensaje que menciona
    el basename de un archivo staged va primero y marcado."""
    urgentes, normales = [], []
    basenames = {os.path.basename(s) for s in staged}
    for m in msgs:
        texto = m.get('msg', '')
        de = m.get('de', '?')
        toca = sorted(b for b in basenames if b and b in texto)
        if toca:
            urgentes.append(f"📬⚠ de {de} — MENCIONA {', '.join(toca)} (staged): {texto[:200]}")
        else:
            normales.append(f"📬 de {de}: {texto[:160]}")
    return urgentes + normales


def main():
    try:
        tid = gp.detectar_terminal_id()
        if tid is None:
            return 0                      # el usuario en su shell: silencio
        raiz = (gp._git('rev-parse', '--show-toplevel') or '').strip()
        if not raiz:
            return 0
        path = os.path.join(raiz, '.jarvis', 'mailbox-pendientes.json')
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        msgs = data.get(str(tid)) or []
        if not msgs:
            return 0
        lineas = avisos(msgs, gp._staged())
        print(f"— Tenés {len(msgs)} mensaje(s) sin leer en .jarvis/MAILBOX.md —")
        for l in lineas[:6]:
            print('  ' + l)
        print("  (aviso, no bloquea: leelos antes de seguir)")
    except Exception:
        pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
