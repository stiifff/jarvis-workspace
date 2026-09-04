#!/usr/bin/env bash
# Compila Jarvis.exe — el SHELL de escritorio fino (scripts/jarvis-shell.cs) —
# y lo deja en el Escritorio real del usuario de Windows.
#
# App con ventana propia (WebView2)
# que muestra el workspace que vive en Linux, con su pantalla de "Abrir
# workspace". NADA nativo adentro (sin motor, sin Rust): la lección del
# 2026-08-06 es que el quilombo empezó cuando la app quiso ser más que una
# ventana.
#
# El exe resuelve el repo en WSL en runtime — no bakea rutas de esta máquina:
#   $HOME/jarvis-workspace   (override: JARVIS_WSL_DIR)
#   distro default de WSL    (override: JARVIS_WSL_DISTRO)
#
# Toolchain: SOLO el csc.exe que Windows trae de fábrica (.NET Framework 4)
# + las 3 DLLs del SDK de WebView2, que se bajan de NuGet a data/ (gitignored)
# la primera vez y quedan EMBEBIDAS en el exe — un solo archivo, sin
# instalador. El runtime de WebView2 ya viene con Windows 10/11.
set -euo pipefail
cd "$(dirname "$0")"

CSC='/mnt/c/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe'
[ -x "$CSC" ] || { echo "no encuentro csc.exe (¿Windows sin .NET Framework 4?)" >&2; exit 1; }

# ── SDK de WebView2 (cacheado en data/, gitignored) ──
SDK="../data/webview2-sdk"
WV2_VERSION='1.0.2210.55'
if [ ! -f "$SDK/WebView2Loader.dll" ]; then
  echo "bajando el SDK de WebView2 ${WV2_VERSION} de NuGet…"
  mkdir -p "$SDK"
  curl -sL -o "$SDK/wv2.nupkg" \
    "https://www.nuget.org/api/v2/package/Microsoft.Web.WebView2/${WV2_VERSION}"
  python3 - "$SDK" <<'PY'
import sys, zipfile
sdk = sys.argv[1]
z = zipfile.ZipFile(sdk + '/wv2.nupkg')
for n in ('lib/net45/Microsoft.Web.WebView2.Core.dll',
          'lib/net45/Microsoft.Web.WebView2.WinForms.dll',
          'runtimes/win-x64/native/WebView2Loader.dll'):
    open(sdk + '/' + n.split('/')[-1], 'wb').write(z.read(n))
PY
fi

WINUSER=$(/mnt/c/Windows/System32/cmd.exe /c "echo %USERNAME%" 2>/dev/null | tr -d '\r\n')
# El Escritorio REAL sale del registro (puede estar redirigido a D:/OneDrive —
# en esta máquina vive en D:\Users\USER\Desktop, no en C:).
DESKTOP_WIN=$(/mnt/c/Windows/System32/reg.exe query \
    'HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders' \
    /v Desktop 2>/dev/null | grep -o '[A-Z]:\\.*' | tr -d '\r')
DESTINO=$(wslpath "${DESKTOP_WIN:-C:\\Users\\${WINUSER}\\Desktop}")
TMP="/mnt/c/Users/${WINUSER}/AppData/Local/Temp/jarvis-shell-build"

mkdir -p "$TMP"
cp jarvis-shell.cs jarvis.ico "$TMP/"
cp jarvis-shell-ui.html "$TMP/ui.html"      # el splash de siempre (recurso de texto)
cp "$SDK/Microsoft.Web.WebView2.Core.dll" \
   "$SDK/Microsoft.Web.WebView2.WinForms.dll" \
   "$SDK/WebView2Loader.dll" "$TMP/"

# System.Web.Extensions = JavaScriptSerializer (viene con el Framework, va al
# GAC — no hay DLL que shippear): lo usa la Rich Presence de Discord para
# parsear/armar el JSON del IPC.
( cd "$TMP" && "$CSC" /nologo /target:winexe /win32icon:jarvis.ico \
    /r:System.Windows.Forms.dll /r:System.Drawing.dll \
    /r:System.Web.Extensions.dll \
    /r:Microsoft.Web.WebView2.Core.dll /r:Microsoft.Web.WebView2.WinForms.dll \
    /resource:jarvis.ico /resource:ui.html \
    /out:Jarvis.exe jarvis-shell.cs )

