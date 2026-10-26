"""The single active prop-analysis model: licensed The Bridge Funded Lab.

The former notebook numerical modules remain historical reference material only;
new portal operations do not invoke their simulator.
"""
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import platform
import shutil
import subprocess

from .adapter import digest
from .bridge_source import prepare_source, matching_exports
from .bridge_engine import engine_identity, run_bridge

MODEL_VERSION = 'thebridge-funded-lab-v1'
DEFAULTS = dict(PROP_FIRM='Apex', ACCOUNT_TYPE='Apex EOD', ACCOUNT_SIZE='50K', DAILY_LOSS_LIMIT='on',
                LUCID_EVAL_DAYS='no limit', SIZE_FOR='most net per year per slot', OUT_OF_SAMPLE_FROM='',
                NET_OPPOSITE=False, EVAL_PRICE='49', ACTIVATION_FEE='129', SLOTS='20', MAX_TOTAL_NQ='4',
                PAYOUT_REQUEST='the full payout cap each time', APPROVAL_DAY_COUNTS=True,
                SIMULATION_SIZE='standard', BLOCK_DAYS='5')


def resolved_settings(overrides):
    if not isinstance(overrides, dict) or set(overrides) - DEFAULTS.keys():
        raise ValueError('Unknown Bridge setting. Notebook overrides are retired for new analyses.')
    settings = {**DEFAULTS, **overrides}
    fixed = ('PROP_FIRM', 'ACCOUNT_TYPE', 'ACCOUNT_SIZE', 'LUCID_EVAL_DAYS', 'SIZE_FOR', 'PAYOUT_REQUEST', 'SIMULATION_SIZE')
    if any(settings[k] != DEFAULTS[k] for k in fixed):
        raise ValueError('This integration supports the matched Apex 50K EOD standard run, slot-year selection and full-cap payout policy.')
    for k in ('NET_OPPOSITE', 'APPROVAL_DAY_COUNTS'):
        if type(settings[k]) is not bool:
            raise ValueError(f'{k} must be boolean.')
    from decimal import Decimal, InvalidOperation
    for k in ('EVAL_PRICE', 'ACTIVATION_FEE', 'MAX_TOTAL_NQ', 'SLOTS'):
        if not isinstance(settings[k], str) or len(settings[k]) > 32:
            raise ValueError(f'{k} must be a numeric string, matching the Bridge form.')
        try:
            value = Decimal(settings[k])
        except InvalidOperation as exc:
            raise ValueError(f'Invalid {k}.') from exc
        if not value.is_finite() or not 0 <= value <= 100000:
            raise ValueError(f'Invalid {k}.')
        if k == 'MAX_TOTAL_NQ' and value <= 0:
            raise ValueError('MAX_TOTAL_NQ must be positive.')
        if k == 'SLOTS' and (value != int(value) or not 1 <= value <= 20):
            raise ValueError('SLOTS must be an integer from 1 to 20.')
    if settings['DAILY_LOSS_LIMIT'] not in ('on', 'off') or settings['BLOCK_DAYS'] not in ('1', '5', '10'):
        raise ValueError('Invalid Bridge DLL or bootstrap block choice.')
    if not isinstance(settings['OUT_OF_SAMPLE_FROM'], str):
        raise ValueError('OUT_OF_SAMPLE_FROM must be an ISO date or empty string.')
    if settings['OUT_OF_SAMPLE_FROM']:
        date.fromisoformat(settings['OUT_OF_SAMPLE_FROM'])
    return settings


def prepare(runs, source_id, trade_file=None, settings=None, export_timezone='America/Chicago'):
    resolved = resolved_settings(settings or {})
    if trade_file is None:
        matches = matching_exports(runs, source_id)
        if len(matches) != 1:
            raise ValueError('Select a matching trade export; automatic matching needs exactly one fully reconciled file.')
        trade_file = matches[0]['path']
    snapshot, rows = prepare_source(runs, source_id, trade_file, export_timezone)
    return snapshot, rows, resolved


def run_analysis(runs, request, staged, progress):
    snapshot, rows, settings = prepare(runs, request['source_backtest_id'], request.get('trade_file'),
                                       request.get('settings'), request['export_timezone'])
    progress('Source trade IDs, UTC times, quantities and net costs reconciled')
    inputs = staged / 'inputs'
    inputs.mkdir()
    source_file = Path(snapshot['bridge_input']['path'])
    copied = inputs / source_file.name
    shutil.copyfile(source_file, copied)
    if digest(copied) != snapshot['bridge_input']['sha256']:
        raise ValueError('Trade export changed before capture.')
    settings_file = inputs / 'settings.json'
    settings_file.write_text(json.dumps(settings, indent=2), encoding='utf-8')
    identity = engine_identity()
    output = staged / 'bridge'
    result = run_bridge(copied, settings_file, output, identity, progress)
    # The black box must actually consume the selected source and all its trades.
    if result.get('load_errors') or len(result.get('files', [])) != 1 or result['files'][0].get('trades') != len(rows):
        raise ValueError('Bridge source loading/count differs from the checked backtest.')
    if result.get('settings_form') != settings:
        raise ValueError('Bridge resolved settings differ from the submitted form.')
    if digest(source_file) != snapshot['bridge_input']['sha256'] or digest(runs.root / request['source_backtest_id'] / 'trades.csv') != snapshot['trades_sha256']:
        raise ValueError('Source changed while The Bridge was running.')
    (staged / 'trades.csv').write_text(_csv(rows), encoding='utf-8')
    try:
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=Path(__file__).resolve().parents[2], text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = 'unavailable'
    return dict(format_version=2, model_version=MODEL_VERSION, engine=identity, source=snapshot,
                settings=settings, bridge_results=result, runtime=dict(python=platform.python_version()),
                application_commit=commit, implementation_sha256={p.name:digest(p) for p in Path(__file__).parent.glob('*.py')},
                input_sha256=digest(copied), settings_sha256=digest(settings_file),
                calculation_contract='All financial calculations, random draws, size selections and charts are generated by the licensed Bridge engine. Portal checks source identity and displays saved outputs.',
                compatibility='Historical notebook reports remain immutable; new operations use The Bridge.')


def _csv(rows):
    import csv, io
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()
