"""Server-authoritative current-procedure membership for observed monitoring."""
from copy import deepcopy
from decimal import Decimal
from hashlib import sha256
import json
from alphaquest.prop.adapter import canonical,digest as file_digest,source_record
from alphaquest.prop.phase_profiles import SavedTradeSource,verify_phase_source


def fingerprint(value):return sha256(canonical(value).encode()).hexdigest()


def resolve_policy(robust,declaration):
    """Read actual sealed current application; never accept a caller package.

    This is admission for supplied observation, not rerunning an old numerical
    engine or certifying current provider/platform deployment compatibility.
    """
    binding=declaration.policy_binding
    if binding is None:raise ValueError('A current procedure policy binding is required.')
    analyses=robust.analyses
    with analyses.lock:
        with analyses.connect() as db:
            latest=db.execute("SELECT x.id,x.analysis_id FROM research_procedure_applications x LEFT JOIN analyses a ON a.id=x.analysis_id WHERE x.campaign_id=? AND x.purpose='current_development' ORDER BY COALESCE(a.created,'') DESC,x.rowid DESC LIMIT 1",(binding.campaign_id,)).fetchone()
        if not latest or latest[0]!=binding.application_id:
            raise ValueError('Select the latest authoritative current-development application, not an earlier fold/final/retired selection.')
        application=robust.application(binding.campaign_id,binding.application_id)
        if application['purpose']!='current_development' or application['status']!='complete':
            raise ValueError('Complete the current-development procedure application before observing its selected policy.')
        report=robust.application_report(binding.campaign_id,binding.application_id)
        if report.get('model_version')!='procedure-application-v1':raise ValueError('Current policy requires a full-procedure application report.')
        result=report['calculations'];procedure=robust._procedure(binding.campaign_id)
        if (result['purpose']!='current_development' or result['application_id']!=binding.application_id
                or result['campaign_id']!=binding.campaign_id or result['procedure_sha256']!=procedure['procedure_sha256']):
            raise ValueError('Current application differs from its authoritative complete procedure.')
        recommendation=[row for row in result['recommendation'] if row['phase']==binding.phase]
        if len(recommendation)!=1:raise ValueError('Requested phase has no unique current recommendation.')
        recommendation=recommendation[0]
        if recommendation['status'] not in ('POLICY_FAMILY_REQUIRES_PREFERENCE','RESEARCH_CANDIDATE_ONLY','QUALIFIED_FOR_FORWARD_REVIEW'):
            raise ValueError('No qualified current policy is available; only an unbound, explicitly synthetic diagnostic is allowed.')
        if recommendation.get('evidence_blockers'):raise ValueError('Current selection evidence gates are unmet.')
        phases=[row for row in result['economic_selection']['phases'] if row['phase']==binding.phase]
        if len(phases)!=1:raise ValueError('Requested phase selection is missing or ambiguous.')
        phase=phases[0];family=phase['frozen_packages']
        if canonical(recommendation['selected_packages'])!=canonical(family):raise ValueError('Recommendation membership differs from the frozen phase family.')
        if sorted(phase['decision']['selected_ids'])!=sorted(p['candidate_id'] for p in family):
            raise ValueError('Frozen phase decision omits or adds a family member.')
        selected=[p for p in family if p['package_sha256']==binding.package_sha256]
        if len(selected)!=1:raise ValueError('Requested package is not exactly one current selected family member.')
        if len(family)>1 and not (binding.family_preference_reason or '').strip():
            raise ValueError('A retained family requires an explicit recorded preference reason; monitoring cannot invent a historical winner.')
        package=deepcopy(selected[0]);payload=deepcopy(package);checksum=payload.pop('package_sha256')
        if checksum!=fingerprint(payload):raise ValueError('Current selected package hash changed.')
        if (package.get('schema_version')!='procedure-phase-freeze-v1'
                or package.get('application_role')!='current_development' or package.get('package_role','selected_policy')!='selected_policy'
                or package.get('phase')!=binding.phase or package.get('application_id')!=binding.application_id
                or package.get('campaign_id')!=binding.campaign_id or package.get('procedure_sha256')!=procedure['procedure_sha256']):
            raise ValueError('Package is not the exact current selected phase policy.')
        qualified={row['candidate_id'] for row in result['qualification']['candidates'] if row['status']=='PASS'}
        if qualified!=set(result['qualification']['approved_ids']) or package['source_configuration_id'] not in qualified:
            raise ValueError('Current selected policy is outside complete PASS edge membership.')
        child_id=package['training_analysis_id'];child_record=analyses.get(child_id)
        if not child_record or child_record['status']!='complete' or not analyses.fingerprint(child_id):
            raise ValueError('Current training report artifacts are missing or changed.')
        child_path=analyses.root/child_id/'report.json'
        if file_digest(child_path)!=package['training_report_sha256']:raise ValueError('Current training report hash differs from the frozen package.')
        child=json.loads(child_path.read_text());context=child['training_context']
        if (context.get('version')!='procedure-training-v1'
                or any(context.get(k)!=package.get(k) for k in ('application_id','procedure_sha256','application_role','campaign_id'))
                or context.get('context_sha256')!=package['training_context_sha256']):
            raise ValueError('Training context is outside the authoritative current application.')
        rows=[row for row in child['calculations']['candidates'] if row['candidate_id']==package['candidate_id']]
        if len(rows)!=1:raise ValueError('Frozen candidate is absent or ambiguous in the training report.')
        row=rows[0];manifest=row['manifest']
        if (fingerprint(manifest)!=package['training_candidate_manifest_sha256']
                or canonical(manifest['configuration'])!=canonical(package['configuration'])
                or canonical(manifest['strategy'])!=canonical(package['strategy'])
                or child['implementation']!=package['implementation']
                or child['request'].get('native_execution')!=package.get('native_execution')):
            raise ValueError('Frozen strategy, parameters, execution law or policy configuration changed.')
        config=package['configuration'];source=SavedTradeSource(**config['source'])
        verify_phase_source(robust.runs,source,manifest['source'])
        record=source_record(robust.runs,source.source_backtest_id)
        if canonical(record)!=canonical(manifest['source']['backtest']):raise ValueError('Selected source manifest changed.')
        instrument=record['run_metadata']['instrument'];settings=record['execution_settings']
        symbol=instrument['symbol'].upper()
        if symbol not in ('NQ','MNQ') or Decimal(settings['tick_size'])!=Decimal('.25') or Decimal(settings['point_value'])!=Decimal('2' if symbol=='MNQ' else '20'):
            raise ValueError('Current whole-MNQ phase observation requires a verified NQ/MNQ source contract.')
        # Phase policies are explicitly whole MNQ contracts. A supported NQ
        # training source retains its own identity and cost adaptation; it is
        # never relabeled as measured MNQ execution evidence.
        execution_instrument=dict(symbol='MNQ',tick_size='0.25',point_value='2',currency='USD')
        actual=declaration.instrument.model_dump(mode='json')
        if actual['symbol']!='MNQ' or actual['currency']!='USD' or Decimal(actual['tick_size'])!=Decimal('.25') or Decimal(actual['point_value'])!=2:
            raise ValueError('Observed instrument must match the selected whole-MNQ execution policy.')
        if Decimal(declaration.initial_balance)!=50000:raise ValueError('Current supported phase policy requires the declared fresh $50,000 account baseline.')
        return dict(kind='authoritative_current_procedure_policy',package=package,procedure_sha256=procedure['procedure_sha256'],
            application_id=binding.application_id,application_analysis_id=latest[1],application_report_sha256=file_digest(analyses.root/latest[1]/'report.json'),
            application_created_at_utc=report['created_at_utc'],application_created_clock_semantics='analysis reservation, not publication',
            application_publication_utc=None,policy_selection_sealed_at_utc=result['economic_selection']['sealed_at_utc'],
            publication_bound='Monitor creation occurs after verification that the immutable application is complete; its server clock is the conservative forward evidence boundary.',
            training_analysis_id=child_id,training_report_sha256=package['training_report_sha256'],source_backtest_id=source.source_backtest_id,
            source_manifest_sha256=manifest['source']['manifest_sha256'],source_instrument=deepcopy(instrument),
            source_execution_settings=deepcopy(settings),instrument=execution_instrument,
            strategy=deepcopy(package['strategy']),configuration=deepcopy(config),training_forecast=dict(
                candidate_id=row['candidate_id'],status=row['status'],metrics=deepcopy(row['metrics']),uncertainty=deepcopy(row.get('uncertainty'))),
            recommendation_status=recommendation['status'],recommendation=deepcopy(recommendation),
            family_size=len(family),family_preference_reason=binding.family_preference_reason,
            production_qualified=False,broker_connection_verified=False)
