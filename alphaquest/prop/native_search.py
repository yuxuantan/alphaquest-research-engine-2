"""Shared native candidate admission and immutable preparation, without selection.

Phase owners run forecasts or chronology; existing optimizers retain objectives.
"""
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256

from .adapter import canonical, source_record
from .phase_profiles import verify_phase_source

MAX_NATIVE_SEARCH_BAR_WORK = 50_000_000
MAX_NATIVE_SEARCH_SCHEDULE_BYTES = 16*1024*1024
MAX_NATIVE_SEARCH_CAPTURE_ESTIMATE = 100*1024*1024


def candidate_request(search, candidate, *, forecast=True):
    from .native_replay import NativeReplayRequest
    phase=search.mode.removesuffix('_optimization')
    native=search.native_execution
    if native is None:raise ValueError('Native candidate requires its explicit execution law.')
    value=dict(mode='native_phase_replay',phase=phase,source_backtest_id=candidate.source.source_backtest_id,
        profile=asdict(candidate.profile),micros=candidate.micros,max_micros=candidate.simulation.max_micros,
        costs=asdict(candidate.costs),period=asdict(candidate.period) if candidate.period else None,
        sizing=asdict(candidate.sizing) if candidate.sizing else None)
    if candidate.source.trade_file:
        raise ValueError('Actual native execution cannot use a supplemental fixed-trade excursion export.')
    if phase=='evaluation':value['retry']=asdict(candidate.retry)
    elif phase=='funded':value.update(receipt_delay_calendar_days=search.receipt_delay_calendar_days,
        receipt_amount_convention='kernel_entitlement_unrounded')
    else:raise ValueError('Native candidate requires an independent phase.')
    if forecast:
        value['native_forecast']=dict(model=native.model,simulations=candidate.simulation.simulations,
            seed=candidate.simulation.seed,block_sessions=candidate.sampling.block_weekdays,
            calendar={**asdict(search.calendar),'start_dates':list(search.calendar.start_dates),
                'closures':list(search.calendar.closures)},horizon_calendar_days=native.horizon_calendar_days,
            early_closes=native.early_closes,capture_paths=native.capture_paths)
    return NativeReplayRequest(**value)


def _assessment_mapping(search,candidate,record,assessment):
    if type(assessment) is not dict:raise ValueError('Native OOS requires its exact frozen assessment context.')
    package=assessment['frozen_package']
    if package.get('package_sha256')!=sha256(canonical({k:v for k,v in package.items() if k!='package_sha256'}).encode()).hexdigest():
        raise ValueError('Native assessment frozen package failed its hash check.')
    if canonical(package['search_settings'].get('native_execution'))!=canonical(asdict(search.native_execution)):
        raise ValueError('Native assessment execution law is frozen.')
    research=record['run_metadata']['research']
    for mapping in assessment['sources']:
        if mapping['source_id']!=record['id']:continue
        manifest=mapping['frozen_manifest'];saved=manifest['source']['backtest']
        expected=deepcopy(manifest['configuration'])
        expected['source']['source_backtest_id']=record['id']
        from .phase_lifecycle import instant,session_date
        expected['period']=dict(first_session=str(session_date(instant(record['period_start_utc']))),
            last_session=str(session_date(instant(record['period_end_utc']))))
        old_strategy=deepcopy(saved['run_metadata']['strategy']);old_strategy.pop('session_flattening',None)
        new_strategy=deepcopy(record['run_metadata']['strategy']);new_strategy.pop('session_flattening',None)
        if (canonical(expected)==canonical(asdict(candidate)) and research.get('phase')=='oos'
                and research.get('parent_run_id')==saved['id'] and new_strategy==old_strategy
                and record['run_metadata']['dataset']==saved['run_metadata']['dataset']
                and record['execution_settings']==saved['execution_settings']
                and research['plan']==saved['run_metadata']['research']['plan']
                and mapping['frozen_candidate_id'] in package['candidate_ids']):return mapping
    raise ValueError('Native OOS source/configuration is outside its frozen family.')


