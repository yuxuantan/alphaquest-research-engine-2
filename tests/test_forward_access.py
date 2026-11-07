from fastapi.testclient import TestClient
from alphaquest.app import create_app
from alphaquest.research_access import ResearchAccess
from tests.test_research_access import upload,reservation_request
from tests.test_forward_reconcile import declaration,fixture,time
from tests.test_forward_store import raw
from alphaquest.forward_monitoring import ForwardStore
from alphaquest.forward_access import exposure_adapter


def test_supplied_protected_observations_preserved_without_clean_holdout_claim(tmp_path):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        dataset=upload(client,'UTC');request=reservation_request()
        endpoint='/api/datasets/'+dataset['id']+'/research-reservations'
        reservation=client.post(endpoint,json=request);assert reservation.status_code==201,reservation.text
        analyses=client.app.state.prop_analyses;guard=client.app.state.store.research_access
        store=ForwardStore(analyses,record_exposure=exposure_adapter(guard),clock=lambda:time(20))
        d=declaration();store.create(d);payload=raw()
        checked=store.check_events(d.monitor_id,payload)
        assert checked['research_access']['protected_conflicts'][0]['reservation_id']==request['request_id']
        assert guard.get(request['request_id'])['status']=='RESERVED'
        assert store.events(d.monitor_id)['total']==0
        access=client.post(endpoint+'/preview',json=request).json()['access']
        assert access['status']=='PREVIOUSLY_ACCESSED'
        saved=store.append(d.monitor_id,payload)
        assert saved['research_access']['event_id']==checked['research_access']['event_id']
        store.clock=lambda:time(30)
        assert store.append(d.monitor_id,payload)['research_access']['event_id']==checked['research_access']['event_id']
        assert store.events(d.monitor_id)['total']==17
        assert client.get('/api/datasets/'+dataset['id']+'/csv').status_code==409


def test_nonfinancial_status_batch_does_not_invent_price_access(tmp_path):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        dataset=upload(client,'UTC');request=reservation_request();endpoint='/api/datasets/'+dataset['id']+'/research-reservations'
        assert client.post(endpoint,json=request).status_code==201
        store=ForwardStore(client.app.state.prop_analyses,record_exposure=exposure_adapter(client.app.state.store.research_access),clock=lambda:time(20))
        d=declaration();store.create(d)
        result=store.append(d.monitor_id,raw(fixture()[-2:]))
        assert result['research_access']['status']=='NO_MARKET_OR_FINANCIAL_OBSERVATION'
        assert client.post(endpoint+'/preview',json=request).json()['access']['status']=='ELIGIBLE_UNDER_DECLARED_LOCAL_SCOPE'
