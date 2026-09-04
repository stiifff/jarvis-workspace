# plotspace/tests/test_provenance_salud.py
"""Canario de la provenance: detectar que se rompió, ANTES de que cueste caro.

El sistema anterior (parseo de panes) se murió en silencio y nadie se enteró
durante horas: los tests seguían verdes porque usaban fixtures con el formato
viejo hardcodeado, y en producción se detectaban CERO operaciones.

La defensa es doble y las dos se testean acá:
  1. `formato_sospechoso`: el payload llegó, es de una herramienta de ESCRITURA,
     y aun así no pudimos sacarle una ruta → el contrato del CLI cambió. Es la
     señal temprana exacta que faltó la vez pasada.
  2. `salud`: contadores vivos (ops, formatos raros, última op) para responder
     "¿esto está funcionando ahora mismo?" sin adivinar.
"""
from plotspace.core import provenance
from plotspace.core.provenance import formato_sospechoso, salud, normalizar_payload


def setup_function():
    provenance.reset()


# ─── formato_sospechoso: el detector de drift del contrato ────────────────────

def test_payload_bueno_no_es_sospechoso():
    assert formato_sospechoso('Edit', {'file_path': 'a.py', 'old_string': 'x',
                                       'new_string': 'y'}) is None


def test_herramienta_de_escritura_sin_ruta_es_sospechosa():
    """El caso que importa: mañana el CLI renombra `file_path` y esto lo canta
    en la primera edición, en vez de dejarnos ciegos por horas."""
    motivo = formato_sospechoso('Write', {'archivo_destino': 'a.py', 'texto': 'x'})
    assert motivo and 'ruta' in motivo.lower()


def test_herramienta_no_de_archivos_no_es_sospechosa():
    """Bash/Grep no tienen ruta y está perfecto: no son falsos positivos."""
    assert formato_sospechoso('Bash', {'command': 'ls'}) is None
    assert formato_sospechoso('Grep', {'pattern': 'x'}) is None


def test_escritura_sin_contenido_reconocible_es_sospechosa_pero_no_ciega():
    """Se registra igual la propiedad (no perdemos lo esencial) PERO se avisa:
    el detalle del hunk se está perdiendo y con él el commit por hunk."""
    ti = {'file_path': 'a.py', 'campo_del_futuro': 'z'}
    assert normalizar_payload('Edit', ti)[0]['path'] == 'a.py'
    motivo = formato_sospechoso('Edit', ti)
    assert motivo and 'contenido' in motivo.lower()


def test_payload_no_dict_es_sospechoso():
    assert formato_sospechoso('Edit', None) is not None


def test_borrar_contenido_NO_es_formato_raro():
    """Falso positivo encontrado en la prueba end-to-end: una edición que borra
    trae `new_string: ""` de forma legítima, y el canario la marcaba como
    contrato cambiado. El canario canta cuando cambia el CONTRATO, nunca cuando
    el agente borra algo."""
    assert formato_sospechoso('Edit', {'file_path': 'index.html',
                                       'old_string': '<div>x</div>',
                                       'new_string': ''}) is None


def test_write_de_archivo_vacio_NO_es_formato_raro():
    assert formato_sospechoso('Write', {'file_path': 'vacio.txt',
                                        'content': ''}) is None


def test_edits_con_borrado_NO_es_formato_raro():
    assert formato_sospechoso('Edit', {'file_path': 'a.js', 'edits': [
        {'old_text': 'viejo', 'new_text': ''}]}) is None


# ─── salud: contadores vivos ──────────────────────────────────────────────────

def test_salud_arranca_vacia():
    s = salud()
    assert s['ops'] == 0 and s['ultima_op_ts'] is None and s['formatos_raros'] == 0


def test_salud_cuenta_ops_registradas():
    provenance.registrar(7, 1, 'A', 'a.py', 'write', despues='x')
    provenance.registrar(7, 1, 'A', 'b.py', 'write', despues='y')
    s = salud()
    assert s['ops'] == 2
    assert s['ultima_op_ts'] is not None
    assert s['archivos'] == 2
    assert s['agentes'] == 1


def test_salud_cuenta_formatos_raros():
    provenance.contar_formato_raro('Write', 'sin ruta')
    provenance.contar_formato_raro('Write', 'sin ruta')
    assert salud()['formatos_raros'] == 2
    assert 'Write' in salud()['ultimo_formato_raro']


def test_salud_muda_cuando_no_hubo_ops():
    """`muda` es la bandera que mira el humano: hubo escrituras reportadas o no."""
    assert salud()['muda'] is True
    provenance.registrar(7, 1, 'A', 'a.py', 'write', despues='x')
    assert salud()['muda'] is False


def test_reset_limpia_contadores():
    provenance.registrar(7, 1, 'A', 'a.py', 'write', despues='x')
    provenance.contar_formato_raro('Write', 'x')
    provenance.contar_aviso_colision()
    provenance.reset()
    s = salud()
    assert s['ops'] == 0 and s['formatos_raros'] == 0
    assert s['avisos_colision_emitidos'] == 0


def test_salud_cuenta_avisos_de_colision():
    """El path de aviso de colisión, ahora OBSERVABLE en salud: cuántos se
    emitieron y cuándo. Antes salud solo veía el lado de ENTRADA (ops, formatos
    raros); si el aviso al agente se moría, salud quedaba en verde igual."""
    assert salud()['avisos_colision_emitidos'] == 0
    assert salud()['ultimo_aviso_colision_ts'] is None
    provenance.contar_aviso_colision()
    provenance.contar_aviso_colision()
    s = salud()
    assert s['avisos_colision_emitidos'] == 2
    assert s['ultimo_aviso_colision_ts'] is not None


if __name__ == '__main__':
    import sys
    import pytest
    sys.exit(pytest.main([__file__, '-q']))
