"""Independent CSV, membership, date and cash audit; no engine imports."""
import argparse
import csv
from datetime import date,timedelta
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import zipfile


def verify(root):
    outcomes=[]
    for path in sorted(root.glob('test_large_campaign_confirmati[01]/workflow.json')):
        flow=json.loads(path.read_text());folder=path.parent
        campaign=json.loads((folder/'campaign.json').read_text())
        report=json.loads((folder/'report.json').read_text())
        rows=report['calculations']['candidates']
        assert [d['accepted'] for d in flow['dialogs']]==[False,True]
        assert all(d['type']=='confirm' and '129 candidates' in d['message'] for d in flow['dialogs'])
        assert flow['reopen_posts']==[]
        assert campaign['manifest']['candidate_search_count']==129
        assert campaign['declaration']['confirmed_candidate_count']==129
        assert campaign['declaration'].get('maximum_candidates') is None
        assert campaign['manifest']['candidate_confirmation']==dict(threshold=128,confirmed_count=129)
        expected={(id,size) for id in flow['source_ids'] for size in flow['sizes']}
        actual={(c['manifest']['configuration']['source']['source_backtest_id'],c['manifest']['configuration']['micros']) for c in rows}
        assert len(expected)==len(rows)==129 and actual==expected
        for name,checksum in flow['downloads'].items():
            assert sha256((folder/name).read_bytes()).hexdigest()==checksum
        start=date.fromisoformat(report['request']['calendar']['start_dates'][0])
        with zipfile.ZipFile(folder/'analysis.zip') as archive:
            assert archive.read('report.json')==(folder/'report.json').read_bytes()
            for name,info in report['files'].items():
                assert sha256(archive.read(name)).hexdigest()==info['sha256']
            for row in rows:
                c=row['manifest']['configuration'];source=c['source']['source_backtest_id']
                trades=list(csv.DictReader(archive.read(f'inputs/{source}/trades.csv').decode().splitlines()))
                assert len(trades)==8
                assert all(Decimal(t['total_commissions'])==Decimal(t['slippage_cost'])==0 for t in trades)
                assert {Decimal(t['net_pnl'])/Decimal(t['contracts'])/10 for t in trades}=={Decimal(300)}
                if flow['phase']=='evaluation':
                    assert 300*c['micros']>=3000
                    ready=start+timedelta(days=2)
                    assert (ready.weekday(),start.weekday())==(2,0)
                    cost=Decimal(c['profile']['evaluation_price'])+Decimal(c['profile']['activation_fee'])
                    assert cost==row['metrics']['cost_per_funded']==70
                    assert row['metrics']['expected_calendar_days_to_funded']==2
                    assert all(p['funded_date']==ready.isoformat() for p in row['paths'])
                else:
                    assert 300*c['micros']>=900
                    cutoff=start+timedelta(days=14)
                    opens=[start+timedelta(days=i) for i in range(14) if (start+timedelta(days=i)).weekday()<5]
                    requests=[opens[4],opens[9]]
                    receipts=[d+timedelta(days=4) for d in requests]
                    received=sum(1500 for d in receipts if d<cutoff)
                    assert received==row['metrics']['expected_payouts']==1500
                    assert row['metrics']['expected_pending_cash']==1500
                    assert row['metrics']['expected_gross_account_deductions']==3000
                    for p in row['paths']:
                        assert [e['request_date'] for e in p['payout_events']]==[d.isoformat() for d in requests]
                        assert [e['receipt_date'] for e in p['payout_events']]==[d.isoformat() for d in receipts]
        selection=report['calculations']['frontier' if flow['phase']=='evaluation' else 'ranking']
        assert len(selection)==129 and set(selection)=={r['candidate_id'] for r in rows}
        outcomes.append(dict(**flow,independent_rows_verified=len(rows),membership_verified=True,
            expected_metrics=dict(cost=70,days=2) if flow['phase']=='evaluation' else dict(received=1500,pending=1500,gross=3000),
            zip_artifacts_verified=len(report['files'])+1))
    assert {r['phase'] for r in outcomes}=={'evaluation','funded'}
    return dict(production_imports=False,synthetic=True,workflows=outcomes)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--browser-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    result=verify(args.browser_root)
    with args.output.open('x') as stream:json.dump(result,stream,indent=2)
    print(json.dumps(result,indent=2))
