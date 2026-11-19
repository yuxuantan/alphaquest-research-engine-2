"""Original sealed bytes are the independent oracle for storage-only changes."""
from contextlib import closing
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import sqlite3
from uuid import uuid4
import zipfile

import pytest
from starlette.testclient import TestClient
from fastapi import FastAPI

from alphaquest.prop.store import seal_report,sealed_checks
from alphaquest.prop_report_storage import compact,restore,read_bytes,digest,artifact_response


def sealed(folder):
    folder.mkdir(parents=True)
    values=dict(native_profit='123.45',path_outcomes=[dict(net=i,censored=False) for i in range(500)])
    original=json.dumps(values,ensure_ascii=False,indent=2).encode()
    joint=json.dumps(dict(pairs=[{'size':3,'net':'100.00'}]),indent=4).encode()
    (folder/'calculations.json').write_bytes(original);(folder/'joint_sizing.json').write_bytes(joint)
    seal_report(folder,dict(format_version=3,source={'backtest':{'id':'a'*32}},settings={},calculations=values),folder.name,'2026-11-19T00:00:00Z')
    return original,joint,sealed_checks(folder)


def test_compact_restore_and_retry_preserve_original_bytes_and_all_seals(tmp_path):
    original,joint,seals=sealed(tmp_path/'report')
    for name,expected in [('calculations.json',original),('joint_sizing.json',joint)]:
        assert not (tmp_path/'report'/name).exists()
        assert read_bytes(tmp_path/'report'/name)==expected
        assert digest(tmp_path/'report'/name)==sha256(expected).hexdigest()
    assert compact(tmp_path/'report',seals)['files']==[]
    assert restore(tmp_path/'report',seals)['restored']==['calculations.json','joint_sizing.json']
    assert (tmp_path/'report/calculations.json').read_bytes()==original
    assert (tmp_path/'report/joint_sizing.json').read_bytes()==joint
    assert sealed_checks(tmp_path/'report')==seals
    result=compact(tmp_path/'report',seals)
    assert result['files']==['calculations.json','joint_sizing.json']
    assert result['unpacked_bytes']==len(original)+len(joint)
    assert sealed_checks(tmp_path/'report')==seals


def test_all_originals_are_verified_before_any_removal_and_bad_zip_rejects(tmp_path):
    folder=tmp_path/'report';original,joint,seals=sealed(folder);restore(folder,seals)
    (folder/'joint_sizing.json').write_bytes(b'tampered')
    with pytest.raises(ValueError,match='changed'):compact(folder,seals)
    assert (folder/'calculations.json').read_bytes()==original
    assert (folder/'joint_sizing.json').read_bytes()==b'tampered'
    (folder/'joint_sizing.json').write_bytes(joint)
    with (folder/'analysis.zip').open('ab') as f:f.write(b'changed archive')
    with pytest.raises(ValueError,match='checksum changed'):compact(folder,seals)
    assert (folder/'calculations.json').exists() and (folder/'joint_sizing.json').exists()


def test_interrupted_removal_is_readable_and_resumes_without_rewriting_report(tmp_path):
    folder=tmp_path/'report';original,joint,seals=sealed(folder);restore(folder,seals)
    count=0
    def stop():
        nonlocal count
        count+=1
        if count==2:raise RuntimeError('interruption oracle')
    with pytest.raises(RuntimeError,match='interruption oracle'):compact(folder,seals,checkpoint=stop)
    assert not (folder/'calculations.json').exists() and (folder/'joint_sizing.json').exists()
    assert read_bytes(folder/'calculations.json')==original and read_bytes(folder/'joint_sizing.json')==joint
    assert compact(folder,seals)['files']==['joint_sizing.json']
    assert sealed_checks(folder)==seals


def test_download_held_before_compaction_keeps_original_body_and_rejects_wrong_hash(tmp_path):
    folder=tmp_path/'report';original,joint,seals=sealed(folder);restore(folder,seals)
    expected=dict(bytes=len(original),sha256=sha256(original).hexdigest())
    # Hold the original file open, then remove its directory entry. The real
    # response must still finish without a FileResponse stat/open race.
    response=artifact_response(folder/'calculations.json',filename='original.json',expected=expected)
    compact(folder,seals)
    app=FastAPI()
    @app.get('/download')
    def get():return response
    with TestClient(app) as client:
        actual=client.get('/download')
        assert actual.status_code==200 and actual.content==original
        assert actual.headers['content-length']==str(len(original))
        assert actual.headers['content-disposition']=='attachment; filename="original.json"'
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:artifact_response(folder/'calculations.json',expected=dict(expected,sha256='0'*64))
    assert error.value.status_code==409 and 'checksum' in error.value.detail


