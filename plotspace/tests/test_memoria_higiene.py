"""
Test: higiene del sistema de memoria compartida (.jarvis/memory/).

El router de memoria no tenía NINGÚN test. Esta suite cubre la capa Higiene:
  - _parsear: comillas YAML fuera del título + campos actualizado/estado
  - INDEX.md enriquecido (tags · fecha) con marca [OBSOLETA]/[LAPIDA]
  - _regenerar_index compara antes de escribir (cero churn de mtime/git)
  - PUT bumpea `actualizado:` en el frontmatter
"""
import os
import sys
import tempfile
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plotspace.tests._harness import fresh_db
from plotspace.core.database import get_db
from plotspace.routers import memory as mem


def _crear_memoria(d, slug, titulo='Título', tags='a, b', creado='2026-07-01',
                   extra_front='', cuerpo='Cuerpo de la memoria.'):
    mdir = os.path.join(d, '.jarvis', 'memory')
    os.makedirs(mdir, exist_ok=True)
    with open(os.path.join(mdir, slug + '.md'), 'w', encoding='utf-8') as f:
        f.write(f"---\ntitulo: {titulo}\ntags: [{tags}]\ncreado: {creado}\n"
                f"autor: test\n{extra_front}---\n\n{cuerpo}\n")


# ─── _parsear: comillas + campos nuevos ──────────────────────────────────────

def test_parsear_stripea_comillas_del_titulo():
    p = mem._parsear('x', '---\ntitulo: "Con comillas YAML"\n---\ncuerpo')
    assert p['titulo'] == 'Con comillas YAML'
    p2 = mem._parsear('x', "---\ntitulo: 'Simples'\n---\ncuerpo")
    assert p2['titulo'] == 'Simples'


def test_parsear_lee_actualizado_y_estado():
    src = ('---\ntitulo: T\ntags: [a]\ncreado: 2026-06-01\n'
           'actualizado: 2026-07-09\nestado: obsoleta\n---\ncuerpo')
    p = mem._parsear('x', src)
    assert p['actualizado'] == '2026-07-09'
    assert p['estado'] == 'obsoleta'


def test_parsear_defaults_vigente_sin_actualizado():
    p = mem._parsear('x', '---\ntitulo: T\n---\ncuerpo')
    assert p['estado'] == 'vigente'
    assert p['actualizado'] == ''


# ─── INDEX enriquecido ───────────────────────────────────────────────────────

def test_index_enriquecido_con_tags_y_fecha():
    with tempfile.TemporaryDirectory() as d:
        _crear_memoria(d, 'mi-memoria', titulo='Gotcha del preview',
                       tags='preview, xterm', creado='2026-07-01')
        mem._regenerar_index(d)
        idx = open(os.path.join(d, '.jarvis', 'memory', 'INDEX.md')).read()
        linea = next(l for l in idx.splitlines() if 'mi-memoria' in l)
        assert '[[mi-memoria]]' in linea
        assert 'Gotcha del preview' in linea
        assert '#preview' in linea and '#xterm' in linea
        assert '2026-07-01' in linea


def test_index_marca_obsoletas_y_prefiere_actualizado():
    with tempfile.TemporaryDirectory() as d:
        _crear_memoria(d, 'vieja', titulo='Ya no aplica',
                       extra_front='estado: obsoleta\nactualizado: 2026-07-08\n')
        mem._regenerar_index(d)
        idx = open(os.path.join(d, '.jarvis', 'memory', 'INDEX.md')).read()
        linea = next(l for l in idx.splitlines() if 'vieja' in l)
        assert '[OBSOLETA]' in linea
        assert '2026-07-08' in linea      # gana actualizado sobre creado


def test_regenerar_no_escribe_si_no_cambio():
    with tempfile.TemporaryDirectory() as d:
        _crear_memoria(d, 'estable')
        mem._regenerar_index(d)
        path = os.path.join(d, '.jarvis', 'memory', 'INDEX.md')
        os.utime(path, (100.0, 100.0))    # mtime viejo reconocible
        mem._regenerar_index(d)           # sin cambios → NO debe reescribir
        assert os.path.getmtime(path) == 100.0, "regeneró sin cambios (churn de mtime/git)"


