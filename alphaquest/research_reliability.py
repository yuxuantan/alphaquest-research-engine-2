"""Descriptive, fold-cluster reliability of a declared selection procedure.

This module consumes immutable forecasts and chronological outcomes. It never
simulates an account, chooses a policy, or turns a selected family into weights.
"""
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from math import ceil, isfinite, sqrt
from statistics import mean
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator

from .prop.adapter import canonical

VERSION = 'selection-reliability-v1'
INSUFFICIENT = 'INSUFFICIENT_EVIDENCE'
ASSESSABLE = 'ASSESSABLE_WITH_LIMITATIONS'


class ReliabilitySettings(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    minimum_outer_blocks: StrictInt = Field(default=5, ge=2, le=10000)
    minimum_complete_fold_fraction: float = Field(default=1., gt=0, le=1, strict=True)
    confidence_level: float = Field(default=.95, ge=.5, lt=1, strict=True)
    bootstrap_block_folds: StrictInt = Field(default=1, ge=1, le=10000)
    historical_bootstrap_replicates: StrictInt = Field(default=1000, ge=100, le=10000)
    historical_bootstrap_seed: StrictInt = Field(default=137, ge=0, le=2**32-1)
    minimum_calibration_blocks: StrictInt = Field(default=20, ge=2, le=10000)
    minimum_baseline_mean_improvement: Decimal = Decimal('0')
    require_baseline_for_recommendation: StrictBool = True
    abstention_action: Literal['unmeasured', 'no_account_no_fee'] = 'unmeasured'

    @field_validator('minimum_baseline_mean_improvement', mode='before')
    @classmethod
    def finite_threshold(cls, value):
        try:
            threshold = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError('Baseline improvement must be a finite nonnegative number.') from exc
        if type(value) is bool or not threshold.is_finite() or threshold < 0 or not isfinite(float(threshold)):
            raise ValueError('Baseline improvement must be finite and nonnegative.')
        return value


def _digest(value):
    return sha256(canonical(value).encode()).hexdigest()


def _number(value):
    if value is None or type(value) is bool:
        return None
    number = float(value)
    return number if isfinite(number) else None


def logical_policy_identity(package):
    """Cross-fold policy identity excludes dates, draws and generated report IDs."""
    config = package['configuration']
    strategy = deepcopy(package['strategy'])
    strategy.pop('session_flattening', None)
    signal = dict(id=strategy.get('id'), parameters=strategy.get('parameters', {}))
    sizing = dict(micros=config['micros'], sizing=config.get('sizing'),
                  max_micros=config['simulation']['max_micros'])
    profile = config['profile']
    value = dict(phase=package['phase'], strategy=strategy, sizing=sizing,
                 profile=profile, costs=config['costs'], retry=config.get('retry'))
    return dict(policy_sha256=_digest(value), signal_sha256=_digest(signal),
                sizing_sha256=_digest(sizing), profile_sha256=_digest(profile), definition=value)


def _window(outer):
    return dict(outer['test'], cutoff_date_exclusive=(
        date.fromisoformat(outer['test']['last_session'])+timedelta(days=1)).isoformat())


def _member(package, forecast, replay, outer):
    phase = package['phase']; reasons = []
    forecast_reasons = []
    metrics = deepcopy((forecast or {}).get('metrics', {}))
    actual = replay or {}
    window = _window(outer)
    if package.get('outer_window') != window:
        reasons.append('frozen_window_differs_from_declared_outer')
    if not forecast:
        forecast_reasons.append('training_forecast_missing')
    if not replay:
        reasons.append('chronological_replay_missing')
    elif actual.get('frozen_binding', {}).get('package_sha256') != package.get('package_sha256'):
        reasons.append('replay_package_binding_differs')
    identity = logical_policy_identity(package)
    row = dict(candidate_id=package['candidate_id'], package_sha256=package['package_sha256'],
               logical_policy=identity, profile=deepcopy(package['configuration']['profile']),
               costs=deepcopy(package['configuration']['costs']), window=window,
               forecast_metrics=metrics, forecast_uncertainty=deepcopy((forecast or {}).get('uncertainty', {})),
               historical_paths=1 if replay else 0, outcome=actual.get('outcome'),
               production_qualified=False, observation_reasons=reasons,
               forecast_comparability_reasons=forecast_reasons)
    if phase == 'funded':
        if actual and actual.get('horizon_observations_complete') is not True:
            reasons.append('incomplete_outer_horizon')
        convention = package.get('receipt_amount_convention')
        if actual and actual.get('receipt_amount_convention') != convention:
            reasons.append('receipt_convention_differs')
        # The current dated forecast owner models raw kernel entitlements only.
        if convention != 'kernel_entitlement_unrounded':
            forecast_reasons.append('forecast_receipt_convention_not_supported')
        expected = _number(metrics.get('expected_funded_cash_payouts_within_horizon'))
        received = _number(actual.get('cash_received'))
        if expected is None:
            forecast_reasons.append('forecast_received_cash_estimand_missing')
        if received is None:
            reasons.append('observed_received_cash_missing')
        probability = _number(metrics.get('probability_first_payout'))
        row.update(receipt_delay_calendar_days=package.get('receipt_delay_calendar_days'),
                   receipt_amount_convention=convention, expected_cash_received=expected,
                   cash_received=received, pending_cash=_number(actual.get('pending_cash')),
                   gross_account_deductions=_number(actual.get('gross_account_deductions')),
                   lifetime_censored=actual.get('lifetime_censored'),
                   forecast_error=received-expected if not reasons and not forecast_reasons else None,
                   payout_probability=probability, payout_received=bool(received > 0) if received is not None else None,
                   comparable=not reasons and not forecast_reasons, observation_valid=not reasons)
    else:
        row.update(paid_fees=_number(actual.get('paid_fees')),
                   acquisition_completed=actual.get('acquisition_completed'), censored=actual.get('censored'),
                   calendar_days_to_funded=_number(actual.get('calendar_days_to_funded')),
                   effective_observation_cutoff_exclusive=actual.get('effective_observation_cutoff_exclusive'),
                   forecast_error=None, comparable=False,
                   observation_valid=not reasons and _number(actual.get('paid_fees')) is not None)
        row['acquisition_comparability'] = 'Eventual acquisition mean and finite-horizon censored observation are different estimands.'
    row['comparability_reasons'] = reasons + forecast_reasons
    return row


def _empirical_bounds(values, confidence_level):
    """One-based inverse-CDF ranks without floating tail-boundary movement."""
    numerator, denominator = Decimal(str(confidence_level)).as_integer_ratio()
    tail_numerator = denominator-numerator
    tail_denominator = 2*denominator
    count = len(values)
    lower = (count*tail_numerator+tail_denominator-1)//tail_denominator
    upper = (count*(tail_denominator-tail_numerator)+tail_denominator-1)//tail_denominator
    ordered = sorted(values)
    return [float(ordered[lower-1]), float(ordered[upper-1])], [lower, upper]


def _interval(values, settings):
    """Circular moving-block fold bootstrap, descriptive and explicitly conditional."""
    n = len(values); block = settings.bootstrap_block_folds
    if n < settings.minimum_outer_blocks or n // block < 2:
        return dict(status=INSUFFICIENT, interval=None, observed_outer_blocks=n,
                    reason='Too few complete historical fold blocks for the declared bootstrap.')
    numerator, denominator = Decimal(str(settings.confidence_level)).as_integer_ratio()
    if settings.historical_bootstrap_replicates*(denominator-numerator) < 10*denominator:
        return dict(status=INSUFFICIENT, interval=None, observed_outer_blocks=n,
                    reason='Historical bootstrap requires at least five expected replicates per two-sided tail at the declared confidence.')
    rng = np.random.default_rng(settings.historical_bootstrap_seed)
    means = []
    for _ in range(settings.historical_bootstrap_replicates):
        starts = rng.integers(0, n, size=ceil(n/block))
        indices = [(int(start)+offset) % n for start in starts for offset in range(block)][:n]
        means.append(mean(values[index] for index in indices))
    bounds, ranks = _empirical_bounds(means, settings.confidence_level)
    return dict(status=ASSESSABLE, interval=bounds, inverse_cdf_ranks=ranks,
                observed_outer_blocks=n, method='circular_moving_block_bootstrap_of_saved_fold_outputs',
                block_folds=block, confidence_level=settings.confidence_level,
                replicates=settings.historical_bootstrap_replicates, seed=settings.historical_bootstrap_seed,
                interpretation='Descriptive historical output variability conditional on this saved procedure. Does not refit selection, establish independent blocks or bound future performance.')


def _stability(rows):
    pairs = []
    for previous, current in zip(rows, rows[1:]):
        def ids(row, field):
            return {member['logical_policy'][field] for member in row['members']}
        before, after = ids(previous, 'policy_sha256'), ids(current, 'policy_sha256')
        comparable = previous['action'] != 'missing' and current['action'] != 'missing'
        pairs.append(dict(from_fold=previous['outer_fold'], to_fold=current['outer_fold'],
            comparable=comparable,
            family_jaccard=len(before & after)/len(before | after) if comparable and before | after else None,
            signal_changed=ids(previous, 'signal_sha256') != ids(current, 'signal_sha256') if comparable else None,
            sizing_changed=ids(previous, 'sizing_sha256') != ids(current, 'sizing_sha256') if comparable else None,
            profile_changed=ids(previous, 'profile_sha256') != ids(current, 'profile_sha256') if comparable else None))
    return dict(transitions=pairs, distinct_policies=len({m['logical_policy']['policy_sha256'] for r in rows for m in r['members']}),
                interpretation='Changes describe the adaptive procedure, not its quality. Generated source IDs, training windows and random seeds are excluded.')


def _index(items, key):
    result = {item[key]: item for item in items}
    if len(result) != len(items):
        raise ValueError(f'Duplicate reliability evidence identity: {key}.')
    return result


def _fold_row(phase, outer, fold, settings):
    selection = (fold or {}).get('economic_selection') or {}
    phases = _index(selection.get('phases', []), 'phase')
    selected = phases.get(phase, {})
    packages = selected.get('frozen_packages', [])
    forecasts = _index(selected.get('training_forecasts', []), 'candidate_id')
    replays = _index([item for item in ((fold or {}).get('chronological_replay') or {}).get('items', [])
                      if item['phase'] == phase], 'candidate_id')
    _index(packages, 'candidate_id')
    members = [_member(package, forecasts.get(package['candidate_id']),
                        (replays.get(package['candidate_id']) or {}).get('result'), outer) for package in packages]
    status = selected.get('decision', {}).get('status', selection.get('status', 'MISSING_FOLD'))
    is_abstention = bool(fold and selection and not packages and status in (
        'NO_QUALIFIED_CONFIGURATION', 'NO_FEASIBLE_POLICY', 'INSUFFICIENT_EVIDENCE',
        'NO_FEASIBLE_CANDIDATE', 'NO_CANDIDATE'))
    # Inspect the coordinator's no-choice status rather than treating a missing
    # replay or malformed selected record as an intentional no-account action.
    if not packages and selection.get('status') in ('NO_QUALIFIED_CONFIGURATION', 'NO_FEASIBLE_POLICY', 'INSUFFICIENT_EVIDENCE'):
        is_abstention = True
    no_account = is_abstention and settings.abstention_action == 'no_account_no_fee'
    action = ('selected_policy' if len(members) == 1 else 'selected_family' if members else
              'no_account_no_fee' if no_account else 'unmeasured_abstention' if is_abstention else 'missing')
    eligible = len(members) == 1 and members[0]['historical_paths'] == 1
    if eligible:
        eligible = members[0]['observation_valid']
    baseline_members = []
    references = [r for r in (fold or {}).get('baseline_results', []) if r['phase'] == phase]
    _index(references, 'baseline_id')
    for reference in references:
        member = _member(reference['frozen_package'], reference.get('training_forecast'),
                         reference.get('chronological_replay'), outer)
        member.update(baseline_id=reference['baseline_id'], required=reference['required'],
                      edge_qualification=reference.get('edge_qualification'), recommendation_eligible=False)
        baseline_members.append(member)
    return dict(outer_fold=outer['index'], window=_window(outer), selection_status=status,
                action=action, family_size=len(members), members=members, baseline_members=baseline_members,
                scalar_eligible=bool(eligible or no_account), completed_fold=bool(fold),
                abstained=is_abstention, no_account_cash=0. if no_account else None,
                no_account_fees=0. if no_account else None)


def _comparisons(phase, rows, declarations, settings, ambiguous):
    comparisons = []
    for declaration in declarations:
        pairs = []; excluded = []
        for row in rows:
            ref = next((m for m in row['baseline_members'] if m['baseline_id'] == declaration['id']), None)
            reason = None
            selected = row['members'][0] if len(row['members']) == 1 else None
            if ref is None:
                reason = 'baseline_missing'
            elif not row['scalar_eligible']:
                reason = 'selected_action_ambiguous_or_unmeasured'
            elif not ref['observation_valid']:
                reason = 'baseline_' + ','.join(ref['observation_reasons'] or ['observed_economics_missing'])
            elif selected and (selected['profile'] != ref['profile'] or selected['costs'] != ref['costs']):
                reason = 'profile_or_cost_assumptions_differ'
            elif phase == 'funded' and (selected and (
                    selected['receipt_delay_calendar_days'] != ref['receipt_delay_calendar_days'] or
                    selected['receipt_amount_convention'] != ref['receipt_amount_convention'])):
                reason = 'receipt_estimands_differ'
            elif phase == 'evaluation' and (selected is None or not selected['acquisition_completed'] or
                                            not ref['acquisition_completed'] or selected['censored'] or ref['censored']):
                reason = 'acquisition_incomplete_or_no_account_action'
            if reason:
                excluded.append(dict(outer_fold=row['outer_fold'], reason=reason))
                continue
            if phase == 'funded':
                actual = selected['cash_received'] if selected else 0.
                baseline = ref['cash_received']
                pairs.append(dict(outer_fold=row['outer_fold'], selected=actual, baseline=baseline,
                                  improvement=actual-baseline, selected_action=row['action']))
            else:
                if any(m['paid_fees'] is None or m['calendar_days_to_funded'] is None for m in (selected, ref)):
                    excluded.append(dict(outer_fold=row['outer_fold'], reason='completed_acquisition_metrics_missing'))
                    continue
                pairs.append(dict(outer_fold=row['outer_fold'], selected=selected['paid_fees'], baseline=ref['paid_fees'],
                    improvement=ref['paid_fees']-selected['paid_fees'],
                    calendar_days_improvement=ref['calendar_days_to_funded']-selected['calendar_days_to_funded']))
        values = [p['improvement'] for p in pairs]
        # No interval over a success-only subset or an implicitly weighted family.
        complete = bool(rows) and len(pairs) == len(rows) and not ambiguous
        interval = _interval(values, settings) if complete else dict(status=INSUFFICIENT, interval=None,
            observed_outer_blocks=len(values), reason='Incomplete pairing or selected family; no survivor-only inference.')
        lower = interval['interval'][0] if interval['interval'] is not None else None
        threshold = float(settings.minimum_baseline_mean_improvement)
        pass_mean = mean(values) > threshold if values else False
        decision = (INSUFFICIENT if not complete or interval['status'] == INSUFFICIENT else
                    'DESCRIPTIVE_THRESHOLD_MET' if lower > threshold and (phase == 'funded' or
                    all(p['calendar_days_improvement'] >= 0 for p in pairs)) else 'THRESHOLD_NOT_MET')
        comparisons.append(dict(baseline_id=declaration['id'], required=declaration['required'],
            declared_outer_folds=len(rows), paired_outer_folds=len(pairs), pairs=pairs, exclusions=excluded,
            metric='received_cash_improvement' if phase == 'funded' else 'completed_acquisition_fee_saving',
            paired_mean_improvement=mean(values) if values else None,
            minimum_mean_improvement=threshold, point_estimate_exceeds_threshold=pass_mean,
            historical_interval=interval, decision=decision, production_qualified=False,
            interpretation='Predeclared paired reference comparison; positive values favor selection. Descriptive intervals are not simultaneous superiority or future guarantees.'))
    return comparisons


def _phase_result(phase, plan, folds, settings):
    by_fold = _index(folds, 'index')
    rows = [_fold_row(phase, outer, by_fold.get(outer['index']), settings) for outer in plan['folds']]
    count = len(rows); eligible = [r for r in rows if r['scalar_eligible']]
    ambiguous = any(r['family_size'] > 1 for r in rows)
    reasons = []
    if count < settings.minimum_outer_blocks:
        reasons.append('minimum_outer_blocks_not_met')
    if not count or len(eligible)/count < settings.minimum_complete_fold_fraction:
        reasons.append('minimum_complete_fold_fraction_not_met')
    if ambiguous:
        reasons.append('selected_family_has_no_predeclared_unique_action')
    complete_scalar = bool(count) and len(eligible) == count and not ambiguous
    if not complete_scalar:
        reasons.append('scalar_procedure_outcome_incomplete')
    measured = [r['members'][0] for r in eligible if r['action'] == 'selected_policy']
    scalar = dict(status='complete' if complete_scalar else 'unavailable', denominator_outer_folds=count,
                  observed_unique_actions=len(eligible), mean_cash_received=None,
                  mean_acquisition_cost=None, mean_calendar_days_to_funded=None)
    errors = dict(status=INSUFFICIENT, paired_fold_count=0, mean_error=None, mean_absolute_error=None,
                  root_mean_squared_error=None, historical_interval=None)
    calibration = dict(status=INSUFFICIENT, historical_block_count=0, minimum_blocks=settings.minimum_calibration_blocks,
                       brier_score=None, observed_rate=None, predicted_rate=None,
                       reason='No comparable unique-action finite-horizon probability pairs.')
    if phase == 'funded':
        cash = [r['members'][0]['cash_received'] if r['members'] else 0. for r in eligible]
        scalar.update(total_observed_cash_received=sum(cash) if not ambiguous and eligible else None,
                      observed_pending_cash=sum(m['pending_cash'] or 0 for m in measured) if not ambiguous else None,
                      mean_cash_received=mean(cash) if complete_scalar else None,
                      historical_interval=_interval(cash, settings) if complete_scalar else None)
        if complete_scalar and scalar['historical_interval']['status'] == INSUFFICIENT:
            reasons.append('historical_interval_evidence_insufficient')
        paired = [m for m in measured if m['comparable']]
        if not ambiguous and paired:
            deviations = [m['forecast_error'] for m in paired]
            errors.update(status='DESCRIPTIVE', paired_fold_count=len(paired),
                mean_error=mean(deviations), mean_absolute_error=mean(abs(v) for v in deviations),
                root_mean_squared_error=sqrt(mean(v*v for v in deviations)),
                historical_interval=_interval(deviations, settings) if len(paired) == count else None)
            probabilities = [m for m in paired if m['payout_probability'] is not None and 0 <= m['payout_probability'] <= 1]
            if probabilities:
                n = len(probabilities)
                sufficient = n == count and n >= settings.minimum_calibration_blocks
                calibration.update(status=ASSESSABLE if sufficient else INSUFFICIENT, historical_block_count=n,
                    brier_score=mean((m['payout_probability']-int(m['payout_received']))**2 for m in probabilities),
                    observed_rate=mean(int(m['payout_received']) for m in probabilities),
                    predicted_rate=mean(m['payout_probability'] for m in probabilities),
                    reason='Descriptive payout-receipt calibration; independent historical blocks are not established.' if sufficient else
                           'Too few complete historical probability pairs; Monte Carlo paths cannot increase this count.')
    else:
        all_acquired = complete_scalar and len(measured) == count and all(m['acquisition_completed'] and not m['censored'] for m in measured)
        scalar.update(total_observed_paid_fees=sum(m['paid_fees'] for m in measured) if not ambiguous else None,
            completed_acquisitions=sum(m['acquisition_completed'] is True for m in measured) if not ambiguous else None,
            censored_acquisitions=sum(m['censored'] is True for m in measured) if not ambiguous else None,
            mean_acquisition_cost=mean(m['paid_fees'] for m in measured) if all_acquired else None,
            mean_calendar_days_to_funded=mean(m['calendar_days_to_funded'] for m in measured) if all_acquired and all(m['calendar_days_to_funded'] is not None for m in measured) else None,
            interpretation='All paid fees retained. Acquisition means require every declared action to complete; eventual forecast versus censored finite-horizon errors are not computed.')
        if not all_acquired:
            reasons.append('acquisition_mean_unidentified_with_censoring_or_missing_actions')
    declarations = [d for d in plan.get('baselines', []) if d['phase'] == phase]
    comparisons = _comparisons(phase, rows, declarations, settings, ambiguous)
    if settings.require_baseline_for_recommendation and not declarations:
        reasons.append('predeclared_baseline_missing')
    if any(c['required'] and c['decision'] != 'DESCRIPTIVE_THRESHOLD_MET' for c in comparisons):
        reasons.append('required_baseline_threshold_not_established')
    if settings.require_baseline_for_recommendation and comparisons and not any(c['decision'] == 'DESCRIPTIVE_THRESHOLD_MET' for c in comparisons):
        reasons.append('baseline_improvement_not_established')
    coverage = dict(declared_outer_folds=count, completed_outer_folds=sum(r['completed_fold'] for r in rows),
        folds_with_selected_policy=sum(bool(r['members']) for r in rows),
        abstained_folds=sum(r['abstained'] for r in rows), unmeasured_folds=sum(not r['scalar_eligible'] for r in rows),
        selected_family_folds=sum(r['family_size'] > 1 for r in rows), scalar_eligible_folds=len(eligible),
        complete_fold_fraction=len(eligible)/count if count else 0.,
        historical_outer_blocks=sum(any(m['historical_paths'] for m in r['members']) for r in rows),
        independent_block_count=None,
        unique_outer_sessions=len({s for r in rows for s in r['window']['sessions']}))
    return dict(status=INSUFFICIENT if reasons else ASSESSABLE, reasons=sorted(set(reasons)), coverage=coverage,
                folds=rows, scalar_metrics=scalar, forecast_errors=errors, calibration=calibration,
                stability=_stability(rows), baseline_comparisons=comparisons, production_qualified=False)


def consolidate_reliability(plan, folds, settings):
    """Retain the declared denominator and every member; never select on outcomes."""
    if not isinstance(settings, ReliabilitySettings):
        settings = ReliabilitySettings.model_validate(settings)
    planned = _index(plan['folds'], 'index')
    if any(fold['index'] not in planned for fold in folds):
        raise ValueError('Unexpected outer fold in reliability evidence.')
    phase_names = [s['phase'] for s in plan.get('economic_studies', [])]
    if len(set(phase_names)) != len(phase_names) or any(p not in ('evaluation', 'funded') for p in phase_names):
        raise ValueError('Reliability needs distinct supported independent phases.')
    phases = {phase: _phase_result(phase, plan, folds, settings) for phase in phase_names}
    limitations = [
        'The changing selection procedure is the unit evaluated; no last-fold or best outer policy is promoted.',
        'Outer folds are historical clusters, not proven independent experiments. Shared regimes and overlapping training windows remain dependencies.',
        'Historical output bootstrap does not refit the entire procedure and is not a future-performance confidence bound.',
        'Conditional Monte Carlo error, historical sampling variability and model/provider/execution/future uncertainty are separate quantities.',
        'Families retain all correlated alternatives without implicit weights; incomplete and censored folds remain in denominators.',
        'Provider rules, native account-state strategy reruns, final procedure verification and deployment checks remain separate gates.',
        'Thresholds are declared research assumptions, not universal statistical certification.']
    return dict(version=VERSION, procedure_sha256=plan.get('input_identity'), settings=settings.model_dump(mode='json'),
        status=ASSESSABLE if phases and all(p['status'] == ASSESSABLE for p in phases.values()) else INSUFFICIENT,
        phases=phases, limitations=limitations, production_qualified=False,
        recommendation_eligibility='RESEARCH_EVIDENCE_ONLY',
        uncertainty_components=dict(conditional_monte_carlo='Preserved in each member forecast_uncertainty.',
            historical='Descriptive bootstrap of saved outer-fold outputs, with declared blocks and coverage.',
            model_and_future='Unquantified rule, execution, settlement, fitting and future-regime uncertainty.'))
