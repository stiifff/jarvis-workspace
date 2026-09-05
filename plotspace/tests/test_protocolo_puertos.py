"""
Test: protocolo de puertos inyectado en el CLAUDE.md de cada proyecto.

La regla: el puerto 3000 es de Jarvis Workspace — ningún agente puede
levantar nada ahí, y antes de levantar cualquier servidor hay que listar
los puertos ocupados. Vive en plotspace/core/puertos.py y se inyecta entre
markers JARVIS_PUERTOS_* (mismo patrón idempotente que mailbox/memoria).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plotspace.core.puertos import (
    PROTOCOLO,
    PROTOCOLO_MARKER_START,
    PROTOCOLO_MARKER_END,
    asegurar_protocolo_puertos,
)


def _leer(tmp_path):
    with open(os.path.join(tmp_path, 'CLAUDE.md'), encoding='utf-8') as f:
        return f.read()


def test_protocolo_menciona_la_regla():
    assert '3000' in PROTOCOLO
    assert 'FORBIDDEN' in PROTOCOLO
    assert 'ss -tlnp' in PROTOCOLO
    assert PROTOCOLO.startswith(PROTOCOLO_MARKER_START)
    assert PROTOCOLO.endswith(PROTOCOLO_MARKER_END)


def test_inyecta_en_claude_md_inexistente(tmp_path):
    asegurar_protocolo_puertos(str(tmp_path))
    contenido = _leer(str(tmp_path))
    assert PROTOCOLO in contenido


def test_inyecta_preservando_contenido_previo(tmp_path):
    previo = '# Mi proyecto\n\nInstrucciones del usuario.\n'
    with open(os.path.join(str(tmp_path), 'CLAUDE.md'), 'w', encoding='utf-8') as f:
        f.write(previo)
    asegurar_protocolo_puertos(str(tmp_path))
    contenido = _leer(str(tmp_path))
    assert contenido.startswith(previo.rstrip('\n'))
    assert PROTOCOLO in contenido


def test_idempotente_no_duplica(tmp_path):
    asegurar_protocolo_puertos(str(tmp_path))
    asegurar_protocolo_puertos(str(tmp_path))
    contenido = _leer(str(tmp_path))
    assert contenido.count(PROTOCOLO_MARKER_START) == 1
    assert contenido.count(PROTOCOLO_MARKER_END) == 1


def test_regenera_bloque_viejo_entre_markers(tmp_path):
    # Simula una versión vieja del protocolo: debe ser reemplazada, no acumulada
    viejo = f'# Proyecto\n\n{PROTOCOLO_MARKER_START}\nregla vieja\n{PROTOCOLO_MARKER_END}\n'
    with open(os.path.join(str(tmp_path), 'CLAUDE.md'), 'w', encoding='utf-8') as f:
        f.write(viejo)
    asegurar_protocolo_puertos(str(tmp_path))
    contenido = _leer(str(tmp_path))
    assert 'regla vieja' not in contenido
    assert PROTOCOLO in contenido
    assert contenido.count(PROTOCOLO_MARKER_START) == 1


# ─── Matar el server de un puerto (✕ del pill de preview) ────────────────────
from plotspace.core.puertos import parse_pids_puerto, matar_puerto, PUERTO_JARVIS

_SS = """State  Recv-Q Send-Q Local Address:Port  Peer Address:Port Process
LISTEN 0      4096   127.0.0.1:5050      0.0.0.0:*         users:(("python3",pid=4321,fd=3))
LISTEN 0      511    0.0.0.0:3000        0.0.0.0:*         users:(("uvicorn",pid=99,fd=7))
LISTEN 0      128    127.0.0.1:50500     0.0.0.0:*         users:(("node",pid=777,fd=9))
"""

def test_parse_pids_puerto_exacto():
    assert parse_pids_puerto(_SS, 5050) == {4321}
    assert parse_pids_puerto(_SS, 3000) == {99}
    # :5050 NO debe matchear a :50500 (word boundary)
    assert parse_pids_puerto(_SS, 50500) == {777}
    assert parse_pids_puerto(_SS, 9999) == set()
    assert parse_pids_puerto('', 5050) == set()

def test_matar_puerto_nunca_jarvis():
    r = matar_puerto(PUERTO_JARVIS)   # 3000
    assert r['ok'] is False and not r['pids'] and '3000' in r['motivo']

def test_matar_puerto_invalido():
    assert matar_puerto('abc')['ok'] is False
    assert matar_puerto(None)['ok'] is False

def test_matar_puerto_sin_proceso():
    # Puerto altísimo, nada escuchando → ok False sin reventar.
    r = matar_puerto(59321)
    assert r['ok'] is False and r['pids'] == []
