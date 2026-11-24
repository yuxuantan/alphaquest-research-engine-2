"""Normal product lifecycle, independent constant-source oracle and sealed outputs."""
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
from uuid import uuid4

import pytest

from test_prop_sim_assessment_reuse import qualified_library
from test_prop_sim import body,wait_prop
from test_prop_evaluation_validation import wait_assessment


@pytest.mark.parametrize('profile',['apex-50k-eod','lucidflex-50k'])
def test_frozen_choices_get_complementary_checks_without_refits(qualified_library,monkeypatch,tmp_path,profile):
    client,source=qualified_library
    for target in ('alphaquest.prop.oos_qualification.historical_ratios','alphaquest.prop.oos_bootstrap.run','alphaquest.prop.native_oos_bootstrap.run'):
        monkeypatch.setattr(target,lambda *a,**k:pytest.fail('Nested historical refits must not run'))
    config=dict(body(source),automatic=False,profile_id=profile,evaluation_minimum_micros=10,evaluation_maximum_micros=10,
        funded_minimum_micros=10,funded_maximum_micros=10,simulations=8,maximum_funded_breach_probability=None)
    if profile=='lucidflex-50k':config.update(evaluation_price='99.50',activation_fee='0',evaluation_consistency_percent=50)
    response=client.post('/api/prop-sim',json=config);assert response.status_code==202,response.text
    saved=wait_prop(client,response.json()['id']);outputs={}
    for phase in ('evaluation','funded'):
        prefix=f"/api/prop-sim/{saved['id']}/validation/{phase}"
        report=client.get(f"/api/prop-sim/{saved['id']}/results/{phase}").json()
        original=client.app.state.prop_analyses.fingerprint(report['id'])
        chosen=(report['calculations']['frontier'] if phase=='evaluation' else report['calculations']['ranking'])[:1]
        assert client.post(prefix+'/freeze',json=dict(candidate_ids=chosen,rationale='SYNTHETIC constant-day arithmetic oracle; no live claim')).status_code==200
        rid=uuid4().hex;launched=client.post(prefix,json=dict(request_id=rid,kind='qualification'));assert launched.status_code==202,launched.text
        attempt,result=wait_assessment(client,prefix,rid)
        calc=result['calculations'];row,=calc['candidates'];q=row['prop_qualification']
        assert q['version']=='prop-complementary-evidence-v2' and q['historical_replicates']==0
        assert 'qualification_bootstrap' not in calc and 'qualification_complementary' in calc
        assert q['status']=='GO',q
        assert all(f['state']=='PASS' for f in q['findings']),q
        assert q['forward_execution']['status']=='PENDING'
        assert {row['frozen_candidate_id']}==set(chosen) and calc['winner'] is None
        package,=calc['qualification_complementary']
        assert len(package['stress'])==5
        for role in ('is','oos'):
            assert all(len(c['paths'])==5000 for c in package['primary'][role])
        if phase=='evaluation':
            assert [c['summary']['horizon_calendar_days'] for c in package['primary']['oos']]==[90,180,365]
            assert all(c['summary']['funded_probability']['mean']==1 for c in package['primary']['oos'])
            assert all(c['summary']['fees_spent']['mean']==(178 if profile=='apex-50k-eod' else 99.5) for c in package['primary']['oos'])
        else:assert q['account_comparison']['oos'][0]['received_cash']['mean']==(13000 if profile=='apex-50k-eod' else 9000)
        assert len(package['account_starts']['candidates'][0]['paths'])==24
        summary=client.get(prefix+'/'+rid+'?summary=true').json()
        assert 'qualification_complementary' not in summary['calculations']
        assert summary['calculations']['candidates'][0]['prop_qualification']==q
        again=client.post(prefix,json=dict(request_id=uuid4().hex,kind='qualification'))
        assert again.status_code==202 and again.json()['analysis_id']==result['id'] and again.json()['reused']
        assert client.app.state.prop_analyses.fingerprint(report['id'])==original
        for name in ('report.json','complementary_evidence.json','oos_qualification.json','qualification_policy.json','analysis.zip'):
            response=client.get('/api/prop-analyses/'+result['id']+'/downloads/'+name)
            assert response.status_code==200,response.text
            (tmp_path/(phase+'-'+name)).write_bytes(response.content)
        outputs[phase]=dict(analysis_id=result['id'],verdict=q['status'],findings=q['findings'],is_report_sha256=original['files']['report.json'])
    (tmp_path/'journey.json').write_text(json.dumps(dict(synthetic=True,profile=profile,simulation=saved['id'],source=source,configuration=config,outputs=outputs),indent=2))
    if destination:=os.environ.get('ALPHAQUEST_COMPLEMENTARY_EVIDENCE_DIR'):
        target=Path(destination)/profile;target.mkdir(parents=True,exist_ok=True)
        for p in tmp_path.iterdir():
            if p.is_file():shutil.copyfile(p,target/p.name)
        if library:=os.environ.get('ALPHAQUEST_COMPLEMENTARY_SAVE_LIBRARY'):
            shutil.copytree(client.app.state.prop_analyses.root.parent,Path(library)/profile,dirs_exist_ok=True)
