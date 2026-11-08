"""Fixed phase selections on one observed dated timeline (portfolio milestone 1).

Uses the same evaluation-session and funded-account transitions as the sampled
models. No sampling, expected acquisition charges, annualization or budget is
substituted for the observed lifecycle. All outputs use the ordinary report store.
"""
from dataclasses import asdict, replace
from datetime import datetime, timedelta, time, timezone
from decimal import Decimal
import json
import platform
from pathlib import Path
import shutil
from zoneinfo import ZoneInfo

import pandas as pd

from .adapter import canonical, digest

PHASE_DEFAULTS = dict(ANALYSIS_MODE='dated_lifecycle', EVALUATION_MICROS='10',
                      FUNDED_MICROS='3', ACTIVATION_WAIT_WEEKDAYS='')
CHICAGO = ZoneInfo('America/Chicago')


def resolve_phase_settings(settings):
    if settings.get('ANALYSIS_MODE') not in ('dated_lifecycle', 'budgeted_lifecycle'):
        raise ValueError('Phase settings require ANALYSIS_MODE=dated_lifecycle; omit phase settings for annualized analysis.')
    result = {**PHASE_DEFAULTS, **settings}
    lucid = result.get('ACCOUNT_TYPE') == 'LucidFlex'
    for key, upper in [('EVALUATION_MICROS', 40 if lucid else 60), ('FUNDED_MICROS', 40)]:
        value = result[key]
        if not isinstance(value, str) or not value.isascii() or not value.isdigit() or not 1 <= int(value) <= upper:
            raise ValueError(f'{key} must be a whole MNQ size from 1 to {upper}.')
        try: cap = Decimal(result.get('MAX_TOTAL_NQ', '4')) * 10
        except Exception as exc: raise ValueError('Invalid MAX_TOTAL_NQ.') from exc
        if not cap.is_finite() or int(value) > cap:
            raise ValueError(f'{key} exceeds the total NQ exposure cap.')
    delay = result['ACTIVATION_WAIT_WEEKDAYS']
    minimum = 0 if lucid else 1
    if delay != '' and (not isinstance(delay, str) or not delay.isascii() or not delay.isdigit() or not minimum <= int(delay) <= 261):
        raise ValueError(f'ACTIVATION_WAIT_WEEKDAYS must be blank or {minimum}–261; provider minimum cannot be shortened.')
    return result


def dated(request):
    return request.get('settings', {}).get('ANALYSIS_MODE') in ('dated_lifecycle', 'budgeted_lifecycle')


def source_snapshots(snapshot):
    return snapshot.get('phase_sources', {'evaluation': snapshot}).values()


