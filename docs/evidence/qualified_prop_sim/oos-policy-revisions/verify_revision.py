"""Independent, read-only checks of the actual saved synthetic revision outputs."""
from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZipFile

folder=Path(__file__).resolve().parent
out={}
for phase in ('evaluation','funded'):
    old=json.loads((folder/f'{phase}-oos-report.json').read_text())
    new=json.loads((folder/f'{phase}-revised-report.json').read_text())
    before=old['calculations']['assessment_policy'];after=new['calculations']['assessment_policy']
    assert before['revision']==1 and after['revision']==2
    assert after['previous_policy_sha256']==before['policy_sha256']
    assert after['declaration_timing']=='retrospective'
    assert old['assessment']['frozen_package']==new['assessment']['frozen_package']
    assert old['implementation']==new['implementation']
    with ZipFile(folder/f'{phase}-oos-evidence.zip') as archive:
        original=archive.read('report.json')
    assert json.loads(original)==old
    assert new['assessment']['prop_sim_review']['base_report']['sha256']==sha256(original).hexdigest()
    for original,revised in zip(old['calculations']['candidates'],new['calculations']['candidates'],strict=True):
        assert original['candidate_id']==revised['candidate_id']
        assert original['metrics']==revised['metrics'] and original['paths']==revised['paths']
        assert original['economic_assessment']['verdict']=='PASS'
        assert revised['economic_assessment']['verdict']=='FAIL'
        paths=original['paths']
        if phase=='evaluation':
            mean=sum(p['paid_fees'] for p in paths)/len(paths)
            assert mean==130.59375
            assert mean<=float(before['limits']['maximum_cost_per_funded'])
            assert mean>float(after['limits']['maximum_cost_per_funded'])
        else:
            mean=sum(sum(e['trader_cash_received'] for e in p['payout_events']) for p in paths)/len(paths)
            assert mean==2812.5
            assert mean>=float(before['limits']['minimum_funded_receipts'])
            assert mean<float(after['limits']['minimum_funded_receipts'])
        out[phase]=dict(original_verdict='PASS',revised_verdict='FAIL',unchanged_mean_usd=mean,
            mc_paths_unchanged=True,original_sealed_report_sha256=sha256(ZipFile(folder/f'{phase}-oos-evidence.zip').read('report.json')).hexdigest())
print(json.dumps(out,indent=2))
