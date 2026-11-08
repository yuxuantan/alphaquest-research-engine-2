"""Frozen pair admission and orchestration delegated by phase_lifecycle.

Existing native execution and phase controllers calculate both independent
policies. Only already completed ordinary OOS sources are admitted.
"""
from copy import deepcopy
from datetime import date,timedelta
from hashlib import sha256
from typing import Literal
from uuid import uuid4
from zoneinfo import ZoneInfo

from pydantic import BaseModel,ConfigDict,Field,model_validator

from alphaquest.prop.adapter import canonical,source_record
from alphaquest.optimization_cache import artifacts,engine_identity
from alphaquest.session_calendar import load_calendar,session_date
from alphaquest.prop.phase_lifecycle import instant
from alphaquest.prop.cash_ledger import merge_pair_cash


def require(value,message):
    if not value:raise ValueError(message)


def fingerprint(value):
    return sha256(canonical(value).encode()).hexdigest()


def module_for(phase):
    from alphaquest.prop.phase_dispatch import module_for as owner
    return owner(phase)


def seal(value,key):
    result=deepcopy(value);result[key]=fingerprint(result);return result


def verified(value,key):
    require(value.get(key)==fingerprint({k:v for k,v in value.items() if k!=key}),'Pair binding hash changed.')


class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,frozen=True)


class FrozenPhaseReference(Strict):
    campaign_id:str=Field(pattern=r'^[0-9a-f]{32}$')
    package_sha256:str=Field(pattern=r'^[0-9a-f]{64}$')
    candidate_id:str=Field(pattern=r'^[0-9a-f]{64}$')
    source_backtest_id:str=Field(pattern=r'^[0-9a-f]{32}$')


class NamedFrozenPair(Strict):
    id:str=Field(min_length=1,max_length=120)
    evaluation:FrozenPhaseReference
    funded:FrozenPhaseReference


class PairWindow(Strict):
    first_session:str
    cutoff_date_exclusive:str

    @model_validator(mode='after')
    def dates(self):
        a,b=date.fromisoformat(self.first_session),date.fromisoformat(self.cutoff_date_exclusive)
        require(str(a)==self.first_session and str(b)==self.cutoff_date_exclusive and 1<=(b-a).days<=365,
            'Pair window requires canonical dates spanning 1–365 days, with an exclusive cutoff.')
        return self


class PairComparisonRequest(Strict):
    mode:Literal['predefined_lifecycle_comparison']='predefined_lifecycle_comparison'
    request_id:str=Field(pattern=r'^[0-9a-f]{32}$')
    window:PairWindow
    pairs:list[NamedFrozenPair]=Field(min_length=1,max_length=20)
    continuation:Literal['first_ready_session_until_common_cutoff']='first_ready_session_until_common_cutoff'
    replacement:Literal['none']='none'

    @model_validator(mode='after')
    def membership(self):
        require(len({p.id for p in self.pairs})==len(self.pairs),'Pair names must be unique.')
        require(all(p.id.strip()==p.id and p.id for p in self.pairs),'Pair names must be nonempty without surrounding whitespace.')
        require(len({canonical(dict(evaluation=p.evaluation.model_dump(),funded=p.funded.model_dump())) for p in self.pairs})==len(self.pairs),
            'Duplicate frozen pair definitions are not permitted.')
        return self


def _ordinary_context():
    from alphaquest.research_access import _authorization,_metadata
    require(_authorization.get() is None and not _metadata.get(),
        'Pair comparison accepts ordinary recorded OOS access, not protected final authorization or metadata-only bypass.')


