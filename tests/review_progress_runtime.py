"""Normal API benchmark for progress overhead. Synthetic flat execution source."""
import argparse
from datetime import datetime,timedelta
import hashlib
import json
from pathlib import Path
from time import perf_counter
from uuid import uuid4
from research_fixtures import ResearchClient as TestClient
from alphaquest.app import create_app


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--bars',type=int,default=20000)
    args=parser.parse_args();args.output.mkdir(parents=True)
    lines=['Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol']
    for i in range(args.bars):
        lines.append((datetime(2026,1,5)+timedelta(minutes=i)).strftime('%m/%d/%Y,%H:%M')+',100,100,100,100,100,50,50')
    raw=('\n'.join(lines)+'\n').encode();(args.output/'SYNTHETIC-flat-progress.csv').write_bytes(raw)
    with TestClient(create_app(args.output/'datasets.sqlite3')) as client:
        dataset=client.post('/api/datasets',params=dict(filename='SYNTHETIC-flat-progress.csv',name='SYNTHETIC progress benchmark',source_timezone='UTC',tick_size='.25',point_value='10'),content=raw).json()
        updates=[];tracker=client.app.state.progress;original=tracker.update_backtest
        def update(*values,**kwargs):
            if values[2]=='replaying':updates.append(values[3])
            return original(*values,**kwargs)
        tracker.update_backtest=update
        request=dict(dataset_id=dataset['id'],strategy_id='consecutive_green_hold',strategy_parameters=dict(green_bar_count=1,hold_minutes=1,contracts=1),execution_settings=dict(initial_capital='10000',slippage_ticks=0,commission_per_contract_per_side='0'),reuse_results=False,reuse_prepared=False,reuse_calculations=False)
        progress_id=str(uuid4());started=perf_counter()
        response=client.post('/api/backtests',json=request,params=dict(progress_id=progress_id));assert response.status_code==201,response.text
        elapsed=perf_counter()-started;record=response.json();id=record['id']
        assert record['summary']['trades_taken']==0 and float(record['summary']['final_equity'])==10000 and float(record['summary']['total_net_pnl'])==0
        state=client.get('/api/progress/'+progress_id).json();assert state==dict(stage='done',bars_processed=args.bars,total_bars=args.bars,run_id=id)
        assert updates[-1]==args.bars
        result=dict(synthetic=True,bars=args.bars,id=id,seconds=elapsed,replay_progress_updates=len(updates),final_progress=state,summary=record['summary'],csv_sha256={kind:hashlib.sha256(client.get('/api/backtests/'+id+'/exports/'+kind).content).hexdigest() for kind in ('trades','equity')})
    (args.output/'verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
