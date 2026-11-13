"""Read-only independent arithmetic over the automatic normal-product exports."""
from hashlib import sha256
import json
from pathlib import Path
from statistics import mean
from zipfile import ZipFile

root=Path(__file__).resolve().parents[1]/'docs/evidence/qualified_prop_sim/automatic-flow/final'
output=[]
for profile in ('apex-50k-eod','lucidflex-50k'):
    folder=root/profile;saved=json.loads((folder/'simulation.json').read_text())
    journey=json.loads((folder/'journey.json').read_text())
    assert journey['required_followup_actions']==0 and journey['source_checked_inside_run']
    assert journey['navigated_away_during_work'] and saved['configuration']['automatic']
    for phase in ('evaluation','funded'):
        original=json.loads((folder/(phase+'-is.json')).read_text())
        is_sha=sha256(json.dumps(original,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        with ZipFile(folder/(phase+'-oos.zip')) as archive:
            assert archive.testzip() is None
            result=json.loads(archive.read('report.json'))
        frozen=result['assessment']['frozen_package'];state=saved['automation']['phases'][phase]
        assert state['stage']=='complete'
        assert frozen['report_sha256']==is_sha==state['selection']['is_report_sha256']
        rows=original['calculations']['candidates'];assert sorted(r['configuration']['micros'] if 'configuration' in r else r['manifest']['configuration']['micros'] for r in rows)==[9,10]
        if phase=='evaluation':
            cost=178 if profile=='apex-50k-eod' else 80.5;days=2 if profile=='apex-50k-eod' else 3
            assert all(r['metrics']['cost_per_funded']==cost and r['metrics']['expected_calendar_days_to_funded']==days for r in rows)
        else:
            cash=13000 if profile=='apex-50k-eod' else 9000
            assert all(r['metrics']['expected_funded_cash_payouts_within_horizon']==cash for r in rows)
            assert all(mean(p['cash_received'] for p in r['paths'])==cash for r in rows)
        # Both tested sizes have identical objective values, so the independent
        # tie rule must select 9 MNQ and collapse all roles into one candidate.
        selected,=state['selection']['candidates'];assert selected['micros']==9
        assert len(selected['roles'])==(3 if phase=='evaluation' else 2)
        assert frozen['candidate_ids']==[selected['candidate_id']]
        oos,=result['calculations']['candidates'];assert oos['frozen_candidate_id']==selected['candidate_id']
        assert oos['configuration']['micros']==9
        assert oos['prop_qualification']['status']=='GO'
        assert oos['prop_qualification']['forward_execution']['status']=='PENDING'
        assert all(c['lower']==c['upper']==1. for c in oos['prop_qualification']['checks'])
        assert result['assessment']['prop_sim_review']['automatic_selection']==state['selection']
        output.append(dict(profile=profile,phase=phase,chosen_mnq=9,collapsed_roles=len(selected['roles']),
            original_is_report_hash_verified=True,required_followup_actions=0,oos='GO',forward='PENDING'))
print(json.dumps(output,indent=2))
