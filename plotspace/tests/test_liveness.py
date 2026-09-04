# plotspace/tests/test_liveness.py
"""Liveness del enjambre: distinguir un agente VIVO de un cadáver que figura vivo.

EL BUG QUE MATA
---------------
`terminals.activa` solo baja con la ✕ explícita del usuario. Si el CLI se muere
adentro del pane (crash, /exit, rate-limit), la fila queda `activa = 1` PARA
SIEMPRE y el reconcile del arranque hasta le resucita la sesión tmux. Para el
resto del enjambre ese muerto es indistinguible de un agente idle:

  · le respetan el territorio (hasta 30 min de TTL) y le piden permiso al vacío;
  · el guard de commits bloquea en nombre de un fantasma;
  · le tipean el digest del mailbox adentro de un bash;
  · y —lo peor— le esperan commits que ya nadie va a hacer.

DOS FORMAS DE ESTAR MUERTO
--------------------------
  'caido'      la sesión tmux vive pero el pane cayó al SHELL: el CLI salió.
  'sin_sesion' no hay sesión tmux: se la llevaron por abajo.

FALLA ABIERTA, SIEMPRE. Sin dato no se inventa un muerto: declarar difunto a un
agente vivo es peor que tardar en enterrar a uno muerto (le liberaríamos el
territorio y otro le pisaría el trabajo en curso).
"""
from plotspace.core import liveness


# ─── Resolución pura ──────────────────────────────────────────────────────────

def test_el_que_trabaja_esta_vivo_aunque_no_sepamos_del_pane():
    assert liveness.resolver('trabajando', 'claude', '', False) == 'trabajando'


def test_cli_de_ia_con_el_pane_en_bash_es_un_caido():
    assert liveness.resolver('idle', 'claude', 'bash', True) == 'caido'
    assert liveness.resolver('idle', 'codex', 'zsh', True) == 'caido'


def test_cli_de_ia_corriendo_su_proceso_esta_idle():
    assert liveness.resolver('idle', 'claude', 'node', True) == 'idle'
    assert liveness.resolver('idle', 'codex', 'python', True) == 'idle'


def test_sin_sesion_tmux_es_muerte_aunque_la_db_diga_activa():
    assert liveness.resolver('idle', 'claude', '', False) == 'sin_sesion'


def test_una_terminal_shell_en_bash_no_es_un_caido():
    """El tipo 'shell'/manual ES un bash: marcarlo caído sería un falso positivo
    permanente sobre las terminales que el usuario abre para él mismo."""
    assert liveness.resolver('idle', 'shell', 'bash', True) == 'idle'
    assert liveness.resolver('idle', None, 'bash', True) == 'idle'


def test_sin_dato_del_pane_no_se_declara_muerto_a_nadie():
    """Falla abierta: `tmux list-panes` puede fallar y no por eso hay una masacre."""
    assert liveness.resolver('idle', 'claude', '', True) == 'idle'


def test_vivo_distingue_las_dos_muertes_de_los_dos_estados_sanos():
    assert liveness.vivo('trabajando') and liveness.vivo('idle')
    assert not liveness.vivo('caido')
    assert not liveness.vivo('sin_sesion')


# ─── Lectura del snapshot de tmux (un solo fork para TODO el enjambre) ────────

def test_parsea_el_listado_de_panes():
    salida = 'jarvis_441\tnode\njarvis_442\tbash\nddhp-web\tvim\n'
    assert liveness.parsear_panes(salida) == {441: 'node', 442: 'bash'}


def test_ignora_sesiones_que_no_son_de_jarvis():
    assert liveness.parsear_panes('otra-cosa\tnode\n') == {}


def test_salida_vacia_o_basura_no_rompe():
    for basura in ('', None, 'sin tabs', 'jarvis_x\tnode'):
        assert liveness.parsear_panes(basura) == {}


def test_la_primera_ventana_gana_si_una_sesion_tiene_varios_panes():
    """Una sesión con varios panes: nos interesa el primero (el del CLI)."""
    assert liveness.parsear_panes('jarvis_1\tnode\njarvis_1\tbash\n') == {1: 'node'}


# ─── Estado de todo el enjambre de una ─────────────────────────────────────────

def test_estados_resuelve_cada_terminal_con_su_tipo_y_fase():
    terminales = [{'id': 1, 'tipo_ia': 'claude'}, {'id': 2, 'tipo_ia': 'claude'},
                  {'id': 3, 'tipo_ia': 'claude'}]
    panes = {1: 'node', 2: 'bash'}            # 3 no aparece: sin sesión
    r = liveness.estados(terminales, {1: 'trabajando'}, panes)
    assert r == {1: 'trabajando', 2: 'caido', 3: 'sin_sesion'}


def test_estados_sin_panes_no_mata_a_nadie():
    """Si el fork de tmux falló (panes None) NADIE se declara muerto."""
    terminales = [{'id': 1, 'tipo_ia': 'claude'}, {'id': 2, 'tipo_ia': 'claude'}]
    r = liveness.estados(terminales, {}, None)
    assert r == {1: 'idle', 2: 'idle'}


def test_estados_tolera_terminales_con_forma_rara():
    assert isinstance(liveness.estados([{}, None, {'id': 5}], {}, {}), dict)


# ─── El falso positivo del arranque ───────────────────────────────────────────
# Entre que el server levanta y que reconciliar_sesiones_tmux recrea las
# sesiones, TODAS las terminales están legítimamente sin sesión. Enterrarlas ahí
# liberaría su territorio y dejaría commitear encima de agentes que vuelven en
# dos segundos.

def test_sin_reconcile_la_ausencia_de_sesion_no_mata():
    terminales = [{'id': 1, 'tipo_ia': 'claude'}]
    r = liveness.estados(terminales, {}, {99: 'node'}, permitir_sin_sesion=False)
    assert r == {1: 'idle'}


def test_pero_un_caido_se_detecta_igual_durante_el_arranque():
    """'caido' exige una sesión VIVA con el pane en un shell: no tiene el falso
    positivo del arranque, así que no hay motivo para suprimirlo."""
    terminales = [{'id': 1, 'tipo_ia': 'claude'}]
    r = liveness.estados(terminales, {}, {1: 'bash'}, permitir_sin_sesion=False)
    assert r == {1: 'caido'}


def test_estados_ahora_no_entierra_a_nadie_si_tmux_no_reporto_sesiones(monkeypatch):
    """tmux sin ninguna sesión de Jarvis = tmux se reinició, no una masacre."""
    monkeypatch.setattr(liveness, 'panes_ahora', lambda *a, **k: {})
    terminales = [{'id': 1, 'tipo_ia': 'claude'}, {'id': 2, 'tipo_ia': 'claude'}]
    assert liveness.estados_ahora(terminales, {}) == {1: 'idle', 2: 'idle'}
