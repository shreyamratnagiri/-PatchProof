"""Numerical and response handling boundaries for model-backed retrieval."""
from __future__ import annotations
import math
import pytest
from packages.retrieval import cosine, rank, ollama_embed


def test_cosine_nonfinite_or_mismatch_is_error():
    for other in ([1.0], [float('nan'), 1.0], [float('inf'),0.0]):
        with pytest.raises(ValueError):
            cosine([1.,0.],other)


def test_semantic_and_hybrid_with_real_numeric_fixture():
    # Controlled embedding fixture tests ranking algebra only, not model inference.
    entries=[{'path':'sum.py','symbols':[], 'source':'sum numbers', 'imports':[],'language':'python'},
             {'path':'divide.py','symbols':[],'source':'divide numbers','imports':[],'language':'python'}]
    def vectors(texts):
        return [[1.,0.] if 'sum' in t or 'add' in t else [0.,1.] for t in texts]
    for method in ('semantic','hybrid'):
        result=rank(entries,'sum numbers',method,embed=vectors)
        assert result[0]['path']=='sum.py'
        assert result[0]['semantic'] == 1.0


def test_ollama_embed_checks_nonfinite(monkeypatch):
    class Response:
        def raise_for_status(self): pass
        def json(self): return {'embeddings':[[1.0, float('nan')]]}
    class Client:
        def __init__(self,**kwargs): pass
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def post(self,*args,**kwargs): return Response()
    monkeypatch.setattr('packages.retrieval.httpx.Client',Client)
    with pytest.raises(ValueError,match='non-finite'):
        ollama_embed(['example'])
