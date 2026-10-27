"""Bounded, disposable code-owned replay streams; never a source of truth.

Only verified copies enter job workspaces. Source CSV integrity is checked on
all hits before any cached pickle is decoded. Missing/corrupt entries are misses.
"""
from contextlib import contextmanager
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import sqlite3
from threading import Lock
import time
from uuid import uuid4
from .database import connection

log=logging.getLogger(__name__)


class ReplayCache:
    def __init__(self,directory,limit=None):
        self.root=Path(directory);self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.path=self.root/'index.sqlite3';self.lock=Lock()
        self.limit=int(os.environ.get('ALPHAQUEST_REPLAY_CACHE_MB','2048'))*1024**2 if limit is None else limit
        with connection(self.path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS streams (key TEXT PRIMARY KEY, name TEXT NOT NULL, sha TEXT NOT NULL, size INTEGER NOT NULL, metadata TEXT NOT NULL, used REAL NOT NULL)')

    @contextmanager
    def safe(self):
        try:yield
        except (OSError,sqlite3.Error,ValueError):log.warning('Disposable replay cache unavailable',exc_info=True)

    def restore(self,key,destination):
        destination=Path(destination)
        if destination.exists() or destination.is_symlink():raise FileExistsError(destination)
        created=False
        with self.safe(),self.lock,connection(self.path) as db:
            row=db.execute('SELECT name,sha,metadata FROM streams WHERE key=?',(key,)).fetchone()
            if row:
                name,expected,metadata=row
                if Path(name).name!=name or not name.endswith('.bin'):return None
                source=self.root/name
                if source.is_symlink():return None
                try:
                    # Hash the exact private copy that will be decoded; no reopen
                    # of mutable cache bytes after verification.
                    with source.open('rb') as incoming,destination.open('xb') as outgoing:
                        created=True
                        shutil.copyfileobj(incoming,outgoing)
                    with Path(destination).open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
                    if actual!=expected:raise ValueError('Replay cache checksum differs.')
                    db.execute('UPDATE streams SET used=? WHERE key=?',(time.time(),key))
                    return json.loads(metadata)
                except (OSError,ValueError):
                    if created:destination.unlink(missing_ok=True)
                    db.execute('DELETE FROM streams WHERE key=?',(key,))
                    source.unlink(missing_ok=True)
        if created:destination.unlink(missing_ok=True)
        return None

    def save(self,key,source,metadata):
        if self.limit<=0 or Path(source).stat().st_size>self.limit:return
        with self.safe(),self.lock,connection(self.path) as db:
            if db.execute('SELECT 1 FROM streams WHERE key=?',(key,)).fetchone():return
            name=uuid4().hex+'.bin';target=self.root/name
            try:
                with Path(source).open('rb') as incoming,target.open('xb') as outgoing:shutil.copyfileobj(incoming,outgoing)
                with target.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
                size=target.stat().st_size
                db.execute('INSERT INTO streams VALUES (?,?,?,?,?,?)',(key,name,sha,size,json.dumps(metadata),time.time()))
                total=db.execute('SELECT COALESCE(SUM(size),0) FROM streams').fetchone()[0]
                for old_key,old_name,old_size in db.execute('SELECT key,name,size FROM streams ORDER BY used').fetchall():
                    if total<=self.limit:break
                    if Path(old_name).name==old_name:(self.root/old_name).unlink(missing_ok=True)
                    db.execute('DELETE FROM streams WHERE key=?',(old_key,));total-=old_size
            except BaseException:
                target.unlink(missing_ok=True)
                raise
