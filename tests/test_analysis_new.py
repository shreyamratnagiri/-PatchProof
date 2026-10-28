from pathlib import Path
import pytest
from packages.intelligence import index_repository, dependency_graph
from packages.retrieval import rank, cosine
from packages.repair import LLMReplacement, candidate_diff
from packages.properties import check_linear_int_property

def test_parsing_import_graph(tmp_path):
    (tmp_path/'mathutil.py').write_text('def increment(x):\n    return x+1\n')
    (tmp_path/'service.py').write_text('from mathutil import increment\nclass Service:\n    def run(self,x):\n        return increment(x)\n')
    entries=index_repository(tmp_path)
    assert [e['path'] for e in entries]==['mathutil.py','service.py']
    assert entries[1]['symbols'][0]['name']=='Service'
    assert {'source':'service.py','target':'mathutil.py'} in dependency_graph(entries)['edges']

def test_ranking_with_real_injected_vectors(tmp_path):
    (tmp_path/'add.py').write_text('def add(a,b):\n    return a+b\n')
    (tmp_path/'sub.py').write_text('def subtract(a,b):\n    return a-b\n')
    entries=index_repository(tmp_path)
    # Only deterministic injection for unit tests; production uses Ollama real inference.
    def embedding(texts):
        return [[1.,0.] if 'add' in t.lower() else [0.,1.] for t in texts]
    assert rank(entries,'add operation','lexical')[0]['path']=='add.py'
    assert rank(entries,'add operation','semantic',embed=embedding)[0]['path']=='add.py'
    assert rank(entries,'add operation','hybrid',embed=embedding)[0]['path']=='add.py'
    assert cosine([0.,1.],[1.,0.])==0

def test_diff_is_scoped_and_does_not_mutate(tmp_path):
    original='def add(a,b):\n    return a-b\n'
    (tmp_path/'add.py').write_text(original)
    repl=LLMReplacement(path='add.py',old='a-b',new='a+b',rationale='Use sum operation')
    old,new,diff=candidate_diff(tmp_path,repl,{'add.py'})
    assert old==original and 'a+b' in new and '+    return a+b' in diff
    assert (tmp_path/'add.py').read_text()==original
    with pytest.raises(ValueError):candidate_diff(tmp_path,repl,set())

def test_property_solver_fails_closed():
    result=check_linear_int_property(['x'],[{'left':'x','op':'>=','right':5}],{'left':'x','op':'>=','right':0})
    assert result['status'] in {'proved','unavailable'}
    assert result['verified'] is (result['status']=='proved')

def test_regression_candidate_schema():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        LLMReplacement(path='calc.py',old='1',new='2',rationale='few',regression_test='pass')
    assert LLMReplacement(path='calc.py',old='1',new='2',rationale='Change incorrect arithmetic',regression_test='import unittest\n').regression_test