def prepare_request(runs, request):
    from .native_analysis import prepare
    if not dated(request):
        if request.get('funded_source_backtest_id') or request.get('funded_trade_file'):
            raise ValueError('Select dated_lifecycle to configure a funded phase source.')
        return prepare(runs, request['source_backtest_id'], request.get('trade_file'),
                       request.get('settings'), request.get('export_timezone', 'America/Chicago'))
    settings = request.get('settings') or {}
    source_id = request['source_backtest_id']
    funded_id = request.get('funded_source_backtest_id') or source_id
    inherits_export = not request.get('funded_trade_file') and funded_id == source_id
    snapshots, rows = {}, {}
    for phase, id, path, zone in [
        ('evaluation', source_id, request.get('trade_file') or '', request.get('export_timezone', 'America/Chicago')),
        ('funded', funded_id,
         request.get('funded_trade_file') or (request.get('trade_file') or '' if funded_id == source_id else ''),
         request.get('export_timezone', 'America/Chicago') if inherits_export else
         request.get('funded_export_timezone') or request.get('export_timezone', 'America/Chicago'))]:
        try:
            snap, trades, resolved = prepare(runs, id, path, settings, zone)
            validate_phase_source(snap, trades)
        except (ValueError, OSError, KeyError) as exc:
            raise ValueError(f'{phase.capitalize()} source incompatible: {exc}') from exc
        snapshots[phase], rows[phase] = snap, trades
    a, b = [s['backtest'] for s in snapshots.values()]
    phases = [r['run_metadata'].get('research', {}).get('phase') for r in (a,b)]
    if phases[0] not in ('is','oos') or phases[0] != phases[1]:
        raise ValueError('Both phase sources must use the same declared research phase (IS with IS, or manually executed OOS with OOS).')
    start = max(instant(r['period_start_utc']) for r in (a,b))
    end = min(instant(r['period_end_utc']) for r in (a,b))
    if start >= end:
        raise ValueError('Phase sources have no common research window.')
    calendars = [r['run_metadata']['strategy'].get('session_flattening', {}).get('calendar') for r in (a,b)]
    if all(calendars) and calendars[0] != calendars[1]:
        raise ValueError('Phase source calendars differ; use the same versioned calendar snapshot.')
    # Check explicit declarations too: a selected IS source must not consume
    # dates declared as OOS by its companion, even under different saved plans.
    for record in (a,b):
        research = record['run_metadata']['research']
        plan = research['plan']; prefix = research['phase']
        zone = ZoneInfo(plan['source_timezone'])
        if not (plan[prefix+'_start'] <= start.astimezone(zone).date().isoformat()
                <= end.astimezone(zone).date().isoformat() <= plan[prefix+'_end']):
            raise ValueError('Common window lies outside a source research declaration.')
    grid = pd.bdate_range(session_date(start), session_date(end))
    if not 2 <= len(grid) <= 20000:
        raise ValueError('Common window requires 2–20,000 session weekdays.')
    checks = dict(start_utc=start.isoformat(), end_utc=end.isoformat(),
        first_session=str(grid[0].date()), last_session=str(grid[-1].date()), weekdays=len(grid),
        research_phase=phases[0], calendar='CME Chicago session dates; zero-trade weekdays including holidays retained',
        source_calendars=calendars, scaling='Fixed-quantity strategy paths only; normalize source exposure once to MNQ. Fixed phase targets remain subject to provider tiers.',
        activation_clock='Weekdays after the passing session; eligibility at session close, funded observations from the following session. No bank-settlement or monthly-budget forecast.')
    for phase in rows:
        selected = [r for r in rows[phase] if start <= instant(r['entry_utc']) and instant(r['exit_utc']) <= end]
        if not selected: raise ValueError(f'{phase.capitalize()} source has no complete trades in the common research window.')
        checks[phase+'_included_trades'] = len(selected)
        checks[phase+'_excluded_trades'] = len(rows[phase])-len(selected)
    # Keep the established primary source shape for existing report routing.
    snapshot = {**snapshots['evaluation'], 'phase_sources': snapshots, 'phase_checks': checks}
    if resolved['ANALYSIS_MODE'] == 'budgeted_lifecycle':
        from .cash_ledger import check_window
        check_window(checks, resolved)
        checks['cash_policy'] = 'One unfunded slot; activation-priority reservation; exact monthly cap independent of receipts. Saved settlement/deadline assumptions apply.'
    return snapshot, rows, resolved


