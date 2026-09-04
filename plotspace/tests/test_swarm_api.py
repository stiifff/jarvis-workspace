# plotspace/tests/test_swarm_api.py
"""API del enjambre: ingesta de provenance (POST /api/swarm/op) y guarda previa
(POST /api/swarm/check).

Es la puerta por la que entra el dato REAL de cada edición (la manda el hook
PostToolUse del CLI). Los tests validan el contrato con el hook: qué acepta, qué
rechaza y que NUNCA tira 500 — un endpoint que falla dejaría a los agentes sin
propiedad otra vez, y encima con la guarda previa colgando sus herramientas.
"""
import pytest
from fastapi.testclient import TestClient

from plotspace.core import provenance, territorio


@pytest.fixture()
def cliente(monkeypatch, tmp_path):
    """App mínima con solo el router de live/swarm montado (sin auth ni WS)."""
    from fastapi import FastAPI
    from plotspace.routers import live

    app = FastAPI()
    app.include_router(live.router)

    # Terminal 397 del proyecto 7 en tmp_path; 999 no existe.
    def _row(tid):
        if tid == 397:
            return {'tid': 397, 'tnombre': 'Claude Code #2', 'tipo_ia': 'claude',
                    'pid': 7, 'ruta': str(tmp_path)}
        return None

    from plotspace.core import agent_live
    monkeypatch.setattr(agent_live, '_row_terminal', _row)
    monkeypatch.setattr(agent_live, '_rows_de', lambda pid=None: [
        {'tid': 397, 'tnombre': 'Claude Code #2', 'tipo_ia': 'claude',
         'pid': 7, 'ruta': str(tmp_path)}])

    async def _noop_publicar(*a, **k):
        return None
    monkeypatch.setattr(agent_live, '_publicar', _noop_publicar)

    agent_live._archivos.clear()
    agent_live._duenos.clear()
    agent_live._alertas.clear()
    provenance.reset()
    territorio.reset()
    return TestClient(app)


# ─── POST /api/swarm/op ───────────────────────────────────────────────────────

def test_op_edit_registra_propiedad(cliente):
    r = cliente.post('/api/swarm/op', json={
        'terminal_id': 397, 'tool_name': 'Edit',
        'tool_input': {'file_path': 'plotspace/core/x.py',
                       'old_string': 'a', 'new_string': 'b'}})
    assert r.status_code == 200
    assert r.json()['ops'][0]['estado'] == 'nueva'
    assert provenance.ediciones(pid=7, path='plotspace/core/x.py')


def test_op_write_marca_sobrescritura(cliente):
    cliente.post('/api/swarm/op', json={
        'terminal_id': 397, 'tool_name': 'Write',
        'tool_input': {'file_path': 'a.py', 'content': 'nuevo'}})
    ed = provenance.ediciones(pid=7, path='a.py')
    assert ed and ed[0]['sobrescritura'] is True


def test_op_opencode_edit_registra_provenance(cliente, tmp_path):
    """Contrato del plugin de opencode: reenvía sus args CRUDOS (tool `edit`,
    ruta ABSOLUTA, camelCase) y /swarm/op los registra igual que un Claude — la
    ruta absoluta se relativiza contra el proyecto."""
    abs_path = str(tmp_path / 'svc' / 'api.js')
    r = cliente.post('/api/swarm/op', json={
        'terminal_id': 397, 'tool_name': 'edit',
        'tool_input': {'filePath': abs_path, 'oldString': 'a=1', 'newString': 'a=2'}})
    assert r.status_code == 200
    assert r.json()['ops'][0]['estado'] == 'nueva'
    ed = provenance.ediciones(pid=7, path='svc/api.js')
    assert ed and ed[0]['antes'] == 'a=1' and ed[0]['despues'] == 'a=2'


def test_op_codex_apply_patch_registra_provenance(cliente, tmp_path):
    """Contrato del tailer de Codex: manda cada edición del rollout como
    `apply_patch` (ruta absoluta + antes/después del unified_diff) por el MISMO
    /swarm/op — apply_patch clasifica como escritura y se registra."""
    abs_path = str(tmp_path / 'mod.py')
    r = cliente.post('/api/swarm/op', json={
        'terminal_id': 397, 'tool_name': 'apply_patch',
        'tool_input': {'file_path': abs_path, 'old_string': 'def f():',
                       'new_string': 'def f(x):'}})
    assert r.status_code == 200
    assert r.json()['ops'][0]['estado'] == 'nueva'
    ed = provenance.ediciones(pid=7, path='mod.py')
    assert ed and ed[0]['despues'] == 'def f(x):'


