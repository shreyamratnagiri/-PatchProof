import json
from benchmarks.evaluate import BASE,evaluate

def test_benchmark_reproducibility(tmp_path):
    results=evaluate(BASE/'fixtures/cases.json',tmp_path)
    assert results['cases']==6
    assert results['methods']['lexical']['status']=='measured'
    assert len(json.loads((tmp_path/'per_case.json').read_text()))==24
    # Disabled Ollama does not silently become fake semantic similarity.
    assert results['methods']['semantic']['status'] in {'measured','incomplete'}
