"""
memoria_scan — el "Repo Knowledge" determinista de un proyecto nuevo.

La semilla global le da a un proyecto nuevo las lecciones de ENTORNO, pero
del repo en sí el enjambre arranca sabiendo CERO: cada agente re-descubre el
stack, cómo se instala, cómo se corre y cómo se testea. Este scanner lee los
manifiestos reales (package.json, requirements.txt, pyproject, Cargo.toml,
go.mod, docker-compose) y deja ese conocimiento como memoria
`stack-y-comandos.md` — el patrón "Repo Knowledge", en versión
determinista: cero API, cero tokens, solo hechos verificables del disco.

Corre desde asegurar_memoria_proyecto (al preparar el proyecto). Guardas:
no pisa un scan existente, y si el corpus ya tiene memoria viva (>5) no
escribe nada — el scan es para proyectos amnésicos, no para sumar ruido.
"""
import json
import os
from datetime import date

SCAN_BASENAME = 'stack-y-comandos.md'
_MAX_MEMORIAS_PARA_SCAN = 5
_MAX_DIRS = 8
_DIRS_IGNORADOS = {'.git', '.jarvis', '.workspace', 'node_modules', 'venv',
                   '.venv', '__pycache__', 'dist', 'build', '.next', 'target'}


def _leer(path: str) -> str:
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            return f.read()
    except OSError:
        return ''


def _detectar_node(project_path: str, info: dict) -> None:
    pkg_path = os.path.join(project_path, 'package.json')
    if not os.path.exists(pkg_path):
        return
    try:
        pkg = json.loads(_leer(pkg_path) or '{}')
    except ValueError:
        return
    deps = {**pkg.get('dependencies', {}), **pkg.get('devDependencies', {})}
    scripts = pkg.get('scripts', {}) or {}
    # framework por dependencia (la primera que matchea nombra el stack)
    for dep, nombre in (('next', 'Next.js'), ('expo', 'Expo'),
                        ('react-native', 'React Native'), ('astro', 'Astro'),
                        ('svelte', 'Svelte'), ('vue', 'Vue'),
                        ('vite', 'Vite'), ('react', 'React'),
                        ('express', 'Express'), ('fastify', 'Fastify')):
        if dep in deps:
            info['stack'].append(f'{nombre} (node)')
            break
    else:
        info['stack'].append('Node.js')
    # gestor por lockfile
    if os.path.exists(os.path.join(project_path, 'pnpm-lock.yaml')):
        gestor, run = 'pnpm', 'pnpm'
    elif os.path.exists(os.path.join(project_path, 'yarn.lock')):
        gestor, run = 'yarn', 'yarn'
    else:
        gestor, run = 'npm', 'npm run'
    info['instalar'].append(f'{gestor} install')
    for script, destino in (('dev', 'correr'), ('start', 'correr'), ('test', 'tests')):
        if script in scripts:
            comando = f'{run} {script}' if not (gestor == 'npm' and script in ('start', 'test')) \
                else f'npm {script}'
            info[destino].append(f'{comando}  ({scripts[script][:60]})')


def _detectar_python(project_path: str, info: dict) -> None:
    reqs = os.path.join(project_path, 'requirements.txt')
    pyproject = os.path.join(project_path, 'pyproject.toml')
    contenido = ''
    if os.path.exists(reqs):
        contenido = _leer(reqs).lower()
        info['instalar'].append('pip install -r requirements.txt')
    elif os.path.exists(pyproject):
        contenido = _leer(pyproject).lower()
        info['instalar'].append('pip install -e .')
    else:
        return
    for dep, nombre in (('fastapi', 'FastAPI'), ('django', 'Django'),
                        ('flask', 'Flask'), ('streamlit', 'Streamlit')):
        if dep in contenido:
            info['stack'].append(f'{nombre} (python)')
            break
    else:
        info['stack'].append('Python')
    if 'uvicorn' in contenido:
        info['correr'].append('uvicorn <modulo>:app --reload  (ver el entrypoint real)')
    if 'pytest' in contenido or os.path.isdir(os.path.join(project_path, 'tests')):
        info['tests'].append('pytest')


