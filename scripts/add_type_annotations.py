#!/usr/bin/env python
"""
Type Annotation Helper Script

This script helps add type annotations to Python files in the codebase.
It scans for functions without return type annotations and suggests appropriate types.

Usage:
    python scripts/add_type_annotations.py [file_or_directory]
"""

import ast
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Set


class FunctionVisitor(ast.NodeVisitor):
    """Visit functions and methods to detect missing type annotations."""
    
    def __init__(self):
        self.functions_without_returns = []
        self.functions_without_arg_types = []
        
    def visit_FunctionDef(self, node):
        self._check_function(node)
        self.generic_visit(node)
        
    def visit_AsyncFunctionDef(self, node):
        self._check_function(node)
        self.generic_visit(node)
        
    def _check_function(self, node):
        # Check if function has a return type annotation
        if node.returns is None:
            self.functions_without_returns.append(node)
            
        # Check if all arguments have type annotations
        for arg in node.args.args + node.args.kwonlyargs:
            if arg.annotation is None and arg.arg != 'self' and arg.arg != 'cls':
                self.functions_without_arg_types.append((node, arg))


def guess_return_type(node) -> str:
    """Try to guess the return type of a function based on its content and name."""
    # Check for common naming patterns
    name = node.name.lower()
    
    # Async functions that don't explicitly return anything likely return None
    if isinstance(node, ast.AsyncFunctionDef):
        for n in ast.walk(node):
            if isinstance(n, ast.Return) and n.value is not None:
                # If it has at least one return with a value, it's not None
                break
        else:
            # No returns with values found
            if name.startswith(('get_', 'fetch_', 'load_', 'read_')):
                return 'Any | None'
            else:
                return 'None'
    
    # Common patterns based on function name prefixes
    if name.startswith(('is_', 'has_', 'should_', 'can_', 'check_')):
        return 'bool'
    elif name.startswith(('get_', 'fetch_', 'load_', 'read_')):
        if 'list' in name or name.endswith('s'):
            return 'list[Any]'
        elif 'dict' in name or 'map' in name:
            return 'dict[str, Any]'
        else:
            return 'Any'
    elif name.startswith('count_'):
        return 'int'
    elif name == '__init__' or name == '__post_init__':
        return 'None'
        
    # Default
    return 'Any'


def guess_arg_type(arg_name: str) -> str:
    """Try to guess argument type based on its name."""
    name = arg_name.lower()
    
    # Common parameter naming patterns
    if name in ('id', 'user_id', 'guild_id', 'channel_id', 'message_id') or name.endswith('_id'):
        return 'str'
    elif name == 'ctx' or name == 'context':
        return 'commands.Context'
    elif name == 'interaction':
        return 'discord.Interaction'
    elif name == 'bot':
        return 'commands.Bot'
    elif name in ('limit', 'count', 'size', 'length', 'index', 'position', 'offset'):
        return 'int'
    elif name in ('enabled', 'disabled', 'visible', 'active', 'force'):
        return 'bool'
    elif name in ('name', 'title', 'description', 'message', 'content', 'text', 'reason'):
        return 'str'
    elif name == 'amount':
        return 'float'
    elif name == 'user':
        return 'discord.User'
    elif name == 'member':
        return 'discord.Member'
    elif name == 'guild':
        return 'discord.Guild'
    elif name == 'channel':
        return 'discord.TextChannel'
    elif name in ('args',):
        return 'tuple'
    elif name in ('kwargs',):
        return 'dict'
    
    # Default
    return 'Any'


