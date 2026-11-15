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

VERSION = 'entry-protection-ohlc-sensitivity-v1'
FILE = 'entry_protection_ambiguities.csv'
PREFIX = 'entry_protection_favorable_'
NOTE = ('One-minute OHLC cannot establish the post-entry sequence. Adverse-first assumes a possible '
        'post-entry stop occurs first; favorable-first takes an eligible target first or treats an uncertain '
        'stop-only touch as preceding entry. Both replay the complete strategy with actual scenario positions '
        'and costs. Open-entry and later held-bar brackets retain stop first. These are entry-bar sensitivity '
        'scenarios, not observed fills, profit bounds, historical confidence or future assurance.')


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
                       dataset, metadata, fill_assumptions, progress):
    """Fresh strategy, identical frozen bars/costs, favorable entry ambiguity only."""
    from .execution import execute
    from .reporting import generate_report
    from .strategy_features import create_strategy
    from .prepared_data import CHUNK_SIZE
    directory = Path(directory)
    saved = deepcopy(metadata)
    # Diagnostic replay must not create a second campaign acceptance decision.
    saved.pop('research', None)
    saved.pop('automatic_prop_analysis', None)
    saved['entry_protection_sensitivity'] = dict(version=VERSION, role='favorable_first_diagnostic', interpretation=NOTE)
    with replay.selected() as selected, create_strategy(definition, parameters, config, feature_paths or {},
                                                        instrument_symbol=dataset.get('symbol')) as strategy:
        strategy.entry_protection_policy = 'favorable_first'
        strategy.session_flattening['entry_protection_ambiguity_policy'] = 'favorable_first'
        strategy.session_flattening['entry_bar_path'] = 'favorable_first diagnostic; unknown OHLC sequence'
        saved['strategy']['session_flattening'] = strategy.session_flattening
        def bars():
            for bar in selected.bars:
                if bar.bar_number == 1 or bar.bar_number % CHUNK_SIZE == 0:
                    progress('entry_protection_sensitivity', bar.bar_number, selected.row_count)
                yield bar
            progress('entry_protection_sensitivity', selected.row_count, selected.row_count)
        events = execute(bars(), strategy, config, capture_risk=True, fill_assumptions=fill_assumptions,
                         capture_entry_protection=True)
        manifest = generate_report(events, directory, config, metadata=saved,
            execution_assumption=definition.execution_assumption + ':favorable_first_diagnostic', detail='compact', capture_risk=True,
            capture_entry_protection=True, expected_bar_count=selected.row_count)
    return directory, manifest


def attach_sensitivity(staging, manifest, evidence):
    """Copy bounded-memory CSV evidence into the same atomic report publication."""
    from .decimal_math import subtract
    source, favorable = evidence
    checksums = {}
    for name in ('report.json', 'trades.csv', 'equity.csv', 'intratrade_risk.csv', FILE):
        target = PREFIX + name
        shutil.copyfile(source / name, staging / target)
        with (staging / target).open('rb') as stream:
            checksums[target] = hashlib.file_digest(stream, 'sha256').hexdigest()
        kind = 'report' if name == 'report.json' else name.removesuffix('.csv')
        manifest['artifacts']['entry_protection_favorable_' + kind] = target
    comparison = dict(version=VERSION, primary_policy='adverse_first', diagnostic_policy='favorable_first',
        interpretation=NOTE, selection='Only the primary conservative result participates in campaign screening; no replacement selection.',
        primary_summary=manifest['summary'], favorable_summary=favorable['summary'],
        primary_ambiguities=manifest['entry_protection'], favorable_ambiguities=favorable['entry_protection'],
        favorable_minus_primary_net_pnl=subtract(favorable['summary']['total_net_pnl'], manifest['summary']['total_net_pnl']),
        favorable_minus_primary_trades=favorable['summary']['trades_taken'] - manifest['summary']['trades_taken'],
        source_identity=manifest['run_metadata']['dataset'], selection_window=manifest['run_metadata']['selection'],
        strategy_identity=manifest['run_metadata']['strategy'], execution_settings=manifest['execution_settings'],
        favorable_artifacts_sha256=checksums)
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
    if record.get('entry_protection_sensitivity'):
        expected = {PREFIX + name for name in ('report.json', 'trades.csv', 'equity.csv', 'intratrade_risk.csv', FILE)}
        if set(record['entry_protection_sensitivity']['favorable_artifacts_sha256']) != expected:
            raise ValueError('Unsupported entry protection sensitivity evidence.')
        names.update(expected)
        if record['artifacts'].get('entry_protection_sensitivity') != 'entry_protection_sensitivity.json':
            raise ValueError('Unsupported entry protection sensitivity artifact.')
        names.add('entry_protection_sensitivity.json')
    return names