def instant(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError('Source timestamps require an explicit timezone offset.')
    return result


def session_date(value):
    return (value.astimezone(CHICAGO).replace(tzinfo=None)+timedelta(hours=7)).date()


def session_open(day):
    return datetime.combine(day-timedelta(days=1), time(17), CHICAGO).astimezone(timezone.utc)


def validate_phase_source(snapshot, rows):
    from .commissions import source_instrument
    record = snapshot['backtest']; strategy = record['run_metadata']['strategy']
    if not (source_instrument(record) or snapshot['commission_simulation']['source_instrument']):
        raise ValueError('Dated phases require an identified NQ/MNQ instrument and matching USD point value.')
    params = strategy['parameters']
    if strategy['id'] not in ('consecutive_green_hold','vwap_pullback_risk_sizing') or params.get('use_vol_sizing'):
        raise ValueError('Source strategy is unsuitable for fixed size scaling; use fixed contracts, without account/risk-budget-dependent sizing.')
    for row in rows:
        if session_date(instant(row['entry_utc'])) != session_date(instant(row['exit_utc'])):
            raise ValueError('A phase source must be intraday flat; overnight risk and an inherited position cannot be reconstructed.')
        if row.get('ohlc_mae_upper') is None and row.get('measured_mae') is None:
            raise ValueError('Complete intratrade risk coverage is required in both phases; close-only fallback cannot qualify a dated lifecycle.')
    snapshot['phase_suitability'] = dict(fixed_quantity=True, instrument=snapshot['commission_simulation']['source_instrument'],
        risk_covered_trades=len(rows), scaling='Linear MNQ exposure scenario on a saved fixed-quantity path; liquidity/size-dependent fills are not resimulated.')


def replay(snapshot, rows, settings):
    from .native_analysis import day_book, is_lucid, model_version
    from . import native_engine as apex, lucid_engine as lucid
    lucid_model = is_lucid(settings)
    rules = lucid.Rules(daily_loss=1200. if settings['DAILY_LOSS_LIMIT']=='on' else None) if lucid_model else replace(apex.Rules(), approval_day_counts=settings['APPROVAL_DAY_COUNTS'])
    checks = snapshot['phase_checks']
    start, end = instant(checks['start_utc']), instant(checks['end_utc'])
    grid = pd.bdate_range(checks['first_session'], checks['last_session'])
    books, identities = {}, {}
    for phase, trades in rows.items():
        selected = sorted([r for r in trades if start <= instant(r['entry_utc']) and instant(r['exit_utc']) <= end],
                          key=lambda r:(r['entry_utc'],int(r['trade_id'])))
        # Reuse exactly the commission/risk/day adaptation of annualized analysis.
        phase_grid, days, _ = day_book(selected, {**settings,'OUT_OF_SAMPLE_FROM':''})
        books[phase] = {d.date():day for d,day in zip(phase_grid,days)}
        identities[phase] = {}
        for r in selected: identities[phase].setdefault(session_date(instant(r['entry_utc'])),[]).append(r)
    trace = []; evaluation_size = int(settings['EVALUATION_MICROS']); funded_size = int(settings['FUNDED_MICROS'])
    cap = int(Decimal(settings['MAX_TOTAL_NQ'])*10)
    delay = int(settings['ACTIVATION_WAIT_WEEKDAYS'] or (0 if lucid_model else 1))
    metrics = {phase:dict(sessions=0,trades_consumed=0,daily_stops=0,account_breaches=0) for phase in rows}
    phase = 'evaluation'; equity=high=best=0.;last_activity=0;elapsed=0;account=None
    activation_index=None; funded_start=None; pass_date=None
    terminal = None; activated=False
    for index, stamp in enumerate(grid):
        day=stamp.date(); events=[]
        if phase == 'activation':
            if index <= activation_index:
                if index == activation_index:
                    events.append('activation_eligible');activated=True
                trace.append(dict(date=str(day),phase='activation',event=';'.join(events) or 'activation_wait',equity=0.,trader_payout=0.,source_id=None))
                continue
            phase='funded';funded_start=day
            account=(lucid.FundedAccount(rules) if lucid_model else apex.FundedAccount(rules))
            events.append('funded_started')
        if phase == 'complete':break
        trades=books[phase].get(day,[]);ids=identities[phase].get(day,[])
        # Only positions opened after this account became eligible are usable.
        # Sources are session-flat and start/end clipping already removes carries.
        opening=equity; hit=consumed=0; payout=0.;gross=0.
        if phase == 'evaluation':
            if index == 0: events.append('evaluation_started')
            elapsed+=1
            if lucid_model:
                equity,high,best,last_activity,outcome,hit,consumed=lucid.evaluation_session(trades,equity,high,best,last_activity,(day-grid[0].date()).days,min(evaluation_size,40,cap),rules.daily_loss)
            else:
                equity,high,outcome,hit,consumed=apex.evaluation_session(trades,equity,high,min(evaluation_size,60,cap))
                if outcome=='open' and elapsed>=21:outcome='expired'
            effective=min(evaluation_size,40 if lucid_model else 60,cap)
        else:
            opening=account.equity
            payout=account.advance(trades,funded_size,cap,calendar_day=(day-funded_start).days) if lucid_model else account.advance(trades,funded_size,cap)
            equity=account.equity;hit=account.last_hit;consumed=account.trades_consumed;effective=account.effective_micros
            gross=account.withdrawals[-1][1] if payout and lucid_model else payout
            outcome=account.outcome
        current=phase; m=metrics[current];m['sessions']+=1;m['trades_consumed']+=consumed
        if hit:
            event='account_breach' if hit==2 else 'daily_stop'
            events.append(event);m['account_breaches' if hit==2 else 'daily_stops']+=1
        if payout:events.append('payout_requested')
        if outcome=='passed':
            events.append('evaluation_passed');pass_date=str(day);activation_index=index+delay
            if delay==0:events.append('activation_eligible');activated=True
            phase='activation'
        elif outcome in ('blown','expired','inactive','paid_all'):
            terminal={'blown':'account_breach','expired':'evaluation_expired','inactive':'inactivity_expired','paid_all':'funded_payout_limit'}[outcome]
            if terminal not in events:events.append(terminal)
            phase='complete'
        trace.append(dict(date=str(day),session_open_utc=session_open(day).isoformat(),phase=current,
            event=';'.join(events) or 'trading',source_id=snapshot['phase_sources'][current]['backtest']['id'],
            target_micros=evaluation_size if current=='evaluation' else funded_size,effective_micros=effective,
            opening_equity=opening,equity=equity,outcome=outcome,first_limit_hit={0:'none',1:'daily_stop',2:'account_breach'}[hit],
            source_trade_ids=[r['trade_id'] for r in ids[:consumed]],trades_consumed=consumed,
            unconsumed_trades=len(trades)-consumed,trader_payout=payout,gross_withdrawal=gross))
        if current=='evaluation' and outcome=='passed':equity=0.
    if terminal is None:
        terminal = 'activation_pending' if phase=='activation' else 'evaluation_unresolved' if phase=='evaluation' else 'funded_open'
    metrics['evaluation'].update(outcome='passed' if pass_date else terminal,pass_date=pass_date,target_micros=evaluation_size)
    metrics['funded'].update(outcome=terminal if funded_start else 'not_started',start_date=str(funded_start) if funded_start else None,
        target_micros=funded_size,trader_payouts=sum(t['trader_payout'] for t in trace),gross_withdrawals=sum(t.get('gross_withdrawal',0.) for t in trace))
    eligible = str((pd.Timestamp(pass_date)+pd.offsets.BDay(delay)).date()) if pass_date else None
    return dict(model_version=model_version(settings),
        analysis_mode='dated_lifecycle',rules=asdict(rules),source_checks=checks,phase_metrics=metrics,
        activation=dict(wait_weekdays=delay,eligible_session=eligible,activated_in_window=activated,funded_start_session=str(funded_start) if funded_start else None),
        outcome=terminal,trace=trace,history=None,
        assumptions=['One evaluation and its subsequent funded account; no automatic repurchase or slot multiplication.',
            'Observed common history, fixed phase targets subject to mandatory provider scaling. No restarted source history or inherited position.',
            'Eligibility is model-based at session close after the configured weekday delay, not proof of provider approval.',
            'Payouts are dated requests/account deductions and trader entitlements, not bank receipts. Exact cash ledger, monthly spending cap, forecasts and portfolio optimization arrive in milestones 2–5.',
            'Existing annualized mode uses training acquisition estimates, annual renewal and acquired-funded-start history; those assumptions are not this dated replay.',
            'Conservative held OHLC risk or reconciled measured MAE; no tick-order or complete provider/Bridge parity claim.'])


def run_analysis(runs, request, staged, progress):
    from .native_analysis import csv_text, model_version
    snapshot, rows, settings = prepare_request(runs,request)
    progress('Local budgeted purchases → evaluation → paid activation → funded trading → modeled receipts' if settings['ANALYSIS_MODE']=='budgeted_lifecycle' else 'Local dated evaluation → activation eligibility → subsequent funded observations')
    for phase, snap in snapshot['phase_sources'].items():
        directory=staged/'inputs'/phase;directory.mkdir(parents=True)
        source_id=snap['backtest']['id']
        shutil.copyfile(runs.root/source_id/'trades.csv', directory/'source_trades.csv')
        if digest(directory/'source_trades.csv')!=snap['trades_sha256']:raise ValueError(f'{phase} source changed before capture.')
        if snap.get('native_risk'):
            shutil.copyfile(runs.root/source_id/'intratrade_risk.csv',directory/'intratrade_risk.csv')
            if digest(directory/'intratrade_risk.csv')!=snap['native_risk']['sha256']:raise ValueError(f'{phase} risk changed before capture.')
        export=snap['excursion_input']
        if export['path']:
            shutil.copyfile(export['path'],directory/export['filename'])
            if digest(directory/export['filename'])!=export['sha256']:raise ValueError(f'{phase} export changed before capture.')
        (staged/(phase+'_trades.csv')).write_text(csv_text(rows[phase]))
        (directory/'source.json').write_text(canonical(snap))
    if settings['ANALYSIS_MODE'] == 'budgeted_lifecycle':
        from .cash_ledger import replay as cash_replay
        result = cash_replay(snapshot, rows, settings)
        for name in ('cash_ledger', 'monthly_ledger', 'accounts', 'pending_receipts'):
            (staged/(name+'.json')).write_text(canonical(result[name]))
            (staged/(name+'.csv')).write_text(csv_text(result[name]))
    else:
        result=replay(snapshot,rows,settings)
    after,_,_=prepare_request(runs,request)
    if canonical(after)!=canonical(snapshot):raise ValueError('A phase source changed during calculation.')
    (staged/'trades.csv').write_text(csv_text(rows['evaluation']))
    (staged/'transition_trace.csv').write_text(csv_text([{**t,'source_trade_ids':json.dumps(t.get('source_trade_ids',[]))} for t in result['trace']]))
    (staged/'transition_trace.json').write_text(canonical(result['trace']))
    (staged/'phase_metrics.json').write_text(canonical(result['phase_metrics']))
    (staged/'commission_reconciliation.json').write_text(canonical({p:s['commission_simulation'] for p,s in snapshot['phase_sources'].items()}))
    (staged/'inputs'/'settings.json').write_text(canonical(settings))
    (staged/'calculations.json').write_text(canonical(result))
    return dict(format_version=3,model_version=model_version(settings),source=snapshot,settings=settings,calculations=result,
        calculation_contract='AlphaQuest local dated phase replay; shared account transitions; no external generated inputs.',
        runtime=dict(python=platform.python_version(),pandas=pd.__version__,calculation_backend='Python session reference'),
        implementation_sha256={p.name:digest(p) for p in Path(__file__).parent.glob('*.py')})


def check_frozen_pairs(datasets, runs, campaigns, request):
    """Additive downstream comparison of already frozen independent policies."""
    from .frozen_pairs import check_frozen_pairs as check
    return check(datasets, runs, campaigns, request)


def run_frozen_pairs(datasets, runs, campaigns, request, checked, **options):
    from .frozen_pairs import run_frozen_pairs as run
    return run(datasets, runs, campaigns, request, checked, **options)
