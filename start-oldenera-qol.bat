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
python -m pip install --no-input --progress-bar off "PySide6>=6.7" "opencv-python>=4.9" "mss>=9.0" "pytesseract>=0.3.10" "Pillow>=10.0" "pynput>=1.7" "pywin32>=306" "pydirectinput>=1.0"
if errorlevel 1 goto error

set "PYTHONPATH=%CD%\src;%PYTHONPATH%"
python -m oldenera_qol
if errorlevel 1 goto error

exit /b 0

:error
echo.
echo OldenEra QOL failed to start. See the error above.
pause
exit /b 1

:python_error
echo.
echo OldenEra QOL needs Python 3.11 or newer. Install Python, or make sure py/python points to Python 3.11+.
pause
exit /b 1
