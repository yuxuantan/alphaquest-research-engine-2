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
from .parallel import map_sweep,diagnostics as execution_diagnostics

MODEL_VERSION = 'alphaquest-apex50k-eod-v4-instrument-commissions'
DEFAULTS = dict(PROP_FIRM='Apex', ACCOUNT_TYPE='Apex EOD', ACCOUNT_SIZE='50K', DAILY_LOSS_LIMIT='on',
                LUCID_EVAL_DAYS='no limit', SIZE_FOR='most net per year per slot', OUT_OF_SAMPLE_FROM='',
                NET_OPPOSITE=False, EVAL_PRICE='49', ACTIVATION_FEE='129', SLOTS='20', MAX_TOTAL_NQ='4',
                PAYOUT_REQUEST='the full payout cap each time', APPROVAL_DAY_COUNTS=True,
                SIMULATION_SIZE='standard', BLOCK_DAYS='5', COMMISSION_MODE='auto',
                COMMISSION_BROKER='Rithmic', SOURCE_INSTRUMENT='auto', COMMISSION_PER_SIDE='')


def resolved_settings(overrides):
    if not isinstance(overrides, dict) or set(overrides) - DEFAULTS.keys():
        raise ValueError('Unknown prop analysis setting.')
    from .lucid_rules import defaults as lucid_defaults
    lucid=overrides.get('PROP_FIRM')=='Lucid' or overrides.get('ACCOUNT_TYPE')=='LucidFlex'
    base=lucid_defaults(DEFAULTS) if lucid else DEFAULTS
    settings = {**base, **overrides}
    if settings['COMMISSION_MODE'] not in ('auto', 'source', 'override'):
        raise ValueError('Commission mode must be auto, source or override.')
    if settings['SOURCE_INSTRUMENT'] not in ('auto', 'NQ', 'MNQ'):
        raise ValueError('This account model supports NQ or MNQ sources.')
    if not isinstance(settings['COMMISSION_BROKER'], str) or not settings['COMMISSION_BROKER'].strip() or len(settings['COMMISSION_BROKER']) > 80:
        raise ValueError('Enter a broker name of 1 to 80 characters.')
    rate = settings['COMMISSION_PER_SIDE']
    if not isinstance(rate, str) or len(rate) > 32:
        raise ValueError('Per-side commission must be a numeric string or blank for the broker default.')
    if rate:
        from decimal import Decimal, InvalidOperation
        try:
            fee = Decimal(rate)
        except InvalidOperation as exc:
            raise ValueError('Invalid per-side commission.') from exc
        if not fee.is_finite() or not 0 <= fee <= 100000:
            raise ValueError('Per-side commission must be finite and nonnegative.')
    fixed = ('PROP_FIRM', 'ACCOUNT_TYPE', 'ACCOUNT_SIZE', 'LUCID_EVAL_DAYS', 'SIZE_FOR', 'PAYOUT_REQUEST', 'SIMULATION_SIZE', 'DAILY_LOSS_LIMIT', 'NET_OPPOSITE')
    if lucid:fixed=tuple(k for k in fixed if k!='DAILY_LOSS_LIMIT')
    if any(settings[k] != base[k] for k in fixed):
        raise ValueError('Supported model: one strategy, Apex 50K EOD, DLL on, standard counts, slot-year selection and full-cap payouts.')
    if lucid and (settings['DAILY_LOSS_LIMIT'] not in ('on','off') or settings['ACTIVATION_FEE']!='0'):
        raise ValueError('LucidFlex supports DLL on/off, standard 40% evaluation consistency and zero activation fee.')
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
        if k == 'SLOTS' and (value != int(value) or not 1 <= value <= (5 if lucid else 20)):
            raise ValueError('SLOTS must be an integer from 1 to '+('5.' if lucid else '20.'))
    if settings['BLOCK_DAYS'] not in ('1', '5', '10'):
        raise ValueError('Bootstrap block must be 1, 5 or 10.')
    if not isinstance(settings['OUT_OF_SAMPLE_FROM'], str):
        raise ValueError('OUT_OF_SAMPLE_FROM must be an ISO date or empty string.')
    if settings['OUT_OF_SAMPLE_FROM']:
        date.fromisoformat(settings['OUT_OF_SAMPLE_FROM'])
    return settings


