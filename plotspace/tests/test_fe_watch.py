# plotspace/tests/test_fe_watch.py
"""Tests de FE Watch (plotspace/core/fe_watch.py) — lógica pura.
Sin asyncio ni broadcaster, espejo de test_agent_live.py.

Nota (2026-07-03): el escaneo de mtimes + máquina de quietud
(firma_frontend/evaluar_cambio, gate por agente) se retiró junto con el
auto-reload por ediciones sin commit (parpadeaba el workspace). Sobrevive
solo la detección de commits que alimenta el banner "Actualizar ahora".
Ver memoria no-pedir-f5-fe-watch."""

from plotspace.core.fe_watch import (
    BOOT_ID,
    cambio_de_commit,
    invalidar_cache_version,
)


# ─── BOOT_ID ──────────────────────────────────────────────────────────────────

def test_boot_id_estable_en_el_proceso():
    # uuid del proceso: existe, no es trivial y no cambia entre lecturas
    assert isinstance(BOOT_ID, str) and len(BOOT_ID) >= 16
    from plotspace.core.fe_watch import BOOT_ID as otra_vez
    assert otra_vez == BOOT_ID


# ─── cambio_de_commit (HEAD se movió = commit nuevo → re-chequea el banner) ────

def test_commit_primer_scan_es_baseline():
    # El commit con el que arrancó el server NO avisa (sería un falso "hay update").
    estado = {'head': None}
    assert cambio_de_commit(estado, 'aaa') is False
    assert cambio_de_commit(estado, 'aaa') is False   # mismo HEAD: nada


def test_commit_nuevo_dispara_una_vez():
    estado = {'head': None}
    cambio_de_commit(estado, 'aaa')                    # baseline
    assert cambio_de_commit(estado, 'bbb') is True     # commit nuevo
    assert cambio_de_commit(estado, 'bbb') is False    # estable: no re-dispara


def test_commits_sucesivos_disparan_cada_uno():
    # Cada tarea terminada (commit) re-chequea el banner, aunque el agente siga.
    estado = {'head': None}
    cambio_de_commit(estado, 'aaa')                    # baseline
    assert cambio_de_commit(estado, 'bbb') is True
    assert cambio_de_commit(estado, 'ccc') is True


def test_commit_head_vacio_no_dispara():
    # git falló / no es repo → '' no debe disparar (ni romper el baseline).
    estado = {'head': None}
    assert cambio_de_commit(estado, '') is False
    assert estado['head'] is None                      # sigue sin baseline
    assert cambio_de_commit(estado, 'aaa') is False    # recién acá baseline
    assert cambio_de_commit(estado, '') is False       # git falla puntual: no avisa


# ─── invalidar_cache_version (el commit nuevo debe VERSE ya en /version) ──────

def test_commit_nuevo_tira_el_cache_de_version(monkeypatch):
    # Carrera que dejaba el banner "Actualizar ahora" esperando MINUTOS: el
    # aviso codigo_commiteado hace que el browser re-chequee /version al toque,
    # pero /version servía un snapshot git cacheado (TTL 30s). Si el cache era
    # de ANTES del commit, el re-chequeo veía hay_update=false y el banner
    # recién aparecía en el próximo poll de 120s. El poller tiene que tirar el
    # cache ANTES de avisar: el re-chequeo siempre ve git fresco.
    from plotspace.routers import system
    estado = {'hay': False}

    def fake_estado_git():
        return (estado['hay'], 'T' if estado['hay'] else '', [])

    monkeypatch.setattr(system, '_estado_git', fake_estado_git)
    system._git_cache = {'fn': None, 'ts': 0.0, 'val': None}
    assert system._snapshot_git()[0][0] is False   # cache caliente pre-commit
    estado['hay'] = True                           # llegó el commit del agente
    assert system._snapshot_git()[0][0] is False   # el TTL de 30s lo esconde
    invalidar_cache_version()                      # lo que hace el poller al detectar
    assert system._snapshot_git()[0][0] is True, \
        'el re-chequeo del banner leyó el cache de antes del commit'


# ─── Auto-push (el server es el DUEÑO del push; el CI del desktop depende) ────
# Los agentes commitean local y por política no pushean; el circuito de update
# del shell (CI → publisher → toast) arranca recién con el push a GitHub. Ese
# eslabón quedaba sin dueño (2026-07-08: 9 commits sin pushear, cero toasts).

from plotspace.core import fe_watch


def test_push_primer_head_es_baseline_y_drena_backlog():
    # Al boot pusheado=None → un HEAD válido dispara push: drena los commits
    # acumulados con el server apagado (o de antes de este feature).
    estado = {'pusheado': None, 'fallo_hasta': 0.0}
    assert fe_watch.debe_pushear(estado, 'aaa', ahora=100.0) is True


def test_push_no_repite_para_el_mismo_head():
    estado = {'pusheado': 'aaa', 'fallo_hasta': 0.0}
    assert fe_watch.debe_pushear(estado, 'aaa', 100.0) is False
    assert fe_watch.debe_pushear(estado, 'bbb', 100.0) is True


def test_push_fallido_respeta_backoff_y_reintenta_despues():
    estado = {'pusheado': 'aaa', 'fallo_hasta': 0.0}
    fe_watch.registrar_push(estado, 'bbb', ok=False, ahora=100.0)
    assert estado['pusheado'] == 'aaa'                 # no se marca como pusheado
    assert fe_watch.debe_pushear(estado, 'bbb', 150.0) is False   # en backoff
    assert fe_watch.debe_pushear(
        estado, 'bbb', 100.0 + fe_watch.PUSH_BACKOFF_S + 1) is True


def test_push_exitoso_registra_head_y_limpia_backoff():
    estado = {'pusheado': None, 'fallo_hasta': 999.0}
    fe_watch.registrar_push(estado, 'bbb', ok=True, ahora=100.0)
    assert estado['pusheado'] == 'bbb'
    assert estado['fallo_hasta'] == 0.0
    assert fe_watch.debe_pushear(estado, 'bbb', 101.0) is False


def test_push_head_vacio_o_deshabilitado_no_dispara():
    estado = {'pusheado': None, 'fallo_hasta': 0.0}
    assert fe_watch.debe_pushear(estado, '', 100.0) is False
    assert fe_watch.debe_pushear(estado, 'aaa', 100.0, habilitado=False) is False


def test_auto_push_habilitado_por_env(monkeypatch):
    monkeypatch.delenv('AUTO_PUSH', raising=False)
    assert fe_watch.auto_push_habilitado() is False    # default OFF
    monkeypatch.setenv('AUTO_PUSH', 'off')
    assert fe_watch.auto_push_habilitado() is False
    monkeypatch.setenv('AUTO_PUSH', 'on')
    assert fe_watch.auto_push_habilitado() is True
