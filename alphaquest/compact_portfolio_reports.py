"""Loss-preserving, offline migration of oversized legacy Portfolio reports."""
import argparse
from contextlib import closing
import json
import mmap
import os
from pathlib import Path
import re
import shutil
import sqlite3
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from .prop.adapter import canonical
from .prop.portfolio_reports import DETAILS, MAX_BYTES, seal_portfolio
from .prop.store import sealed_checks
from .prop_report_storage import PORTFOLIO_PACKED, digest, open_artifact

TOKEN = re.compile(rb'"[^"\\]*(?:\\.[^"\\]*)*"|[\[\]{}]', re.DOTALL)
SPACE = re.compile(rb'\s*')
SCALAR_END = re.compile(rb'[,\]}\s]')


def projected_report(path):
    """Read the summary without materializing embedded multi-gigabyte arrays."""
    with path.open('rb') as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
        def value_end(start):
            first = data[start]
            if first == ord('"'):
                token = TOKEN.match(data, start)
                if token is None:raise ValueError('Unterminated report string.')
                return token.end()
            if first not in b'[{':
                marker = SCALAR_END.search(data, start)
                return marker.start() if marker else len(data)
            depth = 0
            for token in TOKEN.finditer(data, start):
                part = token[0]
                if part in (b'[', b'{'):depth += 1
                elif part in (b']', b'}'):
                    depth -= 1
                    if not depth:return token.end()
            raise ValueError('Unterminated report container.')

        def small(start, end):
            if end-start>MAX_BYTES:raise ValueError('Unexpectedly large Portfolio summary value.')
            return json.loads(data[start:end])

        def project(start, path=()):
            current = SPACE.match(data, start).end()
            omit = (path[:2] == ('calculations','results') and len(path)==3
                    or path == ('calculations','abstention_alternative'))
            if data[current] != ord('{'):
                end=value_end(current)
                return small(current,end),end
            result={}
            current=SPACE.match(data,current+1).end()
            while data[current]!=ord('}'):
                end=value_end(current)
                key=small(current,end)
                colon=SPACE.match(data,end).end()
                if data[colon]!=ord(':'):raise ValueError('Invalid Portfolio report key.')
                start=SPACE.match(data,colon+1).end()
                nested=(*path,key)
                if nested in (('calculations',),('calculations','results'),('calculations','abstention_alternative')) or (
                    nested[:2]==('calculations','results') and len(nested)==3):
                    value,end=project(start,nested)
                    result[key]=value
                else:
                    end=value_end(start)
                    if not (omit and key in DETAILS):result[key]=small(start,end)
                current=SPACE.match(data,end).end()
                if data[current]==ord('}'):break
                if data[current]!=ord(','):raise ValueError('Invalid Portfolio report separator.')
                current=SPACE.match(data,current+1).end()
            return result,current+1

        report,end=project(0)
        if SPACE.match(data,end).end()!=len(data):raise ValueError('Unexpected trailing report data.')
        return report


def keep_original(directory, backup, seals, files):
    backup.mkdir(parents=True, exist_ok=True)
    archive=backup/'analysis.zip'
    if not archive.exists():
        os.link(directory/'analysis.zip', archive)
    if archive.is_symlink() or digest(archive)!=seals['analysis.zip']:
        raise ValueError('Legacy archive checksum mismatch. Original report retained.')
    with ZipFile(archive) as zipped:
        entries=zipped.infolist()
        if (len(entries)!=len(files)+1 or set(zipped.namelist())!=set(files)|{'report.json'}
                or any(zipped.getinfo(name).file_size!=entry['bytes'] for name,entry in files.items())):
            raise ValueError('Legacy archive does not cover the complete original report.')
    (backup/'original-seals.json').write_text(canonical(seals))


