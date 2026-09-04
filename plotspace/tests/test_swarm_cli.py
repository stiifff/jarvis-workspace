# plotspace/tests/test_swarm_cli.py
"""Backend del CLI `jv` — hablar entre agentes sin pagar el precio de hoy.

LO QUE ARREGLA (medido sobre este mismo proyecto)
  · 46 KB de MAILBOX.md que cada agente relee entero porque no hay cursor de
    lectura: `jv inbox` devuelve SOLO lo tuyo no leído.
  · 16 de 112 mensajes (14%) que nunca se entregaron a nadie — nombre ambiguo
    ("@Claude Code" con varios vivos) o terminal ya muerta — y se descartaron
    en silencio: ahora el que manda se entera EN EL ACTO y con sugerencias.
  · 32% del tráfico entre agentes era puro protocolo de coordinación, cada
    mensaje despertando a un agente para un turno completo.
"""
import pytest

from plotspace.core.swarm_cli import (
    sugerir_destinos, resolver_destino_unico, formatear_inbox, linea_mailbox,
    armar_pares, resolver_estado_par,
)

TERMINALES = [
    {'id': 396, 'nombre': 'Claude Code #1'},
    {'id': 397, 'nombre': 'Claude Code #2'},
    {'id': 400, 'nombre': 'Backend'},
]


# ─── Resolución de destinatario: nunca descartar en silencio ─────────────────

def test_nombre_exacto_resuelve():
    assert resolver_destino_unico(TERMINALES, 'Claude Code #2') == (397, None)


def test_nombre_exacto_no_distingue_mayusculas():
    assert resolver_destino_unico(TERMINALES, 'backend')[0] == 400


def test_prefijo_unico_resuelve():
    assert resolver_destino_unico(TERMINALES, 'Back')[0] == 400


def test_ambiguo_no_resuelve_pero_sugiere():
    """El caso que perdía 7 mensajes: '@Claude Code' matchea dos terminales."""
    tid, sug = resolver_destino_unico(TERMINALES, 'Claude Code')
    assert tid is None
    assert set(sug) == {'Claude Code #1', 'Claude Code #2'}


def test_inexistente_sugiere_los_vivos():
    tid, sug = resolver_destino_unico(TERMINALES, 'Frontend')
    assert tid is None
    assert 'Backend' in sug          # devuelve a quién SÍ se le puede escribir


def test_sugerencias_priorizan_lo_parecido():
    sug = sugerir_destinos(TERMINALES, 'claude code #3')
    assert sug[0].startswith('Claude Code')


def test_destino_vacio_no_resuelve():
    assert resolver_destino_unico(TERMINALES, '')[0] is None
    assert resolver_destino_unico(TERMINALES, None)[0] is None


def test_broadcast_no_resuelve_pero_lista_a_todos():
    """'todos' nunca se entregó y nunca se va a entregar (interrumpiría a todo
    el mundo), pero ahora al menos se dice a quién se le puede escribir."""
    tid, sug = resolver_destino_unico(TERMINALES, 'todos')
    assert tid is None
    assert len(sug) == 3


def test_no_se_puede_escribir_a_uno_mismo():
    tid, sug = resolver_destino_unico(TERMINALES, 'Claude Code #2', tid_propio=397)
    assert tid is None
    assert 'vos mismo' in ' '.join(sug).lower() or sug


# ─── Línea del MAILBOX ────────────────────────────────────────────────────────

def test_linea_mailbox_formato_exacto():
    assert linea_mailbox('Backend', 'Claude Code #1', 'el endpoint cambió') == (
        '- @Backend -> @Claude Code #1: el endpoint cambió')


def test_linea_mailbox_aplasta_saltos():
    """Una línea = un mensaje: un salto de línea partiría el mensaje en dos y
    el watcher solo parsearía el primer pedazo."""
    linea = linea_mailbox('A', 'B', 'primera\nsegunda\n\ntercera')
    assert linea.count('\n') == 0
    assert 'primera' in linea and 'tercera' in linea


