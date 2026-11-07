@echo off
setlocal
pushd "%~dp0" || (echo ERROR: Cannot open application folder.& pause & exit /b 1)
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Setup has not completed. Double-click setup.bat first.
  goto :failed
)
where ffmpeg >nul 2>&1
if errorlevel 1 (echo ERROR: FFmpeg is not on PATH. See WINDOWS_INSTALL.md.& goto :failed)
where ffprobe >nul 2>&1
if errorlevel 1 (echo ERROR: FFprobe is not on PATH. See WINDOWS_INSTALL.md.& goto :failed)
where deno >nul 2>&1
if errorlevel 1 (echo ERROR: Deno is not on PATH. See WINDOWS_INSTALL.md.& goto :failed)
echo Starting Local Video Downloader...
echo Keep this window open while downloading. Press Ctrl+C to stop the app.
".venv\Scripts\python.exe" -m downloader.main
if errorlevel 1 goto :failed
popd
exit /b 0
:failed
popd
pause
exit /b 1