def is_lucid(settings):return settings.get('ACCOUNT_TYPE')=='LucidFlex'

def model_version(settings):
    if is_lucid(settings):
        from .lucid_rules import MODEL_VERSION as lucid_version
        return lucid_version
    return MODEL_VERSION

def kernel_identity(settings):
    if is_lucid(settings):
        from .lucid_backend import identity
        return identity()
    return backend_identity()

def account_backend(rules):
    if getattr(rules,'provider',None)=='lucidflex':
        from . import lucid_backend
        return lucid_backend
    return None

def evaluation_model(days,size,sims,seed,block,settings,**kwargs):
    if is_lucid(settings):
        from .lucid_backend import evaluation as lucid_evaluation
        return lucid_evaluation(days,size,sims,seed,block,daily_loss=1200. if settings['DAILY_LOSS_LIMIT']=='on' else None,**kwargs)
    return evaluation(days,size,sims,seed,block,**kwargs)


def prepare(runs, source_id, trade_file=None, settings=None, export_timezone='America/Chicago'):
    from .source import matching_exports, prepare_source
    resolved = resolved_settings(settings or {})
    if trade_file is None:
        matches = matching_exports(runs, source_id)
        if len(matches) == 1:
            trade_file = matches[0]['path']
    snapshot, rows = prepare_source(runs, source_id, trade_file, export_timezone)
    from .commissions import adapt as adapt_commissions
    adapt_commissions(snapshot, rows, resolved)
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
        if is_lucid(settings):
            from datetime import time as clock_time
            eastern=entry.astimezone(ZoneInfo('America/New_York'))
            evening=eastern.time()>=clock_time(18)
            valid_day=eastern.weekday() in (6,0,1,2,3) if evening else eastern.weekday()<5
            if not valid_day or (not evening and eastern.time()>=clock_time(16,45)):
                raise ValueError('LucidFlex source entry is outside regular trading hours (18:00–16:45 America/New_York).')
            cutoff=datetime.combine(eastern.date()+timedelta(days=int(evening)),clock_time(16,45),ZoneInfo('America/New_York'))
            if exit>cutoff:
                raise ValueError('LucidFlex would flatten this source position at 16:45 America/New_York. Its earlier exit price is unavailable; the source is incompatible, not a simulated account breach. Rerun the backtest with an earlier flatten time.')
        day = (entry.astimezone(ZoneInfo('America/Chicago')).replace(tzinfo=None) + timedelta(hours=7)).date()
        if day.weekday() >= 5:
            raise ValueError('Entry lies outside a weekday CME session; no trade is silently excluded.')
        if row.get('risk_cross_session'):
            raise ValueError('Native OHLC risk spans CME session days. This daily model cannot allocate overnight unrealized P&L safely; use an intraday-flat source. No close-only fallback was substituted.')
        q = float(row['quantity'])
        # Retain the matched export's floating representation after full cost/ID
        # reconciliation. Native Decimal amounts remain preserved alongside it.
        net = float(row['export_net_pnl'] if row['export_net_pnl'] is not None else row['source_net_pnl']) / q
        mae = float(row['ohlc_mae_upper']) / q if row.get('ohlc_mae_upper') is not None else float(row['measured_mae']) / q if row['measured_mae'] is not None else max(0., -net)
        if 'simulation_net_per_nq' in row:
            net = float(row['simulation_net_per_nq'])
            mae = float(row['simulation_mae_per_nq'])
        raw_path = row.get('simulation_adverse_path_per_nq', row.get('ohlc_adverse_path'))
        if raw_path is not None:
            divisor = 1 if 'simulation_adverse_path_per_nq' in row else q
            path=tuple((float(amount)/divisor,gap) for amount,gap in json.loads(raw_path))
            trade=(net,mae,path)
        else:
            trade=(net,mae)
        if is_lucid(settings):
            from datetime import time as clock_time
            closed=exit.astimezone(ZoneInfo('America/New_York')).time()
            allowed=closed>=clock_time(18) or closed<=clock_time(15,45)
            trade=(net,mae,trade[2] if len(trade)>2 else None,allowed)
        by_day.setdefault(day, []).append(trade)
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


