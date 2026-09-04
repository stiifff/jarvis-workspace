# plotspace/tests/test_colisiones.py
"""Colisión por FUNCIONALIDAD: avisar cuando uno borra algo que otro usa.

EL CASO REAL (está en el MAILBOX del proyecto)
El agente #3 sacó del Builder los nodos de la cuenta/plan falsos. Eso rompió el
`aplicarIdioma()` del agente #2, que apuntaba a `.bw-cfg-uso-top span`. Tareas
distintas, misma superficie. Nadie lo detectó: lo encontró el #2 de casualidad,
porque se le ocurrió abrir el Builder en inglés. Y la propiedad por ARCHIVO no
habría ayudado — el #3 era el dueño legítimo de ese archivo.

La unidad de coordinación no puede ser el path: tiene que ser la superficie que
uno afecta. Acá se testea la señal: qué símbolos borró una edición y quién los
referencia.

Regla de aviso (invertida respecto de la de antes):
  · mismo archivo, zonas distintas       → NO avisar (está medido que conviven)
  · símbolo que uno borra y otro usa     → AVISAR siempre, aunque sean archivos
                                            distintos
"""
from plotspace.core import provenance
from plotspace.core.provenance import colisiones_por_simbolos, simbolos_perdidos


def setup_function():
    provenance.reset()


def test_caso_real_del_builder():
    """El #3 borra el nodo; el #2 lo referencia en su código."""
    provenance.registrar(7, 396, 'Claude Code #2', 'builder.js', 'write',
                         antes='', despues="$('.bw-cfg-uso-top span').textContent = t")
    perdidos = simbolos_perdidos(
        '<div class="bw-cfg-uso-top"><span>3 de 10</span></div>', '')
    col = colisiones_por_simbolos(perdidos, provenance.ediciones(pid=7), tid_propio=397)
    assert col, 'tendría que detectar que otro agente usa ese símbolo'
    assert col[0]['simbolo'] == 'bw-cfg-uso-top'
    assert col[0]['nombre'] == 'Claude Code #2'
    assert col[0]['path'] == 'builder.js'


def test_no_avisa_de_lo_que_yo_mismo_escribi():
    """Borrar algo que solo usa mi propio código no es una colisión."""
    provenance.registrar(7, 397, 'Yo', 'a.js', 'write', despues="usar('.mi-clase')")
    col = colisiones_por_simbolos({'mi-clase'}, provenance.ediciones(pid=7),
                                  tid_propio=397)
    assert col == []


def test_no_avisa_si_nadie_lo_referencia():
    provenance.registrar(7, 396, 'Otro', 'b.js', 'write', despues='cosas sin relación')
    assert colisiones_por_simbolos({'bw-cfg-uso-top'},
                                   provenance.ediciones(pid=7), tid_propio=397) == []


def test_detecta_aunque_esten_en_archivos_DISTINTOS():
    """El corazón del asunto: paths disjuntos, cero conflicto de archivo, y sin
    embargo uno rompe al otro."""
    provenance.registrar(7, 396, 'Otro', 'frontend/estilos.css', 'write',
                         despues='.bw-cfg-nota { color: red }')
    col = colisiones_por_simbolos({'bw-cfg-nota'}, provenance.ediciones(pid=7),
                                  tid_propio=397)
    assert col and col[0]['path'] == 'frontend/estilos.css'


def test_una_colision_por_simbolo_y_agente():
    """Aunque el otro lo use diez veces, se avisa una vez: el ruido es lo que
    hizo que el 32% del tráfico entre agentes fuera protocolo."""
    for i in range(5):
        provenance.registrar(7, 396, 'Otro', f'x{i}.js', 'write',
                             despues="usa('.la-clase')")
    col = colisiones_por_simbolos({'la-clase'}, provenance.ediciones(pid=7),
                                  tid_propio=397)
    assert len(col) == 1


def test_varios_simbolos_perdidos_dan_varias_colisiones():
    provenance.registrar(7, 396, 'Otro', 'a.js', 'write',
                         despues="$('.uno'); $('.dos')")
    col = colisiones_por_simbolos({'uno-largo', 'dos-largo'},
                                  provenance.ediciones(pid=7), tid_propio=397)
    assert col == []      # 'uno'/'dos' no son los símbolos perdidos
    col = colisiones_por_simbolos({'uno', 'dos'}, provenance.ediciones(pid=7),
                                  tid_propio=397)
    assert len(col) == 2


def test_sin_simbolos_perdidos_no_hay_nada_que_mirar():
    provenance.registrar(7, 396, 'Otro', 'a.js', 'write', despues='.x-y-z')
    assert colisiones_por_simbolos(set(), provenance.ediciones(pid=7),
                                   tid_propio=397) == []


def test_ediciones_de_lectura_no_cuentan():
    """Que otro haya LEÍDO el archivo no es una referencia a mi símbolo."""
    provenance.registrar(7, 396, 'Otro', 'a.js', 'read', despues='')
    assert colisiones_por_simbolos({'mi-simbolo'}, provenance.ediciones(
        pid=7, solo_write=False), tid_propio=397) == []


def test_mensaje_para_el_agente_es_accionable():
    """El texto que va a leer el agente tiene que decirle QUÉ rompió y A QUIÉN
    avisarle — un aviso que no dice qué hacer es ruido."""
    from plotspace.core.provenance import texto_aviso_colision
    txt = texto_aviso_colision([
        {'simbolo': 'bw-cfg-uso-top', 'nombre': 'Claude Code #2', 'path': 'builder.js'}])
    assert 'bw-cfg-uso-top' in txt
    assert 'Claude Code #2' in txt
    assert 'builder.js' in txt
    assert 'MAILBOX' in txt


def test_mensaje_vacio_si_no_hay_colisiones():
    from plotspace.core.provenance import texto_aviso_colision
    assert texto_aviso_colision([]) == ''


if __name__ == '__main__':
    import sys
    import pytest
    sys.exit(pytest.main([__file__, '-q']))
