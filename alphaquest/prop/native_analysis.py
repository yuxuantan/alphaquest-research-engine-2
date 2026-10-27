"""Local prop analysis. Reference reports are never calculation inputs."""
from dataclasses import asdict, replace
from datetime import date, datetime, timedelta
import csv
import io
import json
from pathlib import Path
import platform
import subprocess
import numpy as np
import pandas as pd

from .adapter import digest
from .native_backend import Rules, FundedAccount, evaluation, funded, compact_neutral_runs, identity as backend_identity

MODEL_VERSION = 'alphaquest-apex50k-eod-v1'
DEFAULTS = dict(PROP_FIRM='Apex', ACCOUNT_TYPE='Apex EOD', ACCOUNT_SIZE='50K', DAILY_LOSS_LIMIT='on',
                LUCID_EVAL_DAYS='no limit', SIZE_FOR='most net per year per slot', OUT_OF_SAMPLE_FROM='',
                NET_OPPOSITE=False, EVAL_PRICE='49', ACTIVATION_FEE='129', SLOTS='20', MAX_TOTAL_NQ='4',
                PAYOUT_REQUEST='the full payout cap each time', APPROVAL_DAY_COUNTS=True,
                SIMULATION_SIZE='standard', BLOCK_DAYS='5')


def resolved_settings(overrides):
    if not isinstance(overrides, dict) or set(overrides) - DEFAULTS.keys():
        raise ValueError('Unknown prop analysis setting.')
    settings = {**DEFAULTS, **overrides}
    fixed = ('PROP_FIRM', 'ACCOUNT_TYPE', 'ACCOUNT_SIZE', 'LUCID_EVAL_DAYS', 'SIZE_FOR', 'PAYOUT_REQUEST', 'SIMULATION_SIZE', 'DAILY_LOSS_LIMIT', 'NET_OPPOSITE')
    if any(settings[k] != DEFAULTS[k] for k in fixed):
        raise ValueError('Supported model: one strategy, Apex 50K EOD, DLL on, standard counts, slot-year selection and full-cap payouts.')
    if type(settings['APPROVAL_DAY_COUNTS']) is not bool:
        raise ValueError('APPROVAL_DAY_COUNTS must be boolean.')
    from decimal import Decimal, InvalidOperation
    for k in ('EVAL_PRICE', 'ACTIVATION_FEE', 'MAX_TOTAL_NQ', 'SLOTS'):
        if not isinstance(settings[k], str) or len(settings[k]) > 32:
            raise ValueError(f'{k} must be a numeric string.')
        try:
            value = Decimal(settings[k])
        except InvalidOperation as exc:
            raise ValueError(f'Invalid {k}.') from exc
        if not value.is_finite() or not 0 <= value <= 100000:
            raise ValueError(f'Invalid {k}.')
        if k == 'MAX_TOTAL_NQ' and (value <= 0 or value * 10 != int(value * 10)):
            raise ValueError('MAX_TOTAL_NQ must be a positive whole micro-equivalent quantity.')
        if k == 'SLOTS' and (value != int(value) or not 1 <= value <= 20):
            raise ValueError('SLOTS must be an integer from 1 to 20.')
    if settings['BLOCK_DAYS'] not in ('1', '5', '10'):
        raise ValueError('Bootstrap block must be 1, 5 or 10.')
    if not isinstance(settings['OUT_OF_SAMPLE_FROM'], str):
        raise ValueError('OUT_OF_SAMPLE_FROM must be an ISO date or empty string.')
    if settings['OUT_OF_SAMPLE_FROM']:
        date.fromisoformat(settings['OUT_OF_SAMPLE_FROM'])
    return settings


def prepare(runs, source_id, trade_file=None, settings=None, export_timezone='America/Chicago'):
    from .source import matching_exports, prepare_source
    resolved = resolved_settings(settings or {})
    if trade_file is None:
        matches = matching_exports(runs, source_id)
        if len(matches) == 1:
            trade_file = matches[0]['path']
    snapshot, rows = prepare_source(runs, source_id, trade_file, export_timezone)
    grid, days, split = day_book(rows, resolved)
    if split==0:raise ValueError('At least two session weekdays are needed for separate training and validation.')
    snapshot['session_grid'] = dict(first=str(grid[0].date()), last=str(grid[-1].date()),
                                   weekdays=len(grid), train=split, validation=len(grid)-split,
                                   convention='CME session date: Chicago entry timestamp plus 7 hours; zero-trade weekdays retained')
    return snapshot, rows, resolved


