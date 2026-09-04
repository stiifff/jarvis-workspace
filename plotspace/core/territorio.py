# plotspace/core/territorio.py
"""Territorio del enjambre — que la colisión no llegue a pasar.

EL PRINCIPIO
------------
Un territorio se reclama por NOMBRE: un símbolo (`aplicarIdioma`,
`bw-cfg-uso-top`), un archivo o una carpeta. **Nunca por número de línea.** Las
líneas se mueven: apenas alguien inserta diez líneas arriba, el rango del otro
quedó mal. En este repo eso ya costó una función borrada — un agente filtró sus
cambios por «línea >= 4400» y se llevó puesta una que vivía en la 5739.

QUÉ SE BLOQUEA (y qué no, que es igual de importante)
-----------------------------------------------------
  ✗ Borrar o renombrar un símbolo que otro reclamó  → BLOQUEA. Es el caso real
    que costó un bug encontrado de casualidad.
  ✗ Escribir dentro de una RUTA que otro reclamó explícitamente → BLOQUEA.
    Reclamar una ruta es una declaración fuerte y deliberada.
  ✓ Referenciar un símbolo ajeno (llamar a su función) → PASA. Bloquear esto
    sería el falso positivo más molesto posible.
  ✓ Editar otra zona de un archivo que otro también toca → PASA. Está medido
    que dos ediciones en zonas distintas conviven perfecto; bloquear acá
    reintroduce el ruido que hizo que el 32% del tráfico fuera pedir permisos.

AMPLIACIÓN AUTOMÁTICA
---------------------
Lo que nadie reclamó se concede solo, en el momento, sin preguntarle a nadie: al
escribir, el agente se queda con los símbolos que DECLARÓ. Sin esto la
prevención se vuelve una cárcel — un agente no siempre sabe de antemano qué va a
tener que tocar, y se pasaría el día pidiendo permiso.

Ojo con lo que NO se auto-reclama: el archivo. Si tocar un archivo lo hiciera
tuyo, el segundo agente que entrara a otra zona quedaría bloqueado.
"""
import json
import os
import threading
import time

from plotspace.core.provenance import simbolos, simbolos_perdidos

TTL_S = 1800          # 30 min sin renovar y el territorio se libera

_lock = threading.Lock()
_reclamos: dict = {}  # (pid, patron) → {'tid','nombre','ts','explicito'}


def _limpiar(p):
    return str(p).strip() if p is not None else ''


def _vigente(r, ahora):
    return bool(r) and (ahora - r['ts']) < TTL_S


def duenio(pid, patron, ahora=None):
    """Dueño vigente de un patrón exacto, o None."""
    ahora = time.time() if ahora is None else ahora
    with _lock:
        r = _reclamos.get((pid, _limpiar(patron)))
    return dict(r) if _vigente(r, ahora) else None


def reclamar(pid, tid, nombre, patrones, ts=None, explicito=True):
    """Reclama territorio. Devuelve {otorgados, ocupados}: lo libre se concede,
    lo ajeno se informa con su dueño (no se roba nunca)."""
    ahora = time.time() if ts is None else ts
    otorgados, ocupados = [], []
    with _lock:
        for p in (patrones or []):
            pat = _limpiar(p)
            if not pat:
                continue
            r = _reclamos.get((pid, pat))
            if _vigente(r, ahora) and r['tid'] != tid:
                ocupados.append({'patron': pat, 'de': r['nombre']})
                continue
            _reclamos[(pid, pat)] = {'tid': tid, 'nombre': nombre or '',
                                     'ts': ahora, 'explicito': explicito}
            otorgados.append(pat)
    return {'otorgados': otorgados, 'ocupados': ocupados}


def soltar(pid, tid, patrones):
    """Libera territorio propio (lo ajeno no se toca)."""
    with _lock:
        for p in (patrones or []):
            clave = (pid, _limpiar(p))
            if _reclamos.get(clave, {}).get('tid') == tid:
                _reclamos.pop(clave, None)


def purgar_terminal(tid):
    """La terminal murió: su territorio queda libre."""
    with _lock:
        for clave in [k for k, v in _reclamos.items() if v['tid'] == tid]:
            _reclamos.pop(clave, None)


def reclamos(pid=None, ahora=None):
    """Territorio vigente, para el panel y `jv estado`."""
    ahora = time.time() if ahora is None else ahora
    with _lock:
        datos = list(_reclamos.items())
    return [{'patron': pat, **r} for (p, pat), r in datos
            if (pid is None or p == pid) and _vigente(r, ahora)]


# ─── Chequeo previo ───────────────────────────────────────────────────────────

def _cubre_ruta(patron, path):
    """¿El patrón reclama esta ruta? Exacta, o carpeta que la contiene."""
    if not patron or not path:
        return False
    if patron == path:
        return True
    if patron.endswith('/'):
        return path.startswith(patron)
    return path.startswith(patron + '/')


