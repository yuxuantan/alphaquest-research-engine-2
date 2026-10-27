"""Bounded recovery for SQLite connection-open failures, before any SQL runs."""

import logging
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import time


logger = logging.getLogger(__name__)


def access_error(path, exc):
    detail = "parent directory is missing" if not path.parent.is_dir() else (
        "database file exists" if path.exists() else "database file is missing")
    error = sqlite3.OperationalError(
        f"Cannot access database {path}: {exc} ({getattr(exc, 'sqlite_errorname', 'SQLITE_CANTOPEN')}; {detail}). "
        "Check that the data directory is available and writable, disk space, and the server's open-file limit. "
        "Saved trials remain available; resume the remaining trials after restoring database access.")
    error.sqlite_errorcode = exc.sqlite_errorcode
    error.sqlite_errorname = getattr(exc, "sqlite_errorname", "SQLITE_CANTOPEN")
    return error


def open_database(path: Path):
    # Stores anchor their paths at construction time; workers and later requests
    # must never interpret a catalogue path against a different working directory.
    for attempt, delay in enumerate((0, .1, .3, 1)):
        if delay:
            time.sleep(delay)
        try:
            return sqlite3.connect(path, timeout=30)
        except sqlite3.OperationalError as exc:
            code = getattr(exc, "sqlite_errorcode", 0)
            if code & 255 != sqlite3.SQLITE_CANTOPEN:
                raise
            if attempt < 3 and path.parent.is_dir():
                logger.warning("SQLite open failed for %s (%s); retrying before any transaction", path,
                               getattr(exc, "sqlite_errorname", code))
                continue
            # Retain SQLite's code/name for callers, and the original exception
            # as the cause. Never retry a transaction or create replacement folders.
            raise access_error(path, exc) from exc


@contextmanager
def connection(path):
    conn = open_database(path)
    try:
        with conn:
            conn.execute("PRAGMA foreign_keys = ON")
            yield conn
    except sqlite3.OperationalError as exc:
        if getattr(exc, "sqlite_errorcode", 0) & 255 == sqlite3.SQLITE_CANTOPEN:
            # Journal/temp-file failures may happen after opening. Add context
            # but do not replay any SQL or risk publishing a report twice.
            raise access_error(path, exc) from exc
        raise
    finally:
        conn.close()
