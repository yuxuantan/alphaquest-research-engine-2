"""Drive compiled C# decisions through AQ fills with independently evolving state.

No Python strategy signals are fed to C#. This checks code logic and rounded
protection plans, not an installed MultiCharts SDK or its proprietary fill engine.
"""
from dataclasses import asdict
from decimal import Decimal as D
import json
import os
import subprocess

from alphaquest.execution import execute, Trade, EquityPoint
from alphaquest.strategy import BracketIntent, CloseIntent, EntryIntent, EntryProtection, StopEntriesIntent
from test_twin_continuation import CT


class CSharpStrategy:
    def __init__(self, dotnet, dll, parameters, config, names, transcript):
        self.p,self.config,self.transcript=parameters,config,transcript
        self.closed_trades=0;self.setup=None
        self.process=subprocess.Popen([dotnet,str(dll),'--stream'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,text=True,bufsize=1,
            env=dict(os.environ,DOTNET_CLI_HOME='/private/tmp/aq-twin-dotnet-home'))
        self.send({names[k]:float(v) if type(v) is D else v for k,v in asdict(parameters).items() if k in names})
    def send(self, data):
        self.process.stdin.write(json.dumps(data)+'\n');self.process.stdin.flush()
    def on_entry_fill(self,entry,position):
        self.setup=entry.reason[:2]
    def on_bar(self,bar,position):
        if bar.bar_number<=self.p.max_bars_back:return None
        self.send(dict(bar_number=bar.bar_number,time=bar.timestamp_utc.astimezone(CT).replace(tzinfo=None).isoformat(),
            high=float(bar.high),low=float(bar.low),close=float(bar.close),tick_size=float(self.config.tick_size),
            position=0 if position is None else 1 if position.side=='long' else -1,
            entry_price=0 if position is None else float(position.entry_fill_price),total_trades=self.closed_trades))
        line=self.process.stdout.readline()
        if not line:raise AssertionError(self.process.stderr.read())
        self.transcript.write(line)
        reply=json.loads(line);orders=reply['orders']
        if position is None:
            entries=[o for o in orders if o['entry'] is None]
            if not entries:return None
            self.setup=entries[0]['name'][:2]
            def entry(o):
                plan=None
                if self.p.immediate_protection:
                    swing=next((s['price'] for s in reply['swing_stops'] if s['entry']==o['name']),None)
                    stop=reply['stop_distance'];target=reply['target_distance']
                    plan=EntryProtection(stop_price=D(str(swing)) if swing is not None else None,
                        stop_distance=D(str(stop)) if stop is not None and swing is None else None,
                        max_stop_distance=D(str(stop)) if stop is not None and swing is not None else None,
                        target_distance=D(str(target)) if target is not None else None)
                return EntryIntent(int(o['quantity']),o['name'],side='long' if o['action']=='Buy' else 'short',
                                   timing='next_open',protection=plan)
            if entries[0]['kind']=='market':return entry(entries[0])
            return StopEntriesIntent(tuple((entry(o),D(str(o['price']))) for o in entries))
        parent=self.setup+('-L' if position.side=='long' else '-S')
        owned=[o for o in orders if o['entry']==parent]
        for kind,timing in [('close','same_close'),('market','next_open')]:
            chosen=next((o for o in owned if o['kind']==kind),None)
            if chosen:return CloseIntent(chosen['name'],timing=timing)
        stop=next(o['price'] for o in owned if o['kind']=='stop')
        target=next((o['price'] for o in owned if o['kind']=='limit'),None)
        return BracketIntent(D(str(stop)),D(str(target)) if target is not None else None)
    def on_finish(self,bar,position):
        return CloseIntent('end_of_data') if position else None
    def close(self):
        self.process.stdin.close()
        self.process.wait(timeout=10)
        assert self.process.returncode==0,self.process.stderr.read()
        self.process.stdout.close();self.process.stderr.close()


def replay(dotnet,dll,rows,parameters,config,names,path):
    with path.open('w') as transcript:
        strategy=CSharpStrategy(dotnet,dll,parameters,config,names,transcript)
        try:
            output=[]
            for event in execute(rows,strategy,config,capture_risk=True):
                if type(event) is Trade:strategy.closed_trades+=1
                output.append(event)
            return output
        finally:strategy.close()