def day_book(rows, settings):
    from zoneinfo import ZoneInfo
    by_day = {}
    previous_exit = None
    for row in sorted(rows, key=lambda r: (r['entry_utc'], int(r['trade_id']))):
        entry = datetime.fromisoformat(row['entry_utc'].replace('Z', '+00:00'))
        exit = datetime.fromisoformat(row['exit_utc'].replace('Z', '+00:00'))
        if exit < entry or (previous_exit is not None and entry < previous_exit):
            raise ValueError('This model supports chronological nonoverlapping trades; overlapping positions require an event-position engine.')
        previous_exit = exit
        day = (entry.astimezone(ZoneInfo('America/Chicago')).replace(tzinfo=None) + timedelta(hours=7)).date()
        if day.weekday() >= 5:
            raise ValueError('Entry lies outside a weekday CME session; no trade is silently excluded.')
        q = float(row['quantity'])
        # Retain the matched export's floating representation after full cost/ID
        # reconciliation. Native Decimal amounts remain preserved alongside it.
        net = float(row['export_net_pnl'] if row['export_net_pnl'] is not None else row['source_net_pnl']) / q
        mae = float(row['measured_mae']) / q if row['measured_mae'] is not None else max(0., -net)
        by_day.setdefault(day, []).append((net, mae))
    grid = pd.bdate_range(min(by_day), max(by_day))
    if len(grid) > 20000:
        raise ValueError('Source exceeds 20,000 weekdays.')
    if len(grid) < 2:
        # A short source remains inspectable; no artificial history is created.
        split = 0
    elif settings['OUT_OF_SAMPLE_FROM']:
        split = int(grid.searchsorted(settings['OUT_OF_SAMPLE_FROM']))
        if not 0 < split < len(grid):
            raise ValueError('Explicit holdout date leaves an empty training or validation sample.')
    else:
        split = int(len(grid) * .7)
    return grid, [by_day.get(d.date(), []) for d in grid], split


def summary(accounts, micros):
    total = np.array([sum(v for _, v in a.payouts) for a in accounts])
    count = np.array([len(a.payouts) for a in accounts])
    days = np.array([a.day for a in accounts])
    first = np.array([a.payouts[0][0] for a in accounts if a.payouts])
    sixth = np.array([a.payouts[5][0] for a in accounts if len(a.payouts) == 6])
    n = len(accounts)
    return dict(size=f'{micros} MNQ', sims=n, **{
        'E[payout]':float(total.mean()), 'SE':float(total.std(ddof=1)/np.sqrt(n)) if n>1 else 0.,
        'P(>=1 payout)':float((count>0).mean()), 'P(all 6)':float((count==6).mean()),
        'avg payouts':float(count.mean()), 'blown':sum(a.outcome=='blown' for a in accounts)/n,
        'inactive':sum(a.outcome=='inactive' for a in accounts)/n, 'still open':sum(a.outcome=='open' for a in accounts)/n,
        'T1 median':float(np.median(first)) if len(first) else None,
        'T1 p75':float(np.percentile(first,75)) if len(first) else None,
        'T1 p90':float(np.percentile(first,90)) if len(first) else None,
        'T6 median':float(np.median(sixth)) if len(sixth) else None,
        'days alive':float(days.mean()), '$ per PA-day':float(total.mean()/days.mean()),
        'micros':micros, 'median life':float(np.median(total))})


def annual_summary(accounts):
    total = np.array([sum(v for _,v in a.payouts) for a in accounts])
    return {'E[P] 12m':float(total.mean()), 'SE 12m':float(total.std(ddof=1)/np.sqrt(len(total))) if len(total)>1 else 0.,
            'P(>=1) 12m':float((total>0).mean()), 'median 12m':float(np.median(total))}


