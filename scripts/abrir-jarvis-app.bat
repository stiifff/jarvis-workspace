@echo off
REM ── Jarvis — LA puerta de entrada desde Windows (post-app nativa) ──
REM
REM Doble clic y listo: si el server no esta corriendo lo levanta dentro de
REM WSL (scripts/reiniciar-server.sh) y despues abre el workspace como APP
REM en Chrome (ventana limpia, sin barra de pestanas ni omnibox).
REM
REM Guarda este .bat en Windows (ej. el Escritorio) y hace doble clic.
REM
REM Paths (no hardcodear maquina ajena):
REM   - Repo en WSL: $HOME/jarvis-workspace  (override: JARVIS_WSL_DIR)
REM   - Distro: la default de WSL            (override: JARVIS_WSL_DISTRO)
REM
REM Detalles:
REM   - El health se chequea por 127.0.0.1 (el NOMBRE localhost resuelve ::1
REM     primero y WSL no escucha ahi), pero la ventana abre por localhost:
REM     Chrome cae solo a IPv4, y la Radio necesita ese origen para YouTube.
REM   - Variante kiosk (pantalla completa total, salir con Alt+F4): comenta
REM     la linea del start normal y descomenta la de --kiosk.

setlocal EnableExtensions
set "URL=http://localhost:3000"
set "HEALTH=http://127.0.0.1:3000/api/health"
set intentos=0

if defined JARVIS_WSL_DISTRO (
  set "WSL=wsl.exe -d %JARVIS_WSL_DISTRO%"
) else (
  set "WSL=wsl.exe"
)

curl -s -o NUL --max-time 2 %HEALTH% && goto abrir

echo Levantando Jarvis en WSL...
REM Warm-up primero: si la distro esta FRIA (Windows recien reiniciado, o un
REM `wsl --shutdown`), el primer wsl.exe se va entero en bootearla y el comando
REM de abajo se perderia. Y el log va a data/ del repo, NO a /tmp: /tmp en WSL
REM es tmpfs y se borra en cada arranque de la distro — justo lo que uno
REM necesita leer cuando esto falla.
%WSL% -- true
if errorlevel 1 (
  echo No pude hablar con WSL. Instala Ubuntu u otra distro y reinicia.
  pause
  exit /b 1
)

REM Repo = JARVIS_WSL_DIR, o $HOME/jarvis-workspace adentro de la distro.
REM Windows reenvia JARVIS_WSL_DIR al entorno de WSL si esta seteada.
%WSL% -- bash -lc "REPO=\"${JARVIS_WSL_DIR:-$HOME/jarvis-workspace}\"; if [ ! -f \"$REPO/scripts/reiniciar-server.sh\" ]; then echo \"NO_REPO:$REPO\" >&2; exit 42; fi; cd \"$REPO\" && mkdir -p data && setsid nohup bash scripts/reiniciar-server.sh >>data/lanzador.log 2>&1 </dev/null & exit 0"
if errorlevel 42 goto sin_repo
if errorlevel 1 goto fallo

:esperar
curl -s -o NUL --max-time 2 %HEALTH% && goto abrir
set /a intentos+=1
if %intentos% geq 90 goto fallo
timeout /t 1 /nobreak >NUL
goto esperar

:abrir
set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=%LocalAppData%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" (
  start "" %URL%
  exit /b 0
)
start "" "%CHROME%" --app=%URL% --new-window
REM start "" "%CHROME%" --kiosk %URL% --new-window
exit /b 0

:sin_repo
echo No encuentro Jarvis Workspace dentro de WSL.
echo Clonalo ahi ^(nombre publico del repo^):
echo   git clone https://github.com/stiifff/jarvis-workspace.git ~/jarvis-workspace
echo Si ya esta en otra ruta, setea la variable de entorno JARVIS_WSL_DIR
echo a esa ruta Linux ^(ej. /home/vos/mis-apps/jarvis-workspace^).
pause
exit /b 1

:fallo
echo No pude levantar el server tras 90s. Proba a mano dentro de WSL:
echo   bash ~/jarvis-workspace/scripts/reiniciar-server.sh
echo (log del intento: ~/jarvis-workspace/data/lanzador.log)
echo Repo en otra ruta? setea JARVIS_WSL_DIR. Otra distro? setea JARVIS_WSL_DISTRO.
pause
exit /b 1
