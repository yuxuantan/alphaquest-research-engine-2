"""Independent product expectations, strict requests, and durable value snapshots."""

from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, localcontext
import json

import pytest

from alphaquest.prop import (
    ResolvedProfile, ResolvedSimulation, get_profile, resolve_profile, resolve_simulation,
)
from alphaquest.prop.types import (
    DatedFee, DrawdownRules, InactivityRules, LimitTier, MonteCarloConfig, RuleEvidence,
    RuleSource, SimulationConfig, SizingConfig, StressConfig, TradingLimits, UserFees,
)


D = Decimal
START = datetime(2026, 1, 5, 23, tzinfo=timezone.utc)
END = datetime(2026, 2, 4, 23, tzinfo=timezone.utc)
SOURCE = "https://apextraderfunding.com/help-center/additional-helpful-items/position-sizing-evaluation/"


def request(**overrides):
    values = dict(
        source_backtest_id="completed-source-run", phase="evaluation", analysis="historical",
        observation_mode="bar_close", account_start_utc=START, end_utc=END,
        instrument="NQ", currency="USD", contract_limit_weight=D("1"), contract_limit_source_url=SOURCE,
        quantity=1, calendar_id="test-calendar-v1", calendar_sha256="1" * 64,
        timezone_data_version="test-2026a", coverage_assumption="Complete declared strategy window",
        fees=UserFees("USD", attempt_fee=D("100")),
    )
    values.update(overrides)
    return SimulationConfig(**values)


def test_named_product_has_separate_evaluation_and_funded_rules():
    p = get_profile()
    assert p.id == "apex_50k_eod_rithmic" and p.version == "1.1.0"
    assert p.currency == "USD" and p.provider == "Apex Trader Funding"
    e, f = p.evaluation, p.funded
    assert e.initial_balance == f.initial_balance == D("50000")
    assert e.profit_target == D("3000")
    assert e.drawdown.amount == f.drawdown.amount == D("2000")
    assert e.drawdown.lock_profit == D("3000")
    assert f.drawdown.lock_profit == D("100")
    assert e.limits == TradingLimits(6, D("1000"))
    assert e.minimum_trading_days == 0 and e.access_calendar_days == 30
    assert f.access_calendar_days is None
    assert e.review_time == time(16, 59, 59)
    assert e.expiry_time == e.recognition_not_before == time(18)
    assert p.session.timezone == "America/New_York"
    assert p.session.open_time == p.session.reset_time == time(18)
    assert p.session.trading_date == "session_close_date"


def test_funded_payout_and_activity_values_are_independent_expectations():
    payouts = get_profile().funded.payouts
    assert payouts.qualifying_days == 5 and payouts.qualifying_day_profit == 250
    assert payouts.consistency_limit == D(".50")
    assert payouts.consistency_comparison == "strictly_less"
    assert payouts.minimum_request_balance == D("52600")
    assert payouts.safety_net_balance == D("52100")
    assert payouts.minimum_withdrawal == 500
    assert payouts.ladder == tuple(map(D, ("1500", "1500", "2000", "2500", "2500", "3000")))
    assert sum(payouts.ladder) == D("13000") and payouts.profit_split == 1
    assert payouts.cycle_reset == "approved_payout" and payouts.close_after_ladder is True
    assert get_profile().funded.inactivity == InactivityRules(30, 2, D("50"), 30)


@pytest.mark.parametrize("platform,lock", [("rithmic", D("3000")), ("wealthcharts", D("3000")), ("tradovate", None)])
def test_platform_locks_do_not_silently_use_rithmic_for_tradovate(platform, lock):
    p = get_profile(f"apex_50k_eod_{platform}")
    assert p.platform == platform and p.evaluation.drawdown.lock_profit == lock
    assert p.funded == get_profile().funded
    assert ResolvedProfile.from_json(resolve_profile(p).to_json()).profile == p


@pytest.mark.parametrize("name", [None, True, 123, "Apex", "apex_50k_eod", "apex_50k_eod_legacy"])
def test_unknown_product_is_not_guessed(name):
    with pytest.raises(ValueError, match="profile ID"):
        get_profile(name)


