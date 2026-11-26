"""Frozen account assessment of the first row of a sealed Prop Desk search."""

from collections import Counter
import csv
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory

from ..optimization_cache import digest
from . import desk, desk_basket as basket, desk_optimizer as optimizer, desk_overlap, desk_subset_optimizer
from .adapter import canonical, digest as file_digest
from .phase_profiles import verify_phase_source

MODE = 'prop_desk_oos_assessment'
VERSION = 'prop-desk-oos-assessment-v1'


def selection(parent):
    """Resolve the saved rank, allocation and member order from the parent only."""
    if parent['model_version'] != desk_overlap.version(desk_subset_optimizer.VERSION, parent['configuration']):
        raise ValueError('This Optimise result has no supported frozen subset sizing preset.')
    search = parent['optimizer']
    if not search['ranking']:
        raise ValueError('This Optimise result has no ranked combination with a positive allocation.')
    rank = search['ranking'][0]
    combo = next((item for item in search['combinations'] if item['id'] == rank['combination']), None)
    if combo is None:
        raise ValueError('The first-ranked combination is missing from the saved Optimise result.')
    size = next((item for item in combo['sizes'] if item['micros'] == rank['micros']), None)
    if size is None:
        raise ValueError('The first-ranked size is missing from the saved Optimise result.')
    members = [parent['configuration']['members'][index] for index in combo['members']]
    targets = size['allocation']['micros']
    if len(members) != len(targets) or not all(targets):
        raise ValueError('The saved winning combination has an invalid allocation.')
    for member in members:
        if not member.get('oos_backtest_id'):
            raise ValueError(f"Ranked strategy {member['source_backtest_id'][:8]} has no saved OOS link.")
    if not combo['oos_days']:
        raise ValueError('The ranked members have no common observed OOS sessions.')
    return rank, combo, size, members


def verify_sources(runs, snapshots):
    for group in snapshots.values():
        for snapshot in group:
            id = snapshot['backtest']['id']
            try:
                verify_phase_source(runs, desk.SavedTradeSource(id), snapshot)
            except (OSError, ValueError, KeyError) as exc:
                raise ValueError(f'Saved backtest {id[:8]} is unavailable or changed: {exc}') from exc


def _read_artifact(folder, parent, name):
    content = (folder / name).read_bytes()
    if sha256(content).hexdigest() != parent['files'][name]['sha256']:
        raise ValueError(f'The saved Optimise artifact changed: {name}.')
    return content


def _checked_engine(parent, profile, simulation, sampling, archived_snapshot):
    evidence = parent['provenance']
    active = desk.provenance(parent['phase'], archived_snapshot, profile,
                             evidence['micros'], simulation, sampling)
    if evidence['kernel'] != active['kernel']:
        raise ValueError('The installed account kernel differs from the saved Optimise kernel.')
    active_hashes = active['implementation_sha256']
    for module in (desk, basket, optimizer, desk_subset_optimizer):
        path = Path(module.__file__)
        active_hashes[path.name] = file_digest(path)
    sequential = parent['configuration'].get('overlap_policy') == desk_overlap.POLICY
    if sequential:
        path = Path(desk_overlap.__file__)
        active_hashes[path.name] = file_digest(path)
    for name, sha in active_hashes.items():
        if evidence['implementation_sha256'].get(name) != sha:
            raise ValueError(f'The saved Optimise numerical contract differs at {name}.')
    law = desk_overlap.LAW if sequential else basket.LAW
    if evidence['rng'] != optimizer.SAMPLING or parent['optimizer']['law'] != law:
        raise ValueError('The saved sampling or shared execution rule is incompatible.')


