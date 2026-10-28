"""Real Ollama inference check; no synthetic vector or fabricated model response."""
from __future__ import annotations

import json
import os
import sys
import time
import httpx
from packages.retrieval import ollama_embed
from packages.repair import ollama_candidates


def main() -> int:
    print('Embedding model:', os.getenv('PATCHPROOF_EMBED_MODEL', 'nomic-embed-text'))
    print('Patch model:', os.getenv('PATCHPROOF_PATCH_MODEL', 'qwen2.5-coder:7b'))
    try:
        start = time.perf_counter()
        vectors = ollama_embed(['sum two integers', 'subtract two integers'])
        assert len(vectors) == 2 and len(vectors[0]) > 0
        assert len(vectors[0]) == len(vectors[1])
        print(json.dumps({'embedding_dimensions': len(vectors[0]),
                          'inference_ms': round((time.perf_counter()-start)*1000)}))
        source = 'def add(a, b):\n    return a-b\n'
        entries = [{'path': 'calculator.py', 'source': source, 'symbols': [{'name':'add','line':1}],
                    'imports': [], 'language':'python', 'valid': True}]
        start = time.perf_counter()
        candidates, model = ollama_candidates('Addition returns subtraction. Please fix addition.', entries, attempts=1)
        print(json.dumps({'model': model, 'candidates': len(candidates),
                          'paths': [c.path for c in candidates],
                          'generation_ms': round((time.perf_counter()-start)*1000)}))
        return 0
    except (httpx.HTTPError, ValueError, AssertionError, KeyError, OSError) as exc:
        print('MODEL CHECK FAILED:', type(exc).__name__, str(exc)[:500], file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
