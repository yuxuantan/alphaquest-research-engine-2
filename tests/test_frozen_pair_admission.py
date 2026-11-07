"""Adversarial frozen-parent checks without large temporary source libraries."""
from copy import deepcopy
from contextlib import contextmanager
import sqlite3
from types import SimpleNamespace

import pytest

import alphaquest.prop.frozen_pairs as pair
from alphaquest.research_access import final_authorization,metadata_only


def authority(tmp_path,monkeypatch):
    parent_id,source_id,campaign_id='a'*32,'b'*32,'c'*32
    plan=dict(is_start='2026-01-04',is_end='2026-01-09',oos_start='2026-01-25',oos_end='2026-02-06',source_timezone='UTC')
    metadata=dict(dataset=dict(id='d'*32,sha256='e'*64,source_timezone='UTC'),instrument=dict(symbol='MNQ'),
        strategy=dict(id='vwap_pullback_risk_sizing',parameters=dict(position_size=1)),research=dict(phase='is',plan=plan))
    parent=dict(id=parent_id,status='complete',run_metadata=metadata,execution_settings=dict(commission_per_contract_per_side='0'),
        period_start_utc='2026-01-04T23:01:00Z',period_end_utc='2026-01-09T22:00:00Z')
    source=deepcopy(parent);source.update(id=source_id,period_start_utc='2026-01-25T23:01:00Z',period_end_utc='2026-02-06T22:00:00Z')
    source['run_metadata']['research'].update(phase='oos',parent_run_id=parent_id,attempt_id='f'*32)
    artifacts=dict(trades='bytes')
    config=dict(source=dict(source_backtest_id=parent_id),profile=dict(profile_id='apex-50k-eod',rule_version='frozen'),micros=3)
    manifest=dict(configuration=config,source=dict(backtest=deepcopy(parent)),native_source_check=dict(source_artifacts=artifacts))
    implementation=dict(exact='owner-identity')
    report=dict(implementation=implementation,request=dict(native_execution=dict(horizon_calendar_days=14),candidates=[config]),
        calculations=dict(candidates=[dict(candidate_id='1'*64,manifest=manifest)]))
    campaign_manifest=dict(phase='evaluation')
    package=dict(schema_version='phase-freeze-v1',phase='evaluation',campaign_id=campaign_id,analysis_id='2'*32,
        report_sha256='3'*64,campaign_manifest_sha256=pair.fingerprint(campaign_manifest),candidate_ids=['1'*64],
        search_settings=dict(native_execution=dict(horizon_calendar_days=14)),implementation=implementation,
        candidate_definitions=[dict(candidate_id='1'*64,manifest=manifest)])
    package=pair.seal(package,'package_sha256')
    campaign=dict(frozen=package,manifest=campaign_manifest)
    records={parent_id:parent,source_id:source}
    path=tmp_path/'manual.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE oos_attempts(id,status,parent_run_id,run_id)')
        db.execute('INSERT INTO oos_attempts VALUES (?,?,?,?)',('f'*32,'complete',parent_id,source_id))
    @contextmanager
    def connect():
        with sqlite3.connect(path) as db:yield db
    runs=SimpleNamespace(root=tmp_path,get=records.get,read_source_record=records.get,connect=connect)
    campaigns=SimpleNamespace(get=lambda id:deepcopy(campaign),report=lambda id:deepcopy(report),
        analyses=SimpleNamespace(fingerprint=lambda id:dict(files={'report.json':'3'*64})))
    monkeypatch.setattr(pair,'artifacts',lambda *args:artifacts)
    monkeypatch.setattr(pair,'module_for',lambda phase:SimpleNamespace(implementation_identity=lambda:implementation))
    reference=pair.FrozenPhaseReference(campaign_id=campaign_id,package_sha256=package['package_sha256'],
        candidate_id='1'*64,source_backtest_id=source_id)
    return campaigns,runs,reference,campaign,records


def test_existing_manual_oos_exact_mapping_is_admitted_and_runtime_calendar_evidence_can_differ(tmp_path,monkeypatch):
    campaigns,runs,ref,campaign,records=authority(tmp_path,monkeypatch)
    records[ref.source_backtest_id]['run_metadata']['strategy']['session_flattening']={'observed_window':'different OOS closes'}
    result=pair._resolve_policy(campaigns,runs,ref,'evaluation')
    assert result['source']['id']==ref.source_backtest_id
    assert result['training_last_session']=='2026-01-09'


@pytest.mark.parametrize('field,value',[
    ('phase','outer'),('parent_run_id','9'*32),('attempt_id','8'*32)])
def test_no_final_outer_or_fabricated_parent_attempt_admission(tmp_path,monkeypatch,field,value):
    campaigns,runs,ref,campaign,records=authority(tmp_path,monkeypatch)
    records[ref.source_backtest_id]['run_metadata']['research'][field]=value
    with pytest.raises(ValueError):pair._resolve_policy(campaigns,runs,ref,'evaluation')


@pytest.mark.parametrize('change',['parameters','execution','dataset','instrument','controlled','training_overlap'])
def test_changed_policy_source_and_training_overlap_fail_closed(tmp_path,monkeypatch,change):
    campaigns,runs,ref,campaign,records=authority(tmp_path,monkeypatch);source=records[ref.source_backtest_id]
    if change=='parameters':source['run_metadata']['strategy']['parameters']['position_size']=2
    elif change=='execution':source['execution_settings']['commission_per_contract_per_side']='1'
    elif change=='dataset':source['run_metadata']['dataset']['sha256']='0'*64
    elif change=='instrument':source['run_metadata']['instrument']['symbol']='NQ'
    elif change=='controlled':source['native_account_control']={'already':'controlled'}
    else:source['period_start_utc']='2026-01-09T15:00:00Z'
    with pytest.raises(ValueError):pair._resolve_policy(campaigns,runs,ref,'evaluation')


def test_changed_package_or_unselected_candidate_is_not_authority(tmp_path,monkeypatch):
    campaigns,runs,ref,campaign,records=authority(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match='outside'):pair._resolve_policy(campaigns,runs,ref.model_copy(update=dict(candidate_id='4'*64)),'evaluation')
    campaign['frozen']['search_settings']['native_execution']['horizon_calendar_days']=15
    with pytest.raises(ValueError,match='hash'):pair._resolve_policy(campaigns,runs,ref,'evaluation')


def test_even_rehashed_saved_package_cannot_change_frozen_forecast_horizon(tmp_path,monkeypatch):
    campaigns,runs,ref,campaign,records=authority(tmp_path,monkeypatch)
    package=campaign['frozen'];package.pop('package_sha256')
    package['search_settings']['native_execution']['horizon_calendar_days']=15
    campaign['frozen']=pair.seal(package,'package_sha256')
    changed=ref.model_copy(update=dict(package_sha256=campaign['frozen']['package_sha256']))
    with pytest.raises(ValueError,match='actual training report'):pair._resolve_policy(campaigns,runs,changed,'evaluation')


def test_pair_comparison_cannot_use_a_final_token_or_metadata_bypass():
    pair._ordinary_context()
    with final_authorization('protected-final-token'):
        with pytest.raises(ValueError,match='ordinary recorded OOS'):pair._ordinary_context()
    with metadata_only():
        with pytest.raises(ValueError,match='ordinary recorded OOS'):pair._ordinary_context()
