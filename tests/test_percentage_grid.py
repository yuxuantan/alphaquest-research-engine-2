from decimal import Decimal
import pytest
from alphaquest.prop.sizing_search import PercentageGrid,axis,selection_value


def grid(**extra):return PercentageGrid(minimum='.1',maximum='.3',step='.1',maximum_contracts=40,**extra)


def test_exact_grid_policy_family_and_role_separate_from_native_quantity_cap():
 g=grid();assert g.values()==['0.1','0.2','0.3']
 assert g==PercentageGrid(minimum='0.10',maximum='0.30',step='0.10',maximum_contracts=40)
 policies=g.policies(dict(tick_size='.25',point_value='2',commission_per_contract_per_side='.5'))
 assert len(policies)==3 and all(p.initial_configured_capital=='50000' for p in policies)
 from dataclasses import asdict
 config=dict(micros=40,sizing=asdict(policies[1]));a=axis(config)
 assert a['risk_percent']=='0.2' and a['native_user_cap_contracts']==40 and 'contracts' not in a
 assert selection_value(config)==Decimal('.2')
 assert selection_value(dict(micros=3,sizing=None))==3


@pytest.mark.parametrize('changes',[dict(minimum='0'),dict(step='0'),dict(maximum='.35'),dict(minimum='.4'),dict(minimum='NaN'),dict(step='.001'),dict(maximum_contracts=0)])
def test_ambiguous_invalid_or_overlarge_explicit_grids_reject(changes):
 data=dict(minimum='.1',maximum='.3',step='.1',maximum_contracts=40);data.update(changes)
 with pytest.raises(ValueError):PercentageGrid(**data)


def test_profile_ceiling_is_explicit_and_never_clipped():
 g=grid();assert g.check_ceiling(60) is g
 with pytest.raises(ValueError,match='at most 20'):g.check_ceiling(20)


def test_tiny_exact_percentages_and_costs_round_trip_without_exponent_strings():
 from dataclasses import asdict
 from alphaquest.prop.phase_profiles import SizingConfiguration
 g=PercentageGrid(minimum='0.0000001',maximum='0.0000002',step='0.0000001',maximum_contracts=40)
 policies=g.policies(dict(tick_size='.25',point_value='2',commission_per_contract_per_side='0.00000001'))
 assert [p.policy['risk_percent'] for p in policies]==g.values()
 assert all(SizingConfiguration(**asdict(p))==p for p in policies)
 assert policies[0].planning_execution['commission_per_contract_per_side']=='0.00000001'
