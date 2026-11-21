from pathlib import Path
import json
import sqlite3

import pytest

from alphaquest.compact_portfolio_reports import migrate_one, projected_report
from alphaquest.prop.portfolio_reports import seal_portfolio
from alphaquest.prop.store import seal_report, sealed_checks
from alphaquest.prop_report_storage import read_bytes


def legacy():
    detail = {'cash': {'net_cash': '5.00'}, 'counts': {'evaluation_attempts': 1},
        'accounts': [{'trace': '“, quote: \\" [ ] {}”'}], 'cash_ledger': [{'date': '2025-01-02'}],
        'sizing_decisions': [{'size': 12}]}
    return {'calculations': {'analysis_mode': 'portfolio_cashflow', 'assumptions': [],
        'abstention_alternative': detail, 'results': {'is': detail, 'combined': detail, 'oos': detail}}}


def test_projection_skips_nested_details(tmp_path):
    path = tmp_path/'report.json'
    path.write_text(json.dumps(legacy(), indent=2, ensure_ascii=False))
    result = projected_report(path)['calculations']
    expected = {'cash': {'net_cash': '5.00'}, 'counts': {'evaluation_attempts': 1}}
    assert all(result['results'][role] == expected for role in ('is','combined','oos'))
    assert result['abstention_alternative'] == expected


def test_legacy_migration_preserves_recovery_and_archived_download(tmp_path, monkeypatch):
    original = tmp_path/'id';original.mkdir()
    (original/'combined_sizing_decisions.csv').write_text('size\n12\n')
    (original/'combined_accounts.csv').write_bytes(b'x' * 4096)
    seal_report(original,legacy(),'id','now')
    old_seals = sealed_checks(original)
    with sqlite3.connect(':memory:') as db:
        db.execute('create table analysis_report_checks (id text primary key, payload text)')
        db.execute('insert into analysis_report_checks values (?,?)',('id',json.dumps(old_seals)))
        monkeypatch.setattr('alphaquest.compact_portfolio_reports.MAX_BYTES', 2048)
        result=migrate_one(db,tmp_path,'id','now',tmp_path/'recovery')
        assert result['active_bytes']<result['previous_bytes']
        assert json.loads(db.execute('select payload from analysis_report_checks').fetchone()[0])==sealed_checks(original)
    assert read_bytes(original/'combined_sizing_decisions.csv')==b'size\n12\n'
    assert not (original/'combined_accounts.csv').exists()
    from alphaquest.prop_report_storage import digest
    assert digest(tmp_path/'recovery'/'id'/'analysis.zip')==old_seals['analysis.zip']


def test_portfolio_limit_includes_archive(tmp_path,monkeypatch):
    monkeypatch.setattr('alphaquest.prop.portfolio_reports.MAX_BYTES', 16)
    with pytest.raises(ValueError,match='100 MB'):
        seal_portfolio(tmp_path,{'calculations':{}},'id','now')
