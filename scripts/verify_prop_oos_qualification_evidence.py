"""Read-only independent arithmetic over saved product downloads; no simulation."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from statistics import mean
from zipfile import ZipFile


def verify(root):
    results=[]
    for profile in ('apex-50k-eod','lucidflex-50k'):
        folder=root/profile
        for phase in ('evaluation','funded'):
            report=json.loads((folder/f'{phase}-qualification.json').read_text())
            with ZipFile(folder/f'{phase}-qualification.zip') as archive:
                assert json.loads(archive.read('report.json'))==report
                assert len([p for p in archive.namelist() if p.endswith('/trades.csv')])==2
            row,=report['calculations']['candidates'];q=row['prop_qualification']
            assert q['status']=='GO' and q['forward_execution']['status']=='PENDING'
            assert q['evidence'][0]['actual']==12 and q['evidence'][1]['actual']==261*6
            assert len(row['paths'])==8 and row['configuration']['micros']==10
            histories,=report['calculations']['qualification_bootstrap']
            assert histories['unique_histories_evaluated']==[1,1]
            assert len(histories['replicates'])==10000
            for check in q['checks']:
                ratios=[r['ratios'][check['metric']] for r in histories['replicates']]
                assert min(ratios)==max(ratios)==check['lower']==check['upper']==1.
                assert row['metrics'][check['metric']]/report['assessment']['is_metrics'][row['frozen_candidate_id']][check['metric']]==check['point_ratio']==1.
            if phase=='evaluation':
                cost=49+129 if profile=='apex-50k-eod' else 80.5
                days=2 if profile=='apex-50k-eod' else 3
                assert row['metrics']['cost_per_funded']==cost
                assert row['metrics']['expected_calendar_days_to_funded']==days
            else:
                cash=[sum(e['trader_cash_received'] for e in p['payout_events']) for p in row['paths']]
                assert cash==[p['cash_received'] for p in row['paths']]
                assert mean(cash)==row['metrics']['expected_funded_cash_payouts_within_horizon']
                assert mean(cash)==(13000 if profile=='apex-50k-eod' else 5*2000*.90)
            results.append(dict(profile=profile,phase=phase,metrics=row['metrics'],
                ratio_and_bounds=1.,historical_replicates=10000,forward='PENDING',
                report_sha256=sha256((folder/f'{phase}-qualification.json').read_bytes()).hexdigest()))
    return results


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path,
        nargs='?',default=Path('docs/evidence/qualified_prop_sim/oos-confidence'))
    print(json.dumps(verify(parser.parse_args().directory),indent=2))
