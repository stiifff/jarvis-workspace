"""Consolidación del motor de terminales (auditoría 2026-07-02):
TTL de _preparar_proyecto, kill verificado con target exacto, reconcile de
zombies (activa=0 con sesión viva) y bindings de copy-mode solo en classic."""
import asyncio
import subprocess

from plotspace.routers import terminals as term
# El motor (kill/has-session y los guards globales) vive ahora en
# core/terminal_backend: las aserciones no cambian, solo dónde se espía.
import plotspace.core.terminal_backend as _tb

# Estos tests verifican el argv EXACTO de tmux: desde F5·2 el default es el
# termhost, así que hay que pedir ese motor explícitamente (ver conftest).
import pytest

pytestmark = pytest.mark.usefixtures('motor_tmux')



# ─── TTL de _preparar_proyecto ────────────────────────────────────────────────

def test_preparar_proyecto_ttl(monkeypatch, tmp_path):
    """El cuerpo pesado (git + reescritura de CLAUDE.md + memoria/mailbox) corre
    UNA vez por proyecto por ventana de TTL: 9 conexiones WS del mismo workspace
    ya no lo pagan 9 veces (la 9ª terminal esperaba la suma de las 8 anteriores
    bajo el lock)."""
    llamadas = []
    monkeypatch.setattr(term, '_preparar_proyecto_sync',
                        lambda path, project_id=None: llamadas.append(path))
    term._preparado_ts.clear()
    ruta = str(tmp_path)

    async def escenario():
        await term._preparar_proyecto(ruta, project_id=1)
        await term._preparar_proyecto(ruta, project_id=1)
        await term._preparar_proyecto(ruta, project_id=1)
        assert len(llamadas) == 1, 'dentro del TTL debe correr una sola vez'
        # TTL vencido → vuelve a preparar
        term._preparado_ts[ruta] -= (term._PREPARAR_TTL + 1)
        await term._preparar_proyecto(ruta, project_id=1)
        assert len(llamadas) == 2

    asyncio.run(escenario())
    term._preparado_ts.clear()


def test_preparar_proyecto_otro_proyecto_no_comparte_ttl(monkeypatch, tmp_path):
    llamadas = []
    monkeypatch.setattr(term, '_preparar_proyecto_sync',
                        lambda path, project_id=None: llamadas.append(path))
    term._preparado_ts.clear()
    a, b = str(tmp_path / 'a'), str(tmp_path / 'b')

    async def escenario():
        await term._preparar_proyecto(a)
        await term._preparar_proyecto(b)
        assert llamadas == [a, b]

    asyncio.run(escenario())
    term._preparado_ts.clear()


# ─── _matar_sesion_tmux: target exacto + verificación del kill ────────────────

class _Res:
    def __init__(self, rc, stderr=''):
        self.returncode = rc
        self.stderr = stderr
        self.stdout = ''


def test_matar_sesion_target_exacto_y_verificacion(monkeypatch):
    """kill-session usa '=jarvis_N' (sin '=', tmux resuelve por PREFIJO cuando
    no hay match exacto: matar jarvis_1 muerta podía llevarse jarvis_12 viva) y
    el resultado se VERIFICA con has-session — un tmux trabado que no mata ya
    no pasa silencioso."""
    llamadas = []

    async def fake_tmux(*args, **kw):
        llamadas.append(list(args))
        if 'kill-session' in args:
            return _Res(0)
        if 'has-session' in args:
            return _Res(1, "can't find session")   # quedó muerta
        return _Res(0)

    monkeypatch.setattr(_tb.TmuxBackend, '_async', staticmethod(fake_tmux))
    ok = asyncio.run(term._matar_sesion_tmux(5))
    assert ok is True
    kill = next(c for c in llamadas if 'kill-session' in c)
    assert '=jarvis_5' in kill, kill
    chk = next(c for c in llamadas if 'has-session' in c)
    assert '=jarvis_5' in chk, chk


def test_matar_sesion_detecta_kill_que_no_mato(monkeypatch):
    async def fake_tmux(*args, **kw):
        if 'kill-session' in args:
            return _Res(0)
        return _Res(0)      # has-session: ¡sigue viva!

    monkeypatch.setattr(_tb.TmuxBackend, '_async', staticmethod(fake_tmux))
    assert asyncio.run(term._matar_sesion_tmux(5)) is False


