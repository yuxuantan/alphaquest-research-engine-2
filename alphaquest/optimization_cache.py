"""Conservative completed-trial identity and artifact verification."""

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
from importlib.metadata import distributions


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


def engine_identity():
    # Any production Python change invalidates reuse, including fills, metrics,
    # feature builders and dependency declarations. Legacy reports have no key.
    root = Path(__file__).parent
    files = [(str(path.relative_to(root)), hashlib.sha256(path.read_bytes()).hexdigest())
             for path in sorted(root.rglob("*.py"))]
    from .session_calendar import calendar_path
    try:
        calendar_hash = hashlib.sha256(calendar_path().read_bytes()).hexdigest()
    except OSError:
        calendar_hash = None  # Strategies that select the calendar validate it when loading.
    files.append(("calendars/cme_nq_closures.csv", calendar_hash))
    # Editable installs can appear through both cwd and site-packages. Import
    # path aliases do not change the executing package versions.
    dependencies = sorted({(item.metadata["Name"], item.version) for item in distributions()})
    from .prop.native_backend import identity
    from .prop.lucid_backend import identity as lucid_identity
    return digest([sys.version, dependencies, files, identity(),lucid_identity()])


def trial_key(job, values):
    return digest({"engine": job["engine_identity"], "dataset": job["dataset"],
                   "strategy": job["strategy"], "parameters": values,
                   "execution": job["execution_settings"],
                   "from_date": job["request"].get("from_date"), "to_date": job["request"].get("to_date"),
                   "research": job.get('research'),
                   "market_benchmark": job['request'].get('market_benchmark'),
                   "detail": job["report_detail"], "default_prop_profile": job.get("default_prop_profile")})


def artifact_paths(root, record):
    names = {"trades.csv", "equity.csv", record["artifacts"]["report"]}
    from .entry_protection import evidence_names
    names.update(evidence_names(record))
    if record.get('is_screening'):
        from .workflow_criteria import FILE
        if record['artifacts'].get('is_screening_json') != FILE:
            raise ValueError('Unsupported IS screening artifact.')
        names.add(FILE)
    if record.get('oos_screening'):
        from .oos_criteria import FILE
        if record['artifacts'].get('oos_screening_json') != FILE:
            raise ValueError('Unsupported OOS screening artifact.')
        names.add(FILE)
    if record.get("intratrade_risk"):
        names.add("intratrade_risk.csv")
    if record.get("execution_decisions"):
        from .decision_capture import SIDE_CAR
        if record.get("artifacts", {}).get("execution_decisions_jsonl") != SIDE_CAR:
            raise ValueError("Unsupported native decision artifact.")
        names.add(SIDE_CAR)
    if record.get('risk_diagnostics'):
        if record.get('artifacts',{}).get('risk_metrics_json')!='risk_metrics.json':raise ValueError('Unsupported risk diagnostic artifact.')
        names.add('risk_metrics.json')
    if record.get('native_account_control'):
        if record.get('artifacts', {}).get('native_account_control_json') != 'native_account_control.json':
            raise ValueError('Unsupported native account-control artifact.')
        names.add('native_account_control.json')
    if record.get('market_benchmark'):
        names.add('market_benchmark.json')
        if 'storage' in record['market_benchmark']:
            from .market_equity import STRATEGY_FILE, holding_path
            names.add(STRATEGY_FILE)
        else:
            names.add('market_equity.csv')
    result = {name: root / record['id'] / name for name in sorted(names)}
    if record.get('market_benchmark', {}).get('storage'):
        result['shared_holding_day'] = holding_path(root / record['id'], record['market_benchmark'])
    return result


def artifacts(root, record):
    from .artifact_reads import read_hash
    return {name: read_hash(path) for name,path in artifact_paths(root,record).items()}
