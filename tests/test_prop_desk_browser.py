"""Saved backtest → Prop Desk source check → both phases → durable results."""

from hashlib import sha256
import json
from prop_desk_fixtures import desk_calculator_sources

from research_fixtures import ResearchHTTPClient
from test_backtests_browser import browser, page, playwright, portal
from test_prop_phases import save_source


def test_fixed_prop_desk_product_journey(page, portal, tmp_path, desk_calculator_sources):
    evidence = tmp_path / 'prop-desk-evidence'
    evidence.mkdir()
    with ResearchHTTPClient(base_url=portal['url'], timeout=30) as client:
        good = save_source(client, days=8)
        bad = save_source(client, days=7, instrument='ES')

    root = portal['url']
    good_id, bad_id = good['id'], bad['id']
    page.goto(root + '/#backtests/report/' + good_id)
    playwright.expect(page.locator('#report-summary')).to_be_visible()
    page.locator('.sidebar').get_by_role('link', name='Prop Desk', exact=True).click()
    desk = page.locator('#prop-desk-screen')
    playwright.expect(page.get_by_role('heading', name='Prop Desk.', exact=True)).to_be_visible()
    source = desk.get_by_role('combobox', name='Qualified configuration')
    check = desk.get_by_role('button', name='Check source', exact=True)
    run = desk.get_by_role('button', name='Run simulation', exact=True)
    status = desk.locator('#prop-desk-check-status')
    playwright.expect(check).to_have_count(0)
    playwright.expect(run).to_be_disabled()
    source.select_option(bad_id)
    desk.get_by_role('button', name='Add to portfolio', exact=True).click()
    with page.expect_response('**/api/prop-desk') as rejected:
        run.click()
    assert rejected.value.status == 422
    (evidence / 'rejected-source.json').write_text(json.dumps(rejected.value.json(), indent=2))
    playwright.expect(status).to_contain_text('requires an identified USD NQ or MNQ')
    playwright.expect(run).to_be_enabled()
    assert page.request.get(root + '/api/prop-desk').json()['items'] == []
    page.screenshot(path=evidence / '01-rejected-source.png')

    desk.get_by_role('button', name='Remove member 1').click()
    source.select_option(good_id)
    desk.get_by_role('button', name='Add to portfolio', exact=True).click()
    desk.get_by_label('Account profile').select_option('lucidflex-50k')
    desk.get_by_label('Minimum total MNQ').fill('10')
    desk.get_by_label('Observation horizon (trading days)').fill('60')
    reports = {}
    for phase in ('evaluation', 'funded'):
        label = phase.title()
        if phase == 'funded':
            desk.get_by_role('link', name='← Prop Desk setup').click()
            desk.get_by_role('button', name='Funded', exact=True).click()
            desk.get_by_label('Minimum total MNQ').fill('3')
            desk.get_by_label('Observation horizon (trading days)').fill('30')
        with page.expect_response(lambda response: response.url == root + '/api/prop-desk'
                                  and response.request.method == 'POST') as launched:
            run.click()
        assert launched.value.status == 202
        assert 'check_sha256' not in launched.value.request.post_data_json
        (evidence / f'{phase}-launch.json').write_text(json.dumps(dict(
            request=launched.value.request.post_data_json, response=launched.value.json()), indent=2))
        playwright.expect(desk.get_by_role('heading', name=label + ' result')).to_be_visible(timeout=30000)
        job = page.url.split('analysis=', 1)[1]
        reports[phase] = job
        download_root = root + '/api/prop-analyses/' + job
        report_response = page.request.get(download_root + '/downloads/report.json')
        assert report_response.ok
        report = report_response.json()
        assert report['source']['backtest']['id'] == good_id
        assert report['model_version'] == 'prop-desk-fixed-v1'
        c = report['calculations']
        outcomes = page.request.get(download_root + '/files/path_outcomes.json')
        assert outcomes.ok and len(outcomes.json()) == 1000
        if phase == 'evaluation':
            # $3,000 per day at 10 MNQ. A $3,000 best day represents 100%,
            # 50%, then 33.3% of cumulative profit against the 40% limit.
            assert c['outcome_counts'] == dict(passed=1000, breached=0, observation_cutoff=0)
            assert c['median_trading_days_to_target'] == 3
            assert all(path == dict(outcome='passed', trading_sessions=3) for path in outcomes.json())
            playwright.expect(desk).to_contain_text('Open at observation cutoff')
            playwright.expect(desk).to_contain_text('Median trading days to target')
        else:
            # $900 per day at 3 MNQ gives five $150+ days per cycle. Every
            # five-day cycle can withdraw the $2,000 cap, paying $1,800 net.
            assert [row['median_trading_day'] for row in c['milestones']] == [5, 10, 15, 20, 25]
            assert all(row['reached'] == 1000 for row in c['milestones'])
            assert c['probability_any_payout'] == c['probability_complete_ladder'] == 1
            assert c['probability_breach_before_first_payout'] == 0
            assert c['mean_account_deductions'] == 10000
            assert c['mean_trader_receipts'] == 9000
            playwright.expect(desk.get_by_role('row').last).to_contain_text('25')
            playwright.expect(desk).to_contain_text('$10,000.00')
            playwright.expect(desk).to_contain_text('$9,000.00')

        desk.get_by_text('Local account rules applied', exact=True).click()
        page.screenshot(path=evidence / f'{phase}-desktop.png', full_page=True)
        with page.expect_download() as archive:
            desk.get_by_role('link', name='All evidence ZIP ↓').click()
        archive.value.save_as(evidence / f'{phase}-analysis.zip')
        (evidence / f'{phase}-report.json').write_bytes(report_response.body())

    page.reload()
    playwright.expect(desk.get_by_role('heading', name='Funded result')).to_be_visible()
    page.set_viewport_size({'width': 390, 'height': 844})
    mobile = page.locator('.mobile-nav')
    playwright.expect(mobile.get_by_role('link', name='Prop Desk', exact=True)).to_be_visible()
    page.locator('#prop-desk-header').get_by_role('link', name='Saved runs').click()
    page.locator(f'[data-job-id="{reports["funded"]}"]').get_by_role('link', name='View results').click()
    page.locator('#jobs-detail-content').get_by_role('link', name='Open Prop Desk').click()
    playwright.expect(desk.get_by_role('heading', name='Funded result')).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert desk.get_by_role('region', name='Payout milestones table').evaluate(
        'table => table.scrollWidth <= table.clientWidth')
    page.screenshot(path=evidence / 'funded-mobile-reopened.png', full_page=True)

    mobile.get_by_role('link', name='Prop Desk', exact=True).click()
    source.select_option(good_id)
    desk.get_by_role('button', name='Add to portfolio', exact=True).click()
    desk.get_by_label('Account profile').select_option('lucidflex-50k')
    desk.get_by_label('Minimum total MNQ').fill('10')
    desk.get_by_label('Maximum total MNQ').fill('10')
    with page.expect_response('**/api/prop-desk/basket') as chart_run:
        run.click()
    assert chart_run.value.status == 202
    inspected = chart_run.value.json()['id']
    playwright.expect(desk.get_by_label('Inspect tested size')).to_have_value('10', timeout=30000)
    playwright.expect(desk.get_by_role('img', name='Portfolio and members historical closed-trade equity')).to_be_visible()
    saved_inspection = page.request.get(root + f'/api/prop-analyses/{inspected}/downloads/report.json')
    assert saved_inspection.ok
    (evidence / 'single-size-equity-report.json').write_bytes(saved_inspection.body())

    dataset_id = good['run_metadata']['dataset']['id']
    dataset = page.request.get(root + f'/api/datasets/{dataset_id}/csv')
    assert dataset.ok
    (evidence / 'SYNTHETIC-phase-source.csv').write_bytes(dataset.body())
    (evidence / 'source-backtest.json').write_bytes(page.request.get(root + '/api/backtests/' + good_id).body())
    (evidence / 'source-trades.csv').write_bytes(page.request.get(root + '/api/backtests/' + good_id + '/exports/trades').body())
    (evidence / 'journey.json').write_text(json.dumps(dict(
        source_id=good_id, rejected_source_id=bad_id, analysis_ids={**reports, 'single_size_equity': inspected},
        evidence_type='Synthetic normal-product evidence. No matched Bridge v2.9.16 inputs.',
        sha256={p.name: sha256(p.read_bytes()).hexdigest() for p in sorted(evidence.iterdir())},
    ), indent=2) + '\n')