def prepare(runs, datasets, analyses, parent, parent_sha, folder):
    rank, combo, size, members = selection(parent)
    config, search, evidence = parent['configuration'], parent['optimizer'], parent['provenance']
    sequential = config.get('overlap_policy') == desk_overlap.POLICY
    phase, horizon, preset = parent['phase'], config['observation_sessions'], search['size_rule']
    if phase not in ('evaluation', 'funded'):
        raise ValueError('The saved Optimise account phase is unsupported.')
    valid_preset = preset == 'optimal' if phase == 'evaluation' else preset in ('first_year', 'account_life')
    if not valid_preset or config['size_rule'] != preset or (preset == 'first_year' and horizon < basket.FIRST_YEAR):
        raise ValueError('The saved Optimise sizing preset or observation horizon is incompatible.')
    seeds = evidence['path_seeds']
    if not seeds or len(seeds) != evidence['simulation']['simulations']:
        raise ValueError('The saved Optimise path seeds are incomplete.')
    profile_type = desk.EvaluationProfile if phase == 'evaluation' else desk.FundedProfile
    profile = profile_type(**evidence['profile'])
    if profile.profile_id != config['profile_id']:
        raise ValueError('The saved Optimise account profile is incompatible.')
    simulation = desk.SimulationConfig(**evidence['simulation'])
    sampling = desk.SamplingConfig(**evidence['sampling'])

    snapshots = {'is': [], 'oos': []}
    source_maps = {role: {snapshot['backtest']['id']: snapshot for snapshot in parent['sources'][role]}
                   for role in snapshots}
    for role, key in (('is', 'source_backtest_id'), ('oos', 'oos_backtest_id')):
        for member in members:
            id = member[key]
            if id not in source_maps[role]:
                raise ValueError(f'The saved {role.upper()} source seal for backtest {id[:8]} is missing.')
            snapshots[role].append(source_maps[role][id])
    verify_sources(runs, snapshots)
    _checked_engine(parent, profile, simulation, sampling, snapshots['is'][0])

    is_records = [basket.checked_record(runs, m['source_backtest_id'], 'is') for m in members]
    oos_records = [basket.checked_record(runs, m['oos_backtest_id'], 'oos', original)
                   for m, original in zip(members, is_records, strict=True)]
    dataset = is_records[0]['run_metadata']['dataset']
    if any((source['run_metadata']['dataset']['id'], source['run_metadata']['dataset']['sha256'])
           != (dataset['id'], dataset['sha256']) for source in is_records + oos_records):
        raise ValueError('The ranked members use different saved dataset versions.')
    current = datasets.get(dataset['id'])
    if not current or current['sha256'] != dataset['sha256']:
        raise ValueError('The ranked dataset is unavailable or its identity changed.')
    inventory = basket.inventory_sessions(datasets, dataset['id'], minimum_sessions=1)
    if inventory['source'] != evidence['dataset']:
        raise ValueError('The verified session inventory has a different dataset identity.')
    # Earlier readers may have a different implementation hash (e.g. pre-cache).
    # Reconcile session membership and the exact admitted ledger for both roles.
    frozen_pool = [entry['backtest'] for entry in parent['sources']['is']]
    is_days = basket.period(frozen_pool, inventory, 'is')
    oos_periods = []
    for source in oos_records:
        try:
            oos_periods.append(set(basket.period([source], inventory, 'oos')))
        except ValueError as exc:
            raise ValueError(f"Saved OOS backtest {source['id'][:8]} has insufficient observed coverage: {exc}") from exc
    common = sorted(set.intersection(*oos_periods))
    if not common:
        raise ValueError('The ranked members have no common observed OOS sessions.')
    if is_days[-1] >= common[0]:
        raise ValueError('The common OOS window must follow all common IS sessions.')
    if common != combo['oos_days'] or is_days != search['is_days']:
        raise ValueError('The verified session windows differ from the saved Optimise result.')

    windows = {'is': is_days, 'oos': common}
    targets = size['allocation']['micros']
    weights = [member['weight'] for member in members]
    ledgers = {}
    for role, sources in (('is', is_records), ('oos', oos_records)):
        books = []
        for source, expected in zip(sources, snapshots[role], strict=True):
            snapshot, book = basket.source_book(runs, analyses, source, profile, windows[role])
            keys = ('manifest_sha256', 'trades_sha256', 'excursion_input', 'native_risk')
            if any(snapshot.get(key) != expected.get(key) for key in keys):
                raise ValueError(f"Saved {role.upper()} source {source['id'][:8]} changed while preparing the assessment.")
            books.append(book)
        ledgers[role], _ = basket.admitted(books, windows[role], weights, targets, sequential=sequential)
    prefix = combo['directory']
    name = f'admitted_trades_{rank["micros"]}.csv'
    sealed_trades = _read_artifact(folder, parent, f'{prefix}/{name}')
    with TemporaryDirectory(prefix='aq-desk-oos-') as directory:
        staged = Path(directory)
        threshold = desk_overlap.threshold(parent['rules']) if sequential else None
        basket.equity(staged, rank['micros'], ledgers, targets, snapshots, overlap_threshold=threshold)
        if (staged / name).read_bytes() != sealed_trades:
            raise ValueError('The rebuilt admitted trades differ from the sealed Optimise ledger.')
    verify_sources(runs, snapshots)
    is_paths = json.loads(_read_artifact(folder, parent, f'{prefix}/paths_{rank["micros"]}.json'))
    if len(is_paths) != len(seeds):
        raise ValueError('The saved IS account paths and path seeds differ in number.')
    counts = Counter(row['role'] for row in csv.DictReader(StringIO(sealed_trades.decode('utf-8'))))
    rows = sealed_trades.splitlines(keepends=True)
    oos_csv = rows[0] + b''.join(row for row in rows[1:] if row.startswith(b'oos,'))
    terms = dict(parent_id=parent['id'], combination=combo['id'], micros=rank['micros'],
                 allocation=size['allocation'], members=members, size_rule=preset,
                 profile_id=profile.profile_id, observation_sessions=horizon)
    if sequential:
        terms['overlap_policy'] = desk_overlap.POLICY
    sources = {role: [dict(backtest_id=s['backtest']['id'], manifest_sha256=s['manifest_sha256'],
                           trades_sha256=s['trades_sha256']) for s in group]
               for role, group in snapshots.items()}
    identity = dict(version=VERSION, parent_report_sha256=parent_sha, ranking_sha256=search['ranking_sha256'],
                    configuration=terms, windows=windows, sources=sources,
                    implementation_sha256=file_digest(Path(__file__)),
                    inventory_reader_sha256=file_digest(Path(basket.__file__).parents[1] / 'research_folds.py'))
    return dict(identity=identity, configuration=terms, windows=windows, snapshots=snapshots,
                dataset=current, is_paths=is_paths, days=ledgers['oos'], trade_counts=dict(counts),
                admitted_oos=oos_csv, seeds=seeds, rules=parent['rules'], phase=phase,
                profile=profile, simulation=simulation, sampling=sampling,
                evidence=dict(evidence), key=digest(identity))


