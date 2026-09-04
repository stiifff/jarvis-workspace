# plotspace/tests/test_codex_watch.py
"""Poller que tailea los rollouts de Codex y correlaciona rollout↔terminal.

Codex no tiene hook útil (edita con apply_patch, fuera del gate de PostToolUse),
pero escribe cada edición en el rollout JSONL. Este poller lo tailea. Dos piezas
PURAS (testeables sin tmux/DB/red):
  · asignar_rollouts: empareja cada rollout con SU terminal por cwd + cercanía
    temporal (varios Codex en el mismo proyecto comparten cwd → desempata la hora).
  · ops_nuevas_de_rollout: lee SOLO las líneas nuevas (por offset de bytes) y saca
    las ediciones de los patch_apply_end.
El resto (glob de homes, llamar a swarm_op) es wiring probado por el pattern.
"""
from plotspace.core import codex_watch as cw


# ─── asignar_rollouts: rollout ↔ terminal por cwd + cercanía temporal ─────────

def test_un_rollout_un_terminal_mismo_cwd():
    asign = cw.asignar_rollouts(
        [{'path': 'r1', 'cwd': '/proj/a', 'ts': 100}],
        [{'tid': 5, 'cwd': '/proj/a', 'creada_ts': 98}])
    assert asign == {'r1': 5}


def test_sin_cwd_en_comun_no_asigna():
    asign = cw.asignar_rollouts(
        [{'path': 'r1', 'cwd': '/proj/a', 'ts': 100}],
        [{'tid': 5, 'cwd': '/otro', 'creada_ts': 100}])
    assert asign == {}


def test_dos_codex_mismo_proyecto_desempata_por_hora():
    """Dos Codex en el mismo cwd: cada rollout va al terminal creado más cerca
    en el tiempo (el rollout arranca ~cuando se creó la terminal)."""
    rollouts = [{'path': 'rA', 'cwd': '/p', 'ts': 100},
                {'path': 'rB', 'cwd': '/p', 'ts': 200}]
    terminales = [{'tid': 1, 'cwd': '/p', 'creada_ts': 205},
                  {'tid': 2, 'cwd': '/p', 'creada_ts': 102}]
    asign = cw.asignar_rollouts(rollouts, terminales)
    assert asign == {'rA': 2, 'rB': 1}      # rA↔#2 (100~102), rB↔#1 (200~205)


def test_un_terminal_no_toma_dos_rollouts():
    """Un rollout viejo de una sesión previa (mismo cwd) NO se le asigna al
    terminal si ya tomó el suyo (el más cercano). El viejo queda sin asignar."""
    rollouts = [{'path': 'viejo', 'cwd': '/p', 'ts': 10},
                {'path': 'actual', 'cwd': '/p', 'ts': 200}]
    terminales = [{'tid': 9, 'cwd': '/p', 'creada_ts': 198}]
    asign = cw.asignar_rollouts(rollouts, terminales)
    assert asign == {'actual': 9}           # 'viejo' queda afuera


# ─── ops_nuevas_de_rollout: lectura incremental por offset ────────────────────

_META = ('{"type":"session_meta","payload":{"id":"u","cwd":"/p"}}\n')
_PATCH = ('{"type":"event_msg","payload":{"type":"patch_apply_end","success":true,'
          '"changes":{"/p/x.py":{"type":"update","unified_diff":"@@ -1 +1 @@\\n-a\\n+b"}}}}\n')


def test_ops_nuevas_desde_cero(tmp_path):
    f = tmp_path / 'rollout.jsonl'
    f.write_text(_META + _PATCH, encoding='utf-8')
    ops, off = cw.ops_nuevas_de_rollout(str(f), 0)
    assert len(ops) == 1
    ruta, antes, despues, sobre = ops[0]
    assert ruta == '/p/x.py' and antes == 'a' and despues == 'b'
    assert off == len((_META + _PATCH).encode('utf-8'))


def test_ops_nuevas_solo_lo_agregado(tmp_path):
    f = tmp_path / 'rollout.jsonl'
    f.write_text(_META, encoding='utf-8')
    _, off = cw.ops_nuevas_de_rollout(str(f), 0)          # baseline: solo meta, 0 ops
    with open(f, 'a', encoding='utf-8') as fp:
        fp.write(_PATCH)
    ops, off2 = cw.ops_nuevas_de_rollout(str(f), off)
    assert len(ops) == 1 and off2 > off                   # solo el patch nuevo


def test_ops_nuevas_no_consume_linea_a_medias(tmp_path):
    f = tmp_path / 'rollout.jsonl'
    f.write_bytes(_META.encode('utf-8') + _PATCH.rstrip('\n').encode('utf-8'))  # sin \n final
    ops, off = cw.ops_nuevas_de_rollout(str(f), 0)
    assert len(ops) == 0                                  # el patch a medias no se consume
    assert off == len(_META.encode('utf-8'))              # el offset queda antes del patch


def test_ops_nuevas_archivo_inexistente_no_rompe(tmp_path):
    ops, off = cw.ops_nuevas_de_rollout(str(tmp_path / 'no-existe.jsonl'), 0)
    assert ops == [] and off == 0


if __name__ == '__main__':
    import sys
    import pytest
    sys.exit(pytest.main([__file__, '-q']))
