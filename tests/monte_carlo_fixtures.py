"""Test-only v1 schema fixture over actual native Monte Carlo path outcomes."""
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory

from alphaquest.prop.store import seal_report, sealed_checks


def legacy_assessment(store,id):
    """Represent a completed test population in its prior, internally consistent schema."""
    directory=store.root/id
    report=json.loads((directory/'report.json').read_text())
    report['policy']=dict(report['policy'],version='campaign-full-period-monte-carlo-v1',drawdown_multiple=2)
    report['rules'].append('95th-percentile daily-close maximum drawdown ≤ 2 × historical full-period daily-close maximum drawdown under both block lengths.')
    report.pop('diagnostics',None)
    for candidate in report['candidates']:
        for scenario in candidate['scenarios']:
            limit=2*candidate['observed']['daily_close_max_drawdown']
            scenario['checks'].append(dict(label='Drawdown resilience',passed=scenario['max_drawdown_p95']<=limit,
                actual=scenario['max_drawdown_p95'],required='95th percentile ≤ 2 × observed daily-close drawdown',limit=limit))
            scenario['qualifies']=candidate['evidence_passed'] and all(c['passed'] for c in scenario['checks'])
            for key in ('net_profit_mean','max_drawdown_median','historical_drawdown_percentile_pct','max_drawdown_p95_over_observed'):
                scenario.pop(key,None)
        candidate['qualifies']=candidate['evidence_passed'] and all(s['qualifies'] for s in candidate['scenarios'])
    report['passed']=sum(c['qualifies'] for c in report['candidates'])
    with TemporaryDirectory(dir=store.root) as temp:
        staged=Path(temp)
        for name in ('daily.csv','paths.csv'):shutil.copyfile(directory/name,staged/name)
        seal_report(staged,report,id,report['created_at_utc'])
        for name in ('report.json','analysis.zip'):shutil.copyfile(staged/name,directory/name)
    with store.connect() as db:
        db.execute('UPDATE analyses SET request_hash=? WHERE id=?',('SYNTHETIC v1 schema fixture '+id,id))
        db.execute('UPDATE analysis_report_checks SET payload=? WHERE id=?',(json.dumps(sealed_checks(directory)),id))
    assert store.fingerprint(id)
    return json.loads((directory/'report.json').read_text())
