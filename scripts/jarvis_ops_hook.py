#!/usr/bin/env python3
# Hook de PROVENANCE del enjambre (PreToolUse + PostToolUse) para Claude Code.
#
# POR QUÉ
# -------
# Jarvis deducía qué archivo tocaba cada agente parseando el pane tmux en busca
# de `● Update(archivo)`. Claude Code 2.1.x dejó de imprimir eso: colapsa las
# tool-calls en un resumen que ni nombra el archivo. Medido: 4,8 MB de log de
# dos agentes → CERO operaciones detectadas, y con eso se murieron en silencio
# la propiedad de archivos, el guard de commits y las alertas de conflicto.
#
# Este hook lee el dato del CONTRATO de la herramienta (documentado y estable)
# en vez de la pantalla (superficie de presentación que cambia cada semana).
#
# DOS EVENTOS, DOS RESPONSABILIDADES
# ----------------------------------
#   PostToolUse  → POST /api/swarm/op    : registra la edición YA hecha.
#   PreToolUse   → POST /api/swarm/check : pregunta ANTES de escribir; si Jarvis
#                  contesta que no, se DENIEGA la herramienta con el motivo.
#
# DOCTRINA: best-effort absoluto. Sin JARVIS_TERMINAL_ID (claude fuera de
# Jarvis), sin server, con timeout o con cualquier excepción → NO-OP que deja
# pasar. Un hook jamás puede frenar a un agente por un problema propio: el
# server puede estar reiniciando justo cuando el agente escribe.
#
# Se instala solo (plotspace/core/hooks_cli.py, idempotente, al boot del server).
import json
import os
import sys

TIMEOUT_POST_S = 1.0     # registrar: si tarda, no vale la pena esperar
TIMEOUT_CHECK_S = 1.5    # frenar: vale esperar un poco más, pero poco
TIMEOUT_BRIEF_S = 1.5    # briefing: corre una vez por tarea, no por edición

# Corta-corriente: en WSL, conectar a un puerto cerrado NO se rechaza — se
# descarta, y el intento se come el timeout entero. Sin esto, con Jarvis caído
# CADA edición de CADA agente pagaría ~1s de nada. Medido: 2.165s por edición
# con el server abajo vs 50ms cuando el hook se saltea solo.
CAIDO_NOMBRE = ".hook-swarm-caido"
CAIDO_S = 60             # tras un fallo, no reintentar por un minuto


def _dir_datos():
    return os.environ.get("JARVIS_DATA_DIR") or os.path.join(
        os.path.expanduser("~"), "jarvis", "data")


def _corta_corriente_abierto(data_dir):
    """True si hubo un fallo hace poco → saltear sin tocar la red."""
    try:
        import time
        return (time.time() - os.path.getmtime(
            os.path.join(data_dir, CAIDO_NOMBRE))) < CAIDO_S
    except OSError:
        return False


def _marcar_caido(data_dir, caido=True):
    p = os.path.join(data_dir, CAIDO_NOMBRE)
    try:
        if caido:
            with open(p, "w") as f:
                f.write("")
        elif os.path.exists(p):
            os.unlink(p)
    except OSError:
        pass


