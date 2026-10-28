"""Conservative local source scan for accidentally committed high-risk secrets.

This is not a substitute for repository-history and third-party secret scanning.
Test fixtures and placeholder templates are excluded deliberately.
"""
from __future__ import annotations
import argparse
import re
from pathlib import Path

PATTERNS = {
    'private_key_block': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
    'aws_access_key_id': re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    'github_token': re.compile(r'\bgh[pousr]_[A-Za-z0-9]{30,}\b'),
    'openai_key': re.compile(r'\bsk-(?:proj-)?[A-Za-z0-9_-]{30,}\b'),
}
SKIP_DIRS = {'.git', '.venv', '.runtime', '.verification-logs', '__pycache__',
             'node_modules', 'tests', 'benchmarks', '.pytest_cache'}
SOURCE_SUFFIXES = {'.py', '.ts', '.tsx', '.js', '.json', '.yml', '.yaml', '.md', '.toml', '.sh', '.ps1'}


def scan(root: Path) -> list[tuple[str, int, str]]:
    """Return only pattern names and paths: never echo discovered secret values."""
    matches = []
    for file in root.rglob('*'):
        if file.is_symlink() or not file.is_file():
            continue
        rel = file.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if file.name in {'.env.example', 'FINAL_VALIDATION_REPORT.md', 'REMAINING_LOCAL_VERIFICATION.md'}:
            continue
        if file.suffix not in SOURCE_SUFFIXES or file.stat().st_size > 1_000_000:
            continue
        try:
            source = file.read_text('utf-8')
        except (OSError, UnicodeError):
            continue
        for number, line in enumerate(source.splitlines(), start=1):
            for name, pattern in PATTERNS.items():
                if pattern.search(line):
                    matches.append((rel.as_posix(), number, name))
    return matches


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    root = parser.parse_args().root.resolve()
    findings = scan(root)
    for file, line, kind in findings:
        print(f'{file}:{line}: potential {kind} (value hidden)')
    print(f'Pattern scan: {len(findings)} potential secrets' if findings else 'Pattern scan: no matching high-risk tokens')
    return 1 if findings else 0


if __name__ == '__main__':
    raise SystemExit(main())
