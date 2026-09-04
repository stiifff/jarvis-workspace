# plotspace/tests/test_review_by_agent.py
"""Review de diffs POR-AGENTE (plotspace/routers/review.py).

Dos capas:
  - lógica PURA de atribución archivo→agente (sin git ni DB ni snapshot real)
  - los dos endpoints HTTP vía TestClient sobre un repo git temporal.
La fuente de atribución (snapshot de agent_live) se inyecta por el seam
`review._duenos_para` (monkeypatch), así el test del endpoint no necesita tmux.
"""
import os
import subprocess
import sys
import tempfile

# Imports absolutos 'plotspace.*' al correr el test como script suelto.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from fastapi import FastAPI
from fastapi.testclient import TestClient

from plotspace.tests._harness import fresh_db, make_client_and_project
from plotspace.routers import review


# ─── lógica pura: atribuir_cambios ────────────────────────────────────────────

def test_atribuir_agrupa_por_dueno():
    cambios = [
        {'path': 'a.py', 'status': 'M', 'diff': 'd1'},
        {'path': 'b.py', 'status': 'M', 'diff': 'd2'},
        {'path': 'c.py', 'status': '??', 'diff': 'd3'},
    ]
    duenos = [
        {'terminal_id': 1, 'nombre': 'Backend', 'archivos': ['a.py']},
        {'terminal_id': 2, 'nombre': 'Frontend', 'archivos': ['b.py']},
    ]
    out = review.atribuir_cambios(cambios, duenos)
    assert [a['terminal_id'] for a in out['agentes']] == [1, 2]
    assert out['agentes'][0]['nombre'] == 'Backend'
    assert out['agentes'][0]['archivos'] == [{'path': 'a.py', 'status': 'M', 'diff': 'd1'}]
    assert out['agentes'][1]['archivos'] == [{'path': 'b.py', 'status': 'M', 'diff': 'd2'}]
    # c.py no tiene dueño → sin_atribuir (preserva el dict completo)
    assert out['sin_atribuir'] == [{'path': 'c.py', 'status': '??', 'diff': 'd3'}]
    print('  atribuir agrupa por dueño OK')


def test_atribuir_omite_agentes_sin_cambios():
    # El agente 2 es dueño de cosas pero NINGUNA cambió → no aparece.
    cambios = [{'path': 'a.py', 'status': 'M'}]
    duenos = [
        {'terminal_id': 1, 'nombre': 'A', 'archivos': ['a.py']},
        {'terminal_id': 2, 'nombre': 'B', 'archivos': ['x.py', 'y.py']},
    ]
    out = review.atribuir_cambios(cambios, duenos)
    assert [a['terminal_id'] for a in out['agentes']] == [1]
    assert out['sin_atribuir'] == []
    print('  omite agentes sin cambios reales OK')


def test_atribuir_normaliza_prefijo_punto_barra():
    # git puede dar 'a.py' y agent_live './a.py' (o viceversa): mismo archivo.
    cambios = [{'path': 'a.py', 'status': 'M'}]
    duenos = [{'terminal_id': 7, 'nombre': 'X', 'archivos': ['./a.py']}]
    out = review.atribuir_cambios(cambios, duenos)
    assert len(out['agentes']) == 1
    assert out['agentes'][0]['terminal_id'] == 7
    assert out['sin_atribuir'] == []
    print('  normaliza ./ OK')


def test_atribuir_sin_duenos_todo_sin_atribuir():
    cambios = [{'path': 'a.py', 'status': 'M'}, {'path': 'b.py', 'status': 'A'}]
    out = review.atribuir_cambios(cambios, [])
    assert out['agentes'] == []
    assert out['sin_atribuir'] == cambios
    print('  sin dueños → todo sin_atribuir OK')


def test_atribuir_varios_archivos_mismo_dueno_orden():
    cambios = [
        {'path': 'a.py', 'status': 'M'},
        {'path': 'z.py', 'status': 'A'},
        {'path': 'm.py', 'status': 'M'},
    ]
    duenos = [{'terminal_id': 3, 'nombre': 'Solo', 'archivos': ['m.py', 'a.py', 'z.py']}]
    out = review.atribuir_cambios(cambios, duenos)
    assert len(out['agentes']) == 1
    # preserva el orden de los CAMBIOS, no el del dueño
    assert [f['path'] for f in out['agentes'][0]['archivos']] == ['a.py', 'z.py', 'm.py']
    print('  orden por aparición de cambios OK')


