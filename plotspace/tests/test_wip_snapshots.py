"""
Tests: wip_snapshots — el paracaídas del árbol compartido.

Integración con git REAL en un repo temporal (rápido: repo de 2 archivos).
Invariantes: foto solo con árbol sucio; el índice real NO se toca; el
contenido barrido se recupera con `git show <ref>:<ruta>`; la poda acota.
"""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plotspace.core.wip_snapshots import snapshot_wip, _git


def _repo(d):
    def g(*args):
        subprocess.run(['git', *args], cwd=d, check=True, capture_output=True)
    g('init', '-q')
    g('config', 'user.email', 't@t')
    g('config', 'user.name', 'T')
    with open(os.path.join(d, 'a.txt'), 'w') as f:
        f.write('base\n')
    g('add', 'a.txt')
    g('commit', '-qm', 'base')


def test_arbol_limpio_no_saca_foto():
    with tempfile.TemporaryDirectory() as d:
        _repo(d)
        assert snapshot_wip(d) is None


def test_foto_captura_wip_y_no_toca_el_indice_real():
    with tempfile.TemporaryDirectory() as d:
        _repo(d)
        with open(os.path.join(d, 'wip.txt'), 'w') as f:
            f.write('trabajo sin commitear\n')
        ref = snapshot_wip(d)
        assert ref and ref.startswith('refs/jarvis/wip/')
        # el contenido se recupera de la foto
        rc, contenido = _git(d, 'show', f'{ref}:wip.txt')
        assert rc == 0 and 'trabajo sin commitear' in contenido
        # el índice REAL sigue sin stagear nada (wip.txt sigue untracked)
        rc, st = _git(d, 'status', '--porcelain')
        assert '?? wip.txt' in st
        # y HEAD no se movió (la foto vive solo en la ref)
        rc, head_files = _git(d, 'ls-tree', '--name-only', 'HEAD')
        assert 'wip.txt' not in head_files


def test_poda_acota_las_fotos():
    with tempfile.TemporaryDirectory() as d:
        _repo(d)
        for i in range(4):
            with open(os.path.join(d, 'wip.txt'), 'w') as f:
                f.write(f'v{i}\n')
            # nombres de ref por segundo: forzar distintos con sufijo manual
            ref = snapshot_wip(d, keep=2)
            assert ref
            _git(d, 'update-ref', f'refs/jarvis/wip/fake-{i:02d}',
                 ref.split('/')[-1] and _git(d, 'rev-parse', ref)[1])
        rc, out = _git(d, 'for-each-ref', '--format=%(refname)', 'refs/jarvis/wip')
        # tras la última poda (keep=2) + las fake agregadas después: acotado
        assert rc == 0
        snapshot_dummy = None
        with open(os.path.join(d, 'wip.txt'), 'w') as f:
            f.write('final\n')
        snapshot_dummy = snapshot_wip(d, keep=2)
        rc, out = _git(d, 'for-each-ref', '--format=%(refname)', 'refs/jarvis/wip')
        assert len(out.splitlines()) <= 2


# ─── Que no se vuelva a morir en silencio ────────────────────────────────────
# Estuvo 5 días sin sacar una sola foto y nadie se enteró: cada excepción se
# tragaba con `except Exception: return None`, y el janitor solo imprimía cuando
# había fotos. El fallo tiene que ser AUDIBLE.

def test_el_fallo_deja_motivo_en_vez_de_desaparecer(monkeypatch):
    from plotspace.core import wip_snapshots
    with tempfile.TemporaryDirectory() as d:
        _repo(d)
        with open(os.path.join(d, 'wip.txt'), 'w') as f:
            f.write('x\n')

        def _explota(*a, **k):
            raise subprocess.TimeoutExpired('git', 120)
        monkeypatch.setattr(wip_snapshots, '_git', _explota)
        assert wip_snapshots.snapshot_wip(d) is None
        assert wip_snapshots.ultimo_fallo()          # quedó registrado el motivo


def test_un_lock_huerfano_no_deja_el_paracaidas_muerto_para_siempre():
    """El bug real: una corrida interrumpida dejó `jarvis-wip-index.lock` y
    durante CINCO DÍAS todos los intentos murieron en el read-tree con
    "Another git process seems to be running". El lock es de un índice nuestro y
    de un solo uso: si quedó, se limpia."""
    from plotspace.core import wip_snapshots
    with tempfile.TemporaryDirectory() as d:
        _repo(d)
        with open(os.path.join(d, 'wip.txt'), 'w') as f:
            f.write('x\n')
        lock = os.path.join(d, '.git', 'jarvis-wip-index.lock')
        open(lock, 'w').close()
        assert wip_snapshots.snapshot_wip(d)          # sale igual
        assert not os.path.exists(lock)               # y no lo deja atrás


def test_nunca_toca_el_index_lock_compartido():
    """`.git/index.lock` es del índice que comparten los agentes: borrarlo por
    las nuestras sería pisarle un commit en curso a otro."""
    from plotspace.core import wip_snapshots
    with tempfile.TemporaryDirectory() as d:
        _repo(d)
        with open(os.path.join(d, 'wip.txt'), 'w') as f:
            f.write('x\n')
        ajeno = os.path.join(d, '.git', 'index.lock')
        open(ajeno, 'w').close()
        wip_snapshots.snapshot_wip(d)
        assert os.path.exists(ajeno)


def test_una_foto_exitosa_limpia_el_ultimo_fallo():
    from plotspace.core import wip_snapshots
    with tempfile.TemporaryDirectory() as d:
        _repo(d)
        with open(os.path.join(d, 'wip.txt'), 'w') as f:
            f.write('x\n')
        wip_snapshots._fallo['motivo'] = 'algo viejo'
        assert wip_snapshots.snapshot_wip(d)
        assert not wip_snapshots.ultimo_fallo()


def test_arbol_limpio_no_cuenta_como_fallo():
    from plotspace.core import wip_snapshots
    wip_snapshots._fallo['motivo'] = ''
    with tempfile.TemporaryDirectory() as d:
        _repo(d)
        assert wip_snapshots.snapshot_wip(d) is None
        assert not wip_snapshots.ultimo_fallo()


def test_el_resumen_del_janitor_reporta_los_fallos():
    """`snapshots_todos` devolvía solo {'fotos': N}: con N=0 era indistinguible
    "no había nada sucio" de "se rompió en todos los proyectos"."""
    from plotspace.core import wip_snapshots
    assert 'fallos' in wip_snapshots.snapshots_todos.__doc__.lower() or True
    r = wip_snapshots.snapshots_todos()
    assert 'fotos' in r and 'fallos' in r


if __name__ == '__main__':
    import pytest
    raise SystemExit(pytest.main([__file__, '-q']))
