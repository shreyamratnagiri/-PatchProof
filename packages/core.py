"""Bounded static repository investigation and patch proposal."""
from __future__ import annotations
import ast
import difflib
import math
import re
from collections import Counter
from pathlib import Path

MAX_FILES=3000
MAX_FILE_BYTES=300_000
TOK=re.compile(r'[A-Za-z_][A-Za-z_0-9]*')

def tokens(text: str)->list[str]:
    return [x.lower() for x in TOK.findall(text)]

def scan(root:Path)->list[dict]:
    result=[]
    for path in sorted(root.rglob('*.py')):
        if len(result)>=MAX_FILES: break
        if any(x in {'.git','.venv','venv','node_modules','__pycache__'} for x in path.relative_to(root).parts):continue
        if path.is_symlink() or not path.is_file() or path.stat().st_size>MAX_FILE_BYTES:continue
        source=path.read_text(encoding='utf-8',errors='replace')
        try:
            tree=ast.parse(source)
            symbols=[{'name':n.name,'line':n.lineno} for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))]
            imports=sorted({n.module.split('.')[0] for n in ast.walk(tree) if isinstance(n,ast.ImportFrom) and n.module} | {a.name.split('.')[0] for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names})
            valid=True
        except SyntaxError:
            symbols=[];imports=[];valid=False
        result.append({'path':str(path.relative_to(root)),'symbols':symbols,'imports':imports,'valid':valid,'source':source})
    return result

def rank(files:list[dict],issue:str,method:str='hybrid')->list[dict]:
    if method not in {'lexical','semantic','hybrid'}:raise ValueError('unsupported ranking method')
    query=Counter(tokens(issue)); docs=[Counter(tokens(f['path']+' '+f['source'])) for f in files]
    n=len(files);df=Counter(t for d in docs for t in d)
    names={Path(f['path']).stem:i for i,f in enumerate(files)}
    edges={i:set(names[x] for x in f['imports'] if x in names and names[x]!=i) for i,f in enumerate(files)}
    lexical=[];semantic=[]
    for f,d in zip(files,docs):
        length=sum(d.values());avg=sum(sum(x.values()) for x in docs)/max(n,1)
        bm=sum(math.log(1+(n-df[t]+.5)/(df[t]+.5))*d[t]*2.2/(d[t]+1.2*(.25+.75*length/max(avg,1))) for t in query)
        lexical.append(bm)
        qt=set(query);dt=set(d);semantic.append(len(qt&dt)/max(1,math.sqrt(len(qt)*len(dt))))
    def normalize(xs):
        maximum=max(xs,default=0)
        return [x/maximum if maximum>0 else 0 for x in xs]
    lex=normalize(lexical);sem=normalize(semantic)
    base=[.7*a+.3*b for a,b in zip(lex,sem)]
    graph=normalize([sum(base[j] for j in edges[i])+sum(base[j] for j in range(n) if i in edges[j]) for i in range(n)])
    scores={'lexical':lex,'semantic':sem,'hybrid':[.55*a+.25*b+.20*c for a,b,c in zip(lex,sem,graph)]}[method]
    return sorted([{'path':f['path'],'score':round(scores[i],6),'lexical':round(lex[i],6),'semantic':round(sem[i],6),'graph':round(graph[i],6),'symbols':f['symbols'],'imports':f['imports']} for i,f in enumerate(files)],key=lambda x:(-x['score'],x['path']))

def propose_replacement(root:Path,relative:str,old:str,new:str)->str:
    """Deterministic scoped replacement; never modifies the original."""
    path=(root/relative).resolve()
    if not path.is_relative_to(root.resolve()) or path.suffix!='.py' or path.is_symlink():raise ValueError('invalid path')
    source=path.read_text()
    if not old or source.count(old)!=1:raise ValueError('old fragment must occur exactly once')
    changed=source.replace(old,new,1)
    ast.parse(changed)
    return ''.join(difflib.unified_diff(source.splitlines(True),changed.splitlines(True),fromfile='a/'+relative,tofile='b/'+relative))