@pytest.mark.parametrize("profit,contracts,dll", [
    ("-2000", 2, "1000"), ("0", 2, "1000"), ("1499.9999", 2, "1000"),
    ("1500", 3, "1000"), ("2999.9999", 3, "1000"), ("3000", 4, "2000"),
    ("5999", 4, "2000"), ("5999.9999", 4, "2000"), ("6000", 4, "3000"),
    ("999999", 4, "3000"), ("1500", 3, "1000"), ("0", 2, "1000"),
])
def test_tier_boundaries_and_up_down_resolution(profit, contracts, dll):
    limits = get_profile().funded.tier_for_profit(D(profit)).limits
    assert (limits.max_contracts, limits.daily_loss_limit) == (contracts, D(dll))


def test_sources_conflicts_and_modeling_choices_are_in_the_snapshot():
    p = get_profile()
    assert len(p.sources) == 8
    assert all(source.retrieved_on == date(2026, 10, 25) and source.effective_on is None for source in p.sources)
    assert all(source.url.startswith("https://apextraderfunding.com/") for source in p.sources)
    conflict, = [claim for claim in p.evidence if claim.status == "source_conflict"]
    assert conflict.scope == "funded.tiers"
    assert conflict.source_ids == ("dll", "scaling")
    assert "5999" in conflict.note and "6000" in conflict.note
    assert {claim.scope for claim in p.evidence if claim.status == "modeling_assumption"} >= {
        "assumptions.tier_balance", "assumptions.target_policy", "assumptions.payout_processing",
        "assumptions.incompatible_size", "assumptions.liquidation",
    }
    assert p.assumptions.incompatible_size == "reject_simulation"
    assert p.evaluation.limits.excess_size_action == "reject_order"
    assert p.funded.tiers[0].limits.excess_size_action == "reject_order"


@pytest.mark.parametrize("value", [True, False, "1", 1.0, D("1"), 0, -1])
def test_rule_integer_fields_reject_coercion_and_nonpositive_values(value):
    with pytest.raises(ValueError):
        TradingLimits(value, D("1000"))
    with pytest.raises(ValueError):
        replace(get_profile().funded.payouts, qualifying_days=value)
    with pytest.raises(ValueError):
        replace(get_profile().evaluation, access_calendar_days=value)


@pytest.mark.parametrize("value", [True, 1000, "1000", 1000.0, D("NaN"), D("sNaN"), D("Infinity"), D("-Infinity"), D("0"), D("-1")])
def test_positive_money_rejects_wrong_types_nonfinite_and_invalid_bounds(value):
    with pytest.raises(ValueError):
        DrawdownRules(value, D("100"))
    with pytest.raises(ValueError):
        TradingLimits(1, value)
    with pytest.raises(ValueError):
        replace(get_profile().evaluation, profit_target=value)


@pytest.mark.parametrize("value", ["0", "-0.01", "1", "1.01"])
def test_consistency_limit_is_strictly_between_zero_and_one(value):
    with pytest.raises(ValueError, match="consistency_limit"):
        replace(get_profile().funded.payouts, consistency_limit=D(value))


@pytest.mark.parametrize("change", [
    {"minimum_request_balance": D("52599.99")}, {"ladder": ()},
    {"ladder": (D("499.99"),)}, {"ladder": (D("2000"), D("1500"))},
    {"ladder": [D("1500")]}, {"profit_split": D("0")}, {"profit_split": D("1.01")},
    {"consistency_comparison": "less_or_equal"}, {"close_after_ladder": 1},
])
def test_impossible_or_mutable_payout_settings_are_rejected(change):
    with pytest.raises(ValueError):
        replace(get_profile().funded.payouts, **change)


def test_payout_request_and_split_boundaries_are_valid():
    p = get_profile().funded.payouts
    assert replace(p, minimum_request_balance=D("52600.000")).minimum_request_balance == 52600
    assert replace(p, profit_split=D(".80")).profit_split == D(".8")


