"""
memoria_global — semilla de lecciones cross-proyecto.

Cada proyecto nuevo del workspace arranca con `.jarvis/memory/` vacía: el
enjambre re-tropieza con lo mismo (WSL no reenvía puertos, el 3000 es de
Jarvis, el índice git es compartido) hasta que lo aprende de nuevo. Este
módulo siembra esas lecciones de ENTORNO —las que valen para cualquier repo
corrido en este workspace— al crear el proyecto, y permite PROMOVER una
lección local a global para que los futuros proyectos la hereden.

Dos fuentes: `SEMILLA` (curada, versionada con el código) + un store en el
data dir (`memoria-global/`) que crece cuando se promueve una lección. El
sembrado es idempotente y NUNCA pisa una memoria existente del proyecto.
"""
import os
from datetime import date

from plotspace.core.datadir import ruta_data

# Lecciones de entorno universales (mismas slugs que las canónicas de Jarvis,
# así en el propio repo NO se duplican — sembrar salta lo que ya existe).
SEMILLA = [
    {
        'slug': 'regla-de-puertos',
        'titulo': 'Regla de puertos: el 3000 es de Jarvis — chequeá antes de servir',
        'categoria': 'entorno',
        'tags': ['puertos', 'dev-server', 'entorno'],
        'cuerpo': (
            "El puerto **3000 está PROHIBIDO**: ahí corre Jarvis Workspace. Antes de "
            "levantar CUALQUIER server (dev, api, http.server): listá los puertos "
            "ocupados (`ss -tlnp` o `lsof -iTCP -sTCP:LISTEN -P -n`), elegí uno LIBRE "
            "(rango 5000-5999 u 8081-8999) y pasalo EXPLÍCITO (`--port`/`-p`/`PORT=`) "
            "— no confíes en el default de la herramienta. NUNCA mates un proceso de un "
            "puerto que no levantaste vos.\n\n"
            "**WSL no reenvía puertos nuevos:** en WSL2 un server en un puerto recién "
            "abierto escucha DENTRO de WSL (`curl` 200) pero el `localhostForwarding` a "
            "menudo NO lo reenvía al browser de Windows. Para mostrarle algo al usuario, "
            "servilo por un puerto que ya estaba vivo al boot o usá la IP de WSL "
            "(`hostname -I` → `http://<ip>:PUERTO`)."),
    },
    {
        'slug': 'indice-git-compartido-swarm',
        'titulo': 'Índice de git COMPARTIDO: nunca git add -A / commit -am',
        'categoria': 'entorno',
        'tags': ['git', 'commit', 'swarm', 'entorno'],
        'cuerpo': (
            "Todos los agentes comparten el MISMO árbol de trabajo. Un `git add -A` o "
            "`git commit -am` se lleva puesto el trabajo sin commitear de OTROS agentes "
            "dentro de tu commit. Commiteá SIEMPRE con rutas EXPLÍCITAS: "
            "`git add <ruta1> <ruta2> && git commit -m \"...\"`. Si al stagear ves "
            "archivos que no son tuyos, dejalos afuera. Mensaje en Conventional Commits."),
    },
    {
        'slug': 'gotcha-wsl-mata-procesos-detached',
        'titulo': 'WSL apaga el distro al cerrar la última consola — los detached NO sobreviven',
        'categoria': 'entorno',
        'tags': ['wsl', 'entorno', 'gotcha'],
        'cuerpo': (
            "Cerrar la última consola de WSL apaga el distro entero a los pocos "
            "segundos, matando cualquier proceso 'detached' (`&`, `nohup`, `setsid`) y "
            "el tmux server con él. Para procesos que deben sobrevivir, corrélos dentro "
            "de una sesión tmux persistente, no como huérfanos de la shell."),
    },
]

_STORE_DIRNAME = 'memoria-global'


def _store_dir(store_dir=None) -> str:
    return store_dir or ruta_data(_STORE_DIRNAME)


def _render(m: dict, hoy: str = None) -> str:
    """Memoria de la semilla → markdown con frontmatter (marca de procedencia).
    Fecha del DÍA DE SIEMBRA (antes era un literal congelado: una semilla sin
    uso envejecía hacia la cuarentena contra una fecha que no avanzaba)."""
    hoy = hoy or date.today().isoformat()
    tags = ', '.join(m.get('tags') or [])
    return (f"---\ntitulo: {m['titulo']}\ntags: [{tags}]\n"
            f"categoria: {m['categoria']}\ncreado: {hoy}\nactualizado: {hoy}\n"
            f"autor: semilla-global\nestado: vigente\norigen: semilla-global\n---\n\n"
            f"{m['cuerpo'].strip()}\n")


def _mem_dir(project_path: str) -> str:
    return os.path.join(project_path, '.jarvis', 'memory')


