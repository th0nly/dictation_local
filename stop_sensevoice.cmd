@echo off
rem Stop the Right Alt dictation program (only this program's pythonw processes).
powershell -NoProfile -Command "$p = Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | Where-Object { $_.CommandLine -match 'sensevoice_hotkey|codex_voice' }; if ($p) { $p | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }; 'Stopped.' } else { 'Not running.' }"
timeout /t 2 >nul
