# plotspace/tests/test_hunks_propios.py
"""Commit por HUNK: quedarse solo con los cambios propios de un archivo compartido.

POR QUÉ EXISTE
En este árbol todos los agentes trabajan sobre la misma rama, así que
`git add <archivo>` NO es "lo mío": es el archivo ENTERO, con el trabajo sin
commitear del otro adentro. Los agentes lo descubrieron a los golpes y armaron
a mano una receta (`git diff -U0` → filtrar hunks por CONTENIDO → `git apply
--cached`), que quedó escrita en el MAILBOX después de que un filtro por NÚMERO
DE LÍNEA se llevara puesta una función ajena.

Acá esa receta deja de ser artesanal: la provenance sabe exactamente qué texto
insertó cada agente, así que el filtro se hace con datos, no con heurística.

Invariante de oro: ante la duda, el hunk NO es mío. Dejar afuera un cambio
propio cuesta un segundo commit; llevarse uno ajeno le borra el trabajo a otro.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from hunks_propios import (          # noqa: E402
    partir_diff, lineas_agregadas, lineas_quitadas, hunk_es_mio, filtrar_parche,
)

DIFF = """diff --git a/f.js b/f.js
index 1111111..2222222 100644
--- a/f.js
+++ b/f.js
@@ -3 +3 @@
-  const scrollbar = true;
+  const scrollbar = false;
@@ -10 +10 @@
-  return animar(x);
+  return animarSuave(x, { duracion: 220 });
"""


# ─── parseo ───────────────────────────────────────────────────────────────────

def test_partir_diff_separa_cabecera_y_hunks():
    cab, hunks = partir_diff(DIFF)
    assert cab.startswith('diff --git a/f.js b/f.js')
    assert '+++ b/f.js' in cab
    assert len(hunks) == 2
    assert hunks[0].startswith('@@ -3 +3 @@')
    assert hunks[1].startswith('@@ -10 +10 @@')


def test_partir_diff_vacio():
    assert partir_diff('') == ('', [])
    assert partir_diff(None) == ('', [])
    assert partir_diff('sin hunks acá') == ('sin hunks acá', [])


def test_lineas_agregadas_y_quitadas():
    _, hunks = partir_diff(DIFF)
    assert lineas_agregadas(hunks[0]) == ['const scrollbar = false;']
    assert lineas_quitadas(hunks[0]) == ['const scrollbar = true;']


def test_no_confunde_marcadores_de_cabecera_con_lineas():
    """'+++ b/x' y '--- a/x' no son líneas agregadas/quitadas."""
    h = '@@ -1 +1 @@\n+++ b/no-soy-una-linea\n+de verdad\n'
    assert lineas_agregadas(h) == ['de verdad']


# ─── atribución ───────────────────────────────────────────────────────────────

def test_hunk_es_mio_por_contenido_agregado():
    _, hunks = partir_diff(DIFF)
    assert hunk_es_mio(hunks[0], ['  const scrollbar = false;'], []) is True


def test_hunk_ajeno_no_es_mio():
    _, hunks = partir_diff(DIFF)
    assert hunk_es_mio(hunks[1], ['  const scrollbar = false;'], []) is False


def test_hunk_sin_match_no_es_mio():
    """Conservador: si no puedo probar que es mío, no lo toco."""
    _, hunks = partir_diff(DIFF)
    assert hunk_es_mio(hunks[0], [], []) is False


def test_hunk_ambiguo_no_es_mio():
    """Si el hunk contiene texto mío Y texto de otro, es ambiguo → afuera."""
    h = '@@ -1,2 +1,2 @@\n+mi linea nueva\n+la linea del otro\n'
    assert hunk_es_mio(h, ['mi linea nueva'], ['la linea del otro']) is False


def test_hunk_de_borrado_se_atribuye_por_lo_quitado():
    """Un hunk que SOLO borra no tiene líneas agregadas: se mira lo que quitó
    contra lo que yo tenía como `antes` en mis ediciones."""
    h = '@@ -5,2 +4,0 @@\n-function vieja() {}\n-\n'
    assert hunk_es_mio(h, ['function vieja() {}'], []) is True


def test_lineas_triviales_no_atribuyen():
    """Una llave sola o una línea vacía aparecen en el diff de cualquiera: no
    alcanzan para reclamar un hunk."""
    h = '@@ -1 +1 @@\n+}\n'
    assert hunk_es_mio(h, ['}'], []) is False


def test_match_tolera_indentacion_distinta():
    h = '@@ -1 +1 @@\n+    const scrollbar = false;\n'
    assert hunk_es_mio(h, ['const scrollbar = false;'], []) is True


# ─── armado del parche ────────────────────────────────────────────────────────

def test_filtrar_parche_deja_solo_lo_mio():
    parche = filtrar_parche(DIFF, ['const scrollbar = false;'], [])
    assert parche is not None
    assert 'scrollbar = false' in parche
    assert 'animarSuave' not in parche
    assert parche.startswith('diff --git')
    assert parche.endswith('\n')


def test_filtrar_parche_sin_hunks_propios_devuelve_none():
    assert filtrar_parche(DIFF, ['nada que ver'], []) is None


def test_filtrar_parche_conserva_la_cabecera_completa():
    """Sin las 4 líneas de cabecera, `git apply` no sabe a qué archivo aplicar."""
    parche = filtrar_parche(DIFF, ['const scrollbar = false;'], [])
    for linea in ('diff --git a/f.js b/f.js', '--- a/f.js', '+++ b/f.js'):
        assert linea in parche


# ─── prueba de fuego: contra git de verdad ────────────────────────────────────

def _repo(tmp_path, contenido):
    def git(*a):
        return subprocess.run(['git', *a], cwd=tmp_path, capture_output=True,
                              text=True, timeout=20)
    git('init', '-q')
    git('config', 'user.email', 't@t'); git('config', 'user.name', 'T')
    f = tmp_path / 'f.js'
    f.write_text(contenido, encoding='utf-8')
    git('add', 'f.js'); git('commit', '-qm', 'base')
    return git, f


BASE = ('function chatOutput() {\n'
        '  const scrollbar = true;\n'
        '  // ── zona intermedia, muchas líneas de por medio ──\n'
        '  const a = 1;\n'
        '  const b = 2;\n'
        '  const c = 3;\n'
        '  return animar(x);\n'
        '}\n')


def test_parche_filtrado_aplica_en_git_real(tmp_path):
    """El test que importa: en un repo REAL con dos agentes editando zonas
    distintas del mismo archivo, stagear solo lo mío deja el cambio del otro
    intacto en el working tree (sin commitear, como corresponde).

    Es el caso documentado en el MAILBOX del proyecto: las zonas de dos agentes
    en un archivo grande viven a cientos de líneas de distancia."""
    git, f = _repo(tmp_path, BASE)

    # Agente #1 (otro) toca la animación; agente #2 (yo) saca el scrollbar.
    f.write_text(BASE
                 .replace('const scrollbar = true;', 'const scrollbar = false;')
                 .replace('return animar(x);',
                          'return animarSuave(x, { duracion: 220 });'),
                 encoding='utf-8')

    diff = git('diff', '-U0', '--', 'f.js').stdout
    parche = filtrar_parche(diff, ['  const scrollbar = false;'],
                            ['  return animarSuave(x, { duracion: 220 });'])
    assert parche is not None

    p = tmp_path / 'mio.patch'
    p.write_text(parche, encoding='utf-8')
    r = git('apply', '--cached', '--unidiff-zero', str(p))
    assert r.returncode == 0, r.stderr

    staged = git('diff', '--cached').stdout
    assert 'scrollbar = false' in staged
    assert 'animarSuave' not in staged          # el trabajo del #1 NO se commitea
    assert 'animarSuave' in f.read_text(encoding='utf-8')   # y sigue en el disco


def test_ediciones_ADYACENTES_no_se_parten(tmp_path):
    """LÍMITE CONOCIDO Y DELIBERADO: git funde en UN solo hunk los cambios de
    líneas contiguas, así que si dos agentes editan líneas pegadas no hay forma
    de separarlos por hunk. Ahí NO se stagea nada: mejor pedirle al agente que
    lo resuelva con el dueño que llevarse el cambio del otro en el commit.

    (El caller avisa de estos hunks en vez de tragárselos en silencio.)"""
    git, f = _repo(tmp_path, 'a\n  const scrollbar = true;\n'
                             '  return animar(x);\nz\n')
    f.write_text('a\n  const scrollbar = false;\n'
                 '  return animarSuave(x, { duracion: 220 });\nz\n', encoding='utf-8')
    diff = git('diff', '-U0', '--', 'f.js').stdout
    assert diff.count('@@') == 2                       # UN solo hunk (2 marcas)
    assert filtrar_parche(diff, ['  const scrollbar = false;'],
                          ['  return animarSuave(x, { duracion: 220 });']) is None


if __name__ == '__main__':
    import pytest
    sys.exit(pytest.main([__file__, '-q']))
