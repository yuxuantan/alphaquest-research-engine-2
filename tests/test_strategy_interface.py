from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from alphaquest.strategy import CloseIntent, EntryIntent, ExecutionConfig, Position


def config():
    return ExecutionConfig(Decimal("10000"), Decimal("0.25"), Decimal("10"), 1, Decimal("1"))


def test_exact_configuration_and_intents_are_immutable_values():
    execution = config()
    assert execution.tick_size == Decimal("0.25")
    entry = EntryIntent(contracts=2, reason="test entry")
    close = CloseIntent(reason="end_of_data")
    position = Position(contracts=2, entry_time_utc=datetime(2026, 1, 5, 10, 10, tzinfo=timezone.utc), entry_fill_price=Decimal("100.25"), entry_bar_number=3)
    for value, field, replacement in [(execution, "tick_size", Decimal("1")), (entry, "contracts", 5), (close, "reason", "changed"), (position, "entry_fill_price", Decimal("200"))]:
        with pytest.raises(FrozenInstanceError):
            setattr(value, field, replacement)
    assert position.entry_fill_price == Decimal("100.25")


@pytest.mark.parametrize("value", [True, False, 0, -1, 1.0, Decimal("1"), "1"])
def test_quantity_rejects_nonpositive_noninteger_and_boolean_values(value):
    with pytest.raises(ValueError, match="contracts"):
        EntryIntent(value, "entry")
    with pytest.raises(ValueError, match="contracts"):
        Position(value, datetime(2026, 1, 5, tzinfo=timezone.utc), Decimal("100"), 1)


@pytest.mark.parametrize("value", [True, -1, 0.0, Decimal("0"), "0"])
def test_slippage_ticks_require_a_nonnegative_integer(value):
    with pytest.raises(ValueError, match="slippage_ticks"):
        replace(config(), slippage_ticks=value)
    assert replace(config(), slippage_ticks=0).slippage_ticks == 0


@pytest.mark.parametrize("field", ["initial_capital", "tick_size", "point_value", "commission_per_contract_per_side"])
@pytest.mark.parametrize("value", [0.25, "0.25", True, Decimal("NaN"), Decimal("Infinity"), Decimal("-1")])
def test_execution_fields_reject_floats_strings_nonfinite_and_negative_values(field, value):
    with pytest.raises(ValueError, match=field):
        replace(config(), **{field: value})


@pytest.mark.parametrize("field", ["initial_capital", "tick_size", "point_value"])
def test_positive_execution_fields_reject_zero(field):
    with pytest.raises(ValueError, match=field):
        replace(config(), **{field: Decimal("0")})
    assert replace(config(), commission_per_contract_per_side=Decimal("0")).commission_per_contract_per_side == 0


@pytest.mark.parametrize("reason", ["", " ", None, 1])
def test_intent_reasons_must_be_nonempty_text(reason):
    with pytest.raises(ValueError, match="reason"):
        EntryIntent(1, reason)
    with pytest.raises(ValueError, match="reason"):
        CloseIntent(reason)


def test_position_requires_utc_and_keeps_negative_prices_legal():
    for stamp in (datetime(2026, 1, 5), datetime(2026, 1, 5, tzinfo=timezone(timedelta(hours=8)))):
        with pytest.raises(ValueError, match="UTC"):
            Position(1, stamp, Decimal("100"), 1)
    position = Position(1, datetime(2026, 1, 5, tzinfo=timezone.utc), Decimal("-20"), 1)
    assert position.entry_fill_price == Decimal("-20")
    with pytest.raises(ValueError, match="entry_bar_number"):
        replace(position, entry_bar_number=True)
    with pytest.raises(ValueError, match="finite Decimal"):
        replace(position, entry_fill_price=100.25)