def sembrar(project_path: str, store_dir=None) -> int:
    """Escribe las memorias de la semilla + del store global en el proyecto,
    SIN pisar ninguna existente. Devuelve cuántas creó (0 si ya estaban todas).
    Idempotente — apto para llamarse en cada apertura de proyecto."""
    mdir = _mem_dir(project_path)
    if not os.path.isdir(mdir):
        return 0
    creadas = 0
    # 1) semilla curada (bundleada con el código)
    for m in SEMILLA:
        dest = os.path.join(mdir, m['slug'] + '.md')
        if os.path.exists(dest):
            continue
        try:
            with open(dest, 'w', encoding='utf-8') as f:
                f.write(_render(m))
            creadas += 1
        except OSError:
            pass
    # 2) store global (lecciones promovidas) — copia byte a byte, sin pisar
    sd = _store_dir(store_dir)
    if os.path.isdir(sd):
        for nombre in sorted(os.listdir(sd)):
            if not nombre.endswith('.md'):
                continue
            dest = os.path.join(mdir, nombre)
            if os.path.exists(dest):
                continue
            try:
                with open(os.path.join(sd, nombre), encoding='utf-8') as f:
                    contenido = f.read()
                with open(dest, 'w', encoding='utf-8') as f:
                    f.write(contenido)
                creadas += 1
            except OSError:
                pass
    return creadas


def sugerir_promociones(project_path: str, store_dir=None,
                        motivos_ajenos: list = None,
                        project_id: int = None) -> list:
    """Candidatas a memoria GLOBAL calculadas por el sistema (el canal
    promover() existía pero exigía acordarse de usarlo — estaba en cero).
    Dos señales:
      - lección de ENTORNO: el box (WSL, puertos, git compartido) es el mismo
        para todos los proyectos — una lección de entorno es global por
        definición.
      - lección que matchea un motivo de fallo de OTRO proyecto: si allá
        tropezaron con esto, heredarla les hubiera ahorrado el golpe.
    Devuelve [{slug, motivo}]. El sistema PROPONE; promover es del usuario
    (POST .../promover). `motivos_ajenos` inyectable para tests."""
    from plotspace.core.memoria_endurecimiento import (lecciones_del_proyecto,
                                                     motivo_matchea)
    import re as _re
    lecciones = lecciones_del_proyecto(project_path)
    if not lecciones:
        return []
    ya_globales = {m['slug'] for m in SEMILLA}
    sd = _store_dir(store_dir)
    if os.path.isdir(sd):
        ya_globales.update(n[:-3] for n in os.listdir(sd) if n.endswith('.md'))
    # categoría por lección (frontmatter del archivo)
    cat_re = _re.compile(r'^categoria:\s*(\S+)', _re.MULTILINE)
    if motivos_ajenos is None:
        motivos_ajenos = _motivos_de_otros_proyectos(project_id)
    sugeridas, vistas = [], set()
    for lec in lecciones:
        slug = lec['slug']
        if slug in ya_globales or slug in vistas:
            continue
        src = ''
        try:
            with open(os.path.join(_mem_dir(project_path), slug + '.md'),
                      encoding='utf-8') as f:
                src = f.read()
        except OSError:
            pass
        mc = cat_re.search(src)
        if mc and mc.group(1).strip().lower() == 'entorno':
            sugeridas.append({'slug': slug, 'motivo': 'leccion-de-entorno'})
            vistas.add(slug)
            continue
        if any(motivo_matchea(m, lec['texto']) for m in motivos_ajenos):
            sugeridas.append({'slug': slug, 'motivo': 'reincide-en-otro-proyecto'})
            vistas.add(slug)
    return sugeridas


def _motivos_de_otros_proyectos(project_id, limite: int = 100) -> list:
    """Motivos de fallo de los DEMÁS proyectos (task_events) — la señal
    cruzada de sugerir_promociones. Vacío si no hay DB o datos."""
    try:
        from plotspace.core.database import get_db
        conn = get_db()
        try:
            if project_id is None:
                return []
            filas = conn.execute(
                "SELECT motivo FROM task_events WHERE project_id != ? "
                "AND motivo IS NOT NULL AND motivo != '' "
                "AND event IN ('TASK_BLOCKED','TASK_ERROR') "
                "ORDER BY id DESC LIMIT ?", (project_id, limite)).fetchall()
            return [f['motivo'] for f in filas]
        finally:
            conn.close()
    except Exception:
        return []


def promover(slug: str, project_path: str, store_dir=None) -> bool:
    """Copia una memoria del proyecto al store global (para que la hereden los
    proyectos futuros). No la mueve — queda también en el proyecto. True si ok."""
    origen = os.path.join(_mem_dir(project_path), slug + '.md')
    if not os.path.exists(origen):
        return False
    sd = _store_dir(store_dir)
    try:
        os.makedirs(sd, exist_ok=True)
        with open(origen, encoding='utf-8') as f:
            contenido = f.read()
        with open(os.path.join(sd, slug + '.md'), 'w', encoding='utf-8') as f:
            f.write(contenido)
        return True
    except OSError:
        return False
