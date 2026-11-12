"""Qualified campaign sources -> existing independent phase campaigns/reports."""
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
from uuid import UUID, uuid5

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator, model_validator

from .campaign_broad import invoke
from .campaign_monte_carlo import POLICY as MC_POLICY
from .campaign_oos import context as oos_context, results as oos_results
from .optimization_cache import artifacts, digest
from .research_campaigns import CampaignRequest
from .prop.phase_profiles import rule_version


PROFILE='apex-50k-eod'
SIZE_LIMITS=dict(evaluation=60,funded=40)
DISCLOSURE=('Sizing uses only the selected configuration’s declared IS history. Eligibility has already used OOS and full-period Monte Carlo, so this is post-screening research, not an untouched final holdout. '
            'Saved fixed-signal trades are scaled to whole MNQ contracts with native held-OHLC adverse bounds. Account stops/pauses do not rerun strategy signals; execution, gaps and size-dependent fills remain assumptions. '
            'Evaluation and Funded objectives are independent. Calendars below are declared weekday scenarios, not verified exchange calendars. '
            'Local Apex 50K EOD rules are versioned model assumptions, not newly certified provider rules. Fees are editable scenarios; receipt delay is a modeled assumption. No portfolio allocation or combined annual net projection is calculated.')


def initialize(db):
    db.execute('CREATE TABLE IF NOT EXISTS workflow_prop_simulations (id TEXT PRIMARY KEY, created TEXT NOT NULL, payload TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS workflow_prop_sim_phases (simulation_id TEXT NOT NULL, phase TEXT NOT NULL, campaign_id TEXT NOT NULL UNIQUE, PRIMARY KEY(simulation_id,phase))')


class Selection(BaseModel):
    model_config=ConfigDict(extra='forbid')
    workflow_id: UUID
    oos_job_id: UUID
    monte_carlo_id: UUID
    candidate: StrictInt = Field(ge=1,le=4)


