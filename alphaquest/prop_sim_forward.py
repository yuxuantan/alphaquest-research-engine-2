"""Prop Sim binding to the existing supplied-event forward monitor workflow."""
from copy import deepcopy
from hashlib import sha256
import json

from .prop.adapter import canonical,digest,source_record


def package(report,row):
    frozen=report['assessment']['frozen_package']
    binding=next(x for x in report['assessment']['sources'] if x['frozen_candidate_id']==row['frozen_candidate_id'])
    value=dict(schema_version='prop-sim-forward-policy-v1',phase=report['phase'],
        simulation_id=report['assessment']['prop_sim_review']['simulation_id'],
        campaign_id=frozen['campaign_id'],qualification_analysis_id=report['id'],
        candidate_id=row['frozen_candidate_id'],configuration=binding['frozen_manifest']['configuration'],
        strategy=binding['frozen_manifest']['strategy'],implementation=report['implementation'],
        frozen_package_sha256=frozen['package_sha256'],qualification_implementation=report['calculations']['qualification_implementation'])
    value['package_sha256']=sha256(canonical(value).encode()).hexdigest()
    return value


def current_report(analyses,simulation_id,phase,campaign_id=None):
    with analyses.connect() as db:
        saved=db.execute('SELECT payload FROM workflow_prop_simulations WHERE id=?',(simulation_id,)).fetchone()
        if not saved:return None
        saved=json.loads(saved[0]);cid=saved['campaign_ids'][phase]
        if campaign_id is not None and campaign_id!=cid:raise ValueError('Forward binding belongs to another phase campaign.')
        rows=db.execute('SELECT payload FROM campaign_assessments WHERE campaign_id=? ORDER BY rowid DESC',(cid,)).fetchall()
    for (raw,) in rows:
        attempt=json.loads(raw)
        if attempt.get('kind')!='qualification' or not attempt.get('analysis_id'):continue
        record=analyses.get(attempt['analysis_id'])
        if not record or record['status']!='complete':continue
        if not analyses.fingerprint(record['id']):raise ValueError('Qualification evidence changed.')
        report=json.loads((analyses.root/record['id']/'report.json').read_text())
        from .prop.oos_qualification import implementation
        if report['calculations'].get('qualification_implementation')!=implementation():
            raise ValueError('Run current OOS qualification before binding forward observations.')
        return report
    raise ValueError('Complete OOS qualification before forward observation.')


def launcher(analyses,simulation_id,phase):
    report=current_report(analyses,simulation_id,phase)
    rows=[r for r in report['calculations']['candidates'] if r.get('prop_qualification',{}).get('status')=='GO']
    return dict(calculations=dict(campaign_id=report['assessment']['campaign_id'],application_id=simulation_id,
        recommendation=[dict(phase=phase,status='QUALIFIED_FOR_FORWARD_REVIEW',evidence_blockers=[],
            selected_packages=[package(report,row) for row in rows])]))


def resolve(robust,declaration):
    """Return None for non-Prop-Sim bindings; retain their original resolver."""
    binding=declaration.policy_binding
    if binding is None:return None
    with robust.analyses.connect() as db:
        saved=db.execute('SELECT 1 FROM workflow_prop_simulations WHERE id=?',(binding.application_id,)).fetchone()
    if not saved:return None
    report=current_report(robust.analyses,binding.application_id,binding.phase,binding.campaign_id)
    selected=[(r,package(report,r)) for r in report['calculations']['candidates']
              if r.get('prop_qualification',{}).get('status')=='GO']
    match=[(r,p) for r,p in selected if p['package_sha256']==binding.package_sha256]
    if len(match)!=1:raise ValueError('Forward policy is not a GO member of the current frozen Prop Sim family.')
    if len(selected)>1 and not (binding.family_preference_reason or '').strip():
        raise ValueError('Record your explicit preference among the retained sizes.')
    if declaration.forecast_observation is not None:
        raise ValueError('Prop Sim currently supports execution verification; the optional complete cash-forecast observation scope belongs to native procedure policies.')
    row,p=match[0];config=p['configuration'];source_id=config['source']['source_backtest_id']
    from .prop.phase_profiles import SavedTradeSource,verify_phase_source
    source=next(x['frozen_manifest']['source'] for x in report['assessment']['sources'] if x['frozen_candidate_id']==row['frozen_candidate_id'])
    verify_phase_source(robust.runs,SavedTradeSource(**config['source']),source)
    instrument=declaration.instrument.model_dump(mode='json')
    from decimal import Decimal
    if instrument['symbol']!='MNQ' or Decimal(instrument['point_value'])!=2 or Decimal(instrument['tick_size'])!=Decimal('.25') or Decimal(declaration.initial_balance)!=50000:
        raise ValueError('Use the frozen whole-MNQ execution instrument and fresh $50,000 account.')
    record=source_record(robust.runs,source_id)
    return dict(kind='authoritative_prop_sim_policy',package=deepcopy(p),application_id=binding.application_id,
        application_analysis_id=report['id'],application_report_sha256=digest(robust.analyses.root/report['id']/'report.json'),
        application_created_at_utc=report['created_at_utc'],policy_selection_sealed_at_utc=report['created_at_utc'],
        training_analysis_id=report['assessment']['frozen_package']['analysis_id'],
        source_backtest_id=source_id,source_manifest_sha256=source['manifest_sha256'],
        instrument=instrument,source_instrument=record['run_metadata']['instrument'],
        source_execution_settings=record['execution_settings'],strategy=p['strategy'],configuration=config,
        training_forecast=dict(candidate_id=row['frozen_candidate_id'],status='estimated',metrics=report['assessment']['is_metrics'][row['frozen_candidate_id']]),
        recommendation_status='QUALIFIED_FOR_FORWARD_REVIEW',family_size=len(selected),
        family_preference_reason=binding.family_preference_reason,production_qualified=False,broker_connection_verified=False)


