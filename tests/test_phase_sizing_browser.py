"""Declared sizing policies through the ordinary import/phase-campaign workflow."""
from decimal import Decimal
from hashlib import sha256
import json
import re

import pytest

from research_fixtures import ResearchHTTPClient
from sizing_fixtures import sizing_bytes
from test_backtests_browser import browser, page, portal, playwright
from test_campaign_assessments import saved_is
from test_trade_import_browser import choose_export


def configure_policies(page, *, caps='3,40'):
    page.locator('.campaign-sizes').fill(caps)
    page.locator('.campaign-sizing-mode').select_option('policies')
    page.locator('.campaign-planning-commission').fill('0')
    page.locator('.campaign-policy-dollars').fill('100')
    page.locator('.campaign-add-policy').click()
    policy = page.locator('.campaign-sizing-policy').nth(1)
    policy.locator('.campaign-policy-kind').select_option('percentage_risk')
    policy.locator('.campaign-policy-percent').fill('0.2')
    policy.locator('.campaign-policy-reference').select_option('current_account_balance')
    page.locator('.campaign-add-policy').click()
    page.locator('.campaign-policy-dollars').nth(2).fill('1')


def sizing_evidence(candidate):
    return candidate.get('component', {}).get('provenance', {}).get('sizing') or candidate['provenance']['sizing']


def decision_value(decision, key):
    return decision.get(key, decision.get('decision', {}).get(key))


