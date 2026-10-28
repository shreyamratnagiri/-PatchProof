"""AST and optional tree-sitter analysis with dependency and call approximations."""
from __future__ import annotations
import ast
import os
import re
from pathlib import Path
from packages.ingest import safe_path

EXTENSIONS = {'.py': 'python', '.js': 'javascript', '.jsx': 'javascript', '.ts': 'typescript', '.tsx': 'tsx'}
MAX_INDEXED = 3000
MAX_SCANNED = 25_000
MAX_DIRECTORIES = 10_000
MAX_SOURCE_BYTES = 16_000_000

def _js_analysis(source: str, language: str) -> tuple[list[dict], list[str], bool]:
    try:
        from tree_sitter_language_pack import get_parser
    except ImportError:
        return [], [], False
    try:
        parser = get_parser(language)
        tree = parser.parse(source.encode('utf-8'))
    except (ValueError, RuntimeError, TypeError):
        return [], [], False
    symbols: list[dict] = []
    imports: list[str] = []
    def walk(node):
        if node.type in {'function_declaration', 'class_declaration', 'method_definition', 'interface_declaration', 'type_alias_declaration'}:
            name = node.child_by_field_name('name')
            if name:
                symbols.append({'name': source.encode()[name.start_byte:name.end_byte].decode('utf-8', 'replace'), 'line': node.start_point.row + 1, 'kind': node.type})
        if node.type == 'import_statement':
            raw = source.encode()[node.start_byte:node.end_byte].decode('utf-8', 'replace')
            match = re.search(r'[\'"]([^\'"]+)[\'"]', raw)
            if match:
                imports.append(match.group(1))
    # Iterative traversal avoids recursion depth exhaustion on adversarial syntax trees.
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        walk(node)
        stack.extend(reversed(node.children))
    return symbols, sorted(set(imports)), not tree.root_node.has_error

def index_repository(root: Path) -> list[dict]:
    """Bound tree traversal, file count and indexed source memory.

    Unsupported and oversized content is ignored. An import cannot force
    millions of directory entries to be explored for a handful of code files.
    """
    results = []
    scanned = 0
    visited_directories = 0
    total_bytes = 0
    ignored = {'.git', '.venv', 'node_modules', '__pycache__', '.runtime'}
    # os.walk does not follow directory symlinks with followlinks=False.
    for directory, subdirs, filenames in os.walk(root, followlinks=False):
        visited_directories += 1
        if visited_directories > MAX_DIRECTORIES:
            return results
        subdirs[:] = sorted(d for d in subdirs if d not in ignored and
                            not (Path(directory) / d).is_symlink())
        for filename in sorted(filenames):
            scanned += 1
            if scanned > MAX_SCANNED or len(results) >= MAX_INDEXED or total_bytes >= MAX_SOURCE_BYTES:
                return results
            path = Path(directory) / filename
            if path.suffix not in EXTENSIONS or not path.is_file() or path.is_symlink():
                continue
            rel = path.relative_to(root).as_posix()
            try:
                size = path.stat().st_size
                if size > 750_000 or size > MAX_SOURCE_BYTES - total_bytes:
                    continue
                source = safe_path(root, rel).read_text('utf-8')
            except (UnicodeError, OSError, ValueError):
                continue
            total_bytes += len(source.encode('utf-8'))
            language = EXTENSIONS[path.suffix]
            if language == 'python':
                try:
                    tree = ast.parse(source)
                    symbols = [{'name': n.name, 'line': n.lineno, 'kind': type(n).__name__} for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
                    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
                    for node in ast.walk(tree):
                        if isinstance(node, ast.ImportFrom):
                            prefix = '.' * node.level
                            if node.module:
                                imported.add(prefix + node.module)
                            elif prefix:
                                imported.update(prefix + alias.name for alias in node.names)
                    imports = sorted(imported)
                    calls = sorted({n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)})
                    valid = True
                except SyntaxError:
                    symbols, imports, calls, valid = [], [], [], False
            else:
                symbols, imports, valid = _js_analysis(source, language)
                calls = []
            results.append({'path': rel, 'language': language, 'symbols': symbols, 'imports': imports, 'calls': calls, 'valid': valid, 'source': source[:750000]})
    return results

def dependency_graph(entries: list[dict]) -> dict:
    """Approximate static imports, preferring exact local paths over basename guesses."""
    bypath = {r['path']: r for r in entries}
    bystem: dict[str, set[str]] = {}
    for path in bypath:
        bystem.setdefault(Path(path).stem, set()).add(path)

    def targets(path: str, imported: str) -> set[str]:
        origin = Path(path)
        suffixes = ('.py', '.js', '.jsx', '.ts', '.tsx')
        relative = imported.startswith('.')
        if relative:
            dots = len(imported) - len(imported.lstrip('.'))
            parent = origin.parent
            for _ in range(max(0, dots - 1)):
                parent = parent.parent
            remainder = imported[dots:].replace('.', '/')
            stem = (parent / remainder).as_posix()
        elif '/' in imported:
            stem = imported
        else:
            stem = imported.replace('.', '/')
        matches = {candidate for candidate in bypath if candidate in
                   {stem + ext for ext in suffixes} | {stem + '/index' + ext for ext in suffixes} |
                   {stem + '/__init__.py'}}
        if matches or relative:
            return matches
        # Bare imports could refer to a local module; ambiguity is explicit.
        return bystem.get(imported.split('.')[-1], set())

    edges: set[tuple[str, str]] = set()
    for record in entries:
        for imported in record['imports']:
            for match in targets(record['path'], imported):
                if record['path'] != match:
                    edges.add((record['path'], match))
    return {'nodes': [{'id': record['path'], 'language': record['language'],
                       'symbols': len(record['symbols'])} for record in entries],
            'edges': [{'source': source, 'target': dest} for source, dest in sorted(edges)],
            'note': 'Approximate static import graph; dynamic imports and path aliases are not resolved.'}
