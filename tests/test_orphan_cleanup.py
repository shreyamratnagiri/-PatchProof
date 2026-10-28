import uuid
from pathlib import Path
import pytest
from packages import sandbox_worker, verification


def test_cleanup_only_touches_labeled_containers(monkeypatch):
    commands=[]
    class Result:
        def __init__(self, output=''):
            self.returncode=0
            self.stdout=output
    monkeypatch.setattr(sandbox_worker.shutil, 'which', lambda n: '/usr/bin/docker')
    expected='1'*64
    def command(args, **kwargs):
        commands.append(args)
        return Result(expected+'\n')
    monkeypatch.setattr(sandbox_worker.subprocess,'run',command)
    assert sandbox_worker.cleanup_orphans()==1
    assert 'label=patchproof.owner=trusted-worker' in commands[0]
    assert commands[1] == ['docker','rm','-f',expected]


def test_job_label_is_validated_before_execution(tmp_path: Path):
    with pytest.raises(ValueError,match='job identifier'):
        verification.verify(tmp_path,job_id='--privileged')
