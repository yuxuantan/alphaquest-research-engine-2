#!/bin/sh
# Stable local serving: no reload, no per-request terminal output, one owner.
set -eu
PORTAL_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$PORTAL_ROOT"
exec "${ALPHAQUEST_PORTAL_PYTHON:-$PORTAL_ROOT/.venv/bin/python}" - "$@" <<'PY'
import argparse
import errno
import fcntl
import json
import os
from pathlib import Path
import socket
import sqlite3
import sys
from urllib.request import urlopen

parser = argparse.ArgumentParser(description='Serve the local portal without terminal access logs or development reload.')
parser.add_argument('--port', type=int, default=8000)
parser.add_argument('--recover-interrupted', action='store_true', help='Explicitly allow startup recovery of queued/running jobs after their previous server has stopped.')
args = parser.parse_args()
if not 1 <= args.port <= 65535:
    parser.error('--port must be between 1 and 65535')

data = Path(os.environ.get('ALPHAQUEST_DATA_DIR', 'data')).expanduser().resolve()

def existing_portal(port):
    """Identify a healthy reader for this exact library; never start recovery."""
    try:
        with urlopen(f'http://127.0.0.1:{port}/api/prop-analyses/defaults', timeout=3) as response:
            value = json.load(response)
        return value.get('report_storage', {}).get('catalogue') == str(data/'prop_analyses/catalog.sqlite3')
    except (OSError, ValueError, AttributeError):
        return False

# Bind before application startup: duplicate launches must not run recovery.
listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    listener.bind(('127.0.0.1', args.port))
except OSError as exc:
    if exc.errno == errno.EADDRINUSE and existing_portal(args.port):
        parser.exit(0, f'AlphaQuest is already running at http://127.0.0.1:{args.port}/. Existing jobs were not changed.\n')
    parser.exit(1, f'Cannot own 127.0.0.1:{args.port}: {exc}. Existing servers and jobs were not changed.\n')
listener.listen(2048)
listener.set_inheritable(True)

data.mkdir(parents=True, exist_ok=True)
owner = (data/'.portal-server.lock').open('a+')
try:
    fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    parser.exit(1, 'Another stable portal owns this data directory. Use its existing address.\n')
os.set_inheritable(owner.fileno(), True)

active = []
for path, table, query in (
    (data/'prop_analyses/catalog.sqlite3', 'analyses', "SELECT id FROM analyses WHERE status IN ('queued','running')"),
    (data/'backtests.sqlite3', 'optimizations', "SELECT id FROM optimizations WHERE json_extract(payload,'$.status') IN ('queued','running')"),
    (data/'backtests.sqlite3', 'mechanic_job_attempts', "SELECT id FROM mechanic_job_attempts WHERE status IN ('queued','running')"),
):
    if not path.exists():
        continue
    with sqlite3.connect(path.as_uri()+'?mode=ro', uri=True) as db:
        if db.execute('SELECT 1 FROM sqlite_master WHERE type=? AND name=?', ('table',table)).fetchone():
            active.extend(r[0] for r in db.execute(query))
if active and not args.recover_interrupted:
    parser.exit(1, 'Saved jobs are still marked queued/running: '+', '.join(active)+'. '
        'No portal owns this requested port or stable server lock. These may be interrupted records; '
        'this check does not prove that their workers are still running. '
        'After confirming the previous server and workers have stopped, run '
        f'"sh scripts/serve_portal.sh --port {args.port} --recover-interrupted". '
        'Recovery records unfinished jobs as interrupted; it does not restore partial paths. '
        'No jobs were changed by this launch.\n')

logs = data/'portal_logs'
logs.mkdir(exist_ok=True)
config = dict(version=1, disable_existing_loggers=False,
    formatters=dict(plain=dict(format='%(asctime)s %(levelname)s %(name)s %(message)s')),
    handlers=dict(file=dict(**{'class':'logging.handlers.RotatingFileHandler'},
        filename=str(logs/'server.log'), maxBytes=5*1024*1024, backupCount=3,
        encoding='utf-8', formatter='plain')),
    root=dict(level='INFO', handlers=['file']),
    loggers={'uvicorn':dict(level='INFO', handlers=['file'], propagate=False),
             'uvicorn.error':dict(level='INFO', handlers=[], propagate=True),
             'uvicorn.access':dict(level='WARNING', handlers=[], propagate=False)})
config_path = logs/'logging.json'
config_path.write_text(json.dumps(config, indent=2)+'\n')
owner.seek(0); owner.truncate(); owner.write(json.dumps(dict(pid=os.getpid(), port=args.port))+'\n'); owner.flush()

# Redirect even interpreter errors and prints away from the launching terminal.
# Structured logs rotate; process-output.log is a separate append-only fallback.
with (logs/'process-output.log').open('ab', buffering=0) as stream:
    os.dup2(stream.fileno(), 1)
    os.dup2(stream.fileno(), 2)
os.environ['ALPHAQUEST_DATA_DIR'] = str(data)
os.environ['PYTHONUNBUFFERED'] = '1'
os.environ.pop('UVICORN_RELOAD', None)
os.execv(sys.executable, [sys.executable, '-m', 'uvicorn', 'alphaquest.app:app',
    '--fd', str(listener.fileno()), '--workers', '1', '--no-access-log',
    '--log-config', str(config_path)])
PY
