"""Nested research orchestration using ordinary backtests and AnalysisStore.

Inner qualification feeds independent phase selection and predeclared references.
Durable freezes precede chronological outer replay; reliability remains descriptive.
"""
import csv
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from pydantic import Field, StrictInt, model_validator

from .backtest_api import run_backtest
from .backtest_requests import ExecutionSettings
from .edge_qualification import QualificationSettings, effective_configuration_identity, qualify_candidates
from .execution_scenarios import ExecutionScenario
from .optimization_cache import artifacts, engine_identity
from .prop.adapter import canonical, source_record
from .prop.store import seal_report, sealed_checks
from .research import ResearchConflict
from .research_campaigns import CandidateSource, StrictModel, fingerprint
from .research_folds import FoldSettings, SessionDateRange, generate_folds, inventory_sessions
from .research_complexity import describe_complexity
from .research_regimes import RegimeSettings, build_regime_evidence
from .research_reliability import ReliabilitySettings
from .research_procedure import TerminalSelection, FinalEvidenceRules
from .research_phase_selection import (BaselineDeclaration, PhaseStudy, baseline_study, build_reference_context,
    freeze_reference, reference_training_metadata, build_search, build_training_context, complete_qualified_membership,
    freeze_policy, application_scope, training_role, replay_native_package, policy_training_metadata, resolved_study, select_evaluation, select_funded, validate_native_policies)
from .prop.phase_dispatch import module_for
from .prop.phase_search import validate_phase_work
from .reporting import json_value
from .session_calendar import session_date
from .strategies.registry import get_strategy


class RobustResearchRequest(StrictModel):
    campaign_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    name: str = Field(default='Nested research', min_length=1, max_length=120)
    source_backtest_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    sources: list[CandidateSource] = Field(min_length=1)
    folds: FoldSettings = Field(default_factory=FoldSettings)
    qualification: QualificationSettings = Field(default_factory=QualificationSettings)
    execution_scenarios: list[ExecutionScenario] = Field(default_factory=list, max_length=12)
    regimes: RegimeSettings = Field(default_factory=RegimeSettings)
    economic_studies: list[PhaseStudy] = Field(default_factory=list, max_length=2)
    baselines: list[BaselineDeclaration] = Field(default_factory=list,max_length=16)
    reliability: ReliabilitySettings | None = None
    terminal_selection: TerminalSelection = Field(default_factory=TerminalSelection)
    final_evidence: FinalEvidenceRules = Field(default_factory=FinalEvidenceRules)
    confirmed_economic_candidate_count: StrictInt | None = Field(default=None, ge=1)
    confirmed_backtest_count: int | None = Field(default=None, ge=1)

    @model_validator(mode='after')
    def unique_scenarios(self):
        if any(source.sizing_policies is not None for source in self.sources):
            raise ValueError('Inner qualification uses saved strategy quantities; declare prop sizing policies in the separate phase-selection stage.')
        if len({study.phase for study in self.economic_studies}) != len(self.economic_studies):
            raise ValueError('Declare each independent economic phase at most once.')
        validate_native_policies(self.economic_studies)
        if self.baselines and not self.economic_studies:
            raise ValueError('Predeclared references require an independent economic phase study.')
        if len({b.id for b in self.baselines})!=len(self.baselines):
            raise ValueError('Reference IDs must be unique.')
        identities=[fingerprint({k:v for k,v in b.model_dump(mode='json').items() if k not in ('id','required')}) for b in self.baselines]
        if len(set(identities))!=len(identities):
            raise ValueError('Duplicate reference definitions do not create additional evidence.')
        names = [s.name for s in self.execution_scenarios]
        if len(set(names)) != len(names) or 'baseline' in names:
            raise ValueError('Scenario names must be unique and cannot use the reserved name baseline.')
        return self


class ResearchCancelled(Exception):
    pass


from .research_procedure_store import ProcedureStore


