"""Streamed SCID upload -> actual order-flow backtest -> native Prop Sim portal."""
import json,os,pytest,struct
from decimal import Decimal
from hashlib import sha256
from datetime import timedelta
from dataclasses import replace
from pathlib import Path
from research_fixtures import ResearchHTTPClient
from test_backtests_browser import browser,page,portal as base_portal,playwright
from test_native_replay_browser import configure,run
from test_tick_datasets import native_scid,native_source
from native_replay_fixtures import bars


@pytest.fixture
def portal(tmp_path):
    directory=Path(os.environ.get('AQ_TICK_PRODUCT_DIR',tmp_path))
    directory.mkdir(parents=True,exist_ok=True)
    yield from base_portal.__wrapped__(directory)


def test_upload_tick_source_and_run_orderflow_percentage_prop_in_portal(page,portal,tmp_path):
    tmp_path=Path(os.environ.get('AQ_TICK_PRODUCT_DIR',tmp_path));tmp_path.mkdir(parents=True,exist_ok=True)
    values=bars();values.append(replace(values[-1],bar_number=len(values)+1,timestamp_utc=values[-1].timestamp_utc+timedelta(days=1)))
    raw=native_scid(values);path=tmp_path/'SYNTHETIC-MNQ-trades.scid';path.write_bytes(raw)
    page.goto(portal['url']+'/#datasets')
    page.locator('#dataset-format').select_option('ticks')
    page.locator('#csv-file').set_input_files(path)
    page.locator('#dataset-name').fill('SYNTHETIC MNQ ordered ticks')
    page.locator('#symbol').fill('MNQ')
    page.locator('#dataset-tick-size').fill('.25');page.locator('#dataset-point-value').fill('2')
    invalid=bytearray(raw);struct.pack_into('<I',invalid,80,2)
    rejected=tmp_path/'SYNTHETIC-aggregated.scid';rejected.write_bytes(invalid)
    page.locator('#csv-file').set_input_files(rejected)
    page.locator('#dataset-name').fill('SYNTHETIC aggregated source must reject')
    page.locator('#validate-button').click()
    playwright.expect(page.locator('#validation-result')).to_contain_text('individual trade records',timeout=60000)
    page.screenshot(path=str(tmp_path/'rejected-aggregated-record.png'),full_page=True)
    page.locator('#csv-file').set_input_files(path)
    page.locator('#dataset-name').fill('SYNTHETIC MNQ ordered ticks')
    page.locator('#validate-button').click()
    playwright.expect(page.locator('#validation-result')).to_contain_text('Imported SYNTHETIC MNQ ordered ticks',timeout=60000)
    playwright.expect(page.get_by_role('link',name='Flow CSV',exact=True)).to_be_visible()
    page.screenshot(path=str(tmp_path/'tick-source-upload.png'),full_page=True)
    with ResearchHTTPClient(base_url=portal['url'],timeout=180) as client:
        dataset=next(d for d in client.get('/api/datasets').json() if d['name']=='SYNTHETIC MNQ ordered ticks')
        assert client.get(f"/api/datasets/{dataset['id']}/ticks/source/0").content==raw
        flow=client.get(f"/api/datasets/{dataset['id']}/ticks/flow");assert flow.status_code==200 and 'delta_pct' in flow.text
        original=native_source(client,dataset_id=dataset['id'])
    configure(page,portal,original)
    report=run(page,portal,tmp_path)
    response=page.request.get(portal['url']+'/api/backtests/'+report['native_backtest_id']+'/trades');assert response.ok
    assert Decimal(report['calculations']['trace'][-1]['state_after']['balance'])==Decimal('50160')
    trades=response.json()['items'];assert [t['contracts'] for t in trades]==[10,9,5]
    assert [float(t['net_pnl']) for t in trades]==[-120,180,100]
    page.screenshot(path=str(tmp_path/'tick-percentage-prop-result.png'),full_page=True)
    downloads={}
    urls={'source-report.json':f"/api/backtests/{original['id']}",
          'source-trades.csv':f"/api/backtests/{original['id']}/exports/trades",
          'source-risk.csv':f"/api/backtests/{original['id']}/exports/intratrade_risk",
          'native-trades.csv':f"/api/backtests/{report['native_backtest_id']}/exports/trades",
          'prop-report.json':f"/api/prop-analyses/{report['id']}/downloads/report.json",
          'prop-analysis.zip':f"/api/prop-analyses/{report['id']}/downloads/analysis.zip"}
    for name,url in urls.items():
        saved=page.request.get(portal['url']+url);assert saved.ok
        (tmp_path/name).write_bytes(saved.body());downloads[name]=sha256(saved.body()).hexdigest()
    (tmp_path/'product-evidence.json').write_text(json.dumps(dict(dataset_id=dataset['id'],source_id=original['id'],analysis_id=report['id'],native_backtest_id=report['native_backtest_id'],source_sha256=sha256(raw).hexdigest(),downloads=downloads,expected=dict(quantities=[10,9,5],net_pnls=[-120,180,100],cash_balance=50160,scope="SYNTHETIC historical execution oracle, no forecast or trading qualification"),trades=trades),indent=2))
