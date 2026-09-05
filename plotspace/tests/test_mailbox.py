"""
Test: ruteo del mailbox entre agentes (plotspace/core/mailbox.py).

La regla (2026-06-10): el mailbox es ESTRICTAMENTE 1-a-1. No existe el
broadcast — `@todos`/`all`/`everyone` no se inyecta en ninguna terminal
(antes se mandaba a todas las terminales activas y confundía a los
agentes en pleno trabajo). Un destinatario directo se entrega solo si
resuelve sin ambigüedad: match exacto de nombre, o substring con UN
único candidato. Con 0 o varios candidatos no se inyecta nada.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plotspace.core.mailbox import (
    PROTOCOLO, construir_avisos, leer_lineas_nuevas, resolver_destinos,
    clase_de_mensaje, debe_despertar,
)


TERMINALES = [
    {'id': 1, 'nombre': 'Backend'},
    {'id': 2, 'nombre': 'Claude Code #3'},
    {'id': 3, 'nombre': 'Claude Code #4'},
]


def _ids(destinos):
    return sorted(t['id'] for t in destinos)


# ─── Qué mensaje AMERITA despertar al destinatario ───────────────────────────
# MEDIDO en este proyecto: 52 de 134 mensajes (38%) se mandaron a un agente que
# YA había cerrado su tarea, y 47 de esos 52 eran charla de coordinación. Cada
# entrega tipeada despierta al agente para un turno COMPLETO de inferencia.
# Por eso la regla se decide por el MENSAJE y no por el estado del agente: al que
# terminó igual se lo despierta si le llega algo que de verdad lo necesita.

def test_ask_despierta_porque_alguien_espera_bloqueado():
    """`jv ask` deja al que pregunta bloqueado hasta 240s: si no se despierta al
    destinatario, el ask SIEMPRE expira."""
    assert clase_de_mensaje('¿podés revisar esto?', espera=True) == 'ask'


def test_handoff_despierta_porque_le_pasan_trabajo():
    assert clase_de_mensaje('HANDOFF: te paso el contexto de X') == 'handoff'
    assert clase_de_mensaje('  handoff en minúscula') == 'handoff'


def test_coordinacion_no_despierta():
    assert clase_de_mensaje('ya terminé lo mío') == 'normal'
    assert clase_de_mensaje('OK ui.js: dale') == 'normal'
    assert clase_de_mensaje('') == 'normal'
    assert clase_de_mensaje(None) == 'normal'


def test_debe_despertar_solo_ask_y_handoff():
    assert debe_despertar({'clase': 'ask'}) is True
    assert debe_despertar({'clase': 'handoff'}) is True
    assert debe_despertar({'clase': 'normal'}) is False
    assert debe_despertar({}) is False        # histórico sin clase → no despierta
    assert debe_despertar(None) is False


def test_todos_no_entrega_a_ninguna_terminal():
    # El broadcast fue eliminado del producto: @todos no inyecta nada.
    assert resolver_destinos(TERMINALES, 'todos') == []
    assert resolver_destinos(TERMINALES, 'all') == []
    assert resolver_destinos(TERMINALES, 'everyone') == []
    assert resolver_destinos(TERMINALES, '  Todos ') == []


def test_match_exacto_entrega_solo_a_ese():
    assert _ids(resolver_destinos(TERMINALES, 'Claude Code #3')) == [2]
    assert _ids(resolver_destinos(TERMINALES, 'backend')) == [1]   # case-insensitive


def test_exacto_gana_sobre_substring():
    terminales = [
        {'id': 1, 'nombre': 'Backend'},
        {'id': 2, 'nombre': 'Backend 2'},
    ]
    # "Backend" es substring de ambos, pero hay match exacto → solo ese.
    assert _ids(resolver_destinos(terminales, 'Backend')) == [1]


def test_substring_unico_entrega():
    assert _ids(resolver_destinos(TERMINALES, 'Back')) == [1]


def test_substring_ambiguo_no_entrega_a_nadie():
    # ANTES: "@Claude Code" (o "@Claude") matcheaba TODAS las terminales
    # Claude y el mensaje se inyectaba en cada una → fan-out accidental.
    assert resolver_destinos(TERMINALES, 'Claude Code') == []
    assert resolver_destinos(TERMINALES, 'Claude') == []


def test_exacto_duplicado_no_entrega_a_nadie():
    # Homónimas vivas (la numeración vieja por conteo creó "Claude Code #4"
    # ×3 en producción; resolver_nombre_unico ya evita nuevas, pero las
    # viejas siguen activas): un match exacto MÚLTIPLE es tan ambiguo como
    # el substring — ante la duda no se inyecta nada (1-a-1 estricto).
    terminales = TERMINALES + [{'id': 4, 'nombre': 'Claude Code #4'}]
    assert resolver_destinos(terminales, 'Claude Code #4') == []


def test_sin_match_no_entrega():
    assert resolver_destinos(TERMINALES, 'Inexistente') == []


# ─── construir_avisos: aura NO intrusiva en la card del destinatario ──────────
# Reemplaza la entrega in-terminal (OFF, interrumpía): por cada destinatario
# CONCRETO se emite un WS 'mailbox_aviso' que enciende el aura de su card. Un
# broadcast/ambiguo resuelve a [] (resolver_destinos) → no enciende nada.

def test_construir_avisos_un_evento_por_destinatario():
    avisos = construir_avisos(
        [{'id': 7, 'nombre': 'Claude Code #1'}], 'Claude Code #2', '  hola che  ')
    assert avisos == [{
        'type': 'mailbox_aviso', 'terminal_id': 7,
        'de': 'Claude Code #2', 'resumen': 'hola che',
    }]


def test_construir_avisos_sin_destino_no_enciende_nada():
    # broadcast/ambiguo → resolver_destinos da [] → cero auras (no se molesta a nadie)
    assert construir_avisos([], 'Claude Code #2', 'cualquier cosa') == []


def test_construir_avisos_resumen_acotado():
    avisos = construir_avisos([{'id': 1, 'nombre': 'X'}], 'A', 'z' * 500)
    assert len(avisos[0]['resumen']) <= 140


def test_protocolo_ya_no_instruye_broadcast():
    assert '@todos' not in PROTOCOLO
    assert '1 CONCRETE recipient' in PROTOCOLO
    # La guía nueva: probá/verificá en TU terminal, sin avisar al resto.
    assert 'your terminal' in PROTOCOLO.lower()


def test_protocolo_no_promete_entrega_en_vivo():
    # La entrega in-terminal está OFF a propósito desde 2026-06-18 (interrumpía
    # a los agentes). El protocolo NO debe seguir prometiendo que Jarvis tipea
    # el mensaje en la terminal del destinatario — era mentira y el receptor,
    # confiado, no leía el archivo (permisos PERMISO/OK quedaban colgados).
    p = PROTOCOLO.lower()
    assert 'no hace falta que él mire el archivo' not in PROTOCOLO
    assert 'entrega el mensaje en vivo' not in p
    # La guía correcta: el canal es por archivo, el receptor LEE el MAILBOX.
    assert 'mailbox.md' in p
    assert ('read your messages' in p)


# ─── leer_lineas_nuevas (lectura incremental robusta del MAILBOX) ─────────────
# Los bugs que esto mata (2026-06-10): el watcher hacía f.seek(offset) en modo
# texto (UnicodeDecodeError si el offset caía a mitad de un char multibyte → el
# ciclo fallaba PARA SIEMPRE), avanzaba el offset a getsize() aunque f.read()
# hubiera leído más (re-entrega) y consumía appends a medio escribir (mensaje
# perdido).

def test_lee_solo_lineas_completas(tmp_path):
    archivo = tmp_path / 'MAILBOX.md'
    archivo.write_bytes(b'- @A -> @B: hola\n- @A -> @B: parci')
    lineas, offset = leer_lineas_nuevas(str(archivo), 0)
    assert lineas == ['- @A -> @B: hola']
    # la media línea NO se consume: queda para cuando llegue su '\n'
    assert offset == len(b'- @A -> @B: hola\n')
    with open(archivo, 'ab') as f:
        f.write('al ñoqui\n'.encode('utf-8'))
    lineas, offset2 = leer_lineas_nuevas(str(archivo), offset)
    assert lineas == ['- @A -> @B: parcial ñoqui']
    assert offset2 == archivo.stat().st_size


def test_sin_newline_no_consume_nada(tmp_path):
    archivo = tmp_path / 'MAILBOX.md'
    archivo.write_bytes(b'a medio escrib')
    lineas, offset = leer_lineas_nuevas(str(archivo), 0)
    assert lineas == [] and offset == 0


def test_offset_a_mitad_de_char_utf8_no_explota(tmp_path):
    # '📬' son 4 bytes: un offset que lo parte al medio no puede tirar
    # UnicodeDecodeError (antes mataba el ciclo del watcher en cada vuelta).
    archivo = tmp_path / 'MAILBOX.md'
    archivo.write_bytes('- @A -> @B: 📬 hola\n'.encode('utf-8'))
    lineas, offset = leer_lineas_nuevas(str(archivo), 14)  # cae dentro del emoji
    assert offset == archivo.stat().st_size
    assert len(lineas) == 1  # línea degradada con replacement chars, pero viva


def test_multibyte_completo_intacto(tmp_path):
    archivo = tmp_path / 'MAILBOX.md'
    archivo.write_bytes('- @Ñandú -> @B: acentos y 📬\n'.encode('utf-8'))
    lineas, _ = leer_lineas_nuevas(str(archivo), 0)
    assert lineas == ['- @Ñandú -> @B: acentos y 📬']


# ─── Mailbox v2: estado + entrega en momentos seguros ────────────────────────

def test_es_momento_seguro_solo_idle_puro():
    from plotspace.core.mailbox import es_momento_seguro
    assert es_momento_seguro({'fase': 'idle', 'esperando': False}) is True
    assert es_momento_seguro({'fase': 'trabajando', 'esperando': False}) is False
    # esperando = el agente le hizo una pregunta al usuario: tipearle el digest
    # se tomaría como LA RESPUESTA — jamás
    assert es_momento_seguro({'fase': 'idle', 'esperando': True}) is False
    assert es_momento_seguro({'fase': 'arrancando', 'esperando': False}) is False
    assert es_momento_seguro(None) is False


def test_no_se_le_tipea_el_digest_a_un_pane_muerto():
    """Un CLI cerrado deja el pane en bash: para agent_watch eso es 'idle puro'
    (un prompt de shell no matchea ningún patrón de pregunta), así que el digest
    se tipeaba ADENTRO del bash y el mensaje moría ahí. El estado de liveness es
    la pieza que faltaba."""
    from plotspace.core.mailbox import es_momento_seguro
    idle = {'fase': 'idle', 'esperando': False}
    assert es_momento_seguro(idle, estado_vivo='idle') is True
    assert es_momento_seguro(idle, estado_vivo='caido') is False
    assert es_momento_seguro(idle, estado_vivo='sin_sesion') is False


def test_sin_dato_de_liveness_se_entrega_igual():
    """Falla abierta: si el liveness no se pudo leer, no dejamos de entregar."""
    from plotspace.core.mailbox import es_momento_seguro
    assert es_momento_seguro({'fase': 'idle', 'esperando': False},
                             estado_vivo=None) is True


def test_armar_digest_corto_y_accionable():
    from plotspace.core.mailbox import armar_digest
    msgs = [{'de': 'Backend', 'msg': 'cambié el endpoint a /api/v2'},
            {'de': 'Frontend', 'msg': 'x' * 500}]
    d = armar_digest(msgs)
    assert '2 mensajes' in d
    assert 'de Backend: cambié el endpoint' in d
    assert 'MAILBOX.md' in d
    assert len(d) < 800, 'el digest no puede ser un choclo'
    assert armar_digest([]) == ''


def test_registro_y_pendientes_en_db():
    from plotspace.tests._harness import fresh_db
    from plotspace.core import database as db
    fresh_db()
    mid = db.registrar_mensaje_mailbox(7, 'Backend', 'Frontend', 'mensaje uno', terminal_id=8)
    db.registrar_mensaje_mailbox(7, 'Backend', 'todos', 'broadcast', terminal_id=None)
    pend = db.mensajes_pendientes_mailbox(7)
    assert len(pend) == 1 and pend[0]['msg'] == 'mensaje uno', \
        'sin destino resuelto no queda pendiente (nadie lo entregaría)'
    db.marcar_mensajes_entregados([mid])
    assert db.mensajes_pendientes_mailbox(7) == []


def test_solo_se_tipea_lo_que_amerita_despertar(monkeypatch):
    """EL comportamiento que importa: con el agente IDLE —que es exactamente el
    estado de uno que YA cerró su tarea— la charla NO se le tipea (no se lo
    despierta), pero el HANDOFF sí. Y lo que no se tipea NO se pierde: queda
    pendiente para su `jv inbox` / su próxima tarea."""
    import asyncio
    from plotspace.tests._harness import fresh_db
    from plotspace.core import database as db, mailbox, agent_watch
    import plotspace.routers.orchestrator as orch
    fresh_db()
    conn = db.get_db()
    try:
        conn.execute("INSERT INTO projects (id, nombre, ruta, fecha_creacion, ultimo_acceso) "
                     "VALUES (7, 'p', '/tmp/p', '2026-07-19', '2026-07-19')")
        conn.execute("INSERT INTO terminals (id, project_id, nombre, fecha_creacion) "
                     "VALUES (8, 7, 'Frontend', '2026-07-19')")
        conn.commit()
    finally:
        conn.close()
    db.registrar_mensaje_mailbox(7, 'A', 'Frontend', 'ya terminé lo mío', 8, clase='normal')
    db.registrar_mensaje_mailbox(7, 'A', 'Frontend', 'HANDOFF: te paso X', 8, clase='handoff')

    # idle puro = el estado en el que queda un agente que terminó
    monkeypatch.setattr(agent_watch, '_estados', {8: {'fase': 'idle', 'esperando': False}})
    tipeado = []

    async def _fake_send(tid, texto):
        tipeado.append((tid, texto))
    monkeypatch.setattr(orch, 'send_to_agent', _fake_send)

    asyncio.run(mailbox._entregar_pendientes_idle(7))

    assert len(tipeado) == 1, 'se lo despertó una sola vez'
    texto = tipeado[0][1]
    assert 'HANDOFF' in texto, 'el handoff SÍ despierta'
    assert 'ya terminé lo mío' not in texto, 'la charla NO lo despierta'
    pend = db.mensajes_pendientes_mailbox(7, 8)
    assert len(pend) == 1 and 'ya terminé' in pend[0]['msg'], \
        'lo que no despierta queda pendiente — no se pierde'


def test_bloque_pendientes_para_tarea_marca_entregado():
    from plotspace.tests._harness import fresh_db
    from plotspace.core import database as db
    from plotspace.core.mailbox import bloque_pendientes_para_tarea
    fresh_db()
    conn = db.get_db()
    try:
        conn.execute("INSERT INTO projects (id, nombre, ruta, fecha_creacion, ultimo_acceso) "
                     "VALUES (7, 'p', '/tmp/p', '2026-07-19', '2026-07-19')")
        conn.execute("INSERT INTO terminals (id, project_id, nombre, fecha_creacion) "
                     "VALUES (8, 7, 'Frontend', '2026-07-19')")
        conn.commit()
    finally:
        conn.close()
    db.registrar_mensaje_mailbox(7, 'Backend', 'Frontend', 'ojo con el endpoint', terminal_id=8)
    b = bloque_pendientes_para_tarea(8)
    assert 'ojo con el endpoint' in b and 'MAILBOX' in b
    assert bloque_pendientes_para_tarea(8) == '', 'la tarea ya los llevó: no re-entregar'


def test_offsets_persisten_roundtrip():
    import tempfile
    from plotspace.core import mailbox as mb
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, 'offsets.json')
        bak = dict(mb._offsets)
        try:
            mb._offsets.clear()
            mb._offsets.update({7: 123, 9: 456})
            mb._guardar_offsets(path)
            mb._offsets.clear()
            mb._cargar_offsets(path)
            assert mb._offsets == {7: 123, 9: 456}
        finally:
            mb._offsets.clear()
            mb._offsets.update(bak)


def test_archivar_mailbox_deja_el_vivo_corto():
    import tempfile
    from plotspace.core.mailbox import archivar_mailbox
    with tempfile.TemporaryDirectory() as d:
        mbx = os.path.join(d, 'MAILBOX.md')
        with open(mbx, 'w') as f:
            f.write('# Mailbox del workspace\n<!-- formato -->\n')
            for i in range(150):
                f.write(f'- @A -> @B: mensaje {i}\n')
        n = archivar_mailbox(mbx, max_lineas=120, conservar=40)
        assert n == 110
        vivo = open(mbx).read()
        assert vivo.startswith('# Mailbox del workspace')
        assert 'mensaje 149' in vivo and 'mensaje 0' not in vivo
        assert vivo.count('- @A') == 40
        historico = open(os.path.join(d, 'MAILBOX-archivo.md')).read()
        assert 'mensaje 0' in historico and 'mensaje 109' in historico
        # segunda pasada: ya está corto, no toca nada
        assert archivar_mailbox(mbx, max_lineas=120, conservar=40) == 0


def test_handoff_va_primero_y_entero():
    from plotspace.core.mailbox import armar_digest
    largo = 'HANDOFF: te paso el viewport — ' + 'contexto ' * 60   # >300 chars
    msgs = [{'de': 'A', 'msg': 'aviso corto'},
            {'de': 'B', 'msg': largo}]
    d = armar_digest(msgs)
    lineas = d.splitlines()
    assert 'de B' in lineas[1], 'el HANDOFF va primero'
    assert 'contexto contexto' in d and len([l for l in lineas if 'de B' in l][0]) > 320, \
        'el HANDOFF no se trunca a 300 (un handoff cortado es peor que ninguno)'


def test_protocolo_manda_a_leer_con_jv_inbox_no_el_archivo_entero():
    """El bloque viejo decía «LEÉ .jarvis/MAILBOX.md — revisalo seguido (antes
    de cada commit…)» mientras el bloque jv decía lo contrario. Las dos
    instrucciones convivían inyectadas en cada agente; el que obedecía la vieja
    pagaba ~14K tokens por lectura (el archivo llegó a 58 KB)."""
    p = PROTOCOLO.lower()
    assert 'jv inbox' in p
    assert 'whole' in p
    assert 'antes de cada commit' not in p


def test_archivar_mailbox_tambien_por_bytes(tmp_path):
    """El umbral por LÍNEAS (120) no protege nada con mensajes-ensayo: a 533
    chars promedio (medido en la DB), 109 líneas eran 58 KB. El janitor tiene
    que cortar también por PESO."""
    from plotspace.core.mailbox import archivar_mailbox
    mbx = tmp_path / 'MAILBOX.md'
    lineas = ['# Mailbox', '<!-- header -->'] + [
        f"- @A -> @B: {'x' * 700} ({i})" for i in range(60)]
    mbx.write_text('\n'.join(lineas) + '\n', encoding='utf-8')

    n = archivar_mailbox(str(mbx), max_lineas=120, conservar=40,
                         max_bytes=16384)
    assert n > 0, '60 líneas gordas (~42KB) tienen que disparar el archivado'
    vivo = mbx.read_text(encoding='utf-8')
    assert len(vivo.encode('utf-8')) <= 16384 // 2 + 300, \
        'el vivo tiene que quedar en ~la mitad del umbral'
    assert '(59)' in vivo, 'las más nuevas se conservan'
    assert '# Mailbox' in vivo, 'la cabecera no se archiva'
    archivo = (tmp_path / 'MAILBOX-archivo.md').read_text(encoding='utf-8')
    assert '(0)' in archivo, 'las viejas van al histórico'

    # Segunda pasada: ya está corto → no archiva nada.
    assert archivar_mailbox(str(mbx), max_lineas=120, conservar=40,
                            max_bytes=16384) == 0