def assessment_request(search,candidate,record):
    """Resolve only the frozen horizon, never a newly fitted OOS forecast."""
    from datetime import date,timedelta
    from ..session_calendar import load_calendar
    request=candidate_request(search,candidate,forecast=False)
    first=date.fromisoformat(candidate.period.first_session)
    cutoff=first+timedelta(days=search.native_execution.horizon_calendar_days)
    calendar=load_calendar(symbol=record['run_metadata']['instrument']['symbol'])
    opens=[first+timedelta(days=i) for i in range((cutoff-first).days)
           if calendar.plan(first+timedelta(days=i)).close is not None]
    if not opens or str(opens[-1])>candidate.period.last_session:
        raise ValueError('Native OOS lacks observed coverage for the complete frozen horizon; no shortening or resampling is allowed.')
    return request.model_copy(update=dict(period=dict(first_session=str(opens[0]),last_session=str(opens[-1])))),str(cutoff)


def check_native_candidates(datasets,runs,search,*,assessment=None,training_context=None,observed_sessions=None):
    from .native_replay import check_replay
    from .phase_search import declared_is_coverage
    from .source import prepare_source
    if datasets is None:raise ValueError('Native phase execution requires the existing DatasetStore explicitly.')
    rows=[];common=None;work=0;schedule_bytes=0;capture_bytes=0
    for candidate in search.candidates:
        record=source_record(runs,candidate.source.source_backtest_id)
        mapping=None
        if assessment:mapping=_assessment_mapping(search,candidate,record,assessment)
        elif training_context is None:declared_is_coverage(record)
        request=(assessment_request(search,candidate,record)[0] if assessment else candidate_request(search,candidate))
        checked=check_replay(datasets,runs,request,
            admitted_record=record if assessment or training_context is not None else None)
        sessions=[row['session'] for row in checked['sessions']]
        if observed_sessions is not None and sessions!=list(observed_sessions):
            raise ValueError('Native checked session inventory differs from private training evidence.')
        snapshot,_=prepare_source(runs,record['id'],'',candidate.source.export_timezone,allow_empty=True)
        snapshot['profile_research_period']=dict(**checked['period'],sessions=len(sessions),
            observed_sessions=sessions,calendar_convention='reviewed original observed sessions; no fabricated weekdays')
        snapshot['native_execution_identity_only']=True
        protocol=dict(dataset=record['run_metadata']['dataset'],period=checked['period'],
            execution=record['execution_settings'],calendar=checked['calendar_metadata'],
            session_inventory=sessions,costs=asdict(candidate.costs))
        if common is not None and canonical(protocol)!=canonical(common):
            raise ValueError('Native candidates require identical dataset, source period, calendar and execution costs.')
        common=protocol
        manifest=dict(configuration=asdict(candidate),strategy=record['run_metadata']['strategy'],source=snapshot,
            native_execution=asdict(search.native_execution),native_source_check=checked)
        if training_context is not None:manifest['training_context_sha256']=training_context['context_sha256']
        candidate_id=sha256(canonical(manifest).encode()).hexdigest()
        access=dict(status='recorded',attempts=[],interpretation='IS-only selection; no OOS outcomes enter native forecasts.')
        origins=[]
        with runs.connect() as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='oos_attempts'").fetchone():
                history=db.execute('SELECT id,parent_run_id,run_id,status,created_at FROM oos_attempts WHERE strategy_id=? AND source_sha256=? ORDER BY created_at,id',
                    (record['run_metadata']['strategy']['id'],record['run_metadata']['dataset']['sha256'])).fetchall()
                access['attempts']=[dict(zip(('id','parent_run_id','run_id','status','created_at'),item)) for item in history]
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='optimization_trials'").fetchone():
                origins=[dict(optimization_id=id,trial=trial) for id,trial in db.execute(
                    "SELECT optimization_id,trial FROM optimization_trials WHERE json_extract(payload,'$.run_id')=? ORDER BY optimization_id,trial",(record['id'],)).fetchall()]
        rows.append(dict(candidate_id=candidate_id,manifest=manifest,status='compatible',prior_access=access,
            origin_trials=origins,**({'frozen_candidate_id':mapping['frozen_candidate_id']} if mapping else {})))
        if not assessment:
            plan=checked['native_forecast_plan'];work+=plan['work']['total_bar_work']
            schedule_bytes+=plan['work']['schedule_bytes']
            capture_bytes+=plan['work']['estimated_capture_bytes']
            if getattr(search,'conservative_objective',None) is not None:
                from .funded_profiles import native_historical_preflight
                historical=native_historical_preflight(plan['catalogue'],plan,search.conservative_objective,len(search.candidates))
                rows[-1]['native_historical_preflight']=historical
                work+=historical['conservative_bar_work_bound']
                capture_bytes+=historical['retained_metadata_estimated_bytes']
        else:
            bars=checked['source_check']['observed_bars']
            work+=bars
            capture_bytes+=bars*2048
        if work>MAX_NATIVE_SEARCH_BAR_WORK:
            raise ValueError('Native candidate family exceeds 50 million declared bar work; reduce the explicit family or paths.')
        if schedule_bytes>MAX_NATIVE_SEARCH_SCHEDULE_BYTES:
            raise ValueError('Complete native candidate-family schedules exceed 16 MiB; no candidates or source pools were omitted.')
        if capture_bytes>MAX_NATIVE_SEARCH_CAPTURE_ESTIMATE:
            raise ValueError('Complete native candidate-family capture/refit metadata estimate exceeds 100 MiB; reduce declared work, not retained membership.')
    if len({row['candidate_id'] for row in rows})!=len(rows):raise ValueError('Duplicate native candidate definitions.')
    family_work=dict(candidates=len(rows),total_bar_work=work,schedule_bytes=schedule_bytes,
        capture_and_refit_metadata_estimated_bytes=capture_bytes,
        limits=dict(bar_work=MAX_NATIVE_SEARCH_BAR_WORK,schedule_bytes=MAX_NATIVE_SEARCH_SCHEDULE_BYTES,
            capture_and_refit_metadata_estimated_bytes=MAX_NATIVE_SEARCH_CAPTURE_ESTIMATE),
        interpretation='Complete declared candidate family; no hidden truncation. Capture is a conservative estimate; final encoded report bytes are checked before publication.')
    for row in rows:row['native_search_work']=family_work
    return sorted(rows,key=lambda row:row['candidate_id'])


