from pathlib import Path
import pytest
from packages.core import scan,rank,propose_replacement

def test_legacy_static_analysis(tmp_path):
    (tmp_path/'calc.py').write_text('def divide(a,b):\n    return a/b\n')
    files=scan(tmp_path)
    assert files[0]['symbols'][0]['name']=='divide'
    assert rank(files,'divide by zero')[0]['path']=='calc.py'

def test_legacy_diff(tmp_path):
    (tmp_path/'a.py').write_text('x = 1\n')
    diff=propose_replacement(tmp_path,'a.py','x = 1','x = 2')
    assert '+x = 2' in diff
    with pytest.raises(ValueError):propose_replacement(tmp_path,'../outside.py','x','y')
