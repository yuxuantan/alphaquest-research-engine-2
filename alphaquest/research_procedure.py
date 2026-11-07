"""Pure terminal planning and complete-procedure identity contracts.

Reuses the existing fold/qualification/phase owners;
it neither calculates accounts nor chooses a policy from holdout results.
"""
from copy import deepcopy
from datetime import date, timedelta
from hashlib import sha256
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator

from alphaquest.prop.adapter import canonical
from alphaquest.research_folds import (FoldSettings, SESSION_CONVENTION,
                                      _splits, _validated_dates, _window)


def digest(value):
    return sha256(canonical(value).encode()).hexdigest()


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)


class TerminalSelection(Strict):
    version: Literal['single_terminal_fit_v1'] = 'single_terminal_fit_v1'
    training_law: Literal['same_rolling_or_expanding_law'] = 'same_rolling_or_expanding_law'
    target_law: Literal['next_outer_test_session_count'] = 'next_outer_test_session_count'
    holdout_in_development: Literal[False] = False
    candidate_membership: Literal['complete_frozen_search_space'] = 'complete_frozen_search_space'
    qualification: Literal['rerun_inner_qualification'] = 'rerun_inner_qualification'
    selected_family: Literal['existing_independent_phase_selectors'] = 'existing_independent_phase_selectors'


class FinalEvidenceRules(Strict):
    version: Literal['final_procedure_evidence_v1'] = 'final_procedure_evidence_v1'
    require_final_holdout: bool = False
    require_evaluation_completed_acquisition: bool | None = None
    minimum_funded_trader_receipts: str | None = None

    @field_validator('minimum_funded_trader_receipts')
    @classmethod
    def finite_receipts(cls,value):
        if value is None:return None
        try:
            parsed=Decimal(value)
            if not parsed.is_finite() or parsed<0:raise ValueError('Final receipt threshold must be finite and nonnegative.')
        except (InvalidOperation,OverflowError):raise ValueError('Final receipt threshold must be an exact finite decimal string.') from None
        return value

    require_complete_replay: Literal[True] = True
    require_qualified_current_membership: Literal[True] = True
    require_reliability_assessable: Literal[True] = True
    holdout_selection: Literal['never_rerank_or_replace'] = 'never_rerank_or_replace'
    family_aggregation: Literal['retain_members_without_implicit_weights'] = 'retain_members_without_implicit_weights'
    production_qualification: Literal[False] = False


class SessionWindow(Strict):
    convention: Literal['cme_chicago_1700_v1'] = SESSION_CONVENTION
    sessions: list[str] = Field(min_length=1)

    @model_validator(mode='after')
    def ordered(self):
        _validated_dates(self.sessions)
        return self


def terminal_plan(development, target, settings, *, origin_session, application_id=None):
    """Use existing retained-train/inner split law without synthetic future bars.

    Caller verifies scheduled-open calendar membership. `target` is price-free
    calendar metadata, not inferred missing market observations. No outcome input
    is accepted. Every gap session belongs to the declared development inventory.
    """
    if type(settings) is not FoldSettings:
        raise ValueError('Terminal selection requires validated FoldSettings.')
    _validated_dates(development); _validated_dates(target)
    if origin_session != development[0]:
        raise ValueError('The original development origin cannot silently move.')
    if development[-1] >= target[0]:
        raise ValueError('Final target sessions cannot enter development training.')
    if len(target) != settings.outer_test_sessions:
        raise ValueError('Final target must retain the predeclared outer test session count.')
    gap = settings.purge_sessions + settings.embargo_sessions
    end = len(development)-gap
    if end < settings.outer_train_sessions:
        raise ValueError('Insufficient terminal training history after the declared gap.')
    start = end-settings.outer_train_sessions if settings.mode=='rolling' else 0
    train = _window(development[start:end])
    inner = []
    for fold in _splits(train['sessions'], settings.inner_train_sessions,
                        settings.inner_validation_sessions, settings):
        fold['validation'] = fold.pop('evaluation')
        inner.append(fold)
    if len(inner) < settings.minimum_inner_folds:
        raise ValueError('Insufficient complete terminal inner folds.')
    return dict(version='terminal-window-v1', convention=SESSION_CONVENTION,
        origin_session=origin_session, train=train, inner=inner, test=_window(target),
        excluded=dict(purge_sessions=development[end:end+settings.purge_sessions],
                      embargo_sessions=development[end+settings.purge_sessions:]),
        information_cutoff_session=train['last_session'],
        target_cutoff_date_exclusive=str(date.fromisoformat(target[-1])+timedelta(days=1)),
        boundary_policy='cold_start_finish_flat',
        unused_inner_tail=[day for day in train['sessions'] if day>inner[-1]['validation']['last_session']])