@pytest.mark.parametrize("tiers", [
    (), (LimitTier(D("1"), TradingLimits(2, D("1000"))),),
    (LimitTier(D("0"), TradingLimits(2, D("1000"))), LimitTier(D("0"), TradingLimits(3, D("1000")))),
    (LimitTier(D("0"), TradingLimits(3, D("1000"))), LimitTier(D("1500"), TradingLimits(2, D("1000")))),
    (LimitTier(D("0"), TradingLimits(2, D("2000"))), LimitTier(D("1500"), TradingLimits(3, D("1000")))),
    (LimitTier(D("0"), TradingLimits(2, None)),),
])
def test_tiers_have_strict_unambiguous_bounds_and_enabled_monotonic_limits(tiers):
    with pytest.raises(ValueError):
        replace(get_profile().funded, tiers=tiers)
    with pytest.raises(ValueError):
        LimitTier(D("-1"), TradingLimits(2, D("1000")))


def test_impossible_cross_field_and_phase_settings():
    p = get_profile()
    bad = [
        lambda: replace(p.evaluation, drawdown=DrawdownRules(D("50000"), D("3000"))),
        lambda: replace(p.evaluation, minimum_trading_days=31),
        lambda: replace(p.evaluation, review_time=time(19)),
        lambda: replace(p.funded, access_calendar_days=30),
        lambda: replace(p.funded, payouts=replace(p.funded.payouts, safety_net_balance=D("50000"))),
        lambda: replace(p.funded, payouts=replace(p.funded.payouts, safety_net_balance=D("50100"))),
        lambda: replace(p.funded.inactivity, qualifying_days=31),
        lambda: replace(p.funded.inactivity, initial_grace_calendar_days=22),
        lambda: replace(p.session, timezone="Mars/Olympus"),
        lambda: replace(p.session, close_time=time(18)),
        lambda: replace(p.session, reset_time=time(19)),
        lambda: replace(p.session, open_time=time(18, tzinfo=timezone.utc)),
        lambda: replace(p, evaluation=replace(p.evaluation, initial_balance=D("60000"))),
        lambda: replace(p, platform="tradovate"),  # Cannot keep Rithmic lock.
        lambda: replace(p, evidence=(RuleEvidence("funded.tiers", "verified", ("missing",), "test"),)),
        lambda: replace(p, evidence=(RuleEvidence("funded.missing", "verified", ("dll",), "test"),)),
        lambda: replace(p, sources=p.sources + (p.sources[0],)),
        lambda: replace(p, sources=list(p.sources)),
    ]
    for construct in bad:
        with pytest.raises(ValueError):
            construct()


@pytest.mark.parametrize("value", ["1500", 1500, 1500.0, True, D("NaN"), D("Infinity")])
def test_tier_lookup_requires_finite_decimal_profit(value):
    with pytest.raises(ValueError):
        get_profile().funded.tier_for_profit(value)


def test_valid_simulation_requests_preserve_fees_and_sample_settings():
    historical = request()
    assert historical.fees.origin == "user_supplied" and historical.monte_carlo is None
    funded = request(phase="funded", fees=UserFees("USD", activation_fee=D("0")),
                     contract_limit_weight=D("0.1"), instrument="MNQ", quantity=3)
    assert funded.quantity == 3 and funded.fees.attempt_fee is None
    mc = request(analysis="monte_carlo", monte_carlo=MonteCarloConfig(100, 42, 5, 2),
                 sizing=SizingConfig((1, 2, 3)), stress=StressConfig(D(".25"), 1, D(".10")))
    assert SimulationConfig.from_dict(mc.to_dict()) == mc
    assert SimulationConfig.from_dict(funded.to_dict()) == funded


@pytest.mark.parametrize("change", [
    {"phase": "challenge"}, {"observation_mode": "excursion"}, {"analysis": "daily"},
    {"quantity": True}, {"quantity": D(".3")}, {"quantity": 0},
    {"contract_limit_weight": D("0")}, {"contract_limit_source_url": "NQ means mini"},
    {"account_start_utc": START.replace(tzinfo=None)},
    {"end_utc": START}, {"end_utc": START - timedelta(seconds=1)},
    {"end_utc": END.astimezone(timezone(timedelta(hours=8)))},
    {"calendar_sha256": "not-a-hash"}, {"calendar_mode": "inferred"},
    {"fees": UserFees("EUR", attempt_fee=D("100"))},
    {"fees": UserFees("USD")},
    {"fees": UserFees("USD", attempt_fee=D("100"), activation_fee=D("140"))},
    {"phase": "funded"},
    {"analysis": "monte_carlo"}, {"monte_carlo": MonteCarloConfig(100, 42)},
    {"sizing": SizingConfig((1, 2))},
    {"fees": UserFees("USD", attempt_fee=D("0"), scheduled=(DatedFee("fee", D("1"), END + timedelta(seconds=1)),))},
])
def test_invalid_simulation_combinations_are_rejected(change):
    with pytest.raises(ValueError):
        request(**change)