class Configuration(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_id: UUID
    selections: list[Selection] = Field(min_length=1,max_length=1)
    evaluation_minimum_micros: StrictInt = Field(default=1,ge=1,le=60)
    evaluation_maximum_micros: StrictInt = Field(default=10,ge=1,le=60)
    funded_minimum_micros: StrictInt = Field(default=1,ge=1,le=40)
    funded_maximum_micros: StrictInt = Field(default=10,ge=1,le=40)
    simulations: StrictInt = Field(default=1000,ge=8,le=20000)
    seed: StrictInt = Field(default=42,ge=0,lt=2**32-3)
    block_weekdays: StrictInt = Field(default=5)
    evaluation_price: StrictStr = '49'
    activation_fee: StrictStr = '129'
    start_date: StrictStr
    closures: list[StrictStr] = Field(default_factory=list,max_length=3660)
    funded_horizon_calendar_days: StrictInt = Field(default=90,ge=1,le=365)
    receipt_delay_calendar_days: StrictInt = Field(default=2,ge=0,le=365)
    maximum_funded_breach_probability: float | None = Field(default=None,ge=0,le=1)
    commission_per_mnq_side: StrictStr = '0.51'

    @model_validator(mode='before')
    @classmethod
    def legacy_shared_range(cls,value):
        """Read old declarations without mutating their saved settings/reports."""
        if isinstance(value,dict) and {'minimum_micros','maximum_micros'} & value.keys():
            if any(f'{phase}_{bound}_micros' in value for phase in SIZE_LIMITS for bound in ('minimum','maximum')):
                raise ValueError('Use either legacy shared sizes or separate phase sizes, not both.')
            value=dict(value)
            minimum=value.pop('minimum_micros',1);maximum=value.pop('maximum_micros',10)
            for phase in SIZE_LIMITS:
                value.update({f'{phase}_minimum_micros':minimum,f'{phase}_maximum_micros':maximum})
        return value

    @model_validator(mode='after')
    def ordered_ranges(self):
        for phase in SIZE_LIMITS:
            if getattr(self,f'{phase}_minimum_micros')>getattr(self,f'{phase}_maximum_micros'):
                raise ValueError(f'{phase.title()} minimum size must not exceed its maximum size.')
        return self

    @field_validator('evaluation_price','activation_fee','commission_per_mnq_side')
    @classmethod
    def money(cls,value):
        try:number=Decimal(value)
        except InvalidOperation as exc:raise ValueError('Enter a numeric cost amount.') from exc
        if not number.is_finite() or not 0<=number<=100000:raise ValueError('Costs must be finite, nonnegative amounts ≤100000.')
        return value


def qualified(request,selection):
    """Authoritative qualification for listing, check and launch; no client verdicts."""
    workflow_id=selection.workflow_id.hex;job_id=selection.oos_job_id.hex;mc_id=selection.monte_carlo_id.hex
    workflows=request.app.state.campaign_workflows
    saved,_=workflows.phase(workflow_id,'oos')
    with workflows.runs.connect() as db:
        current=db.execute('SELECT job_id FROM campaign_oos_state WHERE workflow_id=?',(workflow_id,)).fetchone()
    if not current or current[0]!=job_id:raise ValueError('Select the current completed OOS assessment.')
    _,_,identity,job,_=oos_context(request,workflow_id,job_id)
    if job['status']!='complete':raise ValueError('OOS is not complete.')
    result=oos_results(request,workflow_id,job_id)
    candidate=next((i for i in result['items'] if i['trial']==selection.candidate and i['qualifies']),None)
    if not candidate:raise ValueError('This configuration did not pass verified OOS acceptance.')
    analyses=request.app.state.prop_analyses
    with analyses.connect() as db:
        latest=db.execute('SELECT a.id,a.status FROM analyses a JOIN campaign_sanity_jobs c ON c.analysis_id=a.id WHERE c.workflow_id=? AND c.oos_job_id=? ORDER BY a.created DESC LIMIT 1',(workflow_id,job_id)).fetchone()
    if not latest or latest!=(mc_id,'complete'):raise ValueError('Select a configuration from the latest completed Monte Carlo assessment.')
    if not analyses.fingerprint(mc_id):raise ValueError('Monte Carlo evidence integrity check failed.')
    report=json.loads((analyses.root/mc_id/'report.json').read_text())
    if report['policy']!=MC_POLICY or report['frozen_identity']!=identity or report['plan']!=saved['declaration']['plan']:
        raise ValueError('Monte Carlo policy or frozen campaign identity is incompatible.')
    mc=next((i for i in report['candidates'] if i['candidate']==selection.candidate),None)
    if (not mc or not mc['qualifies'] or not mc['evidence_passed']
            or mc['observed']['days']<MC_POLICY['minimum_observed_days']
            or mc['closed_trades']<MC_POLICY['minimum_closed_trades']
            or len(mc['scenarios'])!=len(MC_POLICY['block_lengths'])
            or {s['mean_block_days'] for s in mc['scenarios']}!=set(MC_POLICY['block_lengths'])
            or not all(s['qualifies'] and s['net_profit_p05']>0 for s in mc['scenarios'])):
        raise ValueError('This configuration did not pass the current Monte Carlo criteria.')
    if (mc['parameters']!=candidate['parameters'] or mc['broad_trial']!=candidate['broad_trial']
            or mc['narrow_trial']!=candidate['narrow_trial'] or mc['oos_admission']!=candidate['admission']):
        raise ValueError('Monte Carlo and OOS configuration identities differ.')
    for proof,id in zip(mc['sources'],(candidate['is_run_id'],candidate['run_id']),strict=True):
        native=workflows.runs.get(id)
        if proof['run_id']!=id or proof['manifest_sha256']!=digest(native) or proof['artifacts']!=artifacts(workflows.runs.root,native):
            raise ValueError('Qualified native source evidence changed.')
    from .prop.commissions import source_instrument
    native=workflows.runs.get(candidate['is_run_id'])
    if source_instrument(native) not in ('NQ','MNQ'):raise ValueError('This local prop model requires a saved NQ or MNQ dataset symbol.')
    return dict(selection=selection.model_dump(mode='json'),source_backtest_id=candidate['is_run_id'],
        strategy_id=saved['declaration']['strategy_id'],dataset=saved['declaration']['dataset'],parameters=candidate['parameters'],
        plan=saved['declaration']['plan'],broad_trial=candidate['broad_trial'],narrow_trial=candidate['narrow_trial'],
        oos_report_id=candidate['run_id'],monte_carlo_report_sha256=analyses.fingerprint(mc_id)['files']['report.json'],
        frozen_identity=identity,qualification='mechanics, IS Broad, IS Narrow, OOS and Monte Carlo passed')


def candidates(request):
    runs=request.app.state.runs;analyses=request.app.state.prop_analyses
    with runs.connect() as db:
        workflows=[r[0] for r in db.execute('SELECT workflow_id FROM campaign_oos_state')]
    items=[];unavailable=[]
    for workflow in workflows:
        with runs.connect() as db:job=db.execute('SELECT job_id FROM campaign_oos_state WHERE workflow_id=?',(workflow,)).fetchone()[0]
        with analyses.connect() as db:
            latest=db.execute('SELECT a.id,a.status FROM analyses a JOIN campaign_sanity_jobs c ON c.analysis_id=a.id WHERE c.workflow_id=? AND c.oos_job_id=? ORDER BY a.created DESC LIMIT 1',(workflow,job)).fetchone()
        if not latest or latest[1]!='complete':continue
        try:
            if not analyses.fingerprint(latest[0]):raise ValueError('Monte Carlo evidence is unavailable or changed.')
            report=json.loads((analyses.root/latest[0]/'report.json').read_text())
            for candidate in report['candidates']:
                if not candidate['qualifies']:continue
                ref=Selection(workflow_id=workflow,oos_job_id=job,monte_carlo_id=latest[0],candidate=candidate['candidate'])
                try:items.append(qualified(request,ref))
                except (ValueError,KeyError,OSError) as exc:unavailable.append(dict(workflow_id=workflow,candidate=candidate['candidate'],reason=str(exc)))
        except (ValueError,KeyError,OSError) as exc:unavailable.append(dict(workflow_id=workflow,reason=str(exc)))
    return dict(items=items,unavailable=unavailable,maximum_selected_configurations=1)


def declarations(body,source):
    if body.block_weekdays not in (1,5,10):raise ValueError('Block length must be 1, 5 or 10 weekdays.')
    profile=dict(profile_id=PROFILE,rule_version=rule_version(PROFILE),daily_loss_limit=True)
    # The saved source bounds may start on the prior Chicago session date.
    from .prop.phase_lifecycle import instant, session_date
    native=source['_native']
    first=max(source['plan']['is_start'],session_date(instant(native['period_start_utc'])).isoformat())
    last=min(source['plan']['is_end'],session_date(instant(native['period_end_utc'])).isoformat())
    common=dict(is_window=dict(first_session=first,last_session=last),
        costs=dict(mode='override',broker='Rithmic',per_side=body.commission_per_mnq_side,instrument='auto'))
    calendar=dict(start_dates=[body.start_date],closures=body.closures)
    definitions={}
    for phase in ('evaluation','funded'):
        minimum=getattr(body,f'{phase}_minimum_micros');maximum=getattr(body,f'{phase}_maximum_micros')
        phase_profile=dict(profile)
        sampling=dict(block_weekdays=body.block_weekdays)
        settings=dict(calendar=calendar)
        if phase=='evaluation':
            phase_profile.update(evaluation_price=body.evaluation_price,activation_fee=body.activation_fee)
            sampling.update(chain_simulations=body.simulations,chain_seed=body.seed+3)
        else:
            phase_profile['approval_day_counts']=True
            settings.update(horizon_calendar_days=body.funded_horizon_calendar_days,
                receipt_delay_calendar_days=body.receipt_delay_calendar_days,bootstrap_replicates=100,
                constraints=dict(maximum_account_breach_probability=body.maximum_funded_breach_probability,maximum_position_size=maximum))
        definitions[phase]=CampaignRequest.model_validate(dict(common,campaign_id=uuid5(body.request_id,phase).hex,
            sources=[dict(backtest_id=source['source_backtest_id'],sizes=list(range(minimum,maximum+1)))],
            simulation=dict(simulations=body.simulations,seed=body.seed,max_micros=SIZE_LIMITS[phase]),
            phase=phase,profile=phase_profile,sampling=sampling,search_settings=settings))
    return definitions


def check(request,body):
    source=qualified(request,body.selections[0])
    source['_native']=request.app.state.runs.get(source['source_backtest_id'])
    definitions=declarations(body,source);source.pop('_native')
    checks={}
    for phase,declaration in definitions.items():
        try:checks[phase]=request.app.state.campaigns.expand(declaration)
        except ValueError as exc:raise ValueError(f'{phase.title()} sizing search: {exc}') from exc
    return dict(status='compatible',source=source,phases=checks,disclosure=DISCLOSURE),definitions


def public(request,id):
    with request.app.state.prop_analyses.connect() as db:row=db.execute('SELECT payload FROM workflow_prop_simulations WHERE id=?',(id,)).fetchone()
    if not row:raise KeyError('Prop simulation not found.')
    result=json.loads(row[0])
    result['phases']={}
    for phase,campaign_id in result['campaign_ids'].items():
        campaign=request.app.state.campaigns.get(campaign_id)
        analysis=campaign.get('analysis') or {}
        result['phases'][phase]=dict(campaign_id=campaign_id,status=campaign['status'],analysis_id=campaign['analysis_id'],
            progress=analysis.get('progress'),error=analysis.get('error'),candidate_count=campaign['manifest']['candidate_search_count'])
    return result


def launch(request,body):
    analyses=request.app.state.prop_analyses;id=body.request_id.hex
    with analyses.lock:
        with analyses.connect() as db:previous=db.execute('SELECT payload FROM workflow_prop_simulations WHERE id=?',(id,)).fetchone()
        if previous:
            previous_body=Configuration.model_validate(json.loads(previous[0])['configuration'])
            if previous_body.model_dump(mode='json')!=body.model_dump(mode='json'):raise ValueError('This request ID already belongs to a different simulation.')
            # Revalidate qualification on every explicit launch, even for a cached result.
            qualified(request,body.selections[0])
            saved=json.loads(previous[0])
            for campaign_id in saved['campaign_ids'].values():request.app.state.campaigns.run(campaign_id)
            return public(request,id)
        checked,definitions=check(request,body)
        for declaration in definitions.values():request.app.state.campaigns.create(declaration)
        result=dict(id=id,created_at_utc=datetime.now(timezone.utc).isoformat(),configuration=body.model_dump(mode='json'),
                    qualification=checked['source'],disclosure=DISCLOSURE,campaign_ids={p:d.campaign_id for p,d in definitions.items()})
        with analyses.connect() as db:
            db.execute('INSERT INTO workflow_prop_simulations VALUES (?,?,?)',(id,result['created_at_utc'],json.dumps(result)))
            db.executemany('INSERT INTO workflow_prop_sim_phases VALUES (?,?,?)',[(id,p,d.campaign_id) for p,d in definitions.items()])
        for phase in ('evaluation','funded'):request.app.state.campaigns.run(result['campaign_ids'][phase])
    return public(request,id)


router=APIRouter(prefix='/api/prop-sim')


@router.get('/candidates')
async def sources(request:Request):return await invoke(candidates,request)


@router.get('/defaults')
def defaults():
    from .prop.native_engine import Rules
    from .prop.phase_profiles import EvaluationProfile,FundedProfile
    from .prop.rule_provenance import profile_review
    return dict(profile_id=PROFILE,rule_version=rule_version(PROFILE),disclosure=DISCLOSURE,size_limits=SIZE_LIMITS,
        rule_provenance=dict(evaluation=profile_review(EvaluationProfile(PROFILE,rule_version(PROFILE),'49','129'),'evaluation'),
                             funded=profile_review(FundedProfile(PROFILE,rule_version(PROFILE)),'funded')),
        evaluation_rules=dict(account_size=50000,profit_target=3000,maximum_drawdown=2000,daily_loss_limit=1000,expiry_weekdays=21),
        funded_rules=asdict(Rules()),maximum_selected_configurations=1,
        defaults=dict(evaluation_minimum_micros=1,evaluation_maximum_micros=10,
            funded_minimum_micros=1,funded_maximum_micros=10,simulations=1000,seed=42,block_weekdays=5,
            evaluation_price='49',activation_fee='129',commission_per_mnq_side='0.51',funded_horizon_calendar_days=90,
            receipt_delay_calendar_days=2,maximum_funded_breach_probability=None))


@router.post('/check')
async def preview(body:Configuration,request:Request):
    checked,_=await invoke(check,request,body);return checked


@router.post('',status_code=202)
async def run(body:Configuration,request:Request):return await invoke(launch,request,body)


@router.get('')
async def history(request:Request):
    def read():
        with request.app.state.prop_analyses.connect() as db:
            return dict(items=[json.loads(r[0]) for r in db.execute('SELECT payload FROM workflow_prop_simulations ORDER BY created DESC LIMIT 50')])
    return await invoke(read)


@router.get('/{id}')
async def status(id:UUID,request:Request):return await invoke(public,request,id.hex)


@router.get('/{id}/results/{phase}')
async def results(id:UUID,phase:str,request:Request):
    if phase not in ('evaluation','funded'):raise HTTPException(404,'Unknown phase.')
    saved=await invoke(public,request,id.hex)
    return await invoke(request.app.state.campaigns.report,saved['campaign_ids'][phase])


@router.post('/{id}/cancel')
async def stop(id:UUID,request:Request):
    saved=await invoke(public,request,id.hex)
    for phase in saved['phases'].values():
        if phase['analysis_id'] and phase['status'] in ('queued','running'):
            await invoke(request.app.state.prop_analyses.cancel_phase,phase['analysis_id'])
    return await invoke(public,request,id.hex)