def summary(accounts, micros, payout_count=6):
    total = np.array([sum(v for _, v in a.payouts) for a in accounts])
    count = np.array([len(a.payouts) for a in accounts])
    days = np.array([a.day for a in accounts])
    first = np.array([a.payouts[0][0] for a in accounts if a.payouts])
    sixth = np.array([a.payouts[5][0] for a in accounts if len(a.payouts) == 6])
    n = len(accounts)
    result=dict(size=f'{micros} MNQ', sims=n, **{
        'E[payout]':float(total.mean()), 'SE':float(total.std(ddof=1)/np.sqrt(n)) if n>1 else 0.,
        'P(>=1 payout)':float((count>0).mean()), 'P(all 6)':float((count==6).mean()),
        'P(all)':float((count==payout_count).mean()),'payout_limit':payout_count,
        'avg payouts':float(count.mean()), 'blown':sum(a.outcome=='blown' for a in accounts)/n,
        'inactive':sum(a.outcome=='inactive' for a in accounts)/n, 'still open':sum(a.outcome=='open' for a in accounts)/n,
        'T1 median':float(np.median(first)) if len(first) else None,
        'T1 p75':float(np.percentile(first,75)) if len(first) else None,
        'T1 p90':float(np.percentile(first,90)) if len(first) else None,
        'T6 median':float(np.median(sixth)) if len(sixth) else None,
        'days alive':float(days.mean()), '$ per PA-day':float(total.mean()/days.mean()),
        'micros':micros, 'median life':float(np.median(total))})
    if accounts and hasattr(accounts[0],'withdrawals'):
        result['E[gross withdrawal]']=float(np.mean([sum(v for _,v in a.withdrawals) for a in accounts]))
    return result


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
        backend=account_backend(rules)
        account = backend.FundedAccount(rules) if backend else FundedAccount(rules)
        money.append((index, 0., cost * slots, slots))
        while index < len(grid):
            payout = account.advance(days[index], micros, max_micros,calendar_day=(grid[index]-grid[start]).days) if backend else account.advance(days[index], micros, max_micros)
            if payout:
                money.append((index,payout*slots,0.,0))
            index += 1
            if account.outcome != 'open':
                break
        records.append(dict(account=len(records)+1, start=str(grid[start].date()), end=str(grid[index-1].date()),
                            outcome=account.outcome, payouts=len(account.payouts),
                            payout_days=[str(grid[start+d-1].date()) for d,_ in account.payouts]))
        if backend:
            records[-1].update(gross_withdrawals=account.withdrawals,trader_receipts=account.payouts)
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



def _evaluation_size(value):
    days,size,block,max_micros=value[:4]
    sim=evaluation_model(days,size,3000,42,block,value[4],max_micros=max_micros) if len(value)>4 else evaluation(days,size,3000,42,block,max_micros=max_micros)
    return dict(micros=size,passed=int(sum(sim['outcomes']=='passed')),simulations=3000)