def _token(data_dir):
    try:
        with open(os.path.join(data_dir, "jarvis_token.txt"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def _anfitriones():
    """A qué direcciones intentar, en orden.

    `127.0.0.1` primero: es el caso normal (agente y motor en la misma
    máquina) y el único que existía hasta ahora.

    El segundo caso aparece con el port a Windows: un agente corriendo DENTRO
    de una distro de WSL y el motor del lado de Windows. Ahí `127.0.0.1` es la
    distro, no el host — y sin este respaldo el hook falla en silencio en cada
    escritura, dejando al enjambre sin provenance justo en las terminales de
    perfil WSL. Con `networkingMode=mirrored` el primero ya alcanza; sin él, la
    IP del host es la que WSL deja como nameserver en /etc/resolv.conf.

    Se puede fijar a mano con JARVIS_HOST, que gana sobre todo lo demás.
    """
    fijo = (os.environ.get("JARVIS_HOST") or "").strip()
    if fijo:
        return [fijo]
    hosts = ["127.0.0.1"]
    try:
        # Solo tiene sentido buscar el host si estamos adentro de WSL.
        with open("/proc/version") as f:
            if "microsoft" not in f.read().lower():
                return hosts
        with open("/etc/resolv.conf") as f:
            for linea in f:
                if linea.startswith("nameserver"):
                    ip = linea.split()[1].strip()
                    if ip and ip not in hosts:
                        hosts.append(ip)
                    break
    except OSError:
        pass
    return hosts


def _conectar(puerto, timeout):
    """Socket al motor, probando cada anfitrión. None si ninguno responde —
    el hook es best-effort absoluto y JAMÁS frena al agente."""
    import socket
    for host in _anfitriones():
        try:
            return socket.create_connection((host, int(puerto)), timeout)
        except OSError:
            continue
    return None


def _http_crudo(puerto, ruta, token, cuerpo, timeout):
    """POST JSON por socket pelado. Devuelve el dict de respuesta.

    Por qué no `urllib.request`: importarlo cuesta 82 ms (arrastra http.client →
    todo el paquete `email`), y este hook corre DOS veces por escritura de CADA
    agente. Con socket crudo el import sale 7 ms. Medido, no estimado.

    `Connection: close` evita tener que interpretar Content-Length ni chunked:
    se lee hasta que el server cierra."""
    import socket
    body = json.dumps(cuerpo).encode()
    pedido = (
        f"POST {ruta} HTTP/1.1\r\n"
        f"Host: 127.0.0.1:{puerto}\r\n"
        f"Content-Type: application/json\r\n"
        f"Cookie: jarvis_token={token}\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"Connection: close\r\n\r\n"
    ).encode() + body

    s = _conectar(puerto, timeout)
    if s is None:
        return {}
    try:
        s.settimeout(timeout)
        s.sendall(pedido)
        trozos = []
        while True:
            c = s.recv(65536)
            if not c:
                break
            trozos.append(c)
    finally:
        s.close()
    datos = b"".join(trozos)
    corte = datos.find(b"\r\n\r\n")
    if corte < 0:
        raise ValueError("respuesta HTTP incompleta")
    estado = datos[:datos.find(b"\r\n")].split()
    if len(estado) < 2 or not estado[1].startswith(b"2"):
        raise ValueError(f"HTTP {estado[1].decode() if len(estado) > 1 else '?'}")
    return json.loads(datos[corte + 4:].decode("utf-8", errors="replace") or "{}")


def _http_get(puerto, ruta, token, timeout):
    """GET JSON por socket pelado (mismo motivo que _http_crudo: urllib cuesta
    82 ms de import y este hook corre en el camino caliente del agente)."""
    pedido = (
        f"GET {ruta} HTTP/1.1\r\n"
        f"Host: 127.0.0.1:{puerto}\r\n"
        f"Cookie: jarvis_token={token}\r\n"
        f"Connection: close\r\n\r\n"
    ).encode()
    s = _conectar(puerto, timeout)
    if s is None:
        return {}
    try:
        s.settimeout(timeout)
        s.sendall(pedido)
        trozos = []
        while True:
            c = s.recv(65536)
            if not c:
                break
            trozos.append(c)
    finally:
        s.close()
    datos = b"".join(trozos)
    corte = datos.find(b"\r\n\r\n")
    if corte < 0:
        raise ValueError("respuesta HTTP incompleta")
    estado = datos[:datos.find(b"\r\n")].split()
    if len(estado) < 2 or not estado[1].startswith(b"2"):
        raise ValueError(f"HTTP {estado[1].decode() if len(estado) > 1 else '?'}")
    return json.loads(datos[corte + 4:].decode("utf-8", errors="replace") or "{}")


def _get(ruta, timeout):
    """GET a Jarvis con el mismo corta-corriente que _post. None si está abierto."""
    data_dir = _dir_datos()
    if _corta_corriente_abierto(data_dir):
        return None
    try:
        out = _http_get(os.environ.get("JARVIS_PORT", "3000"), ruta,
                        _token(data_dir), timeout)
    except Exception:
        _marcar_caido(data_dir, True)
        raise
    _marcar_caido(data_dir, False)
    return out


def _post(ruta, cuerpo, timeout):
    """POST JSON a Jarvis. Devuelve el dict de respuesta, o None si el corta-
    corriente está abierto. Propaga la excepción si falla la llamada (el caller
    decide), pero deja marcado el fallo para no reintentar en cada edición."""
    data_dir = _dir_datos()
    if _corta_corriente_abierto(data_dir):
        return None
    try:
        out = _http_crudo(os.environ.get("JARVIS_PORT", "3000"), ruta,
                          _token(data_dir), cuerpo, timeout)
    except Exception:
        _marcar_caido(data_dir, True)
        raise
    _marcar_caido(data_dir, False)
    return out


def _contexto(texto, evento="PostToolUse"):
    """Inyecta texto en el contexto del agente. Se emite en las DOS formas
    conocidas del contrato (top-level y dentro de hookSpecificOutput): los campos
    que el CLI no conoce los ignora, y así el aviso sobrevive a un cambio de
    formato — que es exactamente lo que nos dejó ciegos la vez pasada.

    `evento` tiene que ser el que disparó el hook: con el hookEventName cruzado
    el CLI descarta el bloque y el texto muere mudo."""
    json.dump({
        "additionalContext": texto,
        "hookSpecificOutput": {"hookEventName": evento,
                               "additionalContext": texto},
    }, sys.stdout)
    sys.stdout.write("\n")


def datos_herramienta(payload):
    """(tool_name, tool_input, es_antigravity) del payload, sea cual sea el CLI.

    Claude/qwen/Gemini mandan {tool_name, tool_input}; Antigravity manda
    {toolCall: {name, args}} (protojson, camelCase). Sin traducirlo, el hook no
    vería NINGUNA edición de Antigravity."""
    if not isinstance(payload, dict):
        return None, None, False
    tc = payload.get("toolCall")
    if isinstance(tc, dict):
        args = tc.get("args")
        return tc.get("name"), args if isinstance(args, dict) else None, True
    ti = payload.get("tool_input")
    return payload.get("tool_name"), ti if isinstance(ti, dict) else None, False


def _permitir(texto=None):
    """Antigravity exige JSON válido en stdout o BLOQUEA el loop del agente. Este
    hook es un OBSERVADOR: nunca deniega, siempre deja pasar.

    Si hay algo que contarle (briefing / colisión) viaja como `additionalContext`
    al lado de la decisión: un campo que Antigravity no conozca lo ignora, y es
    el ÚNICO canal que tiene — su hook no corre en el prompt. Mismo criterio
    defensivo que `_contexto`: emitir de más nunca rompió nada; quedarse mudo sí."""
    salida = {"decision": "allow"}
    if texto:
        salida["additionalContext"] = str(texto)
        salida["hookSpecificOutput"] = {"hookEventName": "PreToolUse",
                                        "additionalContext": str(texto)}
    json.dump(salida, sys.stdout)
    sys.stdout.write("\n")


def _denegar(motivo):
    """Formato de bloqueo de PreToolUse (Claude / qwen): exit 0 + JSON con la
    decisión. (El motivo se lo lee el agente, así que tiene que decirle QUÉ
    hacer.) Antigravity nunca deniega — este hook es un observador y le contesta
    siempre `allow` (ver _permitir)."""
    json.dump({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": motivo,
    }}, sys.stdout)
    sys.stdout.write("\n")


def main():
    tid = os.environ.get("JARVIS_TERMINAL_ID")
    if not tid:
        return                      # claude fuera de Jarvis → no-op
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return
    if not isinstance(payload, dict):
        return

    tool_name, tool_input, es_agy = datos_herramienta(payload)
    cuerpo = {
        "terminal_id": tid,
        "tool_name": tool_name,
        "tool_input": tool_input,
        "cwd": payload.get("cwd"),
        "session_id": payload.get("session_id"),
    }
    evento = payload.get("hook_event_name") or ""

    if es_agy:
        # Antigravity: su PostToolUse NO trae ni tool ni ruta, así que el ÚNICO
        # momento con la ruta es PreToolUse → se REGISTRA ahí (antes de que la
        # edición ocurra: es eso o no ver nada). Y su hook corre SÍNCRONO y BLOQUEA
        # el loop del agente, así que el POST es fire-and-forget (corta-corriente +
        # timeout de siempre) y se contesta `allow` SIEMPRE, pase lo que pase.
        r = None
        try:
            r = _post("/api/swarm/op", cuerpo, TIMEOUT_POST_S)
        except Exception:
            pass
        partes = ([p for p in (r.get("aviso_texto"), r.get("briefing")) if p]
                  if isinstance(r, dict) else [])
        _permitir("\n\n".join(str(p) for p in partes) if partes else None)
        return

    # BRIEFING (UserPromptSubmit): el agente arranca una tarea nueva. Se le
    # entrega el estado del enjambre ANTES de que piense — quién más está vivo,
    # qué toca cada uno, qué territorio no puede pisar. Es el canal bueno: cero
    # turnos, cero latencia, y no depende de que el agente se acuerde de
    # preguntar (que es justamente lo que no hacía).
    if evento == "UserPromptSubmit":
        try:
            r = _get(f"/api/swarm/briefing/{tid}", TIMEOUT_BRIEF_S)
        except Exception:
            return                  # server caído → el agente arranca sin briefing
        texto = (r or {}).get("texto") if isinstance(r, dict) else None
        if texto:
            _contexto(str(texto), evento="UserPromptSubmit")
        return

    if evento == "PreToolUse":
        try:
            r = _post("/api/swarm/check", cuerpo, TIMEOUT_CHECK_S)
        except Exception:
            return                  # server caído/lento → dejar pasar
        if isinstance(r, dict) and r.get("permitir") is False and r.get("motivo"):
            _denegar(str(r["motivo"]))
        return

    # PostToolUse (y cualquier otro evento que se enganche acá): registrar.
    try:
        r = _post("/api/swarm/op", cuerpo, TIMEOUT_POST_S)
    except Exception:
        return                      # la provenance de esta edición se pierde; el
                                    # agente no se entera y sigue trabajando

    if not isinstance(r, dict):
        return

    # Lo que se le inyecta al agente, pegado al resultado de su herramienta:
    #   1. COLISIÓN DE SUPERFICIE: borró algo que otro usa. Antes se descubría
    #      de casualidad (o rompiéndose) y costaba una saga de mensajes.
    #   2. BRIEFING de piggyback: para los CLIs SIN hook de prompt (Antigravity,
    #      opencode) este es el único canal que existe. Llega un poco tarde —el
    #      agente ya arrancó— pero antes de que pueda romper algo, porque el
    #      primer movimiento de cualquier agente es tocar un archivo. Solo viaja
    #      cuando el estado CAMBIÓ (el server dedupea por firma), así que no
    #      repite lo mismo en cada edición.
    partes = [p for p in (r.get("aviso_texto"), r.get("briefing")) if p]
    if partes:
        _contexto("\n\n".join(str(p) for p in partes))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass                        # jamás propagar: exit 0 = "sin decisión"
