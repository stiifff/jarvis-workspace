#!/usr/bin/env python3
"""
commit-propio — el commit sin miedo del árbol compartido.

En este repo N agentes comparten un solo working tree y UN índice de git:
elegir a mano qué stagear es la fuente del pánico ("¿me llevo trabajo
ajeno?") y de la carrera stage↔commit (dos agentes stageando a la vez).
Este script lo resuelve:

  1. Identifica al agente por su sesión tmux (jarvis_<id>).
  2. Le pregunta a Jarvis QUÉ TEXTO escribió cada agente en los archivos que
     tocaste (provenance real, la que reporta el hook del CLI) y elige los
     candidatos cruzando eso con los archivos sucios + lo que diga LIVE.md +
     los extras que pases por argumento.
  3. Stagea con el grano que corresponde:
       · archivo que solo tocaste vos → completo.
       · archivo donde OTRO agente tiene trabajo sin commitear → por HUNK,
         filtrando por CONTENIDO (nunca por número de línea: filtrar por línea
         ya se llevó puesta una función ajena que vivía 1300 líneas más abajo).
       · hunk que no se puede atribuir → NO se stagea y se te avisa.
  4. Toma un LOCK (flock sobre .git/jarvis-commit.lock) que serializa
     stage+commit, y de paso saca del índice COMPARTIDO lo que otro haya dejado
     staged (si no, se iría en tu commit).
  5. Commitea con tu mensaje (los hooks corren normal: secretos, propiedad,
     memorias).

Si Jarvis no responde, degrada al camino viejo (LIVE.md + archivo completo) y
te lo dice, para que mires el diff staged antes de confiar.

Uso:  python3 scripts/commit_propio.py -m "fix(x): mensaje" [ruta extra ...]

Si no corrés dentro de una terminal de Jarvis, te lo dice y no hace nada
(el usuario commitea como siempre). Stdlib pura.
"""
import argparse
import os
import subprocess
import sys
import time

# El lock que serializa stage+commit entre agentes. `fcntl` es de Unix: en
# Windows no existe y su import hacía que este script —y su test— ni se
# pudieran cargar. Se elige el mecanismo del sistema.
try:
    import fcntl
except ImportError:                       # Windows
    fcntl = None
    import msvcrt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guard_propiedad as gp


