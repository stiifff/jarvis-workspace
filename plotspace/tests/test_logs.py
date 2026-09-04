"""Logger estructurado del swarm (core/logs.py): escribir + leer/filtrar + no romper.

AISLADO del data/jarvis.log real: antes cada corrida de suite appendeaba
test_evt/test_err_evt/test_raro al audit trail vivo (834+ líneas de ruido
medidas 2026-07-10) — y ese log es ahora el corpus de señales del sistema de
memoria (lecciones, cuarentena). Los tests repuntan _LOG_PATH a un tempfile.
"""
import os
import tempfile
from contextlib import contextmanager

from plotspace.core import logs


@contextmanager
def _log_aislado():
    fd, path = tempfile.mkstemp(suffix='.log', prefix='jarvis_test_')
    os.close(fd)
    orig = logs._LOG_PATH
    logs._LOG_PATH = path
    try:
        yield path
    finally:
        logs._LOG_PATH = orig
        try:
            os.remove(path)
        except OSError:
            pass


def test_evento_y_leer_recientes():
    with _log_aislado():
        logs.evento('test_evt', terminal_id=4242, foo='bar')
        recientes = logs.leer_recientes(20, tipo='test_evt')
        assert any(r.get('terminal_id') == 4242 and r.get('foo') == 'bar' for r in recientes)


def test_filtro_por_nivel():
    with _log_aislado():
        logs.evento('test_err_evt', nivel='error', detalle='boom')
        errs = logs.leer_recientes(20, nivel='error')
        assert any(r.get('evento') == 'test_err_evt' for r in errs)


def test_no_rompe_con_no_serializable():
    with _log_aislado():
        class X:  # no JSON-serializable
            pass
        logs.evento('test_raro', obj=X())   # default=str lo maneja → no debe lanzar


def test_no_toca_el_log_real():
    """El candado de este archivo: escribir con el path aislado no debe crear
    ni engordar el data/jarvis.log del producto."""
    real = logs._LOG_PATH
    tam_antes = os.path.getsize(real) if os.path.exists(real) else 0
    with _log_aislado():
        logs.evento('test_evt_aislado', n=1)
    tam_despues = os.path.getsize(real) if os.path.exists(real) else 0
    assert tam_antes == tam_despues, "el test ensució el jarvis.log real"


if __name__ == "__main__":
    test_evento_y_leer_recientes(); print("  OK evento")
    test_filtro_por_nivel(); print("  OK nivel")
    test_no_rompe_con_no_serializable(); print("  OK no-serializable")
    test_no_toca_el_log_real(); print("  OK aislamiento")
    print("test_logs: TODOS OK")
