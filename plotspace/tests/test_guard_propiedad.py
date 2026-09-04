"""
Tests: candado de propiedad (scripts/guard_propiedad.py).

Pedido del usuario (2026-06-16): la regla del CLAUDE.md «commiteá solo TUS
archivos» es disciplina blanda — un agente puede no leerla, ser otro CLI, o
desviarse (los modelos son probabilísticos). Este es el enforcement DURO:
un hook pre-commit que lee `.jarvis/LIVE.md`, identifica al agente que
commitea por su sesión tmux (`jarvis_<id>`) y BLOQUEA si está por commitear
un archivo cuyo 🔒 dueño es OTRO agente. Gemelo conceptual del escáner de
secretos: la lógica pura vive acá, el hook la corre.

Invariantes:
1. Parsea LIVE.md → agentes (tid, nombre, archivos con 🔒 dueño) + permisos.
2. Un archivo staged cuyo dueño es otro tid → violación.
3. Archivo propio / sin dueño → NO viola.
4. Con un permiso «→ OK» del dueño a mi nombre sobre ese archivo → NO viola.
5. Falla ABIERTO: cualquier error (sin tmux, sin LIVE.md, parse roto) → permite
   (un bug en el guard NUNCA debe brickear los commits de todos los agentes).
"""
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'scripts'))
import guard_propiedad as g


LIVE = """# LIVE — qué está haciendo cada agente (auto-generado, NO editar)
Actualizado: 2026-06-16 10:57:05

## Backend (claude, terminal 100) — 🟢 trabajando
- `plotspace/routers/tasks.py` — write ×3 (hace 1m) 🔒 dueño
- `plotspace/core/database.py` — write ×1 (hace 2m) 🔒 dueño

## Claude Code #2 (claude, terminal 200) — ⚪ idle
- `frontend/shell/workspace.js` — write ×2 (hace 5m) 🔒 dueño
- `frontend/shell/workspace.html` — write ×1 (hace 30m)

## Permisos
- ✅ Claude Code #2 pidió PERMISO sobre `plotspace/core/database.py` (dueño: Backend) — hace 1m → OK: tocá solo las tablas
- ⛔ Claude Code #2 pidió PERMISO sobre `plotspace/routers/tasks.py` (dueño: Backend) — hace 2m → NO: lo estoy editando
"""


# ─── parsear_live ────────────────────────────────────────────────────────────

def test_parsea_agentes_y_propiedad():
    agentes, _ = g.parsear_live(LIVE)
    porid = {a['tid']: a for a in agentes}
    assert set(porid) == {100, 200}
    assert porid[100]['nombre'] == 'Backend'
    assert porid[200]['nombre'] == 'Claude Code #2'        # nombre con '#'
    assert set(porid[100]['owned']) == {
        'plotspace/routers/tasks.py', 'plotspace/core/database.py'}
    # workspace.html NO tiene 🔒 → no es propiedad
    assert porid[200]['owned'] == ['frontend/shell/workspace.js']


def test_parsea_permisos_con_estado():
    _, permisos = g.parsear_live(LIVE)
    assert ('Claude Code #2', 'plotspace/core/database.py', 'ok') in permisos
    assert ('Claude Code #2', 'plotspace/routers/tasks.py', 'no') in permisos


def test_parsea_vacio_o_basura_no_explota():
    assert g.parsear_live('') == ([], [])
    assert g.parsear_live('texto cualquiera\nsin formato') == ([], [])


# ─── violaciones ─────────────────────────────────────────────────────────────

def _ag():
    return g.parsear_live(LIVE)

def test_archivo_de_otro_agente_es_violacion():
    agentes, permisos = _ag()
    # soy 200, intento commitear un archivo de Backend (100) SIN permiso ok
    viol = g.violaciones(['plotspace/routers/tasks.py'], 200, agentes, permisos)
    assert len(viol) == 1
    assert viol[0]['path'] == 'plotspace/routers/tasks.py'
    assert viol[0]['dueno_tid'] == 100
    assert viol[0]['dueno_nombre'] == 'Backend'

def test_archivo_propio_no_es_violacion():
    agentes, permisos = _ag()
    assert g.violaciones(['frontend/shell/workspace.js'], 200, agentes, permisos) == []

def test_archivo_sin_dueno_no_es_violacion():
    agentes, permisos = _ag()
    # workspace.html no tiene 🔒 → libre
    assert g.violaciones(['frontend/shell/workspace.html'], 200, agentes, permisos) == []

def test_archivo_nuevo_no_listado_no_es_violacion():
    agentes, permisos = _ag()
    assert g.violaciones(['scripts/guard_propiedad.py'], 200, agentes, permisos) == []

def test_permiso_ok_exime_la_violacion():
    agentes, permisos = _ag()
    # database.py es de Backend, pero Backend me dio OK → puedo commitearlo
    assert g.violaciones(['plotspace/core/database.py'], 200, agentes, permisos) == []

def test_permiso_no_no_exime():
    agentes, permisos = _ag()
    viol = g.violaciones(['plotspace/routers/tasks.py'], 200, agentes, permisos)
    assert len(viol) == 1

