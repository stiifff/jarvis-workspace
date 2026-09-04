# plotspace/tests/test_provenance.py
"""Tests de la lógica pura de provenance (plotspace/core/provenance.py).

Nada de red, tmux ni DB — espejo de test_agent_live.py.

Contexto: el parser de panes de agent_live quedó CIEGO cuando Claude Code pasó
a resúmenes colapsados ("Making 1 scratchpad edit +2") que ni nombran el
archivo. La provenance ya no se lee de la pantalla: llega por hook con el
payload REAL de la herramienta. Estos tests fijan el contrato defensivo: el
normalizador acepta todas las formas conocidas del payload porque el CLI las
cambia sin avisar (esa fue justamente la causa de muerte del sistema anterior).
"""
from plotspace.core.provenance import (
    normalizar_payload,
    simbolos,
    simbolos_perdidos,
    es_sobrescritura_total,
)


# ─── normalizar_payload: formas del payload de Edit ───────────────────────────

def test_edit_forma_old_string():
    """Forma real de la herramienta Edit de Claude Code 2.1.x."""
    ops = normalizar_payload('Edit', {
        'file_path': 'plotspace/core/x.py',
        'old_string': 'def foo():',
        'new_string': 'def foo(bar):',
    })
    assert ops == [{'op': 'write', 'path': 'plotspace/core/x.py',
                    'antes': 'def foo():', 'despues': 'def foo(bar):'}]


def test_edit_forma_edits_old_text():
    """Forma documentada (edits[] con old_text/new_text): un solo op por edit."""
    ops = normalizar_payload('Edit', {
        'file_path': 'src/index.ts',
        'edits': [
            {'old_text': 'function hello() {', 'new_text': 'function hello(n) {'},
            {'old_text': 'const a = 1', 'new_text': 'const a = 2'},
        ],
    })
    assert len(ops) == 2
    assert ops[0]['antes'] == 'function hello() {'
    assert ops[1]['despues'] == 'const a = 2'
    assert all(o['path'] == 'src/index.ts' and o['op'] == 'write' for o in ops)


def test_edit_forma_edits_old_string():
    """MultiEdit histórico: edits[] pero con old_string/new_string."""
    ops = normalizar_payload('Edit', {
        'file_path': 'a.js',
        'edits': [{'old_string': 'x', 'new_string': 'y'}],
    })
    assert ops == [{'op': 'write', 'path': 'a.js', 'antes': 'x', 'despues': 'y'}]


# ─── normalizar_payload: formas del payload de Write ──────────────────────────

def test_write_forma_content():
    ops = normalizar_payload('Write', {'file_path': 'nuevo.md', 'content': '# hola'})
    assert ops == [{'op': 'write', 'path': 'nuevo.md', 'antes': '', 'despues': '# hola'}]


def test_write_forma_file_text():
    """Forma documentada (file_text)."""
    ops = normalizar_payload('Write', {'file_path': 'README.md', 'file_text': '# P'})
    assert ops == [{'op': 'write', 'path': 'README.md', 'antes': '', 'despues': '# P'}]


# ─── normalizar_payload: formas de opencode (camelCase) ───────────────────────
# opencode edita con `edit` {filePath, oldString, newString} y `write`
# {filePath, content} (verificado del binario). El plugin de provenance reenvía
# esos args CRUDOS, así que el normalizador tiene que entender el camelCase.

def test_opencode_edit_camelcase():
    ops = normalizar_payload('edit', {
        'filePath': '/abs/app.js', 'oldString': 'const a = 1',
        'newString': 'const a = 2', 'replaceAll': False})
    assert ops == [{'op': 'write', 'path': '/abs/app.js',
                    'antes': 'const a = 1', 'despues': 'const a = 2'}]


def test_opencode_write_content():
    ops = normalizar_payload('write', {'filePath': '/abs/nuevo.md', 'content': '# hola'})
    assert ops == [{'op': 'write', 'path': '/abs/nuevo.md', 'antes': '', 'despues': '# hola'}]


def test_qwen_write_file_content():
    """qwen (fork de Gemini CLI): `write_file` trae {file_path, file_content}."""
    ops = normalizar_payload('write_file', {'file_path': '/p/a.py', 'file_content': 'x = 1'})
    assert ops == [{'op': 'write', 'path': '/p/a.py', 'antes': '', 'despues': 'x = 1'}]


