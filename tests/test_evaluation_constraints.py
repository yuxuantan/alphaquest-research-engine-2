"""Independent feasibility-before-dominance examples and strict boundaries."""
from copy import deepcopy
from dataclasses import asdict
import math

import pytest

from alphaquest.prop.evaluation_optimization import EvaluationConstraints, pareto_sort, parse_request
from test_evaluation_optimization import row, profile, calendar


def test_pass_constraint_removes_dominator_before_full_frontier():
    # A wins both objectives but violates the declared pass probability floor.
    # B must remain eligible, despite being dominated in the unconstrained set.
    rows = [row('A', 50, 2), row('B', 80, 4), row('C', 120, 3), row('D', 140, 8)]
    for r, probability in zip(rows, [.2, .8, .9, .9]):
        r['metrics']['pass_probability'] = probability
    assert pareto_sort(deepcopy(rows))['frontier'] == ['A']
    constrained = pareto_sort(deepcopy(rows), EvaluationConstraints(minimum_pass_probability=.75))
    assert constrained['frontier'] == ['B', 'C']
    assert constrained['unresolved_candidates'] == []
    assert len(constrained['candidates']) == 4
    rejected = constrained['candidates'][0]
    assert rejected['constraint_violations'] == ['pass_probability']
    assert rejected['dominance_status'] == 'constraint_excluded'
    assert rejected['pareto_rank'] is rejected['dominated'] is None


def test_inclusive_constraints_and_censored_candidate_stays_unresolved():
    rows = [row('A', 80, 4), row('A2', 80, 4), row('C', None, None, 'censored')]
    for r in rows:
        r['metrics']['pass_probability'] = .8
    result = pareto_sort(rows, EvaluationConstraints(80, 4, .8))
    assert result['frontier'] == ['A', 'A2']
    assert result['unresolved_candidates'] == ['C']
    assert result['winner'] is None


def test_empty_feasible_set_retains_every_result():
    result = pareto_sort([row('A', 50, 2)], EvaluationConstraints(maximum_cost_per_funded=49))
    assert result['frontier'] == [] and len(result['candidates']) == 1
    assert result['unresolved_candidates'] == []


@pytest.mark.parametrize('name,value', [(name, value)
    for name in ('maximum_cost_per_funded','maximum_expected_calendar_days','minimum_pass_probability')
    for value in (-1, True, '1', math.nan, math.inf)] + [('minimum_pass_probability', 1.01)])
def test_strict_constraint_boundaries(name, value):
    with pytest.raises(ValueError, match='constraint'):
        EvaluationConstraints(**{name:value})


def test_strict_request_roundtrip_and_opposite_phase_rejection():
    raw = dict(source_backtest_id='a'*32, calendar=asdict(calendar()),
        candidates=[dict(source=dict(source_backtest_id='a'*32), profile=asdict(profile()), micros=1)],
        constraints=dict(maximum_cost_per_funded=100, minimum_pass_probability=.5))
    search = parse_request(raw)
    assert parse_request(asdict(search)) == search
    raw['constraints']['minimum_p10_payouts'] = 100
    with pytest.raises(ValueError, match='Invalid evaluation-only'):
        parse_request(raw)
