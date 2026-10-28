"""Reproducible held-out localization benchmark (synthetic, NOT SWE-bench)."""
from __future__ import annotations
import json
import math
import os
import statistics
import tempfile
import time
import tracemalloc
from pathlib import Path
from packages.intelligence import index_repository
from packages.retrieval import rank

BASE=Path(__file__).parent

def evaluate(cases_path: Path, output: Path) -> dict:
    cases=json.loads(cases_path.read_text())
    output.mkdir(parents=True,exist_ok=True)
    run_cases=[]
    tracemalloc.start()
    for case in cases:
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for rel,source in case['files'].items():
                path=root/rel
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(source)
            entries=index_repository(root)
            for method in ('lexical','semantic','hybrid_no_graph','hybrid_graph'):
                start=time.perf_counter()
                try:
                    results=rank(entries,case['bug'],method='hybrid' if method.startswith('hybrid') else method, use_graph=method=='hybrid_graph')
                    duration_ms=(time.perf_counter()-start)*1000
                    positions=[i+1 for i,r in enumerate(results) if r['path']==case['fault_file']]
                    position=positions[0] if positions else None
                    row={'case_id':case['id'],'strategy':method,'status':'measured','rank':position,'recall_at_1':int(position==1),'recall_at_5':int(position is not None and position<=5),'reciprocal_rank':(1/position if position else 0),'latency_ms':round(duration_ms,3),'candidate_order':[r['path'] for r in results]}
                except Exception as exc:
                    row={'case_id':case['id'],'strategy':method,'status':'unavailable','reason':type(exc).__name__+': '+str(exc)[:300]}
                run_cases.append(row)
    _,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
    (output/'per_case.json').write_text(json.dumps(run_cases,indent=2)+'\n')
    aggregates={}
    for method in ('lexical','semantic','hybrid_no_graph','hybrid_graph'):
        relevant=[row for row in run_cases if row['strategy']==method]
        successful=[r for r in relevant if r['status']=='measured']
        if len(successful)!=len(relevant):
            aggregates[method]={'status':'incomplete','measured_cases':len(successful),'total_cases':len(relevant),'reason':'Some evaluations require a real configured embedding model. No score is reported for incomplete strategies.'}
        else:
            durations=sorted(r['latency_ms'] for r in successful)
            aggregates[method]={'status':'measured','cases':len(successful),
                  'recall_at_1':sum(r['recall_at_1'] for r in successful)/len(successful),
                  'recall_at_5':sum(r['recall_at_5'] for r in successful)/len(successful),
                  'mrr':sum(r['reciprocal_rank'] for r in successful)/len(successful),
                  'median_latency_ms':statistics.median(durations),
                  'p95_latency_ms':durations[max(0,math.ceil(len(durations)*.95)-1)]}
    summary={'benchmark':'small synthetic fault-localization fixtures; not a public real-world defect benchmark', 'cases':len(cases),'methods':aggregates,'peak_tracemalloc_bytes':peak,
             'limitations':['No real-world patches or model quality claims.','A neural embedding model must be configured for semantic and hybrid methods.','Tracemalloc tracks Python memory, not full process RSS.']}
    (output/'aggregate.json').write_text(json.dumps(summary,indent=2)+'\n')
    return summary

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--cases',type=Path,default=BASE/'fixtures/cases.json')
    parser.add_argument('--output',type=Path,default=BASE/'results')
    args=parser.parse_args()
    print(json.dumps(evaluate(args.cases,args.output),indent=2))