def test_qwen_edit_usa_old_new_string():
    """qwen `edit`/`replace` usa old_string/new_string (ya soportados)."""
    ops = normalizar_payload('replace', {'file_path': '/p/a.py',
                                         'old_string': 'a', 'new_string': 'b'})
    assert ops == [{'op': 'write', 'path': '/p/a.py', 'antes': 'a', 'despues': 'b'}]


def test_read_es_op_de_lectura():
    ops = normalizar_payload('Read', {'file_path': 'plotspace/main.py'})
    assert ops == [{'op': 'read', 'path': 'plotspace/main.py', 'antes': '', 'despues': ''}]


def test_notebook_edit_usa_notebook_path():
    ops = normalizar_payload('NotebookEdit', {'notebook_path': 'nb.ipynb',
                                              'new_source': 'print(1)'})
    assert len(ops) == 1 and ops[0]['path'] == 'nb.ipynb' and ops[0]['op'] == 'write'


# ─── normalizar_payload: robustez (la lección del parser muerto) ──────────────

def test_herramienta_desconocida_no_rompe():
    assert normalizar_payload('Bash', {'command': 'ls'}) == []
    assert normalizar_payload('Grep', {'pattern': 'x'}) == []


def test_payload_basura_no_rompe():
    for basura in (None, {}, {'file_path': ''}, {'no_hay_path': 1}, 'texto', 42, []):
        assert normalizar_payload('Edit', basura) == []
    assert normalizar_payload(None, {'file_path': 'a.py'}) == []


def test_forma_nueva_desconocida_igual_registra_el_archivo():
    """Si el CLI inventa mañana otra forma para el contenido, la op de ESCRITURA
    no se pierde: sin contenido reconocible se registra igual con antes/despues
    vacíos. Perder el detalle es aceptable; perder la propiedad NO (fue el bug
    que mató a agent_live)."""
    ops = normalizar_payload('Edit', {'file_path': 'a.py', 'campo_del_futuro': 'z'})
    assert ops == [{'op': 'write', 'path': 'a.py', 'antes': '', 'despues': ''}]


def test_path_se_normaliza():
    ops = normalizar_payload('Write', {'file_path': './a/b.py', 'content': 'x'})
    assert ops[0]['path'] == 'a/b.py'


# ─── es_sobrescritura_total: la operación que destruye ────────────────────────

def test_write_completo_es_sobrescritura():
    assert es_sobrescritura_total('Write', {'file_path': 'a.py', 'content': 'x'}) is True


def test_edit_por_zona_no_es_sobrescritura():
    assert es_sobrescritura_total('Edit', {'file_path': 'a.py', 'old_string': 'a',
                                           'new_string': 'b'}) is False


def test_read_no_es_sobrescritura():
    assert es_sobrescritura_total('Read', {'file_path': 'a.py'}) is False


# ─── simbolos: qué identificadores define un texto ────────────────────────────

def test_simbolos_de_html_id_y_clases():
    s = simbolos('<div id="bw-cfg-uso-top" class="bw-cfg-fila destacada">x</div>')
    assert 'bw-cfg-uso-top' in s
    assert 'bw-cfg-fila' in s
    assert 'destacada' in s


def test_simbolos_de_selectores_css():
    s = simbolos('.bw-cfg-nota { color: red; }\n#bw-nuevo b { font-weight: 700 }')
    assert 'bw-cfg-nota' in s
    assert 'bw-nuevo' in s


def test_simbolos_de_funciones_js_y_py():
    s = simbolos('function aplicarIdioma() {}\nconst destinoDe = 1\ndef resolver_destino(x):\nclass Motor:')
    for esperado in ('aplicarIdioma', 'destinoDe', 'resolver_destino', 'Motor'):
        assert esperado in s, esperado


def test_simbolos_de_data_attrs():
    assert 'data-bw-page' in simbolos('<style data-bw-page>x</style>')


def test_simbolos_ignora_ruido_corto_y_palabras_comunes():
    s = simbolos('<div id="a" class="x"> function if() {} </div>')
    assert 'a' not in s and 'x' not in s      # <4 chars: ruido
    assert 'if' not in s