@pytest.mark.parametrize("construct", [
    lambda: MonteCarloConfig(0, 1, retained_traces=0),
    lambda: MonteCarloConfig(100, True),
    lambda: MonteCarloConfig(100, -1),
    lambda: MonteCarloConfig(100, 42, block_length=0),
    lambda: MonteCarloConfig(1, 42, retained_traces=2),
    lambda: SizingConfig(()), lambda: SizingConfig((1, True)),
    lambda: SizingConfig((1, 1)), lambda: SizingConfig((1,), validation_fraction=D("1")),
    lambda: SizingConfig((1,), maximum_failure_rate=D("1.01")),
    lambda: SizingConfig((1,), maximum_drawdown=D("0")),
    lambda: StressConfig(D("-.01")), lambda: StressConfig(additional_slippage_ticks=True),
    lambda: StressConfig(exit_profit_reduction=D("1.01")),
    lambda: UserFees("USD", attempt_fee=D("-1")),
    lambda: UserFees("USD", activation_fee=D("NaN")),
    lambda: UserFees("USD", scheduled=(DatedFee("late", D("1"), END), DatedFee("early", D("1"), START))),
    lambda: RuleSource("source", "http://example.com", date(2026, 10, 25)),
    lambda: RuleSource("source", SOURCE, datetime(2026, 10, 25)),
    lambda: RuleSource("source", SOURCE, date(2026, 10, 25), date(2026, 10, 26)),
])
def test_analysis_fee_and_evidence_bounds(construct):
    with pytest.raises(ValueError):
        construct()


def test_profile_and_simulation_snapshots_round_trip_without_current_templates(tmp_path, monkeypatch):
    import alphaquest.prop.rules as rules

    old_profile = get_profile()
    saved = resolve_simulation(request(), old_profile)
    path = tmp_path / "settings.json"
    path.write_text(saved.to_json(), encoding="utf-8")
    updated = replace(old_profile, version="1.1.0", evaluation=replace(old_profile.evaluation, profit_target=D("4000"),
                      drawdown=replace(old_profile.evaluation.drawdown, lock_profit=D("4000"))))
    monkeypatch.setattr(rules, "get_profile", lambda *args: updated)
    restored = ResolvedSimulation.from_json(path.read_text(encoding="utf-8"))
    assert restored == saved
    assert restored.rules.profile.evaluation.profit_target == D("3000")
    assert restored.rules.profile_sha256 != resolve_profile(updated).profile_sha256
    assert restored.config.fees.attempt_fee == D("100")
    assert get_profile().sources[0].effective_on is None


def test_immutability_and_detached_wire_dicts():
    saved = resolve_simulation(request(), get_profile())
    for obj, field, value in [
        (saved, "format_version", 2), (saved.rules.profile, "version", "2.0.0"),
        (saved.rules.profile.funded.tiers[0].limits, "max_contracts", 9),
        (saved.config.fees, "attempt_fee", D("0")),
    ]:
        with pytest.raises(FrozenInstanceError):
            setattr(obj, field, value)
    payload = saved.to_dict()
    payload["rules"]["profile"]["funded"]["tiers"][0]["limits"]["max_contracts"] = 99
    payload["config"]["fees"]["attempt_fee"] = "0"
    assert saved.rules.profile.funded.tiers[0].limits.max_contracts == 2
    assert saved.config.fees.attempt_fee == D("100")


