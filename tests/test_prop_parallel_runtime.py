from datetime import date,timedelta
import json,os,time
import pytest
from alphaquest.prop.parallel import Runtime,CAPACITY,diagnostics,map_sweep
from test_backtest_api import client,body
from test_automatic_prop import expected_cash


def square(value):
    time.sleep(.2)
    return value*value


def child_map(value):
    runtime=Runtime(workers=min(2,CAPACITY))
    try:
        with runtime.activate():
            result=map_sweep(square,[value,value+1],50_000_000)
            return dict(values=result,pool_created=runtime.pool is not None)
    finally:runtime.close()


@pytest.mark.skipif(CAPACITY<2,reason='Multiple CPUs required')
def test_shared_budget_ordered_results_and_no_nested_worker_pool():
    runtime=Runtime(workers=2)
    try:
        with runtime.activate():
            assert map_sweep(square,[3,1,2],50_000_000)==[9,1,4]
            assert diagnostics()['workers_used']==2
            assert os.getpid() not in diagnostics()['worker_pids']
            children=map_sweep(child_map,[3,7],50_000_000)
            assert children==[dict(values=[9,16],pool_created=False),dict(values=[49,64],pool_created=False)]
        with runtime.reserve(CAPACITY-1,exact=True),runtime.activate():
            assert map_sweep(square,[1,2],50_000_000)==[1,4]
            assert diagnostics()['workers_used']==1
        assert runtime.occupied==0
    finally:runtime.close()


def many_trades():
    lines=['Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol'];stamp=date(2026,1,5);count=0
    while count<60:
        if stamp.weekday()<5:
            for trade in range(10):
                for offset,prices in enumerate(('99,100,99,100','100,100.3,100,100.3','100.3,100.3,100.3,100.3')):
                    minute=trade*3+offset
                    lines.append(stamp.strftime('%m/%d/%Y')+f',18:{minute:02d},{prices},100,60,40')
            count+=1
        stamp+=timedelta(days=1)
    return ('\n'.join(lines)+'\n').encode()


@pytest.mark.skipif(CAPACITY<2,reason='Multiple CPUs required')
def test_normal_backtest_runs_standard_prop_sweeps_in_parallel(client,tmp_path):
    dataset=client.post('/api/datasets',params=dict(filename='SYNTHETIC-ten-trades-per-day.csv',name='SYNTHETIC bounded prop parallel cash example',source_timezone='UTC',tick_size='.1',point_value='1000'),content=many_trades()).json()
    request=body(dataset['id']);request['strategy_parameters']=dict(green_bar_count=1,hold_minutes=1,contracts=1)
    request['execution_settings'].update(slippage_ticks=0,commission_per_contract_per_side='0')
    runs=[];reports=[]
    for workers in (1,2):
        client.app.state.prop_analyses.runtime.workers=workers
        response=client.post('/api/backtests',json={**request,'reuse_results':False,'reuse_calculations':False});assert response.status_code==201,response.text
        record=response.json();id=record['run_metadata']['automatic_prop_analysis']['id']
        report=client.get('/api/prop-analyses/'+id+'/downloads/report.json').json()
        expected_cash(report);reports.append(report)
        assert record['summary']['trades_taken']==600 and float(record['summary']['total_net_pnl'])==180000
        assert report['runtime']['prop_execution']['workers_used']==workers
        if workers>1:assert report['runtime']['prop_execution']['worker_pids']
        runs.append(dict(workers=workers,backtest_id=record['id'],prop_id=id,performance=client.get('/api/backtests/'+record['id']+'/performance').json()))
    assert reports[0]['calculations']==reports[1]['calculations']
    (tmp_path/'parallel-verification.json').write_text(json.dumps(dict(synthetic=True,independent_cash=360000-40*(49+129),all_calculations_exact=True,runs=runs),indent=2))


def test_single_worker_optimization_never_enters_prop_pool(monkeypatch):
    runtime=Runtime(workers=1)
    def forbidden(*args):raise AssertionError('optimization entered a nested prop map')
    monkeypatch.setattr(runtime,'map',forbidden)
    with runtime.optimization(1):
        assert runtime.occupied==1
        assert map_sweep(lambda n:n*n,[2,3],50_000_000)==[4,9]
    assert runtime.occupied==0
    runtime.close()


def test_concurrent_serial_reservations_transfer_without_deadlock(monkeypatch):
    import alphaquest.prop.parallel as parallel
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    monkeypatch.setattr(parallel,'CAPACITY',2)
    runtime=Runtime(workers=2);ready=Barrier(2)
    def work():
        with runtime.activate():
            ready.wait(timeout=5)
            with runtime.parallel_slots(2) as slots:
                assert 1<=slots<=2
                assert 1<=runtime.occupied<=2
            assert runtime.occupied>=1
        return True
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(work) for _ in range(2)]
            assert all(f.result(timeout=5) for f in futures)
        assert runtime.occupied==0
    finally:runtime.close()