def test_simbolos_texto_vacio_o_none():
    assert simbolos('') == set()
    assert simbolos(None) == set()


# ─── Llamadas a método NO son selectores CSS ─────────────────────────────────
# Caso real (2026-07-25): al editar `(pane_cmd or '').strip()`, el regex de
# selectores leyó `.strip` como una clase CSS. Consecuencias medidas: el agente
# se auto-reclamó territorio sobre `strip`, `join` y `append`, y el detector de
# colisiones le avisó a otro que "borraste `strip`, que usa Claude Code #2".
# Un aviso falso es peor que ninguno: entrena a ignorar los avisos de verdad.

def test_metodos_de_stdlib_no_son_simbolos():
    s = simbolos("""
        cmd = (pane_cmd or '').strip().lower()
        partes = ', '.join(nombres)
        out.append(linea)
        datos = json.loads(texto)
    """)
    for falso in ('strip', 'join', 'append', 'loads', 'lower'):
        assert falso not in s, f'`{falso}` es una llamada a método, no una clase CSS'


def test_pero_los_selectores_de_verdad_siguen_contando():
    """El fix no puede volverse ciego a lo que sí importa."""
    s = simbolos("""$('.bw-cfg-uso-top'); document.querySelector('.mi-clase')""")
    assert 'bw-cfg-uso-top' in s
    assert 'mi-clase' in s


def test_una_clase_css_seguida_de_llave_sigue_contando():
    assert 'bw-cfg-nota' in simbolos('.bw-cfg-nota { color: red }')


def test_los_dunders_y_los_nombres_universales_no_son_territorio():
    """Visto en vivo: escribir una clase de test me auto-reclamó `__init__` y
    `__call__`. Con eso, OTRO agente que refactorizara el `__init__` de SU clase
    quedaba bloqueado por el guard, en mi nombre. Un símbolo que existe en todos
    los archivos del mundo no identifica el territorio de nadie."""
    s = simbolos('''
        class X:
            def __init__(self): pass
            def __call__(self): pass
            def __repr__(self): pass
        def main(): pass
        def setup(): pass
    ''')
    for generico in ('__init__', '__call__', '__repr__', 'main', 'setup'):
        assert generico not in s, generico


def test_pero_un_helper_con_nombre_propio_si_es_territorio():
    s = simbolos('def resolver_destino(x): pass\ndef _limpiar_lock(y): pass')
    assert 'resolver_destino' in s and '_limpiar_lock' in s


def test_una_funcion_declarada_no_se_pierde_por_llevar_parentesis():
    """`function aplicarIdioma()` va por _DECL_RE, no por el de selectores: el
    filtro de llamadas no puede llevarse puesta una declaración."""
    s = simbolos('function aplicarIdioma() {}\ndef resolver_destino(x):')
    assert 'aplicarIdioma' in s and 'resolver_destino' in s


# ─── simbolos_perdidos: la señal de colisión de la Fase 2 ─────────────────────

def test_simbolos_perdidos_detecta_borrado():
    """El caso REAL: el agente #3 borró el nodo con id bw-cfg-uso-top y eso
    rompió el aplicarIdioma() del agente #2, que lo referenciaba."""
    antes = '<div class="bw-cfg-uso-top"><span>3 de 10</span></div>'
    despues = ''
    assert 'bw-cfg-uso-top' in simbolos_perdidos(antes, despues)


def test_simbolos_perdidos_detecta_renombre():
    antes = 'function aplicarIdioma() {}'
    despues = 'function aplicarLenguaje() {}'
    perdidos = simbolos_perdidos(antes, despues)
    assert 'aplicarIdioma' in perdidos
    assert 'aplicarLenguaje' not in perdidos


def test_simbolos_perdidos_vacio_si_no_se_borro_nada():
    antes = 'function foo() {}'
    despues = 'function foo() { return 1 }'
    assert simbolos_perdidos(antes, despues) == set()


def test_simbolos_perdidos_agregar_no_pierde():
    assert simbolos_perdidos('', 'function nueva() {}') == set()


if __name__ == '__main__':
    import sys
    import pytest
    sys.exit(pytest.main([__file__, '-q']))
