"""Immutable phase campaign declarations; calculations live only in AnalysisStore."""
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from .prop.adapter import canonical
from .research import ResearchConflict


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class CandidateSource(StrictModel):
    backtest_id: str | None = Field(default=None, pattern=r'^[0-9a-f]{32}$')
    optimization_id: str | None = Field(default=None, pattern=r'^[0-9a-f]{32}$')
    trials: list[int] | None = Field(default=None, min_length=1, max_length=128)
    sizes: list[int] = Field(min_length=1, max_length=60)
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
        return self


class CampaignRequest(StrictModel):
    campaign_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    phase: Literal['evaluation', 'funded']
    profile: dict
    sources: list[CandidateSource] = Field(min_length=1, max_length=128)
    maximum_candidates: int = Field(ge=1, le=128)
    is_window: dict
    simulation: dict
    sampling: dict
    costs: dict
    search_settings: dict
    retry: dict | None = None


class FreezeRequest(StrictModel):
    candidate_ids: list[str] = Field(min_length=1, max_length=128)
    rationale: str = Field(min_length=1, max_length=4000)


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
    ''')


def module_for(phase):
    from .prop import evaluation_optimization, funded_optimization
    return evaluation_optimization if phase == 'evaluation' else funded_optimization


def fingerprint(value):
    return sha256(canonical(value).encode()).hexdigest()


class CampaignStore:
    def __init__(self, runs, analyses, optimizations):
        self.runs, self.analyses, self.optimizations = runs, analyses, optimizations

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

    def expand(self, body):
        """Resolve saved grid members without ranking or reading OOS outcomes."""
        candidates, origins = [], []
        count = 0
        for source in body.sources:
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
            count += len(refs)*len(source.sizes)
            if count > body.maximum_candidates:
                raise ValueError(f'Candidate budget exceeded: {count} trial × size combinations exceed {body.maximum_candidates}.')
            for ref in refs:
                for size in sorted(source.sizes):
                    candidate = dict(source=dict(source_backtest_id=ref['run_id'], trade_file=source.trade_file,
                        export_timezone=source.export_timezone), profile=body.profile, micros=size,
                        simulation=body.simulation, sampling=body.sampling, costs=body.costs, period=body.is_window)
                    if body.retry is not None:
                        candidate['retry'] = body.retry
                    candidates.append(candidate)
        if set(body.search_settings) & {'candidates', 'source_backtest_id', 'mode'}:
            raise ValueError('Campaign owns the candidate set, anchor and phase.')
        raw = dict(mode=body.phase+'_optimization', source_backtest_id=min(c['source']['source_backtest_id'] for c in candidates),
                   candidates=candidates, **body.search_settings)
        module = module_for(body.phase)
        search = module.parse_request(raw)
        checks = module.check_search(self.runs, search)
        configurations, risk_conventions = set(), set()
        for row in checks:
            strategy = row['manifest']['strategy']
            signature = canonical(dict(strategy_id=strategy['id'], parameters=strategy['parameters'],
                strategy_source_sha256=strategy['source_sha256'], micros=row['manifest']['configuration']['micros']))
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
            plan = row['manifest']['source']['backtest']['run_metadata']['research']['plan']
            if not plan['is_start'] <= body.is_window['first_session'] <= body.is_window['last_session'] <= plan['is_end']:
                raise ValueError('Campaign research window must lie within declared IS.')
        normalized = json.loads(canonical(asdict(search)))
        normalized['candidates'].sort(key=canonical)
        return dict(schema_version='phase-campaign-v1', phase=body.phase, request=normalized,
            candidate_search_count=count, maximum_candidates=body.maximum_candidates,
            source_checks=checks, optimization_grids=origins,
            selection_objective=('cost_time_pareto' if body.phase == 'evaluation' else module.OBJECTIVE),
            constraints=normalized.get('constraints', {}), model_version=module.MODEL_VERSION,
            numerical_implementation=module.implementation_identity(), input_identity=fingerprint(normalized),
            calculation_key=module.search_key(search, checks),
            screening=dict(method='exhaustive_declared_candidates', status='validated', candidates=count),
            refinement=dict(status='not_requested', reason='One declared sampling schedule; no adaptive pruning or precision certification.'))

    def create(self, body):
        with self.analyses.lock:
            previous = self._row(body.campaign_id)
            if previous:
                if previous['declaration'] != body.model_dump():
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
            checks = module.check_search(self.runs, search)
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
                if row['status'] == 'complete' and not self.analyses.fingerprint(row['analysis_id']):
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
            analysis = self.analyses.submit_phase(self.runs, search, campaign_checks=manifest['source_checks'])
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
            if row['frozen']:
                if row['frozen']['candidate_ids'] != selection or row['frozen']['rationale'] != body.rationale:
                    raise ResearchConflict('Frozen selection is immutable; create a new campaign for a new decision.')
                return row['frozen']
            report = self.report(id)
            calc = report['calculations']
            allowed = calc['frontier'] if row['manifest']['phase'] == 'evaluation' else calc['ranking']
            if set(selection) - set(allowed) or calc.get('unresolved_candidates'):
                raise ValueError('Freeze requires resolved frontier points or feasible funded candidates.')
            # Refresh access metadata only. No OOS bars or outcomes are read.
            access = self.validate(id)
            package = dict(schema_version='phase-freeze-v1', campaign_id=id, phase=row['manifest']['phase'],
                created_at_utc=datetime.now(timezone.utc).isoformat(), candidate_ids=selection, rationale=body.rationale,
                analysis_id=row['analysis_id'], report_sha256=self.analyses.fingerprint(row['analysis_id'])['files']['report.json'],
                campaign_manifest_sha256=fingerprint(row['manifest']),
                prior_access=[dict(candidate_id=c['candidate_id'], prior_access=c['prior_access']) for c in access['candidates']],
                assessment_status='not_run', interpretation='IS selection frozen; no OOS executed. Estimated results, not certified future outcomes.')
            package['package_sha256'] = fingerprint(package)
            with self.analyses.connect() as db:
                db.execute('UPDATE research_campaigns SET frozen=? WHERE id=?', (canonical(package), id))
            return package
