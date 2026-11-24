"""Exact, explicit percentage axes over the existing sizing policy contract."""
from decimal import Decimal,localcontext
from typing import Literal
from pydantic import BaseModel,ConfigDict,StrictStr,StrictInt,StrictBool,field_validator,model_validator
from .sizing import SizingPolicy,amount
from .phase_profiles import SizingConfiguration


def exact_text(value):
    text=format(value,'f')
    return text.rstrip('0').rstrip('.') if '.' in text else text


class PercentageGrid(BaseModel):
    model_config=ConfigDict(extra='forbid',frozen=True)
    minimum:StrictStr
    maximum:StrictStr
    step:StrictStr
    reference:Literal['initial_configured_capital','current_account_balance','available_drawdown_cushion']='initial_configured_capital'
    maximum_contracts:StrictInt
    constrain_to_account_cushion:StrictBool=False
    constrain_to_daily_cushion:StrictBool=False

    @field_validator('minimum','maximum','step')
    @classmethod
    def decimal_text(cls,value):
        v=amount(value)
        if not 0<v<=100:raise ValueError('Risk percentage and step must be positive and at most 100.')
        return exact_text(v)

    @model_validator(mode='after')
    def coherent(self):
        if not 1<=self.maximum_contracts<=60:raise ValueError('Percentage quantity ceiling must be 1–60 MNQ, subject to phase/profile caps.')
        lo,hi,step=map(Decimal,(self.minimum,self.maximum,self.step))
        if lo>hi:raise ValueError('Minimum risk percentage must not exceed maximum.')
        with localcontext() as ctx:
            ctx.prec=256
            if (hi-lo)%step:raise ValueError('Percentage-grid endpoint must align exactly with its step.')
            count=int((hi-lo)/step)+1
        # Same explicit policy family boundary as CandidateSource; never truncate.
        if count>60:raise ValueError('Declare at most 60 percentage policies in one phase grid.')
        return self

    def values(self):
        lo,hi,step=map(Decimal,(self.minimum,self.maximum,self.step))
        with localcontext() as ctx:
            ctx.prec=256
            return [exact_text(lo+step*i) for i in range(int((hi-lo)/step)+1)]

    def policies(self,planning_execution,*,execution_model=None,trade_handling=None):
        return [SizingConfiguration(SizingPolicy(kind='percentage_risk',risk_percent=value,reference=self.reference,
            maximum_contracts=self.maximum_contracts,constrain_to_account_cushion=self.constrain_to_account_cushion,
            constrain_to_daily_cushion=self.constrain_to_daily_cushion).model_dump(mode='json'),'50000',planning_execution,execution_model,trade_handling)
            for value in self.values()]

    def check_ceiling(self,ceiling):
        if self.maximum_contracts>ceiling:raise ValueError(f'This account phase permits at most {ceiling} MNQ.')
        return self


def axis(configuration):
    """Sizing display/selection is separate from legacy native execution caps."""
    sizing=configuration.get('sizing')
    if sizing and sizing['policy']['kind']=='percentage_risk':
        p=sizing['policy'];value=exact_text(Decimal(p['risk_percent']))
        return dict(kind='percentage_risk',risk_percent=value,reference=p['reference'],maximum_contracts=p['maximum_contracts'],
            native_user_cap_contracts=configuration['micros'],label=f"{value}% · {p['reference'].replace('_',' ')}")
    return dict(kind='fixed_contracts',contracts=configuration['micros'],label=f"{configuration['micros']} MNQ")


def selection_value(configuration):
    a=axis(configuration)
    return Decimal(a['risk_percent']) if a['kind']=='percentage_risk' else Decimal(a['contracts'])