def test_op_qwen_write_file_registra_provenance(cliente, tmp_path):
    """Contrato de qwen: `write_file` con `file_content` (ruta absoluta) → el mismo
    /swarm/op (reusa jarvis_ops_hook.py; normalizar_payload aprendió file_content)."""
    abs_path = str(tmp_path / 'q.py')
    r = cliente.post('/api/swarm/op', json={
        'terminal_id': 397, 'tool_name': 'write_file',
        'tool_input': {'file_path': abs_path, 'file_content': 'print(1)'}})
    assert r.status_code == 200
    ed = provenance.ediciones(pid=7, path='q.py')
    assert ed and ed[0]['despues'] == 'print(1)'


def test_op_replace_con_instruction_registra_provenance(cliente, tmp_path):
    """La herramienta `replace` (qwen, heredada del Gemini CLI) trae file_path +
    instruction + old_string/new_string — el `instruction` extra no estorba al
    normalizador, y `replace` clasifica como escritura."""
    abs_path = str(tmp_path / 'g.py')
    r = cliente.post('/api/swarm/op', json={
        'terminal_id': 397, 'tool_name': 'replace',
        'tool_input': {'file_path': abs_path, 'instruction': 'renombrar la función',
                       'old_string': 'viejo', 'new_string': 'nuevo'}})
    assert r.status_code == 200
    ed = provenance.ediciones(pid=7, path='g.py')
    assert ed and ed[0]['antes'] == 'viejo' and ed[0]['despues'] == 'nuevo'


def test_op_antigravity_write_registra_provenance(cliente, tmp_path):
    """Contrato de Antigravity: el hook traduce {toolCall:{name,args}} a
    tool_name/tool_input; sus args usan `path` (no `file_path`) y `content`."""
    abs_path = str(tmp_path / 'agy.py')
    r = cliente.post('/api/swarm/op', json={
        'terminal_id': 397, 'tool_name': 'write_to_file',
        'tool_input': {'path': abs_path, 'content': 'nuevo'}})
    assert r.status_code == 200
    ed = provenance.ediciones(pid=7, path='agy.py')
    assert ed and ed[0]['despues'] == 'nuevo'


def test_op_read_no_crea_dueno(cliente):
    cliente.post('/api/swarm/op', json={
        'terminal_id': 397, 'tool_name': 'Read',
        'tool_input': {'file_path': 'a.py'}})
    from plotspace.core import agent_live
    assert agent_live._duenos == {}


def test_op_multiple_edits_registra_todas(cliente):
    r = cliente.post('/api/swarm/op', json={
        'terminal_id': 397, 'tool_name': 'Edit',
        'tool_input': {'file_path': 'a.js', 'edits': [
            {'old_text': 'x', 'new_text': 'y'},
            {'old_text': 'p', 'new_text': 'q'}]}})
    assert len(r.json()['ops']) == 2
    assert len(provenance.ediciones(pid=7, path='a.js')) == 2


def test_op_terminal_inexistente_no_es_error(cliente):
    """El hook corre en CUALQUIER claude de la máquina: una terminal ajena o
    muerta se ignora en silencio, nunca con un 4xx/5xx que ensucie el pane."""
    r = cliente.post('/api/swarm/op', json={
        'terminal_id': 999, 'tool_name': 'Edit',
        'tool_input': {'file_path': 'a.py', 'old_string': 'a', 'new_string': 'b'}})
    assert r.status_code == 200
    assert r.json()['ops'][0]['estado'] == 'sin_terminal'


def test_op_herramienta_irrelevante_es_noop(cliente):
    r = cliente.post('/api/swarm/op', json={
        'terminal_id': 397, 'tool_name': 'Bash', 'tool_input': {'command': 'ls'}})
    assert r.status_code == 200 and r.json()['ops'] == []


def test_op_payload_incompleto_no_rompe(cliente):
    for cuerpo in ({'terminal_id': 397},
                   {'terminal_id': 397, 'tool_name': 'Edit'},
                   {'terminal_id': 397, 'tool_name': 'Edit', 'tool_input': {}},
                   {'terminal_id': 397, 'tool_name': None, 'tool_input': None}):
        r = cliente.post('/api/swarm/op', json=cuerpo)
        assert r.status_code == 200, cuerpo