def test_agente_no_identificado_sigue_bloqueado_si_toca_ajeno():
    # tmux dio un tid que no está en LIVE.md (sin nombre → sin permisos posibles)
    agentes, permisos = _ag()
    viol = g.violaciones(['plotspace/core/database.py'], 999, agentes, permisos)
    assert len(viol) == 1   # no soy el dueño y no tengo permiso → bloqueado

def test_mezcla_solo_reporta_los_ajenos():
    agentes, permisos = _ag()
    staged = ['frontend/shell/workspace.js',          # mío
              'frontend/shell/workspace.html',         # sin dueño
              'plotspace/routers/tasks.py',        # de Backend, sin permiso
              'scripts/nuevo.py']                       # nuevo
    viol = g.violaciones(staged, 200, agentes, permisos)
    assert [v['path'] for v in viol] == ['plotspace/routers/tasks.py']


# ─── _match_archivo (espejo de agent_live) ───────────────────────────────────

def test_match_archivo():
    assert g._match_archivo('a/b/ui.js', 'a/b/ui.js')
    assert g._match_archivo('frontend/shared/ui.js', 'ui.js')   # dueño responde basename
    assert g._match_archivo('ui.js', 'frontend/shared/ui.js')
    assert not g._match_archivo('a/ui.js', 'b/otro.js')
    assert not g._match_archivo('ui.js', 'gui.js')              # no es sufijo de path


def test_permiso_ok_por_basename_exime():
    # el dueño respondió con el basename: 'database.py' debe matchear el path full
    live = LIVE.replace('sobre `plotspace/core/database.py`', 'sobre `database.py`')
    agentes, permisos = g.parsear_live(live)
    assert g.violaciones(['plotspace/core/database.py'], 200, agentes, permisos) == []


# ─── main() — wiring tmux → LIVE.md → git (lo que los tests puros no cubren) ──

def _con_live(monkeypatch, tmp_path, tid, staged):
    (tmp_path / '.jarvis').mkdir()
    (tmp_path / '.jarvis' / 'LIVE.md').write_text(LIVE, encoding='utf-8')
    monkeypatch.setattr(g, 'detectar_terminal_id', lambda: tid)
    monkeypatch.setattr(g, '_git',
                        lambda *a: str(tmp_path) + '\n' if a and a[0] == 'rev-parse' else '')
    monkeypatch.setattr(g, '_staged', lambda: staged)
    # aislar el registro del bloqueo (registrar_bloqueo) del data/ real
    monkeypatch.setenv('JARVIS_DATA_DIR', str(tmp_path / 'data'))

def test_main_bloquea_archivo_ajeno(monkeypatch, tmp_path):
    _con_live(monkeypatch, tmp_path, 200, ['plotspace/routers/tasks.py'])
    assert g.main() == 1

def test_main_permite_archivo_propio(monkeypatch, tmp_path):
    _con_live(monkeypatch, tmp_path, 200, ['frontend/shell/workspace.js'])
    assert g.main() == 0

def test_main_permite_con_permiso_ok(monkeypatch, tmp_path):
    _con_live(monkeypatch, tmp_path, 200, ['plotspace/core/database.py'])
    assert g.main() == 0

def test_main_permite_sin_tmux(monkeypatch):
    # el usuario commiteando desde su shell (no es jarvis_<id>) → permite
    monkeypatch.setattr(g, 'detectar_terminal_id', lambda: None)
    assert g.main() == 0

def test_main_permite_sin_live_md(monkeypatch, tmp_path):
    # falla abierto: sin .jarvis/LIVE.md no hay nada que proteger
    monkeypatch.setattr(g, 'detectar_terminal_id', lambda: 200)
    monkeypatch.setattr(g, '_git',
                        lambda *a: str(tmp_path) + '\n' if a and a[0] == 'rev-parse' else '')
    monkeypatch.setattr(g, '_staged', lambda: ['plotspace/routers/tasks.py'])
    assert g.main() == 0


# ─── v2: reservas + bypass scoped GUARD_OK ───────────────────────────────────

LIVE_RESERVAS = LIVE + """
## Reservas
- 🔖 `frontend/nuevo.js` — Backend (hace 2m)
"""


# ─── Un muerto no bloquea a los vivos ────────────────────────────────────────
# Era el peor efecto de la ceguera de liveness: el CLI de un agente se cerraba,
# LIVE.md lo seguía mostrando idle con sus 🔒, y el guard le bloqueaba el commit
# a todos los demás en nombre de alguien que ya no iba a commitear nunca.

LIVE_CON_MUERTO = """# LIVE — qué está haciendo cada agente (auto-generado, NO editar)
Actualizado: 2026-07-25 10:57:05

## Backend (claude, terminal 100) — 💀 caído (su CLI se cerró)
- `plotspace/routers/tasks.py` — write ×3 (hace 1m) 🔒 dueño

## Fantasma (claude, terminal 300) — 💀 caído (sin sesión tmux)
- `plotspace/core/x.py` — write ×1 (hace 4m) 🔒 dueño

## Vivo (claude, terminal 200) — 🟢 trabajando
- `frontend/shell/workspace.js` — write ×2 (hace 5m) 🔒 dueño
"""


