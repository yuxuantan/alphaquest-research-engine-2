"""Read-only arithmetic and provenance checks over normal product downloads."""
from hashlib import sha256
import json
from pathlib import Path
from statistics import mean
from zipfile import ZipFile

root=Path(__file__).resolve().parents[1]
folder=root/'docs/evidence/qualified_prop_sim/parallel-confidence'
journey=json.loads((folder/'journey.json').read_text())
assert journey['synthetic'] and journey['initial_run_clicks']==1 and journey['followup_confirmation_clicks']==0
observed=json.loads((folder/'observed-job-progress.json').read_text())
assert len({j['progress'].get('completed') for j in observed})>1
out=[]
for phase in ('evaluation','funded'):
    with ZipFile(folder/(phase+'-oos.zip')) as archive:
        assert archive.testzip() is None
        report=json.loads(archive.read('report.json'))
    data,=report['calculations']['qualification_bootstrap'];row,=report['calculations']['candidates']
    assert len(data['replicates'])==10000 and data['unique_histories_evaluated']==[1,1]
    assert data['execution']['workers_used']==4 and len(data['execution']['worker_pids'])>=2
    assert not data['execution']['nested_pool']
    for index,replicate in enumerate(data['replicates']):
        assert replicate['replicate']==index
        assert all(v==1. for v in replicate['ratios'].values())
    assert all(c['lower']==c['upper']==1. for c in row['prop_qualification']['checks'])
    assert row['prop_qualification']['status']=='GO'
    assert row['prop_qualification']['forward_execution']['status']=='PENDING'
    assert row['configuration']['micros']==9
    if phase=='evaluation':
        assert row['metrics']['cost_per_funded']==80.5
        assert row['metrics']['expected_calendar_days_to_funded']==3
    else:
        assert len(row['paths'])==8
        assert mean(p['cash_received'] for p in row['paths'])==row['metrics']['expected_funded_cash_payouts_within_horizon']==9000
    for filename,expected in report['implementation']['files'].items():
        assert sha256((root/'alphaquest/prop'/filename).read_bytes()).hexdigest()==expected,filename
    captured=report['assessment']['prop_sim_review']['implementation']['files']
    for filename,expected in captured.items():
        path=root/'alphaquest'/filename if filename=='prop_sim_forward.py' else root/'alphaquest/prop'/filename
        assert sha256(path.read_bytes()).hexdigest()==expected,filename
    out.append(dict(phase=phase,workers=4,distinct_worker_pids=len(data['execution']['worker_pids']),
        resamples=10000,paths_per_size=8,bounds=[1.,1.],oos='GO',forward='PENDING',numerical_source_identity_verified=True))
print(json.dumps(out,indent=2))
