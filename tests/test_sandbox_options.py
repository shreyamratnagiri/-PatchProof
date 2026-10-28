"""Inspect the Docker command construction only; never simulate a successful
container run as integration evidence. Runtime integration lives in Docker tests.
"""
from pathlib import Path
import packages.verification as sandbox


def test_sandbox_command_restrictions(tmp_path:Path,monkeypatch):
    folder=tmp_path/'tests';folder.mkdir()
    (folder/'test_case.py').write_text('import unittest\n')
    monkeypatch.setattr(sandbox.shutil,'which',lambda name:'/usr/bin/docker' if name=='docker' else None)
    observed=[]
    def command(args,**kwargs):
        observed.append(args)
        return {'status':'finished','exit_code':125,'stdout':'','stderr':'offline', 'duration_ms':1}
    monkeypatch.setattr(sandbox,'_bounded_command',command)
    class Completed:
        returncode=0
    monkeypatch.setattr(sandbox.subprocess,'run',lambda *args,**kwargs:Completed())
    output=sandbox.verify(tmp_path)
    assert output['status']=='unavailable'
    args=observed[0]
    assert args[:2]==['docker','run']
    for option,value in [('--network','none'),('--read-only','--cap-drop'),('--cap-drop','ALL'),
                         ('--user','65534:65534'),('--memory','256m'),('--pids-limit','64')]:
        offset=args.index(option)
        assert args[offset+1]==value
    assert '--privileged' not in args
    assert '-v' not in args
    mounts=[args[i+1] for i,a in enumerate(args[:-1]) if a=='--mount']
    assert len(mounts)==1 and mounts[0].endswith('readonly')
    assert not any(word.startswith('AWS_') or word.startswith('PATCHPROOF_API_KEY') for word in args)
