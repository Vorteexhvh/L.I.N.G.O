@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Instale as dependencias conforme README.md antes de iniciar.
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "main.py"