def scan_file(file_path: Path) -> Tuple[List[Dict], List[Dict]]:
    """Scan a Python file for missing type annotations."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    try:
        tree = ast.parse(content)
    except SyntaxError as e:
        print(f"Error parsing {file_path}: {e}")
        return [], []
    
    visitor = FunctionVisitor()
    visitor.visit(tree)
    
    functions_without_returns = []
    functions_without_arg_types = []
    
    # Process functions without return types
    for node in visitor.functions_without_returns:
        functions_without_returns.append({
            'name': node.name,
            'line': node.lineno,
            'suggested_type': guess_return_type(node)
        })
    
    # Process functions with missing argument types
    for node, arg in visitor.functions_without_arg_types:
        functions_without_arg_types.append({
            'function': node.name,
            'line': node.lineno,
            'arg': arg.arg,
            'suggested_type': guess_arg_type(arg.arg)
        })
    
    return functions_without_returns, functions_without_arg_types


def scan_directory(directory: Path, exclude_dirs: Set[str] = None) -> Tuple[Dict, Dict]:
    """Scan a directory recursively for Python files with missing type annotations."""
    if exclude_dirs is None:
        exclude_dirs = {'.git', '.venv', '__pycache__', '.pytest_cache', '.ruff_cache'}
    
    all_functions_without_returns = {}
    all_functions_without_arg_types = {}
    
    for root, dirs, files in os.walk(directory):
        # Skip excluded directories
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        
        for file in files:
            if file.endswith('.py'):
                file_path = Path(root) / file
                rel_path = file_path.relative_to(directory)
                
                functions_without_returns, functions_without_arg_types = scan_file(file_path)
                
                if functions_without_returns:
                    all_functions_without_returns[str(rel_path)] = functions_without_returns
                
                if functions_without_arg_types:
                    all_functions_without_arg_types[str(rel_path)] = functions_without_arg_types
    
    return all_functions_without_returns, all_functions_without_arg_types


def print_report(functions_without_returns: Dict, functions_without_arg_types: Dict):
    """Print a report of missing type annotations."""
    total_return_issues = sum(len(issues) for issues in functions_without_returns.values())
    total_arg_issues = sum(len(issues) for issues in functions_without_arg_types.values())
    
    print(f"\n=== Missing Type Annotations Report ===")
    print(f"Found {total_return_issues} missing return type annotations")
    print(f"Found {total_arg_issues} missing argument type annotations")
    print(f"Total issues: {total_return_issues + total_arg_issues}")
    
    if functions_without_returns:
        print("\n=== Functions Missing Return Type Annotations ===")
        for file, issues in functions_without_returns.items():
            print(f"\n{file}:")
            for issue in issues:
                print(f"  Line {issue['line']}: {issue['name']}() -> {issue['suggested_type']}")
    
    if functions_without_arg_types:
        print("\n=== Functions Missing Argument Type Annotations ===")
        for file, issues in functions_without_arg_types.items():
            print(f"\n{file}:")
            for issue in issues:
                print(f"  Line {issue['line']}: {issue['function']}() arg '{issue['arg']}': {issue['suggested_type']}")


def generate_fix_file(functions_without_returns: Dict, functions_without_arg_types: Dict, output_path: Path):
    """Generate a file with fix suggestions."""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("# Type Annotation Fix Suggestions\n\n")
        
        if functions_without_returns:
            f.write("## Missing Return Type Annotations\n\n")
            for file, issues in functions_without_returns.items():
                f.write(f"### {file}\n\n")
                f.write("```python\n")
                for issue in issues:
                    f.write(f"# Line {issue['line']}\n")
                    f.write(f"def {issue['name']}(...) -> {issue['suggested_type']}:\n\n")
                f.write("```\n\n")
        
        if functions_without_arg_types:
            f.write("## Missing Argument Type Annotations\n\n")
            for file, issues in functions_without_arg_types.items():
                f.write(f"### {file}\n\n")
                f.write("```python\n")
                
                # Group by function to avoid repeating the same function
                by_function = {}
                for issue in issues:
                    func = issue['function']
                    if func not in by_function:
                        by_function[func] = []
                    by_function[func].append({
                        'line': issue['line'],
                        'arg': issue['arg'],
                        'suggested_type': issue['suggested_type']
                    })
                
                for func, args in by_function.items():
                    f.write(f"# Line {args[0]['line']}\n")
                    args_str = ", ".join([f"{arg['arg']}: {arg['suggested_type']}" for arg in args])
                    f.write(f"def {func}({args_str}, ...):\n\n")
                
                f.write("```\n\n")


def main():
    """Main entry point for the script."""
    if len(sys.argv) < 2:
        print("Usage: python add_type_annotations.py [file_or_directory]")
        sys.exit(1)
    
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"Error: {path} does not exist")
        sys.exit(1)
    
    output_path = Path('type_annotation_fixes.md')
    
    if path.is_file():
        if not path.name.endswith('.py'):
            print(f"Error: {path} is not a Python file")
            sys.exit(1)
        
        functions_without_returns, functions_without_arg_types = scan_file(path)
        functions_without_returns = {str(path): functions_without_returns}
        functions_without_arg_types = {str(path): functions_without_arg_types}
    else:
        functions_without_returns, functions_without_arg_types = scan_directory(path)
    
    print_report(functions_without_returns, functions_without_arg_types)
    generate_fix_file(functions_without_returns, functions_without_arg_types, output_path)
    
    print(f"\nDetailed fix suggestions written to {output_path}")


if __name__ == "__main__":
    main() 