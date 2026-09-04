# plotspace/tests/test_provenance_snapshot.py
"""El libro de ediciones tiene que SOBREVIVIR al "Actualizar ahora".

QUÉ SE ESTÁ DEFENDIENDO
-----------------------
El update reemplaza el proceso con `os.execv` (mismo PID, imagen nueva): todo lo
que vive en memoria se pierde. El libro de provenance vivía SOLO en memoria, así
que después de cada actualización el enjambre quedaba ciego de golpe: los íconos
de vínculo de todas las cards desaparecían y el overlay se quedaba sin nada que
mostrar, aunque los agentes siguieran trabajando sobre los mismos archivos hacía
diez minutos. Medido en producción: 4 ops en el libro seis minutos después de un
update, con tres agentes escribiendo sin parar.

El snapshot es telemetría viva, no un histórico: se guarda acotado por ventana y
por tamaño, y jamás puede romper ni el arranque ni el reinicio.
"""
import json
import time

from plotspace.core import provenance


def _edicion(tid, path, ts, nombre='Claude Code #1', pid=7):
    provenance.registrar(pid, tid, nombre, path, 'write',
                         antes='', despues='function x() {}', ts=ts)


def test_las_ediciones_sobreviven_al_reinicio(tmp_path):
    """El caso del usuario: actualizar no puede apagar los íconos del enjambre."""
    ruta = tmp_path / 'prov.json'
    provenance.reset()
    ahora = time.time()
    _edicion(400, 'frontend/settings.js', ahora - 60)
    _edicion(401, 'frontend/settings.js', ahora - 30, nombre='Claude Code #2')

    assert provenance.guardar_snapshot(str(ruta)) == 2
    provenance.reset()                       # ← el execv
    assert provenance.ediciones(pid=7) == []

    assert provenance.cargar_snapshot(str(ruta)) == 2
    vueltas = provenance.ediciones(pid=7)
    assert [e['tid'] for e in vueltas] == [400, 401], 'vuelven en orden cronológico'
    assert vueltas[0]['path'] == 'frontend/settings.js'
    assert vueltas[0]['despues'] == 'function x() {}', 'el contenido no se trunca'
    assert vueltas[0]['op'] == 'write'


def test_el_grupo_se_rearma_despues_del_reinicio(tmp_path):
    """La prueba de verdad: el ícono de la card sale de detectar_grupos()."""
    from plotspace.core import swarm_grupos
    ruta = tmp_path / 'prov.json'
    provenance.reset()
    ahora = time.time()
    _edicion(400, 'frontend/settings.js', ahora - 120)
    _edicion(401, 'frontend/settings.js', ahora - 90, nombre='Claude Code #2')
    assert len(swarm_grupos.detectar_grupos(provenance.ediciones(pid=7))) == 1

    provenance.guardar_snapshot(str(ruta))
    provenance.reset()
    assert swarm_grupos.detectar_grupos(provenance.ediciones(pid=7)) == [], \
        'sin snapshot, el enjambre queda ciego (el bug)'

    provenance.cargar_snapshot(str(ruta))
    grupos = swarm_grupos.detectar_grupos(provenance.ediciones(pid=7))
    assert len(grupos) == 1, 'el vínculo vuelve solo al arrancar'
    assert [m['tid'] for m in grupos[0]['miembros']] == [400, 401]


def test_las_colisiones_tambien_sobreviven(tmp_path):
    ruta = tmp_path / 'prov.json'
    provenance.reset()
    provenance.registrar_colision(
        7, 400, 'Claude Code #1', 'a.js',
        [{'simbolo': 'aplicarIdioma', 'tid': 401, 'nombre': 'Claude Code #2',
          'path': 'b.js'}])
    provenance.guardar_snapshot(str(ruta))
    provenance.reset()
    provenance.cargar_snapshot(str(ruta))
    cols = provenance.colisiones(pid=7)
    assert len(cols) == 1 and cols[0]['simbolo'] == 'aplicarIdioma'


def test_no_resucita_ediciones_viejas(tmp_path):
    """Un server apagado toda la noche no puede volver inventando vínculos."""
    ruta = tmp_path / 'prov.json'
    provenance.reset()
    ahora = time.time()
    _edicion(400, 'viejo.js', ahora - provenance.VENTANA_SNAPSHOT_S - 600)
    _edicion(401, 'nuevo.js', ahora - 10)
    assert provenance.guardar_snapshot(str(ruta)) == 1, 'lo viejo no se guarda'

    provenance.reset()
    provenance.cargar_snapshot(str(ruta))
    assert [e['path'] for e in provenance.ediciones()] == ['nuevo.js']


