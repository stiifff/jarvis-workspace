#!/usr/bin/env bash
# JARVIS — Reinicio del server SIN robarle el proceso a la terminal del usuario.
#
# ⚠️ HERRAMIENTA DEL USUARIO (o de Jarvis mismo). LOS AGENTES NO REINICIAN EL
# SERVER: verifican con pytest (corre el código de disco) + el smoke
# `python -c "import plotspace.main"`, y la actualización la aplica el usuario
# desde el banner "Actualizar ahora" de la UI.
#
# Camino correcto (server vivo): POST /api/system/restart → canary de arranque
# (si el código nuevo no importa, rechaza con 409 y NO reinicia) → bump de
# VERSION (1.5.0→1.5.1; hotfix 1.5.1→1.5.1.1) → os.execv re-exec in-place
# (plotspace/routers/system.py): mismo PID, misma sesión, MISMA TERMINAL.
# El server sigue alojado donde el usuario lo levantó — exactamente lo que hace
# el botón "Actualizar" de la UI.
#
# PROHIBIDO `pkill -f uvicorn` + relanzar: eso re-aloja el server en TU shell
# y el usuario pierde el mando de su terminal.
#
# Fallback (server muerto): lo levanta nohup'd en esta shell — única opción si
# no hay proceso vivo — y avisa que quedó alojado acá.
set -u
cd "$(dirname "$0")/.." || exit 1

# 127.0.0.1 y NO localhost: en este box el nombre resuelve IPv6-first (::1) y
# uvicorn escucha solo IPv4 — la regla de la casa (ver memorias wsl-*).
BASE='http://127.0.0.1:3000'
TOKEN_FILE='data/jarvis_token.txt'

vivo() { curl -s -o /dev/null -w '%{http_code}' --max-time 3 "$BASE/api/health" 2>/dev/null; }

esperar_arriba() {  # pollea /api/health hasta 120s; exit code 0 si volvió
  for _ in $(seq 1 120); do
    [ "$(vivo)" = '200' ] && return 0
    sleep 1
  done
  return 1
}

if [ "$(vivo)" = '200' ]; then
  echo "[reiniciar-server] server vivo → reinicio in-place vía POST /api/system/restart"
  # --max-time 150: el endpoint corre un canary de arranque (importa backend.main
  # en un subproceso) antes de responder — tarda varios segundos, no es un cuelgue.
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 150 -X POST \
         -b "jarvis_token=$(cat "$TOKEN_FILE")" "$BASE/api/system/restart")
  if [ "$code" = '409' ]; then
    echo "[reiniciar-server] RECHAZADO: el código nuevo no arranca (canary). El server viejo sigue vivo." >&2
    exit 1
  fi
  if [ "$code" != '200' ]; then
    echo "[reiniciar-server] ERROR: /api/system/restart devolvió '$code' (¿token de $TOKEN_FILE?)" >&2
    exit 1
  fi
  sleep 3   # el re-exec dispara a ~1s; dejarlo morir antes de pollear
  if esperar_arriba; then
    echo "[reiniciar-server] listo: server de vuelta, mismo proceso/terminal del usuario"
    exit 0
  fi
  echo "[reiniciar-server] ERROR: el server no volvió tras ~120s — revisá la terminal del usuario" >&2
  exit 1
fi

echo "[reiniciar-server] no hay server vivo → lo levanto en esta shell (fallback)"
echo "[reiniciar-server] AVISO: el server queda alojado ACÁ, no en la terminal del usuario."
source venv/bin/activate
# `setsid` y no solo `nohup`: cuando quien nos llama es Jarvis.exe (o el .bat),
# del otro lado hay un `wsl.exe` que termina apenas dispara esto. Con el uvicorn
# como hijo en la MISMA sesión, ese cierre se lo puede llevar puesto; con setsid
# queda en una sesión propia, sin terminal de control, y sobrevive a todo el
# árbol que lo lanzó. Es lo único que hace falta para que el doble clic ande.
# El log NO va a /tmp: en WSL es tmpfs y se borra en CADA arranque de la distro,
# justo el caso que uno necesita depurar (un motor que se cayó viene casi siempre
# con un boot en el medio — el 2026-08-08 el log del arranque fallido ya no
# existía). Va a data/ del repo (gitignored), con un truncado simple para que no
# crezca sin techo. Misma lección que data/lanzador.log.
LOG='data/uvicorn.log'
[ -f "$LOG" ] && [ "$(stat -c%s "$LOG" 2>/dev/null || echo 0)" -gt 5242880 ] && mv -f "$LOG" "$LOG.1"
setsid nohup python3 -m uvicorn plotspace.main:app --host 0.0.0.0 --port 3000 \
  --loop asyncio >>"$LOG" 2>&1 </dev/null &
if esperar_arriba; then
  echo "[reiniciar-server] listo: server arriba (logs en $LOG)"
  exit 0
fi
echo "[reiniciar-server] ERROR: no levantó — mirá $LOG" >&2
exit 1