def freeze_procedure(campaign, *, terminal, evidence_rules, terminal_window,
                     report_fingerprint, development_identity, access_evidence,
                     reservation_id, procedure_id, created_at_utc):
    """Create the whole server-derived package, never a selected-winner subset.

    Persistence must bind the resulting SHA to an immutable coordinator journal
    row. A client-supplied selfhash does not confer execution authority.
    """
    if type(terminal) is not TerminalSelection or type(evidence_rules) is not FinalEvidenceRules:
        raise ValueError('Explicit validated terminal and evidence contracts are required.')
    if campaign.get('status') != 'complete' or not report_fingerprint:
        raise ValueError('Freeze requires the complete evaluated research report and its verified artifacts.')
    plan, declaration = campaign['plan'], campaign['declaration']
    if not plan.get('economic_studies') or plan.get('reliability') is None:
        raise ValueError('A full economic procedure requires its evaluated phase/reliability declarations.')
    if declaration.get('terminal_selection') != terminal.model_dump(mode='json'):
        raise ValueError('Terminal law was not declared in the evaluated campaign; rerun the complete procedure.')
    if declaration.get('final_evidence') != evidence_rules.model_dump(mode='json'):
        raise ValueError('Final evidence rules were not declared before evaluation.')
    candidates = sorted(deepcopy(plan['candidates']), key=lambda row: row['id'])
    if not candidates or len({row['id'] for row in candidates}) != len(candidates):
        raise ValueError('Freeze requires complete unique expanded source configurations.')
    configurations = []
    provenance = []
    for row in candidates:
        required = ('id','strategy_id','parameters','strategy','numeric_parameters',
                    'non_signal_parameters','complexity')
        if any(key not in row for key in required):
            raise ValueError('Source expansion omitted part of the configuration contract.')
        configurations.append({key:deepcopy(row[key]) for key in required})
        provenance.append(deepcopy(row))
    algorithm = dict(version='terminal-nested-selection-v1', configurations=configurations,
        fold_settings=deepcopy(declaration['folds']),
        qualification=deepcopy(plan['qualification']), regimes=deepcopy(plan['regimes']),
        execution_settings=deepcopy(plan['execution_settings']),
        execution_scenarios=deepcopy(plan['execution_scenarios']),
        economic_studies=deepcopy(plan['economic_studies']), baselines=deepcopy(plan['baselines']),
        reliability=deepcopy(plan['reliability']), terminal_selection=terminal.model_dump(mode='json'),
        final_evidence=evidence_rules.model_dump(mode='json'), engine_identity=plan['engine_identity'])
    result = dict(schema_version='research-procedure-v1', procedure_id=procedure_id,
        campaign_id=campaign['campaign_id'], created_at_utc=created_at_utc,
        algorithm=algorithm, algorithm_sha256=digest(algorithm),
        evaluated_report=deepcopy(report_fingerprint),
        original_declaration=deepcopy(declaration), evaluated_plan_sha256=digest(plan),
        complete_source_expansion=provenance, optimization_grids=deepcopy(plan['optimization_grids']),
        development=deepcopy(development_identity), terminal_plan=deepcopy(terminal_window),
        access_evidence=deepcopy(access_evidence), reservation_id=reservation_id,
        current_selection_scope='same_pinned_development_excluding_final_holdout',
        readiness='NOT_PRODUCTION_QUALIFIED')
    result['procedure_sha256'] = digest(result)
    return result


def verify_procedure(package, *, authoritative_sha256, current_engine_identity=None):
    """Saved authority is mandatory; a modified, rehashed client blob still fails."""
    if package.get('schema_version') != 'research-procedure-v1':
        raise ValueError('Unsupported procedure version.')
    unsigned = {key:value for key,value in package.items() if key!='procedure_sha256'}
    if digest(unsigned) != package.get('procedure_sha256') or package['procedure_sha256'] != authoritative_sha256:
        raise ValueError('Frozen procedure differs from its authoritative journal seal.')
    if digest(package['algorithm']) != package['algorithm_sha256']:
        raise ValueError('Complete algorithm identity differs.')
    if current_engine_identity is not None and package['algorithm']['engine_identity'] != current_engine_identity:
        raise ValueError('Frozen implementation changed; reports may reopen, but new calculation requires a new procedure.')
    return deepcopy(package)


