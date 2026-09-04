#!/usr/bin/env python3
"""
Gate de admisión de memorias (.jarvis/memory/) — corre en el pre-commit.

La calidad de la memoria compartida se pierde en el momento de ESCRIBIR, no
de leer: memorias sin `estado:`, informes de 100+ líneas y títulos-bitácora
("auditoría 2026-07-18") entraban al corpus sin guardia, y el linter de salud
solo lo reportaba después, cuando nadie procesa la señal. Este guard es el
gemelo de guard_propiedad/scan_secretos: valida el CONTRATO de una memoria
antes de que entre al repo, con mensajes de fix de una línea.

Reglas (todas con arreglo trivial):
  - Frontmatter completo: titulo, tags, categoria, estado (vigente|obsoleta|
    lapida|archivo). Sin eso, el recall/lint/INDEX la manejan a ciegas.
  - Cuerpo ≤ 150 líneas no vacías (más que eso es un informe: destilalo).
  - Memoria NUEVA: sin fecha embebida en slug/título (una memoria es
    conocimiento, no una entrada de bitácora — la fecha va en creado:) y con
    `resumen:` (la línea que el recall inyecta al prompt de los agentes).

Falla ABIERTO (error inesperado → permite) y exime lo autogenerado
(INDEX.md, lecciones-del-enjambre.md). Escape legítimo: --no-verify.
Stdlib pura, sin imports de backend (corre en cualquier clon).
"""
import re
import subprocess
import sys

_FRONT_RE  = re.compile(r'^---\s*\n(.*?)\n---\s*\n?', re.DOTALL)
_TAGS_RE   = re.compile(r'^tags:\s*\[([^\]]*)\]', re.MULTILINE)
_CAMPO_RE  = {k: re.compile(rf'^{k}:\s*(.+)$', re.MULTILINE)
              for k in ('titulo', 'categoria', 'estado', 'resumen')}
# Patrón bitácora: año-mes (2026-07). Un año suelto ("frames 2026") no cuenta.
_FECHA_RE  = re.compile(r'20\d{2}-\d{2}')
_ESTADOS   = {'vigente', 'obsoleta', 'lapida', 'archivo'}
_MAX_LINEAS = 150
_EXENTOS   = {'INDEX.md', 'lecciones-del-enjambre.md'}
_MEM_DIR   = '.jarvis/memory/'


def es_exento(path):
    return path.rsplit('/', 1)[-1] in _EXENTOS


def es_memoria(path):
    return path.startswith(_MEM_DIR) and path.endswith('.md') and not es_exento(path)


def _campo(front, k):
    m = _CAMPO_RE[k].search(front)
    return m.group(1).strip() if m else ''


def validar(slug, src, es_nueva):
    """Lista de violaciones del contrato ([] = memoria admisible)."""
    m = _FRONT_RE.match(src or '')
    if not m:
        return ["sin frontmatter — arrancá el archivo con el bloque `---` del protocolo"]
    front, cuerpo = m.group(1), src[m.end():]
    v = []
    if not _campo(front, 'titulo'):
        v.append("falta `titulo:` en el frontmatter")
    mt = _TAGS_RE.search(front)
    if not (mt and [t for t in mt.group(1).split(',') if t.strip()]):
        v.append("falta `tags: [tema1, tema2]` en el frontmatter")
    if not _campo(front, 'categoria'):
        v.append("falta `categoria:` en el frontmatter (una del protocolo)")
    estado = _campo(front, 'estado').lower()
    if not estado:
        v.append("falta `estado:` en el frontmatter (vigente|obsoleta|lapida|archivo)")
    elif estado not in _ESTADOS:
        v.append(f"`estado: {estado}` inválido (vigente|obsoleta|lapida|archivo)")
    if es_nueva:
        # El tope de líneas solo bloquea memorias NUEVAS: editar una legacy
        # larga (agregar estado:, un hallazgo) no puede exigir reescribirla —
        # eso empuja al --no-verify. Las legacy largas las marca el lint.
        lineas = len([l for l in cuerpo.splitlines() if l.strip()])
        if lineas > _MAX_LINEAS:
            v.append(f"cuerpo de {lineas} líneas (máx {_MAX_LINEAS}) — eso es un informe: "
                     "destilá el hecho y punto")
        if _FECHA_RE.search(slug) or _FECHA_RE.search(_campo(front, 'titulo')):
            v.append("fecha embebida en el slug/título — una memoria no es bitácora: "
                     "la fecha va en `creado:`/`actualizado:`")
        if not _campo(front, 'resumen'):
            v.append("falta `resumen:` (una línea con el hecho — es lo que el recall "
                     "inyecta al prompt de los demás agentes)")
    return v


def memorias_staged():
    """[(path, es_nueva, contenido_staged)] de las memorias en el índice.
    Valida la versión STAGED (git show :path), no la del working tree."""
    salida = subprocess.run(
        ['git', 'diff', '--cached', '--name-status', '--diff-filter=AM'],
        capture_output=True, text=True, timeout=10).stdout
    out = []
    for linea in salida.splitlines():
        partes = linea.split('\t')
        if len(partes) < 2:
            continue
        status, path = partes[0], partes[-1]
        if not es_memoria(path):
            continue
        show = subprocess.run(['git', 'show', f':{path}'],
                              capture_output=True, text=True, timeout=10)
        if show.returncode != 0:
            continue
        out.append((path, status.startswith('A'), show.stdout))
    return out


def memorias_en_rango(viejo, nuevo):
    """[(path, es_nueva, contenido_en_nuevo)] de las memorias tocadas en el
    rango saliente — el gemelo pre-push: caza lo commiteado con --no-verify."""
    salida = subprocess.run(
        ['git', 'diff', '--name-status', '--diff-filter=AM', f'{viejo}..{nuevo}'],
        capture_output=True, text=True, timeout=15).stdout
    out = []
    for linea in salida.splitlines():
        partes = linea.split('\t')
        if len(partes) < 2:
            continue
        status, path = partes[0], partes[-1]
        if not es_memoria(path):
            continue
        show = subprocess.run(['git', 'show', f'{nuevo}:{path}'],
                              capture_output=True, text=True, timeout=10)
        if show.returncode != 0:
            continue
        out.append((path, status.startswith('A'), show.stdout))
    return out


def _reportar(items, origen):
    fallo = 0
    for path, es_nueva, src in items:
        slug = path.rsplit('/', 1)[-1][:-3]
        for violacion in validar(slug, src, es_nueva):
            print(f"✖ MEMORIA {path}: {violacion}")
            fallo = 1
    if fallo:
        print(f"  (contrato de .jarvis/memory/ en {origen} — ver protocolo en "
              "CLAUDE.md; falso positivo legítimo: git commit --no-verify)")
    return fallo


def main():
    try:
        if len(sys.argv) >= 4 and sys.argv[1] == '--rango':
            return _reportar(memorias_en_rango(sys.argv[2], sys.argv[3]), 'el push')
        return _reportar(memorias_staged(), 'el commit')
    except Exception:
        return 0     # falla ABIERTO: un bug acá jamás brickea los commits


if __name__ == '__main__':
    sys.exit(main())
