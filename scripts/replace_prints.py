#!/usr/bin/env python
"""
Print to Logging Converter Script

This script helps replace print statements with proper logging calls.
It scans for print statements and suggests appropriate logging replacements.

Usage:
    python scripts/replace_prints.py [file_or_directory]
"""

import ast
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any


class PrintVisitor(ast.NodeVisitor):
    """Visit print statements to detect and catalog them."""
    
    def __init__(self):
        self.prints = []
        
    def visit_Call(self, node):
        if isinstance(node.func, ast.Name) and node.func.id == 'print':
            self.prints.append(node)
        self.generic_visit(node)


def determine_logging_level(text: str) -> str:
    """
    Determine the appropriate logging level based on the print content.
    
    Args:
        text: The text being printed
        
    Returns:
        The suggested logging level
    """
    # Convert to lowercase for easier pattern matching
    lower_text = text.lower()
    
    # Error-related keywords
    if any(kw in lower_text for kw in ['error', 'exception', 'fail', 'failed', 'critical']):
        return 'error'
    
    # Warning-related keywords
    if any(kw in lower_text for kw in ['warning', 'warn', 'caution', 'deprecated']):
        return 'warning'
    
    # Debug-related keywords
    if any(kw in lower_text for kw in ['debug', 'trace', 'verbose']):
        return 'debug'
    
    # Success or completion keywords
    if any(kw in lower_text for kw in ['success', 'completed', 'finished']):
        return 'info'
    
    # Default to info
    return 'info'


def extract_string_value(node) -> Tuple[str, bool]:
    """
    Extract the string value from a node.
    
    Args:
        node: The AST node to extract from
        
    Returns:
        Tuple of (extracted string value, is_simple_string)
        is_simple_string is True if the node was a simple string literal
    """
    if isinstance(node, ast.Str):
        return node.s, True
    elif isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value, True
    elif isinstance(node, ast.JoinedStr):
        # Handle f-strings
        parts = []
        for value in node.values:
            if isinstance(value, ast.Str) or (isinstance(value, ast.Constant) and isinstance(value.value, str)):
                value_str = value.s if hasattr(value, 's') else value.value
                parts.append(value_str)
            elif isinstance(value, ast.FormattedValue):
                parts.append("{}")
        return "".join(parts), False
    return "<complex-expression>", False


def generate_logging_suggestion(print_node, in_class: bool) -> Dict[str, Any]:
    """
    Generate a logging suggestion for a print statement.
    
    Args:
        print_node: The AST node for the print statement
        in_class: Whether the print is inside a class
        
    Returns:
        Dictionary with logging suggestion details
    """
    args_strings = []
    args_values = []
    has_complex_args = False
    
    for arg in print_node.args:
        arg_str, is_simple = extract_string_value(arg)
        args_strings.append(arg_str)
        args_values.append(arg)
        if not is_simple:
            has_complex_args = True
    
    combined_text = " ".join(args_strings)
    level = determine_logging_level(combined_text)
    
    # Determine the appropriate logging call
    if in_class:
        if has_complex_args and len(print_node.args) > 0:
            # For complex f-strings, preserve the formatting
            if len(print_node.args) == 1 and isinstance(print_node.args[0], ast.JoinedStr):
                # Create a suggestion that preserves the f-string
                return {
                    'level': level,
                    'text': combined_text,
                    'in_class': True,
                    'is_complex': True,
                    'original_node': print_node,
                    'suggestion': f'self.logger.{level}(f"{combined_text}")'
                }
            else:
                # Multiple arguments or complex expressions
                return {
                    'level': level,
                    'text': combined_text,
                    'in_class': True,
                    'is_complex': True,
                    'original_node': print_node,
                    'suggestion': f'self.logger.{level}(<original-expression>)'
                }
        else:
            # Simple string
            return {
                'level': level,
                'text': combined_text,
                'in_class': True,
                'is_complex': False,
                'original_node': print_node,
                'suggestion': f'self.logger.{level}("{combined_text}")'
            }
    else:
        # Same logic for global scope, but using the logging module
        if has_complex_args and len(print_node.args) > 0:
            if len(print_node.args) == 1 and isinstance(print_node.args[0], ast.JoinedStr):
                return {
                    'level': level,
                    'text': combined_text,
                    'in_class': False,
                    'is_complex': True,
                    'original_node': print_node,
                    'suggestion': f'logger.{level}(f"{combined_text}")'
                }
            else:
                return {
                    'level': level,
                    'text': combined_text,
                    'in_class': False, 
                    'is_complex': True,
                    'original_node': print_node,
                    'suggestion': f'logger.{level}(<original-expression>)'
                }
        else:
            return {
                'level': level,
                'text': combined_text,
                'in_class': False,
                'is_complex': False,
                'original_node': print_node,
                'suggestion': f'logger.{level}("{combined_text}")'
            }


