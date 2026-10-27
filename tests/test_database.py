import sqlite3
from pathlib import Path

import pytest

from alphaquest import database
from alphaquest.backtest_runs import RunStore
from alphaquest.datasets import DatasetStore


def cantopen():
    error = sqlite3.OperationalError("unable to open database file")
    error.sqlite_errorcode = sqlite3.SQLITE_CANTOPEN
    error.sqlite_errorname = "SQLITE_CANTOPEN"
    return error


def test_transient_open_failure_retries_before_transaction(tmp_path, monkeypatch):
    original = database.sqlite3.connect
    calls = []
    def open_once_unavailable(*args, **kwargs):
        calls.append(args[0])
        if len(calls) < 3:
            raise cantopen()
        return original(*args, **kwargs)
    monkeypatch.setattr(database.sqlite3, "connect", open_once_unavailable)
    monkeypatch.setattr(database.time, "sleep", lambda seconds: None)
    connection = database.open_database(tmp_path / "catalog.sqlite3")
    try:
        connection.execute("CREATE TABLE proof (value INTEGER)")
        connection.execute("INSERT INTO proof VALUES (1)")
        assert connection.execute("SELECT * FROM proof").fetchall() == [(1,)]
        assert len(calls) == 3
    finally:
        connection.close()


def test_persistent_open_failure_is_bounded_and_names_path(tmp_path, monkeypatch):
    calls = []
    def unavailable(*args, **kwargs):
        calls.append(args[0])
        raise cantopen()
    monkeypatch.setattr(database.sqlite3, "connect", unavailable)
    monkeypatch.setattr(database.time, "sleep", lambda seconds: None)
    path = tmp_path / "catalog.sqlite3"
    with pytest.raises(sqlite3.OperationalError, match=str(path)) as error:
        database.open_database(path)
    assert error.value.sqlite_errorcode == sqlite3.SQLITE_CANTOPEN
    assert len(calls) == 4
    assert "resume" in str(error.value)
    assert error.value.__cause__ is not None


def test_missing_directory_is_not_recreated_or_retried(tmp_path, monkeypatch):
    delays = []
    monkeypatch.setattr(database.time, "sleep", delays.append)
    path = tmp_path / "missing" / "catalog.sqlite3"
    with pytest.raises(sqlite3.OperationalError, match="parent directory is missing"):
        database.open_database(path)
    assert not path.parent.exists()
    assert not delays


def test_non_open_errors_are_not_retried(tmp_path, monkeypatch):
    def locked(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")
    delays = []
    monkeypatch.setattr(database.sqlite3, "connect", locked)
    monkeypatch.setattr(database.time, "sleep", delays.append)
    with pytest.raises(sqlite3.OperationalError, match="database is locked"):
        database.open_database(tmp_path / "catalog.sqlite3")
    assert not delays


def test_transaction_failure_rolls_back_without_replaying_sql(tmp_path):
    path = tmp_path / "catalog.sqlite3"
    with database.connection(path) as conn:
        conn.execute("CREATE TABLE proof (value INTEGER)")
    with pytest.raises(sqlite3.OperationalError, match=str(path)):
        with database.connection(path) as conn:
            conn.execute("INSERT INTO proof VALUES (1)")
            raise cantopen()
    with database.connection(path) as conn:
        assert conn.execute("SELECT * FROM proof").fetchall() == []


def test_catalogue_paths_remain_anchored_when_working_directory_changes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    source = DatasetStore(Path("library/datasets.sqlite3"))
    runs = RunStore(Path("library"))
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert source.path == tmp_path / "library/datasets.sqlite3"
    assert runs.path == tmp_path / "library/backtests.sqlite3"
    with source.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM datasets").fetchone()[0] == 0
    with runs.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
    assert not (elsewhere / "library").exists()
