"""Exact finite-Decimal arithmetic, independent of caller precision settings."""

from decimal import Context, Decimal, Inexact, InvalidOperation, MAX_EMAX, MIN_EMIN, Overflow
from threading import local

_contexts = local()


def _context(precision: int) -> Context:
    # Operand-derived precision prevents rounding accepted prices with more than
    # the default 28 digits. No ambient Decimal context is installed or mutated.
    precision = max(1, precision)
    if not hasattr(_contexts, "values"):
        _contexts.values = {}
    values = _contexts.values
    if precision not in values:
        if len(values) >= 128:
            values.clear()
        values[precision] = Context(prec=precision, Emin=MIN_EMIN, Emax=MAX_EMAX,
                                    traps=[Inexact, InvalidOperation, Overflow])
    return values[precision]


def _sum_context(a: Decimal, b: Decimal) -> Context:
    return _context(max(a.adjusted(), b.adjusted()) - min(a.as_tuple().exponent, b.as_tuple().exponent) + 2)


def add(a: Decimal, b: Decimal) -> Decimal:
    return _sum_context(a, b).add(a, b)


def subtract(a: Decimal, b: Decimal) -> Decimal:
    return _sum_context(a, b).subtract(a, b)


def multiply(a: Decimal, b: Decimal) -> Decimal:
    return _context(len(a.as_tuple().digits) + len(b.as_tuple().digits)).multiply(a, b)
