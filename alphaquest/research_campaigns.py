"""Immutable phase campaign declarations; calculations live only in AnalysisStore."""
from dataclasses import asdict
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from .prop.adapter import canonical, source_record
from .prop.phase_dispatch import module_for
from .prop.phase_search import CANDIDATE_CONFIRMATION_THRESHOLD, require_candidate_confirmation
from .research import ResearchConflict


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class CandidateSource(StrictModel):
    backtest_id: str | None = Field(default=None, pattern=r'^[0-9a-f]{32}$')
    optimization_id: str | None = Field(default=None, pattern=r'^[0-9a-f]{32}$')
    trials: list[int] | None = Field(default=None, min_length=1)
    sizes: list[int] = Field(min_length=1, max_length=60)
    sizing_policies: list[dict] | None = Field(default=None, min_length=1, max_length=60)
    trade_file: str = Field(default='', max_length=4096)
    export_timezone: Literal['America/Chicago', 'America/New_York', 'UTC'] = 'America/Chicago'

    @model_validator(mode='after')
    def reference(self):
        if (self.backtest_id is None) == (self.optimization_id is None):
            raise ValueError('Supply either backtest_id or optimization_id.')
        if self.trials is not None and self.optimization_id is None:
            raise ValueError('Trial numbers require an optimization_id.')
        if len(set(self.sizes)) != len(self.sizes) or (self.trials and len(set(self.trials)) != len(self.trials)):
            raise ValueError('Duplicate trial numbers or sizes are not permitted.')
        if any(size < 1 or size > 60 for size in self.sizes):
            raise ValueError('Sizes must be whole MNQ contracts from 1 to 60; profile caps also apply.')
        if self.sizing_policies is not None:
            from .prop.phase_profiles import SizingConfiguration
            self.sizing_policies = [asdict(SizingConfiguration(**item)) for item in self.sizing_policies]
            if len({canonical(item) for item in self.sizing_policies}) != len(self.sizing_policies):
                raise ValueError('Duplicate sizing policies are not permitted.')
        return self


class CampaignRequest(StrictModel):
    campaign_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    phase: Literal['evaluation', 'funded']
    profile: dict
    sources: list[CandidateSource] = Field(min_length=1)
    # Accepted for old API clients/declarations; no longer limits membership.
    maximum_candidates: int | None = Field(default=None, ge=1, deprecated=True)
    confirmed_candidate_count: int | None = Field(default=None, ge=1)
    is_window: dict
    simulation: dict
    sampling: dict
    costs: dict
    search_settings: dict
    retry: dict | None = None


class SourceWindowRequest(StrictModel):
    sources: list[CandidateSource] = Field(min_length=1)


class FreezeRequest(StrictModel):
    candidate_ids: list[str] = Field(min_length=1)
    rationale: str = Field(min_length=1, max_length=4000)
    names: dict[str, str] = Field(default_factory=dict)


class AssessmentRequest(StrictModel):
    request_id: str = Field(pattern=r'^[0-9a-f]{32}$')


