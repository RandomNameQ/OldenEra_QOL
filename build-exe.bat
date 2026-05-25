@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_CMD=py -3"
%PYTHON_CMD% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if errorlevel 1 (
  set "PYTHON_CMD=python"
  python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
  if errorlevel 1 goto python_error
)

if not exist ".venv\Scripts\python.exe" (
  %PYTHON_CMD% -m venv .venv
  if errorlevel 1 goto error
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 goto error

python -m pip install --upgrade pip
if errorlevel 1 goto error

python -m pip install --no-input --progress-bar off -e ".[dev]"
if errorlevel 1 goto error

python -m PyInstaller --clean --noconfirm oldenera_qol.spec
if errorlevel 1 goto error

echo.
echo Built dist\OldenEraQOL\OldenEraQOL.exe
exit /b 0

:error
echo.
echo OldenEra QOL build failed. See the error above.
pause
exit /b 1

:python_error
echo.
echo OldenEra QOL needs Python 3.11 or newer. Install Python, or make sure py/python points to Python 3.11+.
pause
exit /b 1
