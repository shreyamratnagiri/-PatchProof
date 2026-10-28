"""Bounded, transactional extraction with no symlink or special-file support."""
from __future__ import annotations
import hashlib
import io
import os
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

MAX_ZIP = 16_000_000
MAX_FILES = 5000
MAX_UNPACKED = 40_000_000
MAX_SINGLE_FILE = 750_000

def extract_archive(blob: bytes, destination: Path) -> tuple[str, int]:
    if not blob or len(blob) > MAX_ZIP:
        raise ValueError('archive size outside permitted budget')
    digest = hashlib.sha256(blob).hexdigest()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix='.incoming-') as incoming:
        staging = Path(incoming) / 'code'
        staging.mkdir()
        total = 0
        count = 0
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            infos = archive.infolist()
            # Reject file-parent conflicts *before* writing any member: otherwise
            # mkdir('file/child') raises an unexpected server-side FileExistsError.
            file_paths = {member.filename.rstrip('/').casefold() for member in infos if not member.is_dir()}
            if any(any('/'.join(path.split('/')[:depth]) in file_paths
                       for depth in range(1, len(path.split('/'))))
                   for path in (member.filename.rstrip('/').casefold() for member in infos)):
                raise ValueError('archive file conflicts with child entry')
            if len(infos) > MAX_FILES:
                raise ValueError('archive entry limit exceeded')
            names: set[str] = set()
            regular_files: set[str] = set()
            for info in infos:
                relative = PurePosixPath(info.filename)
                parts = relative.parts
                if (not parts or relative.is_absolute() or any(p in {'', '.', '..'} for p in parts)
                    or '\\' in info.filename or '\x00' in info.filename or ':' in info.filename
                    or any(p.lower() in {'.git', '.env', '.venv', 'node_modules'} for p in parts)):
                    raise ValueError('unsafe archive member')
                filetype = (info.external_attr >> 16) & stat.S_IFMT(0o777777)
                if filetype not in (0, stat.S_IFREG, stat.S_IFDIR):
                    raise ValueError('archive contains unsupported special file')
                normalized = '/'.join(parts).casefold()
                if normalized in names:
                    raise ValueError('case-insensitive duplicate archive path')
                names.add(normalized)
                if not info.is_dir():
                    regular_files.add(normalized)
                if info.is_dir():
                    continue
                total += info.file_size
                count += 1
                if info.file_size > MAX_SINGLE_FILE or total > MAX_UNPACKED:
                    raise ValueError('archive extraction budget exceeded')
                if info.compress_size == 0 and info.file_size > 0 or info.compress_size > 0 and info.file_size / info.compress_size > 200:
                    raise ValueError('excessive decompression ratio')
                target = staging.joinpath(*parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                written = 0
                with archive.open(info) as source, target.open('xb') as output:
                    while part := source.read(65536):
                        written += len(part)
                        if written > MAX_SINGLE_FILE or written > info.file_size:
                            raise ValueError('extraction member size exceeded')
                        output.write(part)
                os.chmod(target, 0o600)
            # Validate file/parent conflicts before moving the staging directory.
            for member in names:
                pieces = member.split('/')
                if any('/'.join(pieces[:i]) in regular_files for i in range(1, len(pieces))):
                    raise ValueError('file conflicts with child archive entry')
        if count == 0:
            raise ValueError('empty archive')
        if destination.exists():
            raise ValueError('repository already exists')
        shutil.move(str(staging), str(destination))
    return digest, count

def safe_path(root: Path, relative: str, *, require_file: bool = True) -> Path:
    path = PurePosixPath(relative)
    if (not relative or path.is_absolute() or relative != path.as_posix()
        or any(x in {'', '.', '..'} for x in path.parts) or '\\' in relative
        or any(ord(ch) < 32 or ord(ch) == 127 for ch in relative)):
        raise ValueError('unsafe relative path')
    target = root.joinpath(*path.parts)
    if not target.resolve().is_relative_to(root.resolve()) or target.is_symlink():
        raise ValueError('unsafe resolved path')
    if require_file and (not target.is_file() or target.stat().st_size > MAX_SINGLE_FILE):
        raise ValueError('file missing or exceeds size budget')
    return target
