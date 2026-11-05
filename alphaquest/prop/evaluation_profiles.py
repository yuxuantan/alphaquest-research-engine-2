"""Evaluation-only orchestration over the existing provider kernels."""
import numpy as np

from .phase_profiles import (
    CONTRACT_VERSION, Censoring, EvaluationProfile, EvaluationProfileResult,
    EvaluationSamplingConfig, ResearchPeriod, SavedTradeSource, SimulationConfig,
    SourceCosts, prepare_phase_source, provenance, verify_phase_source,
)


def simulate_evaluation_profile(
    runs, source: SavedTradeSource, profile: EvaluationProfile, micros: int,
    simulation: SimulationConfig = SimulationConfig(),
    period: ResearchPeriod | None = None,
    sampling: EvaluationSamplingConfig = EvaluationSamplingConfig(),
    costs: SourceCosts = SourceCosts(),
) -> EvaluationProfileResult:
    """Evaluate one saved source/size, stopping at acquisition; never run funded.

    Cost keeps the legacy fee/pass-probability estimator. Replacement duration
    keeps the retained-block repeated-attempt estimator and activation weekday.
    A failed chain guard leaves timing unavailable, never a completed-path mean.
    """
    from .native_analysis import evaluation_model, evaluation_diagnostics, is_lucid, wilson
    if not isinstance(profile, EvaluationProfile):
        raise ValueError('Evaluation simulation requires an EvaluationProfile.')
    if not isinstance(sampling, EvaluationSamplingConfig):
        raise ValueError('Evaluation simulation requires EvaluationSamplingConfig.')
    if sampling.computational_horizon_weekdays is not None and profile.profile_id != 'lucidflex-50k':
        raise ValueError('Apex has a fixed 21-weekday provider deadline; no computational override is supported.')
    snapshot, days, settings = prepare_phase_source(runs, source, profile, micros, simulation, period, costs)

    def runner(*args, **kwargs):
        if sampling.computational_horizon_weekdays is not None:
            kwargs['deadline'] = sampling.computational_horizon_weekdays
        return evaluation_model(*args, **kwargs)

    sim = runner(days, micros, simulation.simulations, simulation.seed,
                 sampling.block_weekdays, settings, max_micros=simulation.max_micros)
    outcomes = sim['outcomes']
    passed = int(sum(outcomes == 'passed'))
    diagnostics = evaluation_diagnostics(sim)
    selected = dict(micros=micros, passed=passed, simulations=simulation.simulations,
                    evaluation_seed=simulation.seed, **{k:v for k,v in diagnostics.items() if k != 'simulations'})
    acquisition = acquisition_economics(days, selected, settings, sampling.block_weekdays,
        simulation.max_micros, [snapshot['profile_research_period'][key] for key in ('first_session', 'last_session')],
        chain_simulations=sampling.chain_simulations, chain_seed=sampling.chain_seed, evaluation_runner=runner)
    # Legacy wording/keys remain untouched in the compatibility entry point.
    acquisition['source'] = 'Requested single evaluation source and research period; no funded simulation or selection'
    if not passed:
        acquisition['reason'] = 'No sampled evaluation passed; acquisition cost and replacement time remain unresolved.'
    computational_censored = int(sum(outcomes == 'timeout')) if is_lucid(settings) else 0
    if computational_censored and not passed:
        acquisition['reason'] = 'Evaluation paths remain computationally censored; acquisition cost and timing are unavailable.'
    chain_status = ('resolved' if acquisition['status'] == 'calibrated' else
                    'censored' if acquisition['funding_chain_simulations'] == 0 and passed and not computational_censored else 'not_run')
    status = 'censored' if computational_censored or chain_status == 'censored' else ('resolved' if passed else 'unresolved')
    evaluation = dict(simulations=simulation.simulations, passed=passed,
        outcome_counts={str(key):int(sum(outcomes == key)) for key in np.unique(outcomes)},
        pass_rate=passed / simulation.simulations, pass_rate_ci=wilson(passed, simulation.simulations),
        pass_probability_bounds=[passed / simulation.simulations,
                                 (passed + computational_censored) / simulation.simulations],
        pass_rate_estimand='Observed pass fraction through the attempt cutoff; censored paths remain unresolved for eventual pass probability',
        median_weekdays_to_pass_conditional=float(np.median(sim['days'][outcomes == 'passed'])) if passed else None,
        provider_deadline_weekdays=None if is_lucid(settings) else 21,
        expired_paths=0 if is_lucid(settings) else int(sum(outcomes == 'timeout')),
        **{k:v for k,v in diagnostics.items() if k != 'simulations'})
    verify_phase_source(runs, source, snapshot)
    return EvaluationProfileResult(CONTRACT_VERSION, evaluation, acquisition,
        outcomes.tolist(), sim['days'].tolist(),
        Censoring(status, computational_censored, acquisition.get('reason'), chain_status,
                  0 if chain_status == 'resolved' else None),
        provenance('evaluation', snapshot, profile, micros, simulation, sampling,
            acquisition_cost_estimand='evaluation fee / single-attempt pass probability + activation fee; legacy Monte Carlo delta-method SE',
            replacement_duration_estimand='Repeated funding chain trading weekdays including existing activation delay; no calendar conversion',
            chain_guard='10,000 attempts; provider-specific computational horizon; aborted chains return no per-path censoring count',
            block_continuity='An unfinished circular block is retained across evaluation retries',
            selection='None; one requested source, profile and size'))


