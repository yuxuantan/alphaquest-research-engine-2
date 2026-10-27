"""Losslessly archive existing optimization JSON reports without replaying trades.

Run with --data-dir and a NEW --evidence directory. Only catalogued optimization
trials are eligible. Archives are verified before catalogue publication and the
original is removed only after publication. Repeating the command safely finishes
an interrupted publication/cleanup; existing archives are never overwritten.
"""

import argparse
from contextlib import contextmanager, closing
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from uuid import uuid4

from .database import connection


CHUNK = 1024 * 1024


def report_progress(message):
    print(message, flush=True)


def digest(path, *, compressed=False):
    result = hashlib.sha256()
    size = 0
    opener = gzip.open if compressed else Path.open
    with opener(path, "rb") as stream:
        while chunk := stream.read(CHUNK):
            result.update(chunk)
            size += len(chunk)
    return result.hexdigest(), size


def identity(path):
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns


def archive_report(folder, record):
    """Prepare/reuse a verified archive. The original and catalogue stay intact."""
    source, target = folder / "report.json", folder / "report.json.gz"
    before = identity(source)
    temporary = folder / f".report-{uuid4().hex}.gz.tmp"
    if not target.exists():
        try:
            with source.open("rb") as original, temporary.open("xb") as output:
                with gzip.GzipFile(filename="", fileobj=output, mode="wb", compresslevel=6, mtime=0) as zipped:
                    while chunk := original.read(CHUNK):
                        zipped.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            # Publishing a verified file must never replace a pre-existing one.
            original_hash, original_size = digest(source)
            if digest(temporary, compressed=True) != (original_hash, original_size):
                raise ValueError(f"Archive verification failed: {source}")
            if identity(source) != before:
                raise ValueError(f"Source changed during compression: {source}")
            os.link(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    else:
        original_hash, original_size = digest(source)
        if digest(target, compressed=True) != (original_hash, original_size):
            raise ValueError(f"Existing archive does not match its original: {target}")
    if identity(source) != before:
        raise ValueError(f"Source changed during verification: {source}")
    compressed_hash, compressed_size = digest(target)
    archive = dict(original_name="report.json", uncompressed_sha256=original_hash,
                   uncompressed_bytes=original_size, compressed_sha256=compressed_hash,
                   compressed_bytes=compressed_size)
    previous = record.get("report_archive")
    if previous and previous != archive:
        raise ValueError(f"Archive differs from its saved verification: {target}")
    return archive, before


@contextmanager
def maintenance_lock(root):
    # OS locks release on process exit, including a crash. Never hold a SQLite
    # write transaction while compressing hundreds of megabytes.
    import fcntl
    with (root / ".optimization-compression.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Another optimization compression is already running.") from None
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def compress_existing(directory, evidence, progress=report_progress):
    root, evidence = Path(directory).expanduser().resolve(), Path(evidence).expanduser().resolve()
    database = root / "backtests.sqlite3"
    if not database.is_file():
        raise ValueError(f"Backtest catalogue not found: {database}")
    with maintenance_lock(root):
        with connection(database) as conn:
            jobs = [json.loads(row[0]) for row in conn.execute("SELECT payload FROM optimizations")]
            if any(job["status"] in ("queued", "running") for job in jobs):
                raise ValueError("Wait for queued/running optimizations to finish before compressing saved reports.")
            rows = conn.execute("""SELECT DISTINCT r.id, r.manifest FROM runs r
                JOIN optimization_trials t ON json_extract(t.payload, '$.run_id') = r.id ORDER BY r.id""").fetchall()
            evidence.mkdir(parents=True, exist_ok=False)
            with closing(sqlite3.connect(evidence / "backtests-before.sqlite3")) as backup:
                conn.backup(backup)
        before = dict(created_at_utc=datetime.now(timezone.utc).isoformat(), data_directory=str(root),
                      jobs=jobs, reports=[json.loads(payload) for _, payload in rows])
        (evidence / "before.json").write_text(json.dumps(before, indent=2) + "\n")
        outcomes = []
        with (evidence / "journal.jsonl").open("x") as journal:
            for number, (run_id, payload) in enumerate(rows, 1):
                if len(run_id) != 32 or any(c not in "0123456789abcdef" for c in run_id):
                    raise ValueError("Invalid saved run ID.")
                record = json.loads(payload)
                folder = root / "backtest_runs" / run_id
                source = folder / "report.json"
                name = record["artifacts"]["report"]
                if name == "report.json.gz" and not source.exists():
                    target = folder / name
                    expanded = digest(target, compressed=True)
                    previous = record.get("report_archive")
                    if previous and (expanded != (previous["uncompressed_sha256"], previous["uncompressed_bytes"])
                                     or digest(target) != (previous["compressed_sha256"], previous["compressed_bytes"])):
                        raise ValueError(f"Saved compressed report failed verification: {target}")
                    outcomes.append(dict(run_id=run_id, status="already_compressed", verified=True))
                    continue
                if name not in ("report.json", "report.json.gz"):
                    raise ValueError(f"Unknown report artifact for {run_id}: {name}")
                csv_before = {name: digest(folder / name)[0] for name in ("trades.csv", "equity.csv")}
                archive, original_identity = archive_report(folder, record)
                converted = {**record, "artifacts": {**record["artifacts"], "report": "report.json.gz"},
                             "report_archive": archive,
                             "report_storage": {**record.get("report_storage", {}),
                                                "detail": record.get("report_storage", {}).get("detail", "full"),
                                                "compression": "gzip",
                                                "per_bar_equity_retained": record.get("report_storage", {}).get("per_bar_equity_retained", True),
                                                "trades": "all", "equity_csv": "initial_and_trade_close"}}
                with connection(database) as conn:
                    conn.execute("BEGIN IMMEDIATE")
                    changed = conn.execute("UPDATE runs SET manifest=? WHERE id=? AND manifest=?",
                                           (json.dumps(converted), run_id, payload)).rowcount
                    if changed != 1:
                        raise ValueError(f"Catalogue changed during compression: {run_id}; original preserved.")
                # Persist the verified/archive-published state before reclaiming
                # space. A crash here leaves two good copies; rerun finishes it.
                entry = dict(run_id=run_id, status="archive_published", **archive, csv_sha256=csv_before)
                journal.write(json.dumps(entry) + "\n"); journal.flush(); os.fsync(journal.fileno())
                if identity(source) != original_identity:
                    raise ValueError(f"Original changed before cleanup: {source}; both files preserved.")
                if any(digest(folder / name)[0] != expected for name, expected in csv_before.items()):
                    raise ValueError(f"Trade/equity CSV changed during compression: {run_id}; original preserved.")
                source.unlink()
                entry = {**entry, "status": "compressed"}
                journal.write(json.dumps(entry) + "\n"); journal.flush(); os.fsync(journal.fileno())
                outcomes.append(entry)
                progress(f"[{number}/{len(rows)}] {run_id}: {archive['uncompressed_bytes']:,} → {archive['compressed_bytes']:,} bytes; SHA-256 verified")
        changed = [item for item in outcomes if item["status"] == "compressed"]
        result = dict(reports=outcomes, compressed_reports=len(changed),
                      before_bytes=sum(item["uncompressed_bytes"] for item in changed),
                      after_bytes=sum(item["compressed_bytes"] for item in changed))
        result["saved_bytes"] = result["before_bytes"] - result["after_bytes"]
        (evidence / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True, help="New directory for catalogue backup, original manifests and verification")
    args = parser.parse_args()
    result = compress_existing(args.data_dir, args.evidence)
    print(f"Compressed {result['compressed_reports']} reports; saved {result['saved_bytes']:,} bytes.")


if __name__ == "__main__":
    main()
