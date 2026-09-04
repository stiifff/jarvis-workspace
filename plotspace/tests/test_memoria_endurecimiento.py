"""
Test: escalera de endurecimiento — reincidencia de lecciones → candidata a guard.

El último escalón del ciclo error→regla→enforcement: si un motivo de fallo
nuevo matchea una lección que YA existe, la lección 'reincide' (contador++). A
las N reincidencias la salud la marca 'candidata a guard determinista' — el
camino guard_propiedad/scan_secretos, donde ni el LLM más distraído la saltea.
El sistema PROPONE la promoción; decidirla es del usuario.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plotspace.core import memoria_endurecimiento as end


# ─── Matching motivo ↔ lección (puro) ────────────────────────────────────────

def test_motivo_matchea_leccion_por_solape():
    leccion = 'Antes de levantar un server chequeá que el puerto esté libre; el 3000 es de Jarvis.'
    assert end.motivo_matchea('el puerto 3000 ya estaba ocupado, choqué con Jarvis', leccion)
    assert not end.motivo_matchea('falla el import de numpy en el test', leccion)


def test_matching_ignora_palabras_funcion():
    # solape solo en stopwords → NO es match
    assert not end.motivo_matchea('esto es para todos con los que', 'para todos con los de la')


# ─── Agregación de reincidencias (puro) ──────────────────────────────────────

def test_contar_reincidencias():
    lecciones = [
        {'slug': 'puerto-libre', 'texto': 'chequeá el puerto libre antes de levantar server, el 3000 es de jarvis'},
        {'slug': 'git-explicito', 'texto': 'commiteá con rutas explícitas nunca git add todo'},
    ]
    motivos = [
        'el puerto 3000 estaba ocupado y el server no levantó',
        'otra vez choqué el puerto al levantar el server',
        'un import roto sin relación',
    ]
    cuenta = end.contar_reincidencias(lecciones, motivos)
    assert cuenta['puerto-libre'] == 2
    assert cuenta.get('git-explicito', 0) == 0


# ─── Persistencia + candidatas a guard ───────────────────────────────────────

def _mem(d, slug, cuerpo, tags='leccion'):
    mdir = os.path.join(d, '.jarvis', 'memory')
    os.makedirs(mdir, exist_ok=True)
    with open(os.path.join(mdir, slug + '.md'), 'w', encoding='utf-8') as f:
        f.write(f"---\ntitulo: {slug}\ntags: [{tags}]\ncategoria: entorno\nestado: vigente\n---\n\n{cuerpo}\n")


def test_lecciones_del_proyecto_solo_tag_leccion():
    with tempfile.TemporaryDirectory() as d:
        _mem(d, 'una-leccion', 'no levantes server en el puerto 3000', tags='leccion, entorno')
        _mem(d, 'no-leccion', 'esto es referencia comun', tags='referencia')
        lecs = end.lecciones_del_proyecto(d)
        slugs = {l['slug'] for l in lecs}
        assert 'una-leccion' in slugs and 'no-leccion' not in slugs


def test_evaluar_persiste_y_marca_candidata():
    with tempfile.TemporaryDirectory() as d:
        _mem(d, 'puerto-libre', 'chequeá el puerto libre antes de levantar el server; el 3000 es de jarvis')
        estado = os.path.join(d, 'end.json')
        # tres motivos distintos que pegan con la misma lección = 3 reincidencias
        motivos = ['el puerto 3000 estaba ocupado, el server no levantó',
                   'de nuevo el puerto ocupado al levantar el server',
                   'choqué el puerto del server, el 3000 ya estaba tomado']
        r = end.evaluar(d, motivos, umbral=3, estado_path=estado)
        st = json.load(open(estado))
        assert st['puerto-libre'] >= 3
        assert any(c['slug'] == 'puerto-libre' for c in r['candidatas'])
        # idempotente: re-evaluar la MISMA ventana no infla el contador
        end.evaluar(d, motivos, umbral=3, estado_path=estado)
        assert json.load(open(estado))['puerto-libre'] == st['puerto-libre']


def test_candidatas_bajo_umbral_no_aparecen():
    with tempfile.TemporaryDirectory() as d:
        _mem(d, 'poco-vista', 'evitá el patrón X en el server del puerto')
        r = end.evaluar(d, ['el puerto del server falló'], umbral=5,
                        estado_path=os.path.join(d, 'e.json'))
        assert r['candidatas'] == []


if __name__ == '__main__':
    import traceback
    fallos = 0
    for nombre, fn in sorted(globals().items()):
        if nombre.startswith('test_') and callable(fn):
            try:
                fn(); print(f'ok  {nombre}')
            except Exception:
                fallos += 1; print(f'FAIL {nombre}'); traceback.print_exc()
    sys.exit(1 if fallos else 0)
