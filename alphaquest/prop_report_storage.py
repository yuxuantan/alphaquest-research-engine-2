"""Lossless ZIP-backed detail JSON, preserving original reports and seals.

The normal report and its original ZIP stay byte-identical. Large detail JSON
already in that ZIP need no second unpacked copy. No numerical inputs change.
"""
from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import tempfile
import zipfile

VERSION = 'analysis-zip-json-v1'
PACKED_JSON = frozenset({'calculations.json', 'joint_sizing.json'})
CHUNK = 1024 * 1024


def capabilities():
    return dict(version=VERSION, compressed_artifacts=sorted(PACKED_JSON),
                report_and_zip_bytes_preserved=True)


@contextmanager
def open_artifact(path):
    path = Path(path)
    if path.is_symlink():raise ValueError('Refusing a symbolic-link result artifact.')
    try:
        stream = path.open('rb')
    except FileNotFoundError:
        if path.name not in PACKED_JSON:raise
        archive = path.parent / 'analysis.zip'
        if archive.is_symlink():raise ValueError('Refusing a symbolic-link result archive.')
        try:
            with zipfile.ZipFile(archive) as zipped:
                entries = [entry for entry in zipped.infolist() if entry.filename == path.name]
                if len(entries) != 1:raise ValueError('Result archive has a missing or duplicate detail artifact.')
                entry, = entries
                if entry.is_dir() or stat.S_ISLNK(entry.external_attr >> 16) or entry.flag_bits & 1:
                    raise ValueError('Invalid result archive member.')
                with zipped.open(entry) as stream:yield stream
        except zipfile.BadZipFile as error:raise ValueError('Invalid sealed result archive.') from error
    else:
        with stream:yield stream


def stream_digest(stream):
    digest = sha256();size = 0
    while chunk := stream.read(CHUNK):digest.update(chunk);size += len(chunk)
    return digest.hexdigest(), size


def digest(path):
    with open_artifact(path) as stream:return stream_digest(stream)[0]


def read_bytes(path):
    with open_artifact(path) as stream:return stream.read()


def is_artifact(path):
    path = Path(path)
    if path.is_file() and not path.is_symlink():return True
    if path.name not in PACKED_JSON:return False
    try:
        with open_artifact(path):return True
    except (OSError, ValueError, zipfile.BadZipFile):return False


def _checked_details(directory, seals, logical_files=None):
    directory = Path(directory)
    if directory.is_symlink():raise ValueError('Refusing a symbolic-link report directory.')
    for name in ('report.json', 'analysis.zip'):
        path = directory / name
        if path.is_symlink() or digest(path) != seals[name]:raise ValueError('Sealed report or ZIP checksum changed: '+name)
    # Publishers already hold the exact manifest just sealed. Reuse that small
    # map rather than parsing another complete Monte Carlo result into memory.
    if logical_files is None:logical_files=json.loads((directory/'report.json').read_bytes()).get('files',{})
    selected = sorted(PACKED_JSON.intersection(logical_files))
    result = []
    with zipfile.ZipFile(directory / 'analysis.zip') as zipped:
        for name in selected:
            metadata = logical_files[name]
            entries = [entry for entry in zipped.infolist() if entry.filename == name]
            if len(entries) != 1:raise ValueError('Detail JSON is missing or duplicated in the original ZIP.')
            entry, = entries
            if entry.is_dir() or stat.S_ISLNK(entry.external_attr >> 16) or entry.flag_bits & 1:
                raise ValueError('Invalid archived detail JSON.')
            with zipped.open(entry) as stream:actual = stream_digest(stream)
            if actual != (metadata['sha256'], metadata['bytes']):raise ValueError('Archived detail JSON failed its original checksum.')
            path = directory / name;identity = None
            if path.is_symlink():raise ValueError('Refusing a symbolic-link detail JSON.')
            if path.exists():
                before = path.stat()
                with path.open('rb') as stream:original = stream_digest(stream)
                after = path.stat()
                identity = (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)
                if original != actual or identity != (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns):
                    raise ValueError('Unpacked detail JSON changed; original retained.')
            result.append(dict(name=name,bytes=actual[1],sha256=actual[0],identity=identity))
    return result


def compact(directory, seals, *, dry_run=False, checkpoint=lambda:None, logical_files=None):
    """Verify every candidate before unlinking any; interrupted runs are retryable."""
    directory = Path(directory);checked = _checked_details(directory, seals,logical_files)
    removed = [];size = 0
    for row in checked:
        if row['identity'] is None:continue
        checkpoint();path = directory / row['name'];current = path.stat()
        if (current.st_dev,current.st_ino,current.st_size,current.st_mtime_ns) != row['identity']:
            raise ValueError('Detail JSON changed before removal; original retained.')
        if not dry_run:path.unlink()
        removed.append(row['name']);size += row['bytes']
    return dict(version=VERSION,files=removed,unpacked_bytes=size,dry_run=dry_run)


def restore(directory, seals):
    """Restore original detail bytes atomically, without replacing newer files."""
    directory = Path(directory);checked = _checked_details(directory, seals);restored = []
    for row in checked:
        if row['identity'] is not None:continue
        fd, temporary = tempfile.mkstemp(prefix='.restore-json-',dir=directory)
        temporary = Path(temporary)
        try:
            with os.fdopen(fd,'wb') as target, open_artifact(directory/row['name']) as source:
                while chunk := source.read(CHUNK):target.write(chunk)
                target.flush();os.fsync(target.fileno())
            if digest(temporary) != row['sha256']:raise ValueError('Restored detail checksum mismatch.')
            os.link(temporary,directory/row['name']);restored.append(row['name'])
        finally:temporary.unlink(missing_ok=True)
    return dict(version=VERSION,restored=restored)


def artifact_response(path, *, filename=None, expected=None):
    """Stream original JSON bytes from a held descriptor across compaction races."""
    from fastapi import HTTPException
    from fastapi.responses import FileResponse, StreamingResponse
    from urllib.parse import quote
    path = Path(path)
    if path.name not in PACKED_JSON:return FileResponse(path,filename=filename)
    context = open_artifact(path);stream = None
    try:
        stream = context.__enter__()
        actual = stream_digest(stream)
        if expected is None or actual != (expected['sha256'],expected['bytes']):
            raise ValueError('Saved result artifact failed its original checksum.')
        stream.seek(0)
        def chunks():
            while chunk := stream.read(CHUNK):yield chunk
        class CheckedArtifactResponse(StreamingResponse):
            async def __call__(self,scope,receive,send):
                try:await super().__call__(scope,receive,send)
                finally:context.__exit__(None,None,None)
        headers={'Content-Length':str(actual[1])}
        if filename:
            encoded=quote(filename)
            headers['Content-Disposition']=(f'attachment; filename="{filename}"' if encoded==filename else "attachment; filename*=utf-8''"+encoded)
        return CheckedArtifactResponse(chunks(),media_type='application/json',headers=headers)
    except BaseException as error:
        if stream is not None:context.__exit__(None,None,None)
        if isinstance(error,(OSError,ValueError,zipfile.BadZipFile)):
            raise HTTPException(409,'Saved result artifact could not be verified against its original checksum.') from error
        raise