def test_linea_mailbox_recorta_lo_gigante():
    linea = linea_mailbox('A', 'B', 'x' * 5000)
    assert len(linea) < 2100


# ─── Inbox: solo lo mío, no leído ─────────────────────────────────────────────

def test_inbox_vacio_es_explicito():
    assert 'sin mensajes' in formatear_inbox([]).lower()


def test_inbox_muestra_de_quien_y_que():
    txt = formatear_inbox([
        {'de': 'Claude Code #1', 'msg': 'PERMISO a.js — toco la zona X',
         'timestamp': '2026-07-22T18:00:00'}])
    assert 'Claude Code #1' in txt
    assert 'PERMISO a.js' in txt


def test_inbox_numera_para_poder_responder():
    txt = formatear_inbox([
        {'de': 'A', 'msg': 'uno', 'timestamp': ''},
        {'de': 'B', 'msg': 'dos', 'timestamp': ''}])
    assert '1.' in txt and '2.' in txt


def test_inbox_no_trunca_un_handoff():
    """Un handoff a medias es peor que ninguno (misma regla que el digest)."""
    largo = 'HANDOFF ' + ('contexto importante ' * 100)
    txt = formatear_inbox([{'de': 'A', 'msg': largo, 'timestamp': ''}])
    assert txt.count('contexto importante') > 50


def test_inbox_recorta_un_mensaje_comun_largo():
    txt = formatear_inbox([{'de': 'A', 'msg': 'z' * 3000, 'timestamp': ''}])
    assert len(txt) < 2000


# ─── Roster de pares: PRESENCIA, no "quién editó" ────────────────────────────
# El campo `otros` de estado() lista a quien ya escribió archivos (provenance).
# `armar_pares` responde otra pregunta: ¿quién MÁS está activo en el proyecto
# AHORA?, aunque todavía no haya tocado nada (o sea un CLI sin hook, como Codex).

PARES_TERMINALES = [
    {'id': 10, 'nombre': 'Frontend', 'tipo_ia': 'claude'},
    {'id': 11, 'nombre': 'Backend', 'tipo_ia': 'codex'},
    {'id': 12, 'nombre': 'Docs', 'tipo_ia': None},
]


def test_pares_lista_los_otros_activos_no_a_mi():
    pares = armar_pares(PARES_TERMINALES, {}, tid_propio=10)
    assert {p['terminal_id'] for p in pares} == {11, 12}   # yo (10) no soy "otro"


def test_pares_reflejan_el_estado_de_agent_watch():
    pares = armar_pares(PARES_TERMINALES, {11: 'trabajando'}, tid_propio=10)
    por_id = {p['terminal_id']: p for p in pares}
    assert por_id[11]['estado'] == 'trabajando'
    assert por_id[12]['estado'] == 'idle'   # agent_watch no la vio → presente, sin actividad


def test_pares_incluye_al_que_no_edito_nada():
    """El corazón del fix: un par aparece por EXISTIR (activa=1), no por haber
    editado. Un Codex que trabaja sin hook de provenance igual se ve presente."""
    pares = armar_pares([{'id': 11, 'nombre': 'Backend', 'tipo_ia': 'codex'}],
                        {11: 'trabajando'}, tid_propio=10)
    assert len(pares) == 1 and pares[0]['nombre'] == 'Backend'


def test_pares_tipo_ia_default_manual():
    pares = armar_pares([{'id': 12, 'nombre': 'Docs', 'tipo_ia': None}], {}, tid_propio=99)
    assert pares[0]['tipo_ia'] == 'manual'


def test_pares_ordenados_por_nombre():
    nombres = [p['nombre'] for p in armar_pares(PARES_TERMINALES, {}, tid_propio=99)]
    assert nombres == sorted(nombres, key=str.lower)