def _tomar_lock(archivo, espera=30.0):
    """Lock exclusivo sobre el archivo abierto, del modo que el sistema soporte.

    Serializa stage+commit entre agentes: sin esto, dos que commitean a la vez
    se llevan los archivos del otro en su commit (el índice de git es
    compartido). Es lo que protege el trabajo ajeno, así que si no se puede
    tomar hay que saberlo, no seguir de largo en silencio.
    """
    limite = time.monotonic() + espera
    while True:
        try:
            if fcntl is not None:
                fcntl.flock(archivo, fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                # Windows: bloquea un byte del archivo. Mismo efecto, otra API.
                msvcrt.locking(archivo.fileno(), msvcrt.LK_NBLCK, 1)
            return
        except OSError:
            if time.monotonic() >= limite:
                raise RuntimeError(
                    'otro agente lleva más de 30s commiteando — reintentá en un momento')
            time.sleep(0.1)


def archivos_de_mi_seccion(texto_live, mi_tid):
    """TODOS los paths listados bajo MI sección del LIVE.md (con o sin 🔒):
    son los archivos que el tracking en vivo me vio escribir."""
    mios, actual = [], None
    for linea in (texto_live or '').splitlines():
        m = gp._RE_AGENTE.match(linea)
        if m:
            actual = int(m.group(2))
            continue
        if linea.startswith('## '):
            actual = None
            continue
        if actual == mi_tid:
            mp = gp._RE_PATH.match(linea)
            if mp:
                mios.append(mp.group(1))
    return mios


def nombre_de_agente(texto_live, mi_tid):
    """Nombre del agente `mi_tid` según su encabezado en LIVE.md, o None. Es la
    identidad que se estampa en el commit: el autor git es el mismo para TODOS
    los agentes (mismo user.name de git), así que sin esto `git log` no puede decir de quién
    es cada commit."""
    for linea in (texto_live or '').splitlines():
        m = gp._RE_AGENTE.match(linea)
        if m and int(m.group(2)) == mi_tid:
            return m.group(1).strip()
    return None


def trailer_atribucion(nombre, mi_tid):
    """Trailer `Jarvis-Agent: <nombre> (tid N)` que hace recuperable de qué
    agente salió un commit, SIN tocar el autor git (que el CI y el popup de
    novedades esperan estable). Una sola línea: los saltos se aplastan para no
    romper el bloque de trailers de git."""
    quien = ' '.join(str(nombre).split()) if nombre else f'terminal {mi_tid}'
    return f'Jarvis-Agent: {quien} (tid {mi_tid})'


def elegir_staged(dirty, mios, extras):
    """Qué stagear: sucios ∩ míos (match tolerante a basename) + extras."""
    out = []
    for f in dirty:
        if any(gp._match_archivo(m, f) for m in mios) and f not in out:
            out.append(f)
    for e in extras:
        if e not in out:
            out.append(e)
    return out


def _dirty(raiz):
    r = subprocess.run(['git', 'status', '--porcelain'], capture_output=True,
                       text=True, cwd=raiz, timeout=15)
    out = []
    for linea in r.stdout.splitlines():
        if len(linea) > 3:
            out.append(linea[3:].strip().strip('"'))
    return out


def _untracked(raiz):
    r = subprocess.run(['git', 'ls-files', '--others', '--exclude-standard'],
                       capture_output=True, text=True, cwd=raiz, timeout=15)
    return {l.strip() for l in r.stdout.splitlines() if l.strip()}


# ─── Stage por HUNK (provenance real, no heurística de líneas) ────────────────

def elegir_candidatos(dirty, archivos_prov, mios_live, extras):
    """Qué archivos entran al commit: los SUCIOS que la provenance o el LIVE.md
    dicen que escribí yo, más los extras explícitos. Nunca lo ajeno."""
    mios = list(archivos_prov) + list(mios_live)
    out = []
    for f in dirty:
        if any(gp._match_archivo(m, f) for m in mios) and f not in out:
            out.append(f)
    for e in extras:
        if e not in out:
            out.append(e)
    return out


def clasificar_archivos(candidatos, untracked, ajenos, extras):
    """Cómo stagear cada archivo:
      'archivo' → completo: nadie más escribió ahí, o es nuevo, o lo pediste vos.
      'hunk'    → por hunks: otro agente también tiene texto sin commitear ahí,
                  y meter el archivo entero se lo llevaría puesto."""
    modo = {}
    for f in candidatos:
        comparte = any(gp._match_archivo(k, f) and v for k, v in (ajenos or {}).items())
        if comparte and f not in untracked and f not in extras:
            modo[f] = 'hunk'
        else:
            modo[f] = 'archivo'
    return modo


def _fragmentos_de_jarvis(mi_tid):
    """{mios, ajenos, archivos} del server. None si Jarvis no contesta (ahí se
    cae al camino viejo: LIVE.md + archivo completo)."""
    import json
    import urllib.request
    puerto = os.environ.get('JARVIS_PORT', '3000')
    try:
        req = urllib.request.Request(
            f'http://127.0.0.1:{puerto}/api/swarm/fragmentos/{mi_tid}')
        with urllib.request.urlopen(req, timeout=4) as r:
            return json.loads(r.read().decode('utf-8', errors='replace'))
    except Exception:
        return None


def _stage_por_hunk(raiz, archivo, mios, ajenos):
    """Aplica al índice SOLO los hunks míos de `archivo`.
    Devuelve (ok, motivo_si_no)."""
    import hunks_propios as hp
    d = subprocess.run(['git', 'diff', '-U0', '--', archivo], capture_output=True,
                       text=True, cwd=raiz, timeout=30)
    if not d.stdout.strip():
        return False, 'sin cambios sin stagear'
    parche = hp.filtrar_parche(d.stdout, mios, ajenos)
    if not parche:
        return False, ('no pude atribuirte ningún hunk (¿editaste líneas pegadas '
                       'a las del otro agente?)')
    import tempfile
    fd, tmp = tempfile.mkstemp(suffix='.patch', dir=os.path.join(raiz, '.git'))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(parche)
        r = subprocess.run(['git', 'apply', '--cached', '--unidiff-zero', tmp],
                           capture_output=True, text=True, cwd=raiz, timeout=30)
        if r.returncode != 0:
            return False, f'git apply falló: {r.stderr.strip()[:200]}'
        return True, ''
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def main():
    ap = argparse.ArgumentParser(description='Commit seguro en el árbol compartido')
    ap.add_argument('-m', '--mensaje', required=True)
    ap.add_argument('extras', nargs='*', help='rutas extra a incluir')
    args = ap.parse_args()

    mi_tid = gp.detectar_terminal_id()
    if mi_tid is None:
        print('commit-propio: no estás en una terminal de Jarvis (jarvis_<id>) — '
              'commiteá normal con git add <rutas> && git commit.')
        return 1
    raiz = (gp._git('rev-parse', '--show-toplevel') or '').strip()
    if not raiz:
        print('commit-propio: acá no hay repo git.')
        return 1
    try:
        with open(os.path.join(raiz, '.jarvis', 'LIVE.md'), encoding='utf-8') as f:
            live = f.read()
    except OSError:
        live = ''
    mios_live = archivos_de_mi_seccion(live, mi_tid)
    trailer = trailer_atribucion(nombre_de_agente(live, mi_tid), mi_tid)

    # Provenance real (hook del CLI). Si Jarvis no contesta, se sigue con
    # LIVE.md y archivo completo — el camino de antes, degradado pero vivo.
    prov = _fragmentos_de_jarvis(mi_tid)
    if prov is None:
        print('commit-propio: Jarvis no responde — voy con LIVE.md y archivos '
              'completos (sin filtrado por hunk). Revisá el diff staged.')
        prov = {'mios': {}, 'ajenos': {}, 'archivos': []}

    dirty = _dirty(raiz)
    extras = set(args.extras)
    candidatos = elegir_candidatos(dirty, prov.get('archivos') or [],
                                   mios_live, args.extras)
    if not candidatos:
        print('commit-propio: no encontré archivos tuyos sucios. Si el tracking '
              'no te vio, pasá las rutas explícitas como argumento.')
        return 1

    modo = clasificar_archivos(candidatos, _untracked(raiz),
                               prov.get('ajenos') or {}, extras)

    lock_path = os.path.join(raiz, '.git', 'jarvis-commit.lock')
    staged, saltados = [], []
    with open(lock_path, 'w') as lock:
        try:
            _tomar_lock(lock)                     # serializa stage+commit

            # El índice es COMPARTIDO: lo que otro dejó staged se iría en MI
            # commit. Se saca antes de empezar (queda en su working tree).
            ya = subprocess.run(['git', 'diff', '--cached', '--name-only'],
                                capture_output=True, text=True, cwd=raiz, timeout=15)
            ajeno_staged = [f for f in ya.stdout.split()
                            if f and not any(gp._match_archivo(c, f) for c in candidatos)]
            if ajeno_staged:
                subprocess.run(['git', 'reset', '-q', '--'] + ajeno_staged,
                               cwd=raiz, timeout=30)
                print('commit-propio: saqué del índice lo que no es tuyo: '
                      + ', '.join(ajeno_staged[:6]))

            for f in candidatos:
                if modo[f] == 'archivo':
                    r = subprocess.run(['git', 'add', '--', f], cwd=raiz,
                                       capture_output=True, text=True, timeout=30)
                    (staged if r.returncode == 0 else saltados).append(
                        f if r.returncode == 0 else (f, r.stderr.strip()[:120]))
                    continue
                ok, motivo = _stage_por_hunk(
                    raiz, f, (prov['mios'] or {}).get(f, []),
                    (prov['ajenos'] or {}).get(f, []))
                (staged if ok else saltados).append(f if ok else (f, motivo))

            if not staged:
                for f, m in saltados:
                    print(f'commit-propio: ⚠ {f} — {m}')
                print('commit-propio: no quedó nada tuyo para commitear.')
                return 1

            r = subprocess.run(['git', 'commit', '-m', args.mensaje, '-m', trailer],
                               cwd=raiz, timeout=120)
            if r.returncode != 0:
                # el hook bloqueó (propiedad/secretos/memoria): deshacer el stage
                # para no dejar el índice a medias para el próximo
                subprocess.run(['git', 'reset', '-q', '--'] + staged,
                               cwd=raiz, timeout=30)
                return r.returncode
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)

    por_hunk = [f for f in staged if modo.get(f) == 'hunk']
    print(f'commit-propio: commiteado ({len(staged)} archivo(s)): '
          + ', '.join(staged[:8]) + ('…' if len(staged) > 8 else ''))
    if por_hunk:
        print('  · por HUNK (compartidos con otro agente): ' + ', '.join(por_hunk))
    for f, m in saltados:
        print(f'  ⚠ afuera: {f} — {m}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
