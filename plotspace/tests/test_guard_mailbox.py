"""
Tests: aviso de mailbox en el pre-commit (scripts/guard_mailbox.py).

Warn-only por diseño: el commit es el momento donde un mensaje no leído
duele ("cambié la interfaz que usás"), pero bloquear por eso empujaría al
--no-verify. Un mensaje que menciona un archivo staged va primero y marcado.
"""
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'scripts'))
import guard_mailbox as gmb


def test_mensaje_que_menciona_staged_va_primero_y_marcado():
    msgs = [{'de': 'A', 'msg': 'charla general del proyecto'},
            {'de': 'B', 'msg': 'ojo: cambié la firma en tasks.js'}]
    out = gmb.avisos(msgs, ['frontend/sections/tasks/tasks.js'])
    assert len(out) == 2
    assert 'MENCIONA tasks.js' in out[0] and 'de B' in out[0]
    assert out[1].startswith('📬 de A')


def test_sin_match_todos_normales():
    out = gmb.avisos([{'de': 'A', 'msg': 'hola'}], ['x.py'])
    assert len(out) == 1 and 'MENCIONA' not in out[0]


def test_main_falla_abierto(monkeypatch):
    def explota():
        raise RuntimeError('tmux roto')
    monkeypatch.setattr(gmb.gp, 'detectar_terminal_id', explota)
    assert gmb.main() == 0


if __name__ == '__main__':
    import pytest
    raise SystemExit(pytest.main([__file__, '-q']))
