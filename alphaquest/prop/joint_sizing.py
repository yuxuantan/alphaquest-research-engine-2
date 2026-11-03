"""Training-only joint evaluation/funded renewal sizing.

Stage profiles are independent under the existing research renewal model, so a
Cartesian search needs one simulation per stage/size, not per pair. Unfinished
lifetimes are bounded, never treated as closed accounts.
"""
from functools import lru_cache
from math import expm1, lgamma, log, log1p, nextafter, sqrt

from .parallel import map_sweep

LIFETIME_HORIZON = 20000
SCREEN_SIMS = 3000
FINAL_SIMS = 20000
REFINEMENT_SEED = 46
ACQUISITION_BOUND_ALPHA = .05


@lru_cache(maxsize=512)
def pass_probability_upper(passed, simulations, candidates):
    """Exact one-sided binomial upper bound, Bonferroni over evaluation sizes.

    Invert Pr[X <= passed] = .05 / candidates. Summation backwards from the
    largest included term avoids underflow and a SciPy runtime dependency.
    This is conditional Monte Carlo sampling uncertainty, not future parity.
    """
    if simulations <= 0 or not 0 <= passed <= simulations or candidates < 1:
        raise ValueError('Invalid acquisition-bound sample counts.')
    if passed == simulations:return 1.
    log_alpha = log(ACQUISITION_BOUND_ALPHA / candidates)
    if passed == 0:return nextafter(-expm1(log_alpha / simulations), 1.)
    low = passed / simulations
    high = 1.
    coefficient = lgamma(simulations + 1) - lgamma(passed + 1) - lgamma(simulations - passed + 1)
    for _ in range(64):
        probability = (low + high) / 2
        if probability == low or probability == high:break
        term = total = 1.
        for index in range(passed, 0, -1):
            term *= index / (simulations - index + 1) * (1 - probability) / probability
            total += term
            if term < total * 1e-16:break
        cdf_log = coefficient + passed * log(probability) + (simulations - passed) * log1p(-probability) + log(total)
        if cdf_log > log_alpha:low = probability
        else:high = probability
    return nextafter(high, 1.)


def unresolved_acquisition(evaluation):
    return evaluation['status'] != 'calibrated' and (
        evaluation.get('screening_passed', evaluation['passed']) > 0
        or evaluation.get('evaluation_censored_paths', 0) > 0)


def acquisition_bound(evaluation, candidates):
    """Optimistic cost/time bounds; never fill an unknown acquisition mean."""
    if not unresolved_acquisition(evaluation):return None
    if any(key not in evaluation for key in ('evaluation_price','activation_fee','activation_days')):return None
    possible = min(evaluation['simulations'], evaluation['passed'] + evaluation.get('evaluation_censored_paths', 0))
    probability = pass_probability_upper(possible, evaluation['simulations'], candidates)
    return dict(pass_probability_upper=probability,
        acquisition_cost_lower_bound=evaluation['evaluation_price'] / probability + evaluation['activation_fee'],
        acquisition_days_lower_bound=1 + evaluation['activation_days'],
        bound_simulations=evaluation['simulations'],bound_candidate_count=candidates,
        bound_method='one-sided exact binomial; Bonferroni 95% family coverage over evaluation sizes; censored evaluations count as possible passes')