def test_hashes_are_canonical_context_independent_and_sensitive_to_settings():
    p = get_profile()
    first = resolve_profile(p)
    assert first.profile_sha256 == "a3996254ebb5c9e58d664db175fc34da719d079eede4a3653cbf67b8d4638256"
    equivalent = replace(p, evaluation=replace(p.evaluation, initial_balance=D("50000.00000")),
                         funded=replace(p.funded, initial_balance=D("5E4")))
    with localcontext() as ctx:
        ctx.prec = 2
        assert resolve_profile(equivalent).profile_sha256 == first.profile_sha256
        assert ResolvedProfile.from_json(first.to_json()) == first
    # Every part of provenance/assumptions, not just numeric rules, is bound.
    assert resolve_profile(replace(p, version="1.0.1")).profile_sha256 != first.profile_sha256
    changed_sources = (replace(p.sources[0], retrieved_on=date(2026, 10, 26)),) + p.sources[1:]
    assert resolve_profile(replace(p, sources=changed_sources)).profile_sha256 != first.profile_sha256
    a = resolve_simulation(request(), p)
    b = resolve_simulation(request(fees=UserFees("USD", attempt_fee=D("101"))), p)
    assert a.rules.profile_sha256 == b.rules.profile_sha256
    assert a.settings_sha256 != b.settings_sha256
    with localcontext() as ctx:
        ctx.prec = 1
        assert resolve_simulation(request(), p).settings_sha256 == a.settings_sha256


@pytest.mark.parametrize("mutate", [
    lambda p: p["profile"]["funded"]["tiers"][0]["limits"].update(max_contracts=99),
    lambda p: p.update(profile_sha256="0" * 64),
    lambda p: p.update(format_version=True),
    lambda p: p.update(format_version=2),
    lambda p: p.update(unrecognized="field"),
    lambda p: p["profile"]["evaluation"].update(profit_target=3000),
    lambda p: p["profile"]["evaluation"].update(profit_target="NaN"),
    lambda p: p["profile"]["evaluation"].update(profit_target="1_000"),
    lambda p: p["profile"]["evaluation"].update(profit_target=" 3000"),
    lambda p: p["profile"]["funded"].update(access_calendar_days=30),
    lambda p: p["profile"]["funded"]["payouts"].update(unknown=True),
    lambda p: p["profile"]["sources"][0].update(retrieved_on="20261025"),
    lambda p: p["profile"]["session"].update(open_time="18:00"),
])
def test_profile_wire_rejects_tampering_unknown_fields_and_coercion(mutate):
    payload = resolve_profile(get_profile()).to_dict()
    mutate(payload)
    with pytest.raises(ValueError):
        ResolvedProfile.from_json(json.dumps(payload))


def test_wire_rejects_duplicates_nonstandard_constants_and_missing_fields():
    text = resolve_profile(get_profile()).to_json()
    for invalid in (
        '{"format_version":1,' + text[1:],
        text.replace('"format_version":1', '"format_version":NaN'),
        '{}', '[]', 'null', '{not json',
    ):
        with pytest.raises(ValueError):
            ResolvedProfile.from_json(invalid)
    payload = request().to_dict()
    payload["account_start_utc"] = START.isoformat()  # Wire clock requires Z, no offset guessing.
    with pytest.raises(ValueError):
        SimulationConfig.from_dict(payload)


def test_simulation_envelope_detects_config_mutation_and_currency_mismatch():
    payload = resolve_simulation(request(), get_profile()).to_dict()
    payload["config"]["quantity"] = 2
    with pytest.raises(ValueError, match="hash mismatch"):
        ResolvedSimulation.from_dict(payload)
    with pytest.raises(ValueError, match="currency"):
        resolve_simulation(request(currency="EUR", fees=UserFees("EUR", attempt_fee=D("0"))), get_profile())


def test_json_key_order_does_not_change_profile_identity():
    resolved = resolve_profile(get_profile())
    payload = resolved.to_dict()
    payload["profile"] = dict(reversed(list(payload["profile"].items())))
    assert ResolvedProfile.from_dict(payload) == resolved


def test_zero_fee_and_extreme_decimal_precision_round_trip_exactly():
    amount = D("123456789012345678901234567890.123456789012345678901234567890")
    fees = UserFees("USD", attempt_fee=D("0"), scheduled=(DatedFee("data", amount, START),))
    resolved = resolve_simulation(request(fees=fees), get_profile())
    with localcontext() as ctx:
        ctx.prec = 1
        assert ResolvedSimulation.from_json(resolved.to_json()) == resolved
        assert ResolvedSimulation.from_json(resolved.to_json()).config.fees.scheduled[0].amount == amount