def test_op_sin_terminal_id_es_422_o_200(cliente):
    """Sin terminal_id no hay nada que registrar; lo importante es que no 500."""
    r = cliente.post('/api/swarm/op', json={'tool_name': 'Edit'})
    assert r.status_code in (200, 422)


# ─── POST /api/swarm/check (guarda previa, Fase 1) ────────────────────────────

def test_check_permite_edit_normal(cliente):
    r = cliente.post('/api/swarm/check', json={
        'terminal_id': 397, 'tool_name': 'Edit',
        'tool_input': {'file_path': 'libre.py', 'old_string': 'a', 'new_string': 'b'}})
    assert r.status_code == 200 and r.json()['permitir'] is True


def test_check_frena_sobrescritura_de_archivo_ajeno_reciente(cliente):
    """El caso PROBADO que destruye: el #1 escribió hace un momento y el #2
    manda un Write completo con su copia vieja → el cambio del #1 desaparece."""
    provenance.registrar(7, 396, 'Claude Code #1', 'compartido.js', 'write',
                         antes='viejo', despues='nuevo del #1')
    r = cliente.post('/api/swarm/check', json={
        'terminal_id': 397, 'tool_name': 'Write',
        'tool_input': {'file_path': 'compartido.js', 'content': 'mi version'}})
    body = r.json()
    assert body['permitir'] is False
    assert 'Claude Code #1' in body['motivo']


def test_check_no_frena_edit_por_zona_en_archivo_ajeno(cliente):
    """Editar por zona un archivo que otro tocó NO se frena: está probado que
    dos ediciones en zonas distintas conviven. Frenar acá sería el ruido que
    generó el 32% de charla de coordinación."""
    provenance.registrar(7, 396, 'Claude Code #1', 'compartido.js', 'write',
                         antes='a', despues='b')
    r = cliente.post('/api/swarm/check', json={
        'terminal_id': 397, 'tool_name': 'Edit',
        'tool_input': {'file_path': 'compartido.js',
                       'old_string': 'otra zona', 'new_string': 'x'}})
    assert r.json()['permitir'] is True


def test_check_no_frena_mi_propia_sobrescritura(cliente):
    provenance.registrar(7, 397, 'Claude Code #2', 'mio.js', 'write',
                         antes='a', despues='b')
    r = cliente.post('/api/swarm/check', json={
        'terminal_id': 397, 'tool_name': 'Write',
        'tool_input': {'file_path': 'mio.js', 'content': 'x'}})
    assert r.json()['permitir'] is True


def test_check_terminal_desconocida_permite(cliente):
    """Falla ABIERTO: si no sé quién sos, no te bloqueo (misma doctrina que el
    guard de propiedad — un bug de la guarda jamás debe frenar a todos)."""
    r = cliente.post('/api/swarm/check', json={
        'terminal_id': 999, 'tool_name': 'Write',
        'tool_input': {'file_path': 'a.js', 'content': 'x'}})
    assert r.json()['permitir'] is True


def test_check_payload_basura_permite(cliente):
    r = cliente.post('/api/swarm/check', json={'terminal_id': 397})
    assert r.status_code == 200 and r.json()['permitir'] is True


# ─── Territorio: la colisión PREVENIDA, no avisada después ───────────────────

def test_claim_concede_lo_libre(cliente):
    r = cliente.post('/api/swarm/claim', json={
        'terminal_id': 397, 'patrones': ['aplicarIdioma', 'builder.js']})
    assert r.json()['otorgados'] == ['aplicarIdioma', 'builder.js']


def test_claim_no_roba_lo_ajeno(cliente):
    from plotspace.core import territorio
    territorio.reclamar(7, 396, 'Claude Code #1', ['aplicarIdioma'])
    d = cliente.post('/api/swarm/claim', json={
        'terminal_id': 397, 'patrones': ['aplicarIdioma']}).json()
    assert d['otorgados'] == []
    assert d['ocupados'][0]['de'] == 'Claude Code #1'


