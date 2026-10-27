"""Retained end-to-end timing benchmark using the normal dataset/backtest APIs.

Synthetic flat bars are an execution benchmark, not trading evidence. Run with
PYTHONPATH=tests:. .venv/bin/python tests/review_backtest_runtime.py --output <new-dir>
"""
import argparse
from datetime import datetime,timedelta
from hashlib import sha256
import json
from pathlib import Path
import statistics
from research_fixtures import ResearchClient as TestClient
from alphaquest.app import create_app


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--bars',type=int,default=20000);parser.add_argument('--repeats',type=int,default=2)
    args=parser.parse_args();args.output.mkdir(parents=True)
    lines=['Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol']
    for i in range(args.bars):
        stamp=datetime(2026,1,5)+timedelta(minutes=i)
        lines.append(stamp.strftime('%m/%d/%Y,%H:%M')+',100,100,100,100,100,50,50')
    raw=('\n'.join(lines)+'\n').encode();(args.output/'SYNTHETIC-flat-speed.csv').write_bytes(raw)
    observations=[]
    with TestClient(create_app(args.output/'datasets.sqlite3')) as client:
        response=client.post('/api/datasets',params=dict(filename='SYNTHETIC-flat-speed.csv',name='SYNTHETIC flat execution benchmark',source_timezone='UTC',tick_size='.25',point_value='10'),content=raw)
        assert response.status_code==201,response.text
        dataset=response.json()
        for repeat in range(args.repeats):
            for detail in ('full','compact'):
                request=dict(dataset_id=dataset['id'],strategy_id='consecutive_green_hold',strategy_parameters=dict(green_bar_count=1,hold_minutes=1,contracts=1),execution_settings=dict(initial_capital='10000',slippage_ticks=0,commission_per_contract_per_side='0'),report_detail=detail)
                from alphaquest.backtest_api import BacktestRequest
                if 'reuse_results' in BacktestRequest.model_fields:request['reuse_results']=False
                if 'reuse_prepared' in BacktestRequest.model_fields:request['reuse_prepared']=False
                response=client.post('/api/backtests',json=request);assert response.status_code==201,response.text
                record=response.json();id=record['id'];directory=client.app.state.runs.root/id
                assert record['summary']['trades_taken']==0 and float(record['summary']['final_equity'])==10000
                assert float(record['summary']['total_net_pnl'])==0
                diagnostics=client.get('/api/backtests/'+id+'/performance').json()
                observation=dict(repeat=repeat,detail=detail,id=id,seconds=diagnostics['elapsed_seconds'],phases=diagnostics['phases_seconds'],report_bytes=(directory/record['artifacts']['report']).stat().st_size,csv_sha256={kind:sha256((directory/(kind+'.csv')).read_bytes()).hexdigest() for kind in ('trades','equity')})
                observations.append(observation)
        assert all(row['csv_sha256']==observations[0]['csv_sha256'] for row in observations)
    medians={detail:statistics.median(row['seconds'] for row in observations if row['detail']==detail) for detail in ('full','compact')}
    result=dict(synthetic=True,expected='Flat bars produce zero entries, zero P&L and unchanged 10,000 equity; prop source is explicitly incompatible with no trades.',bars=args.bars,observations=observations,medians=medians,full_over_compact=medians['full']/medians['compact'],all_csv_hashes_equal=True)
    (args.output/'verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
