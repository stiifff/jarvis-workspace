"""
Test: memoria_lint — chequeos deterministas de salud de .jarvis/memory/.

La memoria compartida no tenía validación alguna: los wikilinks rotos eran
invisibles (el grafo de la UI solo dibuja edges a slugs existentes), las
memorias que citan archivos borrados envejecían en silencio y las huérfanas
no se detectaban. El linter lo hace visible sin gastar un token.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plotspace.tests._harness import fresh_db
from plotspace.core.database import get_db
from plotspace.core.memoria_lint import lint_memorias


def _mem(d, slug, cuerpo, front=''):
    mdir = os.path.join(d, '.jarvis', 'memory')
    os.makedirs(mdir, exist_ok=True)
    with open(os.path.join(mdir, slug + '.md'), 'w', encoding='utf-8') as f:
        f.write(f"---\ntitulo: {slug}\n{front}---\n\n{cuerpo}\n")


def test_detecta_wikilink_roto():
    with tempfile.TemporaryDirectory() as d:
        _mem(d, 'a', 'ver [[b]] y [[no-existe]]')
        _mem(d, 'b', 'cuerpo')
        r = lint_memorias(d)
        assert r['total'] == 2
        assert {'slug': 'a', 'destino': 'no-existe'} in r['rotos']
        assert len(r['rotos']) == 1


def test_wikilink_prosa_se_normaliza_y_es_roto():
    with tempfile.TemporaryDirectory() as d:
        _mem(d, 'a', 'ver [[gesto anti-slop de inputs]]')
        r = lint_memorias(d)
        assert len(r['rotos']) == 1
        assert r['rotos'][0]['destino'] == 'gesto-anti-slop-de-inputs'


def test_detecta_cita_de_archivo_muerto():
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, 'plotspace'))
        with open(os.path.join(d, 'plotspace', 'vivo.py'), 'w') as f:
            f.write('x = 1')
        _mem(d, 'a', 'Ver `plotspace/vivo.py` y `plotspace/borrado.py`.')
        r = lint_memorias(d)
        assert {'slug': 'a', 'ruta': 'plotspace/borrado.py'} in r['citas_muertas']
        assert not any(c['ruta'] == 'plotspace/vivo.py' for c in r['citas_muertas'])


def test_cita_con_primer_segmento_inexistente_no_es_muerta():
    # `src/x.js` donde src/ no existe = ejemplo genérico, no una cita real
    with tempfile.TemporaryDirectory() as d:
        _mem(d, 'a', 'Ejemplo: `src/x.js` en el JSON del workflow.')
        r = lint_memorias(d)
        assert r['citas_muertas'] == []


def test_detecta_huerfanas():
    with tempfile.TemporaryDirectory() as d:
        _mem(d, 'a', 'ver [[b]]')
        _mem(d, 'b', 'cuerpo')          # b recibe link: no huérfana
        _mem(d, 'sola', 'cuerpo aislado')
        r = lint_memorias(d)
        assert r['huerfanas'] == ['sola']


def test_cuenta_obsoletas():
    with tempfile.TemporaryDirectory() as d:
        _mem(d, 'v', 'cuerpo')
        _mem(d, 'o', 'cuerpo', front='estado: obsoleta\n')
        r = lint_memorias(d)
        assert r['obsoletas'] == ['o']


def test_sin_directorio_devuelve_vacio():
    with tempfile.TemporaryDirectory() as d:
        r = lint_memorias(d)
        assert r['total'] == 0 and r['rotos'] == []


# ─── endpoint /memory/salud (no lo debe capturar la ruta {slug}) ─────────────

def test_endpoint_salud():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from plotspace.routers import memory as mem

    fresh_db()
    with tempfile.TemporaryDirectory() as d:
        conn = get_db()
        try:
            conn.execute("INSERT INTO projects (id, nombre, ruta, fecha_creacion, ultimo_acceso) "
                         "VALUES (1, 'p', ?, '2026-07-10', '2026-07-10')", (d,))
            conn.commit()
        finally:
            conn.close()
        _mem(d, 'a', 'ver [[fantasma]]')

        app = FastAPI()
        app.include_router(mem.router)
        client = TestClient(app)
        r = client.get('/api/projects/1/memory/salud')
        assert r.status_code == 200
        data = r.json()
        assert data['total'] == 1
        assert data['rotos'][0]['destino'] == 'fantasma'


# ─── janitor: regenera INDEX de todos los proyectos con memoria ──────────────

def test_mantener_memorias_regenera_index():
    from plotspace.core.mantenimiento import mantener_memorias

    fresh_db()
    with tempfile.TemporaryDirectory() as d:
        conn = get_db()
        try:
            conn.execute("INSERT INTO projects (id, nombre, ruta, fecha_creacion, ultimo_acceso) "
                         "VALUES (1, 'p', ?, '2026-07-10', '2026-07-10')", (d,))
            conn.commit()
        finally:
            conn.close()
        _mem(d, 'nueva-memoria', 'cuerpo')
        # sin INDEX todavía: el janitor lo crea derivado de los archivos
        r = mantener_memorias()
        assert r['proyectos'] >= 1
        idx = open(os.path.join(d, '.jarvis', 'memory', 'INDEX.md')).read()
        assert '[[nueva-memoria]]' in idx


# ─── Contrato de admisión ────────────────────────────────────────────────────

def test_contrato_detecta_memorias_flojas():
    with tempfile.TemporaryDirectory() as d:
        _mem(d, 'sin-tags', 'cuerpo decente con contenido real', front='tags: []\nestado: vigente\n')
        _mem(d, 'buena-con-titulo-decente', 'cuerpo decente',
             front='tags: [terminales]\ncreado: 2026-07-01\nestado: vigente\n')
        mdir = os.path.join(d, '.jarvis', 'memory')
        with open(os.path.join(mdir, 'gigante.md'), 'w') as f:
            f.write('---\ntitulo: Informe enorme\ntags: [x]\ncreado: 2026-07-01\nestado: vigente\n---\n\n'
                    + 'línea de crónica\n' * 200)
        r = lint_memorias(d)
        faltas = {c['slug']: c['faltas'] for c in r['contrato']}
        assert 'sin-tags' in faltas and 'sin-tags' in str(faltas['sin-tags'])
        assert 'gigante' in faltas and any('gigante' in f or 'largo' in f for f in faltas['gigante'])
        assert 'buena-con-titulo-decente' not in faltas


# ─── Canonicidad: reemplazada-por + choques por solape ───────────────────────

def test_vigente_con_reemplazada_por_es_incoherencia():
    with tempfile.TemporaryDirectory() as d:
        _mem(d, 'nueva', 'la verdad actual')
        _mem(d, 'vieja', 'contenido superado',
             front='reemplazada-por: nueva\nestado: vigente\n')
        r = lint_memorias(d)
        assert any(c['slug'] == 'vieja' and 'reemplazada' in c['motivo']
                   for c in r['incoherencias'])


def test_choque_vigente_contra_lapida_por_ruta_compartida():
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, 'plotspace'))
        with open(os.path.join(d, 'plotspace', 'scroll.py'), 'w') as f:
            f.write('x')
        _mem(d, 'lapida-scroll', 'El scrollback de `plotspace/scroll.py` se ELIMINÓ.',
             front='estado: lapida\n')
        _mem(d, 'guia-scroll', 'Cómo usar el scrollback de `plotspace/scroll.py`.')
        r = lint_memorias(d)
        assert any({'lapida-scroll', 'guia-scroll'} == {c['a'], c['b']}
                   for c in r['choques']), f"choques: {r['choques']}"


def test_ruta_hub_no_genera_choque():
    # una ruta citada por MUCHAS memorias (main.py, terminals.py) no es señal:
    # compartirla es lo normal, no un choque lápida-vs-vigente
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, 'plotspace'))
        with open(os.path.join(d, 'plotspace', 'hub.py'), 'w') as f:
            f.write('x')
        _mem(d, 'lapida-x', 'Algo de `plotspace/hub.py` se eliminó.', front='estado: lapida\n')
        for i in range(4):
            _mem(d, f'vigente-{i}', f'Uso normal {i} de `plotspace/hub.py`.')
        r = lint_memorias(d)
        assert r['choques'] == [], f"ruta hub no debe chocar: {r['choques']}"


def test_sin_solape_no_hay_choque():
    with tempfile.TemporaryDirectory() as d:
        _mem(d, 'a', 'tema uno sin rutas')
        _mem(d, 'b', 'tema dos sin rutas', front='estado: lapida\n')
        r = lint_memorias(d)
        assert r['choques'] == []


# ─── Cuarentena: viejas sin uso (propone, no ejecuta) ────────────────────────

def test_cuarentena_viejas_sin_actualizar_y_sin_uso():
    with tempfile.TemporaryDirectory() as d:
        _mem(d, 'anciana', 'cuerpo', front='creado: 2026-01-01\ntags: [a]\n')
        _mem(d, 'fresca', 'cuerpo', front='creado: 2026-07-01\ntags: [a]\n')
        _mem(d, 'anciana-usada', 'cuerpo', front='creado: 2026-01-01\ntags: [a]\n')
        r = lint_memorias(d, hoy='2026-07-10', usados={'anciana-usada'})
        assert 'anciana' in r['cuarentena']
        assert 'fresca' not in r['cuarentena']
        assert 'anciana-usada' not in r['cuarentena'], "el uso registrado exime"


# ─── Categoría en el lint: sin-clasificar + salud por categoría ──────────────

def test_contrato_marca_sin_clasificar():
    with tempfile.TemporaryDirectory() as d:
        _mem(d, 'sin-cat-clara-xyz', 'cuerpo real', front='tags: [banana]\ncreado: 2026-07-01\n')
        _mem(d, 'cosa-de-terminal', 'cuerpo real',
             front='tags: [terminales]\ncreado: 2026-07-01\ncategoria: terminales\nestado: vigente\n')
        r = lint_memorias(d)
        faltas = {c['slug']: c['faltas'] for c in r['contrato']}
        assert 'sin-clasificar' in str(faltas.get('sin-cat-clara-xyz', []))
        assert 'cosa-de-terminal' not in faltas


def test_contrato_sin_estado():
    # el 52% del corpus no declaraba estado: — la jerarquía de autoridad
    # ("la lápida manda", "la más actualizada manda") no se puede aplicar así
    with tempfile.TemporaryDirectory() as d:
        _mem(d, 'sin-estado-x', 'cuerpo real', front='tags: [a]\ncreado: 2026-07-01\n')
        _mem(d, 'con-estado', 'cuerpo real',
             front='tags: [a]\ncreado: 2026-07-01\nestado: vigente\n')
        r = lint_memorias(d)
        faltas = {c['slug']: str(c['faltas']) for c in r['contrato']}
        assert 'sin-estado' in faltas.get('sin-estado-x', '')
        assert 'sin-estado' not in faltas.get('con-estado', '')


def test_contrato_titulo_con_fecha():
    # patrón bitácora: "auditoría 2026-06-20" es una entrada de diario, no
    # conocimiento — la fecha va en creado:/actualizado:
    with tempfile.TemporaryDirectory() as d:
        _mem(d, 'bug-hunt-2026-06-20', 'cuerpo real',
             front='tags: [a]\ncreado: 2026-06-20\nestado: vigente\n')
        _mem(d, 'gotcha-limpio', 'cuerpo real',
             front='tags: [a]\ncreado: 2026-06-20\nestado: vigente\n')
        r = lint_memorias(d)
        faltas = {c['slug']: str(c['faltas']) for c in r['contrato']}
        assert 'titulo-con-fecha' in faltas.get('bug-hunt-2026-06-20', '')
        assert 'titulo-con-fecha' not in faltas.get('gotcha-limpio', '')


# ─── Duplicados: reconciliación al escribir (dos vigentes casi iguales) ──────

def test_detecta_duplicados_casi_identicos():
    cuerpo = ('El flow-control de los websockets de terminales usa watermark '
              'adaptativo por visibilidad para no floodear xterm bajo carga')
    with tempfile.TemporaryDirectory() as d:
        _mem(d, 'flow-control-a', cuerpo, front='tags: [t]\nestado: vigente\n')
        _mem(d, 'flow-control-b', cuerpo + ' (copia con un agregado menor)',
             front='tags: [t]\nestado: vigente\n')
        _mem(d, 'otra-cosa', 'La radio del preview persiste la cola de youtube',
             front='tags: [radio]\nestado: vigente\n')
        r = lint_memorias(d)
        pares = [{p['a'], p['b']} for p in r['duplicados']]
        assert {'flow-control-a', 'flow-control-b'} in pares
        assert not any('otra-cosa' in p for p in pares)


def test_memorias_distintas_no_son_duplicados():
    with tempfile.TemporaryDirectory() as d:
        _mem(d, 'tema-uno', 'El sentinel escribe un json one-shot por terminal',
             front='tags: [a]\nestado: vigente\n')
        _mem(d, 'tema-dos', 'La radio del preview persiste la cola entre reinicios',
             front='tags: [b]\nestado: vigente\n')
        r = lint_memorias(d)
        assert r['duplicados'] == []


def test_lapida_no_entra_en_duplicados():
    cuerpo = 'El scrollback persistente de terminales se guardaba en disco por sesión'
    with tempfile.TemporaryDirectory() as d:
        _mem(d, 'scrollback-lapida', cuerpo, front='tags: [t]\nestado: lapida\n')
        _mem(d, 'scrollback-nuevo', cuerpo, front='tags: [t]\nestado: vigente\n')
        r = lint_memorias(d)
        assert r['duplicados'] == []


# ─── similares(): la señal de reconciliación para crear_memoria ──────────────

def test_similares_encuentra_memoria_del_mismo_tema():
    from plotspace.core.memoria_lint import similares
    with tempfile.TemporaryDirectory() as d:
        _mem(d, 'flow-control-watermark',
             'El flow-control de websockets usa watermark adaptativo por '
             'visibilidad para no floodear xterm bajo flood de output',
             front='tags: [t]\nestado: vigente\n')
        _mem(d, 'radio-cola', 'La radio persiste la cola de youtube',
             front='tags: [radio]\nestado: vigente\n')
        s = similares(d, 'descubrí que el watermark del flow-control de los '
                         'websockets se adapta por visibilidad de xterm')
        assert s and s[0] == 'flow-control-watermark'
        assert 'radio-cola' not in s


def test_similares_texto_nuevo_devuelve_vacio():
    from plotspace.core.memoria_lint import similares
    with tempfile.TemporaryDirectory() as d:
        _mem(d, 'flow-control', 'watermark adaptativo por visibilidad',
             front='tags: [t]\nestado: vigente\n')
        assert similares(d, 'el updater versiona con canary y os.execv') == []


def test_salud_por_categoria():
    with tempfile.TemporaryDirectory() as d:
        _mem(d, 'term-a', 'cuerpo', front='categoria: terminales\ntags: [t]\ncreado: 2026-07-01\n')
        _mem(d, 'term-b', 'cuerpo', front='categoria: terminales\ntags: [t]\ncreado: 2026-07-01\n')
        _mem(d, 'voz-a', 'ver [[fantasma]]',
             front='categoria: voz\ntags: [v]\ncreado: 2026-07-01\n')
        r = lint_memorias(d)
        assert r['por_categoria']['terminales']['total'] == 2
        assert r['por_categoria']['voz']['total'] == 1
        # el link roto de voz-a se contabiliza en su categoría
        assert r['por_categoria']['voz']['rotos'] == 1
        assert r['por_categoria']['terminales']['rotos'] == 0


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


# ─── auto-archivo: la salud EJECUTA lo reversible ────────────────────────────

def test_auto_archivar_solo_viejas_sin_uso():
    from plotspace.core.memoria_lint import auto_archivar
    with tempfile.TemporaryDirectory() as d:
        _mem(d, 'anciana-olvidada', 'cuerpo', front='creado: 2026-01-01\ntags: [a]\nestado: vigente\n')
        _mem(d, 'anciana-usada', 'cuerpo', front='creado: 2026-01-01\ntags: [a]\nestado: vigente\n')
        _mem(d, 'fresca', 'cuerpo', front='creado: 2026-07-01\ntags: [a]\nestado: vigente\n')
        _mem(d, 'lapida-vieja', 'cuerpo', front='creado: 2026-01-01\ntags: [a]\nestado: lapida\n')
        r = auto_archivar(d, hoy='2026-07-19', usados={'anciana-usada'}, dias_extra=30)
        assert r == ['anciana-olvidada']
        src = open(os.path.join(d, '.jarvis', 'memory', 'anciana-olvidada.md')).read()
        assert 'estado: archivo' in src and 'archivado-auto: 2026-07-19' in src
        # las demás intactas
        assert 'estado: vigente' in open(os.path.join(d, '.jarvis', 'memory', 'fresca.md')).read()
        assert 'estado: lapida' in open(os.path.join(d, '.jarvis', 'memory', 'lapida-vieja.md')).read()


def test_auto_archivar_respeta_la_gracia():
    from plotspace.core.memoria_lint import auto_archivar
    with tempfile.TemporaryDirectory() as d:
        # 70 días: pasada la cuarentena (60) pero DENTRO de la gracia (60+30)
        _mem(d, 'en-gracia', 'cuerpo', front='creado: 2026-05-10\ntags: [a]\nestado: vigente\n')
        assert auto_archivar(d, hoy='2026-07-19', dias_extra=30) == []
