"""Exact dated acquisition cash on one observed path, one initially empty slot.

Trading transitions are the existing firm kernels. Decimal cash is separate from
trading equity. No expected acquisition charges, bank feed or terminal valuation.
"""
from dataclasses import asdict, replace
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import heapq
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

from .phase_lifecycle import CHICAGO, instant, session_date

CASH_DEFAULTS = dict(MONTHLY_CAP='', BUDGET_TIMEZONE='', START_DATE='', HORIZON_END='',
    PAYOUT_RECEIPT_DAYS='', PAYOUT_TIMING_ASSUMPTION='', ACTIVATION_DEADLINE_DAYS='',
    ACTIVATION_PAYMENT_DELAY_DAYS='0', ACTIVATION_TIMING_ASSUMPTION='', FEE_OVERRIDE_NOTE='')
ZERO = Decimal('0.00')
UTC = timezone.utc


def cash(value):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError('Cash values must be finite nonnegative USD cents.') from exc
    if not result.is_finite() or not ZERO <= result <= 100000 or result != result.quantize(Decimal('.01')):
        raise ValueError('Cash values must be finite nonnegative USD cents, at most 100000.')
    return result.quantize(Decimal('.01'))


def resolve_cash_settings(settings):
    if settings.get('ANALYSIS_MODE') != 'budgeted_lifecycle':
        raise ValueError('Cash settings require ANALYSIS_MODE=budgeted_lifecycle.')
    result = {**CASH_DEFAULTS, **settings}
    for key in ('MONTHLY_CAP', 'EVAL_PRICE', 'ACTIVATION_FEE'):
        if not isinstance(result[key], str):
            raise ValueError(f'{key} must be a USD string.')
        result[key] = str(cash(result[key]))
    try:
        if not isinstance(result['BUDGET_TIMEZONE'], str): raise ValueError()
        ZoneInfo(result['BUDGET_TIMEZONE'])
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError('BUDGET_TIMEZONE must name an explicit IANA timezone.') from exc
    try:
        start, end = [date.fromisoformat(result[k]) for k in ('START_DATE', 'HORIZON_END')]
        if any(result[k] != d.isoformat() for k, d in zip(('START_DATE','HORIZON_END'), (start,end))): raise ValueError()
        if not 0 <= (end-start).days <= 7300: raise ValueError()
    except (TypeError, ValueError) as exc:
        raise ValueError('START_DATE and inclusive HORIZON_END need ISO dates spanning 0–7300 days.') from exc
    for key, lower in [('PAYOUT_RECEIPT_DAYS',0), ('ACTIVATION_DEADLINE_DAYS',1), ('ACTIVATION_PAYMENT_DELAY_DAYS',0)]:
        value = result[key]
        if not isinstance(value, str) or not value.isascii() or not value.isdigit() or not lower <= int(value) <= 366:
            raise ValueError(f'{key} must be a saved whole calendar-day assumption from {lower} to 366.')
    for key in ('PAYOUT_TIMING_ASSUMPTION','ACTIVATION_TIMING_ASSUMPTION'):
        value = result[key]
        if not isinstance(value,str) or not value.strip() or len(value)>1000:
            raise ValueError(f'{key} is required: describe the unverified modeling assumption (1–1000 characters).')
    if not isinstance(result['FEE_OVERRIDE_NOTE'],str) or len(result['FEE_OVERRIDE_NOTE'])>1000:
        raise ValueError('FEE_OVERRIDE_NOTE must contain at most 1000 characters.')
    if result['SLOTS'] != '1':
        raise ValueError('Budgeted lifecycle initially supports exactly SLOTS=1, starting unfunded.')
    if result['OUT_OF_SAMPLE_FROM']:
        raise ValueError('Budgeted replay uses the declared common observed window; omit internal holdout start.')
    return result


def check_window(checks, settings):
    # No extrapolation past observed sources or restart before their shared window.
    if settings['START_DATE'] < checks['first_session'] or settings['HORIZON_END'] > checks['last_session']:
        raise ValueError('Budget horizon must lie within the common observed session-date window; future trading outcomes are unavailable.')


