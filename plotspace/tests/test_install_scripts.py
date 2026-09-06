"""El camino de un extraño al repo: install.sh / install.ps1.

Quien ve GitHub tiene que copiar UN comando, no un tutorial de venv. Estos
tests clavan las decisiones de producto:

- Linux/macOS = install.sh (apt/dnf/pacman/brew).
- Windows = install.ps1, que instala WSL si falta y deja un .bat en el Escritorio.
- El pip es el requirements.txt COMPLETO (voz local, TTS, todo). No hay
  instalador "diet" que recorte funciones de Jarvis.
- El comando que queda en PATH es el `jarvis` del venv (el motor), no bin/jarvis
  (ese abre un proyecto contra un server que ya corre).
"""
import os
import stat
import subprocess

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SH = os.path.join(_RAIZ, 'install.sh')
_PS1 = os.path.join(_RAIZ, 'install.ps1')


def _leer(ruta):
    with open(ruta, encoding='utf-8') as f:
        return f.read()


def test_install_sh_existe_y_es_ejecutable():
    assert os.path.isfile(_SH), 'install.sh tiene que vivir en la raíz (curl …/main/install.sh)'
    assert os.access(_SH, os.X_OK)


def test_install_sh_sintaxis_bash():
    r = subprocess.run(['bash', '-n', _SH], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_install_sh_help_sale_cero():
    r = subprocess.run(['bash', _SH, '--help'], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    out = r.stdout + r.stderr
    assert 'install.sh' in out
    assert 'Windows' in out or 'install.ps1' in out


def test_install_sh_dry_run_usa_el_clone_local_y_no_clona():
    r = subprocess.run(
        ['bash', _SH, '--dry-run', '--no-start'],
        cwd=_RAIZ, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout + '\n' + r.stderr
    out = r.stdout + r.stderr
    assert 'dry-run' in out.lower()
    assert 'git clone' not in out.lower() or 'skip' in out.lower() or 'existing' in out.lower() or 'ya está' in out.lower() or 'already' in out.lower()
    assert 'plotspace/requirements.txt' in out
    assert 'pip install -e' in out or 'pip install -e .' in out


def test_install_sh_instala_deps_de_sistema_completas():
    """tmux es el motor; ffmpeg lo pide el STT; git/curl/python3 el resto."""
    src = _leer(_SH)
    for paquete in ('tmux', 'git', 'curl', 'ffmpeg', 'python3'):
        assert paquete in src, f'falta {paquete} en install.sh'


def test_install_sh_usa_requirements_completo_no_extras():
    src = _leer(_SH)
    assert 'plotspace/requirements.txt' in src
    # El camino público no es `pip install .` pelado (eso omite voz local).
    assert 'requirements-base.txt' not in src
    assert '[voice]' not in src


def test_install_sh_deja_jarvis_del_venv_en_path():
    """bin/jarvis del repo es OTRO comando (abre un proyecto). El wrapper
    tiene que apuntar al entry point del venv."""
    src = _leer(_SH)
    assert '.local/bin' in src
    assert 'venv/bin/jarvis' in src


def test_install_sh_conoce_brew_y_apt():
    src = _leer(_SH)
    assert 'brew' in src
    assert 'apt' in src
    assert 'dnf' in src or 'yum' in src
    assert 'pacman' in src


def test_install_ps1_existe():
    assert os.path.isfile(_PS1), 'install.ps1 en la raíz (irm …/main/install.ps1 | iex)'


def test_install_ps1_instala_wsl_y_deja_acceso_en_el_escritorio():
    src = _leer(_PS1)
    assert 'wsl --install' in src or 'wsl.exe --install' in src
    assert 'Desktop' in src or 'Escritorio' in src
    assert 'abrir-jarvis-app.bat' in src
    assert 'install.sh' in src
    assert 'celsiusm/jarvis-workspace' in src


def test_install_ps1_no_promete_motor_nativo_windows():
    src = _leer(_PS1).lower()
    assert 'conpty' not in src
    assert 'msi' not in src


def test_readme_tiene_un_comando_por_sistema():
    readme = _leer(os.path.join(_RAIZ, 'README.md'))
    assert 'install.sh' in readme
    assert 'install.ps1' in readme
    assert 'celsiusm/jarvis-workspace' in readme


def test_readme_instalacion_arriba_antes_de_las_capturas():
    """Un extraño no tiene que scrollear cuatro screenshots para instalar."""
    readme = _leer(os.path.join(_RAIZ, 'README.md'))
    shot = readme.find('docs/images/home-empty.png')
    assert shot > 0
    assert readme.find('install.sh') < shot
    assert readme.find('install.ps1') < shot
    # Dos accesos en el header (Unix vs Windows), no tres columnas iguales.
    assert readme.find('](#linux--macos)') < shot or readme.find('](#install-linux') < shot
    assert readme.find('](#windows)') < shot or readme.find('](#install-windows)') < shot