def score_pair(evaluation, funded, bound=None, payout_cap=None):
    c = evaluation['cost_per_funded']
    t = evaluation['replacement_days']
    row = dict(evaluation_micros=evaluation['evaluation_micros'], funded_micros=funded['micros'],
        evaluation_simulations=evaluation['simulations'], funded_simulations=funded['sims'],
        pass_rate=evaluation['pass_rate'], acquisition_cost=c, acquisition_days=t,
        expected_receipts=funded['E[payout]'], funded_days=funded['days alive'],
        funded_censored_paths=funded['censored_paths'], slot_year=None, slot_year_se=None,
        upper_bound=None, reason=None, status='unavailable',
        pass_probability_upper=None, acquisition_cost_lower_bound=None,
        acquisition_days_lower_bound=None, bound_simulations=None,
        bound_candidate_count=None, bound_method=None, calibration_reason=None)
    if evaluation['status'] != 'calibrated':
        row['reason'] = evaluation['reason']
        row['calibration_reason'] = evaluation.get('funding_chain_failure_reason', evaluation['reason'])
        if bound is not None and payout_cap is not None:
            # Even a perfect funded outcome cannot exceed its whole ladder.
            # Unknown funded/evaluation times are bounded below by one session
            # each, plus actual activation days. A negative numerator over an
            # arbitrarily long unknown cycle can approach zero, not turn positive.
            receipts = 0. if funded.get('method') == 'analytical_zero_payout_bound' else payout_cap
            upper = max(0., 261 * (receipts - bound['acquisition_cost_lower_bound']) /
                        (1 + bound['acquisition_days_lower_bound']))
            row.update(bound, status='bounded_acquisition', upper_bound=upper)
        return row
    duration = t + (funded['days alive'] or 0.)
    net = funded['E[payout]'] - c
    if funded.get('lifetime_complete') is False or funded['censored_paths']:
        # Additional receipts cannot exceed each unfinished account's remaining
        # ladder. Additional lifetime can be arbitrarily long. With a negative
        # numerator the safe upper rate is zero, not a negative truncated rate.
        row.update(status='bounded', reason=funded.get('reason','Funded lifetime remains censored.'),
            upper_bound=max(0., 261 * (funded['receipts_upper_bound'] - c) / duration))
        return row
    value = 261 * net / duration
    variance = ((261 / duration)**2 * (funded['SE']**2 + evaluation['cost_se']**2)
        + (261 * net / duration**2)**2 * (funded['lifetime_se']**2 + evaluation['replacement_days_se']**2)
        - 2 * 261**2 * net / duration**3 * funded['receipts_lifetime_covariance'])
    row.update(status='ranked', slot_year=value, slot_year_se=sqrt(max(0., variance)))
    return row


def rank(evaluations, funded, payout_cap=None):
    rows = [score_pair(e, f, acquisition_bound(e, len(evaluations)), payout_cap) for e in evaluations for f in funded]
    ranked = [r for r in rows if r['status'] == 'ranked']
    # Exact score ties favor lower acquisition cost, then smaller funded/eval
    # exposure. Statistical overlap is reported separately, not called certainty.
    best = max(ranked, key=lambda r: (r['slot_year'], -r['acquisition_cost'],
        -r['funded_micros'], -r['evaluation_micros'])) if ranked else None
    blocked = bool(not funded and any(unresolved_acquisition(e) for e in evaluations))
    unresolved_sizes = {e['evaluation_micros'] for e in evaluations if unresolved_acquisition(e)}
    for row in rows:
        if row['status'] == 'bounded_acquisition' and best and row['upper_bound'] < best['slot_year']:
            row.update(status='excluded', reason='Optimistic acquisition bound cannot beat the best complete pair; unknown funding time was not substituted.')
        elif row['status'] in ('bounded','bounded_acquisition'):
            blocked |= best is None or row['upper_bound'] >= best['slot_year']
        elif row['status'] == 'unavailable' and row['evaluation_micros'] in unresolved_sizes:
            blocked = True
    return rows, best, blocked


def _economics(value):
    from .native_analysis import training_economics
    return training_economics(*value)


def _refine_evaluation(value):
    from .native_analysis import evaluation_model, evaluation_diagnostics, training_economics
    train, previous, settings, block, max_micros, sample = value
    sim = evaluation_model(train, previous['evaluation_micros'], FINAL_SIMS, REFINEMENT_SEED,
                           block, settings, max_micros=max_micros)
    selected = dict(micros=previous['evaluation_micros'], simulations=FINAL_SIMS,
        passed=int(sum(sim['outcomes'] == 'passed')), evaluation_seed=REFINEMENT_SEED)
    selected.update(evaluation_diagnostics(sim))
    # Same size/source and seed-45 funding chains are already fully calibrated.
    result = training_economics(train, selected, settings, block, max_micros, sample, chain_stats=previous)
    result['screening_passed'] = previous.get('screening_passed', previous['passed'])
    result['screening_simulations'] = previous.get('screening_simulations', previous['simulations'])
    if previous['status'] != 'calibrated':
        result['funding_chain_failure_reason'] = previous.get('funding_chain_failure_reason', previous['reason'])
    return result