def evaluation_summary(paths, rules):
    expiry = 'provider_expired' if rules['provider_expiry_trading_sessions'] is not None else 'observation_cutoff'
    counts = dict.fromkeys(('passed', 'breached', expiry), 0)
    passing = []
    for path in paths:
        counts[path['outcome']] += 1
        if path['outcome'] == 'passed':
            passing.append(path['trading_sessions'])
    return dict(path_count=len(paths), outcome_counts=counts,
                probabilities={key: value/len(paths) for key, value in counts.items()},
                median_trading_days_to_target=median(passing) if passing else None)


def funded_summary(paths, rules, window, preset):
    projected = []
    for path in paths:
        day = path['observed_weekdays']
        outcome = path['outcome'] if day <= window else 'open'
        projected.append(dict(outcome=outcome, observed_weekdays=min(day, window),
            lifetime_censored=outcome == 'open',
            trader_payouts=[event for event in path['trader_payouts'] if event[0] <= window],
            gross_account_deductions=[event for event in path['gross_account_deductions'] if event[0] <= window]))
    scored = basket.funded_results(projected, rules)
    total = len(paths)
    open_accounts = scored['open_at_cutoff']
    return dict(path_count=total,
                any_payout_count=scored['milestones'][0]['reached'],
                breach_before_first_payout_count=round(scored['probability_breach_before_first_payout'] * total),
                open_at_window_end=open_accounts,
                open_without_payout=sum(p['lifetime_censored'] and not p['trader_payouts'] for p in projected),
                mean_trader_receipts=scored['mean_trader_receipts'],
                mean_account_deductions=scored['mean_account_deductions'],
                resolved_lifetime_mean_receipts=(scored['account_life_mean_receipts']
                                                 if preset == 'account_life' else None))


def calculate(prepared, staged):
    terms = prepared['configuration']
    horizon, preset = terms['observation_sessions'], terms['size_rule']
    targets = terms['allocation']['micros']
    owner = optimizer.evaluation if prepared['phase'] == 'evaluation' else optimizer.funded
    _, oos_paths, rules = owner(prepared['days'], targets, prepared, horizon, prepared['seeds'],
                               sequential=terms.get('overlap_policy') == desk_overlap.POLICY)
    if canonical(rules) != canonical(prepared['rules']):
        raise ValueError('The applied account rules differ from the saved Optimise rules.')
    if len(oos_paths) != len(prepared['is_paths']):
        raise ValueError('The OOS path count differs from the sealed IS comparison.')
    window = basket.FIRST_YEAR if preset == 'first_year' else horizon
    (staged / 'admitted_oos_trades.csv').write_bytes(prepared['admitted_oos'])
    (staged / 'oos_account_paths.json').write_text(canonical(oos_paths), encoding='utf-8')
    result = dict(reporting_window=window)
    for role, paths in (('is', prepared['is_paths']), ('oos', oos_paths)):
        summary = (evaluation_summary(paths, rules) if preset == 'optimal'
                   else funded_summary(paths, rules, window, preset))
        result[role] = dict(summary, sessions=len(prepared['windows'][role]),
                            admitted_trades=prepared['trade_counts'].get(role, 0))
    return result