def execution_check(report,reviewed_episodes,notes):
    """Require actual supplied paper records, fresh clocks, and manual parity review."""
    from .prop.phase_lifecycle import instant,session_date
    calc=report['calculations'];episodes=calc['metrics']['episodes']
    ids=[sha256(canonical(e).encode()).hexdigest() for e in episodes]
    sessions={str(session_date(instant(e['start_utc']))) for e in episodes}
    sessions.update(str(session_date(instant(e['event_time_utc']))) for e in calc['reconciliation'].get('fills',[]))
    issues=[i for i in calc['reconciliation']['issues'] if not i.get('acknowledged')]
    checks=[dict(label='Distinct forward sessions with recorded trading',actual=len(sessions),required=20,passed=len(sessions)>=20),
        dict(label='Closed flat-to-flat trades',actual=len(episodes),required=30,passed=len(episodes)>=30),
        dict(label='Unexplained execution discrepancies',actual=len(issues),required=0,passed=not issues),
        dict(label='Frozen sizing conformance',actual=calc['policy_conformance']['status'],required='MATCH',passed=calc['policy_conformance']['status']=='MATCH'),
        dict(label='Supplied paper provenance',actual=report['request']['observation_kind'],required='paper',passed=report['request']['observation_kind']=='paper'),
        dict(label='Prospective supplied observation clocks',actual=calc['forward_evidence']['status'],required='SUPPLIED_FORWARD_OBSERVATIONS',passed=calc['forward_evidence']['status']=='SUPPLIED_FORWARD_OBSERVATIONS'),
        dict(label='Every closed trade manually reviewed for signal/execution parity',actual=len(set(reviewed_episodes)),required=len(ids),passed=bool(ids) and set(reviewed_episodes)==set(ids) and len(reviewed_episodes)==len(ids) and bool(notes.strip()))]
    failed=any(not c['passed'] for c in checks if c['required'] in (0,'MATCH'))
    return dict(status='GO' if all(c['passed'] for c in checks) else 'NO_GO' if failed else 'INSUFFICIENT_EVIDENCE',
        checks=checks,notes=notes,manual_signal_execution_parity_review=True,
        interpretation='Limited-pilot execution gate from supplied paper events plus manual signal parity review. Source claims and broker/provider implementation are not independently certified; this is not evidence of future profitability.')


def verified_observation(capture,simulation_id,phase,qualification_id,analyses):
    """Recheck the sealed existing forward report; never accept a client verdict."""
    fingerprint=analyses.fingerprint(capture['analysis_id'])
    if not fingerprint or fingerprint['files']['report.json']!=capture['sha256']:
        raise ValueError('Forward observation report changed or is incomplete.')
    report=json.loads((analyses.root/capture['analysis_id']/'report.json').read_text())
    binding=report.get('source_check',{}).get('policy_snapshot',{}).get('package') or {}
    if (binding.get('schema_version')!='prop-sim-forward-policy-v1'
            or binding.get('simulation_id')!=simulation_id or binding.get('phase')!=phase
            or binding.get('qualification_analysis_id')!=qualification_id):
        raise ValueError('Forward observation does not belong to this frozen qualification package.')
    from .forward_monitoring import ForwardStore
    state=ForwardStore(analyses).get(report['monitor_id'])
    if state['assessment_pending'] or state['last_completed_analysis_id']!=report['id']:
        raise ValueError('Assess the latest supplied forward events before saving execution review.')
    if state['retired'] or state['pause_latched']:
        raise ValueError('Resolve the paused or retired observation before saving execution review.')
    records=[json.loads(line) for line in (analyses.root/report['id']/'events.jsonl').read_text().splitlines()]
    return report,records
