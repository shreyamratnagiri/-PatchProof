"""Solver-backed properties are not program proofs. Skip without actual z3 package."""
from __future__ import annotations
import pytest
from packages.properties import check_linear_int_property


def test_property_implication_and_counterexample():
    pytest.importorskip('z3')
    proved=check_linear_int_property(['x'],[{'left':'x','op':'>=','right':5}],
                                     {'left':'x','op':'>=','right':0})
    assert proved['status']=='proved' and proved['verified']
    disproved=check_linear_int_property(['x'],[{'left':'x','op':'>=','right':5}],
                                        {'left':'x','op':'>=','right':8})
    assert disproved['status']=='counterexample' and disproved['witness']['x']<8


def test_unsatisfiable_assumptions_not_proven():
    pytest.importorskip('z3')
    answer=check_linear_int_property(['x'],[{'left':'x','op':'>=','right':5},
                                         {'left':'x','op':'<=','right':3}],
                                     {'left':'x','op':'>=','right':0})
    assert answer['status']=='invalid_assumptions'