def test_check_BLOQUEA_borrar_un_simbolo_ajeno(cliente):
    """El caso real del Builder, ahora PREVENIDO: antes se avisaba después de
    romperlo, y el otro se enteraba cuando su código dejaba de andar."""
    from plotspace.core import territorio
    territorio.reclamar(7, 396, 'Claude Code #1', ['bw-cfg-uso-top'])
    d = cliente.post('/api/swarm/check', json={
        'terminal_id': 397, 'tool_name': 'Edit',
        'tool_input': {'file_path': 'index.html',
                       'old_string': '<div class="bw-cfg-uso-top">x</div>',
                       'new_string': ''}}).json()
    assert d['permitir'] is False
    assert 'bw-cfg-uso-top' in d['motivo']
    assert d['dueno'] == 'Claude Code #1'


def test_check_DEJA_PASAR_referenciar_un_simbolo_ajeno(cliente):
    """Llamar a la función del otro es trabajo normal. Bloquear esto sería el
    falso positivo más molesto posible."""
    from plotspace.core import territorio
    territorio.reclamar(7, 396, 'Otro', ['aplicarIdioma'])
    d = cliente.post('/api/swarm/check', json={
        'terminal_id': 397, 'tool_name': 'Edit',
        'tool_input': {'file_path': 'mio.js', 'old_string': '',
                       'new_string': 'aplicarIdioma()'}}).json()
    assert d['permitir'] is True


def test_check_DEJA_PASAR_otra_zona_del_archivo_compartido(cliente):
    from plotspace.core import territorio
    territorio.reclamar(7, 396, 'Otro', ['aplicarIdioma'])
    d = cliente.post('/api/swarm/check', json={
        'terminal_id': 397, 'tool_name': 'Edit',
        'tool_input': {'file_path': 'builder.js', 'old_string': 'const a = 1',
                       'new_string': 'const a = 2'}}).json()
    assert d['permitir'] is True


def test_check_BLOQUEA_escribir_en_ruta_reclamada(cliente):
    from plotspace.core import territorio
    territorio.reclamar(7, 396, 'Otro', ['plotspace/core/'])
    d = cliente.post('/api/swarm/check', json={
        'terminal_id': 397, 'tool_name': 'Edit',
        'tool_input': {'file_path': 'plotspace/core/x.py', 'old_string': 'a',
                       'new_string': 'b'}}).json()
    assert d['permitir'] is False and d['dueno'] == 'Otro'


def test_op_auto_reclama_los_simbolos_declarados(cliente):
    """Ampliación automática: lo que nadie reclamó se concede solo al escribir."""
    from plotspace.core import territorio
    cliente.post('/api/swarm/op', json={
        'terminal_id': 397, 'tool_name': 'Edit',
        'tool_input': {'file_path': 'a.js', 'old_string': '',
                       'new_string': 'function unaFuncionNueva() {}'}})
    d = territorio.duenio(7, 'unaFuncionNueva')
    assert d is not None and d['tid'] == 397


def test_op_NO_auto_reclama_el_archivo(cliente):
    """Si tocar un archivo lo hiciera tuyo, el segundo agente que entrara a otra
    zona quedaría bloqueado sin motivo."""
    from plotspace.core import territorio
    cliente.post('/api/swarm/op', json={
        'terminal_id': 397, 'tool_name': 'Edit',
        'tool_input': {'file_path': 'compartido.js', 'old_string': '',
                       'new_string': 'function algo() {}'}})
    assert territorio.duenio(7, 'compartido.js') is None


def test_territorio_lista_los_reclamos(cliente):
    from plotspace.core import territorio
    territorio.reclamar(7, 396, 'Otro', ['x.js'])
    d = cliente.get('/api/swarm/territorio/7').json()
    assert d['reclamos'][0]['patron'] == 'x.js'


# ─── Grupos del enjambre (panel de visibilidad) ──────────────────────────────

def test_grupos_vacio_sin_solapamiento(cliente):
    provenance.registrar(7, 396, 'A', 'a.js', 'write', despues='x')
    provenance.registrar(7, 397, 'B', 'b.js', 'write', despues='y')
    assert cliente.get('/api/swarm/grupos/7').json()['grupos'] == []


def test_grupos_detecta_convergencia(cliente):
    provenance.registrar(7, 396, 'A', 'builder.js', 'write', despues='uno')
    provenance.registrar(7, 397, 'B', 'builder.js', 'write', despues='dos')
    g = cliente.get('/api/swarm/grupos/7').json()['grupos']
    assert len(g) == 1
    assert g[0]['estado'] == 'convergencia'      # informativo, NO alarma
    assert len(g[0]['miembros']) == 2


