# plotspace/core/swarm_cli.py
"""Backend del CLI `jv` — que hablar entre agentes deje de costar una fortuna.

QUÉ ESTABA MAL (medido sobre este proyecto)
  · `.jarvis/MAILBOX.md` son 46 KB / 11,6K tokens y el protocolo le pide a cada
    agente que lo relea seguido: no hay cursor de lectura por agente.
  · 16 de 112 mensajes (14%) nunca llegaron a nadie — nombre ambiguo
    ("@Claude Code" con dos vivos) o terminal ya muerta — y se descartaron con
    un print en el stdout del server que nadie mira.
  · El 32% del tráfico era protocolo puro (permisos, reservas, acuses), y cada
    entrega despierta a un agente para un turno completo de inferencia.

QUÉ HACE ESTO
  · `inbox`: SOLO tus mensajes no leídos, y los marca entregados.
  · `enviar`: resuelve el destinatario y, si no puede, te lo dice EN EL ACTO
    con sugerencias — nunca más un mensaje al vacío.
  · `estado`: lo que necesitás saber AHORA (quién toca qué, qué te llegó),
    bajo demanda, en vez de 30K tokens de protocolo en cada sesión.

El canal sigue siendo `.jarvis/MAILBOX.md` (append-only, una línea por
mensaje): el watcher de `mailbox.py` es el que entrega y procesa permisos, y no
se toca. Acá solo se escribe bien y se lee poco.
"""
import os

from plotspace.core.database import (get_db, mensajes_pendientes_mailbox,
                                   marcar_mensajes_entregados)

MAX_MSG = 2000            # una línea del MAILBOX no es un documento
TOPE_COMUN = 600          # recorte al mostrar un mensaje normal
TOPE_HANDOFF = 4000       # un handoff va entero: a medias es peor que ninguno

_BROADCAST = ('todos', 'all', 'everyone', '*')


# ─── Resolución de destinatario ───────────────────────────────────────────────

def sugerir_destinos(terminales, para) -> list:
    """Nombres a los que SÍ se puede escribir, ordenados por parecido con lo
    que se intentó. Es lo que se devuelve cuando el destino no resuelve: el que
    manda se entera al instante en vez de escribirle al vacío."""
    objetivo = (para or '').strip().lower()
    nombres = [t['nombre'] for t in terminales or ()]

    def puntaje(n):
        b = n.lower()
        if objetivo and (b.startswith(objetivo) or objetivo.startswith(b)):
            return 0
        if objetivo and (objetivo in b or b in objetivo):
            return 1
        comunes = len(set(objetivo.split()) & set(b.split()))
        return 2 if comunes else 3

    return sorted(nombres, key=lambda n: (puntaje(n), n))


def resolver_destino_unico(terminales, para, tid_propio=None):
    """(terminal_id, sugerencias). El id solo si hay UN destinatario claro;
    si no, `sugerencias` dice a quién se le puede escribir.

    Escribirse a uno mismo no resuelve: es el error de tipeo más común y
    mandarlo dejaría un mensaje que nadie va a leer."""
    terminales = list(terminales or ())
    objetivo = (para or '').strip().lower()
    if not objetivo:
        return None, sugerir_destinos(terminales, para)
    if objetivo in _BROADCAST:
        return None, [t['nombre'] for t in terminales]

    exactos = [t for t in terminales if t['nombre'].strip().lower() == objetivo]
    candidatos = exactos or [t for t in terminales
                             if objetivo in t['nombre'].strip().lower()]
    if len(candidatos) == 1:
        t = candidatos[0]
        if tid_propio is not None and t['id'] == tid_propio:
            return None, ['(ese sos vos mismo — escribile a otro agente)']
        return t['id'], None
    if candidatos:
        # AMBIGUO: sugerir SOLO los que matchean. Listar todo el roster acá
        # sería ruido — el que escribió "@Claude Code" ya sabe cuál quiere.
        return None, [t['nombre'] for t in candidatos]
    return None, sugerir_destinos(terminales, para)


# ─── Escritura en el canal ────────────────────────────────────────────────────

def linea_mailbox(de, para, msg) -> str:
    """La línea exacta del protocolo. Una línea = un mensaje: los saltos se
    aplastan (si no, el watcher parsea el primer pedazo y pierde el resto)."""
    limpio = ' '.join((msg or '').split())[:MAX_MSG]
    return f'- @{(de or "").strip()} -> @{(para or "").strip()}: {limpio}'


def _terminales_activas(project_id):
    conn = get_db()
    try:
        return [dict(f) for f in conn.execute(
            'SELECT id, nombre FROM terminals WHERE project_id = ? AND activa = 1',
            (project_id,)).fetchall()]
    finally:
        conn.close()