def initialize(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS research_campaigns (
            id TEXT PRIMARY KEY, created TEXT NOT NULL, declaration TEXT NOT NULL,
            manifest TEXT NOT NULL, analysis_id TEXT, frozen TEXT);
        CREATE TABLE IF NOT EXISTS campaign_sources (
            campaign_id TEXT NOT NULL, source_id TEXT NOT NULL,
            PRIMARY KEY(campaign_id,source_id));
        CREATE TABLE IF NOT EXISTS campaign_analyses (
            campaign_id TEXT NOT NULL, analysis_id TEXT NOT NULL,
            PRIMARY KEY(campaign_id,analysis_id));
        CREATE INDEX IF NOT EXISTS campaign_sources_source ON campaign_sources(source_id);
        CREATE TABLE IF NOT EXISTS campaign_jobs (
            campaign_id TEXT NOT NULL, optimization_id TEXT NOT NULL,
            PRIMARY KEY(campaign_id,optimization_id));
        CREATE TABLE IF NOT EXISTS campaign_assessments (
            id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL, payload TEXT NOT NULL);
    ''')


def fingerprint(value):
    return sha256(canonical(value).encode()).hexdigest()


def campaign_search_settings(body):
    """Resolve omitted weekday coverage before saving a concrete phase request.

    Explicit calendars retain their existing validation and historical meaning.
    Coverage supports the phase limit; it never changes that limit or the IS data.
    """
    settings = deepcopy(body.search_settings)
    calendar = settings.get('calendar')
    if not isinstance(calendar, dict) or 'coverage_end' in calendar:
        return settings
    if calendar.get('version', 'user-declared-weekdays-v1') != 'user-declared-weekdays-v1':
        raise ValueError('Automatic coverage supports user-declared-weekdays-v1 only; supply coverage_end for other calendar versions.')
    starts = calendar.get('start_dates')
    if not isinstance(starts, (list, tuple)) or not starts:
        raise ValueError('Calendar start_dates must contain scenario start dates.')
    try:
        latest = max(date.fromisoformat(start) for start in starts)
    except (TypeError, ValueError) as exc:
        raise ValueError('Calendar start dates must use YYYY-MM-DD format.') from exc
    if body.phase == 'evaluation':
        limit = module_for(body.phase).SequentialRetry(**(body.retry or {})).max_calendar_days
    else:
        from .prop.phase_profiles import positive_integer
        limit = settings.get('horizon_calendar_days')
        positive_integer('horizon_calendar_days', limit, 3650)
    try:
        calendar['coverage_end'] = (latest + timedelta(days=limit)).isoformat()
    except OverflowError as exc:
        raise ValueError('Scenario start plus the phase limit exceeds the supported calendar dates.') from exc
    return settings


class CampaignStore:
    def __init__(self, runs, analyses, optimizations, datasets=None):
        self.runs, self.analyses, self.optimizations = runs, analyses, optimizations
        self.datasets = datasets

    def sources(self, kind, query='', offset=0, limit=50):
        """Metadata-only picker; never load OOS outcomes, trades or prop metrics."""
        if kind == 'backtest_id':
            table, document, prefix = 'runs', 'manifest', '$.run_metadata'
            parameters = '$.run_metadata.strategy.parameters'
            extra = "AND json_extract(manifest,'$.status')='complete'"
            total_trials = '1'
        elif kind == 'optimization_id':
            table, document, prefix = 'optimizations', 'payload', '$'
            parameters = '$.request.parameter_ranges'
            extra = "AND json_extract(payload,'$.status')<>'deleting'"
            total_trials = "json_extract(payload,'$.total_trials')"
        else:
            raise ValueError('Unknown campaign source type.')
        # Identifiers/JSON paths above are constants, never request interpolation.
        fields = [f"json_extract({document},'{path}')" for path in (
            '$.status', prefix+'.dataset.name', prefix+'.strategy.id', parameters,
            prefix+'.research.plan.is_start', prefix+'.research.plan.is_end')]
        searchable = " || ' ' || ".join(["id", "created_at", *[f"coalesce({f},'')" for f in fields]])
        where = f"json_extract({document},'{prefix}.research.phase')='is' {extra} AND instr(lower(replace({searchable},'_',' ')),lower(replace(?,'_',' ')))>0"
        with self.runs.connect() as db:
            total = db.execute(f'SELECT COUNT(*) FROM {table} WHERE {where}', (query.strip(),)).fetchone()[0]
            rows = db.execute(f"SELECT id,created_at,{','.join(fields)},{total_trials} FROM {table} WHERE {where} "
                              'ORDER BY created_at DESC,id LIMIT ? OFFSET ?', (query.strip(),limit,offset)).fetchall()
        return dict(items=[dict(id=r[0], created_at=r[1], status=r[2], dataset_name=r[3], strategy_id=r[4],
                    parameters=json.loads(r[5] or '{}'), is_start=r[6], is_end=r[7], total_trials=r[8],
                    selectable=r[2]=='complete') for r in rows], total=total, offset=offset, limit=limit)

    def resolve_sources(self, sources):
        """Resolve complete saved membership without loading trades or outcomes."""
        expanded, origins = [], []
        count = 0
        for source in sources:
            if source.backtest_id:
                refs = [dict(run_id=source.backtest_id)]
            else:
                job = self.optimizations.get(source.optimization_id)
                if not job:
                    with self.runs.connect() as db:
                        backtest = db.execute('SELECT 1 FROM runs WHERE id=?', (source.optimization_id,)).fetchone()
                    if backtest:
                        raise ValueError('This ID belongs to a saved backtest report, not an optimization job. '
                                         'Set Saved source type to Backtest and check candidates again.')
                    raise ValueError('Optimization job not found in this library. Check the job ID and Saved source type; '
                                     'an individual trial report uses Backtest.')
                if job['status'] != 'complete':
                    raise ValueError(f"Optimization job {source.optimization_id} is {job['status']}. "
                                     'Wait for completion or resume a failed/interrupted grid. '
                                     'To use an already completed trial, select Backtest and enter its report ID.')
                with self.runs.connect() as db:
                    rows = db.execute('SELECT trial,payload FROM optimization_trials WHERE optimization_id=? ORDER BY trial',
                                      (source.optimization_id,)).fetchall()
                selected = set(source.trials) if source.trials is not None else {n for n, _ in rows}
                if not selected or selected - {n for n, _ in rows}:
                    raise ValueError('Selected trial does not exist in the saved optimization grid.')
                if source.trials is None and len(rows) != job['total_trials']:
                    raise ValueError('Saved grid membership is incomplete; select explicit saved trials or resume the grid.')
                refs = []
                for number, payload in rows:
                    if number not in selected:
                        continue
                    trial = json.loads(payload)
                    if not trial.get('run_id') or trial.get('status') not in (None, 'complete'):
                        raise ValueError('Selected trial failed or has no saved backtest; no trials are silently excluded.')
                    refs.append(dict(run_id=trial['run_id'], optimization_id=source.optimization_id, trial=number))
                origins.append(dict(optimization_id=source.optimization_id, selected_trials=sorted(selected),
                    total_grid_trials=job['total_trials'], failed_trials=job.get('failed_trials', []),
                    grid=job['request']['parameter_ranges'], strategy=job['strategy']))
            count += len(refs)*len(source.sizes)*len(source.sizing_policies or [None])
            expanded.append((source, refs))
        return expanded, origins, count

    def source_window(self, body):
        """Intersect declared IS with saved bar coverage, in CME session dates."""
        from .prop.phase_lifecycle import instant, session_date
        from .prop.phase_search import declared_is_coverage
        expanded, _, _ = self.resolve_sources(body.sources)
        sources = []
        for id in sorted({ref['run_id'] for _, refs in expanded for ref in refs}):
            record = source_record(self.runs, id)
            declared = declared_is_coverage(record)
            if record['run_metadata'].get('source', {}).get('kind') == 'external_trade_export':
                from .trade_imports import verify_import
                verify_import(self.runs, record)
                sources.append(dict(source_backtest_id=id, declared_is=declared, saved_coverage=declared,
                    provenance='Exporter-declared IS session inventory; no native plan or untouched-OOS claim.'))
                continue
            research = record['run_metadata'].get('research') or {}
            if research.get('phase') != 'is':
                raise ValueError('The research window requires declared IS backtests; OOS and undeclared sources reject.')
            plan = research['plan']
            first = session_date(instant(record['period_start_utc'])).isoformat()
            last = session_date(instant(record['period_end_utc'])).isoformat()
            sources.append(dict(source_backtest_id=id,
                declared_is=dict(first_session=plan['is_start'], last_session=plan['is_end']),
                saved_coverage=dict(first_session=first, last_session=last)))
        first = max(max(s['declared_is']['first_session'], s['saved_coverage']['first_session']) for s in sources)
        last = min(min(s['declared_is']['last_session'], s['saved_coverage']['last_session']) for s in sources)
        if first > last:
            raise ValueError('Selected sources have no common saved IS coverage; choose overlapping IS sources.')
        return dict(is_window=dict(first_session=first, last_session=last), sources=sources,
            convention='CME Chicago session dates; saved bar coverage, including zero-trade sessions')

    def expand(self, body):
        """Resolve saved grid members without ranking or reading OOS outcomes."""
        settings = campaign_search_settings(body)
        expanded, origins, count = self.resolve_sources(body.sources)
        candidates = []
        require_candidate_confirmation(count, body.confirmed_candidate_count)
        for source, refs in expanded:
            for ref in refs:
                for size in sorted(source.sizes):
                    for sizing in source.sizing_policies or [None]:
                        candidate = dict(source=dict(source_backtest_id=ref['run_id'], trade_file=source.trade_file,
                            export_timezone=source.export_timezone), profile=body.profile, micros=size,
                            simulation=body.simulation, sampling=body.sampling, costs=body.costs, period=body.is_window)
                        if sizing is not None:
                            candidate['sizing'] = sizing
                        if body.retry is not None:
                            candidate['retry'] = body.retry
                        candidates.append(candidate)
        if set(settings) & {'candidates', 'source_backtest_id', 'mode'}:
            raise ValueError('Campaign owns the candidate set, anchor and phase.')
        raw = dict(mode=body.phase+'_optimization', source_backtest_id=min(c['source']['source_backtest_id'] for c in candidates),
                   candidates=candidates, **settings)
        module = module_for(body.phase)
        search = module.parse_request(raw)
        checks = module.check_search(self.runs, search, datasets=self.datasets)
        configurations, risk_conventions = set(), set()
        for row in checks:
            strategy = row['manifest']['strategy']
            signature = canonical(dict(strategy_id=strategy['id'], parameters=strategy['parameters'],
                strategy_source_sha256=strategy['source_sha256'], micros=row['manifest']['configuration']['micros'],
                sizing=row['manifest']['configuration'].get('sizing')))
            if signature in configurations:
                raise ValueError('Duplicate candidate strategy/parameter/size configuration across saved reports or source aliases.')
            configurations.add(signature)
            snapshot = row['manifest']['source']
            risk_conventions.add((snapshot['excursion_input'].get('risk_policy', 'measured_mae'),
                                  snapshot.get('native_risk', {}).get('version')))
        if len(risk_conventions) != 1:
            raise ValueError('Candidates require compatible source-risk conventions; measured excursions and held-OHLC bounds cannot be mixed.')
        # Pin the entire window to declared IS, not merely to source file bounds.
        for row in checks:
            from .prop.phase_search import declared_is_coverage
            coverage = declared_is_coverage(row['manifest']['source']['backtest'])
            if not coverage['first_session'] <= body.is_window['first_session'] <= body.is_window['last_session'] <= coverage['last_session']:
                raise ValueError('Campaign research window must lie within declared IS.')
        normalized = json.loads(canonical(asdict(search)))
        normalized['candidates'].sort(key=canonical)
        return dict(schema_version='phase-campaign-v1', phase=body.phase, request=normalized,
            candidate_search_count=count,
            candidate_confirmation=dict(threshold=CANDIDATE_CONFIRMATION_THRESHOLD,
                confirmed_count=body.confirmed_candidate_count),
            source_checks=checks, optimization_grids=origins,
            selection_objective=('cost_time_pareto' if body.phase == 'evaluation' else module.OBJECTIVE),
            constraints=normalized.get('constraints', {}), model_version=module.MODEL_VERSION,
            numerical_implementation=module.implementation_identity(), input_identity=fingerprint(normalized),
            calculation_key=module.search_key(search, checks),
            screening=dict(method='exhaustive_declared_candidates', status='validated', candidates=count),
            refinement=dict(status='not_requested', reason='One declared sampling schedule; no adaptive pruning or precision certification.'))

    def create(self, body):
        with self.analyses.lock:
            with self.analyses.connect() as db:
                if (db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='robust_research'").fetchone()
                        and db.execute('SELECT 1 FROM robust_research WHERE id=?', (body.campaign_id,)).fetchone()):
                    raise ResearchConflict('This ID belongs to a nested research campaign; use a new phase campaign ID.')
            previous = self._row(body.campaign_id)
            if previous:
                if CampaignRequest.model_validate(previous['declaration']).model_dump() != body.model_dump():
                    raise ResearchConflict('Campaign ID already has an immutable declaration; use a new campaign ID.')
                return self.get(body.campaign_id)
            manifest = self.expand(body)
            with self.analyses.connect() as db:
                db.execute('INSERT INTO research_campaigns VALUES (?,?,?,?,NULL,NULL)',
                    (body.campaign_id, datetime.now(timezone.utc).isoformat(), canonical(body.model_dump()), canonical(manifest)))
                db.executemany('INSERT INTO campaign_sources VALUES (?,?)',
                    [(body.campaign_id, id) for id in sorted({c['source']['source_backtest_id'] for c in manifest['request']['candidates']})])
                db.executemany('INSERT INTO campaign_jobs VALUES (?,?)',
                    [(body.campaign_id, id) for id in sorted({g['optimization_id'] for g in manifest['optimization_grids']})])
            return self.get(body.campaign_id)

    def _row(self, id):
        with self.analyses.connect() as db:
            row = db.execute('SELECT created,declaration,manifest,analysis_id,frozen FROM research_campaigns WHERE id=?', (id,)).fetchone()
        if not row:
            return None
        return dict(campaign_id=id, created=row[0], declaration=json.loads(row[1]), manifest=json.loads(row[2]),
                    analysis_id=row[3], frozen=json.loads(row[4]) if row[4] else None)

    def get(self, id):
        row = self._row(id)
        if not row:
            raise KeyError('Campaign not found.')
        analysis = self.analyses.get(row['analysis_id']) if row['analysis_id'] else None
        status = analysis['status'] if analysis else 'validated'
        return dict(**row, status=status, analysis=analysis,
            screening_status='complete' if status == 'complete' else status,
            refinement_status=row['manifest']['refinement']['status'])

    def list(self, source_id=None, limit=50, offset=0):
        with self.analyses.connect() as db:
            rows = db.execute('SELECT id FROM research_campaigns WHERE (? IS NULL OR id IN '
                '(SELECT campaign_id FROM campaign_sources WHERE source_id=?)) ORDER BY created DESC,id LIMIT ? OFFSET ?',
                (source_id, source_id, limit, offset)).fetchall()
        return [dict(campaign_id=id, phase=(r:=self.get(id))['manifest']['phase'], status=r['status'],
                     created=r['created'], analysis_id=r['analysis_id'], frozen=bool(r['frozen'])) for (id,) in rows]

    def attempts(self, id):
        self.get(id)
        with self.analyses.connect() as db:
            rows = db.execute('SELECT a.id FROM analyses a JOIN campaign_analyses c ON c.analysis_id=a.id '
                              'WHERE c.campaign_id=? ORDER BY a.created,a.id', (id,)).fetchall()
        return [self.analyses.get(id) for (id,) in rows]

    def validate(self, id):
        with self.analyses.lock:
            row = self.get(id)
            module = module_for(row['manifest']['phase'])
            search = module.parse_request(row['manifest']['request'])
            checks = module.check_search(self.runs, search, datasets=self.datasets)
            # Access history is provenance, not a new numerical input. Preserve the
            # declaration snapshot and report additional access without inspecting outcomes.
            before = row['manifest']['source_checks']
            if [r['candidate_id'] for r in checks] != [r['candidate_id'] for r in before]:
                raise ResearchConflict('Saved source identity changed; create a new campaign.')
            if module.implementation_identity() != row['manifest']['numerical_implementation']:
                raise ResearchConflict('Numerical implementation changed; create a new campaign.')
            return dict(status='compatible', candidate_search_count=len(checks), candidates=checks)

    def run(self, id):
        with self.analyses.lock:
            row = self.get(id)
            if row['analysis'] and row['status'] in ('queued', 'running', 'complete'):
                if row['status'] == 'complete' and (not self.analyses.fingerprint(row['analysis_id'])
                        or not self.analyses.native_children_unchanged(self.runs,row['analysis_id'])):
                    raise ResearchConflict('Saved calculation failed integrity checks; preserve this campaign and create a new one.')
                return row
            self.validate(id)
            with self.analyses.connect() as db:
                pending = db.execute("SELECT COUNT(*) FROM analyses WHERE status IN ('queued','running')").fetchone()[0]
            if pending >= 8:
                raise ResearchConflict('Analysis queue is full (8 jobs); wait before running this campaign.')
            manifest = row['manifest']
            module = module_for(manifest['phase'])
            search = module.parse_request(manifest['request'])
            # Submit with the original access snapshot, after live source validation.
            analysis = self.analyses.submit_phase(self.runs, search, campaign_checks=manifest['source_checks'], datasets=self.datasets)
            with self.analyses.connect() as db:
                db.execute('INSERT OR IGNORE INTO campaign_analyses VALUES (?,?)', (id, analysis['id']))
                db.execute('UPDATE research_campaigns SET analysis_id=? WHERE id=?', (analysis['id'], id))
            return self.get(id)

    def report(self, id):
        row = self.get(id)
        if row['status'] != 'complete':
            raise ResearchConflict('Campaign has no completed calculation.')
        if not self.analyses.fingerprint(row['analysis_id']):
            raise ResearchConflict('Saved calculation failed integrity checks.')
        return json.loads((self.analyses.root/row['analysis_id']/'report.json').read_text())

    def freeze(self, id, body):
        with self.analyses.lock:
            row = self.get(id)
            selection = sorted(body.candidate_ids)
            if len(set(selection)) != len(selection):
                raise ValueError('Duplicate selected candidates.')
            if set(body.names) - set(selection) or any(not name.strip() or len(name) > 120 for name in body.names.values()):
                raise ValueError('Names must label selected candidates with 1–120 characters.')
            if row['frozen']:
                if (row['frozen']['candidate_ids'] != selection or row['frozen']['rationale'] != body.rationale
                        or any(row['frozen'].get('names', {}).get(k) != v for k,v in body.names.items())):
                    raise ResearchConflict('Frozen selection is immutable; create a new campaign for a new decision.')
                return row['frozen']
            report = self.report(id)
            calc = report['calculations']
            allowed = calc['frontier'] if row['manifest']['phase'] == 'evaluation' else calc['ranking']
            if set(selection) - set(allowed) or calc.get('unresolved_candidates'):
                raise ValueError('Freeze requires resolved frontier points or feasible funded candidates.')
            # Refresh access metadata only. No OOS bars or outcomes are read.
            access = self.validate(id)
            from pathlib import Path
            from .prop.adapter import digest
            profiles = {r['manifest']['configuration']['profile']['profile_id'] for r in calc['candidates']
                        if r['candidate_id'] in selection}
            rule_names = ['native_engine.py'] if 'apex-50k-eod' in profiles else []
            if 'lucidflex-50k' in profiles:
                rule_names += ['lucid_engine.py', 'lucid_rules.py']
            rule_sources = {}
            for name in rule_names:
                path = Path(__file__).parent/'prop'/name
                if digest(path) != report['implementation']['files'][name]:
                    raise ResearchConflict('Rule source changed before freeze; create a new campaign.')
                rule_sources[name] = dict(sha256=digest(path), source=path.read_text())
            package = dict(schema_version='phase-freeze-v1', campaign_id=id, phase=row['manifest']['phase'],
                created_at_utc=datetime.now(timezone.utc).isoformat(), candidate_ids=selection, rationale=body.rationale,
                analysis_id=row['analysis_id'], report_sha256=self.analyses.fingerprint(row['analysis_id'])['files']['report.json'],
                campaign_manifest_sha256=fingerprint(row['manifest']),
                prior_access=[dict(candidate_id=c['candidate_id'], prior_access=c['prior_access']) for c in access['candidates']],
                names={c['candidate_id']:body.names.get(c['candidate_id'],
                    f"{c['manifest']['strategy']['id']} · {c['manifest']['configuration']['micros']} MNQ · {c['candidate_id'][:8]}")
                    for c in calc['candidates'] if c['candidate_id'] in selection},
                selected_candidates=[c for c in report['request']['candidates']
                    if any(r['candidate_id'] in selection and r['manifest']['configuration'] == c for r in calc['candidates'])],
                candidate_definitions=[dict(candidate_id=r['candidate_id'], manifest=r['manifest'],
                    account_rules=r.get('provenance', {}).get('rules')) for r in calc['candidates'] if r['candidate_id'] in selection],
                rule_sources=rule_sources,
                search_settings={k:v for k,v in report['request'].items() if k != 'candidates'},
                model_version=report['model_version'], implementation=report['implementation'],
                selection_criteria=row['manifest']['selection_objective'],
                search_history=row['declaration'],
                assessment_status='not_run', interpretation='IS selection frozen; no OOS executed. Estimated results, not certified future outcomes.')
            package['package_sha256'] = fingerprint(package)
            with self.analyses.connect() as db:
                db.execute('UPDATE research_campaigns SET frozen=? WHERE id=?', (canonical(package), id))
            return package

    def assessments(self, id):
        self.get(id)
        with self.analyses.connect() as db:
            rows = db.execute('SELECT payload FROM campaign_assessments WHERE campaign_id=? ORDER BY rowid', (id,)).fetchall()
        result = []
        for (payload,) in rows:
            row = json.loads(payload)
            if row.get('analysis_id'):
                row['analysis'] = self.analyses.get(row['analysis_id'])
                row['status'] = row['analysis']['status']
            result.append(row)
        return result

    def save_assessment(self, row):
        with self.analyses.lock:
            with self.analyses.connect() as db:
                db.execute('INSERT OR REPLACE INTO campaign_assessments VALUES (?,?,?)',
                    (row['request_id'], row['campaign_id'], canonical(row)))
                db.executemany('INSERT OR IGNORE INTO campaign_sources VALUES (?,?)',
                    [(row['campaign_id'],source) for source in row.get('oos_sources', {}).values()])
        return row

    def begin_assessment(self, id, request_id):
        """Reserve one manual attempt before accessing any OOS prices."""
        with self.analyses.lock:
            with self.analyses.connect() as db:
                previous = db.execute('SELECT campaign_id,payload FROM campaign_assessments WHERE id=?', (request_id,)).fetchone()
            if previous:
                if previous[0] != id:
                    raise ResearchConflict('Assessment request ID already belongs to another campaign.')
                attempt=json.loads(previous[1])
                saved=self.analyses.get(attempt['analysis_id']) if attempt.get('analysis_id') else None
                if saved and saved['status']=='complete' and (not self.analyses.fingerprint(saved['id'])
                        or not self.analyses.native_children_unchanged(self.runs,saved['id'])):
                    raise ResearchConflict('Saved assessment or its native backtest capture changed; preserve the failed identity evidence.')
                return attempt, False
            campaign = self.get(id)
            package = campaign['frozen']
            if not package:
                raise ResearchConflict('Freeze IS candidates before manually launching OOS.')
            report = self.report(id)
            module = module_for(campaign['manifest']['phase'])
            if module.implementation_identity() != report['implementation']:
                raise ResearchConflict('Frozen numerical implementation changed; preserve this package and create a new campaign.')
            access = self.validate(id)
            parents = sorted({r['manifest']['configuration']['source']['source_backtest_id']
                for r in report['calculations']['candidates'] if r['candidate_id'] in package['candidate_ids']})
            if any(r['manifest']['source'].get('source_kind') == 'external_trade_export'
                   for r in report['calculations']['candidates'] if r['candidate_id'] in package['candidate_ids']):
                raise ValueError('Imported frozen choices need a separately supplied verified external OOS source. Native OOS launch cannot rerun an external strategy; external assessment integration is pending.')
            if any(r['manifest']['configuration']['source']['trade_file'] for r in report['calculations']['candidates']
                   if r['candidate_id'] in package['candidate_ids']):
                raise ValueError('Measured-export OOS needs a separately reconciled OOS export; this launch supports captured native risk only.')
            row = dict(request_id=request_id, campaign_id=id, created_at_utc=datetime.now(timezone.utc).isoformat(),
                status='launching', package_sha256=package['package_sha256'], parent_source_ids=parents,
                prior_access=[dict(candidate_id=c['candidate_id'], prior_access=c['prior_access']) for c in access['candidates']],
                oos_sources={}, analysis_id=None,
                native_chronological=package['search_settings'].get('native_execution') is not None,
                interpretation='Manual OOS assessment of the predeclared frozen family. No reranking or reselection. Prior access is retained; no untouched-OOS claim.')
            return self.save_assessment(row), True

    def finish_assessment(self, id, attempt, oos_sources):
        from copy import deepcopy
        with self.analyses.lock:
            campaign = self.get(id)
            package = campaign['frozen']
            report = self.report(id)
            module = module_for(campaign['manifest']['phase'])
            if module.implementation_identity() != report['implementation']:
                raise ResearchConflict('Frozen numerical implementation changed during OOS launch.')
            raw = deepcopy(report['request'])
            selected, mappings = [], []
            for row in report['calculations']['candidates']:
                if row['candidate_id'] not in package['candidate_ids']:
                    continue
                manifest = row['manifest']
                config = deepcopy(manifest['configuration'])
                parent = config['source']['source_backtest_id']
                source_id = oos_sources[parent]
                if config['source']['trade_file']:
                    raise ValueError('Measured-export OOS needs a separately reconciled OOS export; this launch supports captured native risk only.')
                config['source']['source_backtest_id'] = source_id
                plan = manifest['source']['backtest']['run_metadata']['research']['plan']
                if raw.get('native_execution') is not None:
                    from .prop.phase_lifecycle import instant,session_date
                    observed=source_record(self.runs,source_id)
                    config['period']=dict(first_session=str(session_date(instant(observed['period_start_utc']))),
                        last_session=str(session_date(instant(observed['period_end_utc']))))
                else:
                    config['period'] = dict(first_session=plan['oos_start'], last_session=plan['oos_end'])
                selected.append(config)
                mappings.append(dict(source_id=source_id, frozen_candidate_id=row['candidate_id'], frozen_manifest=manifest,
                    name=package.get('names', {}).get(row['candidate_id'], row['candidate_id'][:12])))
            raw.update(candidates=selected, source_backtest_id=min(oos_sources.values()))
            context = dict(campaign_id=id, request_id=attempt['request_id'], frozen_package=package,
                sources=mappings, prior_access=attempt['prior_access'], interpretation=attempt['interpretation'])
            # Protect sources before queueing and keep every report in AnalysisStore.
            with self.analyses.connect() as db:
                db.executemany('INSERT OR IGNORE INTO campaign_sources VALUES (?,?)', [(id,s) for s in oos_sources.values()])
            analysis = self.analyses.submit_phase(self.runs, module.parse_request(raw), assessment=context, datasets=self.datasets)
            with self.analyses.connect() as db:
                db.execute('INSERT OR IGNORE INTO campaign_analyses VALUES (?,?)', (id,analysis['id']))
            return self.save_assessment(dict(attempt, status=analysis['status'], analysis_id=analysis['id'], oos_sources=oos_sources))