def test_estado_suma_el_roster_de_pares(monkeypatch):
    """estado() incluye `pares` (presencia): los otros agentes activos con su
    estado, tomados del ROSTER de la DB (no de provenance) + la fase de
    agent_watch. Así un par que todavía no editó nada igual aparece."""
    from plotspace.core import swarm_cli, provenance, territorio, agent_live
    provenance.reset(); territorio.reset()
    monkeypatch.setattr(swarm_cli, '_nombre_de',
                        lambda tid: {'nombre': 'Frontend', 'project_id': 7, 'ruta': '/x'})
    monkeypatch.setattr(swarm_cli, '_terminales_activas_detalle',
                        lambda pid: [{'id': 10, 'nombre': 'Frontend', 'tipo_ia': 'claude'},
                                     {'id': 11, 'nombre': 'Backend', 'tipo_ia': 'codex'}],
                        raising=False)
    monkeypatch.setattr(agent_live, '_fases_agent_watch', lambda: {11: 'trabajando'})
    monkeypatch.setattr(swarm_cli, 'mensajes_pendientes_mailbox', lambda pid, tid: [])
    d = swarm_cli.estado(10)
    assert [p['nombre'] for p in d['pares']] == ['Backend']   # yo (10) me excluyo
    assert d['pares'][0]['estado'] == 'trabajando'
    assert d['pares'][0]['tipo_ia'] == 'codex'


# ─── Liveness: un CLI que murió y cayó al shell no es un par "presente" ───────
# tmux muestra 'node'/'python' mientras la CLI corre (aun idle, esperando input)
# y cae a 'bash'/'zsh' cuando la CLI sale/crashea. Esa es la señal de "caído".

def test_estado_par_trabajando_gana_a_todo():
    """Si el pane cambia (trabajando), el CLI está vivo aunque momentáneamente
    su comando de foreground sea un shell (la CLI corriendo un `bash -c`)."""
    assert resolver_estado_par('trabajando', 'claude', 'bash') == 'trabajando'


def test_estado_par_cli_ia_en_shell_idle_es_caido():
    assert resolver_estado_par('idle', 'claude', 'bash') == 'caido'
    assert resolver_estado_par('idle', 'codex', '-zsh') == 'caido'   # login shell


def test_estado_par_cli_ia_vivo_es_idle():
    """claude idle sigue siendo el proceso node en foreground: no está caído."""
    assert resolver_estado_par('idle', 'claude', 'node') == 'idle'


def test_estado_par_shell_manual_no_es_caido():
    """Una terminal manual/shell ES un shell a propósito — nunca 'caído'."""
    assert resolver_estado_par('idle', 'manual', 'bash') == 'idle'
    assert resolver_estado_par('idle', 'shell', 'bash') == 'idle'


def test_estado_par_sin_pane_cmd_no_marca_caido():
    """Falla abierto: sin dato de tmux no se penaliza (no inventamos un caído)."""
    assert resolver_estado_par('idle', 'claude', '') == 'idle'


def test_estado_marca_caido_al_cli_que_murio(monkeypatch):
    """Integración: un par cuyo CLI de IA cayó al shell figura 'caido', no idle."""
    from plotspace.core import swarm_cli, provenance, territorio, agent_live
    provenance.reset(); territorio.reset()
    monkeypatch.setattr(swarm_cli, '_nombre_de',
                        lambda tid: {'nombre': 'Frontend', 'project_id': 7, 'ruta': '/x'})
    monkeypatch.setattr(swarm_cli, '_terminales_activas_detalle',
                        lambda pid: [{'id': 10, 'nombre': 'Frontend', 'tipo_ia': 'claude'},
                                     {'id': 11, 'nombre': 'Backend', 'tipo_ia': 'codex'}])
    monkeypatch.setattr(agent_live, '_fases_agent_watch', lambda: {})   # nadie trabajando
    monkeypatch.setattr(swarm_cli, 'mensajes_pendientes_mailbox', lambda pid, tid: [])
    from plotspace.core import liveness
    # Un solo snapshot de tmux para todo el enjambre: los dos panes en bash.
    monkeypatch.setattr(liveness, 'panes_ahora', lambda *a, **k: {10: 'bash', 11: 'bash'})
    d = swarm_cli.estado(10)
    assert d['pares'][0]['nombre'] == 'Backend'
    assert d['pares'][0]['estado'] == 'caido'


