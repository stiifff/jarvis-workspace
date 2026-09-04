# Los textos del PROTOCOLO que se inyectan en el CLAUDE.md de cada proyecto.
#
# POR QUÉ SON ARCHIVOS Y NO CONSTANTES
# ====================================
# Estos textos son las instrucciones que recibe CADA agente del enjambre en
# CADA sesión. Mientras vivieron como constantes adentro de módulos de Python,
# eran inalcanzables para el motor Rust: portarlo obligaba a copiarlos, y dos
# copias de un texto largo se separan sin que nadie lo note. El día que se
# separen, cada agente recibe instrucciones distintas según qué motor le armó la
# sesión — y eso no se ve como un bug, se ve como agentes que "no siguen las
# reglas".
#
# Como archivo, hay UNA fuente y los dos motores leen la misma.
#
# El contenido incluye sus propios markers (`<!-- JARVIS_*_START -->` …): quien
# inyecta busca esos markers para reemplazar el bloque sin tocar el resto del
# archivo, así que sacarlos rompería la idempotencia de la inyección.

import os

_DIR = os.path.dirname(os.path.abspath(__file__))


def leer(nombre: str) -> str:
    """El texto crudo de un protocolo, tal cual está en disco."""
    with open(os.path.join(_DIR, f'{nombre}.md'), encoding='utf-8') as f:
        return f.read()


def memoria(categorias: str) -> str:
    """El protocolo de memoria, con la lista de categorías puesta.

    Es el único con una parte variable: las categorías salen de
    `memoria_categorias`, que es también quien las valida, así que no pueden
    quedar escritas a mano en el texto sin desincronizarse.
    """
    return leer('memoria').replace('{CATEGORIAS}', categorias)


def clis() -> list:
    """La especificación de cada CLI (dónde vive su credencial).

    Igual que los textos: el motor Rust necesita exactamente los mismos
    caminos. Si cada uno tuviera su copia, un motor podría decir "logueado" y
    el otro "no" para la misma cuenta.

    Las rutas vienen con `~` (el home del usuario) y `$CODEX_HOME` (el home
    aislado de la cuenta de Codex activa) sin expandir: quien lo lee resuelve,
    porque los dos valores cambian en caliente.
    """
    import json
    with open(os.path.join(_DIR, 'clis.json'), encoding='utf-8') as f:
        return json.load(f)