def _resolve_policy(campaigns,runs,reference,phase):
    """Resolve authority from the existing saved campaign, never a request blob."""
    campaign=campaigns.get(reference.campaign_id);package=campaign.get('frozen')
    require(package is not None,'Freeze the independent phase candidate before pairing.')
    require(package['schema_version']=='phase-freeze-v1' and package['phase']==phase,
        'Pair reference must name its ordinary independent phase freeze.')
    require(package['package_sha256']==reference.package_sha256,'Pair reference differs from the authoritative frozen package.')
    verified(package,'package_sha256')
    require(package['campaign_id']==reference.campaign_id and package['campaign_manifest_sha256']==fingerprint(campaign['manifest']),
        'Frozen campaign identity changed.')
    require(package['search_settings'].get('native_execution') is not None,'Initial pair comparison supports actual native frozen policies only.')
    require(module_for(phase).implementation_identity()==package['implementation'],'Frozen phase implementation changed.')
    report=campaigns.report(reference.campaign_id)
    checks=campaigns.analyses.fingerprint(package['analysis_id'])
    require(checks and checks['files']['report.json']==package['report_sha256'],'Frozen training report changed.')
    require(report['implementation']==package['implementation'],'Frozen training implementation changed.')
    require(canonical(package['search_settings'])==canonical({k:v for k,v in report['request'].items() if k!='candidates'}),
        'Frozen native horizon, receipt timing or search declaration differs from the actual training report.')
    require(reference.candidate_id in package['candidate_ids'],'Pair candidate is outside the frozen selected family.')
    definitions=[row for row in package['candidate_definitions'] if row['candidate_id']==reference.candidate_id]
    rows=[row for row in report['calculations']['candidates'] if row['candidate_id']==reference.candidate_id]
    require(len(definitions)==len(rows)==1 and definitions[0]['manifest']==rows[0]['manifest'],
        'Frozen candidate definition differs from its actual training report.')
    manifest=deepcopy(definitions[0]['manifest']);config=manifest['configuration']
    parent=source_record(runs,config['source']['source_backtest_id'])
    require(parent==manifest['source']['backtest'],'Frozen original IS source manifest changed.')
    native=manifest['native_source_check']
    require(artifacts(runs.root,parent)==native['source_artifacts'],'Frozen IS source artifacts changed.')
    original=parent['run_metadata'];plan=original['research']['plan']
    require(original['research'].get('phase')=='is','Pair selection requires original declared IS parents.')
    record=source_record(runs,reference.source_backtest_id);meta=record['run_metadata'];research=meta.get('research',{})
    require(research.get('phase')=='oos' and research.get('parent_run_id')==parent['id']
        and not record.get('native_account_control') and meta.get('source',{}).get('kind')!='external_trade_export',
        'Pair source must be an ordinary manually executed OOS report for its exact frozen parent.')
    with runs.connect() as db:
        attempt=db.execute('SELECT status,parent_run_id,run_id FROM oos_attempts WHERE id=?',(research.get('attempt_id'),)).fetchone()
    require(attempt is not None and tuple(attempt)==('complete',parent['id'],record['id']),
        'Pair source requires a durable completed manual OOS attempt; checking never launches a new holdout.')
    strategy=lambda value:{k:v for k,v in value.items() if k!='session_flattening'}
    require(strategy(meta['strategy'])==strategy(original['strategy']) and meta['dataset']==original['dataset']
        and meta['instrument']==original['instrument'] and record['execution_settings']==parent['execution_settings']
        and research['plan']==plan and meta.get('execution_scenario') is None,
        'OOS strategy, parameters, dataset, instrument, execution costs or split differ from the frozen parent.')
    a,b=instant(record['period_start_utc']),instant(record['period_end_utc']);zone=ZoneInfo(plan['source_timezone'])
    require(plan['oos_start']<=str(a.astimezone(zone).date())<=str(b.astimezone(zone).date())<=plan['oos_end'],
        'Saved OOS observations fall outside their exact declared split.')
    require(str(session_date(a))>str(session_date(instant(parent['period_end_utc']))),
        'OOS target overlaps the frozen parent training sessions.')
    return dict(phase=phase,reference=reference.model_dump(),package=package,configuration=config,source=record,
        source_artifacts=artifacts(runs.root,record),training_last_session=str(session_date(instant(parent['period_end_utc']))))


def _native_request(policy,first,last):
    from alphaquest.prop.native_replay import NativeReplayRequest
    config=policy['configuration'];phase=policy['phase'];settings=policy['package']['search_settings']
    value=dict(mode='native_phase_replay',phase=phase,source_backtest_id=policy['source']['id'],
        profile=config['profile'],micros=config['micros'],max_micros=config['simulation']['max_micros'],
        sizing=config.get('sizing'),costs=config['costs'],period=dict(first_session=first,last_session=last))
    if phase=='evaluation':value['retry']=config['retry']
    else:value.update(receipt_delay_calendar_days=settings['receipt_delay_calendar_days'],
        receipt_amount_convention='kernel_entitlement_unrounded')
    return NativeReplayRequest.model_validate(value)


