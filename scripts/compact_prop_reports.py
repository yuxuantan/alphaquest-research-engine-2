#!/usr/bin/env python3
"""Compact sealed Prop Sim detail JSON using the existing checksummed ZIP.

Dry-run by default. Apply only after the running server advertises compatible
readers, or explicitly offline with no active analyses. No report or catalogue
identity is rewritten. Re-run with a new evidence directory after interruption.
"""
import argparse
from contextlib import closing
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import sqlite3
import sys
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from alphaquest.prop_report_storage import VERSION,compact,restore


def snapshot(db):
    return dict(completed_ids=[r[0] for r in db.execute("SELECT id FROM analyses WHERE status='complete' ORDER BY id")],
                seals=dict(db.execute('SELECT id,payload FROM analysis_report_checks ORDER BY id')))


def migrate(data_dir,evidence,*,apply=False,restore_unpacked=False):
    root=Path(data_dir).resolve()/'prop_analyses';evidence=Path(evidence).resolve()
    if not (root/'catalog.sqlite3').is_file():raise ValueError('No existing Prop Sim catalogue; no changes made.')
    if evidence==root or root in evidence.parents:raise ValueError('Keep maintenance evidence outside the report store.')
    evidence.mkdir(parents=True,exist_ok=True)
    if any(evidence.iterdir()):raise ValueError('Use a new empty evidence directory; earlier evidence is never overwritten.')
    with closing(sqlite3.connect(root/'catalog.sqlite3',timeout=60)) as db:
        before=snapshot(db);rows=list(db.execute("SELECT a.id,c.payload FROM analyses a JOIN analysis_report_checks c ON c.id=a.id WHERE a.status='complete' ORDER BY a.id"))
    (evidence/'before.json').write_text(json.dumps(before,indent=2)+'\n')
    totals=dict(reports_checked=0,reports_compacted=0,files_removed=0,unpacked_bytes_removed=0,restored_files=0,eligible_files=0,eligible_unpacked_bytes=0)
    results=[]
    with (evidence/'journal.jsonl').open('x') as journal:
        for id,payload in rows:
            if len(id)!=32 or any(c not in '0123456789abcdef' for c in id):raise ValueError('Invalid catalogued analysis ID.')
            with closing(sqlite3.connect(root/'catalog.sqlite3',timeout=60)) as db:
                if apply:db.execute('BEGIN IMMEDIATE')
                current=db.execute('SELECT a.status,c.payload FROM analyses a JOIN analysis_report_checks c ON c.id=a.id WHERE a.id=?',(id,)).fetchone()
                if current!=('complete',payload):
                    db.rollback();results.append(dict(id=id,status='changed_or_deleted_skipped'));continue
                seals=json.loads(payload)
                if not (root/id).is_dir():raise ValueError('Sealed analysis directory is missing: '+id)
                journal.write(json.dumps(dict(id=id,stage='verified_operation_started',apply=apply,restore=restore_unpacked))+'\n');journal.flush();os.fsync(journal.fileno())
                report=json.loads((root/id/'report.json').read_text())
                if report.get('id')!=id:raise ValueError('Report identity differs from catalogue: '+id)
                if restore_unpacked:
                    if not apply:raise ValueError('Restore requires --apply.')
                    result=restore(root/id,seals);totals['restored_files']+=len(result['restored'])
                else:
                    result=compact(root/id,seals,dry_run=not apply,logical_files=report['files'])
                    totals['eligible_files']+=len(result['files']);totals['eligible_unpacked_bytes']+=result['unpacked_bytes']
                    if apply:
                        totals['reports_compacted']+=bool(result['files']);totals['files_removed']+=len(result['files']);totals['unpacked_bytes_removed']+=result['unpacked_bytes']
                db.commit()
                value=dict(id=id,status='restored' if restore_unpacked else 'compacted' if apply else 'eligible',**result)
                results.append(value);totals['reports_checked']+=1
                journal.write(json.dumps(value)+'\n');journal.flush();os.fsync(journal.fileno())
            if totals['reports_checked']%50==0:print(json.dumps(totals),flush=True)
    with closing(sqlite3.connect(root/'catalog.sqlite3',timeout=60)) as db:
        after=snapshot(db)
        assert set(before['completed_ids'])<=set(after['completed_ids']),'Completed report records changed during maintenance.'
        assert all(after['seals'].get(id)==seal for id,seal in before['seals'].items()),'Original report seals changed.'
        integrity=[r[0] for r in db.execute('PRAGMA quick_check')];assert integrity==['ok'],integrity
    summary=dict(version=VERSION,completed_at_utc=datetime.now(timezone.utc).isoformat(),apply=apply,restore=restore_unpacked,
        **totals,original_seals_preserved=True,catalogue_quick_check=integrity,report_ids_preserved=True,results=results)
    (evidence/'result.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='results'},indent=2),flush=True)
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',type=Path,default=ROOT/'data')
    parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--restore-unpacked',action='store_true')
    parser.add_argument('--server-url',default='http://127.0.0.1:8000')
    parser.add_argument('--offline',action='store_true',help='Explicitly confirm no application reader is running; rejects active analysis records.')
    args=parser.parse_args()
    if args.restore_unpacked and not args.apply:parser.error('--restore-unpacked requires --apply')
    if args.apply and not args.restore_unpacked:
        if args.offline:
            with closing(sqlite3.connect('file:'+str(args.data_dir.resolve()/'prop_analyses/catalog.sqlite3')+'?mode=ro',uri=True)) as db:
                if db.execute("SELECT count(*) FROM analyses WHERE status IN ('queued','running')").fetchone()[0]:raise ValueError('Offline migration refuses active analyses.')
        else:
            with urlopen(args.server_url.rstrip('/')+'/api/prop-analyses/defaults',timeout=30) as response:capability=json.load(response).get('report_storage',{})
            if capability.get('version')!=VERSION:raise ValueError('The running server has not loaded compatible report readers. Keep originals until it is upgraded.')
            if capability.get('catalogue')!=str(args.data_dir.resolve()/'prop_analyses/catalog.sqlite3'):
                raise ValueError('The compatible server belongs to another data library; no files changed.')
    migrate(args.data_dir,args.evidence,apply=args.apply,restore_unpacked=args.restore_unpacked)


if __name__=='__main__':main()