def find_print_statements(file_path: Path) -> List[Dict[str, Any]]:
    """
    Find print statements in a Python file.
    
    Args:
        file_path: Path to the Python file
        
    Returns:
        List of print statements with metadata
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    try:
        tree = ast.parse(content)
    except SyntaxError as e:
        print(f"Error parsing {file_path}: {e}")
        return []
    
    # Find all classes
    class_ranges = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            class_ranges[node.name] = (node.lineno, node.end_lineno)
    
    # Find print statements
    visitor = PrintVisitor()
    visitor.visit(tree)
    
    results = []
    for print_node in visitor.prints:
        # Check if print is in a class
        in_class = any(
            start <= print_node.lineno <= end
            for _, (start, end) in class_ranges.items()
        )
        
        suggestion = generate_logging_suggestion(print_node, in_class)
        suggestion['line'] = print_node.lineno
        results.append(suggestion)
    
    return results


def scan_directory(directory: Path, exclude_dirs: Set[str] = None) -> Dict[str, List[Dict[str, Any]]]:
    """
    Scan a directory recursively for Python files with print statements.
    
    Args:
        directory: Directory to scan
        exclude_dirs: Directories to exclude
        
    Returns:
        Dictionary mapping file paths to lists of print statement metadata
    """
    if exclude_dirs is None:
        exclude_dirs = {'.git', '.venv', '__pycache__', '.pytest_cache', '.ruff_cache'}
    
    all_prints = {}
    
    for root, dirs, files in os.walk(directory):
        # Skip excluded directories
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        
        for file in files:
            if file.endswith('.py'):
                file_path = Path(root) / file
                rel_path = file_path.relative_to(directory)
                
                prints = find_print_statements(file_path)
                
                if prints:
                    all_prints[str(rel_path)] = prints
    
    return all_prints


def generate_replacement_file(all_prints: Dict[str, List[Dict[str, Any]]], output_path: Path):
    """
    Generate a file with suggested replacements for print statements.
    
    Args:
        all_prints: Dictionary mapping file paths to lists of print statement metadata
        output_path: Path to save the output file
    """
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("# Print to Logging Replacement Suggestions\n\n")
        
        for file_path, prints in all_prints.items():
            f.write(f"## {file_path}\n\n")
            
            for print_info in prints:
                f.write(f"### Line {print_info['line']}\n\n")
                f.write("Original:\n")
                f.write("```python\n")
                
                # For simplicity, extract just the line from the source code
                with open(Path(file_path), 'r', encoding='utf-8') as src:
                    lines = src.readlines()
                    line_idx = print_info['line'] - 1
                    if 0 <= line_idx < len(lines):
                        f.write(lines[line_idx])
                    else:
                        f.write(f"print(...) # line {print_info['line']}\n")
                
                f.write("```\n\n")
                f.write("Replace with:\n")
                f.write("```python\n")
                f.write(f"{print_info['suggestion']}\n")
                f.write("```\n\n")
                
                if not print_info['in_class']:
                    f.write("Note: Make sure to add `import logging` and `logger = logging.getLogger(__name__)` at the top of the file if not already present.\n\n")
                
                f.write("---\n\n")


def generate_automatic_replacement_script(all_prints: Dict[str, List[Dict[str, Any]]], output_path: Path):
    """
    Generate a Python script that can automatically apply the replacements.
    
    Args:
        all_prints: Dictionary mapping file paths to lists of print statement metadata
        output_path: Path to save the output script
    """
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("#!/usr/bin/env python\n")
        f.write('"""\n')
        f.write("Automatic Print to Logging Replacement Script\n")
        f.write("\n")
        f.write("This script was generated to automatically replace print statements with proper logging.\n")
        f.write('"""\n\n')
        
        f.write("import re\n")
        f.write("from pathlib import Path\n\n")
        
        f.write("def apply_replacements():\n")
        f.write("    print('Applying print to logging replacements...')\n")
        
        for file_path, prints in all_prints.items():
            # Skip files explicitly excluded from print checking
            if "launcher.py" in file_path or "cluster.py" in file_path or "temp_mongo_test.py" in file_path:
                continue
                
            f.write(f"\n    # Replacements for {file_path}\n")
            f.write(f"    path = Path('{file_path}')\n")
            f.write("    if path.exists():\n")
            f.write("        with open(path, 'r', encoding='utf-8') as file:\n")
            f.write("            content = file.read()\n")
            
            # Check if we need to add import
            needs_import = any(not p['in_class'] for p in prints)
            if needs_import:
                f.write("\n        # Check if logging import is needed\n")
                f.write("        if 'import logging' not in content:\n")
                f.write("            content = 'import logging\\nlogger = logging.getLogger(__name__)\\n\\n' + content\n")
            
            f.write("\n        # Apply replacements\n")
            for print_info in prints:
                line = print_info['line']
                level = print_info['level']
                in_class = print_info['in_class']
                
                # Create a pattern to match the specific print statement
                f.write(f"        # Replace print on line {line}\n")
                f.write(f"        lines = content.split('\\n')\n")
                f.write(f"        if {line-1} < len(lines):\n")
                f.write(f"            line_content = lines[{line-1}]\n")
                f.write(f"            indentation = re.match(r'^\\s*', line_content).group(0)\n")
                
                if in_class:
                    f.write(f"            replacement = f'{{indentation}}self.logger.{level}(')\n")
                else:
                    f.write(f"            replacement = f'{{indentation}}logger.{level}(')\n")
                
                # Replace the print with logger
                f.write(f"            lines[{line-1}] = line_content.replace('print(', replacement, 1)\n")
                f.write(f"            content = '\\n'.join(lines)\n\n")
            
            f.write("        # Write changes back to file\n")
            f.write("        with open(path, 'w', encoding='utf-8') as file:\n")
            f.write("            file.write(content)\n")
            f.write(f"        print(f'Updated {file_path}')\n")
        
        f.write("\n    print('Replacements complete!')\n\n")
        f.write("if __name__ == '__main__':\n")
        f.write("    apply_replacements()\n")


