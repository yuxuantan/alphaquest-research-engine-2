"""Recalculate one affected saved Lucid report through its ordinary UI.

Uses existing immutable backtests; never submits a backtest or edits old results.
Run only against a chosen local portal/report, with a new evidence directory.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import time
from playwright.sync_api import sync_playwright, expect


def review(url, old_id, output):
    output.mkdir(parents=True, exist_ok=False)
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        try:
            page = browser.new_page(viewport=dict(width=1440, height=1100))
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            def get(path):
                response = page.request.get(url + path)
                assert response.ok, response.text()
                return response.json()
            old = get('/api/prop-analyses/' + old_id + '/downloads/report.json')
            assert old['calculations']['funded'] is None
            source_id = old['source']['backtest']['id']
            trades = page.request.get(url + '/api/backtests/' + source_id + '/exports/trades').body()
            old_bytes = page.request.get(url + '/api/prop-analyses/' + old_id + '/downloads/report.json').body()
            (output / 'old-report.json').write_bytes(old_bytes)
            posts = []
            page.on('request', lambda request: posts.append(request.url) if request.method == 'POST' else None)
            page.goto(url + '/#backtests/prop/job/' + old_id)
            expect(page.locator('#prop-report')).to_be_visible(timeout=30000)
            expect(page.locator('#prop-report-content')).to_contain_text('Saved earlier model:')
            page.screenshot(path=str(output / '01-earlier-report.png'), full_page=True)
            page.get_by_role('link', name='Configure new analysis', exact=True).first.click()
            expect(page.locator('#prop-config')).to_be_visible()
            expect(page.locator('#prop-model')).to_have_value('1')
            expect(page.locator('#prop-eval-fee')).to_have_value(old['settings']['EVAL_PRICE'])
            expect(page.locator('#prop-slots')).to_have_value(old['settings']['SLOTS'])
            with page.expect_response(lambda r: r.url.endswith('/api/prop-analyses/check')) as checked:
                page.locator('#prop-check').click()
            assert checked.value.status == 200, checked.value.text()
            check = checked.value.json()
            assert check['settings'] == old['settings']
            assert check['source'] == old['source']
            (output / 'source-check.json').write_text(json.dumps(check, indent=2))
            page.screenshot(path=str(output / '02-source-check.png'), full_page=True)
            expect(page.locator('#prop-run')).to_be_enabled()
            with page.expect_response(lambda r: r.url.endswith('/api/prop-analyses') and r.request.method == 'POST') as submitted:
                page.locator('#prop-run').click()
            assert submitted.value.status == 202, submitted.value.text()
            new_id = submitted.value.json()['id']
            assert new_id != old_id
            print('New analysis:', new_id, flush=True)
            last = None
            deadline = time.monotonic() + 900
            while not page.locator('#prop-report').is_visible():
                assert time.monotonic() < deadline, 'Analysis exceeded review timeout'
                job = get('/api/prop-analyses/' + new_id)
                assert job['status'] != 'error', job
                if job['progress'] != last:
                    print(job['status'], job['progress'], flush=True)
                    last = job['progress']
                page.wait_for_timeout(1000)
            report = get('/api/prop-analyses/' + new_id + '/downloads/report.json')
            c = report['calculations']
            assert c['funded'] is not None and c['history'] is not None
            assert c['training_economics']['funding_chain_simulations'] == 20000
            assert c['training_economics']['funding_chain_diagnostics']['censored_paths'] == 0
            assert c['training_economics']['funding_chain_diagnostics']['continued_paths'] > 0
            assert report['source'] == old['source'] and report['settings'] == old['settings']
            page.screenshot(path=str(output / '03-funded-outcomes.png'), full_page=True)
            page.get_by_role('tab', name='Evaluation', exact=True).click()
            expect(page.locator('#prop-view-evaluation')).to_contain_text('20,000 sessions')
            page.screenshot(path=str(output / '04-continuation-calibration.png'), full_page=True)
            page.get_by_role('tab', name='Historical replay', exact=True).click()
            page.screenshot(path=str(output / '05-historical-net.png'), full_page=True)
            page.get_by_role('tab', name='Source & model', exact=True).click()
            with page.expect_download() as download:
                page.get_by_role('link', name='Training acquisition calibration (JSON)', exact=True).click()
            download.value.save_as(output / 'training_economics.json')
            with page.expect_download() as download:
                page.get_by_role('link', name='Download all results (ZIP)', exact=True).click()
            download.value.save_as(output / 'analysis.zip')
            (output / 'new-report.json').write_text(json.dumps(report, indent=2))
            page.reload()
            expect(page.locator('#prop-report')).to_be_visible(timeout=30000)
            assert not any('/api/backtests' in path for path in posts), posts
            assert page.request.get(url + '/api/prop-analyses/' + old_id + '/downloads/report.json').body() == old_bytes
            assert page.request.get(url + '/api/backtests/' + source_id + '/exports/trades').body() == trades
            assert not errors, errors
            verification = dict(old_id=old_id, new_id=new_id, source_id=source_id,
                model_version=report['model_version'], old_report_preserved=True, source_trades_preserved=True,
                source_trade_sha256=sha256(trades).hexdigest(), backtest_posts=0, source_check_matched_trades=check['matched_trades'],
                training=c['training_economics'], evaluation=c['evaluation'],
                funded_size=c['funded']['selected']['micros'], historical_net=c['history']['totals']['net'],
                reload_read_only=True, javascript_errors=errors)
            (output / 'verification.json').write_text(json.dumps(verification, indent=2))
            print(json.dumps({k: verification[k] for k in ('new_id', 'funded_size', 'historical_net', 'backtest_posts')}), flush=True)
        finally:browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://localhost:8000')
    parser.add_argument('--old-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    review(args.url.rstrip('/'), args.old_id, args.output)
