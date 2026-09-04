"""
Tests: memoria_scan — el "Repo Knowledge" determinista de un proyecto nuevo.

Un proyecto recién agregado arranca con 3 memorias de entorno (semilla) pero
CERO conocimiento del repo: cada agente re-descubre el stack, cómo se corre y
cómo se testea. Este scanner (cero API, stdlib) detecta eso de los manifiestos
reales (package.json, requirements.txt, etc.) y lo deja como memoria
`stack-y-comandos.md` — el agente es productivo en el minuto 1 (patrón
Repo Knowledge, versión determinista).

Invariantes:
1. Node (package.json + lockfile) → gestor correcto + scripts reales.
2. Python (requirements/pyproject) → pip install + pytest si hay tests.
3. Proyecto vacío → no escribe nada (no hay qué saber).
4. Corpus ya poblado (>5 memorias) → skip: el proyecto ya tiene memoria viva.
5. Idempotente: nunca pisa un stack-y-comandos.md existente.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plotspace.core import memoria_scan as ms


def _proj(d, archivos: dict):
    for ruta, contenido in archivos.items():
        path = os.path.join(d, ruta)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(contenido)
    os.makedirs(os.path.join(d, '.jarvis', 'memory'), exist_ok=True)


def test_detecta_node_con_gestor_y_scripts():
    with tempfile.TemporaryDirectory() as d:
        _proj(d, {
            'package.json': json.dumps({
                'scripts': {'dev': 'vite', 'test': 'vitest run', 'build': 'vite build'},
                'dependencies': {'react': '^18'},
                'devDependencies': {'vite': '^5', 'vitest': '^1'},
            }),
            'yarn.lock': '',
            'src/main.jsx': 'x',
        })
        info = ms.detectar(d)
        assert 'React' in ' '.join(info['stack']) or 'Vite' in ' '.join(info['stack'])
        assert any('yarn dev' in c for c in info['correr'])
        assert any('yarn test' in c for c in info['tests'])
        assert any('yarn install' in c for c in info['instalar'])


def test_detecta_python_fastapi_y_pytest():
    with tempfile.TemporaryDirectory() as d:
        _proj(d, {
            'requirements.txt': 'fastapi\nuvicorn\npytest\n',
            'app/main.py': 'x',
            'tests/test_x.py': 'x',
        })
        info = ms.detectar(d)
        assert any('FastAPI' in s for s in info['stack'])
        assert any('pip install -r requirements.txt' in c for c in info['instalar'])
        assert any('pytest' in c for c in info['tests'])


def test_proyecto_vacio_no_detecta_nada():
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, '.jarvis', 'memory'))
        assert ms.detectar(d) is None
        assert ms.sembrar_scan(d) is False
        assert not os.path.exists(
            os.path.join(d, '.jarvis', 'memory', ms.SCAN_BASENAME))


def test_sembrar_scan_escribe_memoria_valida():
    with tempfile.TemporaryDirectory() as d:
        _proj(d, {'package.json': json.dumps({'scripts': {'dev': 'next dev'},
                                              'dependencies': {'next': '^14'}})})
        assert ms.sembrar_scan(d) is True
        src = open(os.path.join(d, '.jarvis', 'memory', ms.SCAN_BASENAME)).read()
        assert 'estado: vigente' in src
        assert 'resumen:' in src
        assert 'Next.js' in src
        assert 'npm run dev' in src
        assert 'verificalo y actualizá' in src.lower() or 'auto-detectado' in src.lower()


def test_sembrar_scan_skip_corpus_poblado():
    # un proyecto con memoria viva no necesita el scan (llegó tarde)
    with tempfile.TemporaryDirectory() as d:
        _proj(d, {'package.json': json.dumps({'scripts': {'dev': 'vite'}})})
        mdir = os.path.join(d, '.jarvis', 'memory')
        for i in range(6):
            with open(os.path.join(mdir, f'm{i}.md'), 'w') as f:
                f.write(f'---\ntitulo: m{i}\ntags: [x]\nestado: vigente\n---\n\ncuerpo\n')
        assert ms.sembrar_scan(d) is False


def test_sembrar_scan_no_pisa_existente():
    with tempfile.TemporaryDirectory() as d:
        _proj(d, {'package.json': json.dumps({'scripts': {'dev': 'vite'}})})
        propio = os.path.join(d, '.jarvis', 'memory', ms.SCAN_BASENAME)
        with open(propio, 'w') as f:
            f.write('mío')
        assert ms.sembrar_scan(d) is False
        assert open(propio).read() == 'mío'


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
