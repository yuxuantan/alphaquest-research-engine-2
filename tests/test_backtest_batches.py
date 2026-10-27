"""One creation endpoint and one backtest resource for single/sweep execution."""
from test_backtest_api import client,save_fixture,body
from test_optimization import optimization_body,wait_job


def test_single_and_exhaustive_requests_share_backtest_endpoint_and_reports(client):
    dataset=save_fixture(client)
    single=client.post('/api/backtests',json=body(dataset['id']))
    assert single.status_code==201,single.text
    response=client.post('/api/backtests',json=optimization_body(dataset['id']))
    assert response.status_code==202,response.text
    id=response.json()['id'];job=wait_job(client,id)
    assert job['status']=='complete'
    assert client.get('/api/backtests/batches/'+id).json()==job
    assert client.get('/api/backtests/batches').json()['items'][0]['id']==id
    results=client.get('/api/backtests/batches/'+id+'/results',params=dict(sort='total_net_pnl',direction='desc')).json()
    assert [r['metrics']['total_net_pnl'] for r in results['items']]==['39.00','26.00','13.00']
    for row in results['items']:
        saved=client.get('/api/backtests/'+row['run_id']).json()
        assert saved['summary']['total_net_pnl']==row['metrics']['total_net_pnl']
        assert client.get('/api/backtests/'+row['run_id']+'/exports/trades').status_code==200
    assert client.get('/api/backtests/batches/'+id+'/exports/results').content==client.get('/api/optimizations/'+id+'/exports/results').content
    assert client.get('/api/backtests/settings').json()==client.get('/api/optimizations/settings').json()
    assert client.get('/api/backtests/batches/'+'a'*32).status_code==404
    assert client.post('/api/backtests/batches/'+id+'/resume').status_code==409


def test_ambiguous_single_and_grid_requests_reject_before_saving(client):
    dataset=save_fixture(client);request=optimization_body(dataset['id'])
    request['strategy_parameters']=body(dataset['id'])['strategy_parameters']
    assert client.post('/api/backtests',json=request).status_code==422
    request.pop('strategy_parameters');request['method']='genetic'
    assert client.post('/api/backtests',json=request).status_code==422
    assert client.get('/api/backtests').json()['total']==0
    assert client.get('/api/backtests/batches').json()['total']==0
