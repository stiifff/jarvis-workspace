#!/usr/bin/env python3
"""jv — el CLI del enjambre. Lo corren los AGENTES, no el usuario.

POR QUÉ EXISTE
--------------
Coordinarse salía carísimo. Medido sobre este proyecto:
  · `.jarvis/MAILBOX.md` son 46 KB / 11,6K tokens y el protocolo pedía releerlo
    seguido, porque no había cursor de lectura por agente.
  · 16 de 112 mensajes (14%) no llegaron nunca a nadie —nombre ambiguo o
    terminal muerta— y se descartaron en silencio.
  · El 32% del tráfico entre agentes era protocolo puro (permisos, reservas,
    acuses), y cada entrega despierta a un agente para un turno completo.
  · Cada sesión arrancaba pagando ~30K tokens de protocolo en el contexto.

`jv` cambia eso: se pregunta lo que hace falta, cuando hace falta.

COMANDOS
--------
  jv estado                  qué tocan los otros, qué te llegó, si el tracking anda
  jv inbox                   tus mensajes nuevos (y los marca leídos)
  jv msg "<agente>" "<texto>"  mandar un mensaje (te dice si llegó)
  jv ask "<agente>" "<texto>"  mandar y ESPERAR la respuesta (sin gastar un turno)
  jv claim "<simbolo|archivo|carpeta>"   reservar territorio ANTES de tocarlo
  jv commit -m "<mensaje>"   commitear solo lo tuyo, por hunk
  jv help

Stdlib pura. Si Jarvis no responde, cada comando lo dice y sale con código 1.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

TIMEOUT_S = 6
ESPERA_ASK_S = 240          # cuánto espera `jv ask` una respuesta
INTERVALO_ASK_S = 3


def _base():
    return f"http://127.0.0.1:{os.environ.get('JARVIS_PORT', '3000')}"


def _tid():
    tid = os.environ.get('JARVIS_TERMINAL_ID')
    if tid:
        return tid
    # Respaldo: la sesión tmux se llama jarvis_<id>.
    import re
    import subprocess
    try:
        r = subprocess.run(['tmux', 'display-message', '-p', '#{session_name}'],
                           capture_output=True, text=True, timeout=3)
        m = re.match(r'jarvis_(\d+)', (r.stdout or '').strip())
        if m:
            return m.group(1)
    except Exception:
        pass
    return None


def _pedir(ruta, cuerpo=None, timeout=TIMEOUT_S):
    req = urllib.request.Request(
        _base() + ruta,
        data=json.dumps(cuerpo).encode() if cuerpo is not None else None,
        headers={'Content-Type': 'application/json'},
        method='POST' if cuerpo is not None else 'GET')
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8', errors='replace'))


def _fallo(msg, code=1):
    print(f'jv: {msg}')
    return code


# ─── Comandos ─────────────────────────────────────────────────────────────────

def cmd_estado(tid, args):
    d = _pedir(f'/api/swarm/estado/{tid}')
    if d.get('error'):
        return _fallo(d['error'])
    print(f"Sos: {d['yo']}")
    pares = d.get('pares') or []
    otros = d.get('otros') or {}
    if pares:
        print(f'Agentes en el proyecto ({len(pares)} además de vos):')
        for p in pares:
            est = p.get('estado')
            marca = ('🟢 trabajando' if est == 'trabajando'
                     else '💀 CLI caído (se cerró)' if est == 'caido'
                     else '💀 caído (sin sesión tmux)' if est == 'sin_sesion'
                     else '⚪ idle')
            linea = f"  · {p['nombre']} ({p.get('tipo_ia', 'manual')}) — {marca}"
            archs = otros.get(p['nombre'])
            if archs:
                linea += ' · edita ' + ', '.join(archs[:6])
            print(linea)
    else:
        print('Sos el único agente activo en el proyecto.')
    if d['mis_archivos']:
        print('Tus archivos: ' + ', '.join(d['mis_archivos'][:12]))
    if d.get('mi_territorio'):
        print('Tu territorio: ' + ', '.join(d['mi_territorio'][:10]))
    if d.get('territorio_ajeno'):
        print('Territorio de otros (no lo borres ni lo renombres):')
        for nombre, patron in d['territorio_ajeno'][:8]:
            print(f'  · {patron} — {nombre}')
    # Herencia: trabajo sin commitear de agentes que ya no están. Nadie lo va a
    # venir a buscar — si tocás uno de esos archivos, commitealo vos.
    for h in (d.get('herencia') or [])[:4]:
        archivos = h.get('archivos') or []
        print(f"⚠ Herencia de {h.get('nombre', '?')} (se fue sin commitear): "
              + ', '.join(archivos[:6])
              + (f' (+{len(archivos) - 6})' if len(archivos) > 6 else ''))
    print(f"Mensajes sin leer: {d['mensajes_sin_leer']}"
          + ('  → corré: jv inbox' if d['mensajes_sin_leer'] else ''))
    s = d.get('salud_provenance') or {}
    if s.get('muda'):
        print('⚠ el tracking de ediciones no registró NADA todavía — si ya '
              'escribiste archivos, avisale al usuario (los hooks pueden estar '
              'caídos y nadie está protegido).')
    return 0


def cmd_inbox(tid, args):
    d = _pedir(f'/api/swarm/inbox/{tid}')
    if d.get('error'):
        return _fallo(d['error'])
    print(d.get('texto') or 'Inbox: sin mensajes nuevos.')
    return 0


def _enviar(tid, para, texto, espera=False):
    d = _pedir('/api/swarm/msg', {'terminal_id': int(tid), 'para': para,
                                  'msg': texto, 'espera': espera})
    if not d.get('ok'):
        print(f"jv: {d.get('error', 'no se pudo enviar')}")
        sug = d.get('sugerencias') or []
        if sug:
            print('     ¿quisiste decir?: ' + ' · '.join(sug[:6]))
        return None
    if d.get('destino_vivo') is False:
        print(f"jv: ⚠ {d['para']} tiene el CLI CERRADO — el mensaje quedó escrito "
              f"en el MAILBOX pero nadie lo va a leer. Si su trabajo te bloquea, "
              f"mirá `jv estado` (su territorio ya está libre y su trabajo sin "
              f"commitear figura como herencia).")
        return d
    print(f"jv: mensaje entregado a {d['para']}")
    return d


def cmd_msg(tid, args):
    if len(args) < 2:
        return _fallo('uso: jv msg "<agente>" "<texto>"')
    return 0 if _enviar(tid, args[0], ' '.join(args[1:])) else 1


def cmd_ask(tid, args):
    """Manda y ESPERA la respuesta. Es lo que convierte una negociación de 6
    turnos de inferencia (con dos agentes despertándose por turno) en UNA
    llamada bloqueante que devuelve el texto por stdout."""
    if len(args) < 2:
        return _fallo('uso: jv ask "<agente>" "<pregunta>"')
    para = args[0]
    # espera=True → el mensaje va como 'ask': es el único caso, junto al HANDOFF,
    # que amerita despertar al destinatario aunque ya haya cerrado su tarea (si no,
    # este ask expiraría siempre).
    d = _enviar(tid, para, ' '.join(args[1:]), espera=True)
    if not d:
        return 1
    # Preguntarle a un muerto es esperar 4 minutos a nadie. El mensaje ya quedó
    # escrito; lo que no tiene sentido es BLOQUEARSE.
    if d.get('destino_vivo') is False:
        print(f'jv: no te quedes esperando — {para} no está para contestar. Seguí.')
        return 2
    limite = time.time() + ESPERA_ASK_S
    print(f'jv: esperando respuesta de {para} (hasta {ESPERA_ASK_S}s)…')
    # `de=` (server 2026-08+): el poll devuelve y marca SOLO los mensajes del
    # preguntado. Sin el filtro, un mensaje de un TERCERO que llegara durante
    # la espera se marcaba entregado acá y no se mostraba nunca.
    import urllib.parse
    filtro = urllib.parse.quote(para)
    while time.time() < limite:
        time.sleep(INTERVALO_ASK_S)
        try:
            d = _pedir(f'/api/swarm/inbox/{tid}?de={filtro}')
        except Exception:
            continue
        for m in d.get('mensajes') or []:
            if para.strip().lower() in (m.get('de') or '').strip().lower():
                print(f"\n{m['de']} respondió:\n{m['msg']}")
                return 0
    print(f'jv: {para} no respondió en {ESPERA_ASK_S}s. Seguí con otra cosa y '
          f'revisá después con: jv inbox')
    return 2


def cmd_claim(tid, args):
    """Reclama territorio por NOMBRE: un símbolo, un archivo o una carpeta.

    Nunca por número de línea — las líneas se mueven, y en este repo eso ya
    costó una función borrada. Lo libre se concede al instante; lo ajeno se
    informa con su dueño, jamás se roba."""
    if not args:
        return _fallo('uso: jv claim "<simbolo|archivo|carpeta>" [más…]\n'
                      '     (para soltarlo: jv claim --soltar "<patrón>")')
    soltar = args[0] in ('--soltar', '-s')
    patrones = args[1:] if soltar else args
    if not patrones:
        return _fallo('decime qué soltar')
    d = _pedir('/api/swarm/claim', {'terminal_id': int(tid),
                                    'patrones': patrones, 'soltar': soltar})
    if not d.get('ok'):
        return _fallo(d.get('error', 'no se pudo'))
    if soltar:
        print('jv: soltado — ' + ', '.join(d.get('soltados') or []))
        return 0
    if d.get('otorgados'):
        print('jv: tuyo — ' + ', '.join(d['otorgados']))
    for o in d.get('ocupados') or []:
        print(f"jv: ⛔ {o['patron']} ya es de {o['de']} — pedíselo con "
              f"jv ask \"{o['de']}\" \"…\"")
    return 0 if d.get('otorgados') or not d.get('ocupados') else 2


def cmd_commit(tid, args):
    import subprocess
    aqui = os.path.dirname(os.path.abspath(__file__))
    return subprocess.run([sys.executable, os.path.join(aqui, 'commit_propio.py'),
                           *args]).returncode


def cmd_help(tid, args):
    bloque = __doc__.split('COMANDOS\n--------\n', 1)[-1]
    print('\n'.join(l[2:] if l.startswith('  ') else l
                    for l in bloque.strip().splitlines()))
    return 0


COMANDOS = {'estado': cmd_estado, 'inbox': cmd_inbox, 'msg': cmd_msg,
            'ask': cmd_ask, 'claim': cmd_claim, 'commit': cmd_commit,
            'help': cmd_help}


def main(argv):
    if not argv or argv[0] in ('-h', '--help'):
        return cmd_help(None, [])
    cmd, args = argv[0], argv[1:]
    fn = COMANDOS.get(cmd)
    if not fn:
        return _fallo(f'comando desconocido "{cmd}". Probá: jv help')
    if cmd == 'help':
        return fn(None, args)
    tid = _tid()
    if not tid:
        return _fallo('no estás en una terminal de Jarvis (no encuentro '
                      'JARVIS_TERMINAL_ID ni la sesión tmux jarvis_<id>).')
    try:
        return fn(tid, args)
    except urllib.error.HTTPError as e:
        return _fallo(f'Jarvis respondió {e.code} — ¿el server está al día?')
    except Exception as e:
        return _fallo(f'no pude hablar con Jarvis ({e}). ¿Está corriendo?')


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