@pytest.mark.parametrize('phase', ['evaluation', 'funded'])
def test_imported_causal_sizing_campaign_membership_decisions_downloads_and_reopen(page, portal, tmp_path, phase):
    url = portal['url']
    content = sizing_bytes()
    (tmp_path/'SYNTHETIC-causal-sizing.json').write_bytes(content)
    page.goto(url+'/#backtests/new?import=external')
    choose_export(page, content, 'SYNTHETIC-causal-sizing.json')
    playwright.expect(page.locator('#trade-import-save')).to_be_enabled()
    page.locator('#trade-import-save').click()
    playwright.expect(page).to_have_url(re.compile(r'/#backtests/report/[a-f0-9]{32}$'))
    source_id = page.url.rsplit('/', 1)[1]
    playwright.expect(page.locator('#report-net')).to_have_text('20')
    page.locator('#report-prop-setup').click()
    page.locator('#campaign-new-'+phase).click()
    playwright.expect(page.locator('#campaign-is-start')).to_have_value('2026-01-05')
    playwright.expect(page.locator('#campaign-is-end')).to_have_value('2026-01-06')
    playwright.expect(page.locator('.campaign-source-info')).to_contain_text('IS 2026-01-05 → 2026-01-06')
    page.locator('#campaign-paths').fill('2')
    page.locator('#campaign-block').select_option('1')
    if phase == 'evaluation':
        page.locator('#campaign-chains').fill('2')
    else:
        page.locator('#campaign-horizon').fill('3')
    configure_policies(page)
    page.screenshot(path=str(tmp_path/'declared-sizing-policies.png'), full_page=True)
    page.locator('#campaign-check').click()
    playwright.expect(page.locator('#campaign-run')).to_be_enabled(timeout=30000)
    playwright.expect(page.locator('#campaign-count')).to_contain_text('6 candidates selected')
    playwright.expect(page.locator('.campaign-checks')).to_contain_text('Every declared candidate is retained')
    page.screenshot(path=str(tmp_path/'checked-sizing-candidates.png'), full_page=True)
    page.locator('#campaign-run').click()
    playwright.expect(page.locator('#prop-heading-title')).to_have_text('Research campaign', timeout=60000)
    campaign_id = page.url.rsplit('/', 1)[1]
    base = url+'/api/research-campaigns/'+campaign_id
    campaign = page.request.get(base).json()
    analysis_id = campaign['analysis_id']
    report_response = page.request.get(url+f'/api/prop-analyses/{analysis_id}/downloads/report.json')
    assert report_response.ok, report_response.text()
    report = report_response.json()
    candidates = report['calculations']['candidates']
    assert len(candidates) == 6
    playwright.expect(page.locator('#campaign-candidates tbody tr')).to_have_count(6)
    assert {(r['manifest']['configuration']['micros'], r['manifest']['configuration']['sizing']['policy']['kind'],
             r['manifest']['configuration']['sizing']['policy'].get('risk_dollars')) for r in candidates} == {
        (cap, kind, risk) for cap in (3, 40) for kind, risk in [('fixed_dollar_risk', '100'), ('percentage_risk', None), ('fixed_dollar_risk', '1')]}
    def pick(kind, cap=40, dollars=None):
        return next(r for r in candidates if r['manifest']['configuration']['micros']==cap
                    and r['manifest']['configuration']['sizing']['policy']['kind']==kind
                    and (dollars is None or r['manifest']['configuration']['sizing']['policy'].get('risk_dollars')==dollars))
    fixed, percentage, skipped, capped = pick('fixed_dollar_risk', dollars='100'), pick('percentage_risk'), pick('fixed_dollar_risk', dollars='1'), pick('fixed_dollar_risk', cap=3, dollars='100')
    fixed_first = sizing_evidence(fixed)['decisions'][:3]
    percentage_first = sizing_evidence(percentage)['decisions'][:3]
    capped_first = sizing_evidence(capped)['decisions'][:3]
    assert [d['quantity'] for d in fixed_first] == [10, 10, 5]
    assert [d['quantity'] for d in percentage_first] == [10, 9, 5]
    assert [Decimal(decision_value(d, 'denominator_value')) for d in percentage_first] == [50000, 49900, 50080]
    assert [Decimal(decision_value(d, 'planned_risk_per_mnq')) for d in fixed_first] == [10, 10, 20]
    assert [d['quantity'] for d in capped_first] == [3, 3, 3]
    assert all('user_cap' in d['reasons'] for d in capped_first)
    skip = sizing_evidence(skipped)
    assert skip['summary']['trade_count'] == 0
    assert skip['summary']['skipped_count'] == skip['summary']['decision_count'] > 0
    assert all(d['quantity']==0 and 'below_minimum_tradable_quantity' in d['reasons'] for d in skip['decisions'])
    assert report['source']['backtest']['summary']['total_net_pnl'] == '20'

    page.locator('#campaign-inspect').select_option(percentage['candidate_id'])
    playwright.expect(page.locator('#campaign-sizing-evidence')).to_contain_text('0.2% of current account balance')
    page.locator('#campaign-sizing-evidence').get_by_text('Inspect retained trade decisions', exact=True).click()
    playwright.expect(page.locator('#campaign-sizing-decisions')).to_contain_text('49900')
    page.screenshot(path=str(tmp_path/'percentage-balance-decisions.png'), full_page=True)
    page.locator('#campaign-inspect').select_option(fixed['candidate_id'])
    page.locator('#campaign-sizing-evidence').get_by_text('Inspect retained trade decisions', exact=True).click()
    page.screenshot(path=str(tmp_path/'fixed-dollar-stop-decisions.png'), full_page=True)
    page.locator('#campaign-inspect').select_option(skipped['candidate_id'])
    playwright.expect(page.locator('#campaign-sizing-evidence')).to_contain_text('below minimum tradable quantity')
    page.screenshot(path=str(tmp_path/'below-minimum-skipped.png'), full_page=True)
    page.locator('#campaign-inspect').select_option(capped['candidate_id'])
    playwright.expect(page.locator('#campaign-sizing-evidence')).to_contain_text('user cap')
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.screenshot(path=str(tmp_path/'narrow-sizing-results.png'), full_page=True)
    page.set_viewport_size({'width': 1440, 'height': 1100})

    heading = 'IS candidate results'
    if phase == 'funded':
        page.locator(f'.campaign-pick[value="{percentage["candidate_id"]}"]').check()
        page.locator('#campaign-rationale').fill('SYNTHETIC arithmetic demonstration only; no edge or live readiness claim.')
        page.locator('#campaign-freeze').click()
        heading = 'Frozen IS selection'
        playwright.expect(page.get_by_role('heading', name=heading)).to_be_visible()
        playwright.expect(page.locator('#prop-report-content')).to_contain_text('Automatic OOS launch is unavailable for imported trades')
        playwright.expect(page.locator('#campaign-launch-oos')).to_have_count(0)
        page.screenshot(path=str(tmp_path/'frozen-imported-oos-unavailable.png'), full_page=True)
    snapshots = {}
    for name, endpoint in [('report.json', f'/api/prop-analyses/{analysis_id}/downloads/report.json'),
                           ('analysis.zip', f'/api/prop-analyses/{analysis_id}/downloads/analysis.zip'),
                           ('sizing_decisions.csv', f'/api/prop-analyses/{analysis_id}/files/sizing_decisions.csv'),
                           ('sizing_summary.json', f'/api/prop-analyses/{analysis_id}/files/sizing_summary.json'),
                           ('campaign.json', f'/api/research-campaigns/{campaign_id}/exports/campaign.json'),
                           ('results.csv', f'/api/research-campaigns/{campaign_id}/exports/results.csv'),
                           ('source.json', f'/api/backtests/{source_id}/exports/source')]:
        response = page.request.get(url+endpoint)
        assert response.ok, response.text()
        snapshots[endpoint] = response.body()
        (tmp_path/name).write_bytes(response.body())
    assert (tmp_path/'source.json').read_bytes() == content
    posts = []
    page.on('request', lambda request: posts.append(request.url) if request.method=='POST' else None)
    page.reload()
    playwright.expect(page.get_by_role('heading', name=heading)).to_be_visible()
    assert posts == []
    for endpoint, before in snapshots.items():
        assert page.request.get(url+endpoint).body() == before
    (tmp_path/'browser-evidence.json').write_text(json.dumps(dict(phase=phase, source_id=source_id,
        campaign_id=campaign_id, analysis_id=analysis_id, candidates=6, raw_sha256=sha256(content).hexdigest(),
        first_simulated_session=dict(fixed_dollar_100_quantities=[10, 10, 5], current_balance_point2percent_quantities=[10, 9, 5],
                                     percentage_reference_balances=[50000, 49900, 50080], planned_risk_per_mnq=[10, 10, 20], hard_cap3_quantities=[3, 3, 3]),
        risk1_skips_all=True, source_net='20', source_fees='0', source_slippage='0', reopen_posts=posts,
        qualification_scope='Synthetic causal sizing arithmetic and local independent phase calculation; no provider parity, future outcomes or trading readiness.',
        downloads={path.rsplit('/', 1)[1]:sha256(content).hexdigest() for path, content in snapshots.items()},
        server='Owned temporary uvicorn server stopped by portal fixture.'), indent=2))


