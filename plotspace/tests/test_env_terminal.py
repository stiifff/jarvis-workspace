"""_env_terminal: el entorno con el que nacen TODAS las terminales de Jarvis."""
from plotspace.routers.terminals import _env_terminal


def test_sin_api_key_y_con_colores(monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-ant-' + 'falsa')  # concatenada: no dispara el escáner
    env = _env_terminal()
    assert 'ANTHROPIC_API_KEY' not in env
    assert env['TERM'] == 'xterm-256color'
    assert env['COLORTERM'] == 'truecolor'


def test_prompt_suggestions_apagadas(monkeypatch):
    """El 'prompt sugerido' (ghost text) de Claude Code v2.1.x agranda el cuadro
    de input con texto que el usuario no puso (pedido 2026-07-02: quitarlo):
    toda terminal de Jarvis nace con la feature APAGADA. Nombre de la var
    verificado contra el binario 2.1.198 instalado y la doc oficial
    (code.claude.com/docs/en/interactive-mode)."""
    monkeypatch.delenv('JARVIS_PROMPT_SUGGESTIONS', raising=False)
    env = _env_terminal()
    assert env['CLAUDE_CODE_ENABLE_PROMPT_SUGGESTION'] == 'false'


def test_prompt_suggestions_escape_hatch(monkeypatch):
    """JARVIS_PROMPT_SUGGESTIONS=on restaura el default de Claude Code."""
    monkeypatch.setenv('JARVIS_PROMPT_SUGGESTIONS', 'on')
    monkeypatch.delenv('CLAUDE_CODE_ENABLE_PROMPT_SUGGESTION', raising=False)
    env = _env_terminal()
    assert 'CLAUDE_CODE_ENABLE_PROMPT_SUGGESTION' not in env


def test_claude_fullscreen_por_default(monkeypatch):
    """Claude Code nace en FULLSCREEN (CLAUDE_CODE_NO_FLICKER=1, v2.1.89+):
    el transcript vive contenido en alt-screen y NADA cae al scrollback — mata
    la familia 'texto multiplicado/cortado al maximizar' (video del usuario
    2026-07-02) y los residuos de /usage. Reintroducido de 3661136 (la 'bala
    de plata' que cayó en el revert masivo) con el OK explícito del usuario."""
    monkeypatch.delenv('JARVIS_CLAUDE_FULLSCREEN', raising=False)
    env = _env_terminal()
    assert env['CLAUDE_CODE_NO_FLICKER'] == '1'


def test_claude_fullscreen_escape_hatch(monkeypatch):
    """JARVIS_CLAUDE_FULLSCREEN=off vuelve al default de Claude Code."""
    monkeypatch.setenv('JARVIS_CLAUDE_FULLSCREEN', 'off')
    monkeypatch.delenv('CLAUDE_CODE_NO_FLICKER', raising=False)
    env = _env_terminal()
    assert 'CLAUDE_CODE_NO_FLICKER' not in env


def test_claude_full_repaint_por_default(monkeypatch):
    """CLAUDE_CODE_ALT_SCREEN_FULL_REPAINT=1 acompaña al fullscreen (deep work
    2026-07-08, video del freeze): al scrollear una conversación GIGANTE
    (212.7k tokens) claude re-layoutea el transcript emitiendo frames PARCIALES
    (mueve bloques sin borrar el resto → regiones negras huérfanas) y se calla
    hasta 29.8s medidos. Con full-repaint cada frame borra y repinta el
    viewport completo (EL en todas las filas): regiones negras imposibles en
    origen y el peor silencio cae a 2.3s (-92%), medido con la MISMA
    conversación del incidente en claude v2.1.204. Costo: ~4x bytes solo
    durante scroll agresivo (~190KB/s pico) — trivial para el motor control."""
    monkeypatch.delenv('JARVIS_CLAUDE_FULLSCREEN', raising=False)
    monkeypatch.delenv('JARVIS_CLAUDE_FULL_REPAINT', raising=False)
    env = _env_terminal()
    assert env['CLAUDE_CODE_ALT_SCREEN_FULL_REPAINT'] == '1'


def test_claude_full_repaint_escape_hatch(monkeypatch):
    """JARVIS_CLAUDE_FULL_REPAINT=off vuelve al render incremental de claude
    (menos bytes) sin apagar el fullscreen."""
    monkeypatch.delenv('JARVIS_CLAUDE_FULLSCREEN', raising=False)
    monkeypatch.setenv('JARVIS_CLAUDE_FULL_REPAINT', 'off')
    monkeypatch.delenv('CLAUDE_CODE_ALT_SCREEN_FULL_REPAINT', raising=False)
    env = _env_terminal()
    assert env['CLAUDE_CODE_NO_FLICKER'] == '1'
    assert 'CLAUDE_CODE_ALT_SCREEN_FULL_REPAINT' not in env


_MARCAS_SESION = (
    'CLAUDECODE', 'CLAUDE_CODE_CHILD_SESSION', 'CLAUDE_CODE_ENTRYPOINT',
    'CLAUDE_CODE_EXECPATH', 'CLAUDE_CODE_SESSION_ID', 'CLAUDE_CODE_SSE_PORT',
    'CLAUDE_PID', 'CLAUDE_EFFORT',
)


def test_sin_marcas_de_la_sesion_claude_que_arranco_el_server(monkeypatch):
    """Si el server lo arrancó una sesión de Claude Code (un dev, un agente),
    su entorno viaja uvicorn → motor → terminal: los claude del workspace
    nacían creyéndose SESIÓN HIJA de esa otra ("Transcript saving is off —
    inherited CLAUDE_CODE_CHILD_SESSION marker", visto 2026-08-02 en la app
    de Linux). Las marcas de identidad de sesión se sellan acá; los knobs de
    config (NO_FLICKER, prompt suggestions) se inyectan DESPUÉS y no se tocan."""
    for var in _MARCAS_SESION:
        monkeypatch.setenv(var, 'x')
    env = _env_terminal()
    for var in _MARCAS_SESION:
        assert var not in env, var
    # Los knobs de config sobreviven al sello (se setean después de limpiar).
    assert env['CLAUDE_CODE_ENABLE_PROMPT_SUGGESTION'] == 'false'


def test_claude_full_repaint_sigue_al_fullscreen(monkeypatch):
    """Sin fullscreen (render inline clásico) el full-repaint no aplica: la
    var no se inyecta para no cambiar el comportamiento del modo default."""
    monkeypatch.setenv('JARVIS_CLAUDE_FULLSCREEN', 'off')
    monkeypatch.delenv('JARVIS_CLAUDE_FULL_REPAINT', raising=False)
    monkeypatch.delenv('CLAUDE_CODE_ALT_SCREEN_FULL_REPAINT', raising=False)
    env = _env_terminal()
    assert 'CLAUDE_CODE_ALT_SCREEN_FULL_REPAINT' not in env
