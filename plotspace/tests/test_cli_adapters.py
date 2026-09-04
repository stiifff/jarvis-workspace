# plotspace/tests/test_cli_adapters.py
"""Instalador del adaptador de provenance de opencode (core/cli_adapters.py).

Claude reporta por su hook PostToolUse; opencode por un PLUGIN JS que Jarvis deja
en ~/.config/opencode/plugin/ al boot. Mismas reglas que hooks_cli: idempotente,
best-effort (nunca rompe el boot), no toca plugins ajenos.
"""
import json
import os

from plotspace.core import cli_adapters

# raíz del repo (plotspace/tests/ → plotspace/ → repo)
RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_instala_el_plugin_de_opencode(tmp_path):
    dest = str(tmp_path / 'plugin')
    assert cli_adapters.asegurar_opencode_plugin(RAIZ, dest) is True
    p = tmp_path / 'plugin' / 'jarvis-swarm.js'
    assert p.exists()
    txt = p.read_text(encoding='utf-8')
    assert '/api/swarm/op' in txt and 'JARVIS_TERMINAL_ID' in txt


def test_es_idempotente(tmp_path):
    dest = str(tmp_path / 'plugin')
    assert cli_adapters.asegurar_opencode_plugin(RAIZ, dest) is True    # primera vez: escribe
    assert cli_adapters.asegurar_opencode_plugin(RAIZ, dest) is False   # ya al día: no reescribe


def test_reescribe_si_cambio(tmp_path):
    dest = tmp_path / 'plugin'
    dest.mkdir()
    (dest / 'jarvis-swarm.js').write_text('plugin viejo', encoding='utf-8')
    assert cli_adapters.asegurar_opencode_plugin(RAIZ, str(dest)) is True   # difiere → reescribe


def test_no_rompe_sin_fuente(tmp_path):
    """Sin scripts/opencode_jarvis_plugin.js en la raíz dada: False, no excepción."""
    assert cli_adapters.asegurar_opencode_plugin(str(tmp_path), str(tmp_path / 'p')) is False


# ─── qwen: hook estilo Claude en ~/.qwen/settings.json ───────────────────────

def test_instala_el_hook_de_qwen(tmp_path):
    import json
    settings = str(tmp_path / 'settings.json')
    assert cli_adapters.asegurar_qwen_hook(RAIZ, settings) is True
    with open(settings, encoding='utf-8') as f:
        data = json.load(f)
    assert 'PostToolUse' in data['hooks'] and 'PreToolUse' in data['hooks']
    post = data['hooks']['PostToolUse'][0]
    assert 'write_file' in post['matcher']                 # tool names de qwen
    assert 'jarvis_ops_hook' in post['hooks'][0]['command']  # reusa el hook de Claude


def test_qwen_hook_es_idempotente(tmp_path):
    settings = str(tmp_path / 'settings.json')
    assert cli_adapters.asegurar_qwen_hook(RAIZ, settings) is True
    assert cli_adapters.asegurar_qwen_hook(RAIZ, settings) is False


def test_qwen_hook_no_pisa_config_ajena(tmp_path):
    """La config del usuario (y un hook suyo en otro evento) sobrevive."""
    import json
    settings = tmp_path / 'settings.json'
    settings.write_text(json.dumps({
        'model': 'qwen-max',
        'hooks': {'SessionStart': [{'matcher': '', 'hooks': [
            {'type': 'command', 'command': 'mio.sh'}]}]}}), encoding='utf-8')
    cli_adapters.asegurar_qwen_hook(RAIZ, str(settings))
    data = json.loads(settings.read_text(encoding='utf-8'))
    assert data['model'] == 'qwen-max'                     # su config intacta
    assert 'SessionStart' in data['hooks'] and 'mio.sh' in json.dumps(data)
    assert 'PostToolUse' in data['hooks']                  # + el nuestro, al lado


def test_no_hay_adaptador_de_gemini_standalone():
    """A propósito: acá lo instalado es ANTIGRAVITY (que lleva Gemini adentro),
    no el `gemini` suelto. Un adaptador para el CLI standalone sería código
    muerto escribiendo un ~/.gemini/settings.json que nadie lee."""
    assert not hasattr(cli_adapters, 'asegurar_gemini_hook')


# ─── Antigravity (agy): otra ESTRUCTURA de archivo, y solo PreToolUse ────────

