# Seguridad

## Qué expone Jarvis Workspace

Jarvis Workspace **ejecuta comandos arbitrarios**: abre terminales y corre agentes de
IA con permiso de escritura sobre tus proyectos. Cualquiera que pueda hablarle
al motor puede correr lo que quiera en tu máquina, con tu usuario.

Por eso:

- Por defecto escucha **solo en `127.0.0.1`**. Exponerlo a la red es explícito
  (`--host 0.0.0.0`) y la app avisa cuando lo hacés.
- La API y los WebSockets exigen un **token** (`data/jarvis_token.txt`).
- El motor de terminales (termhost) escucha en loopback y **exige su propia
  clave**: sin ella corta la conexión.

Si vas a abrirlo a tu red local, tratalo como lo que es: acceso a tu máquina.

## Lo que NUNCA va al repo

Las credenciales de tus cuentas de CLIs viven en `data/cli-accounts/` con
permisos 0600, nunca en la base de datos ni en git. Hay un escáner de secretos
en los hooks de git (`scripts/scan_secretos.py`) que corre antes de cada commit
y de cada push, y bloquea si detecta el formato de una API key **o el valor
real** de un secreto local.

Ese escáner no se esquiva con `--no-verify`: eso apaga también el resto de los
guards. Si hay un falso positivo, se ajusta el patrón.

## Reportar una vulnerabilidad

Abrí un [security advisory privado](https://github.com/stiifff/jarvis-workspace/security/advisories/new)
en vez de una issue pública. Se responde dentro de los 7 días.

Si encontrás algo que permita ejecución remota o escape del token, decilo por
ahí aunque no estés seguro: preferimos revisar un falso positivo.
