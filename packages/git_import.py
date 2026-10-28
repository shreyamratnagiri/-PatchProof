"""Supported HTTPS GitHub ingestion without checking out or executing repository content.

Clone is no-checkout; files are streamed out of Git object database. No external
filters, hooks, submodules or repository commands execute.
"""
from __future__ import annotations
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse
from packages.ingest import MAX_FILES,MAX_SINGLE_FILE,MAX_UNPACKED

REPO = re.compile(r'^/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?/?$')

def github_url(raw: str) -> str:
    parsed=urlparse(raw)
    if (parsed.scheme!='https' or parsed.hostname!='github.com' or parsed.port is not None or parsed.username or parsed.password
        or parsed.query or parsed.fragment or not REPO.fullmatch(parsed.path)):
        raise ValueError('Only public https://github.com/OWNER/REPO Git URLs are supported')
    return 'https://github.com/'+parsed.path.strip('/').removesuffix('.git')+'.git'

def _git(argv: list[str],cwd:Path,env:dict[str,str],timeout:int=30) -> bytes:
    try:
        completed=subprocess.run(['git','-c','credential.helper=','-c','http.followRedirects=false',*argv],cwd=cwd,env=env,
                                 stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout,check=False)
    except (subprocess.TimeoutExpired,OSError) as exc:
        raise ValueError('Git operation unavailable or timed out') from exc
    if completed.returncode!=0:
        raise ValueError('Git import failed: '+completed.stderr.decode('utf-8','replace')[:300])
    return completed.stdout

def clone_public_github(url:str,dest:Path)->tuple[str,int]:
    normalized=github_url(url)
    if not shutil.which('git'):
        raise ValueError('git executable unavailable')
    dest.parent.mkdir(parents=True,exist_ok=True)
    digest=hashlib.sha256(('git:'+normalized).encode()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='.github-',dir=dest.parent) as scratch:
        temporary=Path(scratch)
        repo=temporary/'objects'
        cleanenv={'PATH':os.environ.get('PATH','/usr/bin:/bin'),'HOME':str(temporary),'GIT_CONFIG_NOSYSTEM':'1',
                  'GIT_CONFIG_GLOBAL':os.devnull,'GIT_TERMINAL_PROMPT':'0','GIT_ASKPASS':os.devnull,
                  'GIT_LFS_SKIP_SMUDGE':'1','GIT_OPTIONAL_LOCKS':'0'}
        deadline=time.monotonic()+120
        _git(['clone','--depth','1','--filter=blob:none','--single-branch','--no-checkout','--no-tags',normalized,str(repo)],temporary,cleanenv,60)
        tree=_git(['-C',str(repo),'ls-tree','-r','-z','HEAD'],temporary,cleanenv)
        if tree.count(b'\x00')>MAX_FILES:
            raise ValueError('Git tree exceeds file count budget')
        root=temporary/'extracted';root.mkdir()
        seen=set();total=0;count=0
        for entry in tree.split(b'\x00'):
            if not entry:continue
            header,separator,name=entry.partition(b'\t')
            if not separator:raise ValueError('unparseable Git tree')
            fields=header.split()
            if len(fields)!=3 or fields[0]!=b'100644' and fields[0]!=b'100755' or fields[1]!=b'blob':
                continue  # reject symlinks, submodules and other object types
            try:rel=name.decode('utf-8','strict')
            except UnicodeDecodeError:continue
            parts=Path(rel).parts
            if (rel.startswith('/') or '\\' in rel or any(p in {'','..','.git','node_modules','.venv','.env'} for p in parts)
                or any(c in rel for c in '\x00:\r\n')):continue
            folded=rel.casefold()
            if folded in seen:raise ValueError('case collision in Git tree')
            seen.add(folded)
            remaining=max(1,int(deadline-time.monotonic()))
            if remaining<=1:
                raise ValueError('Git ingestion deadline exceeded')
            oid=fields[2].decode('ascii')
            size_bytes=_git(['-C',str(repo),'cat-file','-s',oid],temporary,cleanenv,min(remaining,10))
            if int(size_bytes.strip())>MAX_SINGLE_FILE:
                raise ValueError('Git blob exceeds file budget')
            contents=_git(['-C',str(repo),'cat-file','blob',oid],temporary,cleanenv,min(remaining,10))
            count+=1;total+=len(contents)
            if count>MAX_FILES or len(contents)>MAX_SINGLE_FILE or total>MAX_UNPACKED:
                raise ValueError('Git repository size budget exceeded')
            target=root.joinpath(*parts)
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(contents)
            target.chmod(0o600)
        if count==0:raise ValueError('Git repository has no supported files')
        shutil.move(str(root),str(dest))
    return digest,count