def test_matar_sesion_ya_muerta_es_idempotente(monkeypatch):
    async def fake_tmux(*args, **kw):
        if 'kill-session' in args:
            return _Res(1, "can't find session: jarvis_5")
        return _Res(1, "can't find session")

    monkeypatch.setattr(_tb.TmuxBackend, '_async', staticmethod(fake_tmux))
    assert asyncio.run(term._matar_sesion_tmux(5)) is True


# ─── Reconcile de arranque: zombies activa=0 con sesión viva ──────────────────

def test_reconciliar_mata_zombies_activa_cero(monkeypatch):
    """Sesión tmux viva cuyo row en DB quedó activa=0 (teardown perdido por
    re-exec/crash): el reconcile del arranque la mata — se acabó el 'agente
    fantasma' invisible editando el repo sin card."""
    corridas = []

    def fake_run(argv, **kw):
        corridas.append(argv)
        if 'list-sessions' in argv:
            r = _Res(0)
            r.stdout = 'jarvis_3\njarvis_7\nsesion_personal'
            return r
        return _Res(0)

    monkeypatch.setattr(term.subprocess, 'run', fake_run)
    monkeypatch.setattr(_tb, '_ESTILO_OBSIDIAN_APLICADO', True)  # no ruido
    vivas = term._reconciliar_tmux_sync({3})

    kills = [c for c in corridas if 'kill-session' in c]
    assert len(kills) == 1 and '=jarvis_3' in kills[0], kills
    assert 'jarvis_3' not in vivas and 'jarvis_7' in vivas
    # la sesión ajena no-jarvis ni se toca ni pierde membresía
    assert 'sesion_personal' in vivas
    # las jarvis_* vivas legítimas siguen recibiendo window-size/status
    # (el motor aplica el juego completo de opciones obligatorias al sanear;
    # lo que importa es que estas dos, las que arreglan bugs reales, estén)
    opts = [' '.join(c) for c in corridas if 'set-option' in c and 'jarvis_7' in ' '.join(c)]
    assert any('window-size latest' in o for o in opts), opts
    assert any('status off' in o for o in opts), opts


def test_reconciliar_subprocesos_con_timeout(monkeypatch):
    kws = []

    def fake_run(argv, **kw):
        kws.append((argv[1] if len(argv) > 1 else '', kw))
        r = _Res(0)
        r.stdout = 'jarvis_9'
        return r

    monkeypatch.setattr(term.subprocess, 'run', fake_run)
    monkeypatch.setattr(_tb, '_ESTILO_OBSIDIAN_APLICADO', True)
    term._reconciliar_tmux_sync(set())
    assert kws, 'debe correr al menos list-sessions'
    assert all(kw.get('timeout') for _, kw in kws), kws


# ─── Bindings de copy-mode: solo motor classic ────────────────────────────────

def test_bindings_copy_mode_solo_en_classic(monkeypatch):
    """En control-mode el scroll es local de xterm (el copy-mode no participa):
    las ~190 bindings son inertes ahí y además se filtran a las sesiones tmux
    PERSONALES del usuario. Solo se instalan con TERMINALES_MOTOR=classic."""
    instaladas = []
    monkeypatch.setattr(term, '_crear_sesion_tmux_sync',
                        lambda tid, cwd, comando_cli=None, es_reanudacion=False: None)
    monkeypatch.setattr(term, '_instalar_bindings_copy_mode',
                        lambda: instaladas.append(1))

    async def correr():
        await term._crear_sesion_tmux(999, '/tmp')
        await asyncio.sleep(0.05)       # deja correr la task en background

    monkeypatch.setenv('TERMINALES_MOTOR', 'control')
    monkeypatch.setattr(term, '_COPY_MODE_BINDINGS_STARTED', False)
    asyncio.run(correr())
    assert instaladas == [], 'en control-mode NO se instalan'

    monkeypatch.setenv('TERMINALES_MOTOR', 'classic')
    monkeypatch.setattr(term, '_COPY_MODE_BINDINGS_STARTED', False)
    asyncio.run(correr())
    assert instaladas == [1], 'en classic sí'
