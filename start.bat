@echo off
rem Studio: sets everything up that's missing, then starts the app.
rem
rem   start.bat           check and set up what's missing, then run the app
rem   start.bat keys      ask for the API keys again, then run the app
rem   start.bat setup     only check and set up; don't run the app
rem   start.bat hidden    run the app with the Studio's window hidden
rem
rem Each step only acts if something is missing, so the second time it goes straight to the app:
rem   1. Python 3.11+        (offers to install it with winget)
rem   2. ffmpeg              (offers to install it with winget)
rem   3. .venv               (created; pipeline\requirements.txt installed again when it changes)
rem   4. the Studio          (built with CMake and Visual Studio 2022)
rem   5. the API keys        (.env, asked for and typed hidden)
rem   6. the app             http://127.0.0.1:8000, the browser opens on it; Ctrl+C here stops it
rem
rem While it runs: this window shows the app's log; the Studio's window shows the renderer building
rem and rendering each shot (closing it stops the run in progress).

setlocal
cd /d "%~dp0"
title Studio
set "MODE=%~1"
set "VENV_PY=.venv\Scripts\python.exe"
set PORT=8000

echo.
echo  Studio: a product photo and a brief in, a finished 3D ad out
echo  ------------------------------------------------------------
echo.

rem ---- 1. Python ---------------------------------------------------------------------------
echo [1/6] Python 3.11 or newer
if not exist "%VENV_PY%" goto :python_find
echo       .venv already made
goto :ffmpeg
:python_find
set "PY="
py -3 -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>&1 && set "PY=py -3"
if not defined PY python -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>&1 && set "PY=python"
if defined PY goto :python_found
echo       Not found.
call :ask "      Install Python 3.13 with winget"
if errorlevel 2 goto :python_manual
winget install --id Python.Python.3.13 -e --accept-source-agreements --accept-package-agreements
echo.
echo       Installed. Close this window and run start.bat again, so it sees the new Python.
goto :stop
:python_manual
echo       Install Python 3.11+ from https://www.python.org/downloads/ ("Add to PATH" ticked),
echo       then run start.bat again.
goto :stop
:python_found
for /f "delims=" %%v in ('%PY% --version') do echo       %%v

rem ---- 2. ffmpeg ---------------------------------------------------------------------------
:ffmpeg
echo [2/6] ffmpeg
where ffmpeg >nul 2>&1
if errorlevel 1 goto :ffmpeg_missing
echo       found
goto :venv
:ffmpeg_missing
echo       Not found: the videos and music are encoded with it.
call :ask "      Install ffmpeg with winget"
if errorlevel 2 goto :ffmpeg_manual
winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
echo.
echo       Installed. Close this window and run start.bat again, so it sees ffmpeg.
goto :stop
:ffmpeg_manual
echo       Install ffmpeg (https://ffmpeg.org/download.html) and put its bin folder on the PATH.
goto :stop

rem ---- 3. The Python environment -----------------------------------------------------------
:venv
echo [3/6] Python environment (.venv)
if exist "%VENV_PY%" goto :venv_packages
echo       Creating it...
%PY% -m venv .venv || goto :fail
:venv_packages
fc /b pipeline\requirements.txt .venv\requirements.installed >nul 2>&1
if errorlevel 1 goto :venv_install
echo       packages up to date
goto :studio
:venv_install
echo       Installing the packages (pipeline\requirements.txt)...
"%VENV_PY%" -m pip install --upgrade pip --quiet
"%VENV_PY%" -m pip install -r pipeline\requirements.txt --quiet || goto :fail
copy /y pipeline\requirements.txt .venv\requirements.installed >nul
echo       done

rem ---- 4. The Studio (renderer) ------------------------------------------------------------
:studio
echo [4/6] The Studio (build\Release\Studio.exe)
if not exist "build\Release\Studio.exe" goto :studio_build
echo       built
goto :keys
:studio_build
set "CMAKE=cmake"
where cmake >nul 2>&1 && goto :build
rem No cmake on the PATH: Visual Studio 2022 ships one.
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%VSWHERE%" goto :no_vs
for /f "usebackq delims=" %%p in (`"%VSWHERE%" -latest -property installationPath`) do set "VSDIR=%%p"
set "CMAKE=%VSDIR%\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
if exist "%CMAKE%" goto :build
:no_vs
echo       Building it needs Visual Studio 2022 with "Desktop development with C++" (it includes CMake):
echo       https://visualstudio.microsoft.com/downloads/  -- then run start.bat again.
goto :stop
:build
echo       Building it (a few minutes, once)...
"%CMAKE%" -S . -B build -G "Visual Studio 17 2022" -A x64 >build_studio.log 2>&1 || goto :build_failed
"%CMAKE%" --build build --config Release >>build_studio.log 2>&1 || goto :build_failed
if not exist "build\Release\Studio.exe" goto :build_failed
del build_studio.log >nul 2>&1
echo       built
goto :keys
:build_failed
echo       The build failed: see build_studio.log.
goto :stop

rem ---- 5. API keys -------------------------------------------------------------------------
:keys
echo [5/6] API keys (.env)
set "ASK="
if /i "%MODE%"=="keys" set "ASK=--ask"
"%VENV_PY%" scripts\setup_env.py %ASK%
echo.
if /i not "%MODE%"=="setup" goto :app
echo  Set up. Run start.bat to start the app.
goto :stop
:app

rem ---- 6. The app --------------------------------------------------------------------------
echo [6/6] The app
set PYTHONUNBUFFERED=1
set STUDIO_VISIBLE=1
if /i "%MODE%"=="hidden" set STUDIO_VISIBLE=0
rem The browser opens once the app answers (up to 60 s), from a second window that closes itself then.
start "open browser" /min cmd /c "for /l %%i in (1,1,60) do (curl -s -o nul http://127.0.0.1:%PORT%/ && (start "" http://127.0.0.1:%PORT%/ & exit) || timeout /t 1 /nobreak >nul)"
echo       http://127.0.0.1:%PORT%/  (the browser opens on it; Ctrl+C here stops it)
echo.
"%VENV_PY%" -m app --port %PORT%
echo.
echo  The app has stopped.
goto :stop

rem ---- helpers -----------------------------------------------------------------------------
:ask
rem Y or N; errorlevel 1 for yes, 2 for no.
choice /c YN /m %1
exit /b %errorlevel%

:fail
echo.
echo  Something went wrong above.
:stop
echo.
pause
endlocal
