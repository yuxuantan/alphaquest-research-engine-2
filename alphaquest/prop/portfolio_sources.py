"""Checked observed NQ/MNQ price paths for native portfolio execution."""
from collections.abc import Mapping
from dataclasses import asdict
from datetime import date,datetime,time,timedelta,timezone
from decimal import Decimal
import pickle
from hashlib import sha256
from pathlib import Path

from ..backtest_data import read_selected_bars
from ..research_folds import SessionDateRange
from ..session_calendar import load_calendar,session_date,CT,resolve_calendar
from ..strategies.registry import get_strategy
from ..strategy_sizing import source_support
from ..strategy import ExecutionConfig
from ..optimization_cache import artifacts,digest
from .native_control import SessionContext
from .native_market_hours import missing_minute_ranges, scheduled_pause_bar_labels
from .phase_profiles import EvaluationProfile,FundedProfile,SizingConfiguration,rule_version
from .phase_search import PhaseCalendar
from .evaluation_optimization import SequentialRetry


class SessionBars(Mapping):
    """Trusted temporary source spool; each worker loads only one session.

    The index travels to pool children, never the entire history's Bar objects.
    Files live in the normal job's temporary directory and are not a second
    dataset/result store. Every read verifies the captured bytes.
    """
    def __init__(self,directory,index=None):
        self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True)
        self.index={} if index is None else index

    def save(self,day,rows):
        filename=self.directory/(str(day)+'.pickle');raw=pickle.dumps(rows,protocol=pickle.HIGHEST_PROTOCOL)
        filename.write_bytes(raw);self.index[day]=(str(filename),sha256(raw).hexdigest())

    def __getitem__(self,day):
        filename,expected=self.index[day];raw=Path(filename).read_bytes()
        if sha256(raw).hexdigest()!=expected:raise ValueError('Temporary portfolio session source changed.')
        return pickle.loads(raw)

    def __len__(self):return len(self.index)
    def __iter__(self):return iter(self.index)
    def subset(self,start,end):return SessionBars(self.directory,{d:v for d,v in self.index.items() if start<=str(d)<=end})


def portfolio_eligibility(source):
    """One compatibility rule for the picker and launch."""
    try:
        descriptor=resolve_calendar(source['dataset'].get('symbol'))
    except ValueError as exc:
        return str(exc)
    if descriptor['id'] not in ('cme_nq','cme_mnq'):
        return 'Portfolio replay requires an NQ or MNQ dataset.'
    definition=get_strategy(source['strategy_id'])
    support=definition.sizing
    if support.session_settings is None or support.holding_start is None:
        return 'This strategy hasn’t declared a holding window and session close.'
    return source['sizing_support']['native_percentage_risk']['reason']


