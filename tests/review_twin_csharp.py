"""Compile the delivered C# core and compare state/orders against the Python port.

This does not compile the MultiCharts adapter or emulate the MultiCharts SDK.
"""
import argparse
from dataclasses import asdict, replace
from datetime import datetime,timedelta
from decimal import Decimal
import json
import math
import os
from pathlib import Path
import random
import subprocess

from alphaquest.execution import execute
from alphaquest.strategy import BracketIntent, CloseIntent, EntryIntent, StopEntriesIntent
from alphaquest.strategies.twin_continuation import TwinContinuation,Parameters
from test_twin_continuation import CT,prices,momentum_rows,momentum_parameters,breakout_rows,config

ROOT=Path(__file__).resolve().parents[1]
NAMES=dict(use_breakout='UseBreakout',use_momentum='UseMomentum',qty='Qty',clock_shift='ClockShift',debug_log='DebugLog',
           immediate_protection='ImmediateProtection')
for name in asdict(Parameters()):
    if name.startswith(('bo_','mo_')):
        prefix,tail=name.split('_',1)
        NAMES[name]=prefix.upper()+'_'+''.join(word.capitalize() for word in tail.split('_'))
NAMES.update(bo_atr_period='BO_ATRPeriod',bo_pivot_tf='BO_PivotTF')


class Capture(TwinContinuation):
    def __init__(self,p):super().__init__(p);self.inputs=[];self.expected=[]
    def on_bar(self,bar,position):
        setup=self.setup if self.was_holding else self.pending_setup
        intent=super().on_bar(bar,position)
        if bar.bar_number<=self.p.max_bars_back:return intent
        self.inputs.append(dict(bar_number=bar.bar_number,time=bar.timestamp_utc.astimezone(CT).replace(tzinfo=None).isoformat(),
            high=float(bar.high),low=float(bar.low),close=float(bar.close),
            position=0 if position is None else 1 if position.side=='long' else -1,
            entry_price=0 if position is None else float(position.entry_fill_price),
            total_trades=self.total_trades-(1 if type(intent) is CloseIntent and intent.timing=='same_close' else 0)))
        self.expected.append(dict(state={key:float(getattr(self,key)) if type(getattr(self,key)) is Decimal else getattr(self,key)
            for key in ('atr','arm_atr','swing_hi','swing_lo','vol_ratio','armed','level_long','level_short','stop_long','stop_short',
                        'hi_open','lo_open','s_count','osc','traded_today')},intent=intent,setup=setup,position=position))
        return intent


def comparable(intent):
    if type(intent) is EntryIntent:return [('market',intent.reason,0)]
    if type(intent) is StopEntriesIntent:return [('stop',e.reason,float(p)) for e,p in intent.orders]
    if type(intent) is CloseIntent:return [('close' if intent.timing=='same_close' else 'market',intent.reason,0)]
    if type(intent) is BracketIntent:
        return [('stop','',float(intent.stop_price))]+([('limit','',float(intent.target_price))] if intent.target_price is not None else [])
    return []


def active_orders(actual,expected):
    position=expected['position']
    if position is None:
        return [(o['kind'],o['name'],o['price']) for o in actual['orders'] if o['entry'] is None]
    entry=expected['setup']+('-L' if position.side=='long' else '-S')
    owned=[o for o in actual['orders'] if o['entry']==entry]
    closes=[o for o in owned if o['kind']=='close']
    markets=[o for o in owned if o['kind']=='market']
    chosen=closes[:1] or markets[:1] or owned
    return [(o['kind'],o['name'] if o['kind'] in ('close','market') else '',o['price']) for o in chosen]


def review(output,dotnet):
    output.mkdir(parents=True,exist_ok=False)
    env=dict(os.environ,DOTNET_CLI_HOME='/private/tmp/aq-twin-dotnet-home',DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1')
    build=subprocess.run([dotnet,'build',str(ROOT/'tests/multicharts_twin/TwinCheck.csproj'),'--nologo','-v','quiet'],capture_output=True,text=True,env=env)
    (output/'build.txt').write_text(build.stdout+build.stderr)
    assert build.returncode==0,build.stdout+build.stderr
    rng=random.Random(8197)
    flat=[];start=datetime(2024,1,10,17,1,tzinfo=CT)
    # Multiple sessions and missing bucket boundaries, enough sessions to make
    # the volatility filter observable; keep positions flat in these probes.
    level=1000
    for i in range(10000):
        stamp=start+timedelta(minutes=i)
        if 16<=stamp.hour<17 or rng.randrange(19)==0:continue
        level+=rng.choice((-2,-1,0,1,2))
        flat.append(prices(len(flat)+1,stamp,level,level+3,level-3,level+1))
    cases=[('momentum-long',momentum_rows(),momentum_parameters(),True),
           ('momentum-short',momentum_rows(short=True),momentum_parameters(),True),
           ('momentum-immediate-long',momentum_rows(),momentum_parameters(immediate_protection=True),True),
           ('momentum-immediate-short',momentum_rows(short=True),momentum_parameters(immediate_protection=True),True),
           ('breakout-long',breakout_rows(),Parameters(max_bars_back=0,use_momentum=False,bo_pivot_tf=15,bo_atr_period=1),True),
           ('breakout-short',breakout_rows(True),Parameters(max_bars_back=0,use_momentum=False,bo_pivot_tf=15,bo_atr_period=1),True),
           ('gaps-sessions',flat,Parameters(max_bars_back=5,bo_vol_lookback=2),False),
           ('clock-shift',flat,Parameters(max_bars_back=5,bo_vol_lookback=2,clock_shift=1),False)]
    observations=[]
    for name,rows,p,replay in cases:
        capture=Capture(p)
        if replay:list(execute(rows,capture,config()))
        else:
            for b in rows:capture.on_bar(b,None)
        path=output/(name+'-input.json')
        path.write_text(json.dumps(dict(parameters={NAMES[k]:float(v) if type(v) is Decimal else v for k,v in asdict(p).items() if k in NAMES},bars=capture.inputs)))
        result=subprocess.run([dotnet,str(ROOT/'tests/multicharts_twin/bin/Debug/net8.0/TwinCheck.dll'),str(path)],capture_output=True,text=True,env=env)
        assert result.returncode==0,result.stderr
        (output/(name+'-csharp.jsonl')).write_text(result.stdout)
        for actual,expected in zip(map(json.loads,result.stdout.splitlines()),capture.expected,strict=True):
            for key,value in expected['state'].items():
                assert actual[key]==value if type(value) is bool else math.isclose(actual[key],value,rel_tol=1e-10,abs_tol=1e-10),(name,actual['bar_number'],key,actual[key],value)
            wanted=comparable(expected['intent']);got=active_orders(actual,expected)
            assert len(wanted)==len(got),(name,actual['bar_number'],wanted,got)
            for a,b in zip(wanted,got):
                assert a[:2]==b[:2] and math.isclose(a[2],b[2],rel_tol=1e-10,abs_tol=1e-10),(name,actual['bar_number'],a,b)
        observations.append(dict(case=name,completed_bars=len(capture.inputs),state_fields=15,orders_match=True))
    (output/'verification.json').write_text(json.dumps(dict(core_only=True,platform_parity=False,observations=observations),indent=2)+'\n')
    print(json.dumps(observations,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--dotnet',default='dotnet')
    args=parser.parse_args();review(args.output.resolve(),args.dotnet)