def _terminales_activas_detalle(project_id):
    """id + nombre + tipo_ia de las terminales activas del proyecto — el roster
    para la PRESENCIA de `jv estado` (armar_pares). Sale de la tabla terminals,
    no de provenance: por eso ve también a los CLIs sin hook."""
    conn = get_db()
    try:
        return [dict(f) for f in conn.execute(
            'SELECT id, nombre, tipo_ia FROM terminals '
            'WHERE project_id = ? AND activa = 1', (project_id,)).fetchall()]
    finally:
        conn.close()


def _nombre_de(terminal_id):
    conn = get_db()
    try:
        f = conn.execute('SELECT nombre, project_id, '
                         '(SELECT ruta FROM projects WHERE id = project_id) AS ruta '
                         'FROM terminals WHERE id = ?', (terminal_id,)).fetchone()
        return dict(f) if f else None
    finally:
        conn.close()


async def enviar(terminal_id, para, msg, espera=False):
    """Manda un mensaje a otro agente. Devuelve la resolución del destinatario
    (o las sugerencias, si no resolvió).

    La entrega es AUTORITATIVA acá, no delegada al watcher del archivo. Motivo,
    encontrado en la prueba end-to-end: el watcher, la primera vez que ve el
    MAILBOX de un proyecto, toma su tamaño como baseline y NO procesa lo que ya
    estaba — así que un mensaje escrito en esa ventana desaparecía sin que
    nadie se enterara, que es exactamente el bug que este CLI vino a matar.

    Entonces: se escribe la línea (el archivo sigue siendo el canal legible), se
    registra el mensaje, se procesan permisos/reservas, y se adelanta el offset
    del watcher para que no lo entregue dos veces."""
    import asyncio

    yo = _nombre_de(terminal_id)
    if not yo:
        return {'ok': False, 'error': 'no encuentro tu terminal'}
    if not (msg or '').strip():
        return {'ok': False, 'error': 'mensaje vacío'}
    pid = yo['project_id']
    destino, sugerencias = resolver_destino_unico(
        _terminales_activas(pid), para, tid_propio=terminal_id)
    if destino is None:
        return {'ok': False, 'error': f'no pude resolver "@{para}"',
                'sugerencias': sugerencias or []}

    archivo = os.path.join(yo['ruta'] or '', '.jarvis', 'MAILBOX.md')
    linea = linea_mailbox(yo['nombre'], para, msg)
    limpio = ' '.join((msg or '').split())[:MAX_MSG]
    try:
        os.makedirs(os.path.dirname(archivo), exist_ok=True)
        # 'a' con una sola write: el append es atómico para líneas cortas, así
        # dos agentes escribiendo a la vez no se intercalan.
        with open(archivo, 'a', encoding='utf-8') as f:
            f.write(linea + '\n')
    except OSError as e:
        return {'ok': False, 'error': f'no pude escribir el MAILBOX: {e}'}

    # El watcher NO tiene que volver a procesar esta línea.
    try:
        from plotspace.core import mailbox
        mailbox._cargar_offsets()
        mailbox._offsets[pid] = os.path.getsize(archivo)
        mailbox._guardar_offsets()
    except Exception:
        pass          # si falla, el watcher la re-entrega: duplicado > pérdida

    # `espera=True` (jv ask) marca el mensaje como 'ask': el que pregunta queda
    # BLOQUEADO hasta 240s, así que este SÍ amerita despertar al destinatario
    # aunque haya cerrado su tarea (ver mailbox.clase_de_mensaje).
    from plotspace.core.database import registrar_mensaje_mailbox
    from plotspace.core.mailbox import clase_de_mensaje
    await asyncio.to_thread(registrar_mensaje_mailbox, pid, yo['nombre'],
                            para.strip(), limpio, destino,
                            clase_de_mensaje(limpio, espera=espera))

    # Permisos / reservas de Agents Live viajan por la misma convención.
    try:
        from plotspace.core import agent_live
        await agent_live.procesar_mensaje_mailbox(pid, yo['nombre'],
                                                  para.strip(), limpio)
    except Exception as e:
        print(f'[jv] agent_live no pudo procesar el mensaje: {e}')

    # Aviso no intrusivo al destinatario (aura de su card).
    try:
        from plotspace.core import mailbox
        from plotspace.core.events import broadcaster
        for ev in mailbox.construir_avisos([{'id': destino}], yo['nombre'], limpio):
            await broadcaster.broadcast(pid, ev)
    except Exception:
        pass

    # ¿El destinatario está VIVO? El mensaje queda escrito igual (el MAILBOX es
    # el registro), pero el que escribe tiene que enterarse EN EL ACTO: sin esto,
    # un `jv ask` se quedaba 240s bloqueado esperando la respuesta de un agente
    # cuyo CLI ya se había cerrado.
    estado_destino = None
    try:
        from plotspace.core import liveness
        # DB + fork de tmux: los dos a un thread (esto es una corrutina).
        detalle = next((t for t in await asyncio.to_thread(
            _terminales_activas_detalle, pid) if t['id'] == destino), None)
        if detalle:
            estado_destino = (await asyncio.to_thread(
                liveness.estados_ahora, [detalle], {})).get(destino)
    except Exception:
        estado_destino = None          # sin dato: se asume vivo (falla abierta)

    return {'ok': True, 'para': para, 'terminal_destino': destino, 'linea': linea,
            'destino_estado': estado_destino,
            'destino_vivo': estado_destino not in ('caido', 'sin_sesion')}


