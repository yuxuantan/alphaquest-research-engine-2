"""Independent comparison only. Never imported by production calculation code.

Usage: python scripts/verify_native_prop.py <native-report.json> <reference-dir>
The external reference is an oracle, never a source of production values.
"""
import argparse
import csv
import json
from pathlib import Path


def compare(calculations,reference):
    reference=Path(reference)
    expected=json.loads((reference/'results.json').read_text())
    checks=[]
    def check(name,actual,want):
        checks.append(dict(name=name,actual=actual,expected=want,pass_=actual==want))
    e=calculations['evaluation'];target=expected['part1']['rows'][0]
    for own,other in [('selected_micros','MNQ'),('pass_rate','pass rate'),('fail_drawdown','fail drawdown'),('timeout','fail deadline'),
                      ('median_days_to_pass','median days to pass'),('cost_per_funded','cost per funded'),
                      ('evaluations_per_funded','evaluations per funded'),('days_to_funded','days to funded'),
                      ('days_to_funded_median','days to funded median')]:
        want=float(target[other]) if own=='selected_micros' else target[other]
        check('evaluation.'+own,e[own],want)
    check('evaluation.discrete_passed',e['passed'],round(target['pass rate']*expected['part1']['simulated_evaluations']))
    check('evaluation.count',e['simulations'],expected['part1']['simulated_evaluations'])
    check('evaluation.interval',e['pass_rate_ci'],[target['range low'],target['range high']])
    target=expected['part2']['alone']['rows'][0];s=calculations['funded']['selected']
    for own,other in [('micros','MNQ'),('E[P] 12m','EV yr1'),('median 12m','median yr1'),('E[payout]','EV life'),
                      ('median life','median life'),('P(>=1) 12m','paid yr1'),('P(all 6)','all six'),('blown','blown'),('T1 median','first payout')]:
        check('funded.'+own,s[own],float(target[other]))
    checks_table=list(csv.DictReader(next(reference.glob('sizes_tried_in_sample_*.csv')).open()))
    check('funded.sweep_rows',len(calculations['funded']['sweep']),len(checks_table))
    for own,target in zip(calculations['funded']['sweep'],checks_table):
        for key,value in own.items():
            if key in target:
                want=float(target[key]) if isinstance(value,(int,float)) and target[key] else target[key] or None
                check(f'funded.sweep.{own["micros"]}.{key}',value,want)
    for own,other in [('data','data'),('train','in_sample'),('validation','out_of_sample'),('weekdays','weekdays')]:
        check('samples.'+own,calculations['samples'][own],expected['dates'][other])
    target=next(iter(expected['part2']['outcomes'].values()))
    for own,other in [('never_paid','never_paid'),('paid_partial','paid_1_to_5'),('paid_all','all_six')]:
        check('chart.outcomes.'+own,calculations['funded']['outcomes'][own],target[other])
    target=list(csv.DictReader(next(reference.glob('slot_accounts_*.csv')).open()))
    check('history.account_count',len(calculations['history']['accounts']),len(target))
    mapping={'blown':'blown','inactive':'closed for inactivity','paid_all':'all 6 payouts paid','open':'still open at the end of the data'}
    for own,want in zip(calculations['history']['accounts'],target):
        for key in ('start','end','payouts','account'):
            check(f'history.{own["account"]}.{key}',own[key],int(want[key]) if key in ('payouts','account') else want[key])
        check(f'history.{own["account"]}.outcome',mapping[own['outcome']],want['outcome'])
        check(f'history.{own["account"]}.payout_days',own['payout_days'],want['payout days'].split(', ') if want['payout days'] else [])
    target=expected['part2']['slots']['rows']
    for own,want in zip([*calculations['history']['years'],calculations['history']['totals']],target):
        for key,other in [('trading_days','trading days'),('payouts','payouts'),('new_funded_accounts','new funded accounts'),('costs','evals + activation'),('net','net')]:
            check(f'history.year.{own.get("year","all")}.{key}',own[key],want[other])
        if 'out_of_sample_share' in own:
            check(f'history.year.{own["year"]}.holdout_share',own['out_of_sample_share'],want['out-of-sample share'])
    return dict(all_pass=all(c['pass_'] for c in checks),comparison_count=len(checks),checks=checks)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('report',type=Path);p.add_argument('reference',type=Path);args=p.parse_args()
    report=json.loads(args.report.read_text());result=compare(report.get('calculations',report),args.reference)
    print(json.dumps(result,indent=2));raise SystemExit(0 if result['all_pass'] else 1)
