"""Launcher-only checks: no application startup, recovery, or simulation work."""
from contextlib import contextmanager
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
from threading import Thread

import pytest


ROOT = Path(__file__).resolve().parents[1]


def library(path):
    catalogue = path/'prop_analyses/catalog.sqlite3'
    catalogue.parent.mkdir(parents=True)
    with sqlite3.connect(catalogue) as db:
        db.execute('CREATE TABLE analyses (id TEXT PRIMARY KEY, status TEXT)')
        db.execute('INSERT INTO analyses VALUES (?, ?)', ('e88d09679de04f2c824a2ac877d6d78b', 'running'))
    return catalogue


@contextmanager
def reader(catalogue):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            assert self.path == '/api/prop-analyses/defaults'
            payload = json.dumps({'report_storage': {'catalogue': str(catalogue)}}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def launch(data, port, *options):
    return subprocess.run(['sh', str(ROOT/'scripts/serve_portal.sh'), '--port', str(port), *options],
        cwd=ROOT, env={**os.environ, 'ALPHAQUEST_DATA_DIR': str(data),
                       'ALPHAQUEST_PORTAL_PYTHON': sys.executable},
        text=True, capture_output=True, timeout=10)


@pytest.mark.parametrize('options', [(), ('--recover-interrupted',)])
def test_existing_same_library_returns_address_without_recovering_live_job(tmp_path, options):
    catalogue = library(tmp_path)
    before = sha256(catalogue.read_bytes()).hexdigest()
    with reader(catalogue) as port:
        result = launch(tmp_path, port, *options)
    assert result.returncode == 0, result.stderr
    assert f'already running at http://127.0.0.1:{port}/' in result.stderr
    assert sha256(catalogue.read_bytes()).hexdigest() == before
    assert not (tmp_path/'.portal-server.lock').exists()


def test_occupied_port_for_another_library_still_rejects(tmp_path):
    catalogue = library(tmp_path)
    before = catalogue.read_bytes()
    with reader(tmp_path/'other/prop_analyses/catalog.sqlite3') as port:
        result = launch(tmp_path, port)
    assert result.returncode == 1
    assert 'Cannot own' in result.stderr
    assert 'already running' not in result.stderr
    assert catalogue.read_bytes() == before


def test_orphaned_job_explains_explicit_recovery_and_retains_original_state(tmp_path):
    catalogue = library(tmp_path)
    before = catalogue.read_bytes()
    with socket.socket() as available:
        available.bind(('127.0.0.1', 0))
        port = available.getsockname()[1]
    result = launch(tmp_path, port)
    assert result.returncode == 1
    assert 'Saved jobs are still marked queued/running: e88d09679de04f2c824a2ac877d6d78b' in result.stderr
    assert f'sh scripts/serve_portal.sh --port {port} --recover-interrupted' in result.stderr
    assert 'does not prove that their workers are still running' in result.stderr
    assert 'does not restore partial paths' in result.stderr
    assert catalogue.read_bytes() == before
