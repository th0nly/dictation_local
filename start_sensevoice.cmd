@echo off
rem Start the Right Alt dictation program in the background.
rem Uses this project's .venv (has sherpa-onnx + sounddevice installed).
if not exist "%~dp0.venv\Scripts\pythonw.exe" (
  echo .venv not found. Run "python setup.py" in this folder first.
  pause
  exit /b 1
)
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0sensevoice_hotkey.py"