def migrate_one(db, root, id, created, recovery):
    directory=root/id
    seals=json.loads(db.execute('SELECT payload FROM analysis_report_checks WHERE id=?',(id,)).fetchone()[0])
    retired=root/f'.portfolio-retired-{id}'
    backup=recovery/id
    if retired.exists():
        if directory.exists() and sealed_checks(directory)==seals:
            if (backup/'original-seals.json').is_file() and digest(backup/'analysis.zip')==json.loads(
                    (backup/'original-seals.json').read_text())['analysis.zip']:
                shutil.rmtree(retired)
            else:raise ValueError('Retired report needs its verified recovery archive.')
        elif sealed_checks(retired)==seals:
            if directory.exists():shutil.rmtree(directory)
            retired.rename(directory)
        else:raise ValueError('Unrecognized interrupted Portfolio migration.')
    before=sum(file.stat().st_size for file in directory.rglob('*') if file.is_file())
    if before<=MAX_BYTES:return None
    if sealed_checks(directory)!=seals:raise ValueError('Portfolio report seal changed.')
    report=projected_report(directory/'report.json')
    if report['calculations']['analysis_mode']!='portfolio_cashflow':raise ValueError('Expected a Portfolio report.')
    old_files=report.pop('files')
    keep_original(directory,backup,seals,old_files)
    selected=(PORTFOLIO_PACKED- {name for name in PORTFOLIO_PACKED if name.endswith('_accounts.json')}) | {
        'allocation_results.json','portfolio_frozen.json','source_checks.json'}
    with TemporaryDirectory(prefix='.portfolio-compact-',dir=root) as temporary:
        staged=Path(temporary)/'report';staged.mkdir()
        for name in sorted(selected.intersection(old_files)):
            source,dest=directory/name,staged/name
            if source.is_symlink() or digest(source)!=old_files[name]['sha256']:
                raise ValueError(f'Saved artifact changed: {name}.')
            with open_artifact(source) as stream, dest.open('wb') as target:
                shutil.copyfileobj(stream,target,1024*1024)
        report['calculations']['assumptions'].append(
            'Original detailed account traces are preserved in the verified legacy recovery archive.')
        size=seal_portfolio(staged,report,id,created)
        updated=sealed_checks(staged)
        directory.rename(retired)
        try:
            staged.rename(directory)
            with db:
                db.execute('UPDATE analysis_report_checks SET payload=? WHERE id=?',(canonical(updated),id))
        except BaseException:
            if directory.exists():directory.rename(staged)
            retired.rename(directory)
            raise
    shutil.rmtree(retired)
    return dict(id=id, previous_bytes=before, active_bytes=size,
        recovery_zip_bytes=(backup/'analysis.zip').stat().st_size, recovery=str(backup))


def main():
    import fcntl
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',type=Path,default=Path('data'))
    parser.add_argument('--recovery-dir',type=Path,required=True)
    args=parser.parse_args()
    root=args.data_dir/'prop_analyses'
    if not (root/'catalog.sqlite3').is_file():raise SystemExit('Portfolio catalogue not found.')
    with (args.data_dir/'.portal-server.lock').open('a+') as lock, closing(sqlite3.connect(root/'catalog.sqlite3')) as db:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise SystemExit('Stop the idle portal before compacting saved Portfolio reports.') from None
        if db.execute("SELECT 1 FROM analyses WHERE status IN ('queued','running')").fetchone():
            raise SystemExit('Queued or running analysis exists. Saved reports were kept.')
        rows=db.execute("""
            SELECT DISTINCT a.id,a.created FROM workflow_prop_simulations p
            JOIN json_each(p.payload,'$.portfolio.attempts') j
            JOIN analyses a ON a.id=j.value WHERE a.status='complete'
        """).fetchall()
        for id,created in rows:
            print(f'Checking Portfolio {id}',flush=True)
            result=migrate_one(db,root,id,created,args.recovery_dir)
            if result:print(json.dumps(result),flush=True)


if __name__=='__main__':
    main()
