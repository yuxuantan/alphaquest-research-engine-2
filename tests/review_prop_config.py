"""Read-only source-check demonstration of the simplified form on a live library.

Owns only a private browser context. Does not submit analyses, backtests or any
other writes, and does not start/stop the user's server.
"""
import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, expect


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--url',default='http://127.0.0.1:8000')
    parser.add_argument('--source',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    assert urlparse(args.url).hostname in ('localhost','127.0.0.1')
    args.output.mkdir(parents=True,exist_ok=False)
    posts=[];errors=[]
    with sync_playwright() as runtime:
        browser=runtime.chromium.launch(headless=True)
        try:
            page=browser.new_page(viewport=dict(width=1440,height=1100))
            page.on('request',lambda r:posts.append(r.url) if r.method=='POST' else None)
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(args.url+'/#backtests/report/'+args.source)
            page.locator('#report-prop-setup').click();expect(page.locator('#prop-config')).to_be_visible()
            page.locator('#prop-method').select_option('budgeted_lifecycle')
            expect(page.locator('#prop-budget-timezone')).to_have_value('America/Chicago')
            assert page.locator('#prop-advanced').get_attribute('open') is None
            page.locator('#prop-check').click()
            expect(page.locator('#prop-check-output [role=alert]')).to_contain_text('Enter your monthly fee cap')
            expect(page.locator('#prop-monthly-cap')).to_be_focused()
            assert not posts  # Required input fails locally, before an API 422.
            page.screenshot(path=str(args.output/'missing-budget-inline.png'),full_page=True)
            page.locator('#prop-monthly-cap').fill('200')
            page.locator('#prop-use-observed').click()
            page.locator('#prop-payout-preset').select_option('5')
            page.locator('#prop-activation-preset').select_option('immediate7')
            with page.expect_response(lambda r:r.url.endswith('/api/prop-analyses/check')) as response:
                with page.expect_request(lambda r:r.url.endswith('/api/prop-analyses/check') and r.method=='POST') as request:
                    page.locator('#prop-check').click()
            assert response.value.status==200,response.value.text()
            expect(page.locator('#prop-run')).to_be_enabled()
            expect(page.locator('#prop-check-output')).to_contain_text('Both phase sources checked')
            assert page.locator('#prop-advanced').get_attribute('open') is None
            checked=response.value.json();payload=request.value.post_data_json
            assert checked['settings']['BUDGET_TIMEZONE']=='America/Chicago'
            assert checked['settings']['PAYOUT_RECEIPT_DAYS']=='5'
            assert checked['settings']['ACTIVATION_DEADLINE_DAYS']=='7'
            (args.output/'source-check.json').write_text(json.dumps(checked,indent=2))
            (args.output/'request.json').write_text(json.dumps(payload,indent=2))
            page.screenshot(path=str(args.output/'main-library-ready.png'),full_page=True)
            visible=page.locator('#prop-form input:visible, #prop-form select:visible, #prop-form textarea:visible').count()
            page.set_viewport_size(dict(width=390,height=900))
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.screenshot(path=str(args.output/'main-library-mobile.png'),full_page=True)
            assert not errors,errors
            assert len(posts)==1 and posts[0].endswith('/api/prop-analyses/check'),posts
            result=dict(source_id=args.source,backtest_url=args.url+'/#backtests/report/'+args.source,
                source_check_status=response.value.status,matched_trades=checked['matched_trades'],
                observed_window=checked['source']['phase_checks'],run_enabled=True,visible_controls=visible,
                presets=dict(receipt_days='5',activation_deadline_days='7',activation_payment_delay_days='0'),
                advanced_settings_opened=False,analyses_submitted=0,backtests_submitted=0,post_requests=posts,
                javascript_errors=errors,browser='closed in finally',server='Existing server left running; no server started.')
            (args.output/'verification.json').write_text(json.dumps(result,indent=2))
            print(json.dumps({k:result[k] for k in ('source_id','source_check_status','matched_trades','run_enabled','analyses_submitted','backtests_submitted')},indent=2))
        finally:browser.close()


if __name__=='__main__':main()