def test_enviar_avisa_si_el_destinatario_tiene_el_cli_cerrado(monkeypatch, tmp_path):
    """Sin esto, `jv ask` se bloqueaba 240s esperando a alguien que ya no está."""
    import asyncio
    from plotspace.core import swarm_cli, liveness
    monkeypatch.setattr(swarm_cli, '_nombre_de',
                        lambda tid: {'nombre': 'Frontend', 'project_id': 7,
                                     'ruta': str(tmp_path)})
    monkeypatch.setattr(swarm_cli, '_terminales_activas',
                        lambda pid: [{'id': 11, 'nombre': 'Backend'}])
    monkeypatch.setattr(swarm_cli, '_terminales_activas_detalle',
                        lambda pid: [{'id': 11, 'nombre': 'Backend', 'tipo_ia': 'claude'}])
    monkeypatch.setattr(liveness, 'panes_ahora', lambda *a, **k: {11: 'bash'})
    r = asyncio.run(swarm_cli.enviar(10, 'Backend', 'hola'))
    assert r['ok'] is True                    # el mensaje QUEDA escrito
    assert r['destino_vivo'] is False         # pero avisa que nadie lo va a leer


def test_enviar_a_un_vivo_no_avisa_nada(monkeypatch, tmp_path):
    import asyncio
    from plotspace.core import swarm_cli, liveness
    monkeypatch.setattr(swarm_cli, '_nombre_de',
                        lambda tid: {'nombre': 'Frontend', 'project_id': 7,
                                     'ruta': str(tmp_path)})
    monkeypatch.setattr(swarm_cli, '_terminales_activas',
                        lambda pid: [{'id': 11, 'nombre': 'Backend'}])
    monkeypatch.setattr(swarm_cli, '_terminales_activas_detalle',
                        lambda pid: [{'id': 11, 'nombre': 'Backend', 'tipo_ia': 'claude'}])
    monkeypatch.setattr(liveness, 'panes_ahora', lambda *a, **k: {11: 'node'})
    assert asyncio.run(swarm_cli.enviar(10, 'Backend', 'hola'))['destino_vivo'] is True


def test_estado_declara_la_herencia_del_que_ya_no_esta(monkeypatch):
    """Un par caído con trabajo sucio a su nombre no se calla: se declara, para
    que el que llega sepa que eso está abandonado y no en vuelo."""
    from plotspace.core import swarm_cli, provenance, territorio, agent_live, liveness
    from plotspace.core import herencia as mod_herencia
    provenance.reset(); territorio.reset(); mod_herencia.reset()
    monkeypatch.setattr(swarm_cli, '_nombre_de',
                        lambda tid: {'nombre': 'Frontend', 'project_id': 7, 'ruta': '/x'})
    monkeypatch.setattr(swarm_cli, '_terminales_activas_detalle',
                        lambda pid: [{'id': 10, 'nombre': 'Frontend', 'tipo_ia': 'claude'},
                                     {'id': 11, 'nombre': 'Backend', 'tipo_ia': 'claude'}])
    monkeypatch.setattr(agent_live, '_fases_agent_watch', lambda: {})
    monkeypatch.setattr(swarm_cli, 'mensajes_pendientes_mailbox', lambda pid, tid: [])
    monkeypatch.setattr(liveness, 'panes_ahora', lambda *a, **k: {10: 'node', 11: 'bash'})
    monkeypatch.setattr(mod_herencia, 'sucios_de', lambda ruta, ahora=None: {'huerfano.py'})
    provenance.registrar(7, 11, 'Backend', 'huerfano.py', 'write', ts=100)
    d = swarm_cli.estado(10)
    assert d['herencia'] == [{'tid': 11, 'nombre': 'Backend',
                              'archivos': ['huerfano.py']}]


