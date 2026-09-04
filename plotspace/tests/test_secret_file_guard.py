"""
Guard de secretos del API de archivos (hallazgo CRÍTICO de la auditoría).

Cuando el repo de Jarvis está registrado como proyecto navegable, su
data/jarvis_token.txt y plotspace/.env quedaban DENTRO del proyecto y el editor
los servía (read/raw/stat/search) → fuga del token de sesión y de la API key.
Estos tests reproducen el vector y exigen 403 / exclusión.

Patrón: harness con DB temporal + proyecto apuntando a un dir real.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plotspace.tests._harness import fresh_db, make_client_and_project
import plotspace.routers.projects_files as pf


def _proyecto_con(archivos: dict):
    """Crea un dir temporal con {ruta_rel: contenido} y lo registra como proyecto."""
    fresh_db()
    d = tempfile.mkdtemp(prefix="jarvis_secguard_")
    for rel, contenido in archivos.items():
        full = os.path.join(d, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, 'w', encoding='utf-8') as f:
            f.write(contenido)
    client, pid = make_client_and_project(d)
    return client, pid


def test_token_por_nombre_no_se_lee():
    client, pid = _proyecto_con({'data/jarvis_token.txt': 'SECRETO-123', 'ok.txt': 'hola'})
    assert client.get(f'/api/projects/{pid}/files/read?path=data/jarvis_token.txt').status_code == 403
    assert client.get(f'/api/projects/{pid}/files/raw?path=data/jarvis_token.txt').status_code == 403
    assert client.get(f'/api/projects/{pid}/files/stat?path=data/jarvis_token.txt').status_code == 403
    # un archivo normal sí se lee (no rompimos el editor)
    r = client.get(f'/api/projects/{pid}/files/read?path=ok.txt')
    assert r.status_code == 200 and r.json().get('content') == 'hola'


def test_env_no_se_lee_en_read():
    # El guard de .env existía en /raw pero faltaba en /read (hueco real).
    client, pid = _proyecto_con({'plotspace/.env': 'ANTHROPIC_API_KEY=sk-secreto'})
    assert client.get(f'/api/projects/{pid}/files/read?path=plotspace/.env').status_code == 403


def test_busqueda_no_devuelve_el_token():
    client, pid = _proyecto_con({
        'data/jarvis_token.txt': 'TOKENSECRETO',
        'telegram.json': '{"token":"TOKENSECRETO"}',
        'codigo.py': '# TOKENSECRETO aparece acá tambien\n',
    })
    r = client.get(f'/api/projects/{pid}/files/search?q=TOKENSECRETO')
    assert r.status_code == 200
    rutas = [x.get('path') for x in r.json().get('results', [])]
    assert 'data/jarvis_token.txt' not in rutas
    assert 'telegram.json' not in rutas
    # el archivo de código legítimo sí puede aparecer
    # (no afirmamos que aparezca para no acoplar al motor; sí que el secreto NO)


def test_repo_de_jarvis_como_proyecto_no_filtra_token():
    # El caso EXACTO de la auditoría: proyecto cuyo dir ES el repo de Jarvis.
    fresh_db()
    raiz = pf._JARVIS_ROOT
    if not os.path.isfile(os.path.join(raiz, 'data', 'jarvis_token.txt')):
        return  # entorno sin token persistido: nada que filtrar
    client, pid = make_client_and_project(raiz)
    assert client.get(f'/api/projects/{pid}/files/read?path=data/jarvis_token.txt').status_code == 403
    assert client.get(f'/api/projects/{pid}/files/raw?path=data/jarvis_token.txt').status_code == 403


def test_save_no_sobreescribe_secretos():
    client, pid = _proyecto_con({'data/jarvis_token.txt': 'ORIGINAL'})
    r = client.post(f'/api/projects/{pid}/files/save',
                    json={'path': 'data/jarvis_token.txt', 'content': 'PWNED'})
    assert r.status_code == 403


def test_rename_no_exfiltra_secreto_por_nombre():
    # Bypass de la 2ª pasada: renombrar el secreto a otro nombre para leerlo luego.
    client, pid = _proyecto_con({'data/jarvis_token.txt': 'SECRETO'})
    r = client.post(f'/api/projects/{pid}/files/rename',
                    json={'src': 'data/jarvis_token.txt', 'dst': 'robado.txt'})
    assert r.status_code == 403


def test_mkdir_no_crea_dentro_de_data_del_repo():
    raiz = pf._JARVIS_ROOT
    if not os.path.isdir(os.path.join(raiz, 'data')):
        return
    fresh_db()
    client, pid = make_client_and_project(raiz)
    r = client.post(f'/api/projects/{pid}/files/mkdir', json={'path': 'data/pwn'})
    assert r.status_code == 403


def test_repo_como_proyecto_rename_de_cookies_bloqueado():
    # El vector EXACTO reportado: mover data/browser_profile/.../Cookies fuera de
    # data/ para servirlo por /raw. Debe dar 403 por realpath.
    raiz = pf._JARVIS_ROOT
    cookies = os.path.join(raiz, 'data', 'browser_profile', 'Default', 'Cookies')
    fresh_db()
    client, pid = make_client_and_project(raiz)
    # cualquier path dentro de data/ debe rechazarse aunque su basename no sea conocido
    r = client.post(f'/api/projects/{pid}/files/rename',
                    json={'src': 'data/browser_profile/Default/Cookies', 'dst': 'robado.db'})
    assert r.status_code in (403, 404)   # 403 (guard) — 404 solo si el archivo no existe en este entorno
    if os.path.isfile(cookies):
        assert r.status_code == 403


def test_delete_secreto_bloqueado():
    client, pid = _proyecto_con({'data/jarvis_token.txt': 'x'})
    r = client.request('DELETE', f'/api/projects/{pid}/files',
                       params={'path': 'data/jarvis_token.txt'})
    assert r.status_code == 403


def test_invariante_es_servible():
    # El invariante que usan TODOS los endpoints (read/save/upload/rename/delete):
    # bloquea data/ y plotspace/.env del repo de Jarvis por realpath; permite el
    # data/ de CUALQUIER OTRO proyecto.
    assert pf._es_servible(os.path.join(pf._JARVIS_DATA, 'x.txt')) is False
    assert pf._es_servible(os.path.join(pf._JARVIS_DATA, 'browser_profile', 'Default', 'Cookies')) is False
    assert pf._es_servible(pf._JARVIS_ENV) is False
    assert pf._es_servible('/tmp/otro_proyecto/data/x.txt') is True
    assert pf._es_servible('/tmp/otro_proyecto/src/app.py') is True


if __name__ == '__main__':
    import traceback
    fallos = 0
    for nombre, fn in sorted(globals().items()):
        if nombre.startswith('test_') and callable(fn):
            try:
                fn(); print(f'ok  {nombre}')
            except Exception:
                fallos += 1; print(f'FAIL {nombre}'); traceback.print_exc()
    sys.exit(1 if fallos else 0)
