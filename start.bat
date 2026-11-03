@echo off
rem Studio: sets up everything that's missing or out of date, then starts the app.
rem
rem   start.bat           check and set up what's needed, then run the app
rem   start.bat keys      ask for the API keys again, then run the app
rem   start.bat setup     only check and set up; don't run the app
rem   start.bat hidden    run the app with the Studio's window hidden
rem
rem Each step only acts if something is missing or changed, so the second time it goes straight to the app:
rem   1. Python 3.11+        (offers to install it with winget)
rem   2. ffmpeg              (offers to install it with winget)
rem   3. .venv               (created; pipeline\requirements.txt installed again when it changes)
rem   4. the voice-over      (pipeline\requirements-voice.txt and Meta's MMS voice, once; optional:
rem                           without them the ads are made with no voice-over)
rem   5. the Studio          (built with CMake and Visual Studio 2019 16.8+, and rebuilt when its code
rem                           changes; a release zip's prebuilt one is used as it is)
rem   6. the API keys        (.env, asked for and typed hidden)
rem   7. a check             (a Studio just built renders its test frame)
rem   8. the app             http://127.0.0.1:8000, the browser opens on it; Ctrl+C here stops it
rem
rem While it runs: this window shows the app's log; the Studio's window shows the renderer building
rem and rendering each shot (closing it stops the run in progress).

setlocal
cd /d "%~dp0"
title Studio
set "MODE=%~1"
set "VENV_PY=.venv\Scripts\python.exe"
set "STUDIO_BIN=build\Release\Studio.exe"
set PORT=8000
set "BUILT_NOW="

echo.
echo  Studio: a product photo and a brief in, a finished 3D ad out
echo  ------------------------------------------------------------
echo.

rem ---- 1. Python ---------------------------------------------------------------------------
echo [1/8] Python 3.11 or newer
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
echo [2/8] ffmpeg
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
echo [3/8] Python environment (.venv)
if exist "%VENV_PY%" goto :venv_packages
echo       Creating it...
%PY% -m venv .venv || goto :fail
:venv_packages
fc /b pipeline\requirements.txt .venv\requirements.installed >nul 2>&1
if errorlevel 1 goto :venv_install
echo       packages up to date
goto :voice
:venv_install
echo       Installing the packages (pipeline\requirements.txt)...
"%VENV_PY%" -m pip install --upgrade pip --quiet
"%VENV_PY%" -m pip install -r pipeline\requirements.txt --quiet || goto :fail
copy /y pipeline\requirements.txt .venv\requirements.installed >nul
echo       done

rem ---- 4. The voice-over (optional) --------------------------------------------------------
:voice
echo [4/8] The voice-over (torch, transformers and Meta's MMS voice)
fc /b pipeline\requirements-voice.txt .venv\requirements-voice.installed >nul 2>&1
if errorlevel 1 goto :voice_install
echo       packages up to date
goto :voice_model
:voice_install
echo       Installing them (pipeline\requirements-voice.txt, about 300 MB, once)...
"%VENV_PY%" -m pip install -r pipeline\requirements-voice.txt --quiet
if errorlevel 1 goto :voice_failed
copy /y pipeline\requirements-voice.txt .venv\requirements-voice.installed >nul
echo       done
:voice_model
if exist ".venv\voice.ready" goto :voice_ready
echo       Fetching the voice (facebook/mms-tts-eng, about 150 MB, once)...
"%VENV_PY%" -c "from pipeline.encode import speech; speech._load()" >nul 2>&1
if errorlevel 1 goto :voice_failed
echo ready> .venv\voice.ready
:voice_ready
echo       ready
goto :studio
:voice_failed
echo       Couldn't set it up (see above): the app runs, and its ads are made without a voice-over.
echo       start.bat tries again next time.

rem ---- 5. The Studio (renderer) ------------------------------------------------------------
:studio
echo [5/8] The Studio (%STUDIO_BIN%)
rem A Studio with no build folder came prebuilt (the release zip): used as it is.
if exist "%STUDIO_BIN%" if not exist "build\CMakeCache.txt" goto :studio_prebuilt
rem The newest Visual Studio with the C++ compiler, any edition (Community, Professional,
rem Enterprise, Build Tools): 2019 16.8 or newer (C11), 2022, 2026, or later.
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%VSWHERE%" goto :no_vs
set "VSDIR="
set "VSVER="
set "VSNAME="
set "VC=-latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64"
for /f "usebackq delims=" %%p in (`"%VSWHERE%" %VC% -property installationPath`) do set "VSDIR=%%p"
if not defined VSDIR goto :no_vs
for /f "usebackq tokens=1 delims=." %%v in (`"%VSWHERE%" %VC% -property installationVersion`) do set "VSVER=%%v"
for /f "usebackq delims=" %%n in (`"%VSWHERE%" %VC% -property displayName`) do set "VSNAME=%%n"
if not defined VSVER goto :no_vs
echo       Found %VSNAME% (version %VSVER%)
if %VSVER% LSS 16 goto :vs_too_old
rem CMake's generator for it; a version newer than these is left to its own CMake, which knows it.
set "GEN="
if "%VSVER%"=="16" set "GEN=Visual Studio 16 2019"
if "%VSVER%"=="17" set "GEN=Visual Studio 17 2022"
if "%VSVER%"=="18" set "GEN=Visual Studio 18 2026"
if "%VSVER%"=="16" echo       Note: the engine's libraries in Deps\Libs were built with Visual Studio 2022; 2019 may not link them.
rem CMake: the one inside that Visual Studio (it always knows its own generator), else one on the PATH.
set "CMAKE=%VSDIR%\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
if exist "%CMAKE%" goto :build
set "CMAKE=cmake"
where cmake >nul 2>&1 && goto :build
echo       No CMake: add "C++ CMake tools for Windows" in the Visual Studio Installer, or install it from
echo       https://cmake.org/download/  -- then run start.bat again.
goto :studio_without_vs
:vs_too_old
echo       Too old: the Studio is C11, which needs Visual Studio 2019 16.8 or newer.
:no_vs
if exist "%STUDIO_BIN%" goto :studio_unchecked
echo       Building it needs Visual Studio 2019 16.8 or newer (2022 recommended), or the free Build Tools,
echo       with "Desktop development with C++": https://visualstudio.microsoft.com/downloads/
echo       Or download the release zip, whose Studio comes built. Then run start.bat again.
goto :stop
:studio_without_vs
if exist "%STUDIO_BIN%" goto :studio_unchecked
goto :stop
:studio_unchecked
echo       Using the Studio built before: with no compiler it can't be brought up to date with the code.
goto :keys
:studio_prebuilt
echo       prebuilt (release)
goto :keys
:build
rem A build folder made by another Visual Studio: its CMake cache would be refused, so it goes
rem (only the cache: CMake makes it again).
if not exist "build\CMakeCache.txt" goto :configure
if not defined GEN goto :compile
findstr /c:"CMAKE_GENERATOR:INTERNAL=%GEN%" build\CMakeCache.txt >nul && goto :compile
echo       The build folder was made by another Visual Studio: clearing its CMake cache.
del /q build\CMakeCache.txt
rmdir /s /q build\CMakeFiles
:configure
echo       Configuring the build (once)...
set "GENARG="
if defined GEN set GENARG=-G "%GEN%"
"%CMAKE%" -S . -B build %GENARG% -A x64 -DCMAKE_GENERATOR_INSTANCE="%VSDIR%" >build_studio.log 2>&1 || goto :build_failed
:compile
rem Every time: only what changed is compiled (seconds when nothing has), so the Studio keeps up with
rem its code. Its time, to the second (a file's time in cmd is to the minute), tells whether it was linked again.
set "BEFORE="
if exist "%STUDIO_BIN%" call :mtime BEFORE
if not defined BEFORE echo       Building it (a few minutes, once)...
if defined BEFORE echo       Bringing it up to date with its code...
"%CMAKE%" --build build --config Release >>build_studio.log 2>&1 || goto :build_failed
if not exist "%STUDIO_BIN%" goto :build_failed
del build_studio.log >nul 2>&1
set "AFTER="
call :mtime AFTER
if "%BEFORE%"=="%AFTER%" goto :studio_current
set "BUILT_NOW=1"
echo       built
goto :keys
:studio_current
echo       up to date
goto :keys
:build_failed
if not exist "%STUDIO_BIN%" goto :build_failed_none
echo       Couldn't bring it up to date (see build_studio.log; a Studio still running can't be replaced):
echo       using the one built before.
goto :keys
:build_failed_none
echo       The build failed: see build_studio.log.
goto :stop

rem ---- 6. API keys -------------------------------------------------------------------------
:keys
echo [6/8] API keys (.env)
set "ASK="
if /i "%MODE%"=="keys" set "ASK=--ask"
"%VENV_PY%" scripts\setup_env.py %ASK%

rem ---- 7. A check --------------------------------------------------------------------------
echo [7/8] A check
if defined BUILT_NOW goto :check_studio
echo       nothing new to check (the Studio wasn't built again)
goto :after_check
:check_studio
echo       The Studio just built renders its test frame...
"%STUDIO_BIN%" --check build\check.png >nul 2>&1
if errorlevel 1 goto :check_failed
del build\check.png >nul 2>&1
echo       ok
goto :after_check
:check_failed
echo       The Studio just built couldn't render (its graphics driver needs OpenGL 4.5): ads can't be made.
goto :stop
:after_check
echo.
if /i not "%MODE%"=="setup" goto :app
echo  Set up. Run start.bat to start the app.
goto :stop
:app

rem ---- 8. The app --------------------------------------------------------------------------
echo [8/8] The app
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
:mtime
rem The Studio's modification time in seconds, into the variable named %1.
"%VENV_PY%" -c "import os; print(os.path.getmtime(r'%STUDIO_BIN%'))" > build\studio.mtime
set /p "%~1=" < build\studio.mtime
del build\studio.mtime >nul 2>&1
exit /b

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