def _funded_size(value):
    days,size,block,rules,max_micros,economics=value
    backend=account_backend(rules);runner=backend.funded if backend else funded
    life=runner(days,size,3000,42,block,rules=rules,max_micros=max_micros)
    annual=runner(days,size,3000,42,block,horizon=261,rules=rules,max_micros=max_micros)
    stats={**summary(life,size,len(rules.ladder)),**annual_summary(annual)}
    stats.update(acquisition_cost=economics['cost_per_funded'], replacement_days=economics['replacement_days'], evaluation_pass_rate=economics['pass_rate'])
    stats['slot_year']=261*(stats['E[payout]']-stats['acquisition_cost'])/(stats['days alive']+stats['replacement_days'])
    return stats


def _funded_holdout(value):
    days,size,block,rules,max_micros,horizon=value
    backend=account_backend(rules)
    accounts=(backend.funded if backend else funded)(days,size,20000,43,block,horizon=horizon,rules=rules,max_micros=max_micros)
    if horizon==261:return dict(stats=annual_summary(accounts))
    return dict(stats=summary(accounts,size,len(rules.ladder)),outcomes=dict(never_paid=sum(not a.payouts for a in accounts)/20000,
        paid_partial=sum(0<len(a.payouts)<len(rules.ladder) for a in accounts)/20000,paid_all=sum(len(a.payouts)==len(rules.ladder) for a in accounts)/20000),
        distributions=dict(lifetime_totals=[sum(v for _,v in a.payouts) for a in accounts],payout_counts=[len(a.payouts) for a in accounts],
                           lifetimes=[a.day for a in accounts],first_payout_days=[a.payouts[0][0] for a in accounts if a.payouts]))


def training_economics(train, selected, settings, block, max_micros, sample):
    """Freeze acquisition inputs from training only, before holdout is touched."""
    probability=selected['passed']/selected['simulations']
    result=dict(method='training_simulation',status='unavailable',sample=sample,
                evaluation_micros=selected['micros'],passed=selected['passed'],
                simulations=selected['simulations'],pass_rate=probability,
                pass_rate_ci=wilson(selected['passed'],selected['simulations']),
                evaluation_seed=42,funding_chain_seed=45,funding_chain_simulations=0,requested_funding_chain_simulations=20000,
                evaluation_price=float(settings['EVAL_PRICE']),activation_fee=float(settings['ACTIVATION_FEE']),
                activation_days=0 if is_lucid(settings) else 1,cost_per_funded=None,replacement_days=None,
                source='Training evaluation sweep and repeated funding chains only; frozen before all holdout simulations')
    if not selected['passed']:
        result['reason']='No training evaluation passed. Acquisition cost and replacement time cannot be calibrated; funded sizing is unavailable.'
        return result
    result.update(cost_per_funded=float(settings['EVAL_PRICE'])/probability+float(settings['ACTIVATION_FEE']),
                  evaluations_per_funded=1/probability)
    try:
        chain=evaluation_model(train,selected['micros'],20000,45,block,settings,chain=True,max_micros=max_micros)
    except ValueError as exc:
        if not str(exc).startswith(('No pass within the 10,000-attempt funding-time bound','LucidFlex funding chain is censored')):raise
        result['reason']='Training funding time is unavailable: '+str(exc)
        return result
    result.update(status='calibrated',funding_chain_simulations=20000,replacement_days=float(chain['days'].mean()),
                  replacement_days_median=float(np.median(chain['days'])))
    return result


