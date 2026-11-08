"""Phase-neutral calendar and saved-IS candidate admission."""
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import date
from hashlib import sha256
from .adapter import canonical, source_record
from .phase_profiles import prepare_phase_source


def declared_is_coverage(record):
    """Native plan or explicit exporter IS coverage, without inventing OOS."""
    metadata = record['run_metadata']
    research = metadata.get('research') or {}
    if research.get('phase') != 'is':
        raise ValueError('Phase selection requires a declared IS backtest/trial; OOS and undeclared sources reject.')
    if metadata.get('source', {}).get('kind') == 'external_trade_export':
        sessions = metadata['external_manifest']['coverage']['sessions']
        if not sessions:
            raise ValueError('External IS coverage requires an explicit session inventory.')
        return dict(first_session=sessions[0], last_session=sessions[-1])
    return dict(first_session=research['plan']['is_start'], last_session=research['plan']['is_end'])

CANDIDATE_CONFIRMATION_THRESHOLD = 128


def stable_phase_policy_identity(row, phase):
    """Tie preference independent of run IDs and opposite-phase declarations."""
    if phase not in ('evaluation', 'funded'):
        raise ValueError('Unknown phase for policy identity.')
    strategy = deepcopy(row['manifest']['strategy'])
    strategy.pop('session_flattening', None)
    configuration = deepcopy(row['manifest']['configuration'])
    configuration.pop('source')
    return sha256(canonical(dict(phase=phase, strategy=strategy, configuration=configuration)).encode()).hexdigest()


class CandidateConfirmationRequired(ValueError):
    def __init__(self, count):
        self.detail = dict(code='candidate_confirmation_required', candidate_count=count,
            confirmation_threshold=CANDIDATE_CONFIRMATION_THRESHOLD,
            message=f'This search contains {count} candidates. Confirm this count to continue; larger searches require more time and storage.')
        super().__init__(self.detail['message'])


def require_candidate_confirmation(count, confirmed_count):
    if ((count > CANDIDATE_CONFIRMATION_THRESHOLD and confirmed_count != count)
            or (confirmed_count is not None and confirmed_count != count)):
        raise CandidateConfirmationRequired(count)


def validate_phase_work(search, observed_session_count=None):
    """One preflight bound shared by preview, source checks and reservation.

    Counts describe captured history units, never certify historical evidence.
    A scalar count applies to every candidate; per-candidate counts are accepted
    after ordinary source admission (for external exporter-declared coverage).
    """
    from .phase_dispatch import module_for_mode
    module_for_mode(search.mode)  # Unknown modes fail closed.
    funded = search.mode == 'funded_optimization'
    count = len(search.candidates)
    estimate = (sum(c.simulation.simulations*5000 for c in search.candidates) if funded else
                sum(c.sampling.chain_simulations*700+c.simulation.simulations*100 for c in search.candidates))
    work = sum(c.simulation.simulations for c in search.candidates)*search.horizon_calendar_days if funded else 0
    cfg = getattr(search, 'conservative_objective', None)
    indices = 0
    if cfg is not None:
        work += count*cfg.replicates*cfg.simulations_per_replicate*search.horizon_calendar_days
        estimate += count*cfg.replicates*512
        if observed_session_count is not None:
            counts = ([observed_session_count]*count if type(observed_session_count) is int else list(observed_session_count))
            if len(counts) != count or any(type(n) is not int or n < 0 for n in counts):
                raise ValueError('History capture requires one nonnegative observed-session count per candidate.')
            indices = cfg.replicates*sum(counts)
            estimate += indices*8
            if indices > 1_000_000:
                raise ValueError('Historical resampling capture exceeds one million session indices; narrow the declared search.')
    if estimate > 100*1024*1024:
        raise ValueError('Declared candidate/path capture exceeds the report resource bound; reduce the explicit search.')
    if work > 50_000_000:
        raise ValueError('Declared funded search exceeds 50 million path calendar days including historical refits; narrow the explicit search.')
    return dict(estimated_capture_bytes=estimate, funded_path_calendar_days=work,
                historical_session_indices=indices if observed_session_count is not None else None)