def session_coverage(day, close, entry, timestamps, *, prior_day=False):
    """Inventory missing tradable minutes and require an observed session close."""
    begin = datetime.combine(day - timedelta(days=1), time(17, 1), CT).astimezone(timezone.utc)
    start_day = day - timedelta(days=int(prior_day))
    risk_start = datetime.combine(start_day, time(entry // 100, entry % 100), CT).astimezone(timezone.utc)
    stamps = set(timestamps)
    if len(stamps) != len(timestamps) or any(
        t < begin or t > close or t.second or t.microsecond for t in stamps
    ):
        raise ValueError(f'Portfolio session {day} contains duplicate or invalid one-minute timestamps.')
    if close not in stamps:
        raise ValueError(f'Portfolio session {day} needs an observed bar at the scheduled close ({close.isoformat()}).')

    paused = {t for t in scheduled_pause_bar_labels(day) if begin <= t <= close}
    missing = missing_minute_ranges(day, stamps, close)
    holding = [(max(first, risk_start), last) for first, last in missing if last >= risk_start]
    total_missing = sum(int((last - first) // timedelta(minutes=1)) + 1 for first, last in missing)
    holding_missing = sum(int((last - first) // timedelta(minutes=1)) + 1 for first, last in holding)
    return dict(session=str(day), observed_bars=len(stamps),
                expected_full_session_bars=int((close - begin).total_seconds() // 60) + 1 - len(paused),
                scheduled_pause_minutes=len(paused),
                possible_holding_start_utc=risk_start.isoformat() if risk_start <= close else None,
                observed_close_utc=close.isoformat(),
                entry_window_before_close=risk_start < close,
                missing_pre_entry_bars=total_missing - holding_missing,
                missing_holding_minutes=holding_missing,
                holding_gap_ranges_utc=[(first.isoformat(), last.isoformat()) for first, last in holding])


def prepare(datasets,runs,qualified,settings,*,start,end,checkpoint=lambda:None,bar_directory=None):
    first,last=map(date.fromisoformat,(start,end));books=SessionBars(bar_directory) if bar_directory else {};specs=[];snapshots=[]
    datasets_seen=set();execution=None;calendar=None;holding_starts=[]
    for source in qualified:
        is_source=runs.get(source['source_backtest_id']);oos_source=runs.get(source['oos_report_id'])
        if not is_source or not oos_source:raise ValueError('A qualified portfolio source disappeared.')
        record=is_source;meta=record['run_metadata'];dataset=datasets.get(meta['dataset']['id'])
        if not dataset or any(dataset.get(k)!=v for k,v in meta['dataset'].items()):raise ValueError('Portfolio dataset identity changed.')
        symbol=dataset.get('symbol');descriptor=resolve_calendar(symbol)
        if descriptor['id'] not in ('cme_nq','cme_mnq'):raise ValueError('Portfolio execution requires NQ or MNQ.')
        strategy=meta['strategy'];definition=get_strategy(strategy['id']);parameters=definition.parameters(strategy['parameters'])
        eligibility=portfolio_eligibility(dict(source,sizing_support=dict(
            native_percentage_risk=source_support(definition,parameters,strategy)['percentage_risk'])))
        if eligibility:raise ValueError(eligibility)
        original=ExecutionConfig(**{k:Decimal(v) if k!='slippage_ticks' else v for k,v in record['execution_settings'].items()})
        config=ExecutionConfig(**{**asdict(original),'point_value':Decimal(2),'commission_per_contract_per_side':Decimal(settings['commission_per_mnq_side'])})
        if config.tick_size!=Decimal('.25'):raise ValueError('Portfolio MNQ execution requires the 0.25 tick grid.')
        instance=definition.create(parameters,config,instrument_symbol=symbol)
        if not callable(getattr(instance,'on_bar_controlled',None)):
            raise ValueError('Portfolio replay requires controlled native order admission.')
        holding_starts.append(definition.sizing.holding_start(parameters))
        if execution is not None and execution!=config:raise ValueError('Portfolio sources must share tick grid, execution costs and execution capital.')
        execution=config;calendar=load_calendar(symbol=symbol)
        specs.append(dict(strategy_id=strategy['id'],parameters=strategy['parameters'],symbol=symbol))
        snapshots.append(dict(is_id=is_source['id'],oos_id=oos_source['id'],is_sha256=digest(is_source),oos_sha256=digest(oos_source),
            is_artifacts=artifacts(runs.root,is_source),oos_artifacts=artifacts(runs.root,oos_source),dataset=meta['dataset'],
            price_interpretation='Observed NQ reference prices, MNQ point value 2; unverified micro basis and fills' if descriptor['id']=='cme_nq' else 'Observed MNQ prices and point value 2'))
        if dataset['id'] not in datasets_seen:
            if datasets_seen:raise ValueError('Synchronized portfolios currently require the same saved dataset. Different instrument calendars/prices are not combined.')
            datasets_seen.add(dataset['id'])
            with read_selected_bars(datasets,dataset['id'],SessionDateRange.parse(start,end)) as data:
                current=None;rows=[]
                def save():
                    if current is not None:
                        if isinstance(books,SessionBars):books.save(current,rows)
                        else:books[current]=rows
                for index,bar in enumerate(data.bars):
                    if index%20000==0:checkpoint()
                    day=session_date(bar.timestamp_utc)
                    if day!=current:save();current=day;rows=[]
                    rows.append(bar)
                save()
    entry,prior_day=min(holding_starts,key=lambda start:(not start[1],start[0]))
    contexts={};day=first;closed=[];coverage=[]
    while day<=last:
        plan=calendar.plan(day)
        if plan.close is not None:
            rows=books.get(day,[])
            close=plan.close.astimezone(timezone.utc)
            coverage.append(session_coverage(day, close, entry, [bar.timestamp_utc for bar in rows],prior_day=prior_day))
            contexts[day]=SessionContext(day,close,descriptor['id']+'-'+calendar.sha256,calendar.sha256,len(rows),True)
        elif day.weekday()<5:closed.append(str(day))
        day+=timedelta(days=1)
    if not contexts:raise ValueError('The requested portfolio window has no observed open sessions.')
    profile=settings['profile_id'];common=dict(profile_id=profile,rule_version=rule_version(profile),daily_loss_limit=settings['daily_loss_limit'])
    def sizing(phase):
        policy=settings.get(phase+'_policy')
        if policy is None:
            from .portfolio_search import sizing_policies
            policy=sizing_policies(settings[phase+'_grid'])[0]
        return SizingConfiguration(policy,'50000',dict(tick_size='.25',point_value='2',
            entry_slippage_ticks=execution.slippage_ticks,stop_exit_slippage_ticks=execution.slippage_ticks,
            commission_per_contract_per_side=settings['commission_per_mnq_side']))
    return dict(first=start,last=end,bars=books,sessions=contexts,strategies=specs,execution=execution,
        monthly_cap=settings['monthly_cap'],receipt_delay=settings['receipt_delay_calendar_days'],
        evaluation_sizing=sizing('evaluation'),funded_sizing=sizing('funded'),
        evaluation_profile=EvaluationProfile(**common,evaluation_price=settings['evaluation_price'],activation_fee=settings['activation_fee'],consistency_percent=settings['evaluation_consistency_percent']),
        funded_profile=FundedProfile(**common,approval_day_counts=True),
        calendar=PhaseCalendar((start,),str(last+timedelta(days=2)),tuple(closed)),retry=SequentialRetry(activation_delay_sessions=0 if profile=='lucidflex-50k' else 1),sources=snapshots,coverage=coverage)