def test_duplicate_zip_member_and_symlinks_are_never_packed(tmp_path):
    folder=tmp_path/'report';original,joint,seals=sealed(folder);restore(folder,seals)
    with pytest.warns(UserWarning,match='Duplicate name'):
        with zipfile.ZipFile(folder/'analysis.zip','a') as z:z.writestr('calculations.json',original)
    updated=dict(seals,**{'analysis.zip':sha256((folder/'analysis.zip').read_bytes()).hexdigest()})
    with pytest.raises(ValueError,match='duplicated'):compact(folder,updated)
    assert (folder/'calculations.json').exists()
    other=tmp_path/'other';sealed(other)
    (other/'calculations.json').symlink_to(folder/'calculations.json')
    with pytest.raises(ValueError,match='symbolic-link'):compact(other,sealed_checks(other))


def test_catalogue_migration_preserves_seals_and_restores_without_touching_active_record(tmp_path):
    script=Path('scripts/compact_prop_reports.py')
    spec=importlib.util.spec_from_file_location('migration',script);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    root=tmp_path/'data/prop_analyses';root.mkdir(parents=True);id=uuid4().hex
    original,joint,seals=sealed(root/id);restore(root/id,seals)
    with closing(sqlite3.connect(root/'catalog.sqlite3')) as db:
        db.execute('CREATE TABLE analyses (id TEXT,status TEXT)');db.execute('CREATE TABLE analysis_report_checks (id TEXT,payload TEXT)')
        db.execute('INSERT INTO analyses VALUES (?,?)',(id,'complete'));db.execute('INSERT INTO analyses VALUES (?,?)',('f'*32,'running'))
        db.execute('INSERT INTO analysis_report_checks VALUES (?,?)',(id,json.dumps(seals)));db.commit()
    dry=module.migrate(tmp_path/'data',tmp_path/'dry')
    assert dry['files_removed']==0 and dry['eligible_files']==2 and (root/id/'calculations.json').read_bytes()==original
    applied=module.migrate(tmp_path/'data',tmp_path/'applied',apply=True)
    assert applied['reports_checked']==1 and applied['files_removed']==2
    assert read_bytes(root/id/'calculations.json')==original and sealed_checks(root/id)==seals
    assert module.migrate(tmp_path/'data',tmp_path/'retry',apply=True)['files_removed']==0
    module.migrate(tmp_path/'data',tmp_path/'restore',apply=True,restore_unpacked=True)
    assert (root/id/'calculations.json').read_bytes()==original
    with closing(sqlite3.connect(root/'catalog.sqlite3')) as db:
        assert db.execute('SELECT status FROM analyses WHERE id=?',('f'*32,)).fetchone()==('running',)
        assert json.loads(db.execute('SELECT payload FROM analysis_report_checks WHERE id=?',(id,)).fetchone()[0])==seals


def test_phase_numerical_identity_does_not_depend_on_storage(tmp_path):
    from alphaquest.prop.evaluation_optimization import implementation_identity as evaluation
    from alphaquest.prop.funded_optimization import implementation_identity as funded
    before=(evaluation(),funded());folder=tmp_path/'report';_,_,seals=sealed(folder)
    restore(folder,seals);compact(folder,seals)
    assert (evaluation(),funded())==before


def test_zip_backed_calculation_cache_reuses_exact_bytes_and_rejects_corruption(tmp_path):
    from alphaquest.prop.calculation_cache import calculate,use
    from alphaquest.prop.native_analysis import MODEL_VERSION
    folder=tmp_path/'cached';folder.mkdir()
    expected=dict(cash=123,model_version=MODEL_VERSION)
    raw=json.dumps(expected).encode();(folder/'calculations.json').write_bytes(raw)
    seal_report(folder,dict(calculations=expected),folder.name,'2026-11-19T00:00:00Z')
    assert not (folder/'calculations.json').exists()
    snapshot=dict(trades_sha256='abc',excursion_input={},source_timezone='UTC',session_grid={})
    calls=[]
    def compute(rows,settings,progress):calls.append(settings);return expected
    _,_,key=calculate([],{},snapshot,lambda _:None,compute)
    with use({key:dict(id='saved',path=str(folder/'calculations.json'),sha256=sha256(raw).hexdigest())}):
        assert calculate([],{},snapshot,lambda _:None,compute)[:2]==(expected,'saved')
        assert len(calls)==1
        (folder/'analysis.zip').write_bytes(b'invalid archive')
        assert calculate([],{},snapshot,lambda _:None,compute)[1] is None
        assert len(calls)==2
