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
    # Editable installs can appear through both cwd and site-packages. Import
    # path aliases do not change the executing package versions.
    dependencies = sorted({(item.metadata["Name"], item.version) for item in distributions()})
    from .prop.native_backend import identity
    return digest([sys.version, dependencies, files, identity()])


def trial_key(job, values):
    return digest({"engine": job["engine_identity"], "dataset": job["dataset"],
                   "strategy": job["strategy"], "parameters": values,
                   "execution": job["execution_settings"],
                   "from_date": job["request"].get("from_date"), "to_date": job["request"].get("to_date"),
                   "research": job.get('research'),
                   "market_benchmark": job['request'].get('market_benchmark'),
                   "detail": job["report_detail"], "default_prop_profile": job.get("default_prop_profile")})


def artifacts(root, record):
    names = {"trades.csv", "equity.csv", record["artifacts"]["report"]}
    if record.get("intratrade_risk"):
        names.add("intratrade_risk.csv")
    if record.get('market_benchmark'):
        names.update(('market_benchmark.json', 'market_equity.csv'))
    result = {}
    for name in sorted(names):
        with (root / record["id"] / name).open("rb") as stream:
            result[name] = hashlib.file_digest(stream, "sha256").hexdigest()
    return result
