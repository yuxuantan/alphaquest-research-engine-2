"""Nested research orchestration using ordinary backtests and AnalysisStore.

This first increment executes inner research only. Outer tests stay reserved;
economic selection/replay must be added before a research-complete verdict.
"""
import csv
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from pydantic import Field, model_validator

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
    confirmed_backtest_count: int | None = Field(default=None, ge=1)

    @model_validator(mode='after')
    def unique_scenarios(self):
        names = [s.name for s in self.execution_scenarios]
        if len(set(names)) != len(names) or 'baseline' in names:
            raise ValueError('Scenario names must be unique and cannot use the reserved name baseline.')
        return self


class ResearchCancelled(Exception):
    pass


class RobustResearchStore:
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
        folds = generate_folds(sessions, body.folds)
        count = len(candidates) * sum((2 + len(body.execution_scenarios)) * len(f['inner']) for f in folds)
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
            execution_scenarios=[s.model_dump(mode='json') for s in body.execution_scenarios],
            regimes=body.regimes.model_dump(mode='json'),
            prior_access=dict(status='previously_accessed_development', reports=access,
                external_access='unknown', untouched=False),
            limitations=[
                'Inner research uses cold starts; training state and open positions are not carried into validation.',
                'Fold lengths count observed sessions. Missing market sessions are not inferred.',
                'Whole-session purge/embargo is declared, not inferred from an unknown feature or label horizon.',
                'Saved source configurations may already reflect prior research; this is not an untouched history claim.',
                'This increment does not execute outer tests, optimize prop policies or recommend deployment.',
                'Selected execution scenarios rerun the strategy and fills on the same validation window; all selected scenarios gate admission.',
                'Regime thresholds fit only inner training; entry labels use strictly earlier completed bars and unknown classifications remain visible.',
                'OHLC limit penetration and extra stop slippage are declared sensitivity assumptions, not measured order-book execution probabilities.'])
        result['input_identity'] = fingerprint({k:v for k,v in result.items() if k != 'prior_access'})
        return result

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
        with self.analyses.connect() as db:
            if db.execute('SELECT cancel_requested FROM robust_research WHERE id=?', (id,)).fetchone()[0]:
                raise ResearchCancelled('Cancelled at a safe checkpoint. Completed backtests remain available; Run resumes them.')

    def _backtest(self, campaign, analysis_id, candidate, outer, inner, role, scenario=None):
        id, plan = campaign['campaign_id'], campaign['plan']
        key = f"{outer['index']}:{inner['index']}:{candidate['id']}:{role}"
        if scenario:
            key += ':' + scenario.name
        with self.analyses.connect() as db:
            row = db.execute('SELECT payload FROM robust_research_steps WHERE campaign_id=? AND step_key=?', (id, key)).fetchone()
        if row:
            saved = json.loads(row[0]); record = self.runs.get(saved['run_id'])
            if not record or artifacts(self.runs.root, record) != saved['artifacts'] or fingerprint(record) != saved['manifest_sha256']:
                raise ResearchConflict('A completed research backtest changed; create a new campaign.')
            return record
        window = inner['train' if role == 'inner_train' else 'validation']
        self._checkpoint(id)
        # Reserve access before loading bars, even when the attempt fails.
        with self.analyses.connect() as db:
            db.execute('INSERT INTO research_access_intervals VALUES (?,?,?,?,?,?,?,?,?)',
                (uuid4().hex, plan['dataset']['sha256'], plan['dataset']['source_timezone'], plan['convention'],
                 window['first_session'], window['last_session'], role, id, datetime.now(timezone.utc).isoformat()))
        dataset = self.datasets.get(plan['dataset']['id'])
        definition = get_strategy(candidate['strategy_id'])
        parameters = definition.parameters(candidate['parameters'])
        config = ExecutionSettings.model_validate(plan['execution_settings']).execution_config(dataset)
        split = dict(is_start=outer['train']['first_session'], is_end=outer['train']['last_session'],
                     oos_start=outer['test']['first_session'], oos_end=outer['test']['last_session'],
                     strategy_id=candidate['strategy_id'], source_sha256=dataset['sha256'],
                     source_timezone=dataset['source_timezone'], convention=plan['convention'], version=2)
        research = dict(phase='inner', role=role, plan=split, campaign_id=id,
            outer_fold=outer['index'], inner_fold=inner['index'], window=window,
            information_cutoff_session=window['last_session'], cold_start=True)
        if scenario:
            research['execution_scenario'] = scenario.model_dump(mode='json')
        def progress(stage, processed, total):
            if stage != 'done':
                self._checkpoint(id)
            self.analyses._update(analysis_id, 'running',
                f"Outer {outer['index']}/{len(plan['folds'])}, inner {inner['index']}, {candidate['strategy_id']}, {role}: {stage}")
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
        saved = dict(run_id=record['id'], manifest_sha256=fingerprint(record), artifacts=artifacts(self.runs.root, record))
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

    def _verify_steps(self, id):
        with self.analyses.connect() as db:
            steps = db.execute('SELECT payload FROM robust_research_steps WHERE campaign_id=?', (id,)).fetchall()
        for (payload,) in steps:
            saved = json.loads(payload)
            record = self.runs.get(saved['run_id'])
            if (not record or fingerprint(record) != saved['manifest_sha256']
                    or artifacts(self.runs.root, record) != saved['artifacts']):
                raise ResearchConflict('Generated research backtest changed before publication; no aggregate report was published.')

    def _run(self, id, analysis_id):
        try:
            self.analyses._update(analysis_id, 'running', 'Checking frozen research inputs')
            self.check(id)
            campaign = self.get(id); plan = campaign['plan']
            folds = []
            for outer in plan['folds']:
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
                folds.append(dict(index=outer['index'], qualification=qualification, backtests=backtests,
                    inner_evidence=evidence, regime_evidence=regime_evidence,
                    outer_test_status='not_run', policy_selection_status='not_run'))
            self._checkpoint(id)
            self.check(id)
            self._verify_steps(id)
            result = dict(folds=folds, readiness=dict(status='INCOMPLETE', reasons=[
                'Inner qualification is complete. Economic selection, frozen outer replay, reliability and final recommendation remain pending.',
                'No deployment recommendation or live qualification is produced.']), limitations=plan['limitations'])
            with TemporaryDirectory(prefix='.pending-', dir=self.analyses.root) as temp:
                staged = Path(temp)/'report'; staged.mkdir()
                (staged/'research_plan.json').write_text(canonical(plan))
                (staged/'calculations.json').write_text(canonical(result))
                with (staged/'qualification.csv').open('w', newline='') as stream:
                    writer = csv.writer(stream); writer.writerow(['outer_fold','candidate_id','status','reasons'])
                    for fold in folds:
                        for c in fold['qualification']['candidates']:
                            writer.writerow([fold['index'], c['candidate_id'], c['status'], canonical(c['reasons'])])
                report = dict(format_version=6, phase='research_integrity', model_version='nested-research-v2',
                    settings=dict(ANALYSIS_MODE='nested_research'), request=campaign['declaration'],
                    plan=plan, calculations=result, implementation=dict(engine_identity=plan['engine_identity']))
                seal_report(staged, report, analysis_id, self.analyses.get(analysis_id)['created'])
                staged.rename(self.analyses.root/analysis_id)
            with self.analyses.connect() as db:
                db.execute('INSERT INTO analysis_report_checks VALUES (?,?)',
                    (analysis_id, canonical(sealed_checks(self.analyses.root/analysis_id))))
                db.execute("UPDATE analyses SET status='complete',progress=? WHERE id=?",
                    ('Inner qualification saved; outer economic validation pending', analysis_id))
        except Exception as exc:
            self.analyses._update(analysis_id, 'error', 'Research stopped; completed backtests retained', f'{type(exc).__name__}: {exc}')
