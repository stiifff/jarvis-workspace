"""Qué CLIs de agente hay instalados, y cómo instalar los que faltan.

POR QUÉ ESTO NO EXISTÍA Y HACE FALTA
====================================
Hasta ahora Jarvis daba por hecho que los CLIs estaban: abría la terminal y
tipeaba `claude`. En una máquina de desarrollo eso es cierto. En la máquina de
alguien que acaba de instalar la app, no — y lo que ve es una terminal negra
con `claude: command not found`. Esa sería la primera impresión de todo
usuario nuevo.

LO QUE NO SE HACE
=================
**Los CLIs no se bundlean.** Son producto de otro (Anthropic, OpenAI, Google),
con su licencia, su login y su ritmo de actualización; empaquetarlos sería
redistribuir software ajeno y shippear una versión vieja el día uno. El usuario
trae sus propios agentes y sus propias cuentas — el modelo BYOK de siempre.

Lo que sí se puede es **ayudar a instalarlos**: casi todos son paquetes de npm.
La detección mira el PATH del propio server (todo corre en el mismo mundo:
Linux/WSL); el que arma nvm en el rc del usuario es el mismo que hereda uvicorn.
"""
import shutil
import subprocess
from typing import Dict, List, Optional

# Cómo se llama el ejecutable de cada uno y de qué paquete sale. `None` en
# `paquete` = no se instala por npm (Antigravity es app de escritorio; Cursor
# CLI tiene su curl-installer oficial), así que se detecta pero no se ofrece
# botón de instalar. `binarios` (tupla) son alternativas del mismo CLI: con
# que UNA exista por el PATH, se da por instalado. `npm_flags` se antepone al
# paquete en `npm install -g`.
CATALOGO = [
    {'id': 'claude',      'nombre': 'Claude Code', 'binario': 'claude',
     'paquete': '@anthropic-ai/claude-code'},
    {'id': 'codex',       'nombre': 'Codex CLI',   'binario': 'codex',
     'paquete': '@openai/codex'},
    {'id': 'opencode',    'nombre': 'opencode',    'binario': 'opencode',
     'paquete': 'opencode-ai'},
    {'id': 'qwen',        'nombre': 'Qwen Code',   'binario': 'qwen',
     'paquete': '@qwen-code/qwen-code'},
    {'id': 'antigravity', 'nombre': 'Antigravity', 'binario': 'agy',
     'paquete': None},
    {'id': 'grok',        'nombre': 'Grok Build',  'binario': 'grok',
     'paquete': '@xai-official/grok'},
    {'id': 'cursor',      'nombre': 'Cursor CLI',
     # El curl-installer oficial crea DOS symlinks al mismo binario:
     # `agent` (el nombre que documenta) y `cursor-agent` (legacy). Se sondea
     # primero el legacy para no confundirlo con cualquier OTRO `agent` que
     # ya ande en el PATH de la máquina.
     'binarios': ('cursor-agent', 'agent'), 'paquete': None},
    {'id': 'pi',          'nombre': 'Pi',          'binario': 'pi',
     'paquete': '@earendil-works/pi-coding-agent',
     # El quickstart de Pi manda `--ignore-scripts`: el paquete no necesita
     # correr los scripts de lifecycle del install y algunos entornos las
     # rechazan.
     'npm_flags': ['--ignore-scripts']},
]


def _existe_local(binario: str, path: Optional[str] = None) -> bool:
    return shutil.which(binario, path=path) is not None


def detectar(existe_local=None) -> List[Dict]:
    """Estado de cada CLI en el entorno del propio motor.

    Cada entrada: `{id, nombre, instalado, instalable}`. `instalable` es False
    cuando no hay un paquete que instalar (Antigravity) — ahí la app informa
    en vez de ofrecer un botón que no puede cumplir.
    """
    existe_local = existe_local or _existe_local

    salida = []
    for cli in CATALOGO:
        # Cada sonda va con su red: un PATH roto no puede tumbar la pantalla
        # de bienvenida entera. Ante la duda, "no instalado": ofrecer
        # instalarlo es recuperable; decir que está y que falle al abrir la
        # terminal, no.
        bins = cli.get('binarios') or ([cli['binario']] if cli.get('binario') else [])
        instalado = False
        for b in bins:
            try:
                if existe_local(b):
                    instalado = True
                    break
            except Exception:
                continue
        salida.append({
            'id': cli['id'],
            'nombre': cli['nombre'],
            'instalado': bool(instalado),
            'instalable': cli['paquete'] is not None,
        })
    return salida


def comando_instalar(cli_id: str) -> Optional[List[str]]:
    """El comando que instala ese CLI, o None si no corresponde.

    `npm install -g` y no un gestor de versiones: es la política "app-managed"
    (lo que instalamos, lo actualizamos; lo que instaló el usuario, no se
    toca)."""
    cli = next((c for c in CATALOGO if c['id'] == cli_id), None)
    if not cli or not cli['paquete']:
        return None
    return ['npm', 'install', '-g', *(cli.get('npm_flags') or []), cli['paquete']]


def hay_node(existe_local=None) -> bool:
    """¿Se puede instalar algo? Sin Node no hay npm y el botón «Instalar» sería
    una promesa vacía."""
    existe_local = existe_local or _existe_local
    try:
        return bool(existe_local('npm'))
    except Exception:
        return False


def instalar(cli_id: str, correr=None) -> Dict:
    """Instala un CLI. Bloquea hasta terminar (npm tarda minutos), así que el
    caller lo saca del event loop.

    → `{'ok', 'salida'}`. El error se devuelve TAL CUAL lo escupió npm: quien
    ve esto acaba de instalar la app y no tiene nada más para orientarse — un
    "no se pudo" genérico lo deja sin salida.
    """
    cmd = comando_instalar(cli_id)
    if not cmd:
        return {'ok': False, 'salida': 'ese agente no se instala desde acá'}
    try:
        correr = correr or subprocess.run
        r = correr(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return {'ok': False, 'salida': 'la instalación tardó demasiado (10 min) y se cortó'}
    except Exception as e:
        return {'ok': False, 'salida': str(e)}
    ok = getattr(r, 'returncode', 1) == 0
    salida = (getattr(r, 'stdout', '') or '') + (getattr(r, 'stderr', '') or '')
    return {'ok': ok, 'salida': salida.strip()[-2000:]}


def estado() -> Dict:
    """Lo que la pantalla de bienvenida necesita, de una."""
    clis = detectar()
    return {
        'clis': clis,
        'hay_node': hay_node(),
        # Si no hay NINGUNO, es un primer arranque y la app tiene algo que
        # decir; con al menos uno, se puede empezar a trabajar ya.
        'primer_arranque': not any(c['instalado'] for c in clis),
    }
