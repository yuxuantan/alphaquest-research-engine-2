"""Inspect sealed synthetic outputs through existing source/report portal routes.

Run after the evidence-enabled API journey; no new simulations or demo routes.
"""
import json
from pathlib import Path
import socket
from threading import Thread
import time

from playwright.sync_api import sync_playwright
import uvicorn
from alphaquest.app import create_app


def main():
    root=Path('artifacts/strategy-sizing-20261117')
    rows=json.loads((root/'summary.json').read_text())['scenarios'];observations=[]
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(channel='chrome',headless=True)
        try:
            for row in rows:
                listener=socket.socket();listener.bind(('127.0.0.1',0))
                base=f'http://127.0.0.1:{listener.getsockname()[1]}'
                server=uvicorn.Server(uvicorn.Config(create_app(Path(row['library'])/'datasets.sqlite3'),log_level='error'))
                thread=Thread(target=server.run,kwargs=dict(sockets=[listener]),daemon=True);thread.start()
                page=browser.new_page(viewport=dict(width=1440,height=1000));errors=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                try:
                    deadline=time.monotonic()+15
                    while not server.started:
                        assert thread.is_alive() and time.monotonic()<deadline
                        time.sleep(.02)
                    page.goto(base+'/#backtests/report/'+row['source_backtest_id'])
                    page.locator('#report-prop-setup').wait_for(state='visible',timeout=30000)
                    page.goto(base+'/#backtests/prop/job/'+row['analysis_id'])
                    page.locator('#prop-report').wait_for(state='visible',timeout=30000)
                    page.wait_for_function("document.querySelector('#prop-report-content').innerText.length>100")
                    text=page.locator('#prop-report-content').inner_text()
                    assert '0.2' in text,text[:1000]
                    assert not errors,errors
                    page.screenshot(path=str(root/row['folder']/'portal.png'),full_page=True)
                    observations.append(dict(folder=row['folder'],source_backtest_id=row['source_backtest_id'],analysis_id=row['analysis_id'],
                        normal_route='#backtests/prop/job/'+row['analysis_id'],page_errors=errors,visible_text=text))
                finally:
                    page.close();server.should_exit=True;thread.join(15);listener.close()
                    assert not thread.is_alive(),'Temporary portal failed to stop.'
        finally:browser.close()
    (root/'portal-inspection.json').write_text(json.dumps(dict(synthetic=True,servers_stopped=True,observations=observations),indent=2)+'\n')
    print(f'Inspected {len(observations)} saved source/report journeys; all temporary servers stopped.')


if __name__=='__main__':main()
