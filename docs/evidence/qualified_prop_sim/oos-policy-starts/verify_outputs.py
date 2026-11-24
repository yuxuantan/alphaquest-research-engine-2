"""Read-only independent arithmetic over the saved synthetic product outputs."""
from pathlib import Path
import json
import math

root=Path(__file__).resolve().parent
results={}
for phase in ('evaluation','funded'):
    report=json.loads((root/f'{phase}-oos-report.json').read_text())
    starts=json.loads((root/f'{phase}-account_starts-report.json').read_text())
    assert [r['paths'] for r in report['calculations']['candidates']]==[r['paths'] for r in starts['calculations']['candidates']]
    observations=[]
    for row in report['calculations']['candidates']:
        paths=row['paths'];n=len(paths);limits=report['calculations']['assessment_policy']['limits']
        if phase=='evaluation':
            cost=sum(p['paid_fees'] for p in paths)/n
            days=sum(p['calendar_days_to_funded'] for p in paths)/n
            assert cost==row['metrics']['cost_per_funded']
            assert days==row['metrics']['expected_calendar_days_to_funded']
            assert cost<=float(limits['maximum_cost_per_funded']) and days<=limits['maximum_calendar_days_to_funded']
            observations.append(dict(mean_cost_usd=cost,mean_calendar_days=days))
        else:
            cash=sorted(sum(e['trader_cash_received'] for e in p['payout_events']) for p in paths)
            assert cash==sorted(p['cash_received'] for p in paths)
            expected=dict(p10=cash[math.ceil(.1*n)-1],median=cash[math.ceil(.5*n)-1],p90=cash[math.ceil(.9*n)-1])
            assert expected==row['outcome_summary']['cash_quantiles']
            assert sum(cash)/n==row['metrics']['expected_funded_cash_payouts_within_horizon']
            assert sum(cash)/n>=float(limits['minimum_funded_receipts'])
            assert cash.count(0)/n==row['outcome_summary']['probability_zero_received_cash']
            observations.append(dict(mean_receipts_usd=sum(cash)/n,cash_quantiles=expected,zero_receipt_probability=cash.count(0)/n))
        assert row['economic_assessment']['verdict']=='PASS'
    paths=starts['calculations']['account_start_sensitivity']['candidates'][0]['paths']
    if phase=='evaluation':
        assert [p['result']['calendar_days_to_funded'] for p in paths]==[6,20,5,21,5]
        assert all(p['result']['paid_fees']==99.5 for p in paths)
    else:
        assert [p['result']['cash_received'] for p in paths]==[3600,1800,3600,0,3600]
        assert [p['result']['pending_cash'] for p in paths]==[0,1800,0,0,0]
        assert paths[3]['result']['outcome']=='inactive'
    results[phase]=dict(arithmetic=observations,covered_starts=len(paths),mc_paths_unchanged=True)
print(json.dumps(results,indent=2))
