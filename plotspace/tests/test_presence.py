"""
Test: Discord Rich Presence (plotspace/routers/system.py).

La tarjeta "Jugando Jarvis" de Discord la ARMA este backend (GET
/api/system/presence: details/state ya formateados, bilingüe ES/EN + conteo de
agentes vivos) y la EMPUJA al IPC de Discord el lanzador Jarvis.exe
(scripts/jarvis-shell.cs — el pipe discord-ipc-N vive en Windows y WSL no lo
alcanza).
Acá se prueba la lógica PURA de formateo + el estado en memoria que el frontend
reporta con POST /presence/state. La conexión IPC vive fuera de pytest.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plotspace.core import agent_watch
from plotspace.routers import system


# ─── Sección (línea 1: "In Settings" / "En Ajustes") ─────────────────────────

def test_formatear_seccion_en():
    assert system.formatear_seccion('settings', 'en') == 'In Settings'
    assert system.formatear_seccion('terminals', 'en') == 'In Terminals'


def test_formatear_seccion_es():
    assert system.formatear_seccion('settings', 'es') == 'En Ajustes'
    assert system.formatear_seccion('terminals', 'es') == 'En Terminales'
    assert system.formatear_seccion('review', 'es') == 'En Revisión'


def test_formatear_seccion_desconocida_cae_a_jarvis():
    # None (recién booteado, sin reporte) o clave inexistente → Jarvis.
    assert system.formatear_seccion(None, 'en') == 'In Jarvis'
    assert system.formatear_seccion('inexistente', 'es') == 'En Jarvis'


# ─── Estado (línea 2: conteo de agentes, bilingüe) ───────────────────────────

def test_formatear_estado_con_trabajando():
    assert system.formatear_estado(3, 1, 12, 'en') == '3 agents · 1 working (3 of 12)'
    assert system.formatear_estado(3, 1, 12, 'es') == '3 agentes · 1 trabajando (3 de 12)'


def test_formatear_estado_singular():
    assert system.formatear_estado(1, 0, 12, 'en') == '1 agent (1 of 12)'
    assert system.formatear_estado(1, 1, 12, 'es') == '1 agente · 1 trabajando (1 de 12)'


def test_formatear_estado_sin_trabajando_omite_clausula():
    # Nadie trabajando → no ensuciar con "· 0 working".
    assert system.formatear_estado(2, 0, 12, 'en') == '2 agents (2 of 12)'
    assert system.formatear_estado(2, 0, 12, 'es') == '2 agentes (2 de 12)'


def test_formatear_estado_sin_agentes():
    assert system.formatear_estado(0, 0, 12, 'en') == 'Idle — no agents'
    assert system.formatear_estado(0, 0, 12, 'es') == 'Inactivo — sin agentes'


# ─── Conteo de agentes (activos en DB + trabajando según agent_watch) ────────

def test_conteo_agentes_sin_proyecto():
    assert system._conteo_agentes(None) == (0, 0)


def test_conteo_agentes(monkeypatch):
    monkeypatch.setattr(system, '_terminales_activas_de', lambda pid: {10, 11, 12})
    monkeypatch.setattr(agent_watch, '_estados', {
        10: {'fase': 'trabajando'},
        11: {'fase': 'idle'},
        12: {'fase': 'trabajando'},
    })
    assert system._conteo_agentes(5) == (3, 2)


# ─── Estado en memoria que reporta el frontend (POST /presence/state) ────────

def test_set_presence_normaliza():
    system._set_presence({'seccion': 'settings', 'locale': 'en',
                          'project_id': '7', 'proyecto': 'mi-app'})
    st = system._PRESENCE
    assert st['seccion'] == 'settings'
    assert st['locale'] == 'en'
    assert st['project_id'] == 7          # '7' string → int
    assert st['proyecto'] == 'mi-app'


def test_set_presence_locale_desconocido_default_es():
    system._set_presence({'seccion': 'terminals', 'locale': 'xx', 'project_id': None})
    assert system._PRESENCE['locale'] == 'es'
    assert system._PRESENCE['project_id'] is None


def test_set_presence_project_id_no_numerico_es_none():
    system._set_presence({'seccion': 't', 'project_id': 'abc'})
    assert system._PRESENCE['project_id'] is None
    # bool no debe colarse como int (True == 1)
    system._set_presence({'seccion': 't', 'project_id': True})
    assert system._PRESENCE['project_id'] is None


# ─── Payload final que consume el shell (GET /presence) ──────────────────────

def test_payload_presence_forma(monkeypatch):
    monkeypatch.setattr(system, '_conteo_agentes', lambda pid: (3, 1))
    monkeypatch.setattr(system, '_max_terminales', lambda: 12)
    system._set_presence({'seccion': 'settings', 'locale': 'en',
                          'project_id': 5, 'proyecto': 'x'})
    p = system._payload_presence()
    assert p['app'] == 'Jarvis'
    assert p['details'] == 'In Settings'
    assert p['state'] == '3 agents · 1 working (3 of 12)'
    assert p['large_image'] == 'plotspace-icon-1024'   # la key real del Portal
    assert p['large_text'] == 'Jarvis'
    assert p['small_text'] == '1 working'
    assert p['agentes_activos'] == 3 and p['agentes_trabajando'] == 1
    assert p['max'] == 12


def test_payload_presence_dot_off_por_defecto(monkeypatch):
    # Dot apagado por ahora (default vacío) → small_image vacío: Discord no
    # muestra mini-icono, pero el resto de la tarjeta va igual.
    monkeypatch.setattr(system, '_conteo_agentes', lambda pid: (3, 1))
    system._set_presence({'seccion': 'settings', 'locale': 'en', 'project_id': 5})
    assert system._payload_presence()['small_image'] == ''


def test_payload_presence_dot_on_si_hay_assets(monkeypatch):
    # Prendible por env → verde si alguien trabaja, gris en reposo.
    monkeypatch.setattr(system, '_PRESENCE_DOT_ON', 'dot_verde')
    monkeypatch.setattr(system, '_PRESENCE_DOT_OFF', 'dot_gris')
    monkeypatch.setattr(system, '_conteo_agentes', lambda pid: (3, 1))
    system._set_presence({'seccion': 'settings', 'locale': 'en', 'project_id': 5})
    assert system._payload_presence()['small_image'] == 'dot_verde'
    monkeypatch.setattr(system, '_conteo_agentes', lambda pid: (2, 0))
    assert system._payload_presence()['small_image'] == 'dot_gris'


def test_payload_presence_idle_sin_agentes(monkeypatch):
    monkeypatch.setattr(system, '_conteo_agentes', lambda pid: (0, 0))
    monkeypatch.setattr(system, '_max_terminales', lambda: 12)
    system._set_presence({'seccion': 'terminals', 'locale': 'es', 'project_id': 5})
    p = system._payload_presence()
    assert p['small_text'] == 'Inactivo'
    assert p['state'] == 'Inactivo — sin agentes'
    assert p['details'] == 'En Terminales'
