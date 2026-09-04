@echo off
REM ── Jarvis — LA puerta de entrada desde Windows (post-app nativa) ──
REM
REM Doble clic y listo: si el server no esta corriendo lo levanta dentro de
REM WSL (scripts/reiniciar-server.sh) y despues abre el workspace como APP
REM en Chrome (ventana limpia, sin barra de pestanas ni omnibox).
REM
REM Guarda este .bat en Windows (ej. el Escritorio) y hace doble clic.
REM
REM Detalles:
REM   - El health se chequea por 127.0.0.1 (el NOMBRE localhost resuelve ::1
REM     primero y WSL no escucha ahi), pero la ventana abre por localhost:
REM     Chrome cae solo a IPv4, y la Radio necesita ese origen para YouTube.
REM   - Variante kiosk (pantalla completa total, salir con Alt+F4): comenta
REM     la linea del start normal y descomenta la de --kiosk.

set "URL=http://localhost:3000"
set "HEALTH=http://127.0.0.1:3000/api/health"
set intentos=0

curl -s -o NUL --max-time 2 %HEALTH% && goto abrir

echo Levantando Jarvis en WSL...
REM Warm-up primero: si la distro esta FRIA (Windows recien reiniciado, o un
REM `wsl --shutdown`), el primer wsl.exe se va entero en bootearla y el comando
REM de abajo se perderia. Y el log va a data/ del repo, NO a /tmp: /tmp en WSL
REM es tmpfs y se borra en cada arranque de la distro — justo lo que uno
REM necesita leer cuando esto falla.
wsl.exe -d Ubuntu -- true
wsl.exe -d Ubuntu -- bash -lc "cd ~/jarvis && mkdir -p data && setsid nohup bash scripts/reiniciar-server.sh >>data/lanzador.log 2>&1 </dev/null & exit 0"

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

:fallo
echo No pude levantar el server tras 90s. Proba a mano dentro de WSL:
echo   bash ~/jarvis/scripts/reiniciar-server.sh
echo (log del intento: ~/jarvis/data/lanzador.log)
pause
exit /b 1
