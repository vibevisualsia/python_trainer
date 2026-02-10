@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv312\Scripts\python.exe" (
  echo No existe .venv312. Crea el entorno con:
  echo py -3.12 -m venv .venv312
  echo .venv312\Scripts\python -m pip install -r requirements-dev.txt
  pause
  exit /b 1
)

".venv312\Scripts\python.exe" -m ui.vscode_app

endlocal
