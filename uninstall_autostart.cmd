@echo off
rem Stop starting the Right Alt dictation program automatically at login.
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "FOUND="
for %%f in (start_sensevoice.cmd start_codex_voice.cmd) do (
  if exist "%STARTUP%\%%f" (
    del "%STARTUP%\%%f"
    set "FOUND=1"
  )
)
if defined FOUND (echo Autostart removed.) else (echo Autostart was not installed.)
pause