def chequear(pid, tid, path, antes='', despues='', ahora=None):
    """¿Esta edición pisa territorio ajeno? None si puede seguir; si no, un
    dict con el motivo y el dueño (el texto lo lee el agente, así que dice qué
    hacer, no solo que no puede)."""
    ahora = time.time() if ahora is None else ahora
    path = _limpiar(path)
    vigentes = [(pat, r) for (p, pat), r in
                [((k[0], k[1]), v) for k, v in _reclamos.items()]
                if p == pid and _vigente(r, ahora) and r['tid'] != tid]
    if not vigentes:
        return None

    # 1. Ruta reclamada explícitamente por otro.
    for pat, r in vigentes:
        if r.get('explicito') and _cubre_ruta(pat, path):
            return {'motivo': (
                f"`{path}` es territorio de {r['nombre']}, que lo reclamó "
                f"explícitamente. Pedile por .jarvis/MAILBOX.md antes de tocarlo "
                f"(o esperá: el reclamo vence solo)."), 'dueno': r['nombre'],
                'patron': pat}

    # 2. Borrar o renombrar un símbolo ajeno. Solo lo que DESAPARECE — usar el
    #    símbolo del otro (llamar a su función) es trabajo normal y pasa.
    perdidos = simbolos_perdidos(antes, despues)
    if perdidos:
        for pat, r in vigentes:
            if pat in perdidos:
                return {'motivo': (
                    f"Estás por borrar o renombrar `{pat}`, que es de "
                    f"{r['nombre']}. Si de verdad tiene que irse, avisale por "
                    f".jarvis/MAILBOX.md y que lo adapte él — si lo sacás ahora, "
                    f"su código se rompe sin que se entere."),
                    'dueno': r['nombre'], 'patron': pat}
    return None


def registrar_escritura(pid, tid, nombre, path, antes='', despues='', ts=None):
    """Ampliación automática: al escribir, el agente se queda con los símbolos
    que DECLARÓ y que no tengan dueño. Silencioso y sin preguntar — es lo que
    hace que la prevención no se vuelva una cárcel.

    NO se auto-reclama el archivo: si tocarlo lo hiciera tuyo, el segundo agente
    que entrara a otra zona quedaría bloqueado sin motivo."""
    nuevos = simbolos(despues or '')
    if not nuevos:
        return {'otorgados': [], 'ocupados': []}
    return reclamar(pid, tid, nombre, sorted(nuevos), ts=ts, explicito=False)


# ─── Snapshot: que los reclamos sobrevivan al re-exec del updater ────────────
# 'Actualizar ahora' reemplaza el proceso (os.execv, mismo PID): la memoria se va
# entera. Sin esto, cada update borraba el territorio de TODOS hasta que
# reescribieran, y el guard de commits quedaba un rato sin dueños que defender.
# `ts` es reloj de pared (time.time()), así que sobrevive intacto al re-exec.

RUTA_SNAPSHOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'data', 'swarm-territorio.json')


def guardar_snapshot(ruta=None, ahora=None) -> int:
    """Vuelca los reclamos VIGENTES a disco. Devuelve cuántos guardó (0 si falló o
    no había ninguno). Best-effort: lo llama el updater justo antes del execv, y
    un error acá jamás puede frenar una actualización."""
    ruta = ruta or RUTA_SNAPSHOT
    ahora = time.time() if ahora is None else ahora
    try:
        with _lock:
            items = [{'pid': p, 'patron': pat, **r}
                     for (p, pat), r in _reclamos.items() if _vigente(r, ahora)]
        # Guardar NADA no puede borrar un snapshot bueno: un arranque sin reclamos
        # o un reinicio encadenado no deben dejar el snapshot en cero (el mismo
        # error que una vez borró el Builder — un estado vacío tratado como válido).
        if not items:
            return 0
        tmp = ruta + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump({'v': 1, 'ts': ahora, 'reclamos': items}, f, ensure_ascii=False)
        os.replace(tmp, ruta)          # atómico: nunca se lee un archivo a medias
        return len(items)
    except Exception as e:
        print(f'[territorio] snapshot no guardado: {e}')
        return 0


def cargar_snapshot(ruta=None, ahora=None) -> int:
    """Repuebla los reclamos al arrancar. Devuelve cuántos cargó. Falla ABIERTA (0)
    ante cualquier cosa rara; no duplica si ya hay estado vivo; solo restaura los
    que siguen dentro del TTL (no resucita territorio ya muerto)."""
    ruta = ruta or RUTA_SNAPSHOT
    ahora = time.time() if ahora is None else ahora
    try:
        with _lock:
            if _reclamos:
                return 0               # estado vivo: no pisar ni duplicar
        with open(ruta, encoding='utf-8') as f:
            datos = json.load(f)
        items = datos.get('reclamos') if isinstance(datos, dict) else None
        if not isinstance(items, list):
            return 0
        n = 0
        with _lock:
            for it in items:
                if not isinstance(it, dict):
                    continue
                pid, pat = it.get('pid'), it.get('patron')
                if pid is None or not pat or it.get('tid') is None:
                    continue
                if (ahora - it.get('ts', 0)) >= TTL_S:
                    continue           # ya vencido: no lo resucito
                _reclamos[(pid, _limpiar(pat))] = {
                    'tid': it['tid'], 'nombre': it.get('nombre', ''),
                    'ts': it.get('ts', ahora), 'explicito': bool(it.get('explicito')),
                }
                n += 1
        return n
    except FileNotFoundError:
        return 0
    except Exception as e:
        print(f'[territorio] snapshot no leído ({ruta}): {e}')
        return 0


def reset():
    """Solo para tests."""
    with _lock:
        _reclamos.clear()