# ─── Lectura: solo lo mío, solo lo nuevo ──────────────────────────────────────

def _es_handoff(msg):
    return (msg or '').strip().upper().startswith('HANDOFF')


def formatear_inbox(mensajes) -> str:
    """Texto que lee el agente. Corto y numerado; los HANDOFF van enteros."""
    if not mensajes:
        return 'Inbox: sin mensajes nuevos.'
    out = [f'Inbox — {len(mensajes)} mensaje(s) nuevo(s):']
    for i, m in enumerate(mensajes, 1):
        tope = TOPE_HANDOFF if _es_handoff(m.get('msg')) else TOPE_COMUN
        texto = (m.get('msg') or '')[:tope]
        out.append(f"{i}. de {m.get('de', '?')}: {texto}")
    out.append('Respondé con: jv msg "<nombre>" "<tu respuesta>"')
    return '\n'.join(out)


def filtrar_de(msgs, de):
    """Solo los mensajes de UN remitente — substring case-insensitive, el
    mismo criterio con el que `jv ask` reconoce la respuesta. Sin `de` no
    filtra nada."""
    d = (de or '').strip().lower()
    if not d:
        return msgs
    return [m for m in msgs if d in (m.get('de') or '').strip().lower()]


def inbox(terminal_id, marcar=True, de=None):
    """Mis mensajes pendientes (con `de`, SOLO los de ese remitente). Marca
    entregados únicamente los que DEVUELVE: el poll de `jv ask` filtra por el
    preguntado, así un mensaje de un tercero que llegue durante la espera no
    se consume sin mostrarse (se entregaba como leído y moría mudo)."""
    yo = _nombre_de(terminal_id)
    if not yo:
        return {'mensajes': [], 'error': 'no encuentro tu terminal'}
    msgs = mensajes_pendientes_mailbox(yo['project_id'], terminal_id)
    if de:
        msgs = filtrar_de(msgs, de)
    if marcar and msgs:
        marcar_mensajes_entregados([m['id'] for m in msgs])
    return {'mensajes': msgs, 'texto': formatear_inbox(msgs)}


JV_NOMBRE = os.path.join('.jarvis', 'jv')


def asegurar_jv(project_path: str, raiz_jarvis: str) -> bool:
    """Deja un ejecutable `.jarvis/jv` en el proyecto que reenvía al CLI real.

    Así el agente corre `.jarvis/jv inbox` en CUALQUIER proyecto sin tocarle el
    PATH ni instalar nada. Se reescribe si cambió (el repo puede haberse
    movido). Best-effort: si no se puede, el protocolo sigue funcionando."""
    destino = os.path.join(project_path, JV_NOMBRE)
    real = os.path.join(raiz_jarvis, 'scripts', 'jv.py')
    contenido = f'#!/bin/sh\n# Generado por Jarvis — CLI del enjambre.\nexec python3 "{real}" "$@"\n'
    # Gemelo para las terminales de Windows: un script `sh` no corre en
    # PowerShell ni en cmd. Se escriben LOS DOS siempre (no solo en Windows)
    # porque un mismo proyecto puede tener a la vez un agente en PowerShell y
    # otro en WSL — que es justamente lo que el motor nuevo habilita. `python`
    # y no `python3`: en Windows el instalador oficial deja `python`.
    contenido_cmd = (
        '@echo off\r\n'
        f'rem Generado por Jarvis — CLI del enjambre.\r\n'
        f'python "{real}" %*\r\n'
    )
    try:
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        cambio = _escribir_si_cambio(destino, contenido, ejecutable=True)
        cambio |= _escribir_si_cambio(destino + '.cmd', contenido_cmd)
        return cambio
    except Exception:
        return False


def _escribir_si_cambio(destino: str, contenido: str, ejecutable: bool = False) -> bool:
    """Escribe solo si el contenido difiere (el repo puede haberse movido).
    Devuelve True si tocó el archivo."""
    # `newline=''` en la LECTURA también: sin eso Python traduce los \r\n del
    # .cmd a \n al leer, la comparación nunca coincide y el archivo se
    # reescribe en cada arranque — ruido en el árbol compartido de todos.
    try:
        with open(destino, encoding='utf-8', newline='') as f:
            if f.read() == contenido:
                return False
    except OSError:
        pass
    with open(destino, 'w', encoding='utf-8', newline='') as f:
        f.write(contenido)
    if ejecutable:
        try:
            os.chmod(destino, 0o755)
        except OSError:
            pass          # en Windows el bit de ejecución no existe
    return True


