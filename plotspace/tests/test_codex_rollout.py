# plotspace/tests/test_codex_rollout.py
"""Parser del rollout JSONL de Codex (core/codex_rollout.py).

Codex edita con la herramienta `apply_patch`, que NO pasa por el gate de los
hooks PostToolUse — así que la provenance de Codex NO puede venir por hook (como
Claude/opencode). Pero cada edición queda escrita en el rollout de la sesión
(`$CODEX_HOME/sessions/**/rollout-*.jsonl`) como un evento `patch_apply_end` con
la ruta ABSOLUTA y el `unified_diff`. Este parser lee ese formato (verificado
contra rollouts reales en disco, codex-cli 0.144.0). Lógica pura: sin red ni DB.
"""
from plotspace.core import codex_rollout as cr

META = ('{"type":"session_meta","timestamp":"2026-06-22T01:08:24Z","payload":'
        '{"id":"abc-uuid","cwd":"/home/user/jarvis","cli_version":"0.144.0"}}')
PATCH = ('{"type":"event_msg","timestamp":"2026-06-22T04:23:53Z","payload":'
         '{"type":"patch_apply_end","call_id":"c1","turn_id":"t1","success":true,'
         '"status":"completed","changes":{"/home/user/jarvis/x.py":{"type":"update",'
         '"unified_diff":"@@ -1,2 +1,2 @@\\n-def foo():\\n+def foo(bar):\\n ctx"}}}}')


def test_session_meta_extrae_id_y_cwd():
    assert cr.session_meta(cr.parse_linea(META)) == {'id': 'abc-uuid', 'cwd': '/home/user/jarvis'}


def test_una_linea_de_patch_no_es_session_meta():
    assert cr.session_meta(cr.parse_linea(PATCH)) is None


def test_patch_changes_de_un_patch_apply_end():
    ch = cr.patch_changes(cr.parse_linea(PATCH))
    assert ch and '/home/user/jarvis/x.py' in ch


def test_patch_apply_fallido_no_da_changes():
    """Una edición que falló no cambió nada: no se registra."""
    fail = PATCH.replace('"success":true', '"success":false')
    assert cr.patch_changes(cr.parse_linea(fail)) is None


def test_una_linea_que_no_es_patch_no_da_changes():
    assert cr.patch_changes(cr.parse_linea(META)) is None


def test_diff_antes_despues_separa_borrado_de_agregado():
    antes, despues = cr.diff_antes_despues("@@ -1,2 +1,2 @@\n-def foo():\n+def foo(bar):\n ctx")
    assert 'def foo():' in antes and 'def foo():' not in despues
    assert 'def foo(bar):' in despues and 'def foo(bar):' not in antes
    assert 'ctx' in antes and 'ctx' in despues        # el contexto va a los dos lados


def test_changes_a_ops_update():
    ops = cr.changes_a_ops({'/x.py': {'type': 'update',
                                      'unified_diff': '@@ -1 +1 @@\n-a\n+b'}})
    assert ops == [{'op': 'write', 'path': '/x.py', 'antes': 'a', 'despues': 'b',
                    'sobrescritura': False}]


def test_changes_a_ops_add_es_sobrescritura():
    ops = cr.changes_a_ops({'/n.py': {'type': 'add', 'unified_diff': '@@ -0,0 +1 @@\n+nuevo'}})
    assert ops[0]['despues'] == 'nuevo' and ops[0]['antes'] == ''
    assert ops[0]['sobrescritura'] is True


def test_changes_a_ops_delete_pone_todo_en_antes():
    ops = cr.changes_a_ops({'/d.py': {'type': 'delete', 'unified_diff': '@@ -1 +0,0 @@\n-viejo'}})
    assert ops[0]['antes'] == 'viejo' and ops[0]['despues'] == ''


def test_changes_a_ops_multi_archivo():
    ops = cr.changes_a_ops({
        '/a.py': {'type': 'update', 'unified_diff': '@@ -1 +1 @@\n-x\n+y'},
        '/b.py': {'type': 'add', 'unified_diff': '@@ -0,0 +1 @@\n+z'}})
    assert {o['path'] for o in ops} == {'/a.py', '/b.py'}


def test_robustez_basura_no_rompe():
    assert cr.parse_linea('no es json {') is None
    assert cr.patch_changes(None) is None
    assert cr.session_meta(None) is None
    assert cr.changes_a_ops(None) == []
    assert cr.changes_a_ops({'/x': 'no-dict'}) == []
    assert cr.diff_antes_despues(None) == ('', '')


if __name__ == '__main__':
    import sys
    import pytest
    sys.exit(pytest.main([__file__, '-q']))
