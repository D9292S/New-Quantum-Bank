#!/usr/bin/env python3
"""
UV Tool - Helper script for uv package management operations
-----------------------------------------------------------
This script provides simplified commands for common uv operations:
- update: Update all dependencies to their latest compatible versions
- clean: Clean the environment and rebuild from scratch
- sync: Sync the environment with the lock file
- add: Add a new package to the project
- remove: Remove a package from the project
- list: List all installed packages
- check: Check for outdated packages
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def run_command(cmd, check=True, capture=False):
    """Run a command and return the result."""
    print(f"Running: {' '.join(cmd)}")
    if capture:
        return subprocess.run(cmd, check=check, capture_output=True, text=True)
    else:
        return subprocess.run(cmd, check=check)


def ensure_uv_installed():
    """Make sure uv is installed and accessible."""
    try:
        run_command(["uv", "--version"], capture=True)
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        print("Error: uv is not installed or not in PATH.")
        print("Please run the setup script first.")
        return False


def update_dependencies(args):
    """Update all dependencies to their latest compatible versions."""
    if not ensure_uv_installed():
        return False
    
    print("Updating dependencies to latest compatible versions...")
    
    # Update based on constraints in pyproject.toml
    if args.all:
        print("Updating all dependencies including major versions...")
        result = run_command(["uv", "pip", "compile", "pyproject.toml", "--upgrade-package", "*", "--output-file", "requirements.txt"], check=False)
    else:
        result = run_command(["uv", "pip", "compile", "pyproject.toml", "--upgrade", "--output-file", "requirements.txt"], check=False)
    
    if result.returncode != 0:
        print("Error updating dependencies. Reverting to previous state.")
        return False
    
    # Install from the updated requirements
    print("Installing updated dependencies...")
    run_command(["uv", "pip", "install", "-e", "."])
    
    # Update the lockfile
    print("Updating lock file...")
    run_command(["uv", "pip", "sync", "pyproject.toml"])
    
    print("Dependencies successfully updated!")
    return True


def clean_environment(args):
    """Clean the environment and rebuild from scratch."""
    if not ensure_uv_installed():
        return False
    
    venv_path = Path(".venv")
    
    # Ask for confirmation if not --force
    if not args.force and venv_path.exists():
        response = input("This will delete your virtual environment. Continue? (y/n): ")
        if response.lower() != "y":
            print("Operation cancelled.")
            return False
    
    # Remove virtual environment
    if venv_path.exists():
        print("Removing virtual environment...")
        import shutil
        shutil.rmtree(venv_path)
    
    # Create new environment
    print("Creating new virtual environment...")
    run_command(["uv", "venv"])
    
    # Install dependencies
    print("Installing dependencies...")
    run_command(["uv", "pip", "install", "-e", "."])
    
    if args.dev:
        print("Installing development dependencies...")
        run_command(["uv", "pip", "install", "-e", ".[development]"])
    
    print("Environment successfully rebuilt!")
    return True


def sync_environment(args):
    """Sync the environment with the lock file or pyproject.toml."""
    if not ensure_uv_installed():
        return False
    
    if Path("uv.lock").exists() and not args.no_lock:
        print("Syncing environment from lock file...")
        run_command(["uv", "pip", "sync"])
    else:
        print("Syncing environment from pyproject.toml...")
        run_command(["uv", "pip", "sync", "pyproject.toml"])
    
    print("Environment successfully synced!")
    return True


def add_package(args):
    """Add a package to the project."""
    if not ensure_uv_installed():
        return False
    
    package_specs = args.packages
    if not package_specs:
        print("Error: No packages specified.")
        return False
    
    # Build command with all options
    cmd = ["uv", "pip", "install"]
    
    # Add development flag if specified
    if args.dev:
        cmd.append("--dev")
    
    # Add all packages
    cmd.extend(package_specs)
    
    # Run the install command
    print(f"Adding package(s): {', '.join(package_specs)}")
    result = run_command(cmd, check=False)
    if result.returncode != 0:
        print("Error adding package(s).")
        return False
    
    # Update the lock file
    print("Updating lock file...")
    run_command(["uv", "pip", "sync", "pyproject.toml"])
    
    print("Package(s) successfully added!")
    return True


def remove_package(args):
    """Remove a package from the project."""
    if not ensure_uv_installed():
        return False
    
    package_names = args.packages
    if not package_names:
        print("Error: No packages specified.")
        return False
    
    # Build command with all options
    cmd = ["uv", "pip", "uninstall"]
    
    # Add all packages
    cmd.extend(package_names)
    
    # Always confirm
    cmd.append("-y")
    
    # Run the uninstall command
    print(f"Removing package(s): {', '.join(package_names)}")
    result = run_command(cmd, check=False)
    if result.returncode != 0:
        print("Error removing package(s).")
        return False
    
    # Update the lock file
    print("Updating lock file...")
    run_command(["uv", "pip", "sync", "pyproject.toml"])
    
    print("Package(s) successfully removed!")
    return True


def list_packages(args):
    """List all installed packages."""
    if not ensure_uv_installed():
        return False
    
    print("Installed packages:")
    if args.outdated:
        run_command(["uv", "pip", "list", "--outdated"])
    else:
        run_command(["uv", "pip", "list"])
    
    return True


def check_packages(args):
    """Check for potential issues with installed packages."""
    if not ensure_uv_installed():
        return False
    
    print("Checking for outdated packages:")
    run_command(["uv", "pip", "list", "--outdated"])
    
    # Check for specific Python 3.12 compatibility issues
    known_issues = {
        "tensorflow": "Tensorflow compatibility with Python 3.12 is limited. Check the official docs.",
        "pandas<2.0.0": "Older Pandas versions may have issues with Python 3.12.",
        "numpy<1.26.0": "Older NumPy versions may have issues with Python 3.12.",
    }
    
    # Get list of installed packages
    result = run_command(["uv", "pip", "list", "--format=freeze"], capture=True)
    installed = result.stdout.splitlines()
    
    found_issues = False
    print("\nChecking for packages with known Python 3.12 compatibility issues:")
    for package_line in installed:
        package_name = package_line.split("==")[0] if "==" in package_line else package_line
        for issue_pkg, issue_desc in known_issues.items():
            if issue_pkg == package_name or (issue_pkg.endswith(">") and package_name in issue_pkg):
                print(f"⚠️  {package_name}: {issue_desc}")
                found_issues = True
    
    if not found_issues:
        print("No known compatibility issues found!")
    
    return True


def setup_argparse():
    """Set up argument parsing."""
    parser = argparse.ArgumentParser(
        description="UV Tool - Helper for uv package management operations"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # update command
    update_parser = subparsers.add_parser("update", help="Update dependencies")
    update_parser.add_argument("--all", action="store_true", help="Update all dependencies, ignoring version constraints")
    
    # clean command
    clean_parser = subparsers.add_parser("clean", help="Clean environment")
    clean_parser.add_argument("--force", "-f", action="store_true", help="Don't ask for confirmation")
    clean_parser.add_argument("--dev", "-d", action="store_true", help="Install development dependencies")
    
    # sync command
    sync_parser = subparsers.add_parser("sync", help="Sync environment")
    sync_parser.add_argument("--no-lock", action="store_true", help="Don't use lock file even if present")
    
    # add command
    add_parser = subparsers.add_parser("add", help="Add packages")
    add_parser.add_argument("packages", nargs="+", help="Packages to add")
    add_parser.add_argument("--dev", "-d", action="store_true", help="Add as development dependency")
    
    # remove command
    remove_parser = subparsers.add_parser("remove", help="Remove packages")
    remove_parser.add_argument("packages", nargs="+", help="Packages to remove")
    
    # list command
    list_parser = subparsers.add_parser("list", help="List packages")
    list_parser.add_argument("--outdated", "-o", action="store_true", help="Show only outdated packages")
    
    # check command
    check_parser = subparsers.add_parser("check", help="Check packages")
    
    return parser


def main():
    """Main entry point."""
    parser = setup_argparse()
    args = parser.parse_args()
    
    # Create mapping of commands to functions
    commands = {
        "update": update_dependencies,
        "clean": clean_environment,
        "sync": sync_environment,
        "add": add_package,
        "remove": remove_package,
        "list": list_packages,
        "check": check_packages,
    }
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Run the appropriate command
    success = commands[args.command](args)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main()) 