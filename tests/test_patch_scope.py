from pathlib import Path
import pytest
from packages.repair import LLMReplacement, candidate_diff


@pytest.mark.parametrize('name', ['tests/test_math.py', 'src/__tests__/math.test.ts', 'test_app.py', 'src/app.spec.js'])
def test_repair_cannot_masquerade_as_test_patch(tmp_path: Path, name: str):
    source=tmp_path/name
    source.parent.mkdir(parents=True,exist_ok=True)
    source.write_text('x=1\n')
    candidate=LLMReplacement(path=name,old='x=1',new='x=2',rationale='Modification to a test must not be allowed')
    with pytest.raises(ValueError,match='test sources'):
        candidate_diff(tmp_path,candidate,{name})
    assert source.read_text()=='x=1\n'