def calculate(rows, settings, progress=lambda _:None):
    grid, days, split = day_book(rows,settings)
    if split==0:
        raise ValueError('At least two session weekdays are needed for separate training and validation; no history is fabricated.')
    days=compact_neutral_runs(days)
    train, validation = days[:split],days[split:]
    block = int(settings['BLOCK_DAYS']); max_micros = int(round(float(settings['MAX_TOTAL_NQ'])*10))
    if is_lucid(settings):
        from .lucid_backend import Rules as LucidRules
        rules=LucidRules(daily_loss=1200. if settings['DAILY_LOSS_LIMIT']=='on' else None)
    else:rules = replace(Rules(),approval_day_counts=settings['APPROVAL_DAY_COUNTS'])
    samples=dict(data=[str(grid[0].date()),str(grid[-1].date())],
                 train=[str(grid[0].date()),str(grid[split-1].date())],
                 validation=[str(grid[split].date()),str(grid[-1].date())],weekdays=[split,len(validation)])
    progress('Local evaluation sizing on training sessions')
    sizes=list(range(1,min(40 if is_lucid(settings) else 60,max_micros)+1))
    work=sum(map(len,train))*3000
    evaluation_sweep=map_sweep(_evaluation_size,[(train,size,block,max_micros,settings) if is_lucid(settings) else (train,size,block,max_micros) for size in sizes],work*len(sizes))
    selected=max(evaluation_sweep,key=lambda r:r['passed'])
    progress('Local training acquisition calibration: 20,000 funding chains')
    economics=training_economics(train,selected,settings,block,max_micros,samples['train'])
    sweep=None;size=None;funded_sizes=None
    if economics['status']=='calibrated':
        progress('Local funded sizing with frozen training acquisition economics')
        funded_sizes=list(range(1,min(max(level[1] for level in rules.levels),max_micros)+1))
        sweep=map_sweep(_funded_size,[(train,n,block,rules,max_micros,economics) for n in funded_sizes],work*len(funded_sizes)*2*(2000 if is_lucid(settings) else 1))
        size=max(sweep,key=lambda r:r['slot_year'])['micros']
    # Evaluation size, funded size and acquisition inputs are now fixed. Holdout
    # results can neither rescore candidates nor gate a successful training fit.
    progress('Local holdout evaluation: 20,000 paths')
    sim=evaluation_model(validation,selected['micros'],20000,43,block,settings,max_micros=max_micros)
    outcomes=sim['outcomes']; passed=int(sum(outcomes=='passed')); probability=passed/20000
    result=dict(model_version=model_version(settings),rules=asdict(rules),settings=settings,samples=samples,
                seeds=dict(training=42,holdout=43,funding_chain=44,training_funding_chain=45,generator='MT19937 / RandomState bounded integers',block_days=block),
                training_economics=economics,
                evaluation=dict(selected_micros=selected['micros'],simulations=20000,passed=passed,pass_rate=probability,
                                fail_drawdown=float((outcomes=='blown').mean()),timeout=float((outcomes=='timeout').mean()),
                                pass_rate_ci=wilson(passed,20000),cost_per_funded=None,evaluations_per_funded=None,
                                days_to_funded=None,days_to_funded_median=None,
                                median_days_to_pass=float(np.median(sim['days'][outcomes=='passed'])) if passed else None),
                evaluation_sweep=evaluation_sweep)
    if is_lucid(settings):
        from .lucid_rules import CONTRACT
        result['provider_contract']=CONTRACT
        result['evaluation'].update(inactivity=float((outcomes=='inactive').mean()),censored=float((outcomes=='timeout').mean()),
            horizon_weekdays=2000,provider_deadline=None)
    if passed:
        result['evaluation'].update(cost_per_funded=float(settings['EVAL_PRICE'])/probability+float(settings['ACTIVATION_FEE']),
                                    evaluations_per_funded=1/probability)
        try:
            chain=evaluation_model(validation,selected['micros'],20000,44,block,settings,chain=True,max_micros=max_micros)
        except ValueError as exc:
            if not str(exc).startswith(('No pass within the 10,000-attempt funding-time bound','LucidFlex funding chain is censored')):raise
            result['evaluation']['timing_unavailable']=str(exc)
        else:
            result['evaluation'].update(days_to_funded=float(chain['days'].mean()),days_to_funded_median=float(np.median(chain['days'])))
    else:
        result['evaluation']['unavailable']='No validation evaluation passed. Holdout acquisition cost and funding time are unavailable; training selection remains frozen.'
    if sweep is None:
        reason=economics['reason']
        if not passed:reason+=' No validation evaluation passed either.'
        result.update(funded=None,history=None,unavailable=reason)
        return result
    progress('Local funded holdout: 20,000 lifetime and 20,000 first-year accounts')
    life,annual=map_sweep(_funded_holdout,[(validation,size,block,rules,max_micros,horizon) for horizon in (2000,261)],sum(map(len,validation))*20000*2)
    stats={**life['stats'],**annual['stats']}
    result['funded']=dict(selected=stats,sweep=sweep,search_range=dict(min_micros=1,max_micros=funded_sizes[-1],step=1,selected_at_limit=size==funded_sizes[-1],permitted_micros=max(level[1] for level in rules.levels),user_cap_micros=max_micros,tier_caps=[level[1] for level in rules.levels]),selection_economics=economics,
        outcomes=life['outcomes'])
    progress('Local chronological replay with frozen training acquisition economics')
    result['history']=replay_history(grid,days,size,economics['replacement_days'],economics['cost_per_funded'],int(settings['SLOTS']),rules,max_micros,split)
    result['history']['acquisition_economics']=dict(source='training',cost_per_funded=economics['cost_per_funded'],replacement_days=economics['replacement_days'])
    result['distributions']={**life['distributions'],'evaluation_days':sim['days'].tolist()}
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
        outcomes=result['funded']['outcomes'];labels=['No payout','Partial ladder',f'All {len(result["rules"]["ladder"])} payouts'];values=list(outcomes.values())
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
    if snapshot.get('native_risk'):
        copied=inputs/'intratrade_risk.csv'
        shutil.copyfile(runs.root/request['source_backtest_id']/'intratrade_risk.csv',copied)
        if digest(copied)!=snapshot['native_risk']['sha256']:raise ValueError('Native risk changed before capture.')
    if export['path']:
        copied=inputs/export['filename'];shutil.copyfile(export['path'],copied)
        if digest(copied)!=export['sha256']:raise ValueError('Excursion export changed before capture.')
    (inputs/'settings.json').write_text(json.dumps(settings,indent=2))
    if is_lucid(settings):
        from .lucid_rules import CONTRACT
        (staged/'provider_rules.json').write_text(json.dumps(CONTRACT,indent=2))
    from .calculation_cache import calculate as cached_calculate
    result,reused_from,calculation_key=cached_calculate(rows,settings,snapshot,progress,calculate)
    if digest(runs.root/request['source_backtest_id']/'trades.csv')!=snapshot['trades_sha256']:
        raise ValueError('Native source changed during calculation.')
    if snapshot.get('native_risk') and digest(runs.root/request['source_backtest_id']/'intratrade_risk.csv')!=snapshot['native_risk']['sha256']:
        raise ValueError('Native risk changed during calculation.')
    if export['path'] and digest(export['path'])!=export['sha256']:
        raise ValueError('Excursion export changed during calculation.')
    (staged/'trades.csv').write_text(csv_text(rows))
    (staged/'commission_reconciliation.json').write_text(json.dumps(snapshot['commission_simulation'],indent=2,allow_nan=False))
    (staged/'evaluation_sizing.csv').write_text(csv_text(result['evaluation_sweep']))
    (staged/'training_economics.json').write_text(json.dumps(result['training_economics'],indent=2,allow_nan=False))
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
    return dict(format_version=3,model_version=model_version(settings),source=snapshot,settings=settings,calculations=result,
                calculation_contract='AlphaQuest local account transitions, random sampling, sizing, economics and charts; no external calculation engine or externally generated result inputs; verified local calculation reuse is recorded.',
                runtime=dict(python=platform.python_version(),numpy=np.__version__,pandas=pd.__version__,native_kernel=kernel_identity(settings),prop_execution=execution_diagnostics(),calculation_key=calculation_key,calculation_reused_from=reused_from),
                application_commit=commit,implementation_sha256={p.name:digest(p) for p in Path(__file__).parent.glob('*.py')})