def test_el_snapshot_esta_acotado_en_tamano(tmp_path, monkeypatch):
    """Un Write de 100 KB por edición no puede dejar un archivo de 400 MB."""
    ruta = tmp_path / 'prov.json'
    monkeypatch.setattr(provenance, 'MAX_BYTES_SNAPSHOT', 20_000)
    provenance.reset()
    ahora = time.time()
    for i in range(20):
        provenance.registrar(7, 400, 'A', f'f{i}.js', 'write',
                             despues='x' * 5_000, ts=ahora - (20 - i))
    n = provenance.guardar_snapshot(str(ruta))
    assert 0 < n < 20, 'entra lo que entra, no todo'
    assert ruta.stat().st_size <= 40_000

    provenance.reset()
    provenance.cargar_snapshot(str(ruta))
    paths = [e['path'] for e in provenance.ediciones()]
    assert paths[-1] == 'f19.js', 'se conserva lo MÁS NUEVO (lo que arma grupos hoy)'


def test_cargar_nunca_rompe_el_arranque(tmp_path):
    """Falla abierto: sin archivo, con basura o con JSON de otra forma."""
    provenance.reset()
    assert provenance.cargar_snapshot(str(tmp_path / 'no-existe.json')) == 0

    roto = tmp_path / 'roto.json'
    roto.write_text('{esto no es json', encoding='utf-8')
    assert provenance.cargar_snapshot(str(roto)) == 0

    raro = tmp_path / 'raro.json'
    raro.write_text(json.dumps({'ediciones': 'no soy una lista'}), encoding='utf-8')
    assert provenance.cargar_snapshot(str(raro)) == 0
    assert provenance.ediciones() == []


def test_un_libro_vacio_no_pisa_un_snapshot_bueno(tmp_path):
    """Guardar NADA no puede borrar lo que había: es el mismo error que dejó sin
    Builder al usuario (un estado vacío tratado como estado válido).

    Pasa de verdad: un arranque sin escrituras todavía, o un reinicio encadenado.
    Y de yapa, evita que los tests que levantan el lifespan escriban en el
    `data/` real del usuario."""
    ruta = tmp_path / 'prov.json'
    provenance.reset()
    _edicion(400, 'frontend/settings.js', time.time() - 20)
    assert provenance.guardar_snapshot(str(ruta)) == 1

    provenance.reset()                          # libro vacío (nadie escribió aún)
    assert provenance.guardar_snapshot(str(ruta)) == 0, 'no escribe nada'
    guardado = json.loads(ruta.read_text(encoding='utf-8'))
    assert [e['path'] for e in guardado['ediciones']] == ['frontend/settings.js'], \
        'el snapshot bueno sigue intacto'

    # Y un snapshot que nunca existió tampoco se crea vacío.
    nueva = tmp_path / 'no-deberia-nacer.json'
    assert provenance.guardar_snapshot(str(nueva)) == 0
    assert not nueva.exists()


def test_cargar_no_duplica_sobre_un_libro_vivo(tmp_path):
    """Solo repuebla un libro VACÍO: cargar dos veces no clona las ediciones."""
    ruta = tmp_path / 'prov.json'
    provenance.reset()
    _edicion(400, 'a.js', time.time() - 5)
    provenance.guardar_snapshot(str(ruta))
    provenance.reset()

    assert provenance.cargar_snapshot(str(ruta)) == 1
    assert provenance.cargar_snapshot(str(ruta)) == 0, 'segunda carga: no-op'
    assert len(provenance.ediciones()) == 1


def test_guardar_nunca_rompe_el_reinicio(tmp_path):
    """Un disco lleno o un path imposible NO puede frenar el update."""
    provenance.reset()
    _edicion(400, 'a.js', time.time())
    assert provenance.guardar_snapshot(str(tmp_path / 'no' / 'existe' / 'x.json')) == 0


def test_el_boton_actualizar_ahora_vuelca_el_libro(tmp_path, monkeypatch):
    """El cableado del caso real: `_reexec()` guarda ANTES del execv.

    Es el único momento en que se puede: el execv no dispara el shutdown del
    lifespan, así que si no se vuelca acá el libro se pierde entero."""
    from plotspace.routers import system

    ruta = tmp_path / 'prov.json'
    monkeypatch.setattr(provenance, 'RUTA_SNAPSHOT', str(ruta))
    provenance.reset()
    _edicion(400, 'frontend/settings.js', time.time() - 20)

    class _Exec(Exception):
        pass

    def _no_exec(*a, **k):
        raise _Exec()
    monkeypatch.setattr(system.os, 'execv', _no_exec)
    monkeypatch.setattr(system.os, 'chdir', lambda *a, **k: None)

    try:
        system._reexec()
    except _Exec:
        pass

    assert ruta.exists(), 'el update se llevó el libro puesto'
    guardado = json.loads(ruta.read_text(encoding='utf-8'))
    assert [e['path'] for e in guardado['ediciones']] == ['frontend/settings.js']