def print_report(all_prints: Dict[str, List[Dict[str, Any]]]):
    """
    Print a summary report of print statements found.
    
    Args:
        all_prints: Dictionary mapping file paths to lists of print statement metadata
    """
    total_prints = sum(len(prints) for prints in all_prints.values())
    
    print(f"\n=== Print to Logging Conversion Report ===")
    print(f"Found {total_prints} print statements in {len(all_prints)} files")
    
    # Count by level
    levels = {'info': 0, 'warning': 0, 'error': 0, 'debug': 0}
    for file_path, prints in all_prints.items():
        for print_info in prints:
            levels[print_info['level']] += 1
    
    print("\nSuggested logging levels:")
    for level, count in levels.items():
        print(f"  {level}: {count}")
    
    print("\nFiles with print statements:")
    for file_path, prints in sorted(all_prints.items(), key=lambda x: len(x[1]), reverse=True):
        print(f"  {file_path}: {len(prints)} statements")


def main():
    """Main entry point for the script."""
    if len(sys.argv) < 2:
        print("Usage: python replace_prints.py [file_or_directory]")
        sys.exit(1)
    
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"Error: {path} does not exist")
        sys.exit(1)
    
    suggestions_path = Path('print_to_logging_suggestions.md')
    replacements_script_path = Path('scripts/apply_logging_replacements.py')
    
    if path.is_file():
        if not path.name.endswith('.py'):
            print(f"Error: {path} is not a Python file")
            sys.exit(1)
        
        prints = find_print_statements(path)
        all_prints = {str(path): prints}
    else:
        all_prints = scan_directory(path)
    
    print_report(all_prints)
    generate_replacement_file(all_prints, suggestions_path)
    generate_automatic_replacement_script(all_prints, replacements_script_path)
    
    print(f"\nDetailed suggestions written to {suggestions_path}")
    print(f"Automatic replacement script written to {replacements_script_path}")
    print(f"Run 'python {replacements_script_path}' to apply the replacements")


if __name__ == "__main__":
    main() 