@dataclass(frozen=True)
class PhaseCalendar:
    start_dates: tuple[str, ...]
    coverage_end: str
    closures: tuple[str, ...] = ()
    timezone: str = 'America/Chicago'
    version: str = 'user-declared-weekdays-v1'

    def __post_init__(self):
        if not isinstance(self.start_dates, tuple) or not isinstance(self.closures, tuple):
            raise ValueError('Calendar dates must be immutable tuples.')
        for value in (*self.start_dates, self.coverage_end, *self.closures):
            if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
                raise ValueError('Calendar dates must use canonical YYYY-MM-DD format.')
        if not 1 <= len(self.start_dates) <= 366 or len(set(self.start_dates)) != len(self.start_dates):
            raise ValueError('Use 1–366 distinct target start dates.')
        starts = [date.fromisoformat(s) for s in self.start_dates]
        end = date.fromisoformat(self.coverage_end)
        if not max(starts) <= end or (end - min(starts)).days > 40000:
            raise ValueError('Calendar coverage must contain the start cohort and span at most 40,000 days.')
        if self.timezone != 'America/Chicago':
            raise ValueError('Only the CME America/Chicago session-date convention is supported.')
        if not isinstance(self.version, str) or not self.version or len(set(self.closures)) != len(self.closures):
            raise ValueError('A calendar version and unique full-session closures are required.')
        for closure in self.closures:
            if not min(starts) <= date.fromisoformat(closure) <= end:
                raise ValueError('Closure is outside declared calendar coverage.')


