@echo off
title MediaPull - one-click start
rem Everything runs relative to this script's folder, so double-clicking works
rem from any location, including paths with spaces.
cd /d "%~dp0"

echo.
echo   MediaPull one-click start
echo   =========================
echo.

rem ---------------------------------------------------------------- preflight

rem Python: prefer "python" on PATH, fall back to the "py" launcher.
set "PY_CMD="
python --version >nul 2>nul && set "PY_CMD=python"
if not defined PY_CMD py -3 --version >nul 2>nul && set "PY_CMD=py -3"
if not defined PY_CMD (
    echo   [ERROR] Python was not found on this computer.
    echo.
    echo   Install Python 3.11 or newer from:
    echo       https://www.python.org/downloads/
    echo   During install, tick "Add python.exe to PATH", then run this
    echo   script again.
    goto :fail
)

rem Require Python 3.11+.
set "PY_OK="
set "PY_VER="
for /f "tokens=2" %%v in ('%PY_CMD% --version 2^>^&1') do (
    set "PY_VER=%%v"
    for /f "tokens=1,2 delims=." %%a in ("%%v") do (
        if %%a GTR 3 set "PY_OK=1"
        if %%a EQU 3 if %%b GEQ 11 set "PY_OK=1"
    )
)
if not defined PY_OK (
    echo   [ERROR] Python %PY_VER% is too old - MediaPull needs 3.11 or newer.
    echo.
    echo   Install the latest Python from:
    echo       https://www.python.org/downloads/
    goto :fail
)
echo   [OK] Python %PY_VER%

rem Require Node.js 18+.
node --version >nul 2>nul
if errorlevel 1 (
    echo   [ERROR] Node.js was not found on this computer.
    echo.
    echo   Install Node.js 18 or newer ^(LTS is fine^) from:
    echo       https://nodejs.org/
    echo   then run this script again.
    goto :fail
)
set "NODE_OK="
set "NODE_VER="
for /f "tokens=1" %%v in ('node --version') do (
    set "NODE_VER=%%v"
    for /f "tokens=1 delims=v." %%a in ("%%v") do (
        if %%a GEQ 18 set "NODE_OK=1"
    )
)
if not defined NODE_OK (
    echo   [ERROR] Node.js %NODE_VER% is too old - MediaPull needs 18 or newer.
    echo.
    echo   Install the latest LTS from:
    echo       https://nodejs.org/
    goto :fail
)
echo   [OK] Node.js %NODE_VER%

rem ffmpeg is optional: only subtitle generation needs it, so warn, don't stop.
where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo   [WARN] ffmpeg not found - the app works, but subtitle generation
    echo          ^(speech-to-text^) needs it. Get it from https://ffmpeg.org/
    echo          and add it to PATH if you want auto-generated subtitles.
) else (
    echo   [OK] ffmpeg found
)
echo.

rem ---------------------------------------------- first-run install (server)

rem The marker file is written only after pip finishes, so an interrupted
rem install is retried on the next run.
if exist "server\.venv\.deps-installed" goto :server_deps_done
echo   [SETUP] First run: setting up the Python environment ...
if not exist "server\.venv\Scripts\python.exe" %PY_CMD% -m venv "server\.venv"
if not exist "server\.venv\Scripts\python.exe" (
    echo   [ERROR] Could not create server\.venv - see messages above.
    goto :fail
)
echo   [SETUP] Installing server dependencies ^(this can take a few minutes^) ...
"server\.venv\Scripts\python.exe" -m pip install -r "server\requirements.txt"
if errorlevel 1 (
    echo   [ERROR] Server dependency install failed - see messages above.
    goto :fail
)
> "server\.venv\.deps-installed" echo ok
:server_deps_done

rem ---------------------------------------------- first-run install (client)

if exist "client\node_modules" goto :client_deps_done
echo   [SETUP] Installing client dependencies ^(this can take a few minutes^) ...
pushd client
call npm install
if errorlevel 1 (
    popd
    echo   [ERROR] Client dependency install failed - see messages above.
    goto :fail
)
popd
:client_deps_done

rem ------------------------------------------------------------- .env files

rem Copies happen only when the .env is missing; an existing .env is never
rem touched.
if not exist "server\.env" (
    copy "server\.env.example" "server\.env" >nul
    echo   [SETUP] Created server\.env ^(defaults; add GROQ_API_KEY for subtitles^)
)
if not exist "client\.env" (
    copy "client\.env.example" "client\.env" >nul
    echo   [SETUP] Created client\.env
)

rem ------------------------------------------------------------------- run

echo.
echo   Starting MediaPull ...
echo     - backend  : http://localhost:8000  ^(window "MediaPull server"^)
echo     - frontend : http://localhost:5173  ^(window "MediaPull client"^)
echo   Close those two windows to stop MediaPull.
echo.

rem /D sets each window's working directory, so the commands inside stay
rem relative and immune to spaces in the install path.
start "MediaPull server" /D "%~dp0server" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app"
start "MediaPull client" /D "%~dp0client" cmd /k "npm run dev"

rem Give both dev servers a moment to bind before the browser asks for the page.
timeout /t 5 /nobreak >nul 2>nul

start "" "http://localhost:5173"

echo   Done. If the page shows an error, wait a few seconds and reload -
echo   the servers may still be starting.
echo.
pause
exit /b 0

:fail
echo.
pause
exit /b 1
