"""BM25 / local neural embeddings / ablatable graph-aware ranker.

Hybrid = 0.55 norm(BM25) + 0.30 norm(cosine_embedding)
         + 0.15 norm(maximum neighbor baseline score).
Scores normalize by max positive score in query. Graph is the undirected one-hop
import neighborhood; baseline neighbor score = 0.65 lexical + 0.35 semantic.
"""
from __future__ import annotations
import math
import os
import re
from collections import Counter
from typing import Callable
import httpx
from packages.intelligence import dependency_graph

_TOKEN = re.compile(r'[A-Za-z][a-z]*|[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+')

def tokenize(value: str) -> list[str]:
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', value.replace('_', ' '))
    return [t.lower() for t in _TOKEN.findall(text) if len(t) > 1]

def ollama_embed(texts: list[str]) -> list[list[float]]:
    """Real local inference. Raises on missing model; no fake fallback vectors."""
    if not texts:
        return []
    url = os.environ.get('PATCHPROOF_OLLAMA_URL', 'http://127.0.0.1:11434').rstrip('/')
    model = os.environ.get('PATCHPROOF_EMBED_MODEL', 'nomic-embed-text')
    with httpx.Client(timeout=30, trust_env=False) as client:
        response = client.post(f'{url}/api/embed', json={'model': model, 'input': texts, 'truncate': True})
        response.raise_for_status()
        result = response.json()['embeddings']
    if (not isinstance(result,list) or len(result) != len(texts) or
        any(not isinstance(row,list) or not row or len(row)>8192 for row in result)):
        raise ValueError('embedding model returned unexpected dimensions')
    size=len(result[0])
    if any(len(row)!=size or any(type(v) not in (int,float) or not math.isfinite(v) for v in row)
           for row in result):
        raise ValueError('embedding vector contains inconsistent or non-finite values')
    return result

def cosine(x: list[float], y: list[float]) -> float:
    if len(x) != len(y) or not x or any(not math.isfinite(t) for t in x+y):
        raise ValueError('invalid embedding dimensions or non-finite values')
    a = math.sqrt(sum(t*t for t in x))
    b = math.sqrt(sum(t*t for t in y))
    return sum(u*v for u,v in zip(x,y)) / (a*b) if a*b else 0.

def norm(xs: list[float]) -> list[float]:
    best = max(xs, default=0)
    return [max(0, a)/best if best > 0 else 0 for a in xs]

def rank(entries: list[dict], query: str, method: str = 'lexical', *, embed: Callable[[list[str]], list[list[float]]] | None = None, use_graph: bool = True, limit: int = 100) -> list[dict]:
    if method not in {'lexical', 'semantic', 'hybrid'}:
        raise ValueError('invalid localization method')
    if not 1 <= limit <= 3000:
        raise ValueError('invalid result limit')
    if not entries:
        return []
    docs = [Counter(tokenize(e['path'] + ' ' + ' '.join(s['name'] for s in e['symbols']) + ' ' + e['source'])) for e in entries]
    query_terms = Counter(tokenize(query))
    df = Counter(t for doc in docs for t in doc)
    avgdl = sum(sum(d.values()) for d in docs) / len(docs)
    rawbm = []
    for d in docs:
        length = sum(d.values())
        rawbm.append(sum(math.log(1+(len(docs)-df[t]+.5)/(df[t]+.5)) * (tf*2.2) / (tf+1.2*(.25+.75*length/max(1,avgdl))) * count for t,count in query_terms.items() if (tf := d.get(t,0))))
    lexical = norm(rawbm)
    semantic = [0.]*len(entries)
    if method != 'lexical':
        inference = embed or ollama_embed
        docs_text = [e['path'] + '\n' + '\n'.join(s['name'] for s in e['symbols']) + '\n' + e['source'][:4000] for e in entries]
        # Chunk embedding API calls for a bounded server request.
        vectors = []
        for start in range(0, len(docs_text), 12):
            batch = docs_text[start:start + 12]
            result = inference(batch)
            if not isinstance(result, list) or len(result) != len(batch):
                raise ValueError('embedding provider returned incorrect document count')
            vectors.extend(result)
        query_result = inference([query])
        if not isinstance(query_result, list) or len(query_result) != 1:
            raise ValueError('embedding provider returned incorrect query count')
        qvec = query_result[0]
        if not isinstance(qvec, list) or not qvec:
            raise ValueError('embedding provider returned empty query vector')
        semantic = norm([max(0, cosine(qvec, v)) for v in vectors])
    graph = [0.]*len(entries)
    if method == 'hybrid' and use_graph:
        edges = dependency_graph(entries)['edges']
        paths = {e['path']: i for i,e in enumerate(entries)}
        base = [.65*l+.35*s for l,s in zip(lexical,semantic)]
        for edge in edges:
            a, b = paths[edge['source']], paths[edge['target']]
            graph[a] = max(graph[a],base[b]); graph[b] = max(graph[b],base[a])
        graph = norm(graph)
    score = lexical if method == 'lexical' else semantic if method == 'semantic' else [.55*l+.30*s+.15*g for l,s,g in zip(lexical,semantic,graph)]
    return sorted(({'path': e['path'], 'score': round(score[i],6), 'lexical':round(lexical[i],6), 'semantic':round(semantic[i],6), 'graph':round(graph[i],6), 'symbols':e['symbols'], 'imports':e['imports']} for i,e in enumerate(entries)), key=lambda v: (-v['score'],v['path']))[:limit]
