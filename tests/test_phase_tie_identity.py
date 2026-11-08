"""Nested exact ties cannot depend on opposite-phase administrative identity."""
from copy import deepcopy
from types import SimpleNamespace
from alphaquest.prop.funded_optimization import FundedConstraints, OBJECTIVE, rank_candidates
from alphaquest.prop.phase_search import stable_phase_policy_identity


def candidate(id, micros):
    return dict(candidate_id=id, status='estimated',
        manifest=dict(strategy=dict(id='same_signal', parameters={'period':20}, provenance='stable_code'),
            configuration=dict(source={'source_backtest_id':id*32}, micros=micros, profile={'phase':'funded'}),
            training_context_sha256='whole_parent_declaration'),
        metrics={OBJECTIVE:1500, 'account_breach_probability':.1, 'probability_first_payout':.7, 'p10_payouts':0},
        uncertainty={'mean_family_interval':[1300,1700]})


def test_nested_winner_stable_when_generated_source_context_ids_change():
    search = SimpleNamespace(constraints=FundedConstraints(), near_tie_cash=0)
    before = [candidate('a',3), candidate('z',5)]
    after = [candidate('z',3), candidate('a',5)]
    for row in after:
        row['manifest']['training_context_sha256'] = 'different_opposite_phase_settings'
        row['manifest']['strategy']['session_flattening'] = 'generated_window_metadata'
    def chosen(rows, nested):
        result = rank_candidates(deepcopy(rows), search,
            tie_key=(lambda row:stable_phase_policy_identity(row,'funded')) if nested else None)
        return next(row['manifest']['configuration']['micros'] for row in result['candidates'] if row['candidate_id']==result['winner'])
    assert chosen(before, True) == chosen(after, True)
    assert chosen(before, False) == 3 and chosen(after, False) == 5  # Legacy public presentation retained.
    assert stable_phase_policy_identity(before[0],'funded') == stable_phase_policy_identity(after[0],'funded')
    assert stable_phase_policy_identity(before[0],'funded') != stable_phase_policy_identity(before[1],'funded')
