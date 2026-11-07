"""Independent audit of saved coverage, zero-trade edges, dates and cash."""
import argparse
import csv
from datetime import datetime,timedelta
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo
import zipfile


def session(value):
    local=datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(ZoneInfo('America/Chicago'))
    return (local.replace(tzinfo=None)+timedelta(hours=7)).date()


def verify(root):
    outcomes=[]
    for path in sorted(root.glob('test_observed_is_default_in_pr[01]/workflow.json')):
        flow=json.loads(path.read_text());folder=path.parent
        report=json.loads((folder/'report.json').read_text())
        campaign=json.loads((folder/'campaign.json').read_text())
        metadata=json.loads((folder/'window-metadata.json').read_text())
        expected=dict(first_session='2021-01-04',last_session='2021-01-15')
        assert flow['expected_is_window']==campaign['declaration']['is_window']==expected
        assert metadata['is_window']==expected
        for id,count in ((flow['source_id'],10),(flow['zero_edge_source_id'],8)):
            backtest=folder/'backtest_runs'/id
            record=json.loads((backtest/'report.json').read_text())
            plan=record['run_metadata']['research']['plan']
            assert (plan['is_start'],plan['is_end'])==('2021-01-01','2021-01-17')
            assert record['period_start_utc']=='2021-01-03T23:01:00Z'
            assert record['period_end_utc']=='2021-01-14T23:04:00Z'
            first=max(plan['is_start'],session(record['period_start_utc']).isoformat())
            last=min(plan['is_end'],session(record['period_end_utc']).isoformat())
            assert dict(first_session=first,last_session=last)==expected
            with (backtest/'trades.csv').open() as stream:trades=list(csv.DictReader(stream))
            assert len(trades)==count
            if count==8:
                assert session(trades[0]['entry_time_utc']).isoformat()=='2021-01-05'
                assert session(trades[-1]['exit_time_utc']).isoformat()=='2021-01-14'
        for name,checksum in flow['downloads'].items():
            assert sha256((folder/name).read_bytes()).hexdigest()==checksum
        row=report['calculations']['candidates'][0];config=row['manifest']['configuration']
        assert config['period']==expected
        assert row['manifest']['source']['profile_research_period']['weekdays']==10
        with zipfile.ZipFile(folder/'analysis.zip') as archive:
            assert archive.read('report.json')==(folder/'report.json').read_bytes()
            for name,info in report['files'].items():assert sha256(archive.read(name)).hexdigest()==info['sha256']
            trades=list(csv.DictReader(archive.read(f"inputs/{flow['source_id']}/trades.csv").decode().splitlines()))
        assert len(trades)==10
        assert all(Decimal(t['net_pnl'])==3000 and Decimal(t['total_commissions'])==Decimal(t['slippage_cost'])==0 for t in trades)
        if flow['phase']=='evaluation':
            # Ten MNQ earn $3,000/session; Monday pass, Tuesday activation,
            # Wednesday first usable funded session. $30 purchase + $40 activation.
            assert config['micros']==10
            assert Decimal(config['profile']['evaluation_price'])+Decimal(config['profile']['activation_fee'])==70
            assert row['metrics']['cost_per_funded']==70 and row['metrics']['expected_calendar_days_to_funded']==2
            assert all(p['funded_date']=='2021-01-06' for p in row['paths'])
        else:
            # Three MNQ earn $900/session. Five-day requests Jan 8/15; lag 4,
            # receipts Jan 12/19; exclusive cutoff Jan 18 leaves the latter pending.
            assert config['micros']==3
            assert row['metrics']['expected_payouts']==row['metrics']['expected_pending_cash']==1500
            assert row['metrics']['expected_gross_account_deductions']==3000
            for p in row['paths']:
                assert [e['request_date'] for e in p['payout_events']]==['2021-01-08','2021-01-15']
                assert [e['receipt_date'] for e in p['payout_events']]==['2021-01-12','2021-01-19']
        assert flow['reopen_posts']==[]
        outcomes.append(dict(**flow,zero_trade_edge_sessions_retained=True,zip_artifacts_verified=len(report['files'])+1))
    assert {r['phase'] for r in outcomes}=={'evaluation','funded'}
    return dict(production_imports=False,synthetic=True,workflows=outcomes)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--browser-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    result=verify(args.browser_root)
    with args.output.open('x') as stream:json.dump(result,stream,indent=2)
    print(json.dumps(result,indent=2))