# ─── duenos_desde_snapshot: snapshot de agent_live → mapeo dueño ──────────────

def test_duenos_desde_snapshot_solo_archivos_con_dueno():
    snap = {
        'agentes': [
            {'terminal_id': 1, 'nombre': 'Backend', 'archivos': [
                {'path': 'a.py', 'dueno': True},
                {'path': 'leido.py', 'dueno': False},   # solo leído, no es dueño
            ]},
            {'terminal_id': 2, 'nombre': 'Frontend', 'archivos': [
                {'path': 'b.css', 'dueno': True},
            ]},
        ],
    }
    duenos = review.duenos_desde_snapshot(snap)
    assert duenos == [
        {'terminal_id': 1, 'nombre': 'Backend', 'archivos': ['a.py']},
        {'terminal_id': 2, 'nombre': 'Frontend', 'archivos': ['b.css']},
    ]
    print('  duenos_desde_snapshot filtra dueno=True OK')


# ─── helpers de repo git temporal ─────────────────────────────────────────────

def _git(cwd, *args):
    subprocess.run(['git', *args], cwd=cwd, check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _init_repo(d):
    _git(d, 'init', '-q')
    _git(d, 'config', 'user.email', 'test@jarvis.local')
    _git(d, 'config', 'user.name', 'Test')
    with open(os.path.join(d, 'a.txt'), 'w', encoding='utf-8') as f:
        f.write('uno\n')
    with open(os.path.join(d, 'b.txt'), 'w', encoding='utf-8') as f:
        f.write('dos\n')
    _git(d, 'add', 'a.txt', 'b.txt')
    _git(d, 'commit', '-q', '-m', 'init')


def _client_repo():
    fresh_db()
    d = tempfile.mkdtemp()
    _init_repo(d)
    app = FastAPI()
    app.include_router(review.router)
    # reusar el harness para insertar el proyecto + obtener pid
    _, pid = make_client_and_project(d)
    return TestClient(app), pid, d


# ─── GET /review/by-agent ─────────────────────────────────────────────────────

def test_by_agent_agrupa_y_deja_sin_atribuir():
    client, pid, d = _client_repo()
    # a.txt modificado (dueño Backend), b.txt modificado (sin dueño), u.txt untracked
    with open(os.path.join(d, 'a.txt'), 'w', encoding='utf-8') as f:
        f.write('uno cambiado\n')
    with open(os.path.join(d, 'b.txt'), 'w', encoding='utf-8') as f:
        f.write('dos cambiado\n')
    with open(os.path.join(d, 'u.txt'), 'w', encoding='utf-8') as f:
        f.write('nuevo\n')

    orig = review._duenos_para
    review._duenos_para = lambda project_id: [
        {'terminal_id': 11, 'nombre': 'Backend', 'archivos': ['a.txt']},
    ]
    try:
        r = client.get(f"/api/projects/{pid}/review/by-agent")
    finally:
        review._duenos_para = orig

    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data['agentes']) == 1
    ag = data['agentes'][0]
    assert ag['terminal_id'] == 11 and ag['nombre'] == 'Backend'
    assert [f['path'] for f in ag['archivos']] == ['a.txt']
    assert ag['archivos'][0]['status'] == 'M'
    assert 'uno cambiado' in ag['archivos'][0]['diff']
    # b.txt (M, sin dueño) y u.txt (??) en sin_atribuir
    sin = {f['path']: f for f in data['sin_atribuir']}
    assert set(sin) == {'b.txt', 'u.txt'}
    assert sin['b.txt']['status'] == 'M'
    assert sin['u.txt']['status'] == '??'
    assert 'nuevo' in sin['u.txt']['diff']
    print('  by-agent agrupa + sin_atribuir OK')


def test_by_agent_limpio_devuelve_vacio():
    client, pid, d = _client_repo()
    orig = review._duenos_para
    review._duenos_para = lambda project_id: []
    try:
        r = client.get(f"/api/projects/{pid}/review/by-agent")
    finally:
        review._duenos_para = orig
    assert r.status_code == 200, r.text
    data = r.json()
    assert data['agentes'] == []
    assert data['sin_atribuir'] == []
    print('  by-agent repo limpio OK')