def wilson(successes, n):
    p = successes/n; z = 1.96; den = 1+z*z/n
    center = (p+z*z/(2*n))/den
    margin = z/den*np.sqrt(p*(1-p)/n+z*z/(4*n*n))
    return [float(max(0.,center-margin)), float(min(1.,center+margin))]


def replay_history(grid, days, micros, replacement_days, cost, slots, rules=Rules(), max_micros=40, split=0):
    index = 0
    records = []
    money = []
    while index < len(grid):
        start = index
        account = FundedAccount(rules)
        money.append((index, 0., cost * slots, slots))
        while index < len(grid):
            payout = account.advance(days[index], micros, max_micros)
            if payout:
                money.append((index,payout*slots,0.,0))
            index += 1
            if account.outcome != 'open':
                break
        records.append(dict(account=len(records)+1, start=str(grid[start].date()), end=str(grid[index-1].date()),
                            outcome=account.outcome, payouts=len(account.payouts),
                            payout_days=[str(grid[start+d-1].date()) for d,_ in account.payouts]))
        index += int(np.ceil(replacement_days))
    quarters=[]
    for period in sorted(set(grid.to_period('Q'))):
        entries=[(p,c,n) for i,p,c,n in money if grid[i].to_period('Q')==period]
        # Round each calendar quarter first; annual totals add the rounded cash.
        quarters.append(dict(period=str(period),year=int(period.year),trading_days=int(sum(grid.to_period('Q')==period)),
                             payouts=round(sum(p for p,_,_ in entries)),new_funded_accounts=sum(n for _,_,n in entries),
                             costs=round(sum(c for _,c,_ in entries))))
        quarters[-1]['net']=quarters[-1]['payouts']-quarters[-1]['costs']
    years=[]
    for year in sorted(set(grid.year)):
        selected=[q for q in quarters if q['year']==year]
        years.append(dict(year=int(year),**{k:sum(q[k] for q in selected) for k in ('trading_days','payouts','new_funded_accounts','costs','net')},out_of_sample_share=float(sum(grid[split:].year==year)/sum(grid.year==year))))
    return dict(accounts=records,quarters=quarters,years=years,totals={k:sum(y[k] for y in years) for k in ('trading_days','payouts','new_funded_accounts','costs','net')})



