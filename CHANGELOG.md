# Changelog

Las novedades del aviso de actualización se **auto-detectan del git** (los commits
nuevos, agrupados por área). Este archivo es solo el respaldo por si algún día no
hay git. Formato: `## X.Y.Z` + bullets `- …`, más nuevo arriba.

## 1.7.2
- Install: one command per OS (`install.sh` on Linux/macOS, `install.ps1` on Windows). Full app; Windows leaves Jarvis.bat on the Desktop.

## 1.7.1
- Sin token de acceso: abrís `http://localhost:3000` y entrás. El default sigue siendo 127.0.0.1.

## 1.7.0
- Voz: primer arranque pide una clave gratis de Groq y la tecla (o Mouse 1–4) para dictar.
- Cuentas: un CLI ya logueado en el sistema (Grok, Claude, …) aparece sin pulsar Conectar.
- Terminales: la rueda llega a Grok y otros TUI en buffer normal; al redimensionar ya no quedan restos de texto.

## 1.5.0
- Interfaz: el aviso de actualización muestra qué trae cada versión, agrupado por área.
- Motor: reinicio en el lugar (re-exec) — no se pierde el chat de los agentes al actualizar.
- Seguridad: transcripción de voz con límite de tamaño y archivos temporales aislados.