def verify_training_context(runs, search, context):
    """Admit server-created nested training reports without relabeling them IS.

    This argument is never part of a public phase request. Its self-hash is an
    integrity check; authority comes from the coordinator and saved reports.
    """
    from ..optimization_cache import artifacts, engine_identity
    def require(condition, message):
        if not condition:
            raise ValueError('Invalid nested phase training context: ' + message)
    require(isinstance(context, dict), 'expected an internal context object.')
    terminal = context.get('version') in ('procedure-training-v1', 'procedure-reference-v1')
    reference = context.get('version') in ('nested-phase-reference-v1', 'procedure-reference-v1')
    membership_key = 'source_configuration_ids' if reference else 'qualified_configuration_ids'
    admission_key = 'reference_declaration_sha256' if reference else 'qualification_sha256'
    role = ('procedure_reference_train' if reference else 'procedure_policy_train') if terminal else ('baseline_train' if reference else 'policy_train')
    required = {'version', 'campaign_id', admission_key,
        'input_identity', 'engine_identity', 'train_window', 'information_cutoff_session',
        membership_key, 'training_sources', 'session_inventory', 'context_sha256'}
    required |= {'application_id','procedure_sha256','application_role'} if terminal else {'outer_fold_index'}
    require(required <= context.keys(), 'missing provenance fields.')
    unsigned = {k:v for k,v in context.items() if k != 'context_sha256'}
    require(context['version'] in ('nested-phase-training-v1', 'nested-phase-reference-v1', 'procedure-training-v1', 'procedure-reference-v1') and
        sha256(canonical(unsigned).encode()).hexdigest() == context['context_sha256'], 'identity differs.')
    if terminal:
        require(context.get('application_role') in ('final_fit','current_development') and 'outer_fold_index' not in context, 'invalid terminal application discriminant.')
    if reference:
        declarations = context.get('reference_declarations')
        require(context.get('admission_scope') == 'predeclared_reference' and
            isinstance(declarations, list) and declarations, 'missing explicit reference declaration.')
        require(context.get('recommendation_eligible') is False,
            'a reference context cannot grant recommendation authority.')
        require('qualified_configuration_ids' not in context and 'qualification_sha256' not in context,
            'a measured reference must not masquerade as qualified membership.')
        require(sha256(canonical(declarations).encode()).hexdigest() == context[admission_key],
            'reference declaration changed.')
        require(context.get('reference_ids') == sorted({d['id'] for d in declarations})
            and len(context['reference_ids']) == len(declarations), 'reference identifiers differ.')
        require(context.get(membership_key) == sorted({d['source_configuration_id'] for d in declarations}),
            'reference signal membership differs.')
    require(context['engine_identity'] == engine_identity(), 'implementation changed.')
    window = context['train_window']; sessions = window.get('sessions', [])
    require(isinstance(sessions, list) and sessions and sessions == sorted(set(sessions)), 'invalid ordered session inventory.')
    require(all(isinstance(s, str) and date.fromisoformat(s).isoformat() == s for s in sessions), 'noncanonical session date.')
    require(window.get('first_session') == sessions[0] and window.get('last_session') == sessions[-1]
        and context['information_cutoff_session'] == sessions[-1], 'training window/cutoff differs.')
    inventory = context['session_inventory']
    require(isinstance(inventory, dict) and set(inventory) == set(sessions) and
        all(type(n) is int and n > 0 for n in inventory.values()), 'each included session needs observed bars.')
    sources = context['training_sources']; ids = context[membership_key]
    require(isinstance(sources, dict) and sources and isinstance(ids, list) and ids == sorted(set(ids)), 'invalid qualified membership.')
    require(sorted(s['configuration_id'] for s in sources.values()) == ids, 'training sources omit or duplicate qualified configurations.')
    require({c.source.source_backtest_id for c in search.candidates} == set(sources), 'candidate sources differ from the complete qualified set.')
    for candidate in search.candidates:
        require(candidate.period is not None and asdict(candidate.period) ==
            dict(first_session=sessions[0], last_session=sessions[-1]), 'candidate window is not the full declared training window.')
    for id, expected in sources.items():
        record = source_record(runs, id); meta = record['run_metadata']; research = meta.get('research') or {}
        require(record['status'] == 'complete' and meta.get('source', {}).get('kind') != 'external_trade_export', 'expected a complete native training report.')
        require(research.get('phase') == 'inner' and research.get('role') == role, 'source has the wrong nested training role.')
        require(research.get('campaign_id') == context['campaign_id'], 'source campaign differs.')
        if terminal:
            require(all(research.get(key)==context[key] for key in ('application_id','procedure_sha256','application_role')) and 'outer_fold' not in research, 'source terminal application differs.')
        else:
            require(research.get('outer_fold') == context['outer_fold_index'], 'source fold differs.')
        require(canonical(research.get('window')) == canonical(window) and
            research.get('information_cutoff_session') == sessions[-1], 'source information boundary differs.')
        require(research.get(admission_key) == context[admission_key] and
            research.get('input_identity') == context['input_identity'] and research.get('cold_start') is True,
            'source qualification/protocol differs.')
        if reference:
            require(research.get('reference_ids') == context['reference_ids'] and
                research.get('admission_scope') == 'predeclared_reference' and
                research.get('recommendation_eligible') is False, 'source reference authority differs.')
        strategy = meta['strategy']
        require(strategy['id'] == expected['strategy_id'] and canonical(strategy['parameters']) == canonical(expected['parameters'])
            and sha256(canonical(strategy).encode()).hexdigest() == expected['strategy_provenance_sha256'], 'strategy parameters or implementation changed.')
        require(sha256(canonical(record).encode()).hexdigest() == expected['manifest_sha256'], 'source manifest changed.')
        require(artifacts(runs.root, record) == expected['artifact_sha256'], 'source artifact changed.')
    if reference:
        from .phase_profiles import EvaluationProfile, FundedProfile, SizingConfiguration
        from .phase_dispatch import module_for_mode
        module_for_mode(search.mode)  # Reject unknown phases before resolving the profile type.
        phase = search.mode.removesuffix('_optimization')
        profile_type = EvaluationProfile if phase == 'evaluation' else FundedProfile
        matched = []
        for candidate in search.candidates:
            configuration_id = sources[candidate.source.source_backtest_id]['configuration_id']
            options = []
            for declaration in declarations:
                if declaration['phase'] != phase or declaration['source_configuration_id'] != configuration_id:
                    continue
                policy = declaration['policy']
                sizing = SizingConfiguration(**policy['sizing']) if policy.get('sizing') is not None else None
                if (candidate.profile == profile_type(**declaration['profile']) and candidate.micros == policy['micros']
                        and candidate.sizing == sizing):
                    options.append(declaration['id'])
            require(len(options) == 1, 'reference quantity/profile/policy is outside its declaration.')
            matched.extend(options)
        require(sorted(matched) == context['reference_ids'], 'reference candidates omit or duplicate a declared reference.')
    return sessions


