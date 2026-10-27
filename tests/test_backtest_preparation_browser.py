"""Preparation scans must never look like a completed/restarted strategy replay."""
import json
from threading import Event
from test_backtests_browser import browser,page,portal,playwright,prepare,post_requests,FIXTURES
from alphaquest import backtest_api,prepared_data,strategy_features
from research_fixtures import reserved_source,register,seed_declarations


def test_real_preparation_then_replay_uses_a_single_percentage_bar(page,portal,tmp_path,monkeypatch):
    entered={name:Event() for name in ('source','features','replay')}
    release={name:Event() for name in entered}
    stages=[]
    original_data=prepared_data.prepare_data
    original_features=strategy_features.prepare_features
    original_report=backtest_api.prepare_backtest_report
    def paused_data(source,id,dates,path,progress,*args,**kwargs):
        def capture(stage,processed,total):
            progress(stage,processed,total);stages.append(dict(stage=stage,processed=processed,total=total))
            if processed==total:
                entered['source'].set();assert release['source'].wait(20)
        return original_data(source,id,dates,path,capture,*args,**kwargs)
    def paused_features(definition,prepared,values,root,progress,*args,**kwargs):
        # This real VWAP path builds all its declared pure indicators.
        def capture(stage,processed,total):
            progress(stage,processed,total);stages.append(dict(stage=stage,processed=processed,total=total))
            if processed==total:
                entered['features'].set();assert release['features'].wait(20)
        return original_features(definition,prepared,values,root,capture,*args,**kwargs)
    def paused_report(store,output,dataset,definition,parameters,config,dates,progress,**kwargs):
        def capture(stage,processed,total):
            progress(stage,processed,total);stages.append(dict(stage=stage,processed=processed,total=total))
            if stage=='replaying' and processed==0:
                entered['replay'].set();assert release['replay'].wait(20)
        return original_report(store,output,dataset,definition,parameters,config,dates,capture,**kwargs)
    monkeypatch.setattr(prepared_data,'prepare_data',paused_data)
    monkeypatch.setattr(strategy_features,'prepare_features',paused_features)
    monkeypatch.setattr(backtest_api,'prepare_backtest_report',paused_report)
    raw,split=reserved_source((FIXTURES/'arithmetic_5m.csv').read_bytes())
    uploaded=page.request.post(portal['url']+'/api/datasets',
        params=dict(filename='SYNTHETIC-progress-stages.csv',name='SYNTHETIC progress stage demonstration',source_timezone='UTC',tick_size='.25',point_value='10'),
        data=b'\xef\xbb\xbf'+raw)
    assert uploaded.status==201
    portal['saved']['arithmetic_5m']=uploaded.json()
    register(uploaded.json(),split);seed_declarations(portal['app'])
    prepare(page,portal)
    page.locator('#backtest-strategy').select_option('vwap_pullback_risk_sizing')
    requests=post_requests(page)
    bar=page.locator('#backtest-progress-bar');percent=page.locator('#backtest-progress-percent')
    try:
        page.locator('#start-backtest').click()
        assert entered['source'].wait(10)
        playwright.expect(page.locator('#backtest-progress-title')).to_contain_text('checking source bars')
        playwright.expect(page.locator('#backtest-progress-detail')).to_have_text('8 / 8 source bars checked')
        playwright.expect(percent).to_have_text('')
        assert bar.get_attribute('value') is None
        page.locator('#backtest-progress').screenshot(path=str(tmp_path/'01-source-preparation.png'))
        release['source'].set();assert entered['features'].wait(10)
        playwright.expect(page.locator('#backtest-progress-title')).to_contain_text('calculating indicators')
        playwright.expect(page.locator('#backtest-progress-detail')).to_have_text('7 / 7 indicator bars prepared')
        playwright.expect(percent).to_have_text('')
        assert bar.get_attribute('value') is None
        playwright.expect(page.locator('#backtest-progress-note')).to_contain_text('percentage bar tracks strategy replay only')
        page.locator('#backtest-progress').screenshot(path=str(tmp_path/'02-indicator-preparation.png'))
        release['features'].set();assert entered['replay'].wait(10)
        playwright.expect(page.locator('#backtest-progress-title')).to_have_text('Running backtest')
        playwright.expect(percent).to_have_text('0% of bars')
        playwright.expect(bar).to_have_attribute('value','0')
        page.locator('#backtest-progress').screenshot(path=str(tmp_path/'03-strategy-replay.png'))
    finally:
        for event in release.values():event.set()
    playwright.expect(page.locator('#backtest-completion')).to_be_visible(timeout=20000)
    assert len(requests)==1
    id=page.url.rsplit('/',1)[1]
    record=page.request.get(portal['url']+'/api/backtests/'+id).json()
    assert record['summary']['trades_taken']==0 and float(record['summary']['total_net_pnl'])==0
    assert float(record['summary']['final_equity'])==10000
    (tmp_path/'verification.json').write_text(json.dumps(dict(stages=stages,backtest=record,requests=1,expected='Default VWAP on the seven-bar arithmetic fixture produces no entries, zero net and unchanged 10,000 equity. Preparation has no replay percentage; replay begins once at zero.'),indent=2))