def test_instala_el_hook_de_antigravity(tmp_path):
    import json
    hooks_json = str(tmp_path / 'hooks.json')
    assert cli_adapters.asegurar_antigravity_hook(RAIZ, hooks_json) is True
    with open(hooks_json, encoding='utf-8') as f:
        data = json.load(f)
    # Estructura PROPIA: {"<nombre>": {evento: [...]}}, no {"hooks": {...}}
    assert 'hooks' not in data
    nuestro = data['jarvis-provenance']
    assert 'PreToolUse' in nuestro          # el ÚNICO evento suyo que trae la ruta
    assert 'PostToolUse' not in nuestro     # el suyo no trae ni tool ni path
    grupo = nuestro['PreToolUse'][0]
    assert 'write_to_file' in grupo['matcher']
    assert 'replace_file_content' in grupo['matcher']
    assert 'jarvis_ops_hook' in grupo['hooks'][0]['command']


def test_antigravity_hook_es_idempotente(tmp_path):
    hooks_json = str(tmp_path / 'hooks.json')
    assert cli_adapters.asegurar_antigravity_hook(RAIZ, hooks_json) is True
    assert cli_adapters.asegurar_antigravity_hook(RAIZ, hooks_json) is False


def test_antigravity_no_pisa_hooks_ajenos(tmp_path):
    """Su hooks.json es un mapa de hooks CON NOMBRE: el del usuario sobrevive."""
    import json
    hooks_json = tmp_path / 'hooks.json'
    hooks_json.write_text(json.dumps({
        'mi-hook': {'Stop': [{'matcher': '', 'hooks': [
            {'type': 'command', 'command': 'mio.sh'}]}]}}), encoding='utf-8')
    cli_adapters.asegurar_antigravity_hook(RAIZ, str(hooks_json))
    data = json.loads(hooks_json.read_text(encoding='utf-8'))
    assert 'mi-hook' in data and 'mio.sh' in json.dumps(data)
    assert 'jarvis-provenance' in data       # el nuestro, al lado


def test_antigravity_no_pisa_json_ilegible(tmp_path):
    """Config corrupta: preferimos NO instalar antes que borrársela (misma
    doctrina que hooks_cli con el settings.json)."""
    hooks_json = tmp_path / 'hooks.json'
    hooks_json.write_text('{ esto no es json', encoding='utf-8')
    assert cli_adapters.asegurar_antigravity_hook(RAIZ, str(hooks_json)) is False
    assert 'esto no es json' in hooks_json.read_text(encoding='utf-8')


# ─── Cobertura del BRIEFING por CLI ───────────────────────────────────────────
# El briefing tiene dos canales y no todos los CLIs tienen los dos. Este bloque
# fija QUÉ canal le toca a cada uno, para que "soporta multi-CLI" sea verificable
# y no una promesa del README:
#
#   Claude       UserPromptSubmit (canal bueno: antes de pensar) + piggyback
#   qwen         UserPromptSubmit (si su versión lo conoce)      + piggyback
#   Antigravity  piggyback en su PreToolUse (único canal: no tiene hook de prompt)
#   opencode     piggyback en tool.execute.after (idem)
#   Codex        NINGUNO — sus ediciones no pasan por hooks (se tailea el
#                rollout), así que no hay dónde inyectarle contexto. Se entera
#                con `.jarvis/jv estado`, que funciona en cualquier terminal.

def test_qwen_declara_el_evento_del_briefing(tmp_path):
    settings = tmp_path / 'settings.json'
    cli_adapters.asegurar_qwen_hook(RAIZ, str(settings))
    hooks = json.loads(settings.read_text(encoding='utf-8'))['hooks']
    assert 'UserPromptSubmit' in hooks
    assert 'matcher' not in hooks['UserPromptSubmit'][0]


def test_el_hook_de_antigravity_sigue_siendo_solo_pretooluse(tmp_path):
    """Antigravity NO recibe UserPromptSubmit a propósito: su PostToolUse no trae
    ruta y su contrato de hooks es otro. Su briefing viaja pegado al `allow` del
    PreToolUse. Si esto cambia, que falle y se decida a conciencia."""
    hooks_json = tmp_path / 'hooks.json'
    cli_adapters.asegurar_antigravity_hook(RAIZ, str(hooks_json))
    mio = json.loads(hooks_json.read_text(encoding='utf-8'))['jarvis-provenance']
    assert set(mio) == {'PreToolUse'}


def test_el_plugin_de_opencode_lee_la_respuesta_del_server():
    """Era fire-and-forget con .catch(() => {}): la respuesta se tiraba, y con
    ella el único canal de briefing que tiene opencode."""
    fuente = os.path.join(RAIZ, 'scripts', cli_adapters.NOMBRE_PLUGIN_SRC)
    with open(fuente, encoding='utf-8') as f:
        js = f.read()
    assert 'briefing' in js
    assert 'await post(' in js


if __name__ == '__main__':
    import sys
    import pytest
    sys.exit(pytest.main([__file__, '-q']))