def check_frozen_pairs(datasets,runs,campaigns,request):
    """No strategy or new OOS execution. Existing OOS bytes may be revalidated."""
    from alphaquest.prop.native_replay import check_replay
    _ordinary_context()
    require(type(request) is PairComparisonRequest,'Pair comparison requires its strict request contract.')
    first,end=date.fromisoformat(request.window.first_session),date.fromisoformat(request.window.cutoff_date_exclusive)
    pairs=[];family_work=0;capture_bytes=0
    for pair in request.pairs:
        policies={phase:_resolve_policy(campaigns,runs,getattr(pair,phase),phase) for phase in ('evaluation','funded')}
        a,b=policies.values();profiles=[p['configuration']['profile'] for p in policies.values()]
        require(profiles[0]['profile_id']==profiles[1]['profile_id'] and profiles[0]['rule_version']==profiles[1]['rule_version'],
            'Evaluation and Funded must share the same supported provider/account program and rule version.')
        identities=[{k:p['source']['run_metadata'][k] for k in ('dataset','instrument')} for p in policies.values()]
        require(identities[0]==identities[1],'Paired sources require identical actual market data and timestamp interpretation.')
        require(all((end-first).days<=p['package']['search_settings']['native_execution']['horizon_calendar_days'] for p in policies.values()),
            'Common comparison horizon cannot exceed either independently tested native horizon.')
        require(all(str(first)>p['training_last_session'] for p in policies.values()),'Pair target overlaps a phase training window.')
        calendar=load_calendar(symbol=a['source']['run_metadata']['instrument']['symbol'])
        opens=[str(first+timedelta(days=i)) for i in range((end-first).days)
            if calendar.plan(first+timedelta(days=i)).close is not None]
        require(opens and opens[0]==str(first),'Pair start must be an actual observed open session.')
        for phase,policy in policies.items():
            native_request=_native_request(policy,opens[0],opens[-1])
            checked=check_replay(datasets,runs,native_request,admitted_record=policy['source'])
            require([s['session'] for s in checked['sessions']]==opens,'Pair source has incomplete actual common-session coverage.')
            policy.update(native_request=native_request.model_dump(mode='json'),native_source_check=checked)
            family_work+=checked['source_check']['observed_bars'];capture_bytes+=checked['source_check']['observed_bars']*2048
        require(family_work<=50_000_000 and capture_bytes<=100*1024*1024,
            'Complete pair family exceeds its bar-work or capture bound; reduce the declared family/window.')
        binding=seal(dict(schema_version='frozen-pair-application-v1',pair_id=pair.id,
            window=request.window.model_dump(),continuation=request.continuation,replacement=request.replacement,
            policies={phase:dict(campaign_id=p['reference']['campaign_id'],package_sha256=p['package']['package_sha256'],
                candidate_id=p['reference']['candidate_id'],source_backtest_id=p['source']['id'],source_manifest_sha256=fingerprint(p['source']),
                source_artifacts=p['source_artifacts'],configuration_sha256=fingerprint(p['configuration'])) for phase,p in policies.items()},
            engine_identity=engine_identity(),calendar_metadata=calendar.metadata(),observed_sessions=opens), 'binding_sha256')
        pairs.append(dict(id=pair.id,policies=policies,binding=binding))
    return seal(dict(schema_version='frozen-pair-check-v1',request=request.model_dump(mode='json'),pairs=pairs,
        work=dict(total_bar_work=family_work,capture_estimated_bytes=capture_bytes),
        interpretation='Previously accessed manual OOS only; not a new holdout test or an untouched-data claim.'),'check_sha256')


def derive_continuation(binding,evaluation,child_id):
    verified(binding,'binding_sha256')
    require(evaluation.get('phase')=='evaluation' and evaluation.get('mode')=='native_historical_chronological_replay',
        'Continuation requires the actual chronological Evaluation owner result.')
    first=binding['window']['first_session'];end=binding['window']['cutoff_date_exclusive']
    ready=[e['date'] for e in evaluation['cash_ledger'] if e['event']=='funded_ready']
    if evaluation.get('acquisition_completed') is not True:
        require(not ready,'Uncompleted acquisition cannot contain a funded-ready cash event.')
        return None
    start=evaluation.get('ready_date')
    require(ready==[start] and first<=start<end and start in binding['observed_sessions'],
        'Funded continuation must start at the authenticated ready event before the common exclusive cutoff.')
    return seal(dict(schema_version='frozen-pair-continuation-v1',pair_binding_sha256=binding['binding_sha256'],
        evaluation_backtest_id=child_id,evaluation_result_sha256=fingerprint(evaluation),
        funded_package_sha256=binding['policies']['funded']['package_sha256'],
        window=dict(first_session=start,cutoff_date_exclusive=end),
        estimand='remaining_horizon_chronological_continuation',strategy_boundary='cold_start_finish_flat',
        fresh_nominal_capital='50000',replacement='none'),'continuation_sha256')