def _detectar_otros(project_path: str, info: dict) -> None:
    if os.path.exists(os.path.join(project_path, 'Cargo.toml')):
        info['stack'].append('Rust')
        info['correr'].append('cargo run')
        info['tests'].append('cargo test')
    if os.path.exists(os.path.join(project_path, 'go.mod')):
        info['stack'].append('Go')
        info['correr'].append('go run .')
        info['tests'].append('go test ./...')
    if (os.path.exists(os.path.join(project_path, 'docker-compose.yml'))
            or os.path.exists(os.path.join(project_path, 'compose.yml'))):
        info['correr'].append('docker compose up')
    if not info['stack'] and os.path.exists(os.path.join(project_path, 'index.html')):
        info['stack'].append('Sitio estático (HTML)')


def detectar(project_path: str):
    """Señales del repo: {stack, instalar, correr, tests, estructura} o None
    si no hay nada que saber (proyecto vacío)."""
    info = {'stack': [], 'instalar': [], 'correr': [], 'tests': [], 'estructura': []}
    _detectar_node(project_path, info)
    _detectar_python(project_path, info)
    _detectar_otros(project_path, info)
    try:
        dirs = sorted(e for e in os.listdir(project_path)
                      if os.path.isdir(os.path.join(project_path, e))
                      and e not in _DIRS_IGNORADOS and not e.startswith('.'))
        info['estructura'] = [d + '/' for d in dirs[:_MAX_DIRS]]
    except OSError:
        pass
    if not info['stack']:
        return None
    return info


def _cuerpo(info: dict) -> str:
    lineas = ["Auto-detectado de los manifiestos del repo al preparar el proyecto — "
              "verificalo y actualizá esta memoria si cambia.\n"]
    lineas.append(f"**Stack:** {', '.join(info['stack'])}")
    if info['instalar']:
        lineas.append(f"**Instalar:** `{'` · `'.join(info['instalar'])}`")
    if info['correr']:
        lineas.append('**Correr:** ' + ' · '.join(f'`{c}`' for c in info['correr']))
    if info['tests']:
        lineas.append('**Tests:** ' + ' · '.join(f'`{c}`' for c in info['tests']))
    if info['estructura']:
        lineas.append(f"**Estructura:** {' '.join(info['estructura'])}")
    lineas.append("\nRecordá la regla de puertos del proyecto (el 3000 es de Jarvis) "
                  "al levantar cualquier server — ver [[regla-de-puertos]].")
    return '\n'.join(lineas)


def sembrar_scan(project_path: str, hoy: str = None) -> bool:
    """Escribe stack-y-comandos.md si el proyecto es 'nuevo' (corpus chico),
    el archivo no existe y hay algo que decir. True si escribió."""
    mdir = os.path.join(project_path, '.jarvis', 'memory')
    if not os.path.isdir(mdir):
        return False
    dest = os.path.join(mdir, SCAN_BASENAME)
    if os.path.exists(dest):
        return False
    try:
        memorias = [n for n in os.listdir(mdir)
                    if n.endswith('.md') and n != 'INDEX.md']
    except OSError:
        return False
    if len(memorias) > _MAX_MEMORIAS_PARA_SCAN:
        return False       # corpus vivo: el scan llegó tarde, no sumar ruido
    info = detectar(project_path)
    if not info:
        return False
    hoy = hoy or date.today().isoformat()
    resumen = f"Stack {', '.join(info['stack'])}" + (
        f" — correr: {info['correr'][0].split('  ')[0]}" if info['correr'] else '')
    try:
        with open(dest, 'w', encoding='utf-8') as f:
            f.write(f"---\ntitulo: Stack y comandos del proyecto (auto-detectado)\n"
                    f"tags: [stack, comandos, arranque]\ncategoria: entorno\n"
                    f"resumen: {resumen}\n"
                    f"creado: {hoy}\nactualizado: {hoy}\nautor: scan-automatico\n"
                    f"estado: vigente\norigen: scan-automatico\n---\n\n"
                    f"{_cuerpo(info)}\n")
        return True
    except OSError:
        return False
