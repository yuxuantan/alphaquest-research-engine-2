"""Predeclared admission of configuration regions from inner validation only.

This assessor has no dataset, backtest, prop-account or outer-test reader. The
orchestrator must construct bounded inner-validation evidence. An evidence label
is not itself proof of causal data construction. No candidate is ranked here.
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import math
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, field_validator, model_validator


CONTRACT_VERSION = 'inner-edge-qualification-v1'


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)


def _money(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError('Money must be a finite decimal amount, never boolean.')
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('Money must be a finite decimal amount.') from exc
    if not result.is_finite() or abs(result) > Decimal('1e15'):
        raise ValueError('Money must be finite and within 1e15 currency units.')
    return result


class QualificationSettings(_StrictModel):
    """Research-specific thresholds; defaults are examples, not universal tests.

    Money uses the candidate's recorded trade quantities and costs. Sessions
    include zero-trade sessions; per-trade stress is an ADDITIONAL round-trip cost.
    Predeclare required execution scenarios and relevant causal regimes to make
    absent assessments block admission. These names do not trigger a rerun here.
    """
    currency: Literal['USD'] = 'USD'
    quantity_basis: Literal['saved_source_contracts'] = 'saved_source_contracts'
    minimum_folds: StrictInt = Field(default=3, ge=2, le=1000)
    minimum_sessions: StrictInt = Field(default=30, ge=2, le=20000)
    minimum_trades: StrictInt = Field(default=30, ge=1, le=1000000)
    minimum_trades_per_fold: StrictInt = Field(default=5, ge=1, le=1000000)
    minimum_mean_session_net: Decimal = Decimal('0')
    minimum_positive_fold_fraction: float = Field(default=2 / 3, ge=0, le=1, strict=True)
    maximum_profit_concentration: float = Field(default=.6, gt=0, le=1, strict=True)
    additional_round_trip_cost: Decimal = Decimal('0')
    minimum_stressed_mean_session_net: Decimal = Decimal('0')
    minimum_neighbors: StrictInt = Field(default=1, ge=0, le=10000)
    minimum_neighbor_pass_fraction: float = Field(default=.5, ge=0, le=1, strict=True)
    bootstrap_replicates: StrictInt = Field(default=2000, ge=100, le=100000)
    bootstrap_block_sessions: StrictInt = Field(default=5, ge=1, le=1000)
    bootstrap_seed: StrictInt = Field(default=42, ge=0, lt=2**32)
    confidence_level: float = Field(default=.95, gt=.5, lt=1, strict=True)
    minimum_bootstrap_tail_samples: StrictInt = Field(default=5, ge=1, le=1000)
    multiplicity: Literal['bonferroni_declared_family'] = 'bonferroni_declared_family'
    required_scenarios: tuple[StrictStr, ...] = ()
    required_regimes: tuple[StrictStr, ...] = ()
    minimum_regime_sessions: StrictInt = Field(default=10, ge=2, le=20000)
    minimum_regime_trades: StrictInt = Field(default=10, ge=1, le=1000000)
    minimum_scenario_mean_session_net: Decimal = Decimal('0')
    minimum_regime_mean_session_net: Decimal = Decimal('0')

    @field_validator('minimum_mean_session_net', 'additional_round_trip_cost',
                     'minimum_stressed_mean_session_net', 'minimum_scenario_mean_session_net',
                     'minimum_regime_mean_session_net', mode='before')
    @classmethod
    def finite_money(cls, value):
        return _money(value)

    @model_validator(mode='after')
    def declared_requirements(self):
        if self.additional_round_trip_cost < 0:
            raise ValueError('Additional round-trip cost cannot be negative.')
        for names in (self.required_scenarios, self.required_regimes):
            if len(set(names)) != len(names) or any(not n.strip() or len(n) > 100 for n in names):
                raise ValueError('Required assessment names must be unique nonempty strings of at most 100 characters.')
        return self


class _Candidate(_StrictModel):
    id: StrictStr = Field(min_length=1, max_length=200)
    strategy_id: StrictStr = Field(min_length=1, max_length=200)
    parameters: dict

    @field_validator('parameters')
    @classmethod
    def scalar_parameters(cls, values):
        if any(not isinstance(k, str) or not k for k in values):
            raise ValueError('Parameter names must be nonempty strings.')
        for value in values.values():
            if value is not None and type(value) not in (str, int, float, bool):
                raise ValueError('Parameters must be JSON scalar values.')
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError('Parameters must be finite.')
        return values


class _Session(_StrictModel):
    session: StrictStr
    net_pnl: Decimal
    trade_count: StrictInt = Field(ge=0, le=1000000)

    @field_validator('session')
    @classmethod
    def canonical_date(cls, value):
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError('Session must be an ISO date YYYY-MM-DD.')
        return value

    @field_validator('net_pnl', mode='before')
    @classmethod
    def finite_net(cls, value):
        return _money(value)

    @model_validator(mode='after')
    def empty_session(self):
        if not self.trade_count and self.net_pnl != 0:
            raise ValueError('A zero-trade session must have zero completed-trade net P&L.')
        return self


class _Regime(_StrictModel):
    name: StrictStr = Field(min_length=1, max_length=100)
    observable_at_decision: StrictBool
    sessions: list[_Session]


class _Fold(_StrictModel):
    fold_index: StrictInt = Field(ge=0, le=10000)
    scope: Literal['inner_validation'] = 'inner_validation'
    sessions: list[_Session]
    scenarios: dict[str, list[_Session]] = Field(default_factory=dict)
    regimes: list[_Regime] = Field(default_factory=list)

    @model_validator(mode='after')
    def ordered_evidence(self):
        def dates(rows):
            result = [r.session for r in rows]
            if result != sorted(set(result)):
                raise ValueError('Session rows must be unique and chronological; evidence is never silently sorted.')
            return result
        base = dates(self.sessions)
        for name, rows in self.scenarios.items():
            if not name.strip() or dates(rows) != base:
                raise ValueError('Execution scenarios must retain exactly the baseline session dates, including no-trade sessions.')
        names = [r.name for r in self.regimes]
        if len(names) != len(set(names)):
            raise ValueError('Regime names must be unique within each fold.')
        counts = {r.session: r.trade_count for r in self.sessions}
        for regime in self.regimes:
            if not set(dates(regime.sessions)).issubset(base):
                raise ValueError('Regime sessions must lie within their inner fold.')
            if any(r.trade_count > counts[r.session] for r in regime.sessions):
                raise ValueError('Regime trade counts cannot exceed baseline session counts.')
        return self


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _bootstrap(folds, settings, family_size, key):
    """Stratified circular session blocks: do not cross an inner fold boundary."""
    alpha = (1 - settings.confidence_level) / family_size
    tail = alpha / 2
    if settings.bootstrap_replicates * tail + 1e-12 < settings.minimum_bootstrap_tail_samples:
        return None, 'bootstrap_tail_resolution'
    if any(len(f.sessions) < settings.bootstrap_block_sessions * 2 for f in folds):
        return None, 'too_few_sessions_for_blocks'
    seed = int.from_bytes(sha256((str(settings.bootstrap_seed) + key).encode()).digest()[:8], 'big')
    rng = np.random.default_rng(seed)
    sums = np.zeros(settings.bootstrap_replicates)
    count = sum(len(f.sessions) for f in folds)
    for fold in folds:
        values = np.asarray([float(s.net_pnl) for s in fold.sessions])
        blocks = math.ceil(len(values) / settings.bootstrap_block_sessions)
        # Chunking bounds temporary memory for large declared experiments.
        for first in range(0, settings.bootstrap_replicates, 256):
            last = min(first + 256, settings.bootstrap_replicates)
            starts = rng.integers(0, len(values), size=(last-first, blocks))
            indexes = (starts[..., None] + np.arange(settings.bootstrap_block_sessions)) % len(values)
            sums[first:last] += values[indexes.reshape(last-first, -1)[:, :len(values)]].sum(axis=1)
    means = sums / count
    bounds = np.quantile(means, [tail, 1-tail], method='linear').tolist()
    return dict(lower=bounds[0], upper=bounds[1], family_size=family_size,
                family_confidence_level=settings.confidence_level,
                nominal_candidate_confidence_level=1-alpha,
                bootstrap_replicates=settings.bootstrap_replicates,
                block_sessions=settings.bootstrap_block_sessions,
                unit='USD per observed inner-validation session',
                method='Within-fold circular session block percentile bootstrap; Bonferroni declared-family tail levels',
                limitations='Approximate historical resampling interval, not a guaranteed confidence bound. Assumes representative locally stationary sessions within folds; sparse tails, dependence beyond blocks, regime changes and searched procedures may invalidate coverage. Replicates do not add historical observations.'), None


def _neighbors(candidates):
    """Adjacent declared numeric grid values, differing along exactly one axis.

    Categorical choices, including booleans, define separate strata. Distances
    are never inferred between unrelated strategies or categorical settings.
    """
    result = {c.id: [] for c in candidates}
    levels = defaultdict(set)
    for c in candidates:
        for name, value in c.parameters.items():
            if type(value) in (int, float):
                levels[c.strategy_id, name].add(value)
    positions = {key: {value: index for index, value in enumerate(sorted(values))}
                 for key, values in levels.items()}
    lines = defaultdict(dict)
    for c in candidates:
        for name, value in c.parameters.items():
            if type(value) not in (int, float):
                continue
            others = _canonical({k: v for k, v in c.parameters.items() if k != name})
            line = lines[c.strategy_id, name, others]
            position = positions[c.strategy_id, name][value]
            # Equivalent numeric levels do not create a false neighborhood.
            line.setdefault(position, []).append(c.id)
    for line in lines.values():
        for position, left in line.items():
            right = line.get(position+1, [])
            for a in left:
                result[a].extend(right)
            for b in right:
                result[b].extend(left)
    return {key: sorted(value) for key, value in result.items()}


def qualify_candidates(candidates, evidence, settings):
    """Return every admitted/rejected/insufficient candidate, never a winner.

    candidates: [{id, strategy_id, parameters}]. evidence: {id: [{fold_index,
    sessions: [{session: ISO date, net_pnl, trade_count}], optional scope fixed to
    inner_validation, scenarios: {name: [session rows]}, regimes: [{name,
    observable_at_decision, sessions: [session rows]}]}]. Unknown fields reject.
    Missing candidate evidence produces INSUFFICIENT_EVIDENCE; unknown evidence
    IDs reject. Shared candidate fold calendars must match exactly; missing
    folds remain insufficient evidence, never a truncated passing result.
    """
    if not isinstance(settings, QualificationSettings):
        settings = QualificationSettings.model_validate(settings)
    if not isinstance(candidates, list) or not candidates or len(candidates) > 10000:
        raise ValueError('Declare 1–10,000 candidates; no candidate is silently dropped.')
    candidates = [_Candidate.model_validate(c) for c in candidates]
    ids = [c.id for c in candidates]
    if len(set(ids)) != len(ids):
        raise ValueError('Candidate IDs must be unique.')
    definitions = [_canonical(dict(strategy_id=c.strategy_id, parameters=c.parameters)) for c in candidates]
    if len(set(definitions)) != len(definitions):
        raise ValueError('Duplicate strategy configurations must be removed explicitly.')
    if not isinstance(evidence, dict) or set(evidence) - set(ids):
        raise ValueError('Evidence must map only declared candidate IDs to inner folds.')
    parsed, common = {}, {}
    for c in candidates:
        raw = evidence.get(c.id, [])
        if not isinstance(raw, list):
            raise ValueError('Candidate evidence must be a list of inner folds.')
        folds = [_Fold.model_validate(f) for f in raw]
        indexes = [f.fold_index for f in folds]
        if indexes != sorted(set(indexes)):
            raise ValueError('Inner fold indices must be unique and increasing.')
        all_dates = [s.session for f in folds for s in f.sessions]
        if all_dates != sorted(set(all_dates)):
            raise ValueError('Inner validation folds must be chronological and nonoverlapping.')
        for f in folds:
            days = [s.session for s in f.sessions]
            if f.fold_index in common and days != common[f.fold_index]:
                raise ValueError('Candidate inner folds must share the same session calendars, including no-trade sessions.')
            common[f.fold_index] = days
        parsed[c.id] = folds
    common_dates = [s for index in sorted(common) for s in common[index]]
    if common_dates != sorted(set(common_dates)):
        raise ValueError('Declared inner validation folds must be chronological and nonoverlapping.')
    if sum(len(f.sessions) for fs in parsed.values() for f in fs) > 2000000:
        raise ValueError('Qualification exceeds 2,000,000 candidate sessions; reduce the declared experiment.')
    neighbors = _neighbors(candidates)
    rows = []
    for c in sorted(candidates, key=lambda c: c.id):
        folds = parsed[c.id]
        sessions = [s for f in folds for s in f.sessions]
        net = sum((s.net_pnl for s in sessions), Decimal(0))
        trades = sum(s.trade_count for s in sessions)
        mean = net / len(sessions) if sessions else None
        stressed = (net-settings.additional_round_trip_cost*trades) / len(sessions) if sessions else None
        totals = [sum((s.net_pnl for s in f.sessions), Decimal(0)) for f in folds]
        positive = sum(p > 0 for p in totals) / len(folds) if folds else None
        gains = sum((max(p, Decimal(0)) for p in totals), Decimal(0))
        concentration = float(max(totals)/gains) if gains else None
        insufficient, failures = [], []
        if [f.fold_index for f in folds] != sorted(common): insufficient.append('missing_declared_inner_folds')
        if len(folds) < settings.minimum_folds: insufficient.append('too_few_inner_folds')
        if len(sessions) < settings.minimum_sessions: insufficient.append('too_few_validation_sessions')
        if trades < settings.minimum_trades: insufficient.append('too_few_validation_trades')
        if any(sum(s.trade_count for s in f.sessions) < settings.minimum_trades_per_fold for f in folds):
            insufficient.append('too_few_trades_in_an_inner_fold')
        interval, problem = _bootstrap(folds, settings, len(candidates), _canonical(c.model_dump())) if sessions else (None, 'no_inner_validation_evidence')
        if problem: insufficient.append(problem)
        if mean is not None and mean <= settings.minimum_mean_session_net: failures.append('mean_session_net_below_threshold')
        if interval is not None and interval['lower'] <= float(settings.minimum_mean_session_net):
            failures.append('uncertainty_lower_bound_below_threshold')
        if positive is not None and positive < settings.minimum_positive_fold_fraction: failures.append('too_few_profitable_inner_folds')
        if concentration is not None and concentration > settings.maximum_profit_concentration: failures.append('profits_concentrated_in_one_fold')
        if stressed is not None and stressed <= settings.minimum_stressed_mean_session_net: failures.append('additional_cost_stress_failed')
        scenario_results, regime_results = [], []
        for name in settings.required_scenarios:
            available = bool(folds) and all(name in f.scenarios for f in folds)
            subset = [s for f in folds for s in f.scenarios.get(name, [])]
            value = sum((s.net_pnl for s in subset), Decimal(0))/len(subset) if subset else None
            if not available: insufficient.append('missing_scenario:'+name)
            elif value is None or value <= settings.minimum_scenario_mean_session_net: failures.append('scenario_failed:'+name)
            scenario_results.append(dict(name=name, complete=available, mean_session_net=str(value) if value is not None else None))
        for name in settings.required_regimes:
            regimes = [next((r for r in f.regimes if r.name == name), None) for f in folds]
            available = bool(folds) and all(r is not None for r in regimes)
            subset = [s for r in regimes if r for s in r.sessions]
            count = sum(s.trade_count for s in subset)
            causal = available and all(r.observable_at_decision for r in regimes)
            enough = len(subset) >= settings.minimum_regime_sessions and count >= settings.minimum_regime_trades
            value = sum((s.net_pnl for s in subset), Decimal(0))/len(subset) if subset else None
            if not available: insufficient.append('missing_regime:'+name)
            elif not causal: insufficient.append('regime_not_observable_at_decision:'+name)
            elif not enough: insufficient.append('too_few_regime_observations:'+name)
            elif value <= settings.minimum_regime_mean_session_net: failures.append('regime_failed:'+name)
            regime_results.append(dict(name=name, complete=available, observable_at_decision=causal,
                sessions=len(subset), trades=count, mean_session_net=str(value) if value is not None else None))
        rows.append(dict(candidate_id=c.id, strategy_id=c.strategy_id, parameters=c.parameters,
            status='INSUFFICIENT_EVIDENCE' if insufficient else 'FAIL' if failures else 'PASS',
            reasons=[], insufficient_reasons=insufficient, failed_criteria=failures,
            metrics=dict(inner_folds=len(folds), validation_sessions=len(sessions), validation_trades=trades,
                net_pnl=str(net), mean_session_net=str(mean) if mean is not None else None,
                positive_fold_fraction=positive, profit_concentration=concentration,
                fold_net_pnl=[dict(fold_index=f.fold_index, net_pnl=str(p)) for f,p in zip(folds, totals)]),
            uncertainty=interval,
            execution_stress=dict(additional_round_trip_cost=str(settings.additional_round_trip_cost),
                stressed_mean_session_net=str(stressed) if stressed is not None else None,
                break_even_additional_round_trip_cost=str(net/trades) if trades else None,
                cost_basis='Additional USD per completed trade at saved quantity; baseline costs are already in net P&L.',
                scenarios=scenario_results), market_conditions=regime_results,
            parameter_stability={}, limitations=[
                'PASS means the saved research-specific criteria were met, not proof of a persistent edge or deployment readiness.',
                'Only supplied inner validation aggregates are assessed; bounded data access and causal feature construction must be enforced by the orchestrator.',
                'Bootstrap repetitions are computation, not additional independent trades or sessions; family correction does not account for undeclared earlier searches.',
                'Execution changes affecting signals, fills or stops require actual reruns; the additional cost stress changes cash only.',
                'Only predeclared required scenarios and regimes gate admission; other execution, market and strategy-complexity assessments are unverified.']))
    by_id = {r['candidate_id']: r for r in rows}
    # Freeze individual status first; neighbor membership cannot depend on order
    # or recursively promote a failing neighborhood into a passing region.
    individual = {r['candidate_id']: r['status'] for r in rows}
    for row in rows:
        nearby = neighbors[row['candidate_id']]
        passed = [id for id in nearby if individual[id] == 'PASS']
        unknown = [id for id in nearby if individual[id] == 'INSUFFICIENT_EVIDENCE']
        required = max(settings.minimum_neighbors, math.ceil(len(nearby)*settings.minimum_neighbor_pass_fraction))
        enough = len(passed) >= required
        if len(nearby) < settings.minimum_neighbors:
            row['insufficient_reasons'].append('too_few_parameter_neighbors')
        elif not enough:
            if len(passed)+len(unknown) >= required:
                row['insufficient_reasons'].append('neighbor_evidence_incomplete')
            else:
                row['failed_criteria'].append('unstable_parameter_region')
        base_mean = Decimal(row['metrics']['mean_session_net']) if row['metrics']['mean_session_net'] is not None else None
        row['parameter_stability'] = dict(neighbor_ids=nearby, individually_qualified_neighbors=passed,
            insufficient_neighbor_ids=unknown, required_passing_neighbors=required,
            neighbor_mean_changes=[dict(candidate_id=id,
                mean_session_net_change=str(Decimal(by_id[id]['metrics']['mean_session_net'])-base_mean)
                if base_mean is not None and by_id[id]['metrics']['mean_session_net'] is not None else None) for id in nearby],
            definition='One adjacent declared numeric grid coordinate; all other parameters equal within the same strategy. Categorical settings define separate strata.',
            region_criterion_met=enough and len(nearby) >= settings.minimum_neighbors)
        row['status'] = 'INSUFFICIENT_EVIDENCE' if row['insufficient_reasons'] else 'FAIL' if row['failed_criteria'] else 'PASS'
        row['reasons'] = row['insufficient_reasons'] + row['failed_criteria']
        if row['status'] == 'PASS': row['reasons'] = ['all_predeclared_criteria_met']
    snapshot = settings.model_dump(mode='json')
    evidence_snapshot = {key: [f.model_dump(mode='json') for f in folds] for key, folds in sorted(parsed.items())}
    candidate_snapshot = [c.model_dump(mode='json') for c in sorted(candidates, key=lambda c: c.id)]
    return dict(contract_version=CONTRACT_VERSION, settings=snapshot,
        input_sha256=sha256(_canonical(dict(candidates=candidate_snapshot, evidence=evidence_snapshot, settings=snapshot)).encode()).hexdigest(),
        candidates=rows, approved_ids=[r['candidate_id'] for r in rows if r['status'] == 'PASS'],
        selection='Admission of the complete qualifying set only; no ranking or winner.',
        multiplicity_family_size=len(candidates), historical_observation_count=len(common_dates))