def test_el_parseo_marca_a_los_agentes_muertos():
    agentes, _ = g.parsear_live(LIVE_CON_MUERTO)
    porid = {a['tid']: a for a in agentes}
    assert porid[100]['muerto'] is True
    assert porid[300]['muerto'] is True
    assert porid[200]['muerto'] is False


def test_la_propiedad_de_un_caido_no_bloquea():
    agentes, permisos = g.parsear_live(LIVE_CON_MUERTO)
    viol = g.violaciones(['plotspace/routers/tasks.py'], 200, agentes, permisos)
    assert viol == []


def test_la_propiedad_de_uno_sin_sesion_tampoco_bloquea():
    agentes, permisos = g.parsear_live(LIVE_CON_MUERTO)
    assert g.violaciones(['plotspace/core/x.py'], 200, agentes, permisos) == []


def test_la_propiedad_de_un_vivo_sigue_bloqueando():
    """Que se libere lo del muerto NO puede aflojar la defensa de los vivos."""
    agentes, permisos = g.parsear_live(LIVE_CON_MUERTO)
    viol = g.violaciones(['frontend/shell/workspace.js'], 100, agentes, permisos)
    assert [v['path'] for v in viol] == ['frontend/shell/workspace.js']


def test_un_live_md_viejo_sin_marca_de_muerte_se_comporta_como_antes():
    """Compatibilidad: mientras el server no se reinicie, LIVE.md puede seguir
    con el formato de antes. Sin 💀, todos vivos — el comportamiento de siempre."""
    agentes, permisos = g.parsear_live(LIVE)
    assert all(a['muerto'] is False for a in agentes)
    assert len(g.violaciones(['plotspace/routers/tasks.py'], 200, agentes, permisos)) == 1


def test_parsear_reservas():
    rs = g.parsear_reservas(LIVE_RESERVAS)
    assert rs == [('Backend', 'frontend/nuevo.js')]
    assert g.parsear_reservas(LIVE) == []


def test_reserva_ajena_bloquea_y_propia_no():
    agentes, permisos = g.parsear_live(LIVE_RESERVAS)
    reservas = g.parsear_reservas(LIVE_RESERVAS)
    # terminal 200 (Claude Code #2) NO es Backend → la reserva lo bloquea
    viol = g.violaciones(['frontend/nuevo.js'], 200, agentes, permisos, reservas)
    assert len(viol) == 1 and 'reserva' in viol[0]['dueno_nombre']
    assert viol[0]['dueno_tid'] is None
    # terminal 100 ES Backend (el reservante) → pasa
    assert g.violaciones(['frontend/nuevo.js'], 100, agentes, permisos, reservas) == []


def test_filtrar_guard_ok_exime_solo_lo_pedido():
    viol = [{'path': 'a.py', 'dueno_tid': 1, 'dueno_nombre': 'X'},
            {'path': 'b.py', 'dueno_tid': 1, 'dueno_nombre': 'X'}]
    vivas, eximidas = g.filtrar_guard_ok(viol, ['a.py'])
    assert [v['path'] for v in vivas] == ['b.py']
    assert [v['path'] for v in eximidas] == ['a.py']
    assert g.filtrar_guard_ok(viol, []) == (viol, [])


# ─── Identidad del agente: la variable de entorno manda sobre tmux ────────────
# Este guard es el candado de propiedad del enjambre. Si depende de que exista
# una sesión tmux para saber QUIÉN commitea, el día que el motor sea ConPTY
# (Windows) se queda ciego y deja pasar todo. La verdad es la variable que
# Jarvis inyecta al crear la terminal; tmux queda de respaldo para las
# terminales nacidas antes de que existiera.

def test_identidad_prefiere_la_variable_de_entorno(monkeypatch):
    llamadas = []
    monkeypatch.setenv('JARVIS_TERMINAL_ID', '441')
    monkeypatch.setattr(g.subprocess, 'run',
                        lambda *a, **kw: llamadas.append(a) or (_ for _ in ()).throw(
                            AssertionError('no debería consultar a tmux')))
    assert g.detectar_terminal_id() == 441
    assert not llamadas, 'consultó tmux teniendo la variable'


def test_identidad_cae_a_tmux_sin_variable(monkeypatch):
    class _R:
        returncode = 0
        stdout = 'jarvis_77\n'
    monkeypatch.delenv('JARVIS_TERMINAL_ID', raising=False)
    monkeypatch.setattr(g.subprocess, 'run', lambda *a, **kw: _R())
    assert g.detectar_terminal_id() == 77


def test_identidad_ignora_una_variable_basura(monkeypatch):
    # Una variable heredada con basura no debe dar un id inventado: se cae al
    # respaldo, y si tampoco hay, se falla ABIERTO (None = no soy un agente).
    monkeypatch.setenv('JARVIS_TERMINAL_ID', 'no-soy-un-numero')
    monkeypatch.setattr(g.subprocess, 'run',
                        lambda *a, **kw: (_ for _ in ()).throw(OSError('sin tmux')))
    assert g.detectar_terminal_id() is None