# ─── _bumpear_actualizado (puro) + PUT ───────────────────────────────────────

def test_bumpear_actualizado_inserta_y_reemplaza():
    hoy = '2026-07-10'
    sin = '---\ntitulo: T\ncreado: 2026-06-01\n---\n\ncuerpo\n'
    out = mem._bumpear_actualizado(sin, hoy)
    assert 'actualizado: 2026-07-10' in out
    assert out.index('creado:') < out.index('actualizado:')

    con = '---\ntitulo: T\nactualizado: 2026-01-01\n---\ncuerpo\n'
    out2 = mem._bumpear_actualizado(con, hoy)
    assert 'actualizado: 2026-07-10' in out2
    assert 'actualizado: 2026-01-01' not in out2


def test_bumpear_sin_frontmatter_no_toca():
    txt = 'solo cuerpo sin frontmatter\n'
    assert mem._bumpear_actualizado(txt, '2026-07-10') == txt


def test_put_bumpea_actualizado_en_disco():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    fresh_db()
    with tempfile.TemporaryDirectory() as d:
        conn = get_db()
        try:
            conn.execute("INSERT INTO projects (id, nombre, ruta, fecha_creacion, ultimo_acceso) "
                         "VALUES (1, 'p', ?, '2026-07-10', '2026-07-10')", (d,))
            conn.commit()
        finally:
            conn.close()
        _crear_memoria(d, 'para-editar')

        app = FastAPI()
        app.include_router(mem.router)
        client = TestClient(app)
        r = client.put('/api/projects/1/memory/para-editar', json={
            'contenido': '---\ntitulo: Editada\ncreado: 2026-07-01\n---\n\nNuevo cuerpo.\n'})
        assert r.status_code == 200

        src = open(os.path.join(d, '.jarvis', 'memory', 'para-editar.md')).read()
        hoy = datetime.now().strftime('%Y-%m-%d')
        assert f'actualizado: {hoy}' in src


# ─── Categorías: parser + INDEX agrupado ─────────────────────────────────────

def test_parser_lee_categoria_explicita():
    p = mem._parsear('x', '---\ntitulo: T\ncategoria: terminales\n---\ncuerpo')
    assert p['categoria'] == 'terminales'


def test_parser_autoclasifica_si_falta_categoria():
    p = mem._parsear('preview-pestanas', '---\ntitulo: T\ntags: [preview]\n---\ncuerpo')
    assert p['categoria'] == 'preview'
    # y marca que fue inferida (no explícita) para que el lint la pueda señalar
    assert p['categoria_explicita'] is False


def test_index_agrupado_por_categoria():
    with tempfile.TemporaryDirectory() as d:
        _crear_memoria(d, 'mem-term', titulo='Cosa de terminal',
                       extra_front='categoria: terminales\n')
        _crear_memoria(d, 'mem-voz', titulo='Cosa de voz',
                       extra_front='categoria: voz\n')
        mem._regenerar_index(d)
        idx = open(os.path.join(d, '.jarvis', 'memory', 'INDEX.md')).read()
        # encabezados de categoría presentes
        assert mem.mcat.NOMBRE['terminales'] in idx
        assert mem.mcat.NOMBRE['voz'] in idx
        # cada memoria bajo su encabezado (terminales aparece antes que voz en ORDEN)
        assert idx.index('mem-term') < idx.index('mem-voz')
        # el encabezado de terminales viene antes que su memoria
        assert idx.index(mem.mcat.NOMBRE['terminales']) < idx.index('mem-term')


# ─── Estado `archivo`: fuera del INDEX y del recall, sin borrar ──────────────

def test_archivadas_fuera_del_index_con_conteo():
    with tempfile.TemporaryDirectory() as d:
        _crear_memoria(d, 'viva', titulo='Viva')
        _crear_memoria(d, 'cronica-vieja', titulo='Crónica',
                       extra_front='estado: archivo\n')
        mem._regenerar_index(d)
        idx = open(os.path.join(d, '.jarvis', 'memory', 'INDEX.md')).read()
        assert '[[viva]]' in idx
        assert '[[cronica-vieja]]' not in idx, "las archivadas no ensucian el INDEX"
        assert '1 archivada' in idx            # el conteo queda visible al pie