def test_by_agent_proyecto_inexistente_404():
    client, _, _ = _client_repo()
    r = client.get("/api/projects/99999/review/by-agent")
    assert r.status_code == 404, r.text
    print('  by-agent 404 OK')


def test_by_agent_no_repo_400():
    fresh_db()
    d = tempfile.mkdtemp()   # sin git init
    app = FastAPI()
    app.include_router(review.router)
    _, pid = make_client_and_project(d)
    client = TestClient(app)
    r = client.get(f"/api/projects/{pid}/review/by-agent")
    assert r.status_code == 400, r.text
    print('  by-agent no-repo 400 OK')


# ─── POST /review/commit ──────────────────────────────────────────────────────

def test_commit_explicito_ok():
    client, pid, d = _client_repo()
    with open(os.path.join(d, 'a.txt'), 'w', encoding='utf-8') as f:
        f.write('cambio para commitear\n')
    with open(os.path.join(d, 'b.txt'), 'w', encoding='utf-8') as f:
        f.write('NO commitear esto\n')   # debe quedar fuera

    r = client.post(f"/api/projects/{pid}/review/commit",
                    json={'archivos': ['a.txt'], 'mensaje': 'feat: test commit'})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data['ok'] is True, data
    assert data['commit'], data

    # el commit existe y SOLO tocó a.txt
    log = subprocess.run(['git', 'log', '-1', '--name-only', '--format=%s'],
                         cwd=d, capture_output=True, text=True).stdout
    assert 'feat: test commit' in log
    assert 'a.txt' in log
    assert 'b.txt' not in log
    # b.txt sigue modificado en el working tree (no se barrió)
    st = subprocess.run(['git', 'status', '--porcelain'], cwd=d,
                        capture_output=True, text=True).stdout
    assert 'b.txt' in st
    print('  commit explícito solo a.txt OK')


def test_commit_path_traversal_rechazado():
    client, pid, d = _client_repo()
    r = client.post(f"/api/projects/{pid}/review/commit",
                    json={'archivos': ['../escape.txt'], 'mensaje': 'x'})
    assert r.status_code == 400, r.text
    print('  commit traversal 400 OK')


def test_commit_sin_archivos_400():
    client, pid, d = _client_repo()
    r = client.post(f"/api/projects/{pid}/review/commit",
                    json={'archivos': [], 'mensaje': 'x'})
    assert r.status_code == 400, r.text
    print('  commit sin archivos 400 OK')


def test_commit_sin_mensaje_400():
    client, pid, d = _client_repo()
    r = client.post(f"/api/projects/{pid}/review/commit",
                    json={'archivos': ['a.txt'], 'mensaje': '   '})
    assert r.status_code == 400, r.text
    print('  commit sin mensaje 400 OK')


def test_commit_nada_que_commitear_ok_false():
    client, pid, d = _client_repo()
    # a.txt sin cambios → git no tiene nada que commitear
    r = client.post(f"/api/projects/{pid}/review/commit",
                    json={'archivos': ['a.txt'], 'mensaje': 'feat: nada'})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data['ok'] is False, data
    assert 'error' in data
    print('  commit nada que commitear ok:false OK')


if __name__ == '__main__':
    test_atribuir_agrupa_por_dueno()
    test_atribuir_omite_agentes_sin_cambios()
    test_atribuir_normaliza_prefijo_punto_barra()
    test_atribuir_sin_duenos_todo_sin_atribuir()
    test_atribuir_varios_archivos_mismo_dueno_orden()
    test_duenos_desde_snapshot_solo_archivos_con_dueno()
    test_by_agent_agrupa_y_deja_sin_atribuir()
    test_by_agent_limpio_devuelve_vacio()
    test_by_agent_proyecto_inexistente_404()
    test_by_agent_no_repo_400()
    test_commit_explicito_ok()
    test_commit_path_traversal_rechazado()
    test_commit_sin_archivos_400()
    test_commit_sin_mensaje_400()
    test_commit_nada_que_commitear_ok_false()
    print('OK')
