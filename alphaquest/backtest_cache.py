"""Verified references to completed backtests; no duplicate result storage."""
import json
import logging
import sqlite3
from dataclasses import asdict
from .optimization_cache import digest,engine_identity,artifacts
from .prop.automatic import profile


def key(dataset,definition,parameters,config,dates,detail,compress,with_prop,research=None,market_benchmark=None):
    return digest(dict(engine=engine_identity(),dataset=dataset,strategy=definition.provenance(parameters),
                       execution=asdict(config),dates=dates,detail=detail,compress=compress,
                       prop=profile() if with_prop else None,research=research,market_benchmark=market_benchmark))


def lookup(runs,analyses,key):
    try:
        with runs.connect() as db:row=db.execute('SELECT payload FROM backtest_reuse WHERE key=?',(key,)).fetchone()
        if not row:return None
        cached=json.loads(row[0]);record=runs.get(cached['id'])
        if not record or digest(record)!=cached['record'] or artifacts(runs.root,record)!=cached['artifacts']:return None
        if cached['prop'] is not None:
            id=record['run_metadata']['automatic_prop_analysis']['id']
            if analyses.fingerprint(id)!=cached['prop']:return None
        return record
    except (OSError,ValueError,KeyError,sqlite3.Error):
        return None


def save(runs,analyses,key,record):
    try:
        prop=None
        if analyses:
            id=record['run_metadata']['automatic_prop_analysis']['id']
            if analyses.get(id)['status']=='error':return
            prop=analyses.fingerprint(id)
            if prop is None:return
        payload=dict(id=record['id'],record=digest(record),artifacts=artifacts(runs.root,record),prop=prop)
        with runs.connect() as db:db.execute('INSERT OR REPLACE INTO backtest_reuse VALUES (?,?,?)',(key,record['id'],json.dumps(payload)))
    except (OSError,ValueError,KeyError,sqlite3.Error):
        logging.getLogger(__name__).warning('Could not index optional backtest reuse',exc_info=True)
