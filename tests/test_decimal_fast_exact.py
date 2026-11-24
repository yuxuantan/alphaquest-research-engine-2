from decimal import Decimal,Context,MAX_EMAX,MIN_EMIN,Inexact,InvalidOperation,Overflow,localcontext
from itertools import product
from alphaquest.decimal_math import add,subtract,multiply


def test_fast_decimal_and_fallback_preserve_full_value_scale_and_caller_context():
 values=[Decimal(v) for v in ['0','-0.00','1.20','-30000.51','0.00000000000000000000001','9'*140,'1'+'0'*90+'.000', '0E-400','3.141592653589793238462643383279502884197169399375105820974944592307816406286']]
 for a,b in product(values,repeat=2):
  sum_precision=max(a.adjusted(),b.adjusted())-min(a.as_tuple().exponent,b.as_tuple().exponent)+2
  sumctx=Context(prec=max(1,sum_precision),Emin=MIN_EMIN,Emax=MAX_EMAX,traps=[Inexact,InvalidOperation,Overflow])
  mulctx=Context(prec=max(1,len(a.as_tuple().digits)+len(b.as_tuple().digits)),Emin=MIN_EMIN,Emax=MAX_EMAX,traps=[Inexact,InvalidOperation,Overflow])
  with localcontext() as ctx:
   ctx.prec=3
   assert add(a,b).as_tuple()==sumctx.add(a,b).as_tuple()
   assert subtract(a,b).as_tuple()==sumctx.subtract(a,b).as_tuple()
   assert multiply(a,b).as_tuple()==mulctx.multiply(a,b).as_tuple()
   assert ctx.prec==3
