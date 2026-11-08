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


def test_complete_claimed_quiet_sessions_are_exposed_not_only_attestation_clock(tmp_path):
    from alphaquest.forward_contracts import MonitorDeclaration, EventBatch
    from alphaquest.forward_reconcile import digest
    from uuid import uuid4
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:
        dataset=upload(client,'UTC');request=reservation_request();endpoint='/api/datasets/'+dataset['id']+'/research-reservations'
        assert client.post(endpoint,json=request).status_code==201
        body=declaration().model_dump(mode='json')
        body['policy_binding']=dict(campaign_id='a'*32,application_id='b'*32,phase='funded',package_sha256='c'*64)
        body['forecast_observation']=dict(first_session='2026-01-05',cutoff_date_exclusive='2026-01-12',
            open_sessions=['2026-01-05','2026-01-06','2026-01-07','2026-01-08','2026-01-09'],early_closes={},
            calendar_alignment='exact_saved_dates',account_id='synthetic')
        d=MonitorDeclaration.model_validate(body)
        event=dict(kind='account_coverage',event_id='coverage',event_time_utc='2026-01-12T06:00:00Z',
            plan_sha256=digest(d.forecast_observation.model_dump(mode='json')),package_sha256='c'*64,account_id='synthetic',
            first_session='2026-01-05',cutoff_date_exclusive='2026-01-12',coverage='complete',fresh_account=True,
            initial_balance='50000',currency='USD',frozen_policy_followed=True,terminal_status='active_at_cutoff',replacement_accounts=0,
            pending_trader_cash='0',complete_through_utc='2026-01-12T06:00:00Z',statement='Supplied known zero-trade session outcomes')
        batch=EventBatch(batch_id=uuid4().hex,source_id='fixture',events=[event])
        result=exposure_adapter(client.app.state.store.research_access)(d,batch,'d'*64,'2026-01-12T06:00:01Z')
        assert result['protected_conflicts'][0]['reservation_id']==request['request_id']
        assert client.post(endpoint+'/preview',json=request).json()['access']['status']=='PREVIOUSLY_ACCESSED'
        assert client.app.state.store.research_access.get(request['request_id'])['status']=='RESERVED'
