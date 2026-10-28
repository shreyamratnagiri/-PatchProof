from packages.candidate_ranking import candidate_priority

DIFF='--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-x=1\n+x=2\n'

def test_test_evidence_outranks_syntax_only():
    syntax=candidate_priority(DIFF,{'existing_tests':'not_run'})
    success=candidate_priority(DIFF,{'existing_tests':{'status':'passed'},'regression_tests':{'status':'passed'}})
    failure=candidate_priority(DIFF,{'existing_tests':{'status':'failed'}})
    unknown=candidate_priority(DIFF,{'existing_tests':{'status':'unavailable'}})
    assert success['score'] > syntax['score'] == unknown['score'] > failure['score']
    assert success['components']['regression_tests'] == 30
    assert 'NOT patch correctness probability' in success['meaning']