def check_candidates(runs, search, assessment=None, *, training_context=None, datasets=None):
    """Reconcile every source before queueing; admit only comparable saved IS."""
    validate_phase_work(search, len(training_context['session_inventory']) if training_context else None)
    rows = []
    common = None
    if assessment is not None and training_context is not None:
        raise ValueError('Frozen OOS assessment and nested phase training are distinct source roles.')
    observed = verify_training_context(runs, search, training_context) if training_context is not None else None
    if getattr(search,'native_execution',None) is not None:
        from .native_search import check_native_candidates
        return check_native_candidates(datasets,runs,search,assessment=assessment,
            training_context=training_context,observed_sessions=observed)
    for candidate in search.candidates:
        record = source_record(runs, candidate.source.source_backtest_id)
        metadata = record['run_metadata']
        research = metadata.get('research') or {}
        external = metadata.get('source', {}).get('kind') == 'external_trade_export'
        if assessment:
            if external:
                raise ValueError('Imported frozen choices require a separately supplied, verified external OOS source; native OOS rerun cannot generate external strategy outcomes.')
            selected = None
            for mapping in assessment['sources']:
                if mapping['source_id'] != record['id']:
                    continue
                expected = deepcopy(mapping['frozen_manifest']['configuration'])
                expected['source']['source_backtest_id'] = record['id']
                expected['period'] = dict(first_session=research['plan']['oos_start'], last_session=research['plan']['oos_end'])
                if canonical(asdict(candidate)) == canonical(expected):
                    selected = mapping
                    break
            if selected is None:
                raise ValueError('Assessment source is outside the frozen family.')
            saved = selected['frozen_manifest']['source']['backtest']
            if (research.get('phase') != 'oos' or research.get('parent_run_id') != saved['id']
                    or metadata['strategy'] != saved['run_metadata']['strategy']
                    or metadata['dataset'] != saved['run_metadata']['dataset']
                    or record['execution_settings'] != saved['execution_settings']
                    or research['plan'] != saved['run_metadata']['research']['plan']):
                raise ValueError('OOS source must retain its frozen IS parent, strategy, split and execution costs.')
            expected = dict(selected['frozen_manifest']['configuration'])
            expected['source'] = dict(expected['source'], source_backtest_id=record['id'])
            expected['period'] = dict(first_session=research['plan']['oos_start'], last_session=research['plan']['oos_end'])
            if canonical(asdict(candidate)) != canonical(expected):
                raise ValueError('Assessment parameters, size, profile, costs, sampling and window are frozen.')
        elif training_context is None:
            declared_is_coverage(record)
        snapshot, _, _ = prepare_phase_source(runs, candidate.source, candidate.profile,
            candidate.micros, candidate.simulation, candidate.period, candidate.costs, candidate.sizing,
            **({'observed_sessions':observed} if observed is not None else {}))
        protocol = dict(dataset=metadata['dataset'], period=snapshot['profile_research_period'],
            execution=record['execution_settings'], costs=asdict(candidate.costs))
        # Research IDs/strategy IDs may differ; the actual split must not.
        if external:
            manifest = metadata['external_manifest']
            protocol = dict(source_kind='external_trade_export', dataset=manifest['dataset'],
                instrument=manifest['instrument'], time=manifest['time'], coverage=manifest['coverage'],
                period=snapshot['profile_research_period'], execution=manifest['execution'],
                costs=asdict(candidate.costs), research_windows=declared_is_coverage(record))
        elif training_context is not None:
            protocol['research_windows'] = training_context['train_window']
        else:
            protocol['research_windows'] = {k: research['plan'][k] for k in ('is_start', 'is_end', 'oos_start', 'oos_end')}
        if common is not None and canonical(protocol) != canonical(common):
            raise ValueError('Candidates require identical dataset, research windows, source costs and execution protocol.')
        common = protocol
        manifest = dict(configuration=asdict(candidate), strategy=metadata['strategy'],
                        source=snapshot)
        if training_context is not None:
            manifest['training_context_sha256'] = training_context['context_sha256']
        # Retain the full source for audit, but administrative automatic joint
        # reports must not influence phase candidate keys or tie presentation.
        numerical = deepcopy(manifest)
        numerical['source'].pop('manifest_sha256')
        numerical['source']['backtest']['run_metadata'].pop('automatic_prop_analysis', None)
        key = sha256(canonical(numerical).encode()).hexdigest()
        access = dict(status='unavailable', attempts=None)
        if external:
            access = dict(status='exporter_declared', prior_access=research['prior_access'],
                declaration=research['declaration'],
                interpretation='Exporter research/access claims are retained. No untouched-OOS claim or automatic external OOS execution.')
        origins = []
        if hasattr(runs, 'connect'):
            with runs.connect() as db:
                if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='optimization_trials'").fetchone():
                    origins = [dict(optimization_id=id, trial=trial) for id,trial in db.execute(
                        "SELECT optimization_id,trial FROM optimization_trials WHERE json_extract(payload,'$.run_id')=? ORDER BY optimization_id,trial",
                        (record['id'],)).fetchall()]
                exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='oos_attempts'").fetchone()
                if exists and not external:
                    history = db.execute('SELECT id,parent_run_id,run_id,status,created_at FROM oos_attempts WHERE strategy_id=? AND source_sha256=? ORDER BY created_at,id',
                        (metadata['strategy']['id'], metadata['dataset']['sha256'])).fetchall()
                    access = dict(status='recorded', attempts=[dict(zip(('id','parent_run_id','run_id','status','created_at'), r)) for r in history],
                        interpretation='Access history only; no OOS prices, metrics or outcomes enter selection. No untouched-OOS claim.')
        rows.append(dict(candidate_id=key, manifest=manifest, status='compatible', prior_access=access, origin_trials=origins))
    keys = [r['candidate_id'] for r in rows]
    if len(set(keys)) != len(keys):
        raise ValueError('Duplicate candidate definitions; remove duplicates explicitly.')
    if getattr(search, 'conservative_objective', None) is not None and training_context is None:
        counts = []
        for row in rows:
            source = row['manifest']['source']; bounds = source['profile_research_period']
            labels = source.get('canonical_manifest', {}).get('coverage', {}).get('sessions', [])
            counts.append(sum(bounds['first_session'] <= day <= bounds['last_session'] for day in labels))
        validate_phase_work(search, counts)
    return sorted(rows, key=lambda r: r['candidate_id'])


