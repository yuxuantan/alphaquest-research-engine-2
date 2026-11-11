"""IS Narrow searches conditioned on frozen Broad choices, with measured admission."""
from datetime import date, timedelta
from decimal import Decimal
import json
import math
from statistics import NormalDist
from uuid import UUID

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from .backtest_requests import ExecutionSettings, OptimizationRequest, ParameterRange
from .campaign_broad import candidate as broad_candidate, invoke
from .campaign_workflow import now
from .datasets import COLUMNS
from .market_equity import equity_rows
from .optimization import combinations, grid
from .optimization_cache import artifacts, digest, engine_identity
from .research import SplitDeclaration, dates_for, metadata
from .strategies.registry import get_strategy
from .worker_limits import DEFAULT_WORKERS, MAX_WORKERS
from .workflow_criteria import evaluate as broad_evaluate, policy, verified_screening

VERSION = 'is-narrow-v2'
REFINEMENT_VERSION = 'is-narrow-local-refinement-v1'
LEGACY_POLICY = dict(version='is-narrow-v1', neighbor_profit_fraction_gte='0.70', time_periods=4,
              profitable_periods_gte=3, latest_period_positive=True,
              best_complete_month_removed_net_gt='0', confidence_level='0.95',
              daily_equity_basis='last observed source-local bar close per calendar date, including open P&L',
              uncertainty_method='Bartlett HAC one-sided normal lower bound', hac_lag_observations=5,
              minimum_observed_days=100, multiple_search_correction='Bonferroni over all attempted Broad and Narrow trials, including failed/incomplete jobs',
              neighbors='all valid immediate axis neighbors, one coordinate step in either direction; Boolean endpoints adjacent',
              seed=None)
POLICY = dict(version=VERSION, minimum_valid_neighbors=2, neighbor_profit_numerator=2,
              neighbor_profit_denominator=3, time_periods=4, source_observations_each_period=True,
              best_complete_month_removed_net_gt='0', confidence_level='0.95',
              daily_equity_basis=LEGACY_POLICY['daily_equity_basis'],
              uncertainty_method=LEGACY_POLICY['uncertainty_method'], hac_lag_observations=5,
              minimum_observed_days=100, multiple_search_correction=LEGACY_POLICY['multiple_search_correction'],
              neighbors='all valid immediate ordered-numeric axis neighbors; categorical and Boolean axes excluded',
              advisory=['four_period_profitability', 'latest_period_profitability', 'drawdown_duration',
                        'drawdown_depth', 'search_adjusted_daily_net_lower_bound'], seed=None)


