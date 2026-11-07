"""Exact-native and unchanged-float money operations at shared phase boundaries."""
from decimal import Decimal
from alphaquest.decimal_math import add, subtract, multiply


def operands(a,b):
    if isinstance(a,Decimal) or isinstance(b,Decimal):
        if type(a) is int:a=Decimal(a)
        if type(b) is int:b=Decimal(b)
        if not isinstance(a,Decimal) or not isinstance(b,Decimal):
            raise TypeError('Native exact state requires exact rule money; float mixing is forbidden.')
        return a,b
    return None


def money_add(a,b):
    exact=operands(a,b)
    return add(*exact) if exact else a+b


def money_sub(a,b):
    exact=operands(a,b)
    return subtract(*exact) if exact else a-b


def money_mul(a,b):
    exact=operands(a,b)
    return multiply(*exact) if exact else a*b


def money_half(value):
    return multiply(value,Decimal('.5')) if isinstance(value,Decimal) else value*.5


def money_sum(values):
    result=0
    for value in values:result=money_add(result,value)
    return result


def rule_constant(like, text):
    """Exact native interpretation; retain legacy binary-float constants."""
    return Decimal(text) if isinstance(like,Decimal) else float(text)
