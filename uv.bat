@echo off
:: UV Tool - Easy access to uvtool.py
:: This passes all arguments to uvtool.py

:: Find Python executable
for /f "tokens=*" %%i in ('where python 2^>nul') do set PYTHON_EXE=%%i

if "%PYTHON_EXE%"=="" (
    echo Python not found in PATH
    exit /b 1
)

:: Activate virtual environment if it exists but isn't activated
if exist .venv\Scripts\activate.bat (
    if not defined VIRTUAL_ENV (
        call .venv\Scripts\activate.bat
    )
)

:: Run uvtool with all arguments
"%PYTHON_EXE%" scripts\uvtool.py %* 