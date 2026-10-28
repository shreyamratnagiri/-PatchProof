"""Precisely bounded Z3 checks for quantifier-free integer linear implication."""
from __future__ import annotations
from typing import Any

def check_linear_int_property(variables: list[str], assumptions: list[dict], conclusion: dict) -> dict[str, Any]:
    """Constraints: {left: str, op: <=|>=|==, right: int}; implication over signed integers."""
    try:
        import z3
    except ImportError:
        return {'status':'unavailable','verified':False,'reason':'z3-solver package not installed'}
    if not 1 <= len(variables) <= 10 or len(set(variables)) != len(variables) or len(assumptions) > 50:
        raise ValueError('invalid property budget')
    if any(not x.isidentifier() or x.startswith('_') for x in variables):
        raise ValueError('invalid variable')
    symbols = {name:z3.Int(name) for name in variables}
    def clause(c):
        if not isinstance(c,dict) or set(c) != {'left','op','right'} or c['left'] not in symbols or type(c['right']) is not int or abs(c['right'])>1_000_000:
            raise ValueError('unsupported linear constraint')
        if c['op'] not in {'<=','>=','=='}:
            raise ValueError('invalid comparator')
        x,y = symbols[c['left']],c['right']
        return {'<=':lambda:x<=y, '>=':lambda:x>=y, '==':lambda:x==y}[c['op']]()
    solver = z3.Solver()
    solver.set(timeout=1000)
    for c in assumptions: solver.add(clause(c))
    assumptions_status=solver.check()
    if assumptions_status == z3.unknown:
        return {'status':'unknown','verified':False,'reason':solver.reason_unknown()}
    if assumptions_status == z3.unsat:
        return {'status':'invalid_assumptions','verified':False,'reason':'assumptions are unsatisfiable'}
    solver.add(z3.Not(clause(conclusion)))
    result = solver.check()
    if result == z3.unsat:
        return {'status':'proved','verified':True,'scope':'QF_LIA implication of supplied constraints, NOT source code correctness'}
    if result == z3.sat:
        return {'status':'counterexample','verified':False,'witness':{name:int(str(solver.model().eval(sym))) for name,sym in symbols.items()}}
    return {'status':'unknown','verified':False,'reason':solver.reason_unknown()}