def test_native_decisions_download_and_dynamic_policy_requires_rerun(page, portal, tmp_path):
    url = portal['url']
    with ResearchHTTPClient(base_url=url, timeout=300) as client:
        source = saved_is(client)
    page.goto(url+'/#backtests/report/'+source['id'])
    playwright.expect(page.locator('#report-decisions-download')).to_be_visible()
    playwright.expect(page.locator('#report-storage-note')).to_contain_text('A captured decision may have no initial stop')
    response = page.request.get(url+page.locator('#report-decisions-download').get_attribute('href'))
    assert response.ok
    (tmp_path/'execution_decisions.jsonl').write_bytes(response.body())
    assert sha256(response.body()).hexdigest() == source['execution_decisions']['sha256']
    page.screenshot(path=str(tmp_path/'native-entry-decision-download.png'), full_page=True)
    page.locator('#report-prop-setup').click()
    page.locator('#campaign-new-evaluation').click()
    page.locator('.campaign-sizing-mode').select_option('policies')
    page.locator('.campaign-planning-commission').fill('0')
    page.locator('#campaign-check').click()
    playwright.expect(page.locator('#campaign-status')).to_contain_text('rerun', ignore_case=True, timeout=30000)
    playwright.expect(page.locator('#campaign-run')).to_be_disabled()
    page.screenshot(path=str(tmp_path/'native-dynamic-rerun-required.png'), full_page=True)