def application_identity(package, terminal_window, *, purpose, source_identity, current_engine_identity):
    if purpose not in ('final_verification','current_development'):
        raise ValueError('Unknown procedure application role.')
    if package['algorithm']['engine_identity'] != current_engine_identity:
        raise ValueError('Procedure implementation changed.')
    if terminal_window != package['terminal_plan'] or source_identity != package['development']:
        raise ValueError('Development/source/window overrides are forbidden after procedure freeze.')
    value = dict(version='procedure-application-v1', procedure_sha256=package['procedure_sha256'],
        purpose=purpose, terminal_plan=deepcopy(terminal_window), development=deepcopy(source_identity),
        engine_identity=current_engine_identity)
    value['application_sha256'] = digest(value)
    return value


def recommendation_phase(*, current_selection, qualification, reliability_status,
                         final_status, rules, model_blockers=(), operational_blockers=()):
    """An endorsement gate only; it cannot select or replace a family member."""
    if type(rules) is not FinalEvidenceRules:
        raise ValueError('Recommendation requires its frozen evidence rules.')
    approved = sorted(row['candidate_id'] for row in qualification['candidates'] if row['status']=='PASS')
    if approved != sorted(qualification['approved_ids']):
        raise ValueError('Qualification summary differs from complete PASS membership.')
    packages = deepcopy(current_selection.get('frozen_packages', []))
    decision = current_selection.get('decision', {})
    if sorted(decision.get('selected_ids', [])) != sorted(package['candidate_id'] for package in packages):
        raise ValueError('Current phase packages differ from the complete frozen selection family.')
    if any(package['source_configuration_id'] not in approved for package in packages):
        raise ValueError('Current selection contains a nonqualified or reference-only configuration.')
    evidence = []
    if rules.require_reliability_assessable and reliability_status != 'ASSESSABLE_WITH_LIMITATIONS':
        evidence.append('insufficient_selection_reliability')
    if rules.require_final_holdout and final_status != 'COMPLETE_UNRESELECTED_ASSESSMENT':
        evidence.append('required_final_verification_unavailable')
    if final_status in ('FAILED_VERIFICATION_CRITERIA','INCOMPLETE_REPLAY'):
        evidence.append('frozen_final_verification_gate_not_met')
    if not packages or decision.get('status') not in ('FROZEN_POLICY', 'FROZEN_FAMILY'):
        status='NO_QUALIFIED_DEPLOYMENT_CANDIDATE'
    elif evidence:
        status='NO_QUALIFIED_DEPLOYMENT_CANDIDATE'
    elif len(packages)>1:
        status='POLICY_FAMILY_REQUIRES_PREFERENCE'
    elif model_blockers or operational_blockers:
        status='RESEARCH_CANDIDATE_ONLY'
    else:
        status='QUALIFIED_FOR_FORWARD_REVIEW'
    return dict(status=status, selected_packages=packages, approved_configuration_ids=approved,
        evidence_blockers=evidence, model_blockers=list(model_blockers),
        operational_blockers=list(operational_blockers), production_qualified=False,
        final_verification_status=final_status,
        no_reselection=True)


def assess_final_outcomes(replay,rules):
    """Apply only explicit predeclared per-member gates; never rank the holdout."""
    if type(rules) is not FinalEvidenceRules:raise ValueError('Validated final evidence rules required.')
    if not replay or replay.get('status')!='complete':return dict(status='NOT_ASSESSED_NO_SELECTED_POLICY',members=[],no_reselection=True)
    rows=[]
    for item in replay['items']:
        result=item['result'];failures=[]
        if item['phase']=='evaluation' and rules.require_evaluation_completed_acquisition is True and result.get('acquisition_completed') is not True:
            failures.append('required_acquisition_not_completed_within_final_window')
        if item['phase']=='funded' and rules.minimum_funded_trader_receipts is not None:
            amount=result.get('cash_received')
            if amount is None or Decimal(str(amount))<Decimal(rules.minimum_funded_trader_receipts):failures.append('received_cash_below_predeclared_final_floor')
        rows.append(dict(phase=item['phase'],candidate_id=item['candidate_id'],frozen_package_sha256=item['frozen_package_sha256'],
            status='FAILED_DECLARED_GATE' if failures else 'OBSERVED',failures=failures,
            acquisition_completed=result.get('acquisition_completed'),censored=result.get('censored'),cash_received=result.get('cash_received')))
    return dict(status='FAILED_VERIFICATION_CRITERIA' if any(r['failures'] for r in rows) else 'COMPLETE_UNRESELECTED_ASSESSMENT',
        members=rows,no_reselection=True,interpretation='One held-out historical observation per frozen policy; explicit outcome gates do not certify or estimate a future mean.')