def test_grupo_de_TRES_agentes(cliente):
    for tid, n in ((395, 'A'), (396, 'B'), (397, 'C')):
        provenance.registrar(7, tid, n, 'builder.js', 'write', despues=f'de {n}')
    g = cliente.get('/api/swarm/grupos/7').json()['grupos']
    assert len(g) == 1 and len(g[0]['miembros']) == 3


def test_grupo_pasa_a_colision_cuando_hay_una(cliente):
    provenance.registrar(7, 396, 'A', 'builder.js', 'write', despues='uno')
    provenance.registrar(7, 397, 'B', 'builder.js', 'write', despues='dos')
    provenance.registrar_colision(7, 397, 'B', 'builder.js',
                                  [{'simbolo': 'x', 'tid': 396, 'nombre': 'A',
                                    'path': 'builder.js'}])
    assert cliente.get('/api/swarm/grupos/7').json()['grupos'][0]['estado'] == 'colision'


def test_detalle_del_grupo_trae_todo_lo_del_overlay(cliente):
    provenance.registrar(7, 396, 'A', 'builder.js', 'write', despues='function unaCosa(){}')
    provenance.registrar(7, 397, 'B', 'builder.js', 'write', despues='otra cosa acá')
    gid = cliente.get('/api/swarm/grupos/7').json()['grupos'][0]['id']
    d = cliente.get(f'/api/swarm/grupo/7/{gid}').json()
    for clave in ('miembros', 'archivos', 'simbolos', 'agentes', 'timeline',
                  'colisiones', 'mensajes'):
        assert clave in d, clave
    assert len(d['timeline']) == 2
    assert {a['nombre'] for a in d['agentes']} == {'A', 'B'}


def test_detalle_de_grupo_inexistente_es_404(cliente):
    assert cliente.get('/api/swarm/grupo/7/gNOPE').status_code == 404


# ─── Colisión por funcionalidad (Fase 2), sobre el mismo POST /op ────────────

def test_op_que_borra_simbolo_ajeno_devuelve_aviso(cliente):
    """El caso real del Builder, extremo a extremo por la API: el otro agente
    referencia `.bw-cfg-uso-top`, yo borro el nodo → me avisan EN EL ACTO."""
    provenance.registrar(7, 396, 'Claude Code #1', 'builder.js', 'write',
                         despues="$('.bw-cfg-uso-top span').textContent = t")
    r = cliente.post('/api/swarm/op', json={
        'terminal_id': 397, 'tool_name': 'Edit',
        'tool_input': {'file_path': 'index.html',
                       'old_string': '<div class="bw-cfg-uso-top"><span>3</span></div>',
                       'new_string': ''}})
    body = r.json()
    assert body['avisos'], 'la colisión tenía que detectarse'
    assert body['avisos'][0]['simbolo'] == 'bw-cfg-uso-top'
    assert 'Claude Code #1' in body['aviso_texto']
    assert 'MAILBOX' in body['aviso_texto']


def test_colision_funcional_nombra_al_actor(cliente, monkeypatch):
    """El evento WS de colisión lleva el NOMBRE del actor — la animación del
    Swarm necesita decirle a la víctima QUIÉN le borró el símbolo."""
    from plotspace.core.events import broadcaster
    capturados = []

    async def _cap(pid, ev):
        capturados.append(ev)
    monkeypatch.setattr(broadcaster, 'broadcast', _cap)

    provenance.registrar(7, 396, 'Claude Code #1', 'builder.js', 'write',
                         despues="$('.bw-cfg-uso-top span').textContent = t")
    cliente.post('/api/swarm/op', json={
        'terminal_id': 397, 'tool_name': 'Edit',
        'tool_input': {'file_path': 'index.html',
                       'old_string': '<div class="bw-cfg-uso-top"><span>3</span></div>',
                       'new_string': ''}})
    cf = [e for e in capturados if e.get('type') == 'colision_funcional']
    assert cf, 'se emitió el evento de colisión'
    assert cf[0]['terminal_nombre'] == 'Claude Code #2', 'el evento nombra al actor'
    assert cf[0]['colisiones'][0]['simbolo'] == 'bw-cfg-uso-top'


