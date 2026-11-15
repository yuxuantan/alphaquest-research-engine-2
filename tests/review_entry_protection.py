"""Save a normal-product synthetic mechanics -> IS Broad -> report demonstration.

PYTHONPATH=.:tests ALPHAQUEST_TEST_BROWSER_CHANNEL=chrome .venv/bin/python \
  tests/review_entry_protection.py --output artifacts/twin-entry-protection-NEW
Uses a new isolated library and stops its temporary server on exit.
"""
import argparse
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright, expect

from review_optimization_portal import serve_review
from test_entry_protection_sensitivity import start_twin_broad, upload_inconclusive_case


def review(output, url, *, oco=False):
    with httpx.Client(base_url=url, timeout=60) as client:
        workflow, job, raw = start_twin_broad(client, workers=2, oco=oco)
        prefix = '/api/campaign-workflows/'+workflow['id']
        rows = client.get(prefix+'/broad/results').json()['items']
        assert [Decimal(r['metrics']['total_net_pnl']) for r in rows] == ([-412,-52] if oco else [338,-52])
        record = client.get('/api/backtests/'+rows[1]['run_id']).json()
        run = record['id']
        assert Decimal(record['entry_protection_sensitivity']['favorable_minus_primary_net_pnl']) == 390
        assert Decimal(rows[1]['screening']['metrics']['is_stress_net_profit']) == -57
        (output/'SYNTHETIC-twin-campaign.csv').write_bytes(raw)
        (output/'job.json').write_text(json.dumps(job, indent=2)+'\n')
        (output/'workflow.json').write_text(json.dumps(workflow, indent=2)+'\n')
        (output/'broad-results.json').write_text(json.dumps(rows, indent=2)+'\n')
        downloads = {}
        for kind in ('report', 'trades', 'is_screening', *[k for k in record['artifacts'] if k.startswith('entry_protection') or k=='entry_oco_ambiguities']):
            response = client.get(f'/api/backtests/{run}/exports/{kind}')
            assert response.status_code == 200, response.text
            suffix = '.json' if kind in ('report','is_screening','entry_protection_sensitivity') or kind.endswith('_report') else '.csv'
            path = output/(kind+suffix); path.write_bytes(response.content)
            downloads[path.name] = sha256(response.content).hexdigest()
        before = client.get(f'/api/backtests/{run}/exports/report').content
        with sync_playwright() as runtime:
            channel=os.environ.get('ALPHAQUEST_TEST_BROWSER_CHANNEL')
            browser=runtime.chromium.launch(**({'channel':channel} if channel else {}))
            try:
                page=browser.new_page(viewport=dict(width=1440,height=1100))
                errors=[]; page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(url+f'/#campaigns/workflows/{workflow["id"]}/is_broad')
                expect(page.locator('#broad-progress')).to_contain_text('COMPLETE · 2 / 2 trials')
                page.screenshot(path=str(output/'is-broad.png'), full_page=True)
                page.goto(url+'/#backtests/report/'+run)
                panel=page.locator('#report-entry-protection')
                expect(panel).to_be_visible()
                expect(panel.locator('tbody tr').nth(0)).to_contain_text('-52.00')
                expect(panel.locator('tbody tr').nth(1)).to_contain_text('338.00')
                expect(panel.locator('tbody tr')).to_have_count(4)
                panel.scroll_into_view_if_needed()
                panel.get_by_text('Evidence and downloads',exact=True).click()
                panel.screenshot(path=str(output/'entry-protection-sensitivity.png'))
                page.reload(); expect(panel).to_be_visible()
                assert client.get(f'/api/backtests/{run}/exports/report').content == before
                gap_raw,gap_payload=upload_inconclusive_case(client)
                gap=client.post('/api/backtests',json=gap_payload)
                assert gap.status_code==201,gap.text
                gap=gap.json();gap_id=gap['id']
                assert Decimal(gap['summary']['total_net_pnl'])==-47
                assert gap['entry_protection_sensitivity']['status']=='inconclusive'
                (output/'SYNTHETIC-diagnostic-gap.csv').write_bytes(gap_raw)
                (output/'inconclusive-report.json').write_bytes(client.get(f'/api/backtests/{gap_id}/exports/report').content)
                (output/'inconclusive-sensitivity.json').write_bytes(client.get(f'/api/backtests/{gap_id}/exports/entry_protection_sensitivity').content)
                page.goto(url+'/#backtests/report/'+gap_id)
                expect(panel).to_contain_text('Sensitivity inconclusive')
                expect(panel).to_contain_text('No session-close fill was invented')
                panel.screenshot(path=str(output/'inconclusive-sensitivity.png'))
                assert not errors, errors
            finally:
                browser.close()
        result=dict(synthetic=True, workflow_id=workflow['id'], job_id=job['id'], run_id=run,
            mechanics_attestation='Synthetic fixture checklist only; no MultiCharts parity claim.',
            expected=dict(primary_net_pnl='-52.00', stress_net_pnl='-57.00', favorable_net_pnl='338.00',
                          favorable_minus_primary='390.00', ambiguous_entries=1, oco_ambiguous_entries=1 if oco else 0),
            inconclusive_run_id=gap_id,
            actual=record['entry_protection_sensitivity'], downloads_sha256=downloads,
            report_reopened_unchanged=True, browser_errors=errors, oos_run=False,
            portal_path='/#backtests/report/'+run)
        (output/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(dict(evidence=str(output),workflow_id=workflow['id'],run_id=run,expected=result['expected']),indent=2))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--oco',action='store_true',help='Exercise both OCO entry stops in the synthetic campaign.')
    args=parser.parse_args()
    serve_review(args.output,lambda output,url:review(output,url,oco=args.oco))