def calculate(rows, settings, progress=lambda _:None):
    grid, days, split = day_book(rows,settings)
    if split==0:
        raise ValueError('At least two session weekdays are needed for separate training and validation; no history is fabricated.')
    days=compact_neutral_runs(days)
    train, validation = days[:split],days[split:]
    block = int(settings['BLOCK_DAYS']); max_micros = int(round(float(settings['MAX_TOTAL_NQ'])*10))
    rules = replace(Rules(),approval_day_counts=settings['APPROVAL_DAY_COUNTS'])
    progress('Local evaluation sizing on training sessions')
    evaluation_sweep=[]
    for size in sorted(set([min(s,max_micros,25) for s in [*range(1,21),25]])):
        sim = evaluation(train,size,3000,42,block,max_micros=max_micros)
        evaluation_sweep.append(dict(micros=size,passed=int(sum(sim['outcomes']=='passed')),simulations=3000))
    selected=max(evaluation_sweep,key=lambda r:r['passed'])['micros']
    progress('Local holdout evaluation: 20,000 paths')
    sim=evaluation(validation,selected,20000,43,block,max_micros=max_micros)
    outcomes=sim['outcomes']; passed=int(sum(outcomes=='passed')); probability=passed/20000
    result=dict(model_version=MODEL_VERSION,rules=asdict(rules),settings=settings,
                samples=dict(data=[str(grid[0].date()),str(grid[-1].date())],
                             train=[str(grid[0].date()),str(grid[split-1].date())],
                             validation=[str(grid[split].date()),str(grid[-1].date())],weekdays=[split,len(validation)]),
                seeds=dict(training=42,holdout=43,funding_chain=44,generator='MT19937 / RandomState bounded integers',block_days=block),
                evaluation=dict(selected_micros=selected,simulations=20000,passed=passed,pass_rate=probability,
                                fail_drawdown=float((outcomes=='blown').mean()),timeout=float((outcomes=='timeout').mean()),
                                pass_rate_ci=wilson(passed,20000),
                                median_days_to_pass=float(np.median(sim['days'][outcomes=='passed'])) if passed else None),
                evaluation_sweep=evaluation_sweep)
    if not passed:
        result.update(funded=None,history=None,unavailable='No validation evaluation passed. Acquisition time/cost and replacement-dependent sizing are unavailable.')
        return result
    chain=evaluation(validation,selected,20000,44,block,chain=True,max_micros=max_micros)
    cost=float(settings['EVAL_PRICE'])/probability+float(settings['ACTIVATION_FEE'])
    replacement=float(chain['days'].mean())
    result['evaluation'].update(cost_per_funded=cost,evaluations_per_funded=1/probability,
                                days_to_funded=replacement,days_to_funded_median=float(np.median(chain['days'])))
    sweep=[]
    for size in range(1,min(20,max_micros)+1):
        progress(f'Local funded sizing: {size} / {min(20,max_micros)} MNQ')
        life=funded(train,size,3000,42,block,rules=rules,max_micros=max_micros)
        annual=funded(train,size,3000,42,block,horizon=261,rules=rules,max_micros=max_micros)
        stats={**summary(life,size),**annual_summary(annual)}
        stats['slot_year']=261*(stats['E[payout]']-(float(settings['EVAL_PRICE'])/.525+float(settings['ACTIVATION_FEE'])))/(stats['days alive']+5.)
        sweep.append(stats)
    size=max(sweep,key=lambda r:r['slot_year'])['micros']
    progress('Local funded holdout: 20,000 lifetime and 20,000 first-year accounts')
    life=funded(validation,size,20000,43,block,rules=rules,max_micros=max_micros)
    annual=funded(validation,size,20000,43,block,horizon=261,rules=rules,max_micros=max_micros)
    stats={**summary(life,size),**annual_summary(annual)}
    result['funded']=dict(selected=stats,sweep=sweep,selection_economics=dict(pass_rate=.525,replacement_days=5,source='Fixed training-selection assumptions; validation handover used for reported acquisition cost and historical replay'),
        outcomes=dict(never_paid=sum(not a.payouts for a in life)/20000,paid_partial=sum(0<len(a.payouts)<6 for a in life)/20000,paid_all=sum(len(a.payouts)==6 for a in life)/20000))
    progress('Local chronological account replay and calendar-year cash totals')
    result['history']=replay_history(grid,days,size,replacement,cost,int(settings['SLOTS']),rules,max_micros,split)
    result['distributions']=dict(lifetime_totals=[sum(v for _,v in a.payouts) for a in life],
                                  payout_counts=[len(a.payouts) for a in life],
                                  lifetimes=[a.day for a in life],
                                  first_payout_days=[a.payouts[0][0] for a in life if a.payouts],
                                  evaluation_days=sim['days'].tolist())
    return result


def csv_text(rows):
    stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    return stream.getvalue()


