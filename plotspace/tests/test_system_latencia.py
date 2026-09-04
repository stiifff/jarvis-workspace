"""
Latencia de /api/system/version (auditoría 2026-07-02, hallazgo #1 de performance).

Congela tres propiedades:
1. El trabajo git de /version corre FUERA del hilo del event loop (to_thread):
   bajo carga, _estado_git() tardó hasta 22.9s — en el loop eso congela el eco
   de TODAS las terminales a la vez.
2. Cache TTL ~30s con anti-estampida: N pestañas polleando /version no
   multiplican los subprocess git; el cache se invalida por TTL o si
   _estado_git fue reemplazado (monkeypatch de otros tests).
3. La firma de boot NO se computa al importar el módulo (medido 3.07s de import
   bajo carga): es lazy + hilo de captura, y respeta valores ya seteados.

/restart NO usa el cache: decide el bump de versión con estado git fresco.
"""
import asyncio
import threading
import time

from plotspace.routers import system


def _reset_cache():
    system._git_cache = {'fn': None, 'ts': 0.0, 'val': None}


# ─── 1. /version fuera del hilo del loop ─────────────────────────────────────

def test_version_no_corre_git_en_el_hilo_del_loop(monkeypatch):
    hilos = []

    def espia():
        hilos.append(threading.current_thread())
        return (False, '', [])

    monkeypatch.setattr(system, '_estado_git', espia)
    _reset_cache()
    hilo_loop = []

    async def correr():
        hilo_loop.append(threading.current_thread())
        return await system.version()

    d = asyncio.run(correr())
    assert d['hay_update'] is False
    assert hilos, 'el endpoint no llamó a _estado_git'
    assert hilos[0] is not hilo_loop[0], \
        '_estado_git corrió EN el hilo del event loop (debe ir por to_thread)'


def test_version_payload_conserva_campos(monkeypatch):
    # El refactor a to_thread no puede cambiar la forma del payload.
    monkeypatch.setattr(system, '_estado_git', lambda: (False, '', []))
    _reset_cache()
    d = asyncio.run(system.version())
    for campo in ('corriendo', 'disponible', 'proxima', 'hay_update',
                  'agentes_trabajando', 'titulo', 'novedades',
                  'event_loop', 'loop_degradado'):
        assert campo in d, f'falta el campo {campo}'


# ─── 2. Cache TTL + anti-estampida ───────────────────────────────────────────

def test_cache_ttl_evita_git_repetido(monkeypatch):
    n = {'v': 0}

    def contador():
        n['v'] += 1
        return (False, '', [])

    monkeypatch.setattr(system, '_estado_git', contador)
    _reset_cache()
    for _ in range(6):
        system._snapshot_git()
    assert n['v'] == 1, f'esperaba 1 corrida de git, hubo {n["v"]}'


def test_cache_expira_por_ttl(monkeypatch):
    n = {'v': 0}

    def contador():
        n['v'] += 1
        return (False, '', [])

    monkeypatch.setattr(system, '_estado_git', contador)
    _reset_cache()
    system._snapshot_git()
    system._git_cache = dict(system._git_cache, ts=time.monotonic() - 9999)
    system._snapshot_git()
    assert n['v'] == 2


def test_invalidar_cache_git_fuerza_recomputo(monkeypatch):
    # fe_watch la llama al detectar un commit nuevo, ANTES de avisar al browser:
    # el re-chequeo del banner tiene que ver git FRESCO, no el snapshot de hasta
    # 30s de antes del commit (con cache viejo, hay_update salía false y el
    # banner recién aparecía en el poll de 120s — minutos de espera).
    n = {'v': 0}

    def contador():
        n['v'] += 1
        return (False, '', [])

    monkeypatch.setattr(system, '_estado_git', contador)
    _reset_cache()
    system._snapshot_git()
    system._snapshot_git()
    assert n['v'] == 1                      # cache caliente
    system.invalidar_cache_git()
    system._snapshot_git()
    assert n['v'] == 2, 'invalidar_cache_git no tiró el snapshot cacheado'


def test_cache_se_invalida_si_reemplazan_estado_git(monkeypatch):
    # Los tests del repo monkeypatchean _estado_git por request: el cache tiene
    # que detectar el reemplazo (identidad de la función) y recomputar al toque.
    _reset_cache()
    monkeypatch.setattr(system, '_estado_git', lambda: (False, '', []))
    assert system._snapshot_git()[0][0] is False
    monkeypatch.setattr(system, '_estado_git', lambda: (True, 'T', []))
    assert system._snapshot_git()[0][0] is True, 'devolvió cache viejo tras el reemplazo'