def prepare_native_candidate(datasets,runs,search,candidate,check,*,private_admission=False):
    """Return execution inputs to a phase owner; never execute or select here."""
    from decimal import Decimal
    from ..strategies.registry import get_strategy
    from ..strategy import ExecutionConfig
    from .native_replay import check_replay,prepare_native_forecast
    from .phase_profiles import SizingConfiguration
    if datasets is None:raise ValueError('Native phase execution requires DatasetStore.')
    request=candidate_request(search,candidate)
    record=source_record(runs,candidate.source.source_backtest_id)
    current=check_replay(datasets,runs,request,admitted_record=record if private_admission else None)
    if canonical(current)!=canonical(check['manifest']['native_source_check']):
        raise ValueError('Native source or sampling plan changed after candidate admission.')
    plan,catalogue,cohorts=prepare_native_forecast(datasets,request,current)
    definition=get_strategy(record['run_metadata']['strategy']['id'])
    parameters=definition.parameters(record['run_metadata']['strategy']['parameters'])
    config=ExecutionConfig(**{key:Decimal(value) if key!='slippage_ticks' else value for key,value in record['execution_settings'].items()})
    factory=lambda:definition.create(parameters,config,instrument_symbol=current['dataset']['symbol'])
    inputs=dict(catalogue=catalogue,target_contexts_by_cohort=cohorts,strategy_factory=factory,config=config,
        profile=candidate.profile,sizing=SizingConfiguration(**current['sizing']),micros=candidate.micros,
        forecast=request.native_forecast,max_micros=candidate.simulation.max_micros)
    return inputs,plan


