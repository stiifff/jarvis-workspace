"""git corrido por el motor: nunca interactivo.

POR QUÉ EXISTE
==============
El motor llama a git desde pollers de fondo (`fe_watch` hace `git push` con
AUTO_PUSH, el updater compara commits, el enjambre lee historial). Ninguno de
esos caminos tiene un usuario mirando.

Ante la falta de credenciales, git NO falla: pregunta. Y en Windows el Git
Credential Manager pregunta con una VENTANA. El 2026-07-27 abrir la app plantaba
un diálogo «Connect to GitHub — Sign in» que nadie había pedido, disparado por
el auto-push contra un repo privado por HTTPS.

Además de molesto, cuelga: `subprocess.run(..., timeout=120)` con un git
esperando input son dos minutos de proceso trabado por intento.

La regla es simple: **si faltan credenciales, que falle y se loguee.** Quien
tenga que autenticarse lo hace en su terminal, a mano, una vez.
"""
import os
from typing import Dict, Optional

# Las tres puertas por las que git pide credenciales, todas cerradas:
#   GIT_TERMINAL_PROMPT  el prompt de texto en la terminal
#   GCM_INTERACTIVE      la GUI del Git Credential Manager (Windows)
#   *_ASKPASS            el programa gráfico al que git delega el pedido
_NO_INTERACTIVO = {
    'GIT_TERMINAL_PROMPT': '0',
    'GCM_INTERACTIVE': 'never',
    'GIT_ASKPASS': '',
    'SSH_ASKPASS': '',
}


def entorno_no_interactivo(base: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """El entorno del proceso + las guardas anti-prompt.

    Es una COPIA: mutar `os.environ` le cambiaría el entorno a todo el proceso,
    incluidas las terminales de los agentes. Y se parte del entorno real, no de
    uno vacío — sin PATH ni HOME, git no se encuentra ni a sí mismo, y las
    credenciales que SÍ están configuradas dejarían de verse.
    """
    env = dict(os.environ if base is None else base)
    env.update(_NO_INTERACTIVO)
    return env
