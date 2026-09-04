"""
Tests: gate de admisión de memorias (scripts/guard_memoria.py).

La calidad del corpus se degradaba en el momento de ESCRIBIR: memorias sin
`estado:` (52% del corpus al 2026-07-18), informes de 100+ líneas y títulos
con fecha embebida (patrón bitácora). El linter lo detectaba DESPUÉS, cuando
el daño ya estaba hecho y nadie procesaba la señal. Este guard corre en el
pre-commit (gemelo de guard_propiedad/scan_secretos) y valida el contrato
ANTES de que la memoria entre al repo — reconciliación al escribir, no al leer.

Invariantes:
1. Memoria staged sin frontmatter / sin titulo / sin tags / sin categoria /
   sin estado → violación (fix de una línea, mensaje accionable).
2. estado fuera de {vigente, obsoleta, lapida, archivo} → violación.
3. Memoria NUEVA con más de 150 líneas no vacías → violación (informe, no
   memoria). Las legacy largas las marca el lint, no el guard.
4. Memoria NUEVA con fecha embebida en slug o título (patrón `2026-07`) →
   violación (una memoria no es una entrada de bitácora). Las editadas
   legacy no se bloquean por esto.
5. Memoria NUEVA sin `resumen:` → violación (el recall inyecta esa línea).
6. INDEX.md y lecciones-del-enjambre.md están exentos (autogenerados).
7. Falla ABIERTO: cualquier error inesperado permite el commit.
"""
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'scripts'))
import guard_memoria as gm


VALIDA = """---
titulo: Gotcha del fit de xterm con scrollbar oculta
tags: [xterm, css]
categoria: terminales
resumen: Ocultar la scrollbar de xterm activa un fallback de 15px en el fit.
creado: 2026-07-18
autor: Backend
estado: vigente
---

Ocultar la scrollbar dispara el fallback. Detalle del porqué y el fix.
"""


def test_memoria_valida_pasa():
    assert gm.validar('gotcha-fit-scrollbar', VALIDA, es_nueva=True) == []


def test_sin_frontmatter_viola():
    v = gm.validar('suelta', 'texto sin frontmatter', es_nueva=False)
    assert any('frontmatter' in x for x in v)


def test_sin_estado_viola():
    src = VALIDA.replace('estado: vigente\n', '')
    v = gm.validar('gotcha-fit-scrollbar', src, es_nueva=False)
    assert any('estado' in x for x in v)


def test_estado_invalido_viola():
    src = VALIDA.replace('estado: vigente', 'estado: activa')
    v = gm.validar('gotcha-fit-scrollbar', src, es_nueva=False)
    assert any('estado' in x for x in v)


def test_sin_tags_y_sin_categoria_viola():
    src = VALIDA.replace('tags: [xterm, css]\n', '').replace('categoria: terminales\n', '')
    v = gm.validar('gotcha-fit-scrollbar', src, es_nueva=False)
    assert any('tags' in x for x in v)
    assert any('categoria' in x for x in v)


def test_cuerpo_gigante_viola_solo_nuevas():
    src = VALIDA + '\n'.join(f'línea {i}' for i in range(160))
    v = gm.validar('gotcha-fit-scrollbar', src, es_nueva=True)
    assert any('líneas' in x for x in v)
    # editar una legacy larga (agregar estado:, un hallazgo) no exige
    # reescribirla en el mismo commit — eso empuja al --no-verify
    assert not any('líneas' in x for x in
                   gm.validar('gotcha-fit-scrollbar', src, es_nueva=False))


def test_fecha_en_slug_viola_solo_nuevas():
    assert any('bitácora' in x for x in
               gm.validar('auditoria-2026-07-18', VALIDA, es_nueva=True))
    # legacy editada: no se bloquea por el nombre que ya tiene
    assert not any('bitácora' in x for x in
                   gm.validar('auditoria-2026-07-18', VALIDA, es_nueva=False))


def test_fecha_en_titulo_viola_solo_nuevas():
    src = VALIDA.replace('titulo: Gotcha del fit de xterm con scrollbar oculta',
                         'titulo: Bug hunt del fit (2026-07-18)')
    assert any('bitácora' in x for x in gm.validar('bug-hunt-fit', src, es_nueva=True))
    assert not any('bitácora' in x for x in gm.validar('bug-hunt-fit', src, es_nueva=False))


def test_anio_suelto_en_titulo_no_viola():
    # "frames 2026" (año sin mes) es un nombre de concepto, no una bitácora
    src = VALIDA.replace('titulo: Gotcha del fit de xterm con scrollbar oculta',
                         'titulo: Negro en fullscreen con frames 2026 partidos')
    assert gm.validar('negro-fullscreen-frames', src, es_nueva=True) == []


def test_sin_resumen_viola_solo_nuevas():
    src = VALIDA.replace('resumen: Ocultar la scrollbar de xterm activa un fallback de 15px en el fit.\n', '')
    assert any('resumen' in x for x in gm.validar('gotcha-fit-scrollbar', src, es_nueva=True))
    assert not any('resumen' in x for x in gm.validar('gotcha-fit-scrollbar', src, es_nueva=False))


def test_exentos_index_y_lecciones():
    assert gm.es_exento('.jarvis/memory/INDEX.md')
    assert gm.es_exento('.jarvis/memory/lecciones-del-enjambre.md')
    assert not gm.es_exento('.jarvis/memory/una-memoria.md')


def test_es_memoria_detecta_rutas():
    assert gm.es_memoria('.jarvis/memory/foo.md')
    assert not gm.es_memoria('.jarvis/memory/INDEX.md')      # exento
    assert not gm.es_memoria('plotspace/core/x.py')
    assert not gm.es_memoria('.jarvis/MAILBOX.md')


def test_main_falla_abierto(monkeypatch):
    def explota():
        raise RuntimeError('git roto')
    monkeypatch.setattr(gm, 'memorias_staged', explota)
    assert gm.main() == 0


if __name__ == '__main__':
    import pytest
    raise SystemExit(pytest.main([__file__, '-q']))


def test_memorias_en_rango_caza_lo_commiteado(tmp_path):
    # gemelo pre-push: una memoria colada con --no-verify aparece en el rango
    import subprocess
    d = str(tmp_path)
    def g(*args):
        subprocess.run(['git', *args], cwd=d, check=True, capture_output=True)
    g('init', '-q'); g('config', 'user.email', 't@t'); g('config', 'user.name', 'T')
    os.makedirs(os.path.join(d, '.jarvis', 'memory'))
    with open(os.path.join(d, 'base.txt'), 'w') as f:
        f.write('x')
    g('add', 'base.txt'); g('commit', '-qm', 'base')
    sha1 = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=d, capture_output=True,
                          text=True).stdout.strip()
    with open(os.path.join(d, '.jarvis', 'memory', 'colada.md'), 'w') as f:
        f.write('sin frontmatter')
    g('add', '.jarvis/memory/colada.md'); g('commit', '-qm', 'colada')
    sha2 = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=d, capture_output=True,
                          text=True).stdout.strip()
    cwd_bak = os.getcwd()
    try:
        os.chdir(d)
        items = gm.memorias_en_rango(sha1, sha2)
    finally:
        os.chdir(cwd_bak)
    assert len(items) == 1
    path, es_nueva, src = items[0]
    assert path.endswith('colada.md') and es_nueva is True
    assert any('frontmatter' in v for v in gm.validar('colada', src, es_nueva))
