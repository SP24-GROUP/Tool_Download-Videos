@echo off
setlocal
pushd "%~dp0" || (echo ERROR: Cannot open application folder.& pause & exit /b 1)
echo Checking required tools...

set "PYTHON=py -3"
py -3 -c "import sys; raise SystemExit(sys.version_info < (3, 11))" >nul 2>&1
if errorlevel 1 (
  set "PYTHON=python"
  python -c "import sys; raise SystemExit(sys.version_info < (3, 11))" >nul 2>&1
  if errorlevel 1 (
    echo ERROR: Python 3.11 or newer is required. Install Python from https://www.python.org/downloads/windows/
    echo Check "Add python.exe to PATH" in the installer, then rerun setup.bat.
    goto :failed
  )
)

where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo ERROR: FFmpeg is missing from PATH. Install FFmpeg and add its bin folder to PATH.
  echo See WINDOWS_INSTALL.md for the download link and instructions.
  goto :failed
)
ffmpeg -version >nul 2>&1
if errorlevel 1 (echo ERROR: FFmpeg was found but could not run.& goto :failed)
where ffprobe >nul 2>&1
if errorlevel 1 (
  echo ERROR: FFprobe is missing from PATH. It normally comes with FFmpeg.
  goto :failed
)
ffprobe -version >nul 2>&1
if errorlevel 1 (echo ERROR: FFprobe was found but could not run.& goto :failed)
where deno >nul 2>&1
if errorlevel 1 (
  echo ERROR: Deno 2.3 or newer is required for full YouTube support.
  echo See WINDOWS_INSTALL.md for installation instructions.
  goto :failed
)
deno eval "const [major,minor]=Deno.version.deno.split('.').map(Number);Deno.exit(major>2||major===2&&minor>=3?0:1)" >nul 2>&1
if errorlevel 1 (
  echo ERROR: Deno 2.3 or newer is required. Update Deno, then rerun setup.bat.
  goto :failed
)

echo Creating virtual environment for this laptop...
%PYTHON% -m venv --clear .venv
if errorlevel 1 (
  echo ERROR: Could not create the virtual environment.
  goto :failed
)
echo Installing Python dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :pip_failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :pip_failed
".venv\Scripts\python.exe" -c "import fastapi, uvicorn, yt_dlp, yt_dlp_ejs; print('Python dependencies ready')"
if errorlevel 1 goto :pip_failed
if not exist downloads mkdir downloads
echo.
echo Setup complete. Double-click start.bat to open the app.
popd
pause
exit /b 0

:pip_failed
echo ERROR: Python dependency installation failed. Check the message above and your Internet connection.
:failed
popd
pause
exit /b 1
