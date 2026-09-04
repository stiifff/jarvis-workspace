"""
Test: el toolchain Node de WSL al frente del PATH del pane (terminals.py).

En WSL el workspace es un directorio Linux → `codex` debe correr con el binario
NATIVO de Ubuntu (nvm), no con el shim de Windows (/mnt/c/.../npm/codex) que tira
`exec: node: not found` en el auto-lanzamiento. `_nvm_bin_dir()` ubica ese bin
(prioriza el que tiene codex) para anteponerlo al PATH de la sesión tmux.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plotspace.routers import terminals


def _mk(base, version, *bins):
    """Crea <base>/<version>/bin/ con los ejecutables `bins` vacíos. Devuelve el bin."""
    d = os.path.join(base, version, 'bin')
    os.makedirs(d, exist_ok=True)
    for b in bins:
        open(os.path.join(d, b), 'w').close()
    return d


def test_nvm_bin_none_sin_nvm(tmp_path):
    # Entorno sin nvm → None (no rompe la creación de la sesión).
    assert terminals._nvm_bin_dir(str(tmp_path / 'no-existe')) is None


def test_nvm_bin_prefiere_el_que_tiene_codex(tmp_path):
    base = str(tmp_path)
    _mk(base, 'v20.0.0', 'node', 'npm')                 # node pero NO codex
    con_codex = _mk(base, 'v22.22.2', 'node', 'codex')  # node + codex
    # Aunque v20 exista, gana el bin que tiene codex (el que necesitamos).
    assert terminals._nvm_bin_dir(base) == con_codex


def test_nvm_bin_cae_a_node_si_ninguno_tiene_codex(tmp_path):
    base = str(tmp_path)
    _mk(base, 'v18.0.0', 'node')
    mas_nuevo = _mk(base, 'v22.0.0', 'node')
    # Sin codex en ninguno → el bin con node más nuevo (para que node esté al menos).
    assert terminals._nvm_bin_dir(base) == mas_nuevo


def test_nvm_bin_elige_version_mas_alta_con_codex(tmp_path):
    base = str(tmp_path)
    _mk(base, 'v20.1.0', 'node', 'codex')
    alto = _mk(base, 'v22.22.2', 'node', 'codex')
    assert terminals._nvm_bin_dir(base) == alto


# ─── Prefijo shell que antepone el toolchain al PATH del pane ─────────────────
# (Va en el COMANDO, no por `tmux -e PATH=...`: tmux ignora el override de PATH —
# verificado empíricamente en este box. Con -e el pane quedaba con el PATH del
# server y `codex` caía al shim de Windows.)

def test_prefijo_path_con_nvm():
    nvm = '/home/user/.nvm/versions/node/v22.22.2/bin'
    assert terminals._prefijo_path_wsl(nvm) == f'export PATH="{nvm}:$PATH"; '


def test_prefijo_path_sin_nvm_es_vacio():
    assert terminals._prefijo_path_wsl(None) == ''
    assert terminals._prefijo_path_wsl('') == ''