def run_frozen_pairs(datasets,runs,campaigns,request,checked,*,analysis_id,reserve_child,
        checkpoint=lambda:None,progress=lambda message:None):
    """Use normal native execution/phase owners; caller reserves/captures children."""
    from alphaquest.prop.native_replay import NativeReplayRequest,check_replay,execute_checked_replay
    require(callable(reserve_child),'Normal controlled-child reservation is required.')
    verified(checked,'check_sha256');checkpoint()
    require(canonical(check_frozen_pairs(datasets,runs,campaigns,request))==canonical(checked),
        'Frozen pair inputs changed after Check.')
    results=[]
    for index,row in enumerate(checked['pairs'],1):
        progress(f'Pair {index}/{len(checked["pairs"])}: Evaluation acquisition');checkpoint()
        binding=row['binding'];children={};outputs={};continuation=None
        for phase in ('evaluation','funded'):
            policy=row['policies'][phase]
            if phase=='funded' and continuation is None:break
            native_request=NativeReplayRequest.model_validate(policy['native_request']);source_check=policy['native_source_check']
            if phase=='funded':
                native_request=_native_request(policy,continuation['window']['first_session'],source_check['period']['last_session'])
                source_check=check_replay(datasets,runs,native_request,admitted_record=policy['source'])
                progress(f'Pair {index}/{len(checked["pairs"])}: fresh Funded continuation')
            child_id=uuid4().hex;reserve_child(child_id);checkpoint()
            research=dict(phase='lifecycle_comparison',role='frozen_pair_recorded_oos',analysis_id=analysis_id,
                pair_id=row['id'],pair_binding_sha256=binding['binding_sha256'],component_phase=phase,
                source_backtest_id=policy['source']['id'],frozen_package_sha256=policy['package']['package_sha256'],
                frozen_candidate_id=policy['reference']['candidate_id'],recommendation=False)
            if continuation:research['continuation_sha256']=continuation['continuation_sha256']
            child,result=execute_checked_replay(datasets,runs,native_request,source_check,admitted_record=policy['source'],
                research_metadata=research,run_id=child_id,control_metadata=dict(analysis_id=analysis_id,pair_binding_sha256=binding['binding_sha256']),
                replay_cutoff_date_exclusive=request.window.cutoff_date_exclusive,checkpoint=checkpoint,progress=progress)
            children[phase]=child;outputs[phase]=result
            if phase=='evaluation':continuation=derive_continuation(binding,result,child_id)
        cash=merge_pair_cash(outputs['evaluation'],outputs.get('funded'),**request.window.model_dump(),
            child_ids={phase:child['id'] for phase,child in children.items()})
        results.append(dict(id=row['id'],pair_binding=binding,continuation_binding=continuation,
            evaluation=outputs['evaluation'],funded=outputs.get('funded'),
            funded_status='started' if 'funded' in outputs else 'not_started',cash=cash,
            native_backtests=children,selection_status='comparison_only_no_selection',production_qualified=False))
    checkpoint();require(canonical(check_frozen_pairs(datasets,runs,campaigns,request))==canonical(checked),
        'Pair source or frozen package changed during execution; child evidence retained without completed comparison.')
    return dict(mode=request.mode,schema_version='frozen-pair-comparison-v1',request=request.model_dump(mode='json'),
        check_sha256=checked['check_sha256'],pairs=results,selection_status='comparison_only_no_selection',
        winner=None,historical_paths_per_pair=1,production_qualified=False,
        assumptions=['Already accessed manually executed OOS sources; no new holdout execution or untouched-data claim.',
            'Every declared pair retained without ranking, implicit weights, portfolio allocation or funded replacement.',
            'Funded starts fresh only after actual acquisition readiness; its shorter remaining horizon is a separate observed estimand.',
            'Provider rules, OHLC execution ordering and modeled payout receipts remain unverified.'])