def replay(snapshot, rows, settings):
    from .native_analysis import day_book, is_lucid, model_version
    from . import native_engine as apex, lucid_engine as lucid
    is_lucid_model = is_lucid(settings)
    rules = (lucid.Rules(daily_loss=1200. if settings['DAILY_LOSS_LIMIT']=='on' else None)
             if is_lucid_model else replace(apex.Rules(), approval_day_counts=settings['APPROVAL_DAY_COUNTS']))
    zone = ZoneInfo(settings['BUDGET_TIMEZONE'])
    start_day, end_day = [date.fromisoformat(settings[k]) for k in ('START_DATE','HORIZON_END')]
    local_midnight = lambda d: datetime.combine(d,time(),zone).astimezone(UTC)
    start, end = local_midnight(start_day), local_midnight(end_day+timedelta(days=1))
    cap, evaluation_fee, activation_fee = [cash(settings[k]) for k in ('MONTHLY_CAP','EVAL_PRICE','ACTIVATION_FEE')]
    evaluation_size, funded_size = [int(settings[k]) for k in ('EVALUATION_MICROS','FUNDED_MICROS')]
    exposure_cap = int(Decimal(settings['MAX_TOTAL_NQ'])*10)
    wait = int(settings['ACTIVATION_WAIT_WEEKDAYS'] or (0 if is_lucid_model else 1))
    checks = snapshot['phase_checks']; check_window(checks,settings)
    common_start, common_end = [instant(checks[k]) for k in ('start_utc','end_utc')]
    books, identities = {}, {}
    for phase, trades in rows.items():
        selected = sorted((r for r in trades if common_start <= instant(r['entry_utc']) and instant(r['exit_utc']) <= common_end),
                          key=lambda r:(r['entry_utc'],int(r['trade_id'])))
        grid, days, _ = day_book(selected,{**settings,'OUT_OF_SAMPLE_FROM':''})
        books[phase] = {d.date():v for d,v in zip(grid,days)}
        identities[phase] = {}
        for row in selected: identities[phase].setdefault(session_date(instant(row['entry_utc'])),[]).append(row)
    queue=[]; sequence=0
    def enqueue(at, priority, kind, payload=None):
        nonlocal sequence
        at=at.astimezone(UTC)
        if start <= at < end:
            sequence+=1;heapq.heappush(queue,(at,priority,sequence,kind,payload))
    day=start_day
    while day <= end_day:
        enqueue(local_midnight(day),0,'month' if day==start_day or day.day==1 else 'tick')
        day+=timedelta(days=1)
    for stamp in pd.bdate_range(checks['first_session'],checks['last_session']):
        # Existing daily firm transitions settle at modeled Chicago session close.
        enqueue(datetime.combine(stamp.date(),time(16),CHICAGO),3,'session',stamp.date())
    ledger=[]; trace=[]; accounts=[]; receipts=[]; months={}
    active=None; reserved=ZERO; spent=ZERO; received=ZERO; eval_total=ZERO; activation_total=ZERO; month=None
    metrics={p:dict(sessions=0,trades_consumed=0,daily_stops=0,account_breaches=0) for p in rows}
    def emit(at, event, *, expense=ZERO, receipt=ZERO, reservation=ZERO, amount=ZERO, reason='', account=None, **extra):
        # All monetary columns use exact decimal strings; trading equity never enters cash.
        if not (ZERO <= spent <= cap and ZERO <= reserved <= cap-spent):
            raise ValueError('Cash invariant failed: paid fees or reservations exceed the monthly cap; no report published.')
        ledger.append(dict(sequence=len(ledger)+1,timestamp_utc=at.astimezone(UTC).isoformat(),
            timestamp_budget=at.astimezone(zone).isoformat(),month=month,event=event,
            account=account if account is not None else (active['account'] if active else None),
            amount=str(amount),paid_fee=str(expense),trader_receipt=str(receipt),
            cash_delta=str(receipt-expense),reservation_delta=str(reservation),
            paid_this_month=str(spent),remaining_allowance=str(cap-spent),reserved_allowance=str(reserved),
            available_for_purchase=str(cap-spent-reserved),net_cash_to_date=str(received-eval_total-activation_total),
            reason=reason,**extra))
    def release(at,reason):
        nonlocal reserved
        amount=reserved;reserved=ZERO
        emit(at,'reservation_released',amount=amount,reservation=-amount,reason=reason)
    def close(at,outcome):
        nonlocal active
        active['outcome']=outcome;active['closed_at']=at.isoformat()
        emit(at,'failed_attempt' if active['phase']=='evaluation' else 'account_closed',reason=outcome)
        if reserved:release(at,outcome)
        active=None
    def purchase(at):
        nonlocal active,spent,reserved,eval_total
        if active is not None:return
        if cap-spent < evaluation_fee+activation_fee:
            emit(at,'purchase_blocked',amount=evaluation_fee,reason='Monthly allowance cannot cover evaluation plus activation reservation; deferred until a later scheduler tick.')
            return
        number=len(accounts)+1
        if number>1:emit(at,'account_replacement',account=number,reason='Prior attempt/account closed; new purchase uses subsequent observations only.')
        active=dict(account=number,phase='evaluation',purchased_at=at.isoformat(),outcome='evaluation_open',
                    equity=0.,high=0.,best=0.,last_activity=0,sessions=0,first_session=None,
                    passed_on=None,eligible_at=None,activation_deadline=None,activated_at=None,funded_start=None)
        accounts.append(active)
        spent+=evaluation_fee;eval_total+=evaluation_fee
        emit(at,'evaluation_purchase',amount=evaluation_fee,expense=evaluation_fee,reason='Actual saved evaluation price; no expected acquisition charge.')
        reserved=activation_fee
        emit(at,'activation_reserved',amount=activation_fee,reservation=activation_fee,reason='Activation priority: earmark potential obligation before trading this evaluation.')
    while queue:
        at,_,_,kind,payload=heapq.heappop(queue)
        local=at.astimezone(zone); key=local.strftime('%Y-%m')
        # A reset is a calendar boundary in the saved budget zone, even when no trades occur.
        if key!=month:
            if month is not None:
                months[month].update(paid_fees=str(spent),remaining_allowance=str(cap-spent),closing_reserved=str(reserved))
            previous_month=month
            month=key;spent=ZERO
            if previous_month is not None:
                release(at,'Month reset: old earmark expires; no allowance is carried.')
            months[month]=dict(month=month,cap=str(cap),opening_pending_activation=str(activation_fee if active and active['phase'] in ('evaluation','activation') else ZERO))
            emit(at,'month_reset',amount=cap,reason='New calendar-month cap; receipts never change spending permission. Initial partial month assumes no prior spending.')
            if active and active['phase'] in ('evaluation','activation'):
                reserved=activation_fee
                emit(at,'activation_reserved',amount=activation_fee,reservation=activation_fee,reason='Outstanding obligation re-reserved against the NEW cap before purchases; no old allowance carried.')
        if kind in ('month','tick'):
            purchase(at)
        elif kind=='receipt':
            payout=payload
            received+=Decimal(payout['trader_amount']);payout['status']='received'
            emit(at,'trader_receipt',account=payout['account'],amount=Decimal(payout['trader_amount']),receipt=Decimal(payout['trader_amount']),payout_id=payout['payout_id'],reason='Modeled receipt, not verified settlement; saved calendar-day assumption.')
        elif kind in ('eligible','activate','expire'):
            if active is None or active['account']!=payload or active['phase']!='activation':continue
            if kind=='eligible':
                emit(at,'activation_eligible',reason='Model eligibility; not verified provider approval.',deadline=active['activation_deadline'])
            elif kind=='activate':
                if at > instant(active['activation_deadline']):continue
                # Pay only from current-month cap. Reservation is not an expense.
                if activation_fee > cap-spent:
                    emit(at,'activation_payment_blocked',amount=activation_fee,reason='Current monthly cap; pending until deadline.')
                    continue
                release(at,'Activation payment consumes the obligation.')
                spent+=activation_fee;activation_total+=activation_fee
                emit(at,'activation_payment',amount=activation_fee,expense=activation_fee)
                active.update(phase='funded',activated_at=at.isoformat(),outcome='funded_open')
                active['_funded']=(lucid.FundedAccount(rules) if is_lucid_model else apex.FundedAccount(rules))
            else:
                emit(at,'activation_expired',reason='Unpaid at inclusive saved modeled deadline; no refund or terminal value.')
                close(at,'activation_expired')
        elif kind=='session' and active is not None:
            day=payload;phase=active['phase']
            if phase=='activation':continue
            if phase=='funded' and day <= date.fromisoformat(active['eligible_session']):continue
            available_from=instant(active['purchased_at'] if phase=='evaluation' else active['activated_at'])
            ids=identities[phase].get(day,[]);trades=books[phase].get(day,[])
            selected=[(r,t) for r,t in zip(ids,trades) if instant(r['entry_utc'])>=available_from]
            # No inherited positions; no account is allowed a pre-purchase session.
            if at <= available_from:continue
            trades=[t for _,t in selected];ids=[r for r,_ in selected]
            m=metrics[phase];m['sessions']+=1;payout=0.;gross=0.
            if phase=='evaluation':
                if active['first_session'] is None:active['first_session']=str(day)
                active['sessions']+=1
                effective=min(evaluation_size,40 if is_lucid_model else 60,exposure_cap)
                if is_lucid_model:
                    values=lucid.evaluation_session(trades,active['equity'],active['high'],active['best'],active['last_activity'],
                        (day-date.fromisoformat(active['first_session'])).days,effective,rules.daily_loss)
                    active['equity'],active['high'],active['best'],active['last_activity'],outcome,hit,consumed=values
                else:
                    active['equity'],active['high'],outcome,hit,consumed=apex.evaluation_session(trades,active['equity'],active['high'],effective)
                    if outcome=='open' and active['sessions']>=21:outcome='expired'
                equity=active['equity']
            else:
                account=active['_funded']
                if active['funded_start'] is None:active['funded_start']=str(day)
                payout=(account.advance(trades,funded_size,exposure_cap,calendar_day=(day-date.fromisoformat(active['funded_start'])).days)
                        if is_lucid_model else account.advance(trades,funded_size,exposure_cap))
                equity=account.equity;hit=account.last_hit;consumed=account.trades_consumed;effective=account.effective_micros;outcome=account.outcome
                gross=account.withdrawals[-1][1] if payout and is_lucid_model else payout
            m['trades_consumed']+=consumed
            if hit:m['account_breaches' if hit==2 else 'daily_stops']+=1
            trace.append(dict(date=str(day),timestamp_utc=at.isoformat(),account=active['account'],phase=phase,event=outcome,
                source_id=snapshot['phase_sources'][phase]['backtest']['id'],source_trade_ids=[r['trade_id'] for r in ids[:consumed]],
                target_micros=evaluation_size if phase=='evaluation' else funded_size,effective_micros=effective,
                trades_consumed=consumed,first_limit_hit={0:'none',1:'daily_stop',2:'account_breach'}[hit],equity=equity,
                trader_payout=payout,gross_withdrawal=gross))
            if payout:
                # Firm transitions already deducted gross equity and source trading costs.
                # Preserve kernel precision for the account deduction; model a
                # USD-cent bank receipt explicitly, without changing trading rules.
                raw_entitlement=Decimal(str(payout));gross_amount=Decimal(str(gross))
                amount=raw_entitlement.quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
                due=(at.astimezone(zone)+timedelta(days=int(settings['PAYOUT_RECEIPT_DAYS']))).astimezone(UTC)
                payout_id=len(receipts)+1
                emit(at,'payout_request',amount=amount,payout_id=payout_id,reason='Trader entitlement only; no receipt recorded here.')
                emit(at,'account_deduction',amount=gross_amount,payout_id=payout_id,account_equity_delta=str(-gross_amount),reason='Already deducted by funded kernel; not a trader cash expense.')
                receipt=dict(payout_id=payout_id,account=active['account'],requested_at=at.isoformat(),receipt_due_at=due.isoformat(),
                    trader_amount=str(amount),raw_trader_entitlement=str(raw_entitlement),gross_account_deduction=str(gross_amount),
                    status='pending',timing='unverified saved modeling assumption; receipt rounded USD cents HALF_UP')
                receipts.append(receipt);enqueue(due,4,'receipt',receipt)
            if outcome=='passed':
                eligible_day=(pd.Timestamp(day)+pd.offsets.BDay(wait)).date()
                eligible=datetime.combine(eligible_day,time(16),CHICAGO).astimezone(UTC)
                deadline=(eligible.astimezone(zone)+timedelta(days=int(settings['ACTIVATION_DEADLINE_DAYS']))).astimezone(UTC)
                payment=(eligible.astimezone(zone)+timedelta(days=int(settings['ACTIVATION_PAYMENT_DELAY_DAYS']))).astimezone(UTC)
                active.update(phase='activation',outcome='activation_pending',passed_on=str(day),eligible_session=str(eligible_day),
                    eligible_at=eligible.isoformat(),activation_deadline=deadline.isoformat(),activation_payment_due_at=payment.isoformat())
                emit(at,'evaluation_passed',reason='Evaluation profits are not trader cash.',deadline=deadline.isoformat())
                enqueue(eligible,5,'eligible',active['account']);enqueue(payment,6,'activate',active['account']);enqueue(deadline,7,'expire',active['account'])
            elif outcome in ('blown','expired','inactive','paid_all'):
                close(at,{'blown':'account_breach','expired':'evaluation_expired','inactive':'inactivity_expired','paid_all':'funded_payout_limit'}[outcome])
    months[month].update(paid_fees=str(spent),remaining_allowance=str(cap-spent),closing_reserved=str(reserved))
    for record in months.values():
        entries=[r for r in ledger if r['month']==record['month']]
        record.update(evaluation_fees=str(sum((Decimal(r['paid_fee']) for r in entries if r['event']=='evaluation_purchase'),ZERO)),
            activation_fees=str(sum((Decimal(r['paid_fee']) for r in entries if r['event']=='activation_payment'),ZERO)),
            trader_receipts=str(sum((Decimal(r['trader_receipt']) for r in entries),ZERO)),
            unused_expired=str(cash(record['remaining_allowance']) if record['month']!=month else ZERO))
        record['net_cash']=str(Decimal(record['trader_receipts'])-Decimal(record['paid_fees']))
    pending=[r for r in receipts if r['status']=='pending']
    for a in accounts:
        funded=a.pop('_funded',None)
        if funded is not None:
            a['funded_state']=dict(equity=funded.equity,high=funded.high,sessions=funded.day,
                outcome=funded.outcome,qualifying_days=funded.qualifying,payouts=funded.payouts)
            a['equity']=funded.equity
        if a is active:a['closed_at']=None  # Preserve open state, never invent terminal liquidation.
    totals=dict(received_trader_payouts=str(received),paid_evaluation_fees=str(eval_total),paid_activation_fees=str(activation_total),
        total_paid_fees=str(eval_total+activation_total),net_cash_within_horizon=str(received-eval_total-activation_total),
        payout_evaluation_fee_multiple=str(received/eval_total) if eval_total else None,
        pending_trader_receipts=str(sum((Decimal(r['trader_amount']) for r in pending),ZERO)),
        remaining_allowance=str(cap-spent),reserved_allowance=str(reserved),
        pending_activation_obligations=str(activation_fee if active and active['phase']=='activation' else ZERO),
        potential_evaluation_activation=str(activation_fee if active and active['phase']=='evaluation' else ZERO))
    return dict(model_version=model_version(settings),analysis_mode='budgeted_lifecycle',rules=asdict(rules),source_checks=checks,
        phase_metrics=metrics,activation=dict(wait_weekdays=wait),outcome=active['outcome'] if active else 'slot_unfunded',
        history=None,trace=trace,cash_ledger=ledger,monthly_ledger=list(months.values()),accounts=accounts,
        payout_settlements=receipts,pending_receipts=pending,cash_totals=totals,
        budget_contract=dict(timezone=str(zone),start_inclusive=start.isoformat(),end_exclusive=end.isoformat(),
            policy='activation_priority_reserve_at_purchase',initial_state='one unfunded slot',
            receipt_timing='unverified modeling assumption',activation_timing='unverified modeling assumption'),
        assumptions=[
            'One chronological observed path, one initially unfunded slot, fixed phase selections; no sampling, forward trading extrapolation or allocation optimization.',
            'Purchase at budget-local midnight when slot empty; replacements wait until the next daily scheduler tick. The initial partial month has its full cap with no prior spending. Fees are exact USD cents. Payouts never enlarge the monthly cap.',
            'Reserve full activation fee at evaluation purchase. On failure, payment or activation expiry release the earmark. Reservations are not expenses.',
            'At calendar-month reset, release the old reservation and expire unused allowance; re-reserve any evaluation/pending activation obligation against the NEW cap before new purchases. Deadlines do not reset.',
            'Daily trading transitions use Chicago session close (16:00); payment on eligibility plus saved calendar-day delay, inclusive saved deadline. Funded trading uses subsequent sessions and no pre-payment entries.',
            'Activation deadline/delay are saved modeling assumptions, not verified provider policy: '+settings['ACTIVATION_TIMING_ASSUMPTION'],
            'Requests and gross account deductions use existing firm transitions; trader receipts occur only at request time plus saved calendar days in budget timezone: '+settings['PAYOUT_TIMING_ASSUMPTION'],
            'Modeled bank receipts round trader entitlement to USD cents with Decimal ROUND_HALF_UP. Raw entitlement and gross account deduction retain kernel precision; rounding does not change account trading state.',
            'Pending receipts after the exclusive horizon are disclosed, not counted as received cash. Later dates/amounts are conditional modeled obligations, not confirmed bank events.',
            'Evaluation profit, account equity and unused allowance are not cash. Source trading costs remain inside net trading results and are never deducted again from this cash ledger.',
            'Open accounts and obligations remain open at the horizon; no terminal value/refund. Earlier annualized and dated models remain unchanged. No additional provider/Bridge numerical parity claim.',
            'Saved fee override note: '+(settings['FEE_OVERRIDE_NOTE'] or 'User-saved prices; not a live provider-price verification.')])
