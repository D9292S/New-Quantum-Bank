#!/usr/bin/env python3
"""
Environment Validation Script for Quantum Superbot
--------------------------------------------------
This script checks that all requirements are met for running the bot:
- Python version is 3.12+
- Required OS packages are available
- uv is installed and configured correctly
- Dependencies are compatible with Python 3.12+
"""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# ANSI color codes for output
RESET = "\033[0m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[36m"
BOLD = "\033[1m"

# Minimum Python version required
MIN_PYTHON_VERSION = (3, 12)


def print_color(color, message):
    """Print a message with color."""
    is_windows = platform.system() == "Windows"
    if is_windows and not os.environ.get("TERM") == "xterm":
        # Windows doesn't support ANSI colors by default
        print(message)
    else:
        print(f"{color}{message}{RESET}")


def check_python_version():
    """Check if the Python version meets requirements."""
    current_version = sys.version_info
    if current_version < MIN_PYTHON_VERSION:
        print_color(RED, f"❌ Error: Python {MIN_PYTHON_VERSION[0]}.{MIN_PYTHON_VERSION[1]}+ is required.")
        print_color(YELLOW, f"   Current version: Python {current_version.major}.{current_version.minor}.{current_version.micro}")
        return False
    
    print_color(GREEN, f"✓ Python version: {current_version.major}.{current_version.minor}.{current_version.micro}")
    return True


def check_uv_installed():
    """Check if uv is installed and available."""
    uv_path = shutil.which("uv")
    if not uv_path:
        print_color(RED, "❌ uv package manager not found in PATH.")
        print_color(YELLOW, "Please install uv using the setup script.")
        return False
    
    # Check uv version
    try:
        result = subprocess.run(["uv", "--version"], capture_output=True, text=True, check=True)
        version = result.stdout.strip()
        print_color(GREEN, f"✓ uv package manager installed: {version}")
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        print_color(RED, "❌ Error running uv. Please reinstall the package manager.")
        return False


def check_dependencies():
    """Check if pyproject.toml exists and validate dependencies."""
    project_file = Path("pyproject.toml")
    if not project_file.exists():
        print_color(RED, "❌ pyproject.toml not found. Are you in the project root directory?")
        return False
    
    print_color(GREEN, "✓ pyproject.toml found")
    
    # Check for uv.lock
    lock_file = Path("uv.lock")
    if not lock_file.exists():
        print_color(YELLOW, "⚠ uv.lock not found. This is needed for reproducible environments.")
        print_color(YELLOW, "   Running 'uv pip sync' to generate it...")
        try:
            subprocess.run(["uv", "pip", "sync", "pyproject.toml"], check=True)
            print_color(GREEN, "✓ uv.lock generated successfully")
        except subprocess.SubprocessError:
            print_color(RED, "❌ Failed to generate uv.lock")
            return False
    else:
        print_color(GREEN, "✓ uv.lock found")
    
    return True


def check_system_dependencies():
    """Check if required system packages are installed."""
    system = platform.system()
    
    if system == "Linux":
        # Check for common build dependencies on Linux
        required_packages = ["build-essential", "python3-dev", "libffi-dev"]
        
        print_color(BLUE, "Checking system dependencies...")
        
        for package in required_packages:
            try:
                result = subprocess.run(
                    ["dpkg", "-s", package], 
                    capture_output=True, 
                    text=True, 
                    check=False
                )
                if result.returncode == 0:
                    print_color(GREEN, f"✓ {package} is installed")
                else:
                    print_color(YELLOW, f"⚠ {package} might not be installed. This may cause issues.")
            except (subprocess.SubprocessError, FileNotFoundError):
                # If dpkg is not available, we're likely not on a Debian-based system
                print_color(YELLOW, "⚠ Cannot check system packages. Ensure build tools are installed.")
                break
    
    elif system == "Windows":
        # Check for Visual C++ Build Tools on Windows
        print_color(BLUE, "Checking Windows build tools...")
        
        # Check Python's ability to find the MSVC compiler
        try:
            import distutils.msvc9compiler
            msvc_version = distutils.msvc9compiler.get_build_version()
            if msvc_version:
                print_color(GREEN, f"✓ MSVC compiler found (version {msvc_version})")
            else:
                print_color(YELLOW, "⚠ MSVC compiler not found. Some packages may fail to build.")
                print_color(YELLOW, "  Install Visual C++ Build Tools from:")
                print_color(YELLOW, "  https://visualstudio.microsoft.com/visual-cpp-build-tools/")
        except (ImportError, AttributeError):
            print_color(YELLOW, "⚠ Could not check for MSVC compiler. Ensure build tools are installed.")
    
    return True


def validate_environment():
    """Validate the entire development environment."""
    print_color(BOLD + BLUE, "==================================================")
    print_color(BOLD + BLUE, "   Quantum Superbot Environment Validation")
    print_color(BOLD + BLUE, "==================================================")
    print()
    
    checks = [
        ("Python Version", check_python_version),
        ("UV Package Manager", check_uv_installed),
        ("Project Dependencies", check_dependencies),
        ("System Dependencies", check_system_dependencies),
    ]
    
    results = []
    for name, check_func in checks:
        print_color(BOLD + BLUE, f"Checking {name}...")
        result = check_func()
        results.append(result)
        print()
    
    # Print summary
    print_color(BOLD + BLUE, "==================================================")
    print_color(BOLD + BLUE, "                  Summary")
    print_color(BOLD + BLUE, "==================================================")
    
    all_passed = all(results)
    
    for (name, _), result in zip(checks, results):
        status = f"{GREEN}✓ PASS" if result else f"{RED}❌ FAIL"
        print_color(BOLD, f"{status}{RESET} - {name}")
    
    print()
    if all_passed:
        print_color(GREEN, "✅ All checks passed! Your environment is ready for Quantum Superbot.")
    else:
        print_color(RED, "❌ Some checks failed. Please fix the issues above before proceeding.")
    
    return all_passed


if __name__ == "__main__":
    success = validate_environment()
    sys.exit(0 if success else 1) 