def period_boundaries(plan):
    start = date.fromisoformat(plan['is_start'])
    end = date.fromisoformat(plan['is_end']) + timedelta(days=1)
    span = (end - start).days
    return [start + timedelta(days=span * i // 4) for i in range(5)]


def parameter_key(parameters):
    return tuple((name, value if type(value) is bool else Decimal(str(value)))
                 for name, value in sorted(parameters.items()))


def same_parameter(left, right):
    return parameter_key({'value': left}) == parameter_key({'value': right})


def ordered_axes(fields, axes):
    definitions = {field['name']: field for field in fields}
    return {name for name, values in axes.items() if len(values) > 1 and
            definitions[name]['type'] in ('int', 'Decimal') and
            definitions[name].get('refinement_kind') != 'categorical'}


def refinement_options(fields, broad_axes):
    """Numeric Broad axes with a finer representable step; binary modes stay locked."""
    definitions = {field['name']: field for field in fields}
    options = {}
    for name, values in broad_axes.items():
        if len(values) < 2:
            continue
        kind = definitions[name]['type']
        if kind not in ('int', 'Decimal') or definitions[name].get('refinement_kind') == 'categorical':
            continue
        gaps = [Decimal(str(right)) - Decimal(str(left)) for left, right in zip(values, values[1:])]
        if not gaps or min(gaps) <= (1 if kind == 'int' else Decimal('1e-100')):
            continue
        options[name] = dict(type=kind, broad_min_step=str(min(gaps)))
    return options


def validate_refinement(fields, broad_axes, anchor, axes, opted):
    """Return Broad-varied fields that must remain equal to the chosen anchor."""
    varied = {name for name, values in broad_axes.items() if len(values) > 1}
    if len(opted) != len(set(opted)):
        raise ValueError('A Broad parameter can be opted into refinement only once.')
    if set(opted) - varied:
        raise ValueError('Only parameters varied in IS Broad can opt into Broad-value refinement.')
    options = refinement_options(fields, broad_axes)
    if set(opted) - options.keys():
        raise ValueError('This Broad parameter has no valid finer numeric neighborhood; keep it locked.')
    for name in varied - set(opted):
        if len(axes[name]) != 1 or not same_parameter(axes[name][0], anchor[name]):
            raise ValueError(f'{name} varied in IS Broad and must stay fixed at its confirmed value unless explicitly opted into refinement.')
    for name in opted:
        values = axes[name]
        if len(values) < 2 or not any(same_parameter(value, anchor[name]) for value in values):
            raise ValueError(f'{name}: the Narrow grid must vary and include the selected Broad value.')
        gaps = [Decimal(str(right)) - Decimal(str(left)) for left, right in zip(values, values[1:])]
        if min(gaps) >= Decimal(options[name]['broad_min_step']):
            raise ValueError(f'{name}: the Narrow step must be finer than its IS Broad step.')
        nearest = min(abs(Decimal(str(previous)) - Decimal(str(anchor[name])))
                      for previous in broad_axes[name] if not same_parameter(previous, anchor[name]))
        if any(2 * abs(Decimal(str(value)) - Decimal(str(anchor[name]))) >= nearest for value in values):
            raise ValueError(f'{name}: keep the Narrow range inside the selected Broad value’s local neighborhood.')
        if not any(not any(same_parameter(value, previous) for previous in broad_axes[name]) for value in values):
            raise ValueError(f'{name}: the Narrow grid must test a value absent from the IS Broad grid.')
    return sorted(varied - set(opted))


class NarrowGrid(BaseModel):
    model_config = ConfigDict(extra='forbid')
    broad_trial: StrictInt = Field(ge=1)
    parameter_ranges: dict[str, ParameterRange]
    refine_broad_parameters: list[StrictStr] = Field(default_factory=list)
    workers: StrictInt = Field(default=DEFAULT_WORKERS, ge=1, le=MAX_WORKERS)


class NarrowLaunch(NarrowGrid):
    revision: StrictInt = Field(ge=0)
    preview_token: StrictStr


class NarrowSelection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    broad_trial: StrictInt = Field(ge=1)
    job_id: UUID
    revision: StrictInt = Field(ge=0)
    trials: list[StrictInt] = Field(max_length=2)


class NarrowConfirm(BaseModel):
    model_config = ConfigDict(extra='forbid')
    broad_trial: StrictInt = Field(ge=1)
    job_id: UUID
    revision: StrictInt = Field(ge=0)


def branches(store, workflow_id, db=None):
    if db is None:
        with store.runs.connect() as db:
            return branches(store, workflow_id, db)
    broad = store.broad_state(workflow_id, db)
    chosen = broad.get('selection') or []
    result = []
    for selected in chosen:
        row = db.execute('SELECT payload FROM campaign_narrow_state WHERE workflow_id=? AND broad_trial=?',
                         (workflow_id, selected['trial'])).fetchone()
        state = json.loads(row[0]) if row else dict(broad_trial=selected['trial'], job_id=None, revision=0,
                                                   selected_trials=[], selection=[], confirmed_at_utc=None)
        raw = db.execute('SELECT payload FROM optimizations WHERE id=?', (state['job_id'],)).fetchone() if state['job_id'] else None
        state['status'] = ('passed' if state['confirmed_at_utc'] else
                           'review_required' if raw and json.loads(raw[0])['status'] == 'complete' else
                           json.loads(raw[0])['status'] if raw else 'ready')
        state['broad_selection'] = selected
        result.append(state)
    return result


def all_jobs_complete(store, workflow_id, db):
    states = branches(store, workflow_id, db)
    if not states or any(not s['job_id'] for s in states):
        return False
    for state in states:
        job = json.loads(db.execute('SELECT payload FROM optimizations WHERE id=?', (state['job_id'],)).fetchone()[0])
        count = db.execute('SELECT COUNT(*) FROM optimization_trials WHERE optimization_id=?', (job['id'],)).fetchone()[0]
        if job['status'] != 'complete' or count != job['total_trials'] or count != job['completed_trials']:
            return False
    return True


def family_size(db, workflow_id):
    jobs = db.execute('''SELECT payload FROM optimizations WHERE id IN
        (SELECT job_id FROM campaign_broad_jobs WHERE workflow_id=? UNION
         SELECT job_id FROM campaign_narrow_jobs WHERE workflow_id=?)''', (workflow_id, workflow_id)).fetchall()
    return sum(json.loads(row[0])['total_trials'] for row in jobs)


def prepare(request, workflow_id, body):
    store = request.app.state.campaign_workflows
    saved, _ = store.phase(workflow_id, 'is_narrow')
    selected = next((s for s in saved['broad']['selection'] if s['trial'] == body.broad_trial), None)
    if not selected:
        raise ValueError('Select one of the confirmed IS Broad configurations.')
    with store.runs.connect() as db:
        broad_candidate(store, workflow_id, saved['broad']['job_id'], body.broad_trial, db,
                        legacy=not saved['broad'].get('screening_policy'),
                        target_policy=saved['broad'].get('selection_policy') or saved['broad'].get('screening_policy'))
        current = next(s for s in branches(store, workflow_id, db) if s['broad_trial'] == body.broad_trial)
        if current['confirmed_at_utc'] or any(s['confirmed_at_utc'] for s in branches(store, workflow_id, db)):
            raise ValueError('A Narrow selection is confirmed; grids and choices are frozen.')
        broad_job = json.loads(db.execute('SELECT payload FROM optimizations WHERE id=?', (saved['broad']['job_id'],)).fetchone()[0])
    declared = saved['declaration']
    dataset = request.app.state.store.get(declared['dataset']['id'])
    if not dataset or dataset.get('columns') != COLUMNS or any(dataset.get(k) != declared['dataset'].get(k)
            for k in ('sha256', 'source_timezone', 'row_count', 'instrument_settings')):
        raise ValueError('The frozen native dataset or instrument settings are unavailable or changed.')
    definition = get_strategy(declared['strategy_id'])
    if definition.description()['source_sha256'] != declared['strategy_source_sha256']:
        raise ValueError('Strategy source changed; validate a new workflow.')
    axes, total = grid(definition, body.parameter_ranges)
    varied = [name for name, values in broad_job['axes'].items() if len(values) > 1]
    if not varied:
        raise ValueError('IS Broad must vary at least one parameter before a Narrow search.')
    fixed = validate_refinement(definition.description()['parameters'], broad_job['axes'],
                                selected['parameters'], axes, body.refine_broad_parameters)
    if total < 2:
        raise ValueError('Vary at least one remaining parameter so immediate neighbors can be assessed.')
    numeric = ordered_axes(definition.description()['parameters'], axes)
    if sum(min(2, len(axes[name]) - 1) for name in numeric) < POLICY['minimum_valid_neighbors']:
        raise ValueError('IS Narrow needs at least two distinct ordered-numeric neighbors for a candidate. Use at least three values on one numeric axis or vary two numeric axes.')
    for values in combinations(axes):
        definition.validate_source(definition.parameters(values), dataset)
    plan = declared['plan']
    split = dict(mode='dates', **{k: plan[k] for k in ('is_start', 'is_end', 'oos_start', 'oos_end')})
    resolved = request.app.state.research.resolve(request.app.state.store, dataset, declared['strategy_id'],
                                                   SplitDeclaration.model_validate(split))
    if resolved != plan:
        raise ValueError('The saved IS window no longer matches the source.')
    request_body = OptimizationRequest(dataset_id=dataset['id'], strategy_id=declared['strategy_id'],
        method='exhaustive', parameter_ranges=body.parameter_ranges, workers=body.workers,
        automatic_prop=False, reuse_results=True,
        execution_settings=ExecutionSettings.model_validate(declared['execution_settings']),
        sample_split=split, market_benchmark=declared['market_benchmark'])
    config = request_body.execution_settings.execution_config(dataset)
    token = digest(dict(workflow_identity=saved['identity'], broad_selection=selected,
        mechanics=saved['review']['result_identity'], request=request_body.model_dump(),
        refined_broad_parameters=body.refine_broad_parameters,
        refinement_policy=REFINEMENT_VERSION,
        engine=engine_identity(), broad_policy=policy(), narrow_policy=POLICY))
    return saved, dataset, definition, config, axes, total, request_body, token, current, fixed


def preview(request, workflow_id, body):
    *_, axes, total, request_body, token, state, fixed = prepare(request, workflow_id, body)
    return dict(total_trials=total, step_counts={k: len(v) for k, v in axes.items()},
                preview_token=token, revision=state['revision'], broad_trial=body.broad_trial,
                fixed_parameters=fixed, refined_parameters=body.refine_broad_parameters, policy=POLICY)


def launch(request, workflow_id, body):
    store = request.app.state.campaign_workflows
    saved, dataset, definition, config, axes, total, request_body, token, _, fixed = prepare(request, workflow_id, body)
    if token != body.preview_token:
        raise ValueError('The Narrow grid preview is stale. Calculate iterations again.')
    request.app.state.research.claim(saved['declaration']['plan'])
    with store.runs.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        states = branches(store, workflow_id, db)
        state = next(s for s in states if s['broad_trial'] == body.broad_trial)
        if any(s['confirmed_at_utc'] for s in states):
            raise ValueError('Narrow choices are frozen.')
        if state['job_id']:
            current = json.loads(db.execute('SELECT payload FROM optimizations WHERE id=?', (state['job_id'],)).fetchone()[0])
            if state.get('preview_token') == token and current['status'] in ('queued', 'running', 'complete'):
                return current, False, None
            if current['status'] in ('queued', 'running'):
                raise ValueError('This Broad configuration already has a running Narrow grid.')
            if current['status'] == 'complete' and current['research'].get('narrow_policy') == POLICY:
                raise ValueError('This Broad configuration already has a completed Narrow grid; saved results are immutable.')
        if state['revision'] != body.revision:
            raise ValueError('Narrow grid changed in another tab. Reload before launching.')
        research = metadata(saved['declaration']['plan'], workflow_id=workflow_id,
                            workflow_phase='is_narrow', broad_trial=body.broad_trial,
                            broad_selection_identity=digest(state['broad_selection']),
                            screening_policy=policy(), narrow_policy=POLICY,
                            refinement_policy=REFINEMENT_VERSION,
                            refined_broad_parameters=sorted(body.refine_broad_parameters),
                            broad_anchor_parameters=state['broad_selection']['parameters'],
                            period_boundaries=[d.isoformat() for d in period_boundaries(saved['declaration']['plan'])],
                            frozen_broad_parameters={name: state['broad_selection']['parameters'][name] for name in fixed})
        job = request.app.state.optimizations.create(request_body, dataset, definition, config, axes, total, research, connection=db)
        state = dict(broad_trial=body.broad_trial, job_id=job['id'], revision=state['revision']+1,
                     selected_trials=[], selection=[], confirmed_at_utc=None, preview_token=token,
                     broad_selection_identity=research['broad_selection_identity'], policy=POLICY,
                     refinement_policy=REFINEMENT_VERSION,
                     refined_broad_parameters=research['refined_broad_parameters'])
        db.execute('INSERT INTO campaign_narrow_jobs VALUES (?,?,?)', (job['id'], workflow_id, body.broad_trial))
        db.execute('INSERT INTO campaign_narrow_state VALUES (?,?,?) ON CONFLICT(workflow_id,broad_trial) DO UPDATE SET payload=excluded.payload',
                   (workflow_id, body.broad_trial, json.dumps(state)))
    return job, True, (definition, config, dates_for(saved['declaration']['plan']))


def daily_net(runs, report):
    descriptor = report.get('market_benchmark')
    if not descriptor:
        raise ValueError('Daily native equity evidence is unavailable; Narrow cannot qualify.')
    previous = None
    days = []
    for point in equity_rows(runs.root / report['id'], descriptor):
        equity = Decimal(str(point['strategy_equity']))
        if previous is None:
            previous = equity
            continue
        local_date = point.get('date')
        if not local_date:
            raise ValueError('Daily equity has no source-local date.')
        days.append((date.fromisoformat(local_date), equity - previous))
        previous = equity
    if not days or previous != Decimal(str(report['summary']['final_equity'])):
        raise ValueError('Daily equity does not reconcile to the saved native report.')
    if sum((value for _, value in days), Decimal(0)) != Decimal(str(report['summary']['total_net_pnl'])):
        raise ValueError('Daily net P&L does not reconcile to the saved native report.')
    return days


def confidence(days, family):
    """Deterministic five-lag Bartlett HAC bound with Bonferroni family correction."""
    if len(days) < POLICY['minimum_observed_days'] or family < 1:
        return None
    values = [float(net) for _, net in days]
    n = len(values)
    mean = math.fsum(values) / n
    centered = [v - mean for v in values]
    lag = POLICY['hac_lag_observations']
    variance = math.fsum(v * v for v in centered) / n
    for k in range(1, lag + 1):
        covariance = math.fsum(centered[i] * centered[i-k] for i in range(k, n)) / n
        variance += 2 * (1 - k / (lag + 1)) * covariance
    if not math.isfinite(variance) or variance < -1e-9:
        return None
    critical = NormalDist().inv_cdf(1 - 0.05 / family)
    lower = mean - critical * math.sqrt(max(0, variance) / n)
    return dict(mean_net_daily=mean, lower_bound=lower, critical_value=critical,
                observed_days=n, family_size=family, hac_lag_observations=lag)


def neighbor_check(row, all_rows, axes, runs=None, *, target_policy=LEGACY_POLICY, fields=None):
    if target_policy not in (LEGACY_POLICY, POLICY):
        raise ValueError('Unsupported IS Narrow admission policy.')
    if target_policy == POLICY and fields is None:
        raise ValueError('Saved strategy parameter metadata is required for ordered-numeric neighborhood screening.')
    included = set(axes) if target_policy == LEGACY_POLICY else ordered_axes(fields, axes)
    lookup = {parameter_key(r['parameters']): r for r in all_rows}
    good = total = 0
    for name, values in axes.items():
        if name not in included or len(values) < 2:
            continue
        current = row['parameters'][name]
        index = next((i for i, value in enumerate(values) if parameter_key({name:value}) == parameter_key({name:current})), None)
        if index is None:
            raise ValueError('Trial parameters do not match the saved Narrow grid.')
        for adjacent in (index - 1, index + 1):
            if 0 <= adjacent < len(values):
                params = dict(row['parameters'], **{name: values[adjacent]})
                neighbor = lookup.get(parameter_key(params))
                if neighbor is None:
                    raise ValueError('A predeclared immediate neighbor is missing from the completed grid.')
                if runs is not None:
                    native = runs.get(neighbor['run_id'])
                    if not native or native['run_metadata']['strategy']['parameters'] != neighbor['parameters']:
                        raise ValueError('A neighboring native report is unavailable or differs from its grid row.')
                    measured, stress = verified_screening(runs, native)
                    identity = digest([native, artifacts(runs.root, native), stress, artifacts(runs.root, stress)])
                    if (measured != neighbor.get('screening') or
                        Decimal(str(native['summary']['total_net_pnl'])) != Decimal(str(neighbor['metrics']['total_net_pnl'])) or
                        identity != neighbor.get('screening_evidence_identity')):
                        raise ValueError('A neighboring trial’s saved screening evidence changed.')
                total += 1
                good += Decimal(str(neighbor['metrics']['total_net_pnl'])) > 0
    minimum = 1 if target_policy == LEGACY_POLICY else target_policy['minimum_valid_neighbors']
    numerator, denominator = ((7, 10) if target_policy == LEGACY_POLICY else
                              (target_policy['neighbor_profit_numerator'], target_policy['neighbor_profit_denominator']))
    return dict(profitable=good, valid=total, fraction=good/total if total else None,
                passed=total >= minimum and good * denominator >= numerator * total)


def assessment(runs, row, all_rows, axes, family, plan, *, target_policy=POLICY,
               broad_policy=None, fields=None):
    if target_policy not in (LEGACY_POLICY, POLICY):
        raise ValueError('Unsupported IS Narrow admission policy.')
    report = runs.get(row['run_id'])
    if not report:
        raise ValueError('The native Narrow report is missing.')
    captured, stress = verified_screening(runs, report)
    if captured != row.get('screening') or report['run_metadata']['strategy']['parameters'] != row['parameters']:
        raise ValueError('The Narrow screening evidence differs from the saved trial.')
    if (Decimal(str(row['metrics']['total_net_pnl'])) != Decimal(str(report['summary']['total_net_pnl'])) or
        digest([report, artifacts(runs.root, report), stress, artifacts(runs.root, stress)]) != row.get('screening_evidence_identity')):
        raise ValueError('The Narrow report or its cost-stress artifacts changed after publication.')
    base = broad_evaluate(captured['metrics'], captured['closed_trades'], captured['total_net_pnl'],
                          broad_policy or (captured['policy'] if target_policy == LEGACY_POLICY else policy()))
    neighbors = neighbor_check(row, all_rows, axes, runs, target_policy=target_policy, fields=fields)
    days = daily_net(runs, report)
    boundaries = period_boundaries(plan)
    quarter_pnl = [sum((v for d, v in days if boundaries[i] <= d < boundaries[i+1]), Decimal(0)) for i in range(4)]
    quarter_pass = sum(v > 0 for v in quarter_pnl) >= 3 and quarter_pnl[-1] > 0
    complete = [Decimal(str(month['net_pnl'])) for month in captured['months'] if month['complete']]
    without_best = Decimal(str(captured['total_net_pnl'])) - max(complete) if complete else None
    bound = confidence(days, family)
    month_check = dict(id='month_concentration', label='Profit without best complete month',
                       passed=without_best is not None and without_best > 0,
                       actual=str(without_best) if without_best is not None else 'No complete month', required='> 0')
    if target_policy == LEGACY_POLICY:
        checks = [*base['checks'],
            dict(id='neighbors', label='Profitable immediate neighbors', passed=neighbors['passed'],
                 actual=f"{neighbors['profitable']} / {neighbors['valid']}", required='>= 70% of valid immediate neighbors'),
            dict(id='time_stability', label='Four-period stability', passed=quarter_pass,
                 actual=', '.join(str(v) for v in quarter_pnl), required='At least 3 positive, including most recent'),
            month_check,
            dict(id='search_adjusted_bound', label='Search-adjusted daily net lower bound',
                 passed=bound is not None and bound['lower_bound'] > 0,
                 actual=f"{bound['lower_bound']:.4f} CU/day" if bound else 'Insufficient daily evidence',
                 required=f"95% lower bound > 0, HAC lag 5, Bonferroni family of {family} attempted trials")]
        return dict(policy=LEGACY_POLICY, qualifies=all(c['passed'] for c in checks), checks=checks,
                    neighbors=neighbors, quarter_boundaries=[d.isoformat() for d in boundaries],
                    quarter_net_pnl=[str(v) for v in quarter_pnl], net_without_best_month=str(without_best) if without_best is not None else None,
                    confidence=bound, family_size=family)
    observed = [sum(1 for day, _ in days if boundaries[i] <= day < boundaries[i+1]) for i in range(4)]
    checks = [*base['checks'],
        dict(id='period_coverage', label='Observed dates in every IS period', passed=all(observed),
             actual=', '.join(str(value) for value in observed), required='At least one observed source-local date in each of four periods'),
        dict(id='neighbors', label='Profitable ordered-numeric neighbors', passed=neighbors['passed'],
             actual=f"{neighbors['profitable']} / {neighbors['valid']}", required='At least two valid neighbors and at least two-thirds profitable'),
        month_check]
    observations = [
        dict(id='time_stability', label='Four-period net P&L', actual=', '.join(str(value) for value in quarter_pnl),
             context=f"{sum(value > 0 for value in quarter_pnl)} / 4 positive; latest {'positive' if quarter_pnl[-1] > 0 else 'nonpositive'}"),
        dict(id='drawdown_duration', label='Longest mark-to-market drawdown',
             actual=f"{captured['metrics']['is_longest_dd_pct']}% of IS"),
        dict(id='drawdown_depth', label='Maximum mark-to-market drawdown',
             actual=f"{captured['metrics']['is_mtm_max_drawdown']} CU"),
        dict(id='search_adjusted_bound', label='Search-adjusted daily net lower bound',
             actual=f"{bound['lower_bound']:.4f} CU/day" if bound else 'Insufficient daily evidence',
             context=f"95% one-sided; HAC lag 5; Bonferroni family of {family} attempted trials")]
    return dict(policy=POLICY, qualifies=all(check['passed'] for check in checks), checks=checks,
                observations=observations, neighbors=neighbors,
                quarter_boundaries=[d.isoformat() for d in boundaries], period_observed_dates=observed,
                quarter_net_pnl=[str(v) for v in quarter_pnl], net_without_best_month=str(without_best) if without_best is not None else None,
                confidence=bound, family_size=family)


def context(request, workflow_id, broad_trial):
    store = request.app.state.campaign_workflows
    saved, _ = store.phase(workflow_id, 'is_narrow')
    state = next((s for s in branches(store, workflow_id) if s['broad_trial'] == broad_trial), None)
    if not state:
        raise ValueError('Choose a confirmed IS Broad configuration.')
    job = request.app.state.optimizations.get(state['job_id']) if state['job_id'] else None
    return saved, state, job


def results(request, workflow_id, broad_trial, sort, direction, offset, limit):
    saved, state, job = context(request, workflow_id, broad_trial)
    if not job:
        return dict(items=[], total=0, offset=offset, limit=limit, family_size=0)
    page = request.app.state.optimizations.page(job, sort, direction, offset, limit, 0)
    with request.app.state.runs.connect() as db:
        full = all_jobs_complete(request.app.state.campaign_workflows, workflow_id, db)
        family = family_size(db, workflow_id)
        all_rows = [json.loads(r[0]) for r in db.execute('SELECT payload FROM optimization_trials WHERE optimization_id=?', (job['id'],))]
    source_policy = job['research'].get('narrow_policy')
    if source_policy not in (LEGACY_POLICY, POLICY) or state.get('policy') != source_policy:
        raise ValueError('Saved IS Narrow policy differs from its optimizer job.')
    target = state.get('selection_policy') or (source_policy if state['confirmed_at_utc'] else POLICY)
    for row in page['items']:
        if job['status'] == 'complete':
            try:
                row['admission'] = assessment(request.app.state.runs, row, all_rows, job['axes'], family,
                                              saved['declaration']['plan'], target_policy=target,
                                              fields=job['strategy']['parameters'])
                row['admission']['provisional'] = not full
                row['qualifies'] = full and row['admission']['qualifies'] and not row.get('backtest_deleted', False)
            except (ValueError, OSError, KeyError, ArithmeticError) as exc:
                row['admission'] = dict(qualifies=False, checks=[], error=str(exc))
                row['qualifies'] = False
        else:
            row['admission'] = dict(qualifies=False, checks=[], error='Wait for this Narrow grid to finish before screening.')
            row['qualifies'] = False
        row['selected'] = row['trial'] in state['selected_trials']
        row['selectable'] = row['qualifies'] and not state['confirmed_at_utc']
    return dict(page, family_size=family, all_branches_complete=full,
                source_policy=source_policy, selection_policy=target)


def chosen_candidate(store, workflow_id, state, trial, db, family):
    row_data = db.execute('SELECT payload FROM optimization_trials WHERE optimization_id=? AND trial=?', (state['job_id'], trial)).fetchone()
    if not row_data:
        raise ValueError('This trial is not in the selected Narrow grid.')
    row = json.loads(row_data[0])
    all_rows = [json.loads(r[0]) for r in db.execute('SELECT payload FROM optimization_trials WHERE optimization_id=?', (state['job_id'],))]
    job = json.loads(db.execute('SELECT payload FROM optimizations WHERE id=?', (state['job_id'],)).fetchone()[0])
    saved = store.raw(workflow_id, db)
    report = store.runs.get(row['run_id'])
    if not report or row.get('backtest_deleted'):
        raise ValueError('The selected native Narrow report is unavailable.')
    meta = report['run_metadata']
    research = job['research']
    if (meta['strategy']['parameters'] != row['parameters'] or meta['strategy']['id'] != saved['declaration']['strategy_id']
        or meta['strategy']['source_sha256'] != saved['declaration']['strategy_source_sha256']
        or meta['research'].get('workflow_id') != workflow_id or meta['research'].get('workflow_phase') != 'is_narrow'
        or meta['research'].get('broad_trial') != state['broad_trial'] or meta['research'].get('phase') != 'is'
        or meta['research'].get('narrow_policy') != research.get('narrow_policy')
        or meta['research'].get('plan') != saved['declaration']['plan']
        or meta['research'].get('period_boundaries') != [d.isoformat() for d in period_boundaries(saved['declaration']['plan'])]
        or meta['research'].get('broad_selection_identity') != state['broad_selection_identity']
        or report['execution_settings'] != saved['declaration']['execution_settings']
        or any(meta['dataset'][k] != saved['declaration']['dataset'][k] for k in ('id', 'sha256', 'source_timezone'))):
        raise ValueError('Narrow report does not match the frozen source, Broad selection or IS execution settings.')
    if state.get('refinement_policy') or research.get('refinement_policy'):
        anchor = state['broad_selection']['parameters']
        refined = research.get('refined_broad_parameters', [])
        broad_id = store.broad_state(workflow_id, db)['job_id']
        broad = json.loads(db.execute('SELECT payload FROM optimizations WHERE id=?', (broad_id,)).fetchone()[0])
        validate_refinement(get_strategy(saved['declaration']['strategy_id']).description()['parameters'],
                            broad['axes'], anchor, job['axes'], refined)
        expected_fixed = {name: anchor[name] for name, values in broad['axes'].items() if len(values) > 1 and name not in refined}
        if (research.get('refinement_policy') != REFINEMENT_VERSION or state.get('refinement_policy') != REFINEMENT_VERSION
            or refined != state.get('refined_broad_parameters')
            or research.get('broad_anchor_parameters') != anchor or research.get('frozen_broad_parameters') != expected_fixed
            or any(meta['research'].get(key) != research.get(key) for key in
                   ('refinement_policy', 'refined_broad_parameters', 'broad_anchor_parameters', 'frozen_broad_parameters'))):
            raise ValueError('Narrow refinement provenance does not match the selected Broad configuration.')
    for name, value in meta['research']['frozen_broad_parameters'].items():
        if row['parameters'][name] != value:
            raise ValueError('A frozen Broad parameter changed in the Narrow report.')
    target = state.get('selection_policy') or (state['policy'] if state['confirmed_at_utc'] else POLICY)
    admission = assessment(store.runs, row, all_rows, job['axes'], family, saved['declaration']['plan'],
                           target_policy=target, fields=job['strategy']['parameters'])
    if not admission['qualifies']:
        raise ValueError('Only configurations passing all IS Narrow criteria may advance.')
    _, stress = verified_screening(store.runs, report)
    identity = digest([report, artifacts(store.runs.root, report), stress, artifacts(store.runs.root, stress), admission])
    return dict(broad_trial=state['broad_trial'], trial=trial, run_id=row['run_id'], parameters=row['parameters'],
                total_net_pnl=row['metrics']['total_net_pnl'], report_identity=identity, admission=admission)


def save_selection(request, workflow_id, body, confirm=False):
    store = request.app.state.campaign_workflows
    store.phase(workflow_id, 'is_narrow')
    with store.runs.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        states = branches(store, workflow_id, db)
        state = next((s for s in states if s['broad_trial'] == body.broad_trial), None)
        if not state:
            raise ValueError('Unknown confirmed Broad configuration.')
        if state['confirmed_at_utc']:
            raise ValueError('This Broad configuration’s Narrow choices are already confirmed and locked.')
        if state['revision'] != body.revision or state['job_id'] != body.job_id.hex:
            raise ValueError('Narrow selection changed. Reload before saving.')
        if not all_jobs_complete(store, workflow_id, db):
            raise ValueError('Complete the Narrow grid for every selected Broad configuration first.')
        job = json.loads(db.execute('SELECT payload FROM optimizations WHERE id=?', (state['job_id'],)).fetchone()[0])
        source_policy = job['research'].get('narrow_policy')
        if source_policy not in (LEGACY_POLICY, POLICY) or state.get('policy') != source_policy:
            raise ValueError('Saved Narrow policy differs from its optimizer job.')
        if source_policy == POLICY and job['engine_identity'] != engine_identity():
            raise ValueError('Narrow calculation code changed; the current-policy grid cannot be confirmed.')
        family = family_size(db, workflow_id)
        trials = state['selected_trials'] if confirm else body.trials
        if len(trials) != len(set(trials)) or len(trials) > 2 or (confirm and not trials):
            raise ValueError('Choose one or two distinct eligible Narrow configurations.')
        selected = [chosen_candidate(store, workflow_id, state, trial, db, family) for trial in trials]
        if len({digest(s['parameters']) for s in selected}) != len(selected):
            raise ValueError('Selected Narrow parameter configurations must be distinct.')
        state.update(selected_trials=trials, revision=state['revision']+1, selection_policy=POLICY)
        if confirm:
            state.update(selection=selected, confirmed_at_utc=now(), family_size=family,
                         engine_identity=job['engine_identity'])
        for field in ('status', 'broad_selection'):
            state.pop(field, None)
        db.execute('UPDATE campaign_narrow_state SET payload=? WHERE workflow_id=? AND broad_trial=?',
                   (json.dumps(state), workflow_id, body.broad_trial))
    return next(s for s in branches(store, workflow_id) if s['broad_trial'] == body.broad_trial)


def validate_frozen(store, workflow_id, states):
    with store.runs.connect() as db:
        if not states or not all(s['confirmed_at_utc'] and 1 <= len(s['selection']) <= 2 for s in states):
            raise ValueError('Confirm one or two eligible Narrow configurations for each Broad selection.')
        if not all_jobs_complete(store, workflow_id, db):
            raise ValueError('A Narrow optimization is incomplete.')
        family = family_size(db, workflow_id)
        for state in states:
            if family != state['family_size']:
                raise ValueError('The attempted-search family changed after Narrow confirmation.')
            for frozen in state['selection']:
                if chosen_candidate(store, workflow_id, state, frozen['trial'], db, family) != frozen:
                    raise ValueError('A frozen Narrow report or admission changed; OOS is blocked.')


router = APIRouter()


@router.get('/api/campaign-workflows/{workflow_id}/narrow')
async def detail(workflow_id: UUID, request: Request, broad_trial: int = Query(..., ge=1)):
    saved, state, job = await invoke(context, request, workflow_id.hex, broad_trial)
    with request.app.state.runs.connect() as db:
        complete = all_jobs_complete(request.app.state.campaign_workflows, workflow_id.hex, db)
        family = family_size(db, workflow_id.hex)
        broad_job = json.loads(db.execute('SELECT payload FROM optimizations WHERE id=?', (saved['broad']['job_id'],)).fetchone()[0])
    strategy=get_strategy(saved['declaration']['strategy_id']).description()
    return dict(state=state, job=job, branches=branches(request.app.state.campaign_workflows, workflow_id.hex),
                strategy=strategy,
                fixed_parameters=[k for k, axis in broad_job['axes'].items() if len(axis) > 1],
                refinable_parameters=refinement_options(strategy['parameters'], broad_job['axes']),
                max_workers=MAX_WORKERS, default_workers=DEFAULT_WORKERS,
                policy=POLICY, all_branches_complete=complete, family_size=family)


@router.post('/api/campaign-workflows/{workflow_id}/narrow/preview')
async def preview_grid(workflow_id: UUID, body: NarrowGrid, request: Request):
    return await invoke(preview, request, workflow_id.hex, body)


@router.post('/api/campaign-workflows/{workflow_id}/narrow/run', status_code=202)
async def run_grid(workflow_id: UUID, body: NarrowLaunch, request: Request):
    job, fresh, execution = await invoke(launch, request, workflow_id.hex, body)
    if fresh:
        definition, config, dates = execution
        request.app.state.optimizations.executor.submit(request.app.state.optimizations.run, job,
                                                         request.app.state.store, definition, config, dates)
    return job


@router.get('/api/campaign-workflows/{workflow_id}/narrow/results')
async def page(workflow_id: UUID, request: Request, broad_trial: int = Query(..., ge=1),
               sort: str = 'trial', direction: str = 'asc', offset: int = Query(0, ge=0),
               limit: int = Query(50, ge=1, le=1000)):
    return await invoke(results, request, workflow_id.hex, broad_trial, sort, direction, offset, limit)


@router.patch('/api/campaign-workflows/{workflow_id}/narrow/selection')
async def select(workflow_id: UUID, body: NarrowSelection, request: Request):
    return await invoke(save_selection, request, workflow_id.hex, body)


@router.post('/api/campaign-workflows/{workflow_id}/narrow/confirm')
async def confirm(workflow_id: UUID, body: NarrowConfirm, request: Request):
    return await invoke(save_selection, request, workflow_id.hex, body, True)


@router.get('/api/campaign-workflows/{workflow_id}/narrow/download')
async def download(workflow_id: UUID, request: Request, broad_trial: int = Query(..., ge=1)):
    saved, state, job = await invoke(context, request, workflow_id.hex, broad_trial)
    if state['confirmed_at_utc']:
        await invoke(validate_frozen, request.app.state.campaign_workflows, workflow_id.hex,
                     branches(request.app.state.campaign_workflows, workflow_id.hex))
    return Response(json.dumps(dict(workflow_id=workflow_id.hex, declaration=saved['declaration'],
                                    policy=POLICY, state=state, job=job), indent=2),
                    media_type='application/json', headers={'Content-Disposition':f'attachment; filename="is-narrow-{workflow_id.hex}-{broad_trial}.json"'})
