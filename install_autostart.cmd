@echo off
rem Start the Right Alt dictation program automatically when you log in.
rem Puts a one-line launcher in the Startup folder that calls this folder's
rem start_sensevoice.cmd (so moving the project means running this again).
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
if exist "%STARTUP%\start_codex_voice.cmd" del "%STARTUP%\start_codex_voice.cmd"
(echo @call "%~dp0start_sensevoice.cmd") > "%STARTUP%\start_sensevoice.cmd"
if errorlevel 1 (
  echo Failed to install autostart.
) else (
  echo Autostart installed. To remove it, run uninstall_autostart.cmd
)
pause
