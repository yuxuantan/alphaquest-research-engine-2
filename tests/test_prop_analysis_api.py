import json
from pathlib import Path
from threading import Event
import time
from fastapi.testclient import TestClient
import pytest
from alphaquest.app import create_app
from alphaquest.backtest_runs import RunStore

FIXTURES=Path(__file__).parent/'fixtures/backtest_contract'

def backtest(client,name='arithmetic_5m',quantity=2):
    d=client.post('/api/datasets',params=dict(filename=name+'.csv',name='SYNTHETIC '+name,source_timezone='UTC',tick_size='.25',point_value='10'),content=(FIXTURES/(name+'.csv')).read_bytes()).json()
    r=client.post('/api/backtests',json=dict(dataset_id=d.get('id',d.get('dataset_id')),strategy_id='consecutive_green_hold',strategy_parameters=dict(green_bar_count=3,hold_minutes=20,contracts=quantity),execution_settings=dict(initial_capital='10000',tick_size='.25',point_value='10',slippage_ticks=1,commission_per_contract_per_side='1')))
    assert r.status_code==201,r.text
    return r.json()

def wait(client,id):
    until=time.monotonic()+20
    while time.monotonic()<until:
        r=client.get('/api/prop-analyses/'+id).json()
        if r['status'] in ('complete','error'):return r
        time.sleep(.02)
    raise AssertionError('Analysis did not complete')

@pytest.fixture
def portal(tmp_path):
    with TestClient(create_app(tmp_path/'datasets.sqlite3')) as client:yield client


