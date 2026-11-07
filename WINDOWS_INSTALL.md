# Windows installation

This app runs on each Windows 10 or 11 laptop. Queue history, settings, temporary files, and videos stay in that laptop's app folder. No Git, VS Code, account, or terminal is needed for everyday use.

## Install once

1. Copy the entire app folder to a location you can write to, such as `Documents\Local Video Downloader`. Do not run it directly from a ZIP file or a protected `Program Files` folder.
2. Install [Python 3.11 or newer](https://www.python.org/downloads/windows/). Select **Add python.exe to PATH** during installation.
3. Install [FFmpeg for Windows](https://ffmpeg.org/download.html#build-windows). Add the build's `bin` folder, containing both `ffmpeg.exe` and `ffprobe.exe`, to your Windows user PATH.
4. Install [Deno 2.3 or newer](https://docs.deno.com/runtime/getting_started/installation/). Ensure `deno.exe` is on PATH. Deno is needed for full YouTube support.
5. Sign out and back in, or restart Windows, if PATH changes are not recognized.
6. Double-click `setup.bat`. It checks all four required tools, rebuilds `.venv` for this laptop, and installs Python dependencies. Internet access is needed for this step.
7. Double-click `start.bat`. Your default browser opens the app. Keep the command window open while downloading.

The app uses `http://127.0.0.1:8000` when available. If port 8000 is occupied, it selects the first free port through 8010 and opens that address. If all are busy, it prints a clear error. It never binds to a LAN address.

## Everyday use

Paste one link per line, choose quality and simultaneous downloads, then click **Start downloads**. You may add more links while downloads run. Use **Open download folder** to view saved files. Closing the command window stops active downloads; interrupted jobs appear as failed on the next start and can be retried.

Videos are in `downloads` beside `start.bat`. Queue history and the concurrency setting are in `.state\jobs.json`. Copying the app folder to another laptop creates a separate installation. To move history and files intentionally, copy the `downloads` and `.state` folders too.

## Update

Replace the application code while keeping your `downloads` and `.state` folders. Double-click `setup.bat` again to update dependencies. To update yt-dlp specifically, open a command prompt in the app folder once and run:

```bat
.venv\Scripts\python.exe -m pip install -U "yt-dlp[default]"
```

yt-dlp's `default` dependency group includes its matching `yt-dlp-ejs` package. Update Deno separately when yt-dlp requires a newer runtime. See the [yt-dlp EJS guide](https://github.com/yt-dlp/yt-dlp/wiki/EJS).

## Troubleshooting

- **Python missing:** Reinstall Python with its PATH option, or use the Python launcher (`py`).
- **FFmpeg or FFprobe missing:** Both executables must be present in an FFmpeg `bin` directory listed on PATH. The Python `ffmpeg` package is not a substitute.
- **Deno missing or too old:** Install or update Deno, then rerun `setup.bat`.
- **Dependency install fails:** Check Internet access, any corporate proxy rules, and the error shown in the setup window. Rerun `setup.bat`.
- **Browser does not open:** Read the local URL printed by `start.bat` and paste it into your browser.
- **Video fails:** Public availability and format support vary by site. Try updating yt-dlp; review the specific job error. Login-only, DRM, private, blocked, or removed videos are unsupported.
- **Port busy:** The app tries ports 8000–8010. Close the program using those ports and restart.
- **File permission errors:** Move the app folder to a writable location under your user profile.

Only use videos you are allowed to download. The app does not collect cookies or credentials and does not bypass site access restrictions.
