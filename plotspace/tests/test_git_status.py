# plotspace/tests/test_git_status.py
import os
import subprocess
import sys
import tempfile

# Asegurar imports absolutos 'plotspace.*' al correr el test como script suelto.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from plotspace.tests._harness import fresh_db, make_client_and_project


def _git(cwd, *args):
    subprocess.run(
        ['git', *args],
        cwd=cwd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _init_repo(d):
    _git(d, 'init', '-q')
    _git(d, 'config', 'user.email', 'test@jarvis.local')
    _git(d, 'config', 'user.name', 'Test')
    with open(os.path.join(d, 'a.txt'), 'w', encoding='utf-8') as f:
        f.write('hola\n')
    _git(d, 'add', 'a.txt')
    _git(d, 'commit', '-q', '-m', 'init')


def test_repo_archivo_modificado():
    fresh_db()
    d = tempfile.mkdtemp()
    _init_repo(d)
    # modificar el archivo committeado
    with open(os.path.join(d, 'a.txt'), 'w', encoding='utf-8') as f:
        f.write('hola mundo\n')

    client, pid = make_client_and_project(d)
    r = client.get(f"/api/projects/{pid}/files/git-status")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data['git'] is True, data
    assert data['files'].get('a.txt') == 'M', data
    print('  repo modificado -> M OK')


def test_archivo_nuevo_untracked():
    fresh_db()
    d = tempfile.mkdtemp()
    _init_repo(d)
    with open(os.path.join(d, 'nuevo.txt'), 'w', encoding='utf-8') as f:
        f.write('x\n')

    client, pid = make_client_and_project(d)
    data = client.get(f"/api/projects/{pid}/files/git-status").json()
    assert data['git'] is True, data
    assert data['files'].get('nuevo.txt') == 'U', data
    print('  untracked -> U OK')


def test_dir_no_repo():
    fresh_db()
    d = tempfile.mkdtemp()
    client, pid = make_client_and_project(d)
    r = client.get(f"/api/projects/{pid}/files/git-status")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data['git'] is False, data
    print('  no-repo -> git:false OK')


def test_rename_consume_dos_registros():
    fresh_db()
    d = tempfile.mkdtemp()
    _init_repo(d)
    # agregar un segundo archivo committeado que luego modificaremos
    with open(os.path.join(d, 'z.txt'), 'w', encoding='utf-8') as f:
        f.write('z\n')
    _git(d, 'add', 'z.txt')
    _git(d, 'commit', '-q', '-m', 'z')
    # rename a.txt -> b.txt (staged) y modificar z.txt
    _git(d, 'mv', 'a.txt', 'b.txt')
    with open(os.path.join(d, 'z.txt'), 'w', encoding='utf-8') as f:
        f.write('z modificado\n')

    client, pid = make_client_and_project(d)
    data = client.get(f"/api/projects/{pid}/files/git-status").json()
    assert data['git'] is True, data
    assert data['files'].get('b.txt') == 'R', data
    # el origen del rename NO debe aparecer como entrada propia
    assert 'a.txt' not in data['files'], data
    # z.txt sigue mapeado correctamente (no se comió su registro)
    assert data['files'].get('z.txt') == 'M', data
    print('  rename consume 2 registros, z.txt alineado OK')


if __name__ == '__main__':
    test_repo_archivo_modificado()
    test_archivo_nuevo_untracked()
    test_dir_no_repo()
    test_rename_consume_dos_registros()
    print('OK')
