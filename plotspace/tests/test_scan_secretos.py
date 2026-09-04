"""
Tests: escáner de secretos (scripts/scan_secretos.py) — el candado anti-fuga.

Pedido del usuario (2026-06-12): NUNCA debe salir hacia el remoto una API key
(Anthropic, MCP, lo que sea) ni el token de Jarvis — eso cuesta plata. El
escáner es la pieza pura; los hooks .githooks/pre-commit y pre-push lo corren
sobre lo staged / lo que está por pushearse y BLOQUEAN si encuentra algo.

Invariantes:
1. Detecta formatos de proveedores (Anthropic sk-ant, OpenAI, AWS AKIA, GitHub
   ghp_/github_pat_, Slack xox, Google AIza, Telegram bot, private keys, JWT)
   y asignaciones genéricas de literal largo a una var tipo secreto.
2. Detecta los VALORES REALES de los secretos locales (data/jarvis_token.txt,
   plotspace/.env) — leídos en runtime, jamás guardados en el script.
3. NO da falsos positivos con nombres de modelo (claude-*), hashes de git ni
   código normal.
4. La salida ENMASCARA: el valor completo nunca se imprime.
5. CLI: exit 0 limpio / exit 1 con hallazgos (los hooks dependen de esto).
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(RAIZ, 'scripts', 'scan_secretos.py')

import importlib.util
spec = importlib.util.spec_from_file_location('scan_secretos', SCRIPT)
scan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan)


# ─── 1. patrones de proveedores ───────────────────────────────────────────────

FALSOS = {
    'anthropic': 'sk-ant-api03-' + 'x' * 40,
    'openai':    'sk-proj-' + 'A1b2' * 12,
    'aws':       'AKIA' + 'A' * 16,
    'github':    'ghp_' + 'a1B2' * 9,
    'github-pat': 'github_pat_' + 'a1B2c3' * 5,
    'slack':     'xox' + 'b-1234567890-' + 'abcdef' * 3,
    'google':    'AIza' + 'B' * 35,
    'telegram':  '123456789:AA' + 'c' * 33,
    'privkey':   '-----BEGIN RSA ' + 'PRIVATE KEY-----',
    'jwt':       'eyJhbGciOiJIUzI1NiJ9.' + 'eyJzdWIiOiIxMjM0NTY3ODkwIn0.x',
}

def test_detecta_formatos_de_proveedores():
    for nombre, falso in FALSOS.items():
        hallazgos = scan.encontrar_secretos(f'config = "{falso}"\n')
        assert hallazgos, f'no detectó {nombre}'


def test_detecta_asignacion_generica():
    assert scan.encontrar_secretos('API_KEY = "Zx9' + 'q4Lm' * 8 + '"')
    assert scan.encontrar_secretos("password: 'N7" + 'kP2w' * 7 + "'")


# ─── 2. valores reales locales ────────────────────────────────────────────────

def test_detecta_valor_real_local():
    valor = 'un-token-real-cualquiera-9f8e7d6c5b4a'
    hallazgos = scan.encontrar_secretos(
        f'print("{valor}")', valores=[('token-jarvis', valor)])
    assert hallazgos
    assert any(h['patron'] == 'token-jarvis' for h in hallazgos)


def test_valores_locales_lee_archivos(tmp_path, monkeypatch):
    (tmp_path / 'data').mkdir()
    (tmp_path / 'data' / 'jarvis_token.txt').write_text('tokendeprueba123456\n')
    (tmp_path / 'plotspace').mkdir()
    clave_falsa = 'sk-ant-' + 'falsa-para-test-123456'
    (tmp_path / 'plotspace' / '.env').write_text(
        f'ANTHROPIC_API_KEY={clave_falsa}\n'
        'JAI_MODEL=claude-sonnet-4-6\n'   # nombre de modelo: NO es secreto
        '# comentario=nada\n')
    vals = dict(scan.valores_locales(str(tmp_path)))
    assert 'tokendeprueba123456' in vals.values()
    assert clave_falsa in vals.values()
    assert 'claude-sonnet-4-6' not in vals.values()


def test_valores_locales_lee_snapshots_cli_accounts(tmp_path):
    # Los snapshots de cuentas (data/cli-accounts/<id>/*.json) deben aportar sus
    # tokens al set de valores a cazar (defensa en profundidad).
    import json as _json
    d = tmp_path / 'data' / 'cli-accounts' / '7'
    d.mkdir(parents=True)
    token = 'snap-' + 'z' * 30   # literal corto + concat: no auto-dispara el escáner
    (d / 'auth.json').write_text(_json.dumps(
        {'tokens': {'access_token': token, 'account_id': 'corto'}}))
    vals = scan.valores_locales(str(tmp_path))
    valores = [v for _, v in vals]
    assert token in valores          # el token largo se captura
    assert 'corto' not in valores    # los strings cortos NO (evita ruido)


def test_snapshots_ignoran_urls_inocuas_de_vendors(tmp_path):
    # ~/.claude.json (snapshoteado en data/cli-accounts/) trae metadata del
    # marketplace de MCPs con cientos de URLs de vendors (privacy/terms/repos)
    # que NO son secretos y aparecen legítimamente en archivos del repo →
    # bloqueaban el push por falso positivo. Regla: URL simple (dominio + ≤2
    # segmentos de path, sin query/fragment) = inocua. Un webhook con token en
    # el path (estilo Slack, 3+ segmentos) o con query SÍ se sigue cazando.
    import json as _json
    d = tmp_path / 'data' / 'cli-accounts' / '9'
    d.mkdir(parents=True)
    webhook = 'https://hooks.ejemplo.com/services/T000/B000/' + 'x' * 24
    (d / 'config.json').write_text(_json.dumps({
        'plugins': ['https://example.com/privacy', 'https://github.com/vercel',
                    'https://mcp.notion.com/mcp', 'https://ejemplo.dev/site/terms'],
        'hook': webhook,
        'callback': 'https://a.ejemplo.com/cb?code=' + 'y' * 24,
    }))
    valores = [v for _, v in scan.valores_locales(str(tmp_path))]
    assert 'https://example.com/privacy' not in valores
    assert 'https://github.com/vercel' not in valores
    assert 'https://mcp.notion.com/mcp' not in valores
    assert 'https://ejemplo.dev/site/terms' not in valores
    assert webhook in valores                                   # token en path
    assert any(v.startswith('https://a.ejemplo.com/cb?code=') for v in valores)


def test_snapshots_ignoran_emails_slugs_y_texto_humano(tmp_path):
    # Más hojas de ~/.claude.json que NO son secretos y viven también en el
    # repo: el email del dueño de la cuenta, nombres humanos con espacios
    # ("...'s Organization") y slugs kebab-case de skills/plugins
    # (subagent-driven-development). Cero entropía = cero token. Un token real
    # (mezcla de mayúsculas/dígitos) se sigue cazando.
    import json as _json
    d = tmp_path / 'data' / 'cli-accounts' / '3'
    d.mkdir(parents=True)
    token = 'sk-' + 'Ab1' * 10   # concat: no auto-dispara el escáner
    (d / 'meta.json').write_text(_json.dumps({
        'email': 'usuario.de.prueba@gmail.com',
        'org': "usuario.de.prueba@gmail.com's Organization",
        'skill': 'subagent-driven-development',
        'token': token,
    }))
    valores = [v for _, v in scan.valores_locales(str(tmp_path))]
    assert 'usuario.de.prueba@gmail.com' not in valores
    assert "usuario.de.prueba@gmail.com's Organization" not in valores
    assert 'subagent-driven-development' not in valores
    assert token in valores


def test_snapshots_ignoran_rutas_de_proyectos(tmp_path):
    # Codex guarda en su snapshot los directorios donde trabajaste. Esas rutas
    # entraban como "secretos" y bloqueaban CUALQUIER commit que las mencionara
    # — un test, un script de mudanza, un comentario. Peor: el bloqueo es del
    # repo entero, así que le pasa a todo el enjambre y el mensaje habla de
    # "API keys", que no ayuda a entender nada.
    import json as _json
    d = tmp_path / 'data' / 'cli-accounts' / '4'
    d.mkdir(parents=True)
    token = 'sk-' + 'Xy9' * 10
    (d / 'history.json').write_text(_json.dumps({
        'cwd': '/home/user/proyectos/Derlis-APP',
        'anterior': 'C:\\Users\\alguien\\proyectos\\mi-app',
        'home': '~/jarvis/plotspace/routers',
        'token': token,
    }))
    valores = [v for _, v in scan.valores_locales(str(tmp_path))]
    assert '/home/user/proyectos/Derlis-APP' not in valores
    assert 'C:\\Users\\alguien\\proyectos\\mi-app' not in valores
    assert '~/jarvis/plotspace/routers' not in valores
    assert token in valores, 'el token de al lado se sigue cazando'


def test_una_ruta_con_un_token_adentro_sigue_siendo_secreto(tmp_path):
    # El agujero que abriría "las rutas son inocuas" si se aplicara a lo bruto:
    # basta con meter el token en un segmento para pasar el filtro.
    import json as _json
    d = tmp_path / 'data' / 'cli-accounts' / '5'
    d.mkdir(parents=True)
    con_token = '/home/user/' + 'sk-ant-api03-' + 'Kq7' * 12
    (d / 'x.json').write_text(_json.dumps({'ruta': con_token}))
    valores = [v for _, v in scan.valores_locales(str(tmp_path))]
    assert con_token in valores


def test_un_blob_base64_que_arranca_con_barra_no_es_una_ruta(tmp_path):
    # El alfabeto base64 incluye '/', así que un token puede empezar con barra.
    # Si eso contara como "ruta absoluta", se filtraría un secreto real.
    import json as _json
    d = tmp_path / 'data' / 'cli-accounts' / '6'
    d.mkdir(parents=True)
    blob = '/' + 'aB3dEf9Gh2JkLm5N' * 3 + '=='
    (d / 'y.json').write_text(_json.dumps({'k': blob}))
    valores = [v for _, v in scan.valores_locales(str(tmp_path))]
    assert blob in valores


# ─── 3. sin falsos positivos ──────────────────────────────────────────────────

def test_no_flaggea_codigo_normal():
    limpio = '\n'.join([
        'modelo = "claude-sonnet-4-6"',
        'JAI_MODEL = os.environ.get("JAI_MODEL", "claude-haiku-4-5")',
        'commit 5a35c54fa9b2c3d4e5f60718293a4b5c6d7e8f90',
        'token = data["jarvis_token"]',          # referencia, no literal
        'const x = "data/jarvis_token.txt"',     # ruta, no valor
        'subprocess.run(["tmux", "capture-pane", "-S", "-"])',
    ])
    assert scan.encontrar_secretos(limpio) == []


# ─── 4. enmascarado ───────────────────────────────────────────────────────────

def test_salida_enmascara_el_valor():
    falso = 'sk-ant-api03-' + 'S' * 40
    hallazgos = scan.encontrar_secretos(f'k = "{falso}"')
    texto = scan.formatear(hallazgos)
    assert falso not in texto          # el valor completo JAMÁS sale
    assert 'sk-ant' in texto           # pero se entiende qué se encontró


# ─── 5. CLI / exit codes (contrato de los hooks) ─────────────────────────────

def _cli(entrada):
    return subprocess.run([sys.executable, SCRIPT],
                          input=entrada, capture_output=True, text=True)

def test_cli_limpio_exit_0():
    r = _cli('diff limpio sin nada raro\n+ modelo = "claude-sonnet-4-6"\n')
    assert r.returncode == 0

def test_cli_con_secreto_exit_1_y_enmascarado():
    falso = 'sk-ant-api03-' + 'Q' * 40
    r = _cli(f'+ ANTHROPIC_API_KEY = "{falso}"\n')
    assert r.returncode == 1
    assert falso not in r.stdout + r.stderr