def test_lo_sucio_de_un_par_vivo_no_se_declara_herencia(monkeypatch):
    from plotspace.core import swarm_cli, provenance, territorio, agent_live, liveness
    from plotspace.core import herencia as mod_herencia
    provenance.reset(); territorio.reset(); mod_herencia.reset()
    monkeypatch.setattr(swarm_cli, '_nombre_de',
                        lambda tid: {'nombre': 'Frontend', 'project_id': 7, 'ruta': '/x'})
    monkeypatch.setattr(swarm_cli, '_terminales_activas_detalle',
                        lambda pid: [{'id': 10, 'nombre': 'Frontend', 'tipo_ia': 'claude'},
                                     {'id': 11, 'nombre': 'Backend', 'tipo_ia': 'claude'}])
    monkeypatch.setattr(agent_live, '_fases_agent_watch', lambda: {})
    monkeypatch.setattr(swarm_cli, 'mensajes_pendientes_mailbox', lambda pid, tid: [])
    monkeypatch.setattr(liveness, 'panes_ahora', lambda *a, **k: {10: 'node', 11: 'node'})
    monkeypatch.setattr(mod_herencia, 'sucios_de', lambda ruta, ahora=None: {'enCurso.py'})
    provenance.registrar(7, 11, 'Backend', 'enCurso.py', 'write', ts=100)
    assert swarm_cli.estado(10)['herencia'] == []


if __name__ == '__main__':
    import sys
    sys.exit(pytest.main([__file__, '-q']))


# ─── Inbox filtrado por remitente (el poll de jv ask) ────────────────────────

def test_filtrar_de_matchea_como_jv_ask():
    from plotspace.core.swarm_cli import filtrar_de
    msgs = [{'id': 1, 'de': 'Claude Code #1', 'msg': 'a'},
            {'id': 2, 'de': 'Backend', 'msg': 'b'},
            {'id': 3, 'de': 'claude code #1', 'msg': 'c'}]
    assert [m['id'] for m in filtrar_de(msgs, 'Claude Code #1')] == [1, 3]
    assert [m['id'] for m in filtrar_de(msgs, 'backend')] == [2]
    assert filtrar_de(msgs, '') == msgs
    assert filtrar_de(msgs, None) == msgs


def test_inbox_con_de_no_consume_lo_de_terceros(monkeypatch):
    """El bug del poll de `jv ask`: pedía el inbox ENTERO cada 3s durante hasta
    240s, marcando entregado TODO — un mensaje de un tercero que llegara en la
    espera se consumía sin mostrarse jamás. Con `de=`, solo se devuelven y
    marcan los del preguntado; el resto queda pendiente para su entrega
    normal."""
    from plotspace.core import swarm_cli
    marcados = []
    monkeypatch.setattr(swarm_cli, '_nombre_de',
                        lambda tid: {'project_id': 1, 'nombre': 'Yo'})
    monkeypatch.setattr(swarm_cli, 'mensajes_pendientes_mailbox',
                        lambda pid, tid: [
                            {'id': 10, 'de': 'Claude Code #2', 'msg': 'respuesta', 'timestamp': ''},
                            {'id': 11, 'de': 'Claude Code #4', 'msg': 'otro tema', 'timestamp': ''}])
    monkeypatch.setattr(swarm_cli, 'marcar_mensajes_entregados',
                        lambda ids: marcados.extend(ids))

    r = swarm_cli.inbox(5, marcar=True, de='Claude Code #2')
    assert [m['id'] for m in r['mensajes']] == [10]
    assert marcados == [10], 'el mensaje del tercero (11) NO se marca entregado'


def test_inbox_sin_de_sigue_marcando_todo(monkeypatch):
    from plotspace.core import swarm_cli
    marcados = []
    monkeypatch.setattr(swarm_cli, '_nombre_de',
                        lambda tid: {'project_id': 1, 'nombre': 'Yo'})
    monkeypatch.setattr(swarm_cli, 'mensajes_pendientes_mailbox',
                        lambda pid, tid: [{'id': 1, 'de': 'A', 'msg': 'x', 'timestamp': ''},
                                          {'id': 2, 'de': 'B', 'msg': 'y', 'timestamp': ''}])
    monkeypatch.setattr(swarm_cli, 'marcar_mensajes_entregados',
                        lambda ids: marcados.extend(ids))
    r = swarm_cli.inbox(5)
    assert len(r['mensajes']) == 2 and marcados == [1, 2]