def test_op_con_colision_incrementa_el_contador_de_salud(cliente):
    """Cada aviso de colisión emitido queda contado en salud (2a): hace
    observable el path que antes podía morirse dejando salud en verde."""
    provenance.registrar(7, 396, 'Claude Code #1', 'builder.js', 'write',
                         despues="$('.bw-cfg-uso-top span')")
    antes = provenance.salud()['avisos_colision_emitidos']
    cliente.post('/api/swarm/op', json={
        'terminal_id': 397, 'tool_name': 'Edit',
        'tool_input': {'file_path': 'index.html',
                       'old_string': '<div class="bw-cfg-uso-top"><span>3</span></div>',
                       'new_string': ''}})
    assert provenance.salud()['avisos_colision_emitidos'] == antes + 1


def test_op_normal_no_genera_avisos(cliente):
    r = cliente.post('/api/swarm/op', json={
        'terminal_id': 397, 'tool_name': 'Edit',
        'tool_input': {'file_path': 'a.py', 'old_string': 'x = 1',
                       'new_string': 'x = 2'}})
    assert r.json()['avisos'] == [] and r.json()['aviso_texto'] == ''


def test_op_que_borra_algo_solo_mio_no_avisa(cliente):
    provenance.registrar(7, 397, 'Yo', 'a.js', 'write', despues="$('.mi-clase')")
    r = cliente.post('/api/swarm/op', json={
        'terminal_id': 397, 'tool_name': 'Edit',
        'tool_input': {'file_path': 'a.js',
                       'old_string': '<div class="mi-clase">x</div>',
                       'new_string': ''}})
    assert r.json()['avisos'] == []


def test_editar_zonas_distintas_del_mismo_archivo_no_avisa(cliente):
    """La regla invertida: compartir archivo NO es motivo de aviso (está medido
    que las ediciones por zona conviven). Solo avisa la superficie compartida."""
    provenance.registrar(7, 396, 'Otro', 'compartido.js', 'write',
                         despues='return animarSuave(x)')
    r = cliente.post('/api/swarm/op', json={
        'terminal_id': 397, 'tool_name': 'Edit',
        'tool_input': {'file_path': 'compartido.js',
                       'old_string': 'const scrollbar = true;',
                       'new_string': 'const scrollbar = false;'}})
    assert r.json()['avisos'] == []


# ─── GET /api/swarm/fragmentos (insumo del commit por hunk, Fase 1) ──────────

def test_fragmentos_separa_lo_mio_de_lo_ajeno(cliente):
    provenance.registrar(7, 397, 'Yo',   'compartido.js', 'write',
                         antes='const scrollbar = true;',
                         despues='const scrollbar = false;')
    provenance.registrar(7, 396, 'Otro', 'compartido.js', 'write',
                         antes='animar(x)', despues='animarSuave(x)')
    d = cliente.get('/api/swarm/fragmentos/397').json()
    assert 'const scrollbar = false;' in d['mios']['compartido.js']
    assert 'animarSuave(x)' in d['ajenos']['compartido.js']
    assert 'animarSuave(x)' not in d['mios']['compartido.js']


def test_fragmentos_incluye_el_antes_para_atribuir_borrados(cliente):
    """Un hunk que solo BORRA se atribuye por lo que quitó, así que el `antes`
    también tiene que viajar."""
    provenance.registrar(7, 397, 'Yo', 'a.js', 'write',
                         antes='function vieja() {}', despues='')
    assert 'function vieja() {}' in cliente.get(
        '/api/swarm/fragmentos/397').json()['mios']['a.js']


def test_fragmentos_solo_de_archivos_que_toque(cliente):
    """Los archivos que solo tocó otro agente no son asunto mío."""
    provenance.registrar(7, 397, 'Yo',   'mio.js',  'write', despues='x')
    provenance.registrar(7, 396, 'Otro', 'suyo.js', 'write', despues='y')
    d = cliente.get('/api/swarm/fragmentos/397').json()
    assert d['archivos'] == ['mio.js']
    assert 'suyo.js' not in d['ajenos']


def test_fragmentos_terminal_desconocida_vacio(cliente):
    d = cliente.get('/api/swarm/fragmentos/999').json()
    assert d == {'mios': {}, 'ajenos': {}, 'archivos': []}


if __name__ == '__main__':
    import sys
    sys.exit(pytest.main([__file__, '-q']))