# ── Instalación: el exe y sus DLLs juntos, como cualquier app (y como estaba
# la app vieja). Las DLLs NO se embeben: un exe sin firma que las escribe en
# disco al arrancar dispara la heurística de dropper de Defender
# (Trojan:Win32/Sabsik.FL.A!ml — pasó el 2026-08-06 con la versión "un solo
# archivo"). En el Escritorio va un acceso directo con el ícono, que es lo que
# el usuario abre.
APP="/mnt/c/Users/${WINUSER}/AppData/Local/Jarvis"
mkdir -p "$APP"

# Instalación tolerante a "la app está ABIERTA". Windows no deja sobrescribir un
# exe/DLL en uso (cp → "Permission denied"), pero SÍ deja renombrarlo. Entonces:
# si el copiado choca, corremos de nombre al viejo y copiamos encima. La ventana
# abierta sigue andando contra el archivo renombrado y el próximo doble clic ya
# toma el nuevo. Sin esto, compilar con Jarvis abierto abortaba a mitad de la
# instalación y dejaba la app mezclada (exe nuevo con DLLs viejas, o nada).
rm -f "$APP"/*.viejo 2>/dev/null || true      # restos de una instalación anterior

# El origen se valida ANTES de tocar nada del destino. Aprendido a los golpes
# (2026-08-07): si el exe recién compilado quedó ILEGIBLE —Defender lo marca
# como Trojan:Win32/Sabsik.FL.A!ml, un falso positivo clásico contra binarios
# .NET nuevos sin firma— y uno ya renombró el viejo, el usuario se queda SIN
# app y con el acceso directo roto. Primero verificamos, después swapeamos.
legible() { head -c 2 "$1" >/dev/null 2>&1; }

instalar() {
  local origen="$1" destino="$2/$(basename "$1")"
  if ! legible "$origen"; then
    echo "ABORTA: '$origen' no se puede leer (¿Defender lo marcó?). No toco la instalación actual." >&2
    return 1
  fi
  cp "$origen" "$destino" 2>/dev/null && return 0
  # Windows no deja SOBRESCRIBIR lo que está en uso, pero sí renombrarlo.
  mv -f "$destino" "${destino}.viejo" 2>/dev/null || true
  if ! cp "$origen" "$destino" 2>/dev/null; then
    mv -f "${destino}.viejo" "$destino" 2>/dev/null || true   # dejarlo como estaba
    echo "ABORTA: no pude copiar '$origen'. Restauré la instalación anterior." >&2
    return 1
  fi
}
for f in "$TMP/Jarvis.exe" "$TMP/jarvis.ico" \
         "$SDK/Microsoft.Web.WebView2.Core.dll" \
         "$SDK/Microsoft.Web.WebView2.WinForms.dll" \
         "$SDK/WebView2Loader.dll"; do
  instalar "$f" "$APP"
done
rm -rf "$TMP"

# Acceso directo en el Escritorio (nombre + ícono de la app).
APP_WIN="C:\\Users\\${WINUSER}\\AppData\\Local\\Jarvis"
DESTINO_WIN=$(wslpath -w "$DESTINO")
PS1="$APP/crear-acceso.ps1"
cat > "$PS1" <<PSEOF
\$s = (New-Object -ComObject WScript.Shell).CreateShortcut('${DESTINO_WIN}\\Jarvis.lnk')
\$s.TargetPath = '${APP_WIN}\\Jarvis.exe'
\$s.IconLocation = '${APP_WIN}\\jarvis.ico,0'
\$s.WorkingDirectory = '${APP_WIN}'
\$s.Description = 'Jarvis Workspace'
\$s.Save()
PSEOF
/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe \
    -NoProfile -ExecutionPolicy Bypass -File "$(wslpath -w "$PS1")" >/dev/null 2>&1 || true
rm -f "$PS1"

echo "listo: ${APP}/Jarvis.exe"
echo "       acceso directo → ${DESTINO}/Jarvis.lnk"
