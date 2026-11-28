"""Prop Desk job contracts and portal endpoints."""

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import ClassVar, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt
from pydantic import model_validator
from starlette.concurrency import run_in_threadpool

from .prop import (desk, desk_basket, desk_diagnostics, desk_global_ranking, desk_oos, desk_optimizer, desk_overlap,
                   desk_parity, desk_recommendation, desk_subset_optimizer)
from .prop.adapter import canonical, source_record
from .prop.phase_profiles import profile_settings
from .prop.phase_search import saved_oos_period
from .prop.store import seal_report, sealed_checks
from .optimization_cache import digest
from .research import ResearchConflict

router = APIRouter(prefix='/api/prop-desk', tags=['Prop Desk'])


class Configuration(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_backtest_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    phase: Literal['evaluation', 'funded']
    profile_id: Literal['apex-50k-eod', 'lucidflex-50k']
    micros: StrictInt = Field(ge=1, le=60)
    observation_sessions: StrictInt | None = Field(default=None, ge=1, le=2000)

    def resolved(self):
        profile = desk.PROFILES[self.profile_id]
        cap = profile['caps'][self.phase]
        if self.micros > cap:
            raise ValueError(f'{profile["label"]} {self.phase.title()} supports at most {cap} MNQ.')
        sessions = self.observation_sessions or profile[self.phase + '_horizon']
        expiry = profile['evaluation_expiry'] if self.phase == 'evaluation' else None
        if expiry is not None and sessions != expiry:
            raise ValueError(f'{profile["label"]} Evaluation uses its {expiry}-session modeled expiry.')
        return dict(self.model_dump(), observation_sessions=sessions)


class Launch(Configuration):
    check_sha256: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')

    def resolved(self):
        value = super().resolved()
        del value['check_sha256']
        return value


class DiagnosticsLaunch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    parent_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    source_backtest_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    micros: StrictInt = Field(ge=1, le=60)
    combination: StrictInt | None = Field(default=None, ge=1)
    size_basis: Literal['standalone'] | None = None


class OOSAssessmentLaunch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    parent_id: str = Field(pattern=r'^[0-9a-f]{32}$')


class BasketMember(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_backtest_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    oos_backtest_id: str | None = Field(default=None, pattern=r'^[0-9a-f]{32}$')
    weight: StrictInt = Field(ge=1, le=1_000_000)


class BasketConfiguration(BaseModel):
    model_config = ConfigDict(extra='forbid')
    require_full_oos: ClassVar[bool] = True
    members: list[BasketMember] = Field(min_length=1, max_length=60)
    phase: Literal['evaluation', 'funded']
    profile_id: Literal['apex-50k-eod', 'lucidflex-50k']
    minimum_micros: StrictInt = Field(ge=1, le=60)
    maximum_micros: StrictInt = Field(ge=1, le=60)
    observation_sessions: StrictInt | None = Field(default=None, ge=1, le=2000)
    overlap_policy: Literal['sequential_mae'] | None = None

    @model_validator(mode='after')
    def validate_members(self):
        if len({member.source_backtest_id for member in self.members}) != len(self.members):
            raise ValueError('Each basket member needs a distinct saved IS report.')
        if (self.require_full_oos and any(member.oos_backtest_id for member in self.members)
                and not all(member.oos_backtest_id for member in self.members)):
            raise ValueError('Supply a matching saved OOS report for every member, or leave all blank.')
        if self.minimum_micros > self.maximum_micros:
            raise ValueError('Minimum total MNQ must be at most the maximum.')
        return self

    @property
    def source_backtest_id(self):
        return self.members[0].source_backtest_id

    def resolved(self):
        sessions = self.observation_sessions
        if self.phase == 'funded':
            sessions = sessions or 2000
            if sessions < desk_basket.FIRST_YEAR:
                raise ValueError('Funded basket observation must cover at least 261 trading days for First year.')
        single = Configuration(source_backtest_id=self.source_backtest_id, phase=self.phase,
                               profile_id=self.profile_id, micros=self.maximum_micros,
                               observation_sessions=sessions)
        exclude = {'check_sha256'} if self.overlap_policy else {'check_sha256', 'overlap_policy'}
        return dict(self.model_dump(exclude=exclude),
                    observation_sessions=single.resolved()['observation_sessions'])


class BasketLaunch(BasketConfiguration):
    check_sha256: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    simulation_size_rule: Literal['manual', 'optimal', 'conservative', 'first_year', 'account_life'] | None = None

    def resolved(self):
        configuration = super().resolved()
        del configuration['simulation_size_rule']
        rule = self.simulation_size_rule
        if rule is None:
            return configuration
        if type(self) is not BasketLaunch:
            raise ValueError('Simulation sizing applies only to the Simulation portfolio.')
        choices = (('manual', 'optimal', 'conservative') if self.phase == 'evaluation'
                   else ('manual', 'first_year', 'account_life'))
        if rule not in choices:
            raise ValueError('Choose a sizing preset for the selected account phase.')
        desk_optimizer.workload(len(self.members), len(self.members), len(self.members),
                                self.minimum_micros, self.maximum_micros, configuration['observation_sessions'])
        return dict(configuration, size_rule=rule)


class OptimizerLaunch(BasketLaunch):
    require_full_oos: ClassVar[bool] = False
    minimum_members: StrictInt = Field(ge=1, le=60)
    maximum_members: StrictInt = Field(ge=1, le=60)

    def resolved(self):
        configuration = super().resolved()
        desk_optimizer.workload(len(self.members), self.minimum_members, self.maximum_members,
                               self.minimum_micros, self.maximum_micros, configuration['observation_sessions'])
        return configuration


class SubsetOptimizerLaunch(BasketLaunch):
    require_full_oos: ClassVar[bool] = False
    minimum_members: StrictInt = Field(default=1, ge=1, le=60)
    funded_size_rule: Literal['first_year', 'account_life'] | None = None
    compare_accounts: Literal[True] | None = None

    @property
    def maximum_members(self):
        return len(self.members)

    def resolved(self):
        configuration = super().resolved()
        del configuration['funded_size_rule']
        if not self.compare_accounts:
            del configuration['compare_accounts']
        if self.phase == 'evaluation' and self.funded_size_rule is not None:
            raise ValueError('Funded sizing presets apply only to Funded searches.')
        if self.phase == 'funded' and self.observation_sessions is None:
            configuration['observation_sessions'] = desk_basket.FIRST_YEAR
        size_rule = 'optimal' if self.phase == 'evaluation' else self.funded_size_rule or 'first_year'
        desk_optimizer.workload(len(self.members), self.minimum_members, self.maximum_members,
                               self.minimum_micros, self.maximum_micros, configuration['observation_sessions'])
        return dict(configuration, maximum_members=self.maximum_members, size_rule=size_rule)


class RecommendationLaunch(BasketConfiguration):
    require_full_oos: ClassVar[bool] = False
    members: list[BasketMember] = Field(min_length=1, max_length=desk_recommendation.MAX_MEMBERS)
    minimum_members: StrictInt = Field(default=1, ge=1, le=desk_recommendation.MAX_MEMBERS)
    allocation_search: Literal['individual', 'weighted'] = 'individual'
    funded_size_rule: Literal['first_year', 'account_life'] | None = None
    fixed_basket: StrictBool = False
    full_grid: StrictBool = False

    def resolved(self):
        if self.minimum_members > len(self.members) or self.minimum_members > self.maximum_micros:
            raise ValueError('Choose a strategy minimum that fits the selected pool and MNQ cap.')
        if self.phase == 'evaluation' and self.funded_size_rule is not None:
            raise ValueError('Funded sizing presets apply only to Funded searches.')
        if self.fixed_basket and (self.minimum_members != len(self.members) or self.allocation_search != 'individual'):
            raise ValueError('Individual Simulation sizing must use every selected strategy.')
        if self.full_grid and (self.fixed_basket or self.allocation_search != 'individual'):
            raise ValueError('Full-grid Top 5 requires individual sizing in Optimise.')
        if self.phase == 'funded' and self.observation_sessions is None:
            horizon = 2000 if self.funded_size_rule == 'account_life' else desk_basket.FIRST_YEAR
            configuration = BasketConfiguration.resolved(self.model_copy(update={'observation_sessions': horizon}))
        else:
            configuration = super().resolved()
        if not self.fixed_basket:
            del configuration['fixed_basket']
        if self.allocation_search == 'weighted':
            desk_optimizer.workload(len(self.members), self.minimum_members, len(self.members), self.minimum_micros,
                                   self.maximum_micros, configuration['observation_sessions'])
        configuration['size_rule'] = 'optimal' if self.phase == 'evaluation' else self.funded_size_rule or 'first_year'
        if self.full_grid:
            desk_global_ranking.workload(configuration)
        else:
            del configuration['full_grid']
        return configuration


class RecommendationEvidenceLaunch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    parent_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    candidate_id: str = Field(max_length=20, pattern=r'^\d+(?:-\d+){1,4}$')


def prepare(runs, analyses, body, configuration, datasets):
    if isinstance(body, RecommendationLaunch):
        owner = desk_global_ranking if body.full_grid else desk_recommendation
        return owner.prepare(runs, datasets, analyses, body, configuration)
    if isinstance(body, SubsetOptimizerLaunch) and body.compare_accounts:
        return desk_parity.prepare(runs, datasets, analyses, body, configuration, search=True)
    if isinstance(body, BasketLaunch) and body.simulation_size_rule is not None:
        return desk_parity.prepare(runs, datasets, analyses, body, configuration, search=False)
    if isinstance(body, SubsetOptimizerLaunch):
        return desk_subset_optimizer.prepare(runs, datasets, analyses, body, configuration)
    if isinstance(body, OptimizerLaunch):
        return desk_optimizer.prepare(runs, datasets, analyses, body, configuration)
    if isinstance(body, BasketConfiguration):
        return desk_basket.prepare(runs, datasets, analyses, body, configuration)
    checked = desk.prepare(runs, body, configuration)
    analyses.check_oos(checked['evidence']['source'], checked['settings'], runs)
    return checked


def source_summary(snapshot):
    record = snapshot['backtest']
    metadata = record['run_metadata']
    period = snapshot['profile_research_period']
    return dict(backtest_id=record['id'], strategy=metadata['strategy']['id'],
                dataset=metadata['dataset']['name'], first_session=period['first_session'],
                last_session=period['last_session'], source_sessions=period['weekdays'],
                trades=snapshot['phase_suitability']['risk_covered_trades'],
                instrument=snapshot['phase_suitability']['instrument'],
                risk_basis=snapshot['excursion_provenance'], session_convention=period['convention'],
                research_phase=(metadata.get('research') or {}).get('phase'))


def check_configuration(runs, analyses, body, datasets):
    configuration = body.resolved()
    checked = prepare(runs, analyses, body, configuration, datasets)
    if isinstance(body, BasketConfiguration):
        weights = [m.weight for m in body.members]
        return dict(status='compatible', check_sha256=checked['identity'], configuration=configuration,
                    windows=checked['windows'], law=desk_overlap.LAW if body.overlap_policy else desk_basket.LAW,
                    allocations=[dict(size=size, **desk_basket.allocation(weights, size))
                                 for size in range(body.minimum_micros, body.maximum_micros + 1)])
    return dict(status='compatible', check_sha256=checked['identity'], configuration=configuration,
                source=source_summary(checked['evidence']['source']))


def public_job(record):
    parts = record['request_hash'].split(':')
    return dict(id=record['id'], source_backtest_id=record['source_id'], created_at_utc=record['created'],
                phase=parts[1], mode=parts[2] if len(parts) == 4 else 'fixed', status=record['status'],
                progress=record['progress'], error=record['error'])


def dataset_evidence(datasets, dataset_id):
    metadata = datasets.get(dataset_id)
    if metadata is None:
        return None
    return {key: metadata[key] for key in ('id', 'sha256', 'csv_sha256', 'source_timezone',
            'bytes', 'columns', 'row_count', 'tick_data', 'instrument_settings') if key in metadata}


def verify_dataset(datasets, expected):
    """Recheck the queued inventory's backing bytes without parsing bars again."""
    if dataset_evidence(datasets, expected['id']) != expected:
        raise ValueError('The saved basket dataset changed after verification.')
    digest = sha256()
    for chunk in datasets.iter_csv(expected['id']):
        digest.update(chunk)
    if digest.hexdigest() != expected.get('csv_sha256', expected['sha256']):
        raise ValueError('The saved basket dataset bytes changed after verification.')
    if expected.get('tick_data'):
        from .tick_data import check_sources
        check_sources(expected)


def launch(runs, analyses, body, datasets):
    began = perf_counter()
    configuration = body.resolved()
    basket = isinstance(body, BasketConfiguration)
    dataset = None
    if basket:
        dataset_id = source_record(runs, body.source_backtest_id)['run_metadata']['dataset']['id']
        dataset = dataset_evidence(datasets, dataset_id)
        checked = prepare(runs, analyses, body, configuration, datasets)
    with analyses.lock:
        if basket:
            desk_basket.verify(runs, checked)
            source_dataset = checked['snapshots']['is'][0]['backtest']['run_metadata']['dataset']
            if (not dataset or (source_dataset['id'], source_dataset['sha256']) != (dataset_id, dataset['sha256'])
                    or dataset_evidence(datasets, dataset_id) != dataset):
                raise ResearchConflict('The saved basket dataset changed while checking the source. Run again.')
        else:
            checked = prepare(runs, analyses, body, configuration, datasets)
        if getattr(body, 'check_sha256', None) is not None and checked['identity'] != body.check_sha256:
            raise ResearchConflict('The Prop Desk inputs changed. Check the source again before running.')
        if isinstance(body, RecommendationLaunch):
            mode = 'recommendation:'
            checked['launch_timing'] = dict(source_seconds=perf_counter() - began, queued_at=perf_counter())
        elif isinstance(body, SubsetOptimizerLaunch):
            mode = 'subsets:'
        elif isinstance(body, OptimizerLaunch):
            mode = 'optimizer:'
        else:
            mode = 'basket:' if basket else ''
        key = f'{desk.REQUEST_PREFIX}{body.phase}:{mode}{checked["identity"]}'
        refs = ({s['backtest']['id'] for group in checked['snapshots'].values() for s in group}
                if basket else {body.source_backtest_id})
        job = enqueue(analyses, key, body.source_backtest_id, refs, body.phase.title(), run,
                      (runs, body, configuration, checked, datasets, dataset))
        if isinstance(body, RecommendationLaunch) and job['status'] == 'complete':
            queue_ranked_evidence(runs, analyses, datasets, job['id'], checked, dataset)
        return job


def enqueue(analyses, key, source, refs, label, worker, args, *, strict_seal=False):
    """Reuse or publish a queued Desk job while holding the AnalysisStore lock."""
    with analyses.connect() as db:
        previous = db.execute("SELECT id FROM analyses WHERE request_hash=? "
                              "AND status IN ('queued','running','complete') ORDER BY created DESC LIMIT 1",
                              (key,)).fetchone()
        if previous:
            record = analyses.get(previous[0])
            if record['status'] != 'complete' or verified(analyses, record['id']):
                return public_job(record)
            if strict_seal:
                raise ResearchConflict('The saved OOS assessment failed its integrity check.')
        id = uuid4().hex
        db.execute('INSERT INTO analyses VALUES (?,?,?,?,?,?,?)',
                   (id, key, source, datetime.now(timezone.utc).isoformat(),
                    'queued', f'Queued Prop Desk {label}', None))
        db.executemany('INSERT INTO analysis_sources VALUES (?,?)', [(id, ref) for ref in sorted(refs)])
    analyses.worker.submit(worker, analyses, id, *args)
    return public_job(analyses.get(id))


def run(analyses, id, runs, body, configuration, prepared, datasets, dataset):
    recommendation = isinstance(body, RecommendationLaunch)
    try:
        analyses._update(id, 'running', f'Running Prop Desk {body.phase.title()}')
        with TemporaryDirectory(prefix='.pending-', dir=analyses.root) as temp:
            staged = Path(temp) / 'report'
            staged.mkdir()
            with analyses.runtime.activate():
                if isinstance(body, BasketConfiguration):
                    verify_dataset(datasets, dataset)
                    settings = profile_settings(prepared['profile'], desk.SOURCE_COSTS)
                    for group in prepared['snapshots'].values():
                        for snapshot in group:
                            analyses.check_oos(snapshot, settings, runs)
                    if recommendation:
                        report_builder = recommendation_report
                    elif isinstance(body, (OptimizerLaunch, SubsetOptimizerLaunch)):
                        report_builder = optimizer_report
                    else:
                        report_builder = basket_report
                    report = report_builder(runs, analyses, id, body, configuration, prepared, staged)
                else:
                    analyses.check_oos(prepared['evidence']['source'], prepared['settings'], runs)
                    report = fixed_report(runs, body, configuration, prepared, staged)
            publish(analyses, id, staged, report)
    except Exception as exc:
        analyses._update(id, 'error', 'Prop Desk simulation failed', str(exc))
        return
    if recommendation:
        with analyses.lock:
            queue_ranked_evidence(runs, analyses, datasets, id, prepared, dataset)


def publish(analyses, id, staged, report):
    seal_report(staged, report, id, analyses.get(id)['created'], size_limit_bytes=None)
    checks = sealed_checks(staged)
    target = analyses.root / id
    with analyses.lock:
        try:
            with analyses.connect() as db:
                db.execute('INSERT INTO analysis_report_checks VALUES (?,?)', (id, canonical(checks)))
                db.execute("UPDATE analyses SET status='complete', progress=? WHERE id=?",
                           ('Saved Prop Desk result ready', id))
                staged.rename(target)
        except BaseException:
            if target.exists() and not staged.exists():
                target.rename(staged)
            raise


def diagnostic_parent(analyses, id):
    record = analyses.get(id)
    if (not record or not record['request_hash'].startswith(desk.REQUEST_PREFIX)
            or public_job(record)['mode'] in ('diagnostics', 'oos') or record['status'] != 'complete'):
        raise ValueError('Open a completed Prop Desk Simulation or Optimise result.')
    fingerprint = analyses.fingerprint(id)
    if not fingerprint:
        raise ResearchConflict('The saved parent result failed its integrity check.')
    raw = (analyses.root / id / 'report.json').read_bytes()
    if sha256(raw).hexdigest() != fingerprint['files']['report.json']:
        raise ResearchConflict('The saved parent result changed while reading it.')
    return json.loads(raw), fingerprint['files']['report.json']


def recommendation_report(runs, analyses, id, body, configuration, prepared, staged):
    started = perf_counter()
    owner = desk_global_ranking if body.full_grid else desk_recommendation
    result, rules, seeds = owner.calculate(
        prepared, configuration, lambda message: analyses._update(id, 'running', message))
    desk_basket.verify(runs, prepared)
    timing = prepared['launch_timing']
    result['timing'] = dict(source_seconds=timing['source_seconds'],
        worker_and_recheck_seconds=started - timing['queued_at'], is_seconds=perf_counter() - started)
    snapshots = prepared['snapshots']
    result['members'] = [source_summary(snapshot) for snapshot in snapshots['is']]
    return dict(format_version=1, model_version=owner.VERSION, phase=body.phase,
                settings=dict(ANALYSIS_MODE='prop_desk_recommendation'), configuration=configuration,
                profile_label=desk.PROFILES[body.profile_id]['label'],
                source=snapshots['is'][0], source_summary=source_summary(snapshots['is'][0]),
                sources=snapshots, rules=rules, calculations={}, recommendation=result,
                provenance=dict(prepared['evidence'], search_source_sha256=prepared['identity'], path_seeds=seeds))


def recommendation_evidence_key(parent, sha, candidate_id):
    key = digest((desk_recommendation.DETAIL_VERSION, parent['id'], sha, candidate_id))
    return f'{desk.REQUEST_PREFIX}{parent["phase"]}:recommendation-evidence:{key}'


def automatic_oos_candidates(parent):
    search = parent['recommendation']
    if not search['oos_days']:
        return []
    configuration = parent['configuration']
    groups = {group['id']: group for group in search['groups']}
    candidates = []
    for entry in search['ranking']:
        group = groups[entry['combination']]
        if not all(configuration['members'][i]['oos_backtest_id'] for i in group['members']):
            continue
        candidates.append(entry['candidate'])
        if configuration.get('fixed_basket'):
            candidates.extend(row['id'] for row in group['candidates']
                              if row['paths'] == entry['path_count'] and row['id'] != entry['candidate'])
    return candidates


def queue_ranked_evidence(runs, analyses, datasets, id, prepared, dataset):
    """Queue frozen evidence from the same verified preparation as the parent."""
    try:
        parent, sha = diagnostic_parent(analyses, id)
    except (OSError, ValueError, KeyError, ResearchConflict):
        return
    winner = parent['recommendation']['ranking'][0]['candidate']
    for candidate in dict.fromkeys([winner, *automatic_oos_candidates(parent)]):
        try:
            enqueue_recommendation_evidence(runs, analyses, datasets, parent, sha, candidate, prepared, dataset)
        except (OSError, ValueError, KeyError, ResearchConflict):
            # Keep other ranked assessments available if one saved artifact is invalid.
            continue


def recommendation_listing(analyses, parent, sha):
    """Read the account summaries already sealed for this exact recommendation."""
    search = parent['recommendation']
    winner = search['ranking'][0]['candidate']
    keys = {recommendation_evidence_key(parent, sha, row['id']): row['id']
            for group in search['groups'] for row in group['candidates']}
    with analyses.connect() as db:
        db.row_factory = sqlite3.Row
        placeholders = ','.join('?' for _ in keys)
        rows = db.execute(f'''SELECT a.*, c.payload AS checks FROM analyses a
            LEFT JOIN analysis_report_checks c ON c.id=a.id
            WHERE a.request_hash IN ({placeholders}) ORDER BY a.created DESC''', tuple(keys)).fetchall()
    assessed, jobs = {}, {}
    for row in rows:
        candidate = keys[row['request_hash']]
        if candidate not in jobs:
            jobs[candidate] = public_job(row)
        if row['status'] != 'complete' or candidate in assessed:
            continue
        try:
            raw = (analyses.root / row['id'] / 'report.json').read_bytes()
            if sha256(raw).hexdigest() != json.loads(row['checks'] or '{}').get('report.json'):
                continue
            child = json.loads(raw)
            if (child['provenance']['parent_report_sha256'] != sha or
                    child['configuration']['parent_id'] != parent['id'] or
                    child['configuration']['candidate_id'] != candidate):
                continue
            pair = child['basket']['sizes'][0]['account_comparison']
        except (OSError, ValueError, KeyError, IndexError):
            continue
        assessed[candidate] = dict(id=row['id'], oos_metrics=pair.get('oos_metrics'),
                                   unavailable=pair.get('unavailable'))
    return dict(allocation_evidence=assessed, allocation_jobs=jobs, winning_evidence=jobs.get(winner))


def enqueue_recommendation_evidence(runs, analyses, datasets, parent, sha, candidate_id, prepared, dataset):
    group, candidate = desk_recommendation.find_candidate(parent, candidate_id)
    refs = {m[key] for m in parent['configuration']['members'] for key in ('source_backtest_id', 'oos_backtest_id') if m[key]}
    key = recommendation_evidence_key(parent, sha, candidate_id)
    return enqueue(analyses, key, parent['source']['backtest']['id'], refs, 'frozen allocation',
                   run_recommendation_evidence,
                   (runs, datasets, parent, sha, group, candidate, prepared, dataset), strict_seal=True)


def launch_recommendation_evidence(runs, analyses, body, datasets):
    with analyses.lock:
        parent, sha = diagnostic_parent(analyses, body.parent_id)
        if parent['model_version'] == desk_recommendation.LEGACY_VERSION:
            desk_recommendation.find_candidate(parent, body.candidate_id)
            key = recommendation_evidence_key(parent, sha, body.candidate_id)
            with analyses.connect() as db:
                saved = db.execute("SELECT id FROM analyses WHERE request_hash=? AND status='complete'",
                                   (key,)).fetchone()
            if saved:
                diagnostic_parent(analyses, saved[0])
                return public_job(analyses.get(saved[0]))
            raise ResearchConflict('Run Optimise again to generate new allocation evidence for this earlier search.')
    if parent['model_version'] not in (desk_recommendation.VERSION, desk_global_ranking.VERSION):
        raise ValueError('Open a saved strategy recommendation to inspect its allocation.')
    configuration = parent['configuration']
    declaration = RecommendationLaunch.model_validate({k: v for k, v in configuration.items() if k != 'size_rule'})
    prepared = prepare(runs, analyses, declaration, configuration, datasets)
    if prepared['identity'] != parent['provenance']['search_source_sha256']:
        raise ResearchConflict('Verified sources or calculation settings differ from the saved recommendation.')
    dataset_id = prepared['snapshots']['is'][0]['backtest']['run_metadata']['dataset']['id']
    expected = dataset_evidence(datasets, dataset_id)
    if not expected:
        raise ResearchConflict('The saved recommendation dataset is unavailable.')
    with analyses.lock:
        return enqueue_recommendation_evidence(runs, analyses, datasets, parent, sha, body.candidate_id, prepared, expected)


def run_recommendation_evidence(analyses, id, runs, datasets, parent, sha, group, candidate, prepared, dataset):
    began = perf_counter()
    try:
        analyses._update(id, 'running', 'Checking the frozen allocation and comparing OOS')
        with analyses.lock:
            _, active = diagnostic_parent(analyses, parent['id'])
            if active != sha:
                raise ResearchConflict('The sealed recommendation changed after scheduling.')
        verify_dataset(datasets, dataset)
        desk_basket.verify(runs, prepared)
        with TemporaryDirectory(prefix='.pending-', dir=analyses.root) as temp:
            folder = Path(temp) / 'report'
            folder.mkdir()
            with analyses.runtime.activate():
                pair, snapshots = desk_recommendation.evidence(runs, prepared, parent, group, candidate, folder)
            config = parent['configuration']
            terms = dict(config, parent_id=parent['id'], candidate_id=candidate['id'],
                         members=[config['members'][i] for i in group['members']])
            timing = dict(evidence_seconds=perf_counter() - began)
            actual_total = sum(candidate['targets'])
            row = dict(micros=actual_total, allocation=dict(micros=candidate['targets'],
                       unused=candidate['tested_total'] - actual_total),
                       metrics=pair['is_metrics'], overlap_skips=pair['overlap_skips'],
                       account_comparison=dict(pair, oos_paths_file='oos_paths.json',
                            oos_trades_file='oos_trades.csv'))
            # The standard Simulation inspection also drives the equity chart and strategy diagnostics.
            model = dict(windows={'is': parent['recommendation']['is_days'], 'oos': pair.get('oos_days')},
                         law=parent['recommendation']['law'], sizes=[row],
                         members=[source_summary(snapshot) for snapshot in snapshots['is']],
                         size_rule='manual', reporting_preset=config['size_rule'])
            if parent['phase'] == 'funded':
                targets = candidate['targets']
                sequential = bool(config.get('overlap_policy'))
                model['tier_targets'] = [dict(opening_profit=profit, cap_mnq=cap, targets=(
                    desk_basket.allocation(targets, min(sum(targets), cap))['micros'] if sequential
                    else [min(target, cap) for target in targets])) for profit, cap, _ in parent['rules']['levels']]
            report = dict(format_version=1, model_version=desk_recommendation.DETAIL_VERSION, phase=parent['phase'],
                          settings=dict(ANALYSIS_MODE='prop_desk_recommendation_evidence'), configuration=terms,
                          profile_label=parent['profile_label'], source=snapshots['is'][0],
                          source_summary=source_summary(snapshots['is'][0]), sources=snapshots, basket=model,
                          rules=parent['rules'], calculations={}, recommendation_evidence=timing,
                          provenance=dict(parent['provenance'], parent_report_sha256=sha,
                                          path_seeds=parent['provenance']['path_seeds'][:candidate['paths']],
                                          simulation=dict(parent['provenance']['simulation'], simulations=candidate['paths'])))
            publish(analyses, id, folder, report)
    except Exception as exc:
        analyses._update(id, 'error', 'Frozen allocation evidence failed', str(exc))


def launch_diagnostics(runs, analyses, body, datasets):
    terms = body.model_dump()
    if terms['size_basis'] is None:
        del terms['size_basis']
    with analyses.lock:
        parent, parent_sha = diagnostic_parent(analyses, body.parent_id)
    prepared = desk_diagnostics.prepare(runs, analyses, terms, datasets, parent, parent_sha)
    refs = {snapshot['backtest']['id'] for snapshot in prepared['snapshots'].values()}
    key = f'{desk.REQUEST_PREFIX}{parent["phase"]}:diagnostics:{digest(prepared["identity"])}'
    with analyses.lock:
        desk_diagnostics.verify_sources(runs, prepared['snapshots'])
        expected = dataset_evidence(datasets, prepared['dataset']['id'])
        if not expected or any(prepared['dataset'].get(key) != value for key, value in expected.items()):
            raise ResearchConflict('The saved strategy dataset changed while checking it.')
        prepared['dataset'] = expected
        return enqueue(analyses, key, body.source_backtest_id, refs, 'strategy diagnostics', run_diagnostics,
                       (runs, datasets, parent['phase'], parent['profile_label'], prepared))


def run_diagnostics(analyses, id, runs, datasets, phase, profile_label, prepared):
    try:
        analyses._update(id, 'running', 'Simulating standalone strategy diagnostics')
        settings = prepared['identity']
        terms = settings['configuration']
        verify_dataset(datasets, prepared['dataset'])
        desk_diagnostics.verify_sources(runs, prepared['snapshots'])
        with TemporaryDirectory(prefix='.pending-', dir=analyses.root) as temp:
            staged = Path(temp) / 'report'
            staged.mkdir()
            with analyses.runtime.activate():
                summary = desk_diagnostics.calculate(prepared, staged)
            snapshots = prepared['snapshots']
            report = dict(format_version=1, model_version=settings['model_version'], phase=phase,
                          settings=dict(ANALYSIS_MODE=desk_diagnostics.MODE), configuration=terms,
                          profile_label=profile_label, source_summary=source_summary(snapshots['is']),
                          source=snapshots['is'], sources=snapshots, provenance=settings,
                          calculations=summary, diagnostics=True)
            desk_diagnostics.verify_sources(runs, snapshots)
            with analyses.lock:
                _, actual_sha = diagnostic_parent(analyses, terms['parent_id'])
                if actual_sha != settings['parent_report_sha256']:
                    raise ResearchConflict('The saved parent changed during diagnostics.')
                publish(analyses, id, staged, report)
    except Exception as exc:
        analyses._update(id, 'error', 'Prop Desk strategy diagnostics failed', str(exc))


def oos_prefix(parent):
    return f'{desk.REQUEST_PREFIX}{parent["phase"]}:oos:{parent["id"]}.'


def oos_availability(analyses, parent):
    try:
        rank, _, _, _ = desk_oos.selection(parent)
    except ValueError as exc:
        return dict(unavailable=str(exc))
    with analyses.connect() as db:
        saved = db.execute("SELECT id FROM analyses WHERE request_hash GLOB ? "
                           "AND status IN ('queued','running','complete') ORDER BY rowid DESC LIMIT 1",
                           (oos_prefix(parent) + '*',)).fetchone()
    return dict(combination=rank['combination'], micros=rank['micros'],
                saved=public_job(analyses.get(saved[0])) if saved else None)


def launch_oos_assessment(runs, analyses, body, datasets):
    with analyses.lock:
        parent, parent_sha = diagnostic_parent(analyses, body.parent_id)
    if 'optimizer' not in parent:
        raise ValueError('Open a completed Prop Desk Optimise result.')
    prepared = desk_oos.prepare(runs, datasets, analyses, parent, parent_sha, analyses.root / body.parent_id)
    refs = {source['backtest']['id'] for group in prepared['snapshots'].values() for source in group}
    with analyses.lock:
        desk_oos.verify_sources(runs, prepared['snapshots'])
        expected = dataset_evidence(datasets, prepared['dataset']['id'])
        if not expected or any(prepared['dataset'].get(key) != value for key, value in expected.items()):
            raise ResearchConflict('The saved dataset changed while verifying the OOS assessment.')
        prepared['dataset'] = expected
        return enqueue(analyses, oos_prefix(parent) + prepared['key'], prepared['configuration']['members'][0]['source_backtest_id'],
                       refs, 'OOS account assessment', run_oos_assessment,
                       (runs, datasets, parent['profile_label'], prepared), strict_seal=True)


def run_oos_assessment(analyses, id, runs, datasets, profile_label, prepared):
    try:
        analyses._update(id, 'running', 'Assessing the frozen allocation on OOS sessions')
        terms, identity = prepared['configuration'], prepared['identity']
        verify_dataset(datasets, prepared['dataset'])
        desk_oos.verify_sources(runs, prepared['snapshots'])
        with TemporaryDirectory(prefix='.pending-', dir=analyses.root) as temp:
            staged = Path(temp) / 'report'
            staged.mkdir()
            with analyses.runtime.activate():
                summary = desk_oos.calculate(prepared, staged)
            snapshots = prepared['snapshots']
            report = dict(format_version=1, model_version=desk_oos.VERSION, phase=prepared['phase'],
                          settings=dict(ANALYSIS_MODE=desk_oos.MODE), configuration=terms,
                          profile_label=profile_label, source_summary=source_summary(snapshots['is'][0]),
                          source=snapshots['is'][0], sources=snapshots, provenance=dict(
                              identity, parent_evidence=prepared['evidence'], rules=prepared['rules']),
                          calculations=summary, oos_assessment=True)
            verify_dataset(datasets, prepared['dataset'])
            desk_oos.verify_sources(runs, snapshots)
            with analyses.lock:
                _, sha = diagnostic_parent(analyses, terms['parent_id'])
                if sha != identity['parent_report_sha256']:
                    raise ResearchConflict('The saved Optimise result changed during the OOS assessment.')
                publish(analyses, id, staged, report)
    except Exception as exc:
        analyses._update(id, 'error', 'Prop Desk OOS account assessment failed', str(exc))


def fixed_report(runs, body, configuration, prepared, staged):
    results, paths, rules = desk.calculate(runs, body, configuration, prepared)
    evidence = prepared['evidence']
    snapshot = evidence['source']
    (staged / 'source_sessions.json').write_text(canonical(dict(
        period=snapshot['profile_research_period'],
        columns=['net P&L per NQ equivalent', 'adverse excursion per NQ equivalent',
                 'ordered adverse frontier when available', 'Lucid intraday payout eligibility when applicable'],
        days=prepared['days'])), encoding='utf-8')
    (staged / 'path_outcomes.json').write_text(canonical(paths), encoding='utf-8')
    return dict(format_version=1, model_version=desk.VERSION, phase=body.phase,
                settings=dict(ANALYSIS_MODE=desk.MODE), configuration=configuration,
                profile_label=desk.PROFILES[body.profile_id]['label'],
                source=snapshot, source_summary=source_summary(snapshot),
                rules=rules, provenance=evidence, calculations=results,
                check_sha256=prepared['identity'])


def basket_report(runs, analyses, id, body, configuration, prepared, staged):
    def progress(message):
        analyses._update(id, 'running', message)

    version, mode = desk_basket.VERSION, 'prop_desk_basket'
    evidence = prepared['evidence']
    model = {}
    if body.simulation_size_rule is None:
        sizes, rules = desk_basket.calculate(runs, body, configuration, prepared, staged, progress)
        windows = prepared['windows']
    else:
        combo, model, rules, seeds = desk_parity.simulation(runs, body, configuration, prepared, staged, progress)
        evidence = dict(evidence, path_seeds=seeds)
        sizes = combo['sizes']
        windows = {'is': prepared['is_days'], 'oos': combo['oos_days'] or None}
        output = staged / combo['directory']
        for artifact in output.iterdir():
            artifact.rename(staged / artifact.name)
        output.rmdir()
        desk_basket.verify(runs, prepared)
        version, mode = desk_parity.SIMULATION_VERSION, 'prop_desk_simulation'
    snapshots = prepared['snapshots']
    return dict(format_version=1, model_version=desk_overlap.version(version, configuration), phase=body.phase,
                settings=dict(ANALYSIS_MODE=mode), configuration=configuration,
                profile_label=desk.PROFILES[body.profile_id]['label'],
                source=snapshots['is'][0], source_summary=source_summary(snapshots['is'][0]),
                basket=dict(windows=windows, law=desk_overlap.LAW if body.overlap_policy else desk_basket.LAW, sizes=sizes,
                            members=[source_summary(s) for s in snapshots['is']], **model),
                sources=snapshots, rules=rules, provenance=evidence, calculations={},
                check_sha256=prepared['identity'])


def optimizer_report(runs, analyses, id, body, configuration, prepared, staged):
    def progress(message):
        analyses._update(id, 'running', message)

    engine = desk_subset_optimizer if isinstance(body, SubsetOptimizerLaunch) else desk_optimizer
    version, mode = engine.VERSION, engine.MODE
    if isinstance(body, SubsetOptimizerLaunch) and body.compare_accounts:
        result, rules, seeds = desk_parity.search(runs, body, configuration, prepared, staged, progress)
        desk_basket.verify(runs, prepared)
        version = desk_parity.SEARCH_VERSION
    else:
        result, rules, seeds = engine.calculate(runs, body, configuration, prepared, staged, progress)
    snapshots = prepared['snapshots']
    summaries = [source_summary(s) for s in snapshots['is']]
    result['members'] = summaries
    evidence = dict(prepared['evidence'], path_seeds=seeds)
    return dict(format_version=1, model_version=desk_overlap.version(version, configuration), phase=body.phase,
                settings=dict(ANALYSIS_MODE=mode), configuration=configuration,
                profile_label=desk.PROFILES[body.profile_id]['label'], source=snapshots['is'][0],
                source_summary=summaries[0], sources=snapshots, rules=rules, optimizer=result,
                provenance=evidence, calculations={}, check_sha256=prepared['identity'])


def verified(analyses, id):
    try:
        return analyses.fingerprint(id) is not None
    except (OSError, ValueError, KeyError):
        return False


async def qualified_candidates(request):
    """Use the same verified campaign candidates as the main Prop Sim."""
    return (await request.app.state.prop_sim_preparation.candidates_async())['items']


def verify_selection(body, candidates):
    eligible = {}
    for candidate in candidates:
        eligible.setdefault(candidate['source_backtest_id'], set()).add(candidate['oos_report_id'])
    selected = ([(member.source_backtest_id, member.oos_backtest_id) for member in body.members]
                if isinstance(body, BasketConfiguration) else [(body.source_backtest_id, None)])
    for source_id, oos_id in selected:
        if source_id not in eligible:
            raise ValueError(f'Backtest {source_id[:8]} has not passed current campaign qualification. '
                             'Prop Desk requires Mechanics, IS Broad, IS Narrow, OOS and Monte Carlo.')
        if oos_id is not None and oos_id not in eligible[source_id]:
            raise ValueError(f'OOS report {oos_id[:8]} must retain its selected IS parent '
                             'and match that configuration’s current campaign qualification.')


async def invoke(request, fn, body, *, require_qualification=False):
    try:
        if require_qualification:
            verify_selection(body, await qualified_candidates(request))
        return await run_in_threadpool(fn, request.app.state.runs, request.app.state.prop_analyses,
                                       body, request.app.state.store)
    except ResearchConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except (ValueError, KeyError, OSError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get('/defaults')
def defaults():
    return dict(profiles=desk.PROFILES, paths=desk.PATHS, seed=desk.SEED, block=desk.BLOCK_WEEKDAYS,
                basket_first_year=desk_basket.FIRST_YEAR, basket_life_cutoff=2000,
                optimizer=dict(max_pairs=desk_optimizer.MAX_PAIRS, max_pair_sessions=desk_optimizer.MAX_PAIR_SESSIONS,
                               recommendation_max_members=desk_recommendation.MAX_MEMBERS,
                               recommendation_exact_limit=desk_recommendation.EXACT_LIMIT,
                               recommendation_full_screen_limit=desk_recommendation.FULL_SCREEN_LIMIT,
                               global_max_allocations=desk_global_ranking.MAX_ALLOCATIONS,
                               global_max_allocation_sessions=desk_global_ranking.MAX_ALLOCATION_SESSIONS))


def catalogue_page(runs, candidates, offset, limit):
    links = {item['source_backtest_id']: item['oos_report_id'] for item in reversed(candidates)}
    if not links:
        return dict(items=[], total=0)
    placeholders = ','.join('?' for _ in links)
    with runs.connect() as db:
        db.execute('BEGIN')
        total = db.execute(f'SELECT COUNT(*) FROM runs WHERE id IN ({placeholders})', tuple(links)).fetchone()[0]
        records = [json.loads(raw) for raw, in db.execute(
            f'SELECT manifest FROM runs WHERE id IN ({placeholders}) ORDER BY created_at DESC,id LIMIT ? OFFSET ?',
            (*links, limit, offset))]
        items = []
        for record in records:
            meta = record['run_metadata']
            child_id = links[record['id']]
            linked = None
            if child_id is not None:
                row = db.execute('SELECT manifest FROM runs WHERE id=?', (child_id,)).fetchone()
                if not row:
                    raise ValueError('Qualified OOS evidence changed while loading Prop Desk strategies. Retry.')
                linked = dict(id=child_id, **saved_oos_period(json.loads(row[0])))
            items.append(dict(id=record['id'], strategy=meta['strategy']['id'], dataset=meta['dataset']['name'],
                              role=(meta.get('research') or {}).get('phase'),
                              start_utc=record['period_start_utc'], end_utc=record['period_end_utc'], oos=linked))
    return dict(items=items, total=total)


@router.get('/sources')
async def sources(request: Request, offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100)):
    try:
        candidates = await qualified_candidates(request)
        return await run_in_threadpool(catalogue_page, request.app.state.runs, candidates, offset, limit)
    except (ValueError, KeyError, OSError) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post('/check')
async def check(body: Configuration, request: Request):
    return await invoke(request, check_configuration, body, require_qualification=True)

@router.post('/basket/check')
async def check_basket(body: BasketConfiguration, request: Request):
    return await invoke(request, check_configuration, body, require_qualification=True)


@router.post('', status_code=202)
async def submit(body: Launch, request: Request):
    return await invoke(request, launch, body, require_qualification=True)

@router.post('/basket', status_code=202)
async def submit_basket(body: BasketLaunch, request: Request):
    return await invoke(request, launch, body, require_qualification=True)


@router.post('/optimizer', status_code=202)
async def submit_optimizer(body: OptimizerLaunch, request: Request):
    return await invoke(request, launch, body, require_qualification=True)


@router.post('/optimizer/subsets', status_code=202)
async def submit_subset_optimizer(body: SubsetOptimizerLaunch, request: Request):
    return await invoke(request, launch, body, require_qualification=True)


@router.post('/recommendations', status_code=202)
async def submit_recommendation(body: RecommendationLaunch, request: Request):
    return await invoke(request, launch, body, require_qualification=True)


@router.post('/recommendations/evidence', status_code=202)
async def submit_recommendation_evidence(body: RecommendationEvidenceLaunch, request: Request):
    return await invoke(request, launch_recommendation_evidence, body)


@router.post('/diagnostics', status_code=202)
async def submit_diagnostics(body: DiagnosticsLaunch, request: Request):
    return await invoke(request, launch_diagnostics, body)


@router.post('/oos-assessments', status_code=202)
async def submit_oos_assessment(body: OOSAssessmentLaunch, request: Request):
    return await invoke(request, launch_oos_assessment, body)


@router.get('')
def history(request: Request, offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    analyses = request.app.state.prop_analyses
    with analyses.connect() as db:
        db.row_factory = sqlite3.Row
        rows = db.execute('SELECT * FROM analyses WHERE request_hash GLOB ? '
                          'ORDER BY created DESC,id LIMIT ? OFFSET ?',
                          (desk.REQUEST_PREFIX + '*', limit + 1, offset)).fetchall()
    return dict(items=[public_job(row) for row in rows[:limit]], has_more=len(rows) > limit)


@router.get('/{id}/allocation-evidence')
def get_allocation_evidence(id: UUID, request: Request):
    analyses = request.app.state.prop_analyses
    with analyses.lock:
        try:
            report, sha = diagnostic_parent(analyses, id.hex)
        except (OSError, ValueError, KeyError, ResearchConflict) as exc:
            raise HTTPException(409, str(exc)) from exc
        if 'recommendation' not in report:
            raise HTTPException(404, 'Saved strategy recommendation not found.')
        return recommendation_listing(analyses, report, sha)


@router.get('/{id}')
def get(id: UUID, request: Request):
    analyses = request.app.state.prop_analyses
    with analyses.lock:
        record = analyses.get(id.hex)
        if not record or not record['request_hash'].startswith(desk.REQUEST_PREFIX):
            raise HTTPException(404, 'Prop Desk run not found.')
        result = public_job(record)
        if record['status'] == 'complete':
            if not verified(analyses, id.hex):
                raise HTTPException(409, 'Saved Prop Desk result failed its integrity check.')
            report = json.loads((analyses.root / id.hex / 'report.json').read_text())
            result['report'] = {key: report[key] for key in (
                'model_version', 'configuration', 'profile_label', 'source_summary', 'calculations')}
            if report.get('diagnostics'):
                result['report']['diagnostics'] = dict(model=report['provenance']['model'],
                                                       windows=report['provenance']['windows'])
            elif report.get('oos_assessment'):
                result['report']['oos_assessment'] = dict(windows=report['provenance']['windows'])
            else:
                result['report']['rules'] = report['rules']
                result['report']['simulation'] = report['provenance']['simulation']
                result['report']['sampling'] = report['provenance']['sampling']
            if 'basket' in report:
                result['report']['basket'] = report['basket']
            if 'recommendation_evidence' in report:
                result['report']['recommendation_evidence'] = report['recommendation_evidence']
            if 'recommendation' in report:
                result['report']['recommendation'] = report['recommendation']
                sha = sha256((analyses.root / id.hex / 'report.json').read_bytes()).hexdigest()
                result['report'].update(recommendation_listing(analyses, report, sha))
            if 'optimizer' in report:
                result['report']['optimizer'] = report['optimizer']
                if report['model_version'] != desk_overlap.version(desk_parity.SEARCH_VERSION, report['configuration']):
                    result['report']['oos_assessment'] = oos_availability(analyses, report)
    return result