def verify_native_candidate(datasets,runs,search,candidate,check,*,private_admission=False):
    from .native_replay import check_replay
    record=source_record(runs,candidate.source.source_backtest_id)
    current=check_replay(datasets,runs,candidate_request(search,candidate),
        admitted_record=record if private_admission else None)
    if canonical(current)!=canonical(check['manifest']['native_source_check']):
        raise ValueError('Native candidate inputs changed during execution.')
    verify_phase_source(runs,candidate.source,check['manifest']['source'])


def execute_native_assessment(datasets,runs,search,candidate,check,assessment,*,reserve_child,
        checkpoint=lambda:None,progress=lambda message:None):
    """Shared checked execution only; phase owners interpret the actual outcome."""
    from uuid import uuid4
    from .native_replay import execute_checked_replay
    from ..optimization_cache import artifacts
    if reserve_child is None:raise ValueError('Native frozen assessment requires normal child reservation before execution.')
    record=source_record(runs,candidate.source.source_backtest_id)
    mapping=_assessment_mapping(search,candidate,record,assessment)
    request,cutoff=assessment_request(search,candidate,record)
    child_id=uuid4().hex;reserve_child(child_id);checkpoint()
    metadata=dict(phase='native_phase_replay',role='frozen_account_controlled_oos',recommendation=False,
        source_backtest_id=record['id'],frozen_candidate_id=mapping['frozen_candidate_id'],
        frozen_package_sha256=assessment['frozen_package']['package_sha256'],
        campaign_id=assessment['campaign_id'],assessment_request_id=assessment['request_id'])
    child,result=execute_checked_replay(datasets,runs,request,check['manifest']['native_source_check'],
        admitted_record=record,research_metadata=metadata,run_id=child_id,
        control_metadata=dict(analysis_id=assessment['analysis_id'],
            frozen_package_sha256=assessment['frozen_package']['package_sha256']),
        replay_cutoff_date_exclusive=cutoff,checkpoint=checkpoint,progress=progress)
    result['frozen_package_sha256']=assessment['frozen_package']['package_sha256']
    result['frozen_candidate_id']=mapping['frozen_candidate_id']
    return dict(native_backtest=child,native_backtest_id=child_id,native_backtest_artifacts=artifacts(runs.root,child),
        native_chronological_replay=result)


def write_native_artifacts(runs,staged,calculations):
    """Native evidence remains inside the ordinary phase analysis directory."""
    from pathlib import Path
    from ..optimization_cache import artifacts
    staged=Path(staged)
    forecasts=[dict(candidate_id=row['candidate_id'],**row['native_forecast'])
               for row in calculations['candidates'] if 'native_forecast' in row]
    if forecasts:
        for name,values in [('native_forecasts.json',forecasts),
                ('native_forecast_paths.json',[dict(candidate_id=row['candidate_id'],paths=row['paths']) for row in forecasts]),
                ('native_forecast_schedules.json',[dict(candidate_id=row['candidate_id'],schedules=row['schedules']) for row in forecasts]),
                ('native_forecast_captures.json',[dict(candidate_id=row['candidate_id'],captures=row['captures']) for row in forecasts])]:
            (staged/name).write_text(canonical(values))
    chronological=[]
    for row in calculations['candidates']:
        if 'native_chronological_replay' not in row:continue
        child=row['native_backtest'];actual=artifacts(runs.root,child)
        if actual!=row['native_backtest_artifacts']:raise ValueError('Native controlled child changed before capture.')
        chronological.append(dict(candidate_id=row['candidate_id'],native_backtest_id=child['id'],
            **row['native_chronological_replay']))
    if chronological:(staged/'native_chronological_replays.json').write_text(canonical(chronological))
