"""Independent overlap interval, missing-evidence and tier arithmetic checks."""

from decimal import Decimal

from alphaquest.prop import desk_basket, desk_overlap


def test_combined_mae_tracks_active_trades_and_separates_missing_evidence():
    def trade(entry, exit, mae, basis='measured'):
        return dict(entry=entry, exit=exit, scenario=(100, mae * 10), mae_basis=basis)

    selected = [(0, trade(1, 5, 275)), (1, trade(2, 3, 150)),
                (2, trade(3, 4, 500, None)), (1, trade(5, 6, 600))]
    marks = desk_overlap.overlap_marks(selected, [2, 3, 1], 1000)
    assert marks == {
        0: dict(combined=Decimal('1000'), missing=True, flagged=True),
        1: dict(combined=Decimal('1000'), missing=False, flagged=True),
        2: dict(combined=None, missing=True, flagged=False),
    }


def test_sequential_funded_book_applies_one_tier_to_the_basket():
    days = {'day': [(0, {'scenario': (100, 50, ((50, True),), True)}),
                    (1, {'scenario': (200, 40, ((40, True),), False)})]}
    day, = desk_basket.session_book(days, [12, 18], 20, sequential=True)
    assert day == [(40, 20, None, True), (120, 24, None, False)]