def acquisition_economics(train, selected, settings, block, max_micros, sample, chain_stats=None, *, chain_simulations=20000, chain_seed=45, evaluation_runner=None):
    """Freeze acquisition inputs from training only, before holdout is touched."""
    from .native_analysis import evaluation_model, evaluation_diagnostics, is_lucid, wilson
    runner = evaluation_runner or evaluation_model
    probability=selected['passed']/selected['simulations']
    result=dict(method='training_simulation',status='unavailable',sample=sample,
                evaluation_micros=selected['micros'],passed=selected['passed'],
                screening_passed=selected['passed'],screening_simulations=selected['simulations'],
                evaluation_censored_paths=int(selected.get('censored_paths',0)),
                simulations=selected['simulations'],pass_rate=probability,
                pass_rate_ci=wilson(selected['passed'],selected['simulations']),
                evaluation_seed=selected.get('evaluation_seed',42),funding_chain_seed=chain_seed,funding_chain_simulations=0,requested_funding_chain_simulations=chain_simulations,
                evaluation_price=float(settings['EVAL_PRICE']),activation_fee=float(settings['ACTIVATION_FEE']),
                activation_days=0 if is_lucid(settings) else 1,cost_per_funded=None,replacement_days=None,
                cost_se=None,replacement_days_se=None,
                source='Training joint sizing and repeated funding chains only; frozen before all holdout simulations')
    if not selected['passed']:
        result['reason']='No training evaluation passed. Acquisition cost and replacement time cannot be calibrated; funded sizing is unavailable.'
        return result
    if selected.get('censored_paths',0):
        result['reason']='Training evaluation paths remain censored; acquisition probability and timing are unavailable.'
        return result
    result.update(cost_per_funded=float(settings['EVAL_PRICE'])/probability+float(settings['ACTIVATION_FEE']),
                  evaluations_per_funded=1/probability,
                  cost_se=float(settings['EVAL_PRICE'])*np.sqrt(probability*(1-probability)/selected['simulations'])/probability**2)
    if chain_stats is not None:
        if chain_stats['status']=='calibrated':
            for key in ('status','funding_chain_simulations','replacement_days','replacement_days_median','replacement_days_se','funding_chain_diagnostics'):
                if key in chain_stats:result[key]=chain_stats[key]
        else:result['reason']=chain_stats['reason']
        return result
    try:
        chain=runner(train,selected['micros'],chain_simulations,chain_seed,block,settings,chain=True,max_micros=max_micros)
    except ValueError as exc:
        if not str(exc).startswith(('No pass within the 10,000-attempt funding-time bound','LucidFlex funding chain is censored')):raise
        result['reason']='Training funding time is unavailable: '+str(exc)
        return result
    result.update(status='calibrated',funding_chain_simulations=chain_simulations,replacement_days=float(chain['days'].mean()),
                  replacement_days_median=float(np.median(chain['days'])),
                  replacement_days_se=float(chain['days'].std(ddof=1)/np.sqrt(len(chain['days']))))
    if is_lucid(settings):result['funding_chain_diagnostics']=evaluation_diagnostics(chain)
    return result

