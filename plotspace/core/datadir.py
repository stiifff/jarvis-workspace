# Directorio de datos configurable ("modo app").
#
# Por default TODO el estado local vive en <repo>/data — el comportamiento
# histórico. Cuando el shell de escritorio lanza el backend como app instalada,
# setea JARVIS_DATA_DIR para sacar los datos del directorio de instalación
# (que es read-only en una app instalada). Regla del repo: ningún módulo
# construye rutas a data/ a mano — siempre ruta_data(...).

import os

_DEFAULT = os.path.join(os.path.dirname(__file__), '..', '..', 'data')


def _resolver() -> str:
    env = os.environ.get('JARVIS_DATA_DIR', '').strip()
    base = os.path.abspath(os.path.expanduser(env or _DEFAULT))
    # Una app instalada arranca en frío: el directorio tiene que existir antes
    # de que database/auth intenten escribir en él.
    os.makedirs(base, exist_ok=True)
    return base


DATA_DIR = _resolver()


def ruta_data(*partes: str) -> str:
    """Ruta absoluta dentro del directorio de datos activo."""
    return os.path.join(DATA_DIR, *partes)
