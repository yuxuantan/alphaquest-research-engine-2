"""Declared entry-bar OHLC assumptions and full-strategy sensitivity evidence.

These scenarios cannot reconstruct ticks or bound whole-strategy profitability.
The ordinary execution engine remains the sole owner of fills and cash.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from copy import deepcopy
import hashlib
import json
import shutil

LEGACY_VERSION = 'entry-protection-ohlc-sensitivity-v1'
PRIOR_VERSION = 'entry-protection-ohlc-sensitivity-v2'
VERSION = 'entry-protection-multicharts-path-sensitivity-v3'
FILE = 'entry_protection_ambiguities.csv'
OCO_FILE = 'entry_oco_ambiguities.csv'
PREFIX = 'entry_protection_favorable_'
PRIOR_SCENARIOS = {
    'favorable': ('upper_entry_first', 'favorable_first'),
    'lower_adverse': ('lower_entry_first', 'adverse_first'),
    'lower_favorable': ('lower_entry_first', 'favorable_first'),
}
SCENARIOS = {'high_first': ('multicharts', 'multicharts'), 'low_first': ('multicharts', 'multicharts')}

FILES = ('report.json', 'trades.csv', 'equity.csv', 'intratrade_risk.csv', FILE, OCO_FILE)
NOTE = ('Primary minute-bar execution follows the MultiCharts non-magnified path: '
        'Open/High/Low/Close when High is closer to Open; otherwise Open/Low/High/Close, including ties. '
        'Orders fill in path order, with SL/TP active only after entry; the sibling entry cancels. '
        'High-first and Low-first diagnostics replay the entire strategy, including later positions and costs. '
        'These are continuous modeled OHLC paths, not observed tick chronology, profit bounds or future assurance. '
        'Only the fixed primary policy screens candidates. Diagnostic failures remain inconclusive.')



@dataclass(frozen=True, slots=True)
class OCOEntryAmbiguity:
    trade_number: int
    bar_number: int
    timestamp_utc: datetime
    policy: str
    buy_stop: Decimal
    sell_stop: Decimal
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    chosen_side: str
    cancelled_side: str


@dataclass(frozen=True, slots=True)
class ProtectionAmbiguity:
    trade_number: int
    bar_number: int
    timestamp_utc: datetime
    side: str
    policy: str
    entry_reference_price: Decimal
    entry_fill_price: Decimal
    stop_price: Decimal
    target_price: Decimal | None
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    stop_required_after_entry: bool
    target_reached: bool
    assumed_outcome: str
    assumed_exit_net_pnl: Decimal | None


def sensitivity_replay(directory, definition, parameters, config, replay, feature_paths,
                       dataset, metadata, fill_assumptions, progress, *,
                       oco_policy='multicharts', protection_policy='multicharts', path_policy='multicharts'):
    """Fresh strategy on frozen bars/costs under declared entry/exit assumptions."""
    from .execution import execute, ExecutionError
    from .session_calendar import CalendarError
    from .backtest_data import DatasetReadError
    from .reporting import generate_report
    from .strategy_features import create_strategy
    from .prepared_data import CHUNK_SIZE
    directory = Path(directory)
    saved = deepcopy(metadata)
    # Diagnostic replay must not create a second campaign acceptance decision.
    saved.pop('research', None)
    saved.pop('automatic_prop_analysis', None)
    role = path_policy + '/' + oco_policy + '/' + protection_policy
    saved['entry_protection_sensitivity'] = dict(version=VERSION, role=role, interpretation=NOTE)
    last = dict(bar_number=None, timestamp_utc=None)
    with replay.selected() as selected, create_strategy(definition, parameters, config, feature_paths or {},
                                                        instrument_symbol=dataset.get('symbol')) as strategy:
        strategy.ohlc_path_policy = path_policy
        strategy.entry_protection_policy = protection_policy
        strategy.oco_entry_policy = oco_policy
        strategy.session_flattening['oco_entry_policy'] = oco_policy
        strategy.session_flattening['entry_protection_ambiguity_policy'] = protection_policy
        strategy.session_flattening['entry_bar_path'] = role + ' diagnostic modeled OHLC path'
        saved['strategy']['session_flattening'] = strategy.session_flattening
        def bars():
            for bar in selected.bars:
                last.update(bar_number=bar.bar_number, timestamp_utc=bar.timestamp_utc)
                if bar.bar_number == 1 or bar.bar_number % CHUNK_SIZE == 0:
                    progress('entry_protection_sensitivity', bar.bar_number, selected.row_count)
                yield bar
            progress('entry_protection_sensitivity', selected.row_count, selected.row_count)
        events = execute(bars(), strategy, config, capture_risk=True, fill_assumptions=fill_assumptions,
                         capture_entry_protection=True)
        try:
            manifest = generate_report(events, directory, config, metadata=saved,
                execution_assumption=definition.execution_assumption + ':' + role + '_diagnostic', detail='compact', capture_risk=True,
                capture_entry_protection=True, expected_bar_count=selected.row_count)
        except (ExecutionError, CalendarError, DatasetReadError) as exc:
            # Cancellation, I/O failures and implementation/reporting errors
            # propagate. Only declared model/data limitations are diagnostic.
            manifest = dict(status='inconclusive', reason=str(exc), error_type=type(exc).__name__,
                            failure_location=dict(last), summary=None, entry_protection=None)
    return directory, manifest


def sensitivity_replays(directory, *args):
    return {key: sensitivity_replay(Path(directory) / key, *args,
                                   oco_policy=oco, protection_policy=protection, path_policy=key)
            for key, (oco, protection) in SCENARIOS.items()}


def scenario_artifacts(key, *, legacy=False):
    prefix = 'entry_protection_' + key + '_'
    return {prefix + ('report' if name == 'report.json' else name.removesuffix('.csv')): prefix + name
            for name in (FILES[:-1] if legacy else FILES)}


def export_kinds():
    return {'entry_protection_ambiguities', 'entry_oco_ambiguities', 'entry_protection_sensitivity',
            *(kind for key in (*SCENARIOS, *PRIOR_SCENARIOS) for kind in scenario_artifacts(key))}


def attach_sensitivity(staging, manifest, evidence):
    """Copy bounded-memory CSV evidence into the same atomic report publication."""
    from .decimal_math import subtract
    scenarios = {}
    for key, (oco, protection) in SCENARIOS.items():
        source, result = evidence[key]
        complete = result['status'] == 'complete'
        checksums, kinds = {}, {}
        if complete:
            for (kind, target), name in zip(scenario_artifacts(key).items(), FILES, strict=True):
                shutil.copyfile(source / name, staging / target)
                with (staging / target).open('rb') as stream:
                    checksums[target] = hashlib.file_digest(stream, 'sha256').hexdigest()
                manifest['artifacts'][kind] = target
                kinds[kind] = target
        scenarios[key] = dict(status=result['status'], oco_entry_policy=oco, protection_policy=protection, ohlc_path_policy=key,
            summary=result['summary'], ambiguities=result['entry_protection'], artifacts_sha256=checksums,
            artifact_kinds=kinds, reason=result.get('reason'), failure_location=result.get('failure_location'),
            error_type=result.get('error_type'),
            minus_primary_net_pnl=subtract(result['summary']['total_net_pnl'], manifest['summary']['total_net_pnl']) if complete else None)
    comparison = dict(version=VERSION, primary_policy='multicharts', diagnostic_policy='continuous_path_alternatives',
        primary_oco_entry_policy='multicharts', scenarios=scenarios,
        status='complete' if all(s['status'] == 'complete' for s in scenarios.values()) else 'inconclusive',
        interpretation=NOTE, selection='Only the primary MultiCharts-modeled result participates in campaign screening; no replacement selection.',
        primary_summary=manifest['summary'], primary_ambiguities=manifest['entry_protection'],
        source_identity=manifest['run_metadata']['dataset'], selection_window=manifest['run_metadata']['selection'],
        strategy_identity=manifest['run_metadata']['strategy'], execution_settings=manifest['execution_settings'])
    path = staging / 'entry_protection_sensitivity.json'
    from .reporting import json_value
    path.write_text(json.dumps(comparison, default=json_value, allow_nan=False, indent=2) + '\n', encoding='utf-8')
    manifest['artifacts']['entry_protection_sensitivity'] = path.name
    manifest['entry_protection_sensitivity'] = dict(comparison, sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def evidence_names(record):
    names = set()
    if record.get('entry_protection'):
        if record.get('artifacts', {}).get('entry_protection_ambiguities') != FILE:
            raise ValueError('Unsupported entry protection evidence.')
        names.add(FILE)
        if record['entry_protection']['version'] in (PRIOR_VERSION, VERSION):
            if record['artifacts'].get('entry_oco_ambiguities') != OCO_FILE:
                raise ValueError('Unsupported OCO entry evidence.')
            names.add(OCO_FILE)
    if record.get('entry_protection_sensitivity'):
        saved = record['entry_protection_sensitivity']
        if saved['version'] == LEGACY_VERSION:
            expected = set(scenario_artifacts('favorable', legacy=True).values())
            if set(saved['favorable_artifacts_sha256']) != expected:
                raise ValueError('Unsupported entry protection sensitivity evidence.')
            names.update(expected)
        elif saved['version'] in (PRIOR_VERSION, VERSION):
            expected_scenarios = SCENARIOS if saved['version'] == VERSION else PRIOR_SCENARIOS
            if set(saved['scenarios']) != set(expected_scenarios):
                raise ValueError('Unsupported entry sensitivity scenarios.')
            for key, scenario in saved['scenarios'].items():
                expected = scenario_artifacts(key) if scenario['status'] == 'complete' else {}
                if scenario['status'] not in ('complete', 'inconclusive') or scenario['artifact_kinds'] != expected:
                    raise ValueError('Unsupported entry scenario status or artifacts.')
                if set(scenario['artifacts_sha256']) != set(expected.values()):
                    raise ValueError('Unsupported entry scenario evidence.')
                if any(record['artifacts'].get(kind) != name for kind, name in expected.items()):
                    raise ValueError('Entry scenario artifacts differ from the report.')
                names.update(expected.values())
        else:
            raise ValueError('Unsupported entry protection sensitivity version.')
        if record['artifacts'].get('entry_protection_sensitivity') != 'entry_protection_sensitivity.json':
            raise ValueError('Unsupported entry protection sensitivity artifact.')
        names.add('entry_protection_sensitivity.json')
    return names


def evidence_hash(record, name):
    if name == FILE:
        return record['entry_protection']['sha256']
    if name == OCO_FILE:
        return record['entry_protection']['oco_sha256']
    saved = record['entry_protection_sensitivity']
    if name == 'entry_protection_sensitivity.json':
        return saved['sha256']
    if saved['version'] == LEGACY_VERSION:
        return saved['favorable_artifacts_sha256'][name]
    for scenario in saved['scenarios'].values():
        if name in scenario['artifacts_sha256']:
            return scenario['artifacts_sha256'][name]
    raise ValueError('Unknown entry sensitivity artifact.')