def save_charts(result, staged):
    """Generate portable SVGs from local numerical arrays, plus chart-data JSON."""
    from html import escape
    charts=staged/'charts';charts.mkdir()
    ev=result['evaluation']
    chart_data={'evaluation':dict(pass_rate=ev['pass_rate'],ci=ev['pass_rate_ci'])}
    def svg(name,title,body,height=310):
        (charts/(name+'.svg')).write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 {height}" role="img"><title>{escape(title)}</title><rect width="1000" height="{height}" fill="#fff"/><g font-family="sans-serif" fill="#243442"><text x="25" y="35" font-size="20">{escape(title)}</text>{body}</g></svg>')
    low,high=ev['pass_rate_ci'];x=lambda p:200+p*750
    svg('evaluation','Holdout evaluation pass probability',f'<line x1="200" x2="950" y1="160" y2="160" stroke="#ddd"/><line x1="{x(low)}" x2="{x(high)}" y1="160" y2="160" stroke="#14734b" stroke-width="8"/><circle cx="{x(ev["pass_rate"])}" cy="160" r="8" fill="#14734b"/><text x="25" y="100">{ev["pass_rate"]:.2%} at {ev["selected_micros"]} MNQ; 95% interval {low:.2%} to {high:.2%}</text><text x="200" y="200">0%</text><text x="920" y="200">100%</text>')
    def bars(name,title,labels,values,unit):
        lower=min(0.,*values);upper=max(1.,*values);scale=680/(upper-lower)
        zero=260-lower*scale;body=f'<line x1="{zero}" x2="{zero}" y1="60" y2="{80+len(values)*45}" stroke="#bbb"/>'
        for i,(label,value) in enumerate(zip(labels,values)):
            y=80+i*45;end=zero+value*scale
            formatted=f'{value:.2%}' if unit=='probability' else f'${value:,.0f}'
            body+=f'<text x="25" y="{y+18}">{escape(str(label))}</text><rect x="{min(zero,end)}" y="{y}" width="{abs(value)*scale}" height="26" fill="{"#14734b" if value>=0 else "#b57919"}"/><text x="{min(850,max(zero,end)+8)}" y="{y+18}">{escape(formatted)}</text>'
        svg(name,title,body,max(200,120+45*len(values)))
    if result['funded']:
        outcomes=result['funded']['outcomes'];labels=['No payout','Partial ladder','All six payouts'];values=list(outcomes.values())
        bars('outcomes','Funded lifetime payout outcomes',labels,values,'probability')
        years=result['history']['years'];bars('slots','Net cash by calendar year',[y['year'] for y in years],[y['net'] for y in years],'USD')
        chart_data.update(outcomes=outcomes,slots=years)
    (charts/'data.json').write_text(json.dumps(chart_data,allow_nan=False))


def run_analysis(runs,request,staged,progress):
    snapshot,rows,settings=prepare(runs,request['source_backtest_id'],request.get('trade_file'),request.get('settings'),request['export_timezone'])
    progress('Source checked; all simulation arithmetic runs locally in AlphaQuest')
    inputs=staged/'inputs';inputs.mkdir()
    import shutil
    export=snapshot['excursion_input']
    if export['path']:
        copied=inputs/export['filename'];shutil.copyfile(export['path'],copied)
        if digest(copied)!=export['sha256']:raise ValueError('Excursion export changed before capture.')
    (inputs/'settings.json').write_text(json.dumps(settings,indent=2))
    result=calculate(rows,settings,progress)
    if digest(runs.root/request['source_backtest_id']/'trades.csv')!=snapshot['trades_sha256']:
        raise ValueError('Native source changed during calculation.')
    if export['path'] and digest(export['path'])!=export['sha256']:
        raise ValueError('Excursion export changed during calculation.')
    (staged/'trades.csv').write_text(csv_text(rows))
    (staged/'evaluation_sizing.csv').write_text(csv_text(result['evaluation_sweep']))
    if result['funded']:
        (staged/'funded_sizing.csv').write_text(csv_text(result['funded']['sweep']))
        (staged/'slot_accounts.csv').write_text(csv_text(result['history']['accounts']))
        (staged/'slots_year_by_year.csv').write_text(csv_text(result['history']['years']))
        (staged/'slots_by_quarter.csv').write_text(csv_text(result['history']['quarters']))
    save_charts(result,staged)
    (staged/'calculations.json').write_text(json.dumps(result,allow_nan=False))
    try:
        commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=Path(__file__).resolve().parents[2],text=True,stderr=subprocess.DEVNULL).strip()
    except (OSError,subprocess.CalledProcessError):commit='unavailable'
    return dict(format_version=3,model_version=MODEL_VERSION,source=snapshot,settings=settings,calculations=result,
                calculation_contract='AlphaQuest local account transitions, random sampling, sizing, economics and charts; no external engine or generated report inputs.',
                runtime=dict(python=platform.python_version(),numpy=np.__version__,pandas=pd.__version__,native_kernel=backend_identity()),
                application_commit=commit,implementation_sha256={p.name:digest(p) for p in Path(__file__).parent.glob('*.py')})
