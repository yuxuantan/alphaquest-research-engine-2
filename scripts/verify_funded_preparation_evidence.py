"""Read-only independent checks of the synthetic normal-product downloads.

No production account, sampling, selection or report implementation is imported.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZipFile


def verify(root):
    checked=[]
    for profile in ('apex-50k-eod','lucidflex-50k'):
        directory=root/profile
        simulation=json.loads((directory/'simulation.json').read_text())
        assert simulation['configuration']['automatic'] is True
        assert simulation['configuration']['simulations']==8
        assert simulation['configuration']['funded_horizon_calendar_days']==90
        for phase in ('evaluation','funded'):
            state=simulation['automation']['phases'][phase]
            assert state['stage']=='complete'
            assert [c['micros'] for c in state['selection']['candidates']]==[9]
            with ZipFile(directory/(phase+'-oos.zip')) as archive:
                report=json.loads(archive.read('report.json'))
                assert report['id']==state['oos_analysis_id']
                for name,metadata in report['files'].items():
                    payload=archive.read(name)
                    assert len(payload)==metadata['bytes']
                    assert sha256(payload).hexdigest()==metadata['sha256']
                row,=report['calculations']['candidates']
                bootstrap,=report['calculations']['qualification_bootstrap']
                assert row['configuration']['micros']==9
                assert report['assessment']['prop_sim_review']['automatic_selection']==state['selection']
                assert len(row['paths'])==8
                assert bootstrap['unique_histories_evaluated']==[1,1]
                assert len(bootstrap['replicates'])==10000
                for i,replicate in enumerate(bootstrap['replicates']):
                    assert replicate['replicate']==i
                    assert all(ratio==1. for ratio in replicate['ratios'].values())
                verdict=row['prop_qualification']
                assert verdict['status']=='GO' and verdict['forward_execution']['status']=='PENDING'
                assert all(check['lower']==check['upper']==1. for check in verdict['checks'])
                if phase=='funded':
                    # Six Apex full caps, or five Lucid full caps × trader share.
                    expected=sum((1500,1500,2000,2500,2500,3000)) if profile=='apex-50k-eod' else 5*2000*.9
                    assert all(path['cash_received']==expected for path in row['paths'])
                    assert row['metrics']['expected_funded_cash_payouts_within_horizon']==expected
                    preparation=bootstrap['execution']['funded_preparation']
                    assert preparation['version']=='dated-funded-preparation-v1'
                    assert preparation['budget_bytes_per_worker']==32*1024*1024
                    assert 0<preparation['maximum_accounted_bytes']<=preparation['budget_bytes_per_worker']
                else:
                    expected=49+129 if profile=='apex-50k-eod' else 80.5
                    assert row['metrics']['cost_per_funded']==expected
                checked.append(dict(profile=profile,phase=phase,analysis_id=report['id'],
                    expected=expected,paths=8,historical_refits=10000,
                    zip_members_verified=len(report['files'])+1,execution=bootstrap['execution']))
    return dict(synthetic=True,production_imports=False,verified=checked)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--evidence',type=Path,default=Path(__file__).resolve().parents[1]/'docs/evidence/qualified_prop_sim/funded-preparation')
    options=parser.parse_args()
    print(json.dumps(verify(options.evidence),indent=2))
