@echo off
:: Quantum Bank Bot Setup Script for Windows
:: This script helps new users set up the development environment using the uv package manager

echo.
echo =======================================
echo   Quantum Bank Bot Setup Script
echo =======================================
echo.

:: Check if Python 3.12+ is installed
python --version 2>NUL
if %ERRORLEVEL% NEQ 0 (
    echo [31mError: Python not found![0m
    echo [33mPlease install Python 3.12+ and try again.[0m
    exit /b 1
)

:: Extract Python version
for /f "tokens=2" %%a in ('python --version 2^>^&1') do set pyver=%%a
for /f "tokens=1,2 delims=." %%a in ("%pyver%") do (
    set pymajor=%%a
    set pyminor=%%b
)

:: Check version meets requirements
if %pymajor% LSS 3 (
    echo [31mError: Python 3.12 or higher is required![0m
    echo [33mPlease install Python 3.12+ and try again.[0m
    exit /b 1
)
if %pymajor% EQU 3 (
    if %pyminor% LSS 12 (
        echo [31mError: Python 3.12 or higher is required![0m
        echo [33mPlease install Python 3.12+ and try again.[0m
        exit /b 1
    )
)

echo [32m✓ Found Python %pymajor%.%pyminor%[0m

:: Check if uv is installed
where uv >NUL 2>NUL
if %ERRORLEVEL% NEQ 0 (
    echo [33mInstalling uv package manager...[0m
    
    :: Download and run the uv installation script
    echo Downloading uv installer...
    powershell -Command "Invoke-WebRequest -UseBasicParsing -Uri 'https://astral.sh/uv/install.ps1' -OutFile '%TEMP%\uv-install.ps1'"
    
    :: Execute the installer
    powershell -ExecutionPolicy Bypass -File "%TEMP%\uv-install.ps1"
    
    :: Check if installation was successful
    where uv >NUL 2>NUL
    if %ERRORLEVEL% NEQ 0 (
        echo [31mFailed to install uv. Please install it manually:[0m
        echo [33mVisit: https://github.com/astral-sh/uv/blob/main/README.md#installation[0m
        exit /b 1
    )
    
    echo [32m✓ uv installed successfully[0m
) else (
    echo [32m✓ uv package manager is already installed[0m
)

:: Create virtual environment if it doesn't exist
if not exist ".venv" (
    echo [33mCreating virtual environment...[0m
    uv venv
) else (
    echo [32m✓ Virtual environment already exists[0m
)

:: Activate virtual environment
echo [33mActivating virtual environment...[0m
call .venv\Scripts\activate.bat
if %ERRORLEVEL% NEQ 0 (
    echo [31mFailed to activate virtual environment[0m
    exit /b 1
)

:: Install dependencies using uv
echo [33mInstalling dependencies...[0m
uv pip install -e "."
echo [32m✓ Successfully installed basic dependencies[0m

:: Ask if development dependencies should be installed
echo.
set /p installDev="Would you like to install development dependencies? (y/n): "

if /i "%installDev%"=="y" (
    echo [33mInstalling development dependencies...[0m
    uv pip install -e ".[development]"
    echo [32m✓ Successfully installed development dependencies[0m
)

echo.
echo [32m=======================================[0m
echo [32m  Setup completed successfully![0m
echo [32m=======================================[0m
echo [33mTo activate the virtual environment, run:[0m
echo     .venv\Scripts\activate.bat
echo [33mTo start the bot, run:[0m
echo     python launcher.py
echo.

:: Keep the window open
pause 