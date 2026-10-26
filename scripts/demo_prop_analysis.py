"""Run a real portal demonstration on a completed source, with saved downloads.

Uses an ephemeral server/socket; stops only that server. Does not modify source
backtests/datasets or older analysis results. Counts are explicit demo overrides.
"""
import argparse,json,socket,sys,time,io,csv
import httpx
from pathlib import Path
from threading import Thread
import uvicorn
from playwright.sync_api import sync_playwright,expect
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from alphaquest.app import create_app
from alphaquest.prop.analysis import clean,prepare
from alphaquest.backtest_runs import RunStore
from prop_notebook_reference import reference


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--increment',type=int,required=True);parser.add_argument('--fixture',choices=['payout','blown','inactive','horizon']);parser.add_argument('--source',default='d63265dc923444c799c2dfc59e090e76');parser.add_argument('--data-dir',type=Path,default=Path('data'));args=parser.parse_args()
    output=Path('artifacts/prop-notebook')/f'increment{args.increment}';output=output/args.fixture if args.fixture else output;output.mkdir(parents=True,exist_ok=True)
    overrides=dict(PROP_MC_SIMS=256,N_SPAGHETTI=40,PAYOUT_SIMS=256,PAYOUT_SWEEP_SIMS=128,LIFETIME_SIMS=256,LIFETIME_SWEEP_SIMS=128)
    app=create_app(args.data_dir/'datasets.sqlite3');sock=socket.socket();sock.bind(('127.0.0.1',0));url=f'http://127.0.0.1:{sock.getsockname()[1]}'
    server=uvicorn.Server(uvicorn.Config(app,log_level='error',loop='asyncio'));thread=Thread(target=server.run,kwargs=dict(sockets=[sock]),daemon=True);thread.start()
    try:
        deadline=time.monotonic()+15
        while not server.started:
            assert time.monotonic()<deadline and thread.is_alive();time.sleep(.02)
        if args.fixture:
            pnl={'payout':600,'blown':-1100,'inactive':0,'horizon':100}[args.fixture]
            stream=io.StringIO();writer=csv.writer(stream);writer.writerow(['Date','Time','Open','High','Low','Close','Volume','UpVol','DownVol'])
            for i in range(7):
                close=9998+i if i<3 else (10000+pnl if i==6 else 10000)
                opening=close-1 if i<3 else 10000
                writer.writerow(['01/05/2026',f'10:{i*5:02d}',opening,max(opening,close),min(opening,close),close,100,60,40])
            csv_text=stream.getvalue();(output/'synthetic-source.csv').write_text(csv_text)
            with httpx.Client(base_url=url,timeout=30) as client:
                d=client.post('/api/datasets',params=dict(filename='SYNTHETIC-'+args.fixture+'.csv',name='SYNTHETIC notebook boundary '+args.fixture,source_timezone='UTC',tick_size='1',point_value='1'),content=csv_text.encode()).json()
                dataset=d.get('id',d.get('dataset_id'))
                source=client.post('/api/backtests',json=dict(dataset_id=dataset,strategy_id='consecutive_green_hold',strategy_parameters=dict(green_bar_count=3,hold_minutes=20,contracts=2),execution_settings=dict(initial_capital='50000',slippage_ticks=0,commission_per_contract_per_side='0',tick_size='1',point_value='1')))
                assert source.status_code==201,source.text
                source=source.json();args.source=source['id'];assert float(source['summary']['total_net_pnl'])==pnl*2
                (output/'source-backtest.json').write_text(json.dumps(source,indent=2))
            overrides.update(OOS_START_DATE=None,VALIDATION_SPLIT=0,SWEEP_CONTRACTS=[1],PAYOUT_CONTRACTS=[1],PAYOUT_MAX_HORIZON=30)
        with sync_playwright() as runtime:
            browser=runtime.chromium.launch(headless=True);page=browser.new_page(viewport=dict(width=1440,height=1100));errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(url+f'/#backtests/report/{args.source}');page.locator('#report-prop-setup').click();expect(page.locator('#prop-config')).to_be_visible()
            page.locator('#prop-increment').select_option(str(args.increment));page.locator('#prop-sims').fill('256');page.locator('#prop-pricing').select_option('49+129');page.locator('#prop-overrides').fill(json.dumps(overrides));page.locator('#prop-check').click();expect(page.locator('#prop-run')).to_be_enabled(timeout=20000)
            page.screenshot(path=str(output/'source-check.png'),full_page=True)
            page.locator('#prop-run').click();expect(page.locator('#prop-report')).to_be_visible(timeout=180000)
            page.screenshot(path=str(output/'report.png'),full_page=True)
            for name in ('report.json','trades.csv','daily.csv','analysis.zip'):
                with page.expect_download() as event:page.get_by_role('link',name=name+' ↓',exact=True).click()
                event.value.save_as(output/name)
            result=json.loads((output/'report.json').read_text());posts=[];page.on('request',lambda r:posts.append(r.url) if r.method=='POST' else None)
            page.reload();expect(page.locator('#prop-report')).to_be_visible(timeout=20000)
            page.locator('#prop-back').click();page.locator('#report-prop-setup').click();page.locator(f'#prop-saved a[href$="{result["id"]}"]').click();expect(page.locator('#prop-report')).to_be_visible(timeout=20000)
            assert not posts and not errors
            browser.close()
        f,s,settings,origins=prepare(RunStore(args.data_dir),args.source,overrides,'source','49+129')
        oracle=reference(f,settings,args.increment)
        # Compare arrays and all numerical aggregates, with exact discrete counts.
        assert result['evaluation']==clean(oracle['res'])
        assert result['daily']==clean(oracle['daily_full'].to_dict('records'))
        assert result['paths']['equity']==clean(oracle['paths'])
        assert result['paths']['outcomes']==clean(oracle['outcomes'])
        columns=['trade_id','direction','datetime','date','contracts','profit_usd','costs_usd','profit_net_usd','initial_risk_usd','r_mult']
        assert [{k:r[k] for k in columns} for r in result['trades']]==clean(oracle['df_sim'][columns].to_dict('records'))
        assert result['statistics']['bootstrap_usd_ci']==[oracle['lo'],oracle['hi']] if args.increment==1 else True
        if args.increment>=2:
            assert result['sizing']['sweep']==clean(oracle['sweep_data']);assert result['sizing']['validation']==clean(oracle['_val'])
            assert result['sizing']['staged_raw']==clean(oracle['_rows']);assert result['sizing']['flat_pass_rate']==oracle['_p_flat']
        if args.increment>=3:
            assert result['funded']['sweep']==clean(oracle['payout_sweep']);assert result['funded']['selected']==clean(oracle['best']);assert result['funded']['detail']==clean(oracle['detail'])
        if args.increment>=4:
            assert result['lifetime']['sweep']==clean(oracle['lifetime_sweep']);assert result['lifetime']['selected']==clean(oracle['best_life'])
            assert result['economics']['acquisition_cost']==clean(oracle['_acq_cost']);assert result['economics']['expected_net']==clean(oracle['_net']);assert result['economics']['return_multiple']==clean(oracle['_mult'])
            assert result['robustness_raw']==clean(oracle['_reference_robustness'])
        if args.fixture:
            detail=result['funded']['detail'];key={'payout':'qualified','blown':'blown','inactive':'closed_inactive','horizon':'timeout'}[args.fixture]
            assert detail[key]==256
            if args.fixture=='payout':assert detail['expected_payout']==900 and detail['days_to_qualify']==[5]*256
        evidence=dict(id=result['id'],source=args.source,increment=args.increment,settings=result['settings'],runtime=result['runtime'],notebook_sha256=result['notebook_sha256'],fresh_notebook_comparison='exact match; all compared arrays/counts/aggregates, no CI-overlap criterion',reload_reopen_without_post=True,browser_errors=errors,evaluation=result['evaluation'],statistics=result['statistics'],server='ephemeral; stopped on script exit')
        (output/'validation.json').write_text(json.dumps(evidence,indent=2));print(json.dumps(dict(id=result['id'],evidence=str(output),counts={k:result['evaluation'][k] for k in ('passed','fail_dd','fail_time')})))
    finally:
        server.should_exit=True;thread.join(30);sock.close();assert not thread.is_alive(),'Temporary server did not stop'

if __name__=='__main__':main()