def capture_inputs(runs, staged, search, calculations):
    """Seal source inputs once through the existing report directory."""
    import shutil
    from pathlib import Path
    from .adapter import digest
    from .phase_profiles import verify_phase_source
    captured = set()
    for candidate in search.candidates:
        id = candidate.source.source_backtest_id
        if id in captured:
            continue
        captured.add(id)
        folder = staged/'inputs'/id
        folder.mkdir(parents=True)
        record = source_record(runs, id)
        if record['run_metadata'].get('source', {}).get('kind') == 'external_trade_export':
            from .external_source import capture
            capture(runs, id, folder)
        for name in ('trades.csv', 'intratrade_risk.csv', 'execution_decisions.jsonl'):
            path = runs.root/id/name
            if path.is_file(): shutil.copyfile(path, folder/name)
    for row in calculations['candidates']:
        c = next(c for c in search.candidates if canonical(asdict(c)) == canonical(row['manifest']['configuration']))
        snapshot = row['manifest']['source']
        verify_phase_source(runs, c.source, snapshot)
        folder = staged/'inputs'/c.source.source_backtest_id
        if digest(folder/'trades.csv') != snapshot['trades_sha256']:
            raise ValueError('Captured source changed during publication.')
        if snapshot.get('native_risk') and digest(folder/'intratrade_risk.csv') != snapshot['native_risk']['sha256']:
            raise ValueError('Captured risk changed during publication.')
        decisions = snapshot['backtest'].get('execution_decisions')
        if decisions and digest(folder/'execution_decisions.jsonl') != decisions['sha256']:
            raise ValueError('Captured native decisions changed during publication.')
        export = snapshot['excursion_input']
        if export['path']:
            target = staged/('input-export-'+export['sha256']+Path(export['path']).suffix)
            if not target.exists(): shutil.copyfile(export['path'], target)
            if digest(target) != export['sha256']: raise ValueError('Captured export changed during publication.')


def write_sizing_artifacts(staged, calculations):
    """Retained decision detail and complete summaries in the ordinary report."""
    import csv
    from pathlib import Path
    summaries = []
    fields = ['candidate_id', 'source_trade_id', 'stage', 'path_index', 'attempt', 'session_index',
        'source_session_index', 'calendar_date', 'quantity', 'action', 'requested_contracts',
        'denominator', 'denominator_value', 'risk_budget', 'planned_risk_per_mnq',
        'planned_total_risk', 'caps', 'reasons', 'state_before', 'state_after', 'account_hit', 'outcome']
    rows = []
    for candidate in calculations['candidates']:
        provenance = candidate.get('provenance') or candidate.get('component', {}).get('provenance', {})
        sizing = provenance.get('sizing')
        if sizing is None:
            continue
        summaries.append(dict(candidate_id=candidate['candidate_id'], **{k:v for k,v in sizing.items() if k != 'decisions'}))
        for decision in sizing['decisions']:
            value = dict(decision.get('decision', {}), **decision, candidate_id=candidate['candidate_id'])
            rows.append({k:canonical(value[k]) if isinstance(value.get(k), (dict, list)) else value.get(k) for k in fields})
    if not summaries:
        return
    (Path(staged)/'sizing_summary.json').write_text(canonical(summaries), encoding='utf-8')
    with (Path(staged)/'sizing_decisions.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
