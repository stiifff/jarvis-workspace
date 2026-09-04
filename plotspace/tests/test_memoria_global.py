"""
Test: semilla global cross-proyecto.

Cada proyecto nuevo del workspace arranca con .jarvis/memory/ VACÍA — enjambre
amnésico que va a re-tropezar con WSL, el puerto 3000 y el índice git
compartido. La semilla global inyecta esas lecciones de entorno (que valen
para CUALQUIER repo) al crear el proyecto, y una lección local se puede
PROMOVER a global para que los futuros proyectos la hereden.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plotspace.core import memoria_global as mg


# ─── La semilla existe y es sana ─────────────────────────────────────────────

def test_semilla_tiene_lecciones_de_entorno():
    slugs = {m['slug'] for m in mg.SEMILLA}
    # las universales del enjambre en este entorno
    assert any('puerto' in s for s in slugs)
    assert any('git' in s for s in slugs)
    for m in mg.SEMILLA:
        assert m['slug'] and m['titulo'] and m['categoria'] and m['cuerpo']


def test_render_produce_frontmatter_valido():
    md = mg._render(mg.SEMILLA[0])
    assert md.startswith('---\n')
    assert 'estado: vigente' in md
    assert 'tags:' in md and 'categoria:' in md
    assert 'semilla-global' in md      # marca de procedencia


def test_render_fecha_dinamica():
    # la fecha era un literal '2026-07-10': una semilla nunca usada envejecía
    # hacia la cuarentena contra una fecha congelada
    from datetime import date
    md = mg._render(mg.SEMILLA[0])
    assert f'creado: {date.today().isoformat()}' in md
    md2 = mg._render(mg.SEMILLA[0], hoy='2026-01-05')
    assert 'creado: 2026-01-05' in md2


# ─── Sembrado idempotente, sin pisar ─────────────────────────────────────────

def test_sembrar_crea_las_memorias_en_proyecto_nuevo():
    with tempfile.TemporaryDirectory() as d:
        mdir = os.path.join(d, '.jarvis', 'memory')
        os.makedirs(mdir)
        n = mg.sembrar(d)
        assert n == len(mg.SEMILLA)
        for m in mg.SEMILLA:
            assert os.path.exists(os.path.join(mdir, m['slug'] + '.md'))


def test_sembrar_no_pisa_lo_existente():
    with tempfile.TemporaryDirectory() as d:
        mdir = os.path.join(d, '.jarvis', 'memory')
        os.makedirs(mdir)
        # un slug de la semilla ya existe con contenido propio del proyecto
        slug = mg.SEMILLA[0]['slug']
        propio = os.path.join(mdir, slug + '.md')
        with open(propio, 'w') as f:
            f.write('---\ntitulo: Mía\n---\n\nno tocar esto\n')
        mg.sembrar(d)
        assert open(propio).read() == '---\ntitulo: Mía\n---\n\nno tocar esto\n'


def test_sembrar_es_idempotente():
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, '.jarvis', 'memory'))
        mg.sembrar(d)
        n2 = mg.sembrar(d)            # segunda vez: nada nuevo que crear
        assert n2 == 0


# ─── Promoción de una lección local a global ─────────────────────────────────

def test_promover_agrega_al_store_global():
    with tempfile.TemporaryDirectory() as store, tempfile.TemporaryDirectory() as proj:
        mdir = os.path.join(proj, '.jarvis', 'memory')
        os.makedirs(mdir)
        with open(os.path.join(mdir, 'leccion-x.md'), 'w') as f:
            f.write('---\ntitulo: Lección X\ntags: [leccion]\ncategoria: entorno\n'
                    'estado: vigente\n---\n\nNo hagas Y en WSL.\n')
        ok = mg.promover('leccion-x', proj, store_dir=store)
        assert ok
        assert os.path.exists(os.path.join(store, 'leccion-x.md'))
        # y ahora un proyecto nuevo la hereda vía el store
        with tempfile.TemporaryDirectory() as nuevo:
            os.makedirs(os.path.join(nuevo, '.jarvis', 'memory'))
            mg.sembrar(nuevo, store_dir=store)
            assert os.path.exists(os.path.join(nuevo, '.jarvis', 'memory', 'leccion-x.md'))


# ─── Sugerencias de promoción local→global (el canal estaba en cero) ─────────
# promover() existía pero exigía que el usuario se acordara de usarlo. Estas
# sugerencias las calcula el sistema: lecciones de ENTORNO (el box es el mismo
# para todos los proyectos) + lecciones que matchean fallos de OTROS proyectos.

def _leccion(proj, slug, categoria='entorno', cuerpo='regla corta', tags='leccion, wsl'):
    mdir = os.path.join(proj, '.jarvis', 'memory')
    os.makedirs(mdir, exist_ok=True)
    with open(os.path.join(mdir, slug + '.md'), 'w') as f:
        f.write(f'---\ntitulo: {slug}\ntags: [{tags}]\ncategoria: {categoria}\n'
                f'estado: vigente\n---\n\n{cuerpo}\n')


def test_sugerir_leccion_de_entorno_no_global():
    with tempfile.TemporaryDirectory() as store, tempfile.TemporaryDirectory() as proj:
        _leccion(proj, 'gotcha-wsl-nuevo')
        sug = mg.sugerir_promociones(proj, store_dir=store, motivos_ajenos=[])
        assert any(c['slug'] == 'gotcha-wsl-nuevo' for c in sug)


def test_no_sugerir_si_ya_es_global():
    with tempfile.TemporaryDirectory() as store, tempfile.TemporaryDirectory() as proj:
        _leccion(proj, 'gotcha-wsl-nuevo')
        with open(os.path.join(store, 'gotcha-wsl-nuevo.md'), 'w') as f:
            f.write('ya global')
        sug = mg.sugerir_promociones(proj, store_dir=store, motivos_ajenos=[])
        assert not any(c['slug'] == 'gotcha-wsl-nuevo' for c in sug)


def test_no_sugerir_semilla_ni_categoria_local_sin_match():
    with tempfile.TemporaryDirectory() as store, tempfile.TemporaryDirectory() as proj:
        # un slug de la semilla re-escrito localmente no se re-sugiere
        _leccion(proj, mg.SEMILLA[0]['slug'])
        # una lección de UI (tema local del proyecto) sin señal cruzada tampoco
        _leccion(proj, 'gotcha-css-local', categoria='ui', tags='leccion, css')
        sug = mg.sugerir_promociones(proj, store_dir=store, motivos_ajenos=[])
        assert sug == []


def test_sugerir_leccion_que_matchea_fallo_ajeno():
    with tempfile.TemporaryDirectory() as store, tempfile.TemporaryDirectory() as proj:
        _leccion(proj, 'gotcha-npm-workspaces', categoria='swarm',
                 tags='leccion, npm',
                 cuerpo='El hoisting de npm workspaces rompe los symlinks del monorepo.')
        sug = mg.sugerir_promociones(
            proj, store_dir=store,
            motivos_ajenos=['build falló: npm workspaces hoisting symlinks rotos en monorepo'])
        assert any(c['slug'] == 'gotcha-npm-workspaces'
                   and c['motivo'] == 'reincide-en-otro-proyecto' for c in sug)


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