def test_archivadas_fuera_del_recall():
    from plotspace.core.memoria_recall import relevantes
    with tempfile.TemporaryDirectory() as d:
        mdir = os.path.join(d, '.jarvis', 'memory')
        os.makedirs(mdir)
        with open(os.path.join(mdir, 'archivada.md'), 'w') as f:
            f.write('---\ntitulo: A\ntags: [x]\nestado: archivo\n---\n\n'
                    'Cita `plotspace/main.py` con fuerza.\n')
        assert relevantes(d, ['plotspace/main.py'], 'tocar main') == []


# ─── Protocolo v2: campos nuevos + réplica en AGENTS.md ──────────────────────

def test_protocolo_v3_jerarquia_de_autoridad():
    """Cuando dos fuentes chocan, el agente tiene un algoritmo, no una duda."""
    p = mem.PROTOCOLO
    assert 'JERARQUÍA' in p
    assert 'código actual' in p          # (1) el código manda
    assert 'lapida' in p or 'lápida' in p
    assert 'verificá' in p               # (5) verificar, no adivinar
    assert 'te mintió' in p              # corregirla es parte de tu tarea


def test_protocolo_v2_incluye_campos_y_reglas_nuevas():
    p = mem.PROTOCOLO
    assert 'actualizado:' in p
    assert 'estado: vigente' in p
    assert 'lapida' in p
    assert 'leccion' in p
    assert 'UN hecho' in p              # una memoria = un hecho accionable
    assert 'personales' in p            # prohibido linkear memorias personales del CLI


def test_asegurar_inyecta_en_claude_md_y_agents_md():
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, 'CLAUDE.md'), 'w') as f:
            f.write('# Mi proyecto\n\nCosas.\n')
        mem.asegurar_memoria_proyecto(d)

        claude = open(os.path.join(d, 'CLAUDE.md')).read()
        assert mem.PROTOCOLO_MARKER_START in claude
        assert '# Mi proyecto' in claude          # el contenido previo queda intacto

        # AGENTS.md se CREA con el protocolo: Codex/qwen/opencode no leen CLAUDE.md
        agents = open(os.path.join(d, 'AGENTS.md')).read()
        assert mem.PROTOCOLO_MARKER_START in agents


def test_asegurar_refresca_bloque_viejo_en_ambos():
    with tempfile.TemporaryDirectory() as d:
        viejo = (f'# Proyecto\n\n{mem.PROTOCOLO_MARKER_START}\nprotocolo viejo\n'
                 f'{mem.PROTOCOLO_MARKER_END}\n\n## Otra sección\n')
        for nombre in ('CLAUDE.md', 'AGENTS.md'):
            with open(os.path.join(d, nombre), 'w') as f:
                f.write(viejo)
        mem.asegurar_memoria_proyecto(d)
        for nombre in ('CLAUDE.md', 'AGENTS.md'):
            src = open(os.path.join(d, nombre)).read()
            assert 'protocolo viejo' not in src
            assert 'actualizado:' in src
            assert '## Otra sección' in src        # lo demás intacto


def test_asegurar_es_idempotente():
    with tempfile.TemporaryDirectory() as d:
        mem.asegurar_memoria_proyecto(d)
        mem.asegurar_memoria_proyecto(d)
        agents = open(os.path.join(d, 'AGENTS.md')).read()
        assert agents.count(mem.PROTOCOLO_MARKER_START) == 1


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


def test_protocolo_manda_a_grepear_el_index_no_leerlo_entero():
    """El INDEX pesa ~27 KB (~6.7K tokens) con 172 memorias y el protocolo
    mandaba leerlo ENTERO antes de cualquier tarea — un peaje por sesión de
    cada agente. La guía nueva: grep por tema/categoría."""
    from plotspace.routers import memory as mem
    p = mem.PROTOCOLO.lower()
    assert 'grep' in p
    assert 'entero' in p
