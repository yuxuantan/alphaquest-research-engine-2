"""Read-only independent checks of the actual 40-size, 1,000-path outputs."""
from pathlib import Path
import json
from zipfile import ZipFile

folder=Path(__file__).resolve().parent
summary={}
for phase in ('evaluation','funded'):
    with ZipFile(folder/f'{phase}-forty-size-evidence.zip') as archive:
        report=json.loads(archive.read('report.json'))
    rows=report['calculations']['candidates']
    assert len(rows)==40
    assert sorted(row['manifest']['configuration']['micros'] for row in rows)==list(range(1,41))
    for row in rows:
        assert row['manifest']['configuration']['simulation']['simulations']==1000
        assert len(row['paths'])==1000
        if phase=='funded':
            expected=sum(p['cash_received'] for p in row['paths'])/1000
            assert abs(expected-row['metrics']['expected_funded_cash_payouts_within_horizon'])<1e-8
            for path in row['paths']:
                assert abs(path['cash_received']-sum(e['trader_cash_received'] for e in path['payout_events']))<1e-8
        elif row['metrics']['cost_per_funded'] is not None:
            expected=49/row['metrics']['pass_probability']+129
            assert abs(expected-row['metrics']['cost_per_funded'])<1e-8
    summary[phase]=dict(candidates=40,paths_per_size=1000,total_paths=sum(len(r['paths']) for r in rows),
        independent_cash_cost_checks=True,captured_artifact_bytes=sum(f['bytes'] for f in report['files'].values()))
assert 100*1024*1024//(40*5000)==524
print(json.dumps(summary,indent=2))