def test_estampida_concurrente_un_solo_git(monkeypatch):
    n = {'v': 0}

    def lento():
        n['v'] += 1
        time.sleep(0.15)
        return (False, '', [])

    monkeypatch.setattr(system, '_estado_git', lento)
    _reset_cache()
    hilos = [threading.Thread(target=system._snapshot_git) for _ in range(8)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert n['v'] == 1, f'la estampida corrió git {n["v"]} veces'


def test_snapshot_incluye_proxima_bajo_el_mismo_cache(monkeypatch):
    # _version_proxima corre git extra cuando hay update: tiene que viajar
    # DENTRO del snapshot cacheado, no recomputarse por poll.
    monkeypatch.setattr(system, '_estado_git', lambda: (True, 'Hay una nueva versión', []))
    monkeypatch.setattr(system, '_commits_con_archivos', lambda: [{'subject': 'fix: x', 'files': []}])
    monkeypatch.setattr(system, '_VERSION_BOOT', '1.5.1')
    _reset_cache()
    estado, proxima = system._snapshot_git()
    assert estado[0] is True
    assert proxima == '1.5.01.1'   # hotfix: 4º segmento


# ─── 3. Firma de boot lazy ───────────────────────────────────────────────────

def test_firma_boot_respeta_valores_ya_seteados(monkeypatch):
    monkeypatch.setattr(system, '_FIRMA_BOOT', ('patched', 'x'))
    monkeypatch.setattr(system, '_COMMIT_BOOT', 'patched')
    monkeypatch.setattr(system, '_FIRMA_BOOT_LISTA', False)
    llamado = []
    monkeypatch.setattr(system, '_firma_codigo',
                        lambda: llamado.append(1) or ('real', 'y'))
    system._asegurar_firma_boot()
    assert not llamado, '_asegurar_firma_boot pisó un valor ya seteado'
    assert system._FIRMA_BOOT == ('patched', 'x')
    assert system._COMMIT_BOOT == 'patched'


def test_firma_boot_computa_si_falta(monkeypatch):
    monkeypatch.setattr(system, '_FIRMA_BOOT', None)
    monkeypatch.setattr(system, '_COMMIT_BOOT', None)
    monkeypatch.setattr(system, '_FIRMA_BOOT_LISTA', False)
    monkeypatch.setattr(system, '_firma_codigo', lambda: ('head9', 'h9'))
    system._asegurar_firma_boot()
    assert system._FIRMA_BOOT == ('head9', 'h9')
    assert system._COMMIT_BOOT == 'head9'
    assert system._FIRMA_BOOT_LISTA is True


def test_estado_git_se_autoabastece_sin_boot_previo(monkeypatch):
    # Si nadie corrió la captura de boot todavía (import recién hecho),
    # _estado_git la dispara solo y no revienta.
    monkeypatch.setattr(system, '_FIRMA_BOOT', None)
    monkeypatch.setattr(system, '_COMMIT_BOOT', None)
    monkeypatch.setattr(system, '_FIRMA_BOOT_LISTA', False)
    monkeypatch.setattr(system, '_firma_codigo', lambda: ('aaa', 'firma'))
    hay, titulo, nov = system._estado_git()
    assert hay is False   # HEAD no se movió respecto del boot recién capturado


# ─── 4. /restart decide con estado FRESCO (sin cache) ────────────────────────

def test_restart_no_usa_el_cache(monkeypatch):
    n = {'v': 0}

    def contador():
        n['v'] += 1
        return (False, '', [])

    monkeypatch.setattr(system, '_estado_git', contador)
    monkeypatch.setattr(system, '_canary_import', lambda: (True, ''))
    monkeypatch.setattr(system, 'reiniciar_servidor', lambda *a, **k: None)
    monkeypatch.setattr(system, '_escribir_version', lambda v: None)
    _reset_cache()
    system._snapshot_git()          # cache caliente
    assert n['v'] == 1
    system.restart()
    assert n['v'] == 2, '/restart leyó el cache en vez de git fresco'


# ─── 5. Pre-execv: cierre ordenado de hijos ──────────────────────────────────

def test_reexec_cierra_clientes_antes_del_exec(monkeypatch):
    orden = []
    from plotspace.core import control_mode as cm
    monkeypatch.setattr(cm, 'cerrar_clientes_para_reexec',
                        lambda: orden.append('cerrar'), raising=False)
    monkeypatch.setattr(system.os, 'chdir', lambda p: None)
    monkeypatch.setattr(system.os, 'execv', lambda e, a: orden.append('exec'))
    system._reexec()
    assert orden == ['cerrar', 'exec'], \
        f'el cierre no corrió antes del exec: {orden}'


def test_reexec_sobrevive_sin_la_funcion_de_cierre(monkeypatch):
    # El hook es defensivo: si control_mode no expone el cierre (o explota),
    # el re-exec sigue — jamás puede dejar al usuario sin restart.
    from plotspace.core import control_mode as cm
    if hasattr(cm, 'cerrar_clientes_para_reexec'):
        monkeypatch.delattr(cm, 'cerrar_clientes_para_reexec')
    llamadas = {}
    monkeypatch.setattr(system.os, 'chdir', lambda p: None)
    monkeypatch.setattr(system.os, 'execv',
                        lambda e, a: llamadas.__setitem__('exec', True))
    system._reexec()
    assert llamadas.get('exec') is True