# ─── Liveness del pane ────────────────────────────────────────────────────────
# La lógica vive en core/liveness.py, que además distingue 'sin_sesion' y saca el
# estado de TODO el enjambre con UN solo `tmux list-panes` (antes era un
# `display-message` por par idle, en un box donde los forks de tmux ya son un
# problema medido de CPU). Acá quedan los envoltorios que usa el resto del CLI.


def resolver_estado_par(fase, tipo_ia, pane_cmd):
    """Estado de presencia de un par: 'trabajando' | 'idle' | 'caido'. Puro.
    Delega en liveness.resolver asumiendo que la sesión existe (este camino solo
    se llama con panes ya leídos)."""
    from plotspace.core import liveness
    return liveness.resolver(fase, tipo_ia, pane_cmd, True)


def _estados_pares(terminales, fases, tid_propio):
    """{tid: estado} para el roster, con el liveness compartido y cacheado."""
    from plotspace.core import liveness
    estados = liveness.estados_ahora(terminales, fases)
    return {tid: e for tid, e in estados.items() if tid != tid_propio}


def armar_pares(terminales, fases, tid_propio):
    """Roster de PRESENCIA: los otros agentes activos del proyecto (todas las
    terminales activa=1 menos la propia), con su estado de trabajo. Responde
    "¿quién más está laburando acá AHORA?" — independiente de si ya editaron
    archivos, así que incluye a un CLI sin hook de provenance (Codex, qwen…),
    que en `otros` (provenance) sería invisible.

    `terminales`: [{'id','nombre','tipo_ia'}] (terminals activa=1 del proyecto).
    `fases`: {tid: 'trabajando'|'idle'} de agent_watch (criterio card/Live). Una
    terminal que agent_watch todavía no vio queda 'idle' = presente sin actividad
    detectada. Ordenado por nombre. Puro (sin DB ni tmux)."""
    out = []
    for t in terminales or ():
        if t['id'] == tid_propio:
            continue
        out.append({'terminal_id': t['id'], 'nombre': t['nombre'],
                    'tipo_ia': t.get('tipo_ia') or 'manual',
                    'estado': fases.get(t['id'], 'idle')})
    return sorted(out, key=lambda p: (p['nombre'] or '').lower())


def estado(terminal_id):
    """Lo que este agente necesita saber AHORA: quién más está tocando qué, y
    cuántos mensajes tiene sin leer. Bajo demanda — el reemplazo de meterle
    30K tokens de protocolo a cada sesión."""
    from plotspace.core import agent_live, provenance
    yo = _nombre_de(terminal_id)
    if not yo:
        return {'error': 'no encuentro tu terminal'}
    pid = yo['project_id']
    otros = {}
    for e in provenance.ediciones(pid=pid):
        if e['tid'] == terminal_id:
            continue
        otros.setdefault(e['nombre'], set()).add(e['path'])
    mios = sorted({e['path'] for e in provenance.ediciones(pid=pid, tid=terminal_id)})
    pendientes = mensajes_pendientes_mailbox(pid, terminal_id)
    from plotspace.core import territorio
    recl = territorio.reclamos(pid)
    terminales = _terminales_activas_detalle(pid)
    estados = _estados_pares(terminales, agent_live._fases_agent_watch(), terminal_id)
    pares = armar_pares(terminales, estados, terminal_id)

    # HERENCIA: trabajo sin commitear cuyo autor ya no está. Los vivos son las
    # terminales activas que además tienen pane sano — una que figura activa pero
    # con el CLI cerrado NO cuenta como viva, que es justo el caso en el que su
    # trabajo quedaba huérfano sin que nadie se enterara.
    from plotspace.core import herencia as _herencia
    vivos = {t['id'] for t in terminales
             if estados.get(t['id'], 'idle') not in ('caido', 'sin_sesion')}
    vivos.add(terminal_id)                       # yo estoy vivo, obviamente
    lista_herencia = _herencia.de_proyecto(pid, yo.get('ruta'), vivos)

    return {
        'yo': yo['nombre'],
        'mis_archivos': mios,
        'pares': pares,
        'otros': {k: sorted(v) for k, v in otros.items()},
        'mensajes_sin_leer': len(pendientes),
        'mi_territorio': sorted(r['patron'] for r in recl if r['tid'] == terminal_id),
        'territorio_ajeno': sorted(
            {(r['nombre'], r['patron']) for r in recl if r['tid'] != terminal_id}),
        'herencia': lista_herencia,
        'salud_provenance': provenance.salud(),
    }