def export_for(client, record, tmp_path):
    import csv,zipfile,xml.etree.ElementTree as E
    from datetime import datetime
    columns=['Trade #','Type','Date','Contracts','Profit ($)','Drawdown ($)','Run-up ($)']
    rows=list(csv.DictReader((client.app.state.runs.root/record['id']/'trades.csv').open()))
    ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    sheet=E.Element('worksheet',xmlns=ns);data=E.SubElement(sheet,'sheetData')
    values=[columns]
    for r in rows:
        dt=datetime.fromisoformat(r['entry_time_utc'].replace('Z','+00:00')).replace(tzinfo=None)
        serial=(dt-datetime(1899,12,30)).total_seconds()/86400
        values.append([r['trade_number'],'EntryLong' if r['side']=='long' else 'EntryShort',str(serial),r['contracts'],r['net_pnl'],'8','30'])
    for i,row in enumerate(values,1):
        parent=E.SubElement(data,'row',r=str(i))
        for j,value in enumerate(row):
            c=E.SubElement(parent,'c',r=f'{chr(65+j)}{i}',t='inlineStr');E.SubElement(E.SubElement(c,'is'),'t').text=str(value)
    path=tmp_path/'SYNTHETIC export.xlsx'
    with zipfile.ZipFile(path,'w') as z:
        z.writestr('xl/workbook.xml',f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="List of Trades" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr('xl/worksheets/sheet1.xml',E.tostring(sheet))
    return path

@pytest.fixture
def runner(monkeypatch):
    from alphaquest.prop import bridge
    def identity():return dict(executable='Synthetic test executable',version='fixture',sha256='a'*64)
    def run(input_file,settings_file,output,identity,progress):
        from alphaquest.prop.bridge_source import export_trades
        rows=export_trades(input_file);settings=json.loads(settings_file.read_text())
        output.mkdir();progress('Synthetic runner result transport')
        # This test double checks transport only, never claims Monte Carlo parity.
        result=dict(status='ok',exit_code=0,demo=False,load_errors=0,files=[dict(trades=len(rows))],settings_form=settings,
                    part1={'hero':[]},part2={'alone':{'rows':[]}},account={},dates={},settings={},chart_files={},
                    sections=[{'title':'Synthetic transport check','blocks':[{'type':'table','columns':['Net source P&L'],'rows':[[str(sum(r['net'] for r in rows))]]}]}])
        (output/'results.json').write_text(json.dumps(result));(output/'report.html').write_text('<html>Synthetic transport fixture</html>')
        return result
    monkeypatch.setattr(bridge,'engine_identity',identity);monkeypatch.setattr(bridge,'run_bridge',run)
    return run


def test_checked_native_costs_bridge_downloads_and_reload(portal,tmp_path,runner):
    r=backtest(portal);path=export_for(portal,r,tmp_path)
    body=dict(source_backtest_id=r['id'],trade_file=str(path),export_timezone='UTC')
    checked=portal.post('/api/prop-analyses/check',json=body);assert checked.status_code==200,checked.text
    c=checked.json();assert c['matched_trades']==1
    # Reference 40 - source commissions 4 - source slippage 10 = net 26.
    # Bridge receives the already-net 26, with measured excursions from export.
    assert c['source']['reconciliation']['source_totals']['net_pnl']=='26.00'
    assert c['source']['bridge_input']['measured_mae_count']==1
    job=portal.post('/api/prop-analyses',json=body).json();assert wait(portal,job['id'])['status']=='complete'
    response=portal.get(f"/api/prop-analyses/{job['id']}/downloads/report.json");report=response.json()
    assert report['format_version']==2 and report['source']['backtest']==r
    assert report['bridge_results']['sections'][0]['blocks'][0]['rows']==[['26.00']]
    assert report['settings']['BLOCK_DAYS']=='5'
    assert portal.get(f"/api/prop-analyses/{job['id']}/downloads/report.json").content==response.content
    assert 'measured_mae' in portal.get(f"/api/prop-analyses/{job['id']}/downloads/trades.csv").text
    assert portal.get(f"/api/prop-analyses/{job['id']}/files/bridge/results.json").json()==report['bridge_results']
    assert portal.get(f"/api/prop-analyses/{job['id']}/files/unknown.txt").status_code==404
    assert portal.get(f"/api/prop-analyses/{job['id']}/downloads/daily.csv").status_code==404
    import zipfile,io
    archive=zipfile.ZipFile(io.BytesIO(portal.get(f"/api/prop-analyses/{job['id']}/downloads/analysis.zip").content))
    assert json.loads(archive.read('bridge/results.json'))==report['bridge_results']
    assert archive.read('inputs/'+path.name)==path.read_bytes()


def test_rejection_before_bridge_and_legacy_requests_retired(portal,tmp_path):
    r=backtest(portal);path=export_for(portal,r,tmp_path)
    for settings in [dict(unknown=1),dict(BLOCK_DAYS='3'),dict(SLOTS='21'),dict(EVAL_PRICE='NaN'),dict(OUT_OF_SAMPLE_FROM='2024x')]:
        response=portal.post('/api/prop-analyses/check',json=dict(source_backtest_id=r['id'],trade_file=str(path),export_timezone='UTC',settings=settings))
        assert response.status_code==422,response.text
    assert portal.post('/api/prop-analyses',json=dict(source_backtest_id=r['id'],overrides={})).status_code==422
    wrong=portal.post('/api/prop-analyses/check',json=dict(source_backtest_id=r['id'],trade_file=str(path),export_timezone='America/Chicago'))
    assert wrong.status_code==422 and 'entry time' in wrong.text
    path.write_bytes(b'not a workbook')
    assert portal.post('/api/prop-analyses/check',json=dict(source_backtest_id=r['id'],trade_file=str(path))).status_code==422


def test_duplicate_and_failed_operations_remain_errors(portal,tmp_path,monkeypatch):
    import alphaquest.prop.store as store
    r=backtest(portal);path=export_for(portal,r,tmp_path);entered=Event();release=Event()
    def failing(*a,**kw):entered.set();assert release.wait(10);raise RuntimeError('Bridge not licensed fixture')
    monkeypatch.setattr(store,'run_analysis',failing)
    body=dict(source_backtest_id=r['id'],trade_file=str(path),export_timezone='UTC')
    a=portal.post('/api/prop-analyses',json=body).json();assert entered.wait(5)
    try:
        b=portal.post('/api/prop-analyses',json=body).json();assert a['id']==b['id']
        assert portal.get(f"/api/prop-analyses/{a['id']}/downloads/report.json").status_code==409
    finally:release.set()
    result=wait(portal,a['id']);assert result['status']=='error' and 'not licensed' in result['error']
    assert portal.get(f"/api/prop-analyses/{a['id']}/downloads/report.json").status_code==409


def test_source_cost_arithmetic_is_independent_of_decimal_context(portal,tmp_path):
    from decimal import localcontext
    from alphaquest.prop.bridge_source import prepare_source
    r=backtest(portal);path=export_for(portal,r,tmp_path)
    with localcontext() as ctx:
        ctx.prec=1
        snapshot,_=prepare_source(portal.app.state.runs,r['id'],str(path),'UTC')
    assert snapshot['reconciliation']['source_totals']['net_pnl']=='26.00'