def select(train, settings, block, max_micros, rules, sample, progress):
    from .native_analysis import _evaluation_size, _funded_profile, is_lucid
    sizes = list(range(1, min(40 if is_lucid(settings) else 60, max_micros) + 1))
    funded_sizes = list(range(1, min(max(level[1] for level in rules.levels), max_micros) + 1))
    work = max(1, sum(map(len, train))) * SCREEN_SIMS
    progress('Joint sizing: evaluation pass profiles on training sessions')
    sweep = map_sweep(_evaluation_size, [(train, n, block, max_micros, settings) for n in sizes], work * len(sizes))
    progress('Joint sizing: 20,000 funding chains for each eligible evaluation size')
    evaluations = map_sweep(_economics, [(train, row, settings, block, max_micros, sample) for row in sweep], work * len(sizes))
    # Resolve uncertainty in the rare pass estimate before excluding a size.
    # A failed chain is not retried and its acquisition mean remains unknown.
    rare = [e for e in evaluations if unresolved_acquisition(e) and not e.get('evaluation_censored_paths', 0)]
    if rare:
        progress(f'Joint sizing: refining {len(rare)} unresolved acquisition probabilities on 20,000 training paths')
        updated = map_sweep(_refine_evaluation,
            [(train,e,settings,block,max_micros,sample) for e in rare],work * len(rare))
        refined = {e['evaluation_micros']: e for e in updated}
        evaluations = [refined.get(e['evaluation_micros'], e) for e in evaluations]
    profiles = []
    if any(e['status'] == 'calibrated' for e in evaluations):
        progress('Joint sizing: independent funded lifetime profiles on training sessions')
        profiles = map_sweep(_funded_profile,
            [(train, n, block, rules, max_micros, SCREEN_SIMS, 42) for n in funded_sizes], work * len(funded_sizes))
    payout_cap = float(sum(rules.ladder) * getattr(rules,'payout_share',1.))
    screening, best, blocked = rank(evaluations, profiles, payout_cap)
    refinements = []
    # Refine every component of a statistically close pair, then reconsider.
    # This includes a newly competitive unrefined pair after a winner changes.
    # All decisions use training only; seed 43/44 holdout is untouched here.
    while best:
        close = [r for r in rank(evaluations, profiles, payout_cap)[0] if r['status'] == 'ranked'
            and r['slot_year'] + 2 * (r['slot_year_se'] + best['slot_year_se']) >= best['slot_year']
            and not (r != best and r['slot_year'] == best['slot_year']
                     and r['slot_year_se'] == best['slot_year_se'] == 0)]
        eval_sizes = {r['evaluation_micros'] for r in close}
        fund_sizes = {r['funded_micros'] for r in close}
        to_eval = [e for e in evaluations if e['evaluation_micros'] in eval_sizes and e['simulations'] != FINAL_SIMS]
        to_fund = [f for f in profiles if f['micros'] in fund_sizes and f['sims'] != FINAL_SIMS]
        if not to_eval and not to_fund:break
        progress(f'Joint sizing: refining {len(to_eval)} evaluation and {len(to_fund)} funded contenders on 20,000 training paths')
        refined_e = map_sweep(_refine_evaluation,
            [(train, e, settings, block, max_micros, sample) for e in to_eval], work * len(to_eval)) if to_eval else []
        refined_f = map_sweep(_funded_profile,
            [(train, f['micros'], block, rules, max_micros, FINAL_SIMS, REFINEMENT_SEED) for f in to_fund], work * len(to_fund)) if to_fund else []
        emap = {e['evaluation_micros']: e for e in refined_e}
        fmap = {f['micros']: f for f in refined_f}
        evaluations = [emap.get(e['evaluation_micros'], e) for e in evaluations]
        profiles = [fmap.get(f['micros'], f) for f in profiles]
        refinements.append(dict(evaluation_sizes=sorted(emap), funded_sizes=sorted(fmap)))
        _, best, blocked = rank(evaluations, profiles, payout_cap)
    pairs, best, blocked = rank(evaluations, profiles, payout_cap)
    exclusions = []
    blockers = []
    for e in evaluations:
        if not unresolved_acquisition(e):continue
        subset = [r for r in pairs if r['evaluation_micros']==e['evaluation_micros']]
        evidence = dict(evaluation_micros=e['evaluation_micros'],passed=e['passed'],simulations=e['simulations'],
            screening_passed=e.get('screening_passed', e['passed']),
            calibration_reason=e.get('funding_chain_failure_reason', e['reason']),payout_cap=payout_cap,
            best_complete_slot_year=best['slot_year'] if best else None,
            **(acquisition_bound(e,len(evaluations)) or {}))
        evidence['upper_bound'] = max((r['upper_bound'] for r in subset if r['upper_bound'] is not None),default=None)
        (exclusions if subset and all(r['status']=='excluded' for r in subset) else blockers).append(evidence)
    if best and not blocked:
        status = 'selected'
        reason = None
    else:
        status = 'unavailable'
        reason = ('Joint sizing is unavailable: unresolved funding chains or funded lifetimes could change the winning pair.'
                  if blocked or profiles else 'No training evaluation passed. Joint sizing is unavailable.')
        if blockers:
            sizes_text=', '.join(str(e['evaluation_micros']) for e in blockers)
            reason=f'Joint sizing is unavailable: evaluation sizes {sizes_text} MNQ have unresolved acquisition times and cannot be excluded by their optimistic bounds.'
        if profiles and best is None:
            reason = 'Joint sizing is unavailable: no complete funded lifetime estimate; unresolved lifetimes are not treated as closed accounts.'
    selected = best if status == 'selected' else None
    # An evaluation-only diagnostic remains inspectable on unavailable reports;
    # it never supplies an invented funded selection or historical cash value.
    chosen = next(e for e in evaluations if e['evaluation_micros'] == selected['evaluation_micros']) if selected else max(evaluations, key=lambda e: e['pass_rate'])
    joint = dict(objective='long_run_annualized_net_per_slot', formula='261 * (expected_receipts - acquisition_cost) / (funded_days + acquisition_days)',
        status=status, reason=reason, selected=selected, pairs=pairs, screening_pairs=screening,
        evaluation_profiles=evaluations, funded_profiles=profiles, refinements=refinements,
        evaluation_range=sizes, funded_range=funded_sizes, screen_simulations=SCREEN_SIMS,
        refinement_simulations=FINAL_SIMS, refinement_seed=REFINEMENT_SEED, funding_chain_simulations=FINAL_SIMS,
        lifetime_horizon_weekdays=LIFETIME_HORIZON, selection_sample=sample,
        excluded_acquisition_candidates=exclusions,blocking_acquisition_candidates=blockers,
        acquisition_probability_refinements=[e['evaluation_micros'] for e in rare],
        acquisition_bound_confidence=.95,acquisition_payout_cap=payout_cap,
        uncertainty='Delta-method Monte Carlo standard errors conditional on the source sample; not future-performance confidence. Close training contenders are refined at seed 46.',
        tie_break='Highest score, then lower acquisition cost, smaller funded size, smaller evaluation size.',
        nonpositive=bool(selected and selected['slot_year'] <= 0),
        overlapping_pairs=sum(r['status'] == 'ranked' and selected is not None and
            r['slot_year'] + 2 * (r['slot_year_se'] + selected['slot_year_se']) >= selected['slot_year'] for r in pairs))
    return sweep, chosen, profiles, joint