class RobustResearchStore(ProcedureStore):
    """Campaign records reference results in the existing analysis catalogue."""

    def __init__(self, datasets, campaigns):
        self.datasets, self.campaigns = datasets, campaigns
        self.runs, self.analyses = campaigns.runs, campaigns.analyses
        with self.analyses.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS robust_research (
                    id TEXT PRIMARY KEY, created TEXT NOT NULL, declaration TEXT NOT NULL,
                    plan TEXT NOT NULL, analysis_id TEXT, cancel_requested INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS robust_research_steps (
                    campaign_id TEXT NOT NULL, step_key TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(campaign_id,step_key));
                CREATE TABLE IF NOT EXISTS research_access_intervals (
                    id TEXT PRIMARY KEY, source_sha256 TEXT NOT NULL, source_timezone TEXT NOT NULL,
                    convention TEXT NOT NULL, first_session TEXT NOT NULL, last_session TEXT NOT NULL,
                    purpose TEXT NOT NULL, campaign_id TEXT NOT NULL, created TEXT NOT NULL);
            ''')
        self._init_procedures()

    @staticmethod
    def _scope(outer):
        return 'application:'+outer['application_id'] if 'application_id' in outer else outer['index']

    def preview(self, body):
        anchor = source_record(self.runs, body.source_backtest_id)
        from .trade_imports import external
        if external(anchor):
            raise ValueError('Imported trades cannot run native nested research without the corresponding strategy and price dataset.')
        expanded, origins, _ = self.campaigns.resolve_sources(body.sources)
        ids = sorted({ref['run_id'] for _, refs in expanded for ref in refs})
        if any(source.trade_file for source in body.sources):
            raise ValueError('Nested native research reruns strategies; external trade sources require the standalone import milestone.')
        if any(source.sizes != [1] for source in body.sources):
            raise ValueError('Inner qualification uses saved strategy quantities; declare sizes [1]. Prop sizing is a later stage.')
        candidates, common, starts, ends, utc_starts, utc_ends = [], None, [], [], [], []
        sizing_by_strategy, signal_signatures = {}, set()
        for id in ids:
            saved = source_record(self.runs, id)
            if external(saved):
                raise ValueError('Imported candidate trades cannot run native nested research without a local strategy and price dataset.')
            meta = saved['run_metadata']
            research = meta.get('research', {})
            if meta.get('execution_scenario') is not None:
                raise ValueError('Nested research cannot use scenario-bearing IS sources; choose the original baseline source and declare scenarios in this research plan.')
            if research.get('phase') != 'is':
                raise ValueError('Nested research candidates must come from declared IS reports; OOS cannot supply candidates.')
            plan = research['plan']
            strategy = meta['strategy']
            definition = get_strategy(strategy['id'])
            expected = json.loads(json.dumps(definition.provenance(definition.parameters(strategy['parameters'])), default=json_value))
            # Actual replay enriches session_flattening with instrument-specific
            # observations and plan digests. Registry source_sha256 already pins
            # the strategy, calendar implementation and calendar bytes; retain
            # the full saved evidence in the manifest hash, not a default-NQ
            # runtime-metadata equality check.
            expected.pop('session_flattening', None)
            if any(strategy.get(k) != v for k, v in expected.items()):
                raise ValueError('Strategy implementation changed since this report; save a new IS source.')
            protocol = dict(dataset=meta['dataset'], instrument=meta['instrument'], execution=saved['execution_settings'])
            if common is not None and canonical(common) != canonical(protocol):
                raise ValueError('Candidates need identical dataset identity and execution settings.')
            common = protocol
            starts.append(plan['is_start']); ends.append(plan['is_end'])
            utc_starts.append(datetime.fromisoformat(saved['period_start_utc'].replace('Z', '+00:00')))
            utc_ends.append(datetime.fromisoformat(saved['period_end_utc'].replace('Z', '+00:00')))
            identity = dict(strategy_id=strategy['id'], parameters=strategy['parameters'])
            complexity = describe_complexity(strategy['id'], strategy['parameters'])
            non_signal = sorted(complexity['sizing_parameters'] + complexity['diagnostic_parameters'])
            key = fingerprint(identity)
            candidate = dict(id=key, **identity, non_signal_parameters=non_signal, complexity=complexity,
                numeric_parameters=sorted(p['name'] for p in definition.description()['parameters'] if p['type'] in ('int', 'Decimal')))
            effective = effective_configuration_identity(candidate)
            sizing = {name:effective['parameters'][name] for name in complexity['sizing_parameters']}
            if strategy['id'] in sizing_by_strategy and sizing_by_strategy[strategy['id']] != sizing:
                raise ValueError('Signal qualification requires one fixed source-sizing configuration per strategy. Search position-sizing policies in the prop stage.')
            sizing_by_strategy[strategy['id']] = sizing
            signature = canonical(effective)
            if signature in signal_signatures:
                raise ValueError('Duplicate effective signal configurations; diagnostic switches, inactive parameters and equivalent numeric spellings do not create independent candidates.')
            signal_signatures.add(signature)
            if any(c['id'] == key for c in candidates):
                raise ValueError('Duplicate strategy/parameter configurations; choose each once.')
            candidates.append(dict(candidate, source_backtest_id=id,
                source_manifest_sha256=fingerprint(saved), strategy=strategy))
        if anchor['run_metadata'].get('research', {}).get('phase') != 'is':
            raise ValueError('Start nested research from a declared IS report.')
        if anchor['run_metadata']['dataset'] != common['dataset']:
            raise ValueError('Anchor and candidate datasets must match.')
        dataset = self.datasets.get(common['dataset']['id'])
        if dataset is None or any(dataset.get(k) != v for k, v in common['dataset'].items()):
            raise ValueError('The saved dataset is unavailable or its identity changed.')
        if any(dataset.get(k) != v for k, v in common['instrument'].items()):
            raise ValueError('Dataset instrument identity changed since the source report; save a new IS source.')
        # Only session metadata is inspected here; no existing backtest outcome
        # enters candidate admission. A cold start will be used in every window.
        inventory = inventory_sessions(self.datasets, dataset['id'])
        start, end = max(starts), min(ends)
        first_utc, last_utc = max(utc_starts), min(utc_ends)
        sessions = [s for s in inventory['sessions'] if start <= s <= end
            and datetime.fromisoformat(inventory['bounds'][s]['first_utc'].replace('Z', '+00:00')) >= first_utc
            and datetime.fromisoformat(inventory['bounds'][s]['last_utc'].replace('Z', '+00:00')) <= last_utc]
        inventory=dict(inventory,sessions=sessions,**{key:{day:inventory[key][day] for day in sessions} for key in ('counts','bounds','session_content_sha256')})
        folds = generate_folds(sessions, body.folds)
        count = len(candidates) * sum((2 + len(body.execution_scenarios)) * len(f['inner']) for f in folds)
        economic_plan = self._economic_preview(body.economic_studies,candidates,folds,body.baselines,inventory)
        count += economic_plan['estimated_training_backtests'] + economic_plan['estimated_outer_backtests']
        if body.confirmed_economic_candidate_count is not None and body.confirmed_economic_candidate_count != economic_plan['maximum_phase_candidates']:
            raise ValueError('Economic candidate count changed; review and confirm the new preview.')
        if body.confirmed_backtest_count is not None and body.confirmed_backtest_count != count:
            raise ValueError(f'Estimated backtest count changed to {count}; review the plan again.')
        # Cross-strategy prior access is disclosed. This is not an untouched-data
        # certificate: source reports already cover the development window.
        with self.runs.connect() as db:
            access = [dict(run_id=id, research=json.loads(raw).get('run_metadata', {}).get('research'))
                for id, raw in db.execute("SELECT id,manifest FROM runs WHERE json_extract(manifest,'$.run_metadata.dataset.sha256')=?",
                                         (dataset['sha256'],))]
        qualification = body.qualification.model_dump(mode='json')
        qualification['required_scenarios'] = sorted(set(qualification['required_scenarios']) | {s.name for s in body.execution_scenarios})
        result = dict(schema_version='nested-research-v2', name=body.name,
            source_backtest_id=body.source_backtest_id, candidates=sorted(candidates, key=lambda c: c['id']),
            dataset=common['dataset'], instrument=common['instrument'], execution_settings=common['execution'], folds=folds,
            convention=inventory['convention'], session_inventory=inventory,
            estimated_backtests=count, optimization_grids=origins, engine_identity=engine_identity(),
            qualification=qualification,
            economic_studies=[study.model_dump(mode='json') for study in body.economic_studies], economic_plan=economic_plan, baselines=[reference.model_dump(mode='json') for reference in body.baselines],
            reliability=((body.reliability or ReliabilitySettings()).model_dump(mode='json') if body.economic_studies else None),
            execution_scenarios=[s.model_dump(mode='json') for s in body.execution_scenarios],
            regimes=body.regimes.model_dump(mode='json'),
            terminal_selection=body.terminal_selection.model_dump(mode='json'),final_evidence=body.final_evidence.model_dump(mode='json'),
            prior_access=dict(status='previously_accessed_development', reports=access,
                external_access='unknown', untouched=False),
            limitations=[
                'Inner research uses cold starts; training state and open positions are not carried into validation.',
                'Fold lengths count observed sessions. Missing market sessions are not inferred.',
                'Whole-session purge/embargo is declared, not inferred from an unknown feature or label horizon.',
                'Saved source configurations may already reflect prior research; this is not an untouched history claim.',
                ('Economic phases are independent; frozen policies are evaluated on their chronological outer windows. Reliability and deployment remain pending.' if body.economic_studies else 'Economic selection and outer replay are disabled; no deployment recommendation.'),
                'Selected execution scenarios rerun the strategy and fills on the same validation window; all selected scenarios gate admission.',
                'Regime thresholds fit only inner training; entry labels use strictly earlier completed bars and unknown classifications remain visible.',
                'OHLC limit penetration and extra stop slippage are declared sensitivity assumptions, not measured order-book execution probabilities.'])
        result['input_identity'] = fingerprint({k:v for k,v in result.items() if k != 'prior_access'})
        return result

    def _economic_preview(self, studies, candidates, folds, baselines=(), inventory=None):
        counts=[];resolved=[]
        historical_refits=historical_paths=historical_path_days=0
        native_bar_work=0
        def native_bound(request,outer,membership):
            native=request.get('native_execution')
            if native is None or inventory is None:return 0
            bars=sum(inventory['counts'][day] for day in outer['train']['sessions'])
            block=request['candidates'][0]['sampling']['block_weekdays']
            draws=(len(outer['test']['sessions'])+block-1)//block
            paths=sum(c['simulation']['simulations'] for c in request['candidates'])
            history=request.get('conservative_objective')
            if history:paths+=membership*history['replicates']*history['simulations_per_replicate']
            return bars*(1+2*draws)*paths
        for study in studies:
            per_fold=len(candidates)*len(study.profiles)*len(study.policies)
            counts.append(dict(phase=study.phase,profile_count=len(study.profiles),policy_count=len(study.policies),
                max_candidates_per_fold=per_fold,selector=study.selector))
            for outer in folds:
                effective=resolved_study(study,outer)
                context=dict(training_sources={c['source_backtest_id']:{} for c in candidates},train_window=outer['train'])
                request=build_search(effective,context)
                validate_phase_work(module_for(study.phase).parse_request(request),len(outer['train']['sessions']))
                native_bar_work+=native_bound(request,outer,per_fold)
                history=request.get('conservative_objective')
                if history:
                    applicable=per_fold+sum(reference.phase==study.phase for reference in baselines)
                    fits=applicable*history['replicates'];paths=fits*history['simulations_per_replicate']
                    historical_refits+=fits;historical_paths+=paths
                    historical_path_days+=paths*request['horizon_calendar_days']
                # Calendar closures are declared metadata, never inferred from
                # source gaps. An observed market session must have real bars.
                calendar=request['calendar'];closed=set(calendar['closures'])
                cursor=date.fromisoformat(outer['test']['first_session'])
                end=date.fromisoformat(outer['test']['last_session']);expected=[]
                while cursor<=end:
                    day=cursor.isoformat()
                    if cursor.weekday()<5 and day not in closed:expected.append(day)
                    cursor+=timedelta(days=1)
                if expected!=outer['test']['sessions']:
                    raise ValueError('Outer observed sessions do not match the declared economic calendar. Declare known closures; missing bars cannot become zero-trade sessions.')
                resolved.append(dict(**(dict(outer_fold_index=outer['index']) if 'index' in outer else dict(application_role='terminal_preview')),phase=study.phase,
                    candidate_count=per_fold,calendar=calendar,
                    horizon_calendar_days=request.get('horizon_calendar_days'),
                    cutoff_date_exclusive=(end+timedelta(days=1)).isoformat()))
        for reference in baselines:
            reference_study,candidate=baseline_study(reference,studies,candidates)
            for outer in folds:
                request=build_search(resolved_study(reference_study,outer),dict(
                    training_sources={candidate['source_backtest_id']:{}},train_window=outer['train']))
                validate_phase_work(module_for(reference.phase).parse_request(request),len(outer['train']['sessions']))
                native_bar_work+=native_bound(request,outer,1)
        reference_count=len(baselines)*len(folds)
        return dict(enabled=bool(studies),studies=counts,resolved_folds=resolved,
            maximum_native_bar_work=native_bar_work,native_work_estimate='Conservative full-family upper bound including original-source validation, complete warmup prefixes and all refits; actual addressed owner plans enforce budgets before work.',
            baseline_count=len(baselines),estimated_baseline_training_backtests=reference_count,
            maximum_historical_refits=historical_refits,maximum_historical_inner_paths=historical_paths,
            maximum_historical_path_calendar_days=historical_path_days,
            estimated_baseline_outer_backtests=reference_count,
            estimated_training_backtests=(len(candidates)*len(folds) if studies else 0)+reference_count,
            estimated_outer_backtests=sum(row['max_candidates_per_fold'] for row in counts)*len(folds)+reference_count,
            maximum_phase_candidates=sum(row['max_candidates_per_fold'] for row in counts)*len(folds)+reference_count,
            limitations=[
                'Counts are full-family upper bounds before inner qualification, including every possible frozen outer policy.',
                'Saved-path studies support eligible fixed quantities; explicitly declared native studies rerun actual strategy decisions and fills for account-dependent policies. Their sampled bar work includes every family member and historical refit.',
                'Historical chronological outcomes and training Monte Carlo forecasts remain separate.',
                'Training uses observed session inventory; absent days are not invented as no-trade sessions.',
                'Funded receipts retain kernel_entitlement_unrounded precision; declared receipt lag is not verified bank settlement.',
                'Local rule snapshots and declared closures, fees and receipt timing are not newly verified provider terms.',
                'Source history was previously accessed. Freezing precedes new outer strategy execution and assessment, not all prior byte access.'])

    def create(self, body):
        with self.analyses.lock:
            with self.analyses.connect() as db:
                if db.execute('SELECT 1 FROM research_campaigns WHERE id=?', (body.campaign_id,)).fetchone():
                    raise ResearchConflict('This ID belongs to a phase campaign; use a new research ID.')
                exists = db.execute('SELECT declaration FROM robust_research WHERE id=?', (body.campaign_id,)).fetchone()
            if exists:
                if RobustResearchRequest.model_validate(json.loads(exists[0])).model_dump(mode='json') != body.model_dump(mode='json'):
                    raise ResearchConflict('This research ID has an immutable declaration; use a new ID.')
                return self.get(body.campaign_id)
            plan = self.preview(body)
            if plan['estimated_backtests'] > 128 and body.confirmed_backtest_count != plan['estimated_backtests']:
                raise ValueError(f"Confirm the preview's {plan['estimated_backtests']} backtests before saving this large research plan.")
            if plan['economic_plan']['maximum_phase_candidates'] > 128 and body.confirmed_economic_candidate_count != plan['economic_plan']['maximum_phase_candidates']:
                raise ValueError(f"Confirm the preview's {plan['economic_plan']['maximum_phase_candidates']} economic candidates before saving this large research plan.")
            with self.analyses.connect() as db:
                db.execute('INSERT INTO robust_research(id,created,declaration,plan) VALUES (?,?,?,?)',
                    (body.campaign_id, datetime.now(timezone.utc).isoformat(), canonical(body.model_dump(mode='json')), canonical(plan)))
                source_ids = {body.source_backtest_id, *(c['source_backtest_id'] for c in plan['candidates'])}
                db.executemany('INSERT INTO campaign_sources VALUES (?,?)', [(body.campaign_id, id) for id in source_ids])
                db.executemany('INSERT INTO campaign_jobs VALUES (?,?)',
                    [(body.campaign_id, g['optimization_id']) for g in plan['optimization_grids']])
            return self.get(body.campaign_id)

    def get(self, id):
        with self.analyses.connect() as db:
            row = db.execute('SELECT created,declaration,plan,analysis_id,cancel_requested FROM robust_research WHERE id=?', (id,)).fetchone()
        if not row:
            raise KeyError('Research campaign not found.')
        analysis = self.analyses.get(row[3]) if row[3] else None
        result = dict(campaign_id=id, created=row[0], declaration=json.loads(row[1]), plan=json.loads(row[2]),
            analysis_id=row[3], status=analysis['status'] if analysis else 'validated',
            progress=analysis['progress'] if analysis else 'Plan saved; no research executed.',
            error=analysis['error'] if analysis else None, cancel_requested=bool(row[4]))
        if result['status'] == 'complete':
            result['result'] = self.report(id)['calculations']
        result.update(self._procedure_status(id))
        return result

    def list(self, source_id=None):
        with self.analyses.connect() as db:
            rows = db.execute('SELECT id FROM robust_research WHERE (? IS NULL OR id IN '
                '(SELECT campaign_id FROM campaign_sources WHERE source_id=?)) ORDER BY created DESC LIMIT 100',
                (source_id, source_id)).fetchall()
        return [dict(campaign_id=id, name=(r:=self.get(id))['declaration']['name'], status=r['status'],
                     analysis_id=r['analysis_id'], created=r['created']) for (id,) in rows]

    def report(self, id):
        with self.analyses.connect() as db:
            row = db.execute('SELECT analysis_id FROM robust_research WHERE id=?', (id,)).fetchone()
        if not row or not row[0] or self.analyses.get(row[0])['status'] != 'complete':
            raise ResearchConflict('Research has no completed report.')
        if not self.analyses.fingerprint(row[0]):
            raise ResearchConflict('Saved report failed integrity checks; preserve it and create a new campaign.')
        return json.loads((self.analyses.root/row[0]/'report.json').read_text())

    def check(self, id):
        row = self.get(id)
        fresh = self.preview(RobustResearchRequest.model_validate(row['declaration']))
        if fresh['input_identity'] != row['plan']['input_identity']:
            raise ResearchConflict('Source, code or plan identity changed; save a new research campaign.')
        return dict(status='compatible', input_identity=fresh['input_identity'], prior_access=fresh['prior_access'])

    def run(self, id):
        with self.analyses.lock:
            row = self.get(id)
            if row['status'] in ('queued', 'running', 'complete'):
                return row
            self.check(id)
            analysis_id, created = uuid4().hex, datetime.now(timezone.utc).isoformat()
            with self.analyses.connect() as db:
                if db.execute("SELECT count(*) FROM analyses WHERE status IN ('queued','running')").fetchone()[0] >= 8:
                    raise ResearchConflict('Analysis queue is full; wait before running research.')
                db.execute('INSERT INTO analyses VALUES (?,?,?,?,?,?,NULL)',
                    (analysis_id, row['plan']['input_identity'], row['declaration']['source_backtest_id'], created, 'queued', 'Queued inner research'))
                db.execute('UPDATE robust_research SET analysis_id=?,cancel_requested=0 WHERE id=?', (analysis_id, id))
                db.execute('INSERT INTO campaign_analyses VALUES (?,?)', (id, analysis_id))
                db.execute('INSERT INTO analysis_sources SELECT ?,source_id FROM campaign_sources WHERE campaign_id=?', (analysis_id, id))
            # Inner backtests are synchronous on this existing worker; no nested
            # phase jobs are queued/waited on this worker.
            self.analyses.worker.submit(self._run, id, analysis_id)
            return self.get(id)

    def cancel(self, id):
        row = self.get(id)
        if row['status'] not in ('queued', 'running'):
            raise ResearchConflict('Only queued/running research can be cancelled.')
        with self.analyses.connect() as db:
            db.execute('UPDATE robust_research SET cancel_requested=1 WHERE id=?', (id,))
        return self.get(id)

    def _checkpoint(self, id):
        self._application_checkpoint()
        with self.analyses.connect() as db:
            if db.execute('SELECT cancel_requested FROM robust_research WHERE id=?', (id,)).fetchone()[0]:
                raise ResearchCancelled('Cancelled at a safe checkpoint. Completed backtests remain available; Run resumes them.')

    def _backtest(self, campaign, analysis_id, candidate, outer, inner, role, scenario=None, *,
                  window_override=None, research_extra=None, step_suffix=None):
        id, plan = campaign['campaign_id'], campaign['plan']
        key = f"{self._scope(outer)}:{inner['index']}:{candidate['id']}:{role}"
        if scenario:
            key += ':' + scenario.name
        if step_suffix:
            key += ':' + step_suffix
        with self.analyses.connect() as db:
            row = db.execute('SELECT payload FROM robust_research_steps WHERE campaign_id=? AND step_key=?', (id, key)).fetchone()
        if row:
            saved = json.loads(row[0]); record = self.runs.get(saved['run_id'])
            if not record or artifacts(self.runs.root, record) != saved['artifacts'] or fingerprint(record) != saved['manifest_sha256']:
                raise ResearchConflict('A completed research backtest changed; create a new campaign.')
            return record
        window = window_override or inner['train' if role == 'inner_train' else 'validation']
        self._checkpoint(id)
        # Reserve access before loading bars, even when the attempt fails.
        with self.analyses.lock, self.analyses.connect() as db:
            if role in ('outer_test','baseline_outer_test','final_holdout','final_holdout_reference'):
                seal=self._step(id,f"{self._scope(outer)}:economic_selection")
                if not seal or seal['result']['selection_seal_sha256']!=research_extra.get('selection_seal_sha256'):
                    raise ResearchConflict('Outer access requires its durable immutable selection seal.')
                references=None
                if plan.get('baselines'):
                    references=self._step(id,f"{self._scope(outer)}:baseline_selection")
                    if not references or references['result']['reference_seal_sha256']!=research_extra.get('reference_seal_sha256'):
                        raise ResearchConflict('Every predeclared reference must be frozen before any outer access.')
                allowed=({reference['frozen_package']['package_sha256'] for reference in references['result']['baseline_results']}
                    if role in ('baseline_outer_test','final_holdout_reference') and references else
                    {package['package_sha256'] for phase in seal['result']['phases'] for package in phase['frozen_packages']})
                if research_extra.get('frozen_package_sha256') not in allowed:
                    raise ResearchConflict('Outer policy is outside the sealed selection family.')
            access_id=uuid4().hex
            accessed_at=datetime.now(timezone.utc).isoformat()
            if role in ('outer_test','baseline_outer_test','final_holdout','final_holdout_reference'):
                access=dict(kind='outer_access',access_role=role,**application_scope(outer,context=True),window=window,
                    frozen_package_sha256=research_extra['frozen_package_sha256'],
                    selection_seal_sha256=research_extra['selection_seal_sha256'],access_id=access_id,created_at=accessed_at)
                if research_extra.get('reference_seal_sha256'):
                    access['reference_seal_sha256']=research_extra['reference_seal_sha256']
                if role in ('baseline_outer_test','final_holdout_reference'):access['baseline_id']=research_extra['baseline_id']
                access['access_sha256']=fingerprint(access)
                db.execute('INSERT INTO robust_research_steps VALUES (?,?,?)',(id,'outer_access:'+access_id,canonical(access)))
            db.execute('INSERT INTO research_access_intervals VALUES (?,?,?,?,?,?,?,?,?)',
                (access_id, plan['dataset']['sha256'], plan['dataset']['source_timezone'], plan['convention'],
                 window['first_session'], window['last_session'], role, id, accessed_at))
        dataset = self.datasets.get(plan['dataset']['id'])
        definition = get_strategy(candidate['strategy_id'])
        parameters = definition.parameters(candidate['parameters'])
        config = ExecutionSettings.model_validate(plan['execution_settings']).execution_config(dataset)
        split = dict(is_start=outer['train']['first_session'], is_end=outer['train']['last_session'],
                     oos_start=outer['test']['first_session'], oos_end=outer['test']['last_session'],
                     strategy_id=candidate['strategy_id'], source_sha256=dataset['sha256'],
                     source_timezone=dataset['source_timezone'], convention=plan['convention'], version=2)
        research = dict(phase='inner', role=role, plan=split, campaign_id=id,
            **application_scope(outer), inner_fold=inner['index'], window=window,
            information_cutoff_session=window['last_session'], cold_start=True)
        if research_extra:
            research.update(research_extra)
        if scenario:
            research['execution_scenario'] = scenario.model_dump(mode='json')
        def progress(stage, processed, total):
            if stage != 'done':
                self._checkpoint(id)
            self.analyses._update(analysis_id, 'running',
                f"Outer {self._scope(outer)}/{len(plan['folds'])}, inner {inner['index']}, {candidate['strategy_id']}, {role}: {stage}")
        run_id = uuid4().hex
        # Protect the exact publication ID before it becomes visible in RunStore.
        # Completed-step reuse above is checked explicitly; a new step cannot
        # substitute another cache ID between publication and reference capture.
        with self.analyses.lock, self.analyses.connect() as db:
            db.execute('INSERT INTO campaign_sources VALUES (?,?)', (id, run_id))
            db.execute('INSERT INTO analysis_sources VALUES (?,?)', (analysis_id, run_id))
        try:
            record = run_backtest(self.datasets, self.runs, run_id, dataset, definition, parameters, config,
                SessionDateRange.parse(window['first_session'], window['last_session']), progress,
                prop_analyses=None, report_detail='compact', research=research, reuse_results=False,
                execution_scenario=scenario)
        except Exception:
            # A failed unpublished attempt has no artifact to protect. If the
            # report was already published, retain its references for inspection.
            if self.runs.get(run_id) is None:
                with self.analyses.lock, self.analyses.connect() as db:
                    db.execute('DELETE FROM campaign_sources WHERE campaign_id=? AND source_id=?', (id, run_id))
                    db.execute('DELETE FROM analysis_sources WHERE analysis_id=? AND source_id=?', (analysis_id, run_id))
            raise
        saved = dict(kind='backtest', run_id=record['id'], manifest_sha256=fingerprint(record), artifacts=artifacts(self.runs.root, record))
        with self.analyses.connect() as db:
            db.execute('INSERT INTO robust_research_steps VALUES (?,?,?)', (id, key, canonical(saved)))
            db.execute('INSERT OR IGNORE INTO campaign_sources VALUES (?,?)', (id, record['id']))
            db.execute('INSERT OR IGNORE INTO analysis_sources VALUES (?,?)', (analysis_id, record['id']))
        return record

    def _trades(self, record):
        with (self.runs.root/record['id']/'trades.csv').open(newline='') as stream:
            return list(csv.DictReader(stream))

    def _evidence(self, record, window, index):
        sessions = {day:dict(session=day, net_pnl=Decimal(0), trade_count=0) for day in window['sessions']}
        for trade in self._trades(record):
            entry = session_date(datetime.fromisoformat(trade['entry_time_utc'].replace('Z', '+00:00'))).isoformat()
            day = session_date(datetime.fromisoformat(trade['exit_time_utc'].replace('Z', '+00:00'))).isoformat()
            if entry not in sessions or day not in sessions:
                raise ValueError('A trade crossed its validation information boundary.')
            sessions[day]['net_pnl'] += Decimal(trade['net_pnl'])
            sessions[day]['trade_count'] += 1
        return dict(fold_index=index, scope='inner_validation',
            sessions=[dict(row, net_pnl=str(row['net_pnl'])) for row in sessions.values()])

    def _step(self, id, key):
        with self.analyses.connect() as db:
            row=db.execute('SELECT payload FROM robust_research_steps WHERE campaign_id=? AND step_key=?',(id,key)).fetchone()
        if not row:return None
        value=json.loads(row[0]);self._verify_step(value)
        return value

    def _save_step(self, id, key, payload):
        with self.analyses.lock, self.analyses.connect() as db:
            row=db.execute('SELECT payload FROM robust_research_steps WHERE campaign_id=? AND step_key=?',(id,key)).fetchone()
            if row:
                if canonical(json.loads(row[0]))!=canonical(payload):
                    raise ResearchConflict('A completed research checkpoint is immutable; create a new campaign.')
            else:
                db.execute('INSERT INTO robust_research_steps VALUES (?,?,?)',(id,key,canonical(payload)))
        return payload

    def _verify_step(self, saved):
        kind=saved.get('kind','backtest')
        if kind=='backtest':
            record=self.runs.get(saved['run_id'])
            if (not record or fingerprint(record)!=saved['manifest_sha256']
                    or artifacts(self.runs.root,record)!=saved['artifacts']):
                raise ResearchConflict('Generated research backtest changed; no changed checkpoint can be reused.')
        elif kind=='phase_analysis':
            if self.analyses.fingerprint(saved['analysis_id'])!=saved['fingerprint']:
                raise ResearchConflict('Nested phase calculation artifacts changed; create a new campaign.')
        elif kind=='outer_access':
            if fingerprint({k:v for k,v in saved.items() if k!='access_sha256'})!=saved['access_sha256']:
                raise ResearchConflict('Outer access journal changed.')
        elif kind in ('selection_seal','baseline_seal','chronological_replay'):
            if fingerprint(saved['result'])!=saved['result_sha256']:
                raise ResearchConflict('Saved nested selection/replay identity changed.')
            if kind=='chronological_replay':
                self._verify_step(saved['outer_source'])
            if kind in ('selection_seal','baseline_seal'):
                rows=(saved['result'].get('phases',[]) if kind=='selection_seal' else
                      [dict(reference,frozen_packages=[reference['frozen_package']]) for reference in saved['result']['baseline_results']])
                for phase in rows:
                    check=self.analyses.fingerprint(phase['analysis_id'])
                    if not check or check['files']['report.json']!=phase['training_report_sha256']:
                        raise ResearchConflict('Frozen training report changed after selection.')
                    for package in phase['frozen_packages']:
                        if fingerprint({k:v for k,v in package.items() if k!='package_sha256'})!=package['package_sha256']:
                            raise ResearchConflict('Frozen outer policy changed after selection.')
        else:
            raise ResearchConflict('Unknown nested research checkpoint type.')

    def _journal(self,id):
        with self.analyses.connect() as db:
            rows=db.execute('SELECT rowid,step_key,payload FROM robust_research_steps WHERE campaign_id=? ORDER BY rowid',(id,)).fetchall()
        result=[]
        for sequence,key,payload in rows:
            value=json.loads(payload);kind=value.get('kind','backtest')
            if kind=='selection_seal':
                result.append(dict(sequence=sequence,kind=kind,step_key=key,selection_seal_sha256=value['result']['selection_seal_sha256'],
                    frozen_package_sha256=[p['package_sha256'] for phase in value['result']['phases'] for p in phase['frozen_packages']],
                    status=value['result']['status'],created_at=value['result'].get('sealed_at_utc')))
            elif kind=='baseline_seal':
                result.append(dict(sequence=sequence,kind=kind,step_key=key,reference_seal_sha256=value['result']['reference_seal_sha256'],
                    frozen_package_sha256=[reference['frozen_package']['package_sha256'] for reference in value['result']['baseline_results']],
                    baseline_ids=[reference['baseline_id'] for reference in value['result']['baseline_results']],
                    status=value['result']['status'],created_at=value['result'].get('sealed_at_utc')))
            elif kind=='outer_access':
                result.append(dict(value,sequence=sequence,step_key=key))
        return result

    def _verify_steps(self, id):
        with self.analyses.connect() as db:
            steps=db.execute('SELECT payload FROM robust_research_steps WHERE campaign_id=? ORDER BY rowid',(id,)).fetchall()
        for (payload,) in steps:self._verify_step(json.loads(payload))
        with self.analyses.connect() as db:
            plan=json.loads(db.execute('SELECT plan FROM robust_research WHERE id=?',(id,)).fetchone()[0])
        seals={};reference_seals={}
        for event in self._journal(id):
            if event['kind']=='selection_seal':seals[event['selection_seal_sha256']]=event
            elif event['kind']=='baseline_seal':reference_seals[event['reference_seal_sha256']]=event
            else:
                seal=seals.get(event['selection_seal_sha256'])
                reference=reference_seals.get(event.get('reference_seal_sha256'))
                if not seal or seal['sequence']>=event['sequence']:
                    raise ResearchConflict('Outer access did not follow its immutable selection journal seal.')
                if plan.get('baselines') and (not reference or reference['sequence']>=event['sequence']):
                    raise ResearchConflict('Outer access occurred before all predeclared references were frozen.')
                permitted=reference if event.get('access_role') in ('baseline_outer_test','final_holdout_reference') else seal
                if not permitted or event['frozen_package_sha256'] not in permitted['frozen_package_sha256']:
                    raise ResearchConflict('Outer access is outside its frozen selected/reference family.')

    def _phase_report(self,campaign,analysis_id,outer,study,context,key):
        id=campaign['campaign_id'];request=build_search(study,context)
        input_sha=fingerprint(dict(request=request,training_context=context))
        step=self._step(id,key)
        if step:
            if step['input_sha256']!=input_sha:
                raise ResearchConflict('Nested phase request differs from its completed checkpoint.')
            child=self.analyses.get(step['analysis_id'])
        else:
            child=self.analyses.run_phase_inline(self.runs,module_for(study.phase).parse_request(request),
                training_context=context,checkpoint=lambda:self._checkpoint(id),datasets=self.datasets,
                progress=lambda message:self.analyses._update(analysis_id,'running',
                    f"Outer {self._scope(outer)} {study.phase}: {message}"))
            step=dict(kind='phase_analysis',analysis_id=child['id'],input_sha256=input_sha,
                      fingerprint=self.analyses.fingerprint(child['id']))
            self._save_step(id,key,step)
        report=json.loads((self.analyses.root/child['id']/'report.json').read_text())
        if report['request']!=request or report.get('training_context')!=context:
            raise ResearchConflict('Nested phase report source membership or context changed.')
        calculated=report['calculations']['candidates']
        if (len(calculated)!=len(request['candidates']) or len({r['candidate_id'] for r in calculated})!=len(calculated)
                or sorted(canonical(r['manifest']['configuration']) for r in calculated)!=sorted(canonical(c) for c in request['candidates'])):
            raise ResearchConflict('Phase calculation omitted or duplicated a declared candidate configuration.')
        return report,step

    def _prepare_baselines(self,campaign,analysis_id,outer,qualification):
        id=campaign['campaign_id'];plan=dict(campaign['plan'],campaign_id=id)
        declarations=[BaselineDeclaration.model_validate(value) for value in plan.get('baselines',[])]
        if not declarations:return None
        key=f"{self._scope(outer)}:baseline_selection"
        identity=fingerprint(dict(declarations=plan['baselines'],qualification=qualification,outer=outer,input_identity=plan['input_identity']))
        saved=self._step(id,key)
        if saved:
            if saved['input_sha256']!=identity:raise ResearchConflict('Predeclared reference inputs changed after freeze.')
            return saved['result']
        studies=[PhaseStudy.model_validate(value) for value in plan['economic_studies']]
        edge={row['candidate_id']:row for row in qualification['candidates']};results=[]
        for reference in declarations:
            self._checkpoint(id)
            study,candidate=baseline_study(reference,studies,plan['candidates'])
            research=reference_training_metadata(id,outer,reference,plan['input_identity'])
            record=self._backtest(campaign,analysis_id,candidate,outer,dict(index=-3),training_role(outer,reference=True),
                window_override=outer['train'],research_extra=research,step_suffix=fingerprint(reference.model_dump(mode='json')))
            context=build_reference_context(plan,outer,reference,candidate,record,artifacts(self.runs.root,record))
            study=resolved_study(study,outer)
            report,step=self._phase_report(campaign,analysis_id,outer,study,context,
                f"{self._scope(outer)}:baseline_phase:{fingerprint(reference.model_dump(mode='json'))}")
            forecast=report['calculations']['candidates'][0]
            package=freeze_reference(id,outer,study,context,report,step['fingerprint']['files']['report.json'],forecast,reference)
            results.append(dict(baseline_id=reference.id,phase=reference.phase,required=reference.required,
                source_configuration_id=candidate['id'],recommendation_eligible=False,
                edge_qualification={k:edge[candidate['id']][k] for k in ('candidate_id','status','reasons')},
                analysis_id=report['id'],training_report_sha256=step['fingerprint']['files']['report.json'],
                training_context_sha256=context['context_sha256'],training_forecast={k:v for k,v in forecast.items() if k not in ('paths','component','provenance')},
                frozen_package=package,provider_rules=report.get('provider_rules'),deployment_readiness=report.get('deployment_readiness'),
                status='REFERENCE_FROZEN',interpretation='Measured predeclared reference; edge/forecast status does not authorize recommendation.'))
        result=dict(status='REFERENCES_FROZEN',baseline_results=results,sealed_at_utc=datetime.now(timezone.utc).isoformat())
        result['reference_seal_sha256']=fingerprint(result)
        self._save_step(id,key,dict(kind='baseline_seal',input_sha256=identity,result=result,result_sha256=fingerprint(result)))
        return result

    def _select_economic(self,campaign,analysis_id,outer,qualification):
        id=campaign['campaign_id'];plan=dict(campaign['plan'],campaign_id=id)
        studies=[PhaseStudy.model_validate(value) for value in plan.get('economic_studies',[])]
        if not studies:return None
        key=f"{self._scope(outer)}:economic_selection"
        membership=complete_qualified_membership(plan['candidates'],qualification)
        selection_input=fingerprint(dict(qualification=qualification,studies=plan['economic_studies'],
                                         outer=outer,input_identity=plan['input_identity']))
        saved=self._step(id,key)
        if saved:
            if saved['input_sha256']!=selection_input:
                raise ResearchConflict('Economic selection inputs changed after freeze.')
            return saved['result']
        records={};hashes={}
        for candidate in membership['configurations']:
            research=policy_training_metadata(id,outer,membership,plan['input_identity'])
            record=self._backtest(campaign,analysis_id,candidate,outer,dict(index=-1),training_role(outer),
                window_override=outer['train'],research_extra=research)
            records[candidate['id']]=record
            hashes[candidate['id']]=artifacts(self.runs.root,record)
        phases=[];context=None
        if records:
            context=build_training_context(plan,outer,membership,records,hashes)
            for original in studies:
                self._checkpoint(id)
                study=resolved_study(original,outer)
                report,step=self._phase_report(campaign,analysis_id,outer,study,context,f"{self._scope(outer)}:phase:{study.phase}")
                request=report['request'];child=dict(id=report['id'])
                decision=(select_evaluation(report['calculations'],study.selector) if study.phase=='evaluation' else
                          select_funded(report['calculations'],study.selector,request))
                chosen=[row for row in report['calculations']['candidates'] if row['candidate_id'] in decision['selected_ids']]
                report_sha=step['fingerprint']['files']['report.json']
                packages=[freeze_policy(id,outer,study,context,report,report_sha,row) for row in chosen]
                phases.append(dict(phase=study.phase,analysis_id=child['id'],decision=decision,frozen_packages=packages,
                    training_forecasts=[{k:row[k] for k in ('candidate_id','status','manifest','metrics','uncertainty','feasible','constraint_failures','constraint_violations','conservative_expected_cash') if k in row} for row in chosen],
                    complete_search_candidate_count=len(report['calculations']['candidates']),
                    provider_rules=report.get('provider_rules'),deployment_readiness=report.get('deployment_readiness'),
                    training_context_sha256=context['context_sha256'],training_report_sha256=report_sha))
        selected=sum(bool(phase['frozen_packages']) for phase in phases)
        status=(membership['status'] if not records else 'SELECTION_FROZEN' if selected==len(phases) else
                'PARTIAL_SELECTION' if selected else 'INSUFFICIENT_EVIDENCE' if any(p['decision']['status']=='INSUFFICIENT_EVIDENCE' for p in phases) else 'NO_FEASIBLE_POLICY')
        result=dict(version='nested-phase-selection-v1',status=status,membership=membership,phases=phases,
            training_context=context,outer_test_status='not_read' if selected else 'selection_abstained',
            deployment_recommendation=None,
            limitations=['Families are evaluated separately; no implicit portfolio weights or ex-post winner.',
                         'No phase or last-fold winner is a deployment recommendation.'])
        # Durable seal precedes every access event and outer normal backtest.
        self._checkpoint(id)
        result['sealed_at_utc']=datetime.now(timezone.utc).isoformat()
        result['selection_seal_sha256']=fingerprint(result)
        self._save_step(id,key,dict(kind='selection_seal',input_sha256=selection_input,result=result,result_sha256=fingerprint(result)))
        return result

    def _replay_package(self,campaign,analysis_id,outer,selection,package,references=None):
        from .prop.phase_profiles import (SavedTradeSource, EvaluationProfile, FundedProfile,
            SourceCosts, SizingConfiguration, ReplayWindow)
        from .prop.phase_search import PhaseCalendar
        from .prop.evaluation_optimization import SequentialRetry
        from .prop.evaluation_profiles import replay_evaluation_profile
        from .prop.funded_profiles import replay_funded_profile
        id=campaign['campaign_id'];phase=package['phase']
        reference=package.get('package_role')=='predeclared_reference'
        role=(('final_holdout_reference' if reference else 'final_holdout') if 'application_id' in outer else ('baseline_outer_test' if reference else 'outer_test'))
        reference_seal=references['reference_seal_sha256'] if references else None
        self._checkpoint(id)
        key=f"{self._scope(outer)}:chronological:{phase}:{package['candidate_id']}"
        saved=self._step(id,key)
        if saved:
            if (saved['package_sha256']!=package['package_sha256'] or saved['selection_seal_sha256']!=selection['selection_seal_sha256']
                    or saved.get('reference_seal_sha256')!=reference_seal):
                raise ResearchConflict('Chronological checkpoint differs from its frozen selected/reference choice.')
            return saved['result']
        config=package['configuration'];strategy=package['strategy']
        candidate=dict(id=package['candidate_id'],strategy_id=strategy['id'],parameters=strategy['parameters'])
        research=dict(phase='outer',role=role,frozen_package_sha256=package['package_sha256'],
            selection_seal_sha256=selection['selection_seal_sha256'],training_source_id=config['source']['source_backtest_id'],
            selected_candidate_id=package['candidate_id'])
        if reference_seal:research['reference_seal_sha256']=reference_seal
        if reference:
            research.update(baseline_id=package['baseline_id'],reference_declaration_sha256=package['reference_declaration_sha256'],
                recommendation_eligible=False)
        record=self._backtest(campaign,analysis_id,candidate,outer,dict(index=-2),role,
            window_override=outer['test'],research_extra=research,step_suffix=phase)
        if package.get('native_execution') is not None:
            record,output=replay_native_package(self.datasets,self.runs,self.analyses,id,analysis_id,record,package,
                checkpoint=lambda:self._checkpoint(id),progress=lambda message:self.analyses._update(analysis_id,'running',message))
        else:
            calendar=deepcopy(package['calendar'])
            calendar['start_dates']=tuple(calendar['start_dates']);calendar['closures']=tuple(calendar.get('closures',[]))
            common=dict(runs=self.runs,source=SavedTradeSource(**dict(config['source'],source_backtest_id=record['id'])),
                micros=config['micros'],window=ReplayWindow(package['outer_window']['first_session'],package['outer_window']['cutoff_date_exclusive']),
                calendar=PhaseCalendar(**calendar),max_micros=config['simulation']['max_micros'],
                costs=SourceCosts(**config['costs']),sizing=SizingConfiguration(**config['sizing']) if config.get('sizing') else None,
                frozen_binding=package,checkpoint=lambda:self._checkpoint(id))
            self._step(id,f"{self._scope(outer)}:economic_selection")
            if reference_seal:self._step(id,f"{self._scope(outer)}:baseline_selection")
            if phase=='evaluation':
                output=replay_evaluation_profile(profile=EvaluationProfile(**config['profile']),retry=SequentialRetry(**config['retry']),**common)
            else:
                output=replay_funded_profile(profile=FundedProfile(**config['profile']),
                    receipt_delay_calendar_days=package['receipt_delay_calendar_days'],
                    receipt_amount_convention=package['receipt_amount_convention'],**common)
        result=dict(phase=phase,candidate_id=package['candidate_id'],outer_run_id=record['id'],
            frozen_package_sha256=package['package_sha256'],result=output)
        if reference:result['baseline_id']=package['baseline_id']
        step=dict(kind='chronological_replay',package_sha256=package['package_sha256'],
            selection_seal_sha256=selection['selection_seal_sha256'],reference_seal_sha256=reference_seal,
            result=result,result_sha256=fingerprint(result),
            outer_source=dict(kind='backtest',run_id=record['id'],manifest_sha256=fingerprint(record),artifacts=artifacts(self.runs.root,record)))
        self._save_step(id,key,step)
        return result

    def _replay_economic(self,campaign,analysis_id,outer,selection,references=None):
        if selection is None:return None
        items=[self._replay_package(campaign,analysis_id,outer,selection,package,references)
               for phase in selection['phases'] for package in phase['frozen_packages']]
        return dict(mode='historical_chronological',status='complete' if items else 'selection_abstained',
            selection_seal_sha256=selection['selection_seal_sha256'],items=items,
            interpretation='Actual ordered outer-window source path under frozen model rules; no resampling, no reselection, no deployment qualification.')

    def _replay_baselines(self,campaign,analysis_id,outer,selection,references):
        if references is None:return []
        results=[]
        for reference in references['baseline_results']:
            replay=self._replay_package(campaign,analysis_id,outer,selection,reference['frozen_package'],references)
            results.append(dict(reference,outer_run_id=replay['outer_run_id'],chronological_replay=replay['result'],
                reference_seal_sha256=references['reference_seal_sha256'],status='REFERENCE_MEASURED'))
        return results

    def _write_reliability_csv(self,staged,reliability):
        """Export owner-supplied observations without recomputing statistics."""
        members=[];comparisons=[]
        for phase,value in (reliability or {}).get('phases',{}).items():
            for fold in value.get('folds',[]):
                prefix={key:fold.get(key) for key in ('outer_fold','selection_status','action','family_size','scalar_eligible')}
                for member in fold.get('members',[]) or [{}]:
                    identity=member.get('logical_policy',{})
                    members.append(dict(phase=phase,**prefix,policy_sha256=identity.get('policy_sha256'),
                        **{key:item for key,item in member.items() if key!='logical_policy'}))
            for comparison in value.get('baseline_comparisons',[]):
                prefix={key:item for key,item in comparison.items() if key not in ('pairs',)}
                for pair in comparison.get('pairs',[]) or [{}]:comparisons.append(dict(phase=phase,**prefix,**pair))
        for name,rows in [('reliability_folds.csv',members),('baseline_comparison.csv',comparisons)]:
            fields=sorted({key for row in rows for key in row}) or ['phase','outer_fold','status']
            with (staged/name).open('w',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
                for row in rows:writer.writerow({key:canonical(value) if isinstance(value,(dict,list,tuple)) else value for key,value in row.items()})

    def _qualify_window(self,campaign,analysis_id,outer):
        plan=campaign['plan']
        evidence, backtests, regime_evidence = {}, [], []
        for candidate in plan['candidates']:
            evidence[candidate['id']] = []
            for inner in outer['inner']:
                for role in ('inner_train', 'inner_validation'):
                    record = self._backtest(campaign, analysis_id, candidate, outer, inner, role)
                    backtests.append(dict(candidate_id=candidate['id'], role=role,
                        inner_fold_index=inner['index'], run_id=record['id']))
                    if role == 'inner_validation':
                        inner_evidence = self._evidence(record, inner['validation'], inner['index'])
                        inner_evidence['scenarios'] = {}
                        for settings in plan.get('execution_scenarios', []):
                            scenario = ExecutionScenario.model_validate(settings)
                            stress = self._backtest(campaign, analysis_id, candidate, outer, inner, 'execution_scenario', scenario)
                            backtests.append(dict(candidate_id=candidate['id'], role='execution_scenario',
                                scenario_name=scenario.name, inner_fold_index=inner['index'], run_id=stress['id']))
                            inner_evidence['scenarios'][scenario.name] = self._evidence(stress, inner['validation'], inner['index'])['sessions']
                        regime_settings = RegimeSettings.model_validate(plan.get('regimes', {}))
                        if regime_settings.enabled_names:
                            classified = build_regime_evidence(self.datasets, plan['dataset']['id'], inner['train'],
                                inner['validation'], [dict(t, trade_id=t['trade_number']) for t in self._trades(record)], regime_settings)
                            inner_evidence['regimes'] = classified['regimes']
                            regime_evidence.append(dict(candidate_id=candidate['id'], inner_fold_index=inner['index'], **classified))
                        evidence[candidate['id']].append(inner_evidence)
        qualification = qualify_candidates(
            [dict(id=c['id'], strategy_id=c['strategy_id'], parameters=c['parameters'], numeric_parameters=c['numeric_parameters'],
                  non_signal_parameters=c['non_signal_parameters'], complexity=c['complexity']) for c in plan['candidates']],
            evidence, QualificationSettings.model_validate(plan['qualification']))
        return qualification,evidence,backtests,regime_evidence

    def _run(self, id, analysis_id):
        try:
            self.analyses._update(analysis_id, 'running', 'Checking frozen research inputs')
            self.check(id)
            campaign = self.get(id); plan = campaign['plan']
            folds = []
            for outer in plan['folds']:
                qualification,evidence,backtests,regime_evidence=self._qualify_window(campaign,analysis_id,outer)
                selection=self._select_economic(campaign,analysis_id,outer,qualification)
                references=self._prepare_baselines(campaign,analysis_id,outer,qualification)
                replay=self._replay_economic(campaign,analysis_id,outer,selection,references)
                baseline_results=self._replay_baselines(campaign,analysis_id,outer,selection,references)
                folds.append(dict(index=outer['index'], qualification=qualification, backtests=backtests,
                    inner_evidence=evidence, regime_evidence=regime_evidence,economic_selection=selection,chronological_replay=replay,baseline_results=baseline_results,
                    outer_test_status=replay['status'] if replay else 'not_run',
                    policy_selection_status=selection['status'] if selection else 'not_run'))
            self._checkpoint(id)
            self.check(id)
            self._verify_steps(id)
            reviews=[phase for fold in folds for phase in (fold.get('economic_selection') or {}).get('phases',[])]
            reviews.extend(reference for fold in folds for reference in fold['baseline_results'])
            provider_blockers=sorted({reason for review in reviews for reason in (review.get('deployment_readiness') or {}).get('reasons',[])})
            reliability=None
            if plan.get('economic_studies'):
                from .research_reliability import consolidate_reliability
                reliability=consolidate_reliability(plan,folds,ReliabilitySettings.model_validate(plan['reliability']))
            result = dict(folds=folds,reliability=reliability,event_journal=self._journal(id), readiness=dict(status='INCOMPLETE',production_qualified=False,provider_rule_blockers=provider_blockers, reasons=[
                ('Inner qualification, independent selection, predeclared references and chronological outer reliability are saved. Evidence sufficiency and comparisons are reported explicitly; final procedure verification and deployment remain pending.' if plan.get('economic_studies') else 'Inner qualification is complete. Economic selection, frozen outer replay, reliability and final recommendation remain pending.'),
                'No deployment recommendation or live qualification is produced.']), limitations=plan['limitations'])
            with TemporaryDirectory(prefix='.pending-', dir=self.analyses.root) as temp:
                staged = Path(temp)/'report'; staged.mkdir()
                (staged/'research_plan.json').write_text(canonical(plan))
                (staged/'calculations.json').write_text(canonical(result))
                (staged/'economic_selection.json').write_text(canonical([dict(outer_fold=f['index'],selection=f['economic_selection']) for f in folds]))
                (staged/'research_journal.json').write_text(canonical(result['event_journal']))
                (staged/'baseline_results.json').write_text(canonical([dict(outer_fold=f['index'],baseline_results=f['baseline_results']) for f in folds]))
                (staged/'reliability.json').write_text(canonical(reliability))
                self._write_reliability_csv(staged,reliability)
                (staged/'chronological_replay.json').write_text(canonical([dict(outer_fold=f['index'],replay=f['chronological_replay']) for f in folds]))
                with (staged/'qualification.csv').open('w', newline='') as stream:
                    writer = csv.writer(stream); writer.writerow(['outer_fold','candidate_id','status','reasons'])
                    for fold in folds:
                        for c in fold['qualification']['candidates']:
                            writer.writerow([fold['index'], c['candidate_id'], c['status'], canonical(c['reasons'])])
                report = dict(format_version=6, phase='research_integrity', model_version='nested-research-v3',
                    settings=dict(ANALYSIS_MODE='nested_research'), request=campaign['declaration'],
                    plan=plan, calculations=result, implementation=dict(engine_identity=plan['engine_identity']))
                seal_report(staged, report, analysis_id, self.analyses.get(analysis_id)['created'])
                staged.rename(self.analyses.root/analysis_id)
            with self.analyses.connect() as db:
                db.execute('INSERT INTO analysis_report_checks VALUES (?,?)',
                    (analysis_id, canonical(sealed_checks(self.analyses.root/analysis_id))))
                db.execute("UPDATE analyses SET status='complete',progress=? WHERE id=?",
                    ('Nested reliability and references saved; final procedure verification pending' if plan.get('economic_studies') else 'Inner qualification saved; outer economic validation pending', analysis_id))
        except Exception as exc:
            self.analyses._update(analysis_id, 'error', 'Research stopped; completed backtests retained', f'{type(exc).__name__}: {exc}')
