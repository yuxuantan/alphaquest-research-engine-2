"""Exact finite-Decimal arithmetic, independent of caller precision settings."""

from decimal import Context, Decimal, Inexact, InvalidOperation, MAX_EMAX, MIN_EMIN, Overflow


def _context(precision: int) -> Context:
    # Operand-derived precision prevents rounding accepted prices with more than
    # the default 28 digits. No ambient Decimal context is installed or mutated.
    return Context(prec=max(1, precision), Emin=MIN_EMIN, Emax=MAX_EMAX,
                   traps=[Inexact, InvalidOperation, Overflow])


def _sum_context(a: Decimal, b: Decimal) -> Context:
    return _context(max(a.adjusted(), b.adjusted()) - min(a.as_tuple().exponent, b.as_tuple().exponent) + 2)


def add(a: Decimal, b: Decimal) -> Decimal:
    return _sum_context(a, b).add(a, b)


def subtract(a: Decimal, b: Decimal) -> Decimal:
    return _sum_context(a, b).subtract(a, b)


def multiply(a: Decimal, b: Decimal) -> Decimal:
    return _context(len(a.as_tuple().digits) + len(b.as_tuple().digits)).multiply(a, b)
