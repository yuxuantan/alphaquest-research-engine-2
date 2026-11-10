"""Normal native report -> declared nested economics -> frozen outer evidence."""
from prop_setup_helpers import open_prop_task
from datetime import date, timedelta
from hashlib import sha256
import json
import re

from research_fixtures import ResearchHTTPClient
from test_backtests_browser import browser, page, playwright, portal
from test_prop_phases import save_source


def configure_nested(page, portal, source, *, neighbor=None, name='SYNTHETIC nested economic validation'):
    page.goto(portal['url'] + '/#backtests/report/' + source['id'])
    page.locator('#report-prop-setup').click()
    open_prop_task(page, 'research', close_outer=True)
    page.locator('#robust-configure > summary').click()
    page.locator('#robust-name').fill(name)
    if neighbor:
        page.locator('#robust-source-search').fill(neighbor['id'][:8])
        page.get_by_role('checkbox', name=re.compile(neighbor['id'][:8])).check()
    for key, value in dict(outer_train_sessions=10, outer_test_sessions=7,
                           inner_train_sessions=2, inner_validation_sessions=2,
                           purge_sessions=1, embargo_sessions=0,
                           minimum_inner_folds=2, minimum_outer_folds=2).items():
        page.locator('#robust-' + key).fill(str(value))
    page.locator('#robust-qualification-configure > summary').click()
    for key, value in dict(minimum_sessions=6, minimum_trades=6,
                           minimum_trades_per_fold=1, bootstrap_block_sessions=1,
                           minimum_neighbors=1 if neighbor else 0).items():
        page.locator('#robust-qualification-' + key).fill(str(value))
    page.locator('#robust-economic-configure > summary').click()


def enable_phase(page, phase, quantities, *, receipt_delay=2):
    prefix = '#robust-economic-' + phase + '-'
    page.locator('#robust-economic-' + phase).check()
    page.locator(prefix + 'quantities').fill(quantities)
    fields = page.locator(prefix + 'fields')
    fields.get_by_text('Forecast sampling, seeds and model guards', exact=True).click()
    page.locator(prefix + 'simulations').fill('64')
    page.locator(prefix + 'block_weekdays').fill('1')
    if phase == 'evaluation':
        page.locator(prefix + 'chain_simulations').fill('64')
        page.locator(prefix + 'max_calendar_days').fill('60')
        page.locator(prefix + 'max_attempts').fill('30')
    else:
        page.locator(prefix + 'receipt_delay_calendar_days').fill(str(receipt_delay))


def finished_record(page, portal, source):
    page.locator('#robust-preview').click()
    playwright.expect(page.locator('#robust-run')).to_be_enabled(timeout=30000)
    page.locator('#robust-run').click()
    playwright.expect(page.locator('#robust-result')).to_contain_text('Readiness:', timeout=180000)
    with ResearchHTTPClient(base_url=portal['url'], timeout=300) as client:
        records = client.get('/api/research-campaigns/robust', params={'source_id': source['id']}).json()['items']
        assert len(records) == 1
        record = client.get('/api/research-campaigns/robust/' + records[0]['campaign_id']).json()
        assert record['status'] == 'complete', record
        return record


def preserve_evidence(client, record, tmp_path):
    snapshots = {}
    for filename in ['campaign.json', 'report.json', 'analysis.zip', 'qualification.csv', 'research_plan.json',
                     'economic_selection.json', 'chronological_replay.json', 'research_journal.json']:
        response = client.get(f'/api/research-campaigns/robust/{record["campaign_id"]}/exports/{filename}')
        assert response.status_code == 200, response.text
        snapshots[filename] = response.content
        (tmp_path / filename).write_bytes(response.content)
    return snapshots


def test_both_independent_studies_freeze_and_replay_from_saved_report(page, portal, tmp_path):
    with ResearchHTTPClient(base_url=portal['url'], timeout=300) as client:
        source = save_source(client, days=30)
        neighbor = save_source(client, days=30, green=2)
    configure_nested(page, portal, source, neighbor=neighbor)
    enable_phase(page, 'evaluation', '10, 20')
    enable_phase(page, 'funded', '3, 10')
    page.locator('#robust-preview').click()
    playwright.expect(page.locator('#robust-run')).to_be_enabled()
    playwright.expect(page.locator('#robust-economic-plan tbody tr')).to_have_count(2)
    playwright.expect(page.locator('#robust-economic-dates tbody tr')).to_have_count(4)
    playwright.expect(page.locator('#robust-plan')).to_contain_text('44 new backtest tasks')
    page.screenshot(path=str(tmp_path / 'declared-independent-studies.png'), full_page=True)
    page.locator('#robust-plan').screenshot(path=str(tmp_path / 'economic-preview-detail.png'))
    page.locator('#robust-run').click()
    playwright.expect(page.locator('#robust-result')).to_contain_text('Historical chronological replay', timeout=180000)
    playwright.expect(page.locator('#robust-result')).to_contain_text('Readiness:')
    with ResearchHTTPClient(base_url=portal['url'], timeout=300) as client:
        saved = client.get('/api/research-campaigns/robust', params={'source_id': source['id']}).json()['items']
        assert len(saved) == 1
        record = client.get('/api/research-campaigns/robust/' + saved[0]['campaign_id']).json()
        assert record['status'] == 'complete', record
        assert record['plan']['economic_plan']['maximum_phase_candidates'] == 16
        assert len(record['result']['folds']) == 2
        journal = record['result']['event_journal']
        seals = {row['selection_seal_sha256']: row for row in journal if row['kind'] == 'selection_seal'}
        assert len(seals) == 2
        for event in journal:
            if event['kind'] == 'outer_access':
                seal = seals[event['selection_seal_sha256']]
                assert seal['sequence'] < event['sequence']
                assert event['frozen_package_sha256'] in seal['frozen_package_sha256']
        for fold in record['result']['folds']:
            selection = fold['economic_selection']
            assert selection['status'] == 'SELECTION_FROZEN'
            assert len(selection['membership']['configuration_ids']) == 2
            phases = {item['phase']: item for item in selection['phases']}
            assert set(phases) == {'evaluation', 'funded'}
            assert phases['evaluation']['decision']['selector']['mode'] == 'pareto_family'
            # A produces $300/MNQ/day. At both 10 and 20 MNQ it passes
            # on day one, so both exact cost/time ties remain frozen.
            assert len(phases['evaluation']['frozen_packages']) == 2
            assert {item['configuration']['micros'] for item in phases['evaluation']['frozen_packages']} == {10, 20}
            assert all(float(item['metrics']['cost_per_funded']) == 70 for item in phases['evaluation']['training_forecasts'])
            assert all(item['complete_search_candidate_count'] == 4 for item in phases.values())
            assert all(item['deployment_readiness']['production_qualified'] is False for item in phases.values())
            observed = fold['chronological_replay']
            assert observed['status'] == 'complete'
            assert observed['selection_seal_sha256'] == selection['selection_seal_sha256']
            outer = next(item for item in record['plan']['folds'] if item['index'] == fold['index'])['test']
            for item in observed['items']:
                result = item['result']
                assert result['historical_paths'] == 1
                assert result['mode'] == 'historical_chronological_replay'
                package = next(package for package in phases[item['phase']]['frozen_packages'] if package['candidate_id'] == item['candidate_id'])
                assert package['package_sha256'] == item['frozen_package_sha256']
                if item['phase'] == 'evaluation':
                    assert result['evaluation_passed'] and result['acquisition_completed']
                    assert result['ready_date'] == outer['sessions'][2]
                    assert float(result['paid_fees']) == 70
                    assert float(result['net_cash']) == -70
                    assert len(result['attempts']) == 1
                else:
                    assert float(result['gross_account_deductions']) == 1500
                    assert float(result['cash_received']) == 1500
                    assert float(result['pending_cash']) == 0
                    assert len(result['payout_events']) == 1
                    payout = result['payout_events'][0]
                    assert payout['request_date'] == outer['sessions'][4]
                    assert payout['receipt_date'] == (date.fromisoformat(outer['sessions'][4]) + timedelta(days=2)).isoformat()
                    assert payout['received_within_horizon'] is True
                    assert payout['amount_convention'] == 'kernel_entitlement_unrounded'
        snapshots = preserve_evidence(client, record, tmp_path)
    page.locator('.robust-frozen-policy > summary').first.click()
    page.locator('#robust-research-journal > summary').click()
    page.screenshot(path=str(tmp_path / 'frozen-earlier-forecasts-and-outer-observations.png'), full_page=True)
    page.locator('.robust-economic-result').first.screenshot(path=str(tmp_path / 'earlier-forecasts-detail.png'))
    page.locator('#robust-outer-summary-1').screenshot(path=str(tmp_path / 'outer-cash-summary-detail.png'))
    page.locator('#robust-research-journal').screenshot(path=str(tmp_path / 'ordered-freeze-journal-detail.png'))
    page.locator('.robust-cash-ledger > summary').first.click()
    page.screenshot(path=str(tmp_path / 'chronological-cash-ledger.png'), full_page=True)
    page.locator('.phase-provider-review > summary').first.click()
    page.locator('.phase-provider-review').first.locator('details > summary').first.click()
    page.screenshot(path=str(tmp_path / 'captured-provider-rule-gaps.png'), full_page=True)
    page.locator('.phase-provider-review').first.screenshot(path=str(tmp_path / 'provider-rule-gaps-detail.png'))
    page.locator('#robust-result').get_by_role('link', name='Open the saved analysis report', exact=True).click()
    playwright.expect(page.locator('#prop-heading-title')).to_have_text('Nested research · economic validation')
    posts = []
    page.on('request', lambda request: posts.append(request.url) if request.method == 'POST' else None)
    page.reload()
    playwright.expect(page.locator('#prop-report-content')).to_contain_text('Historical chronological replay')
    assert not posts
    page.set_viewport_size({'width': 390, 'height': 844})
    page.reload()
    playwright.expect(page.locator('#prop-heading-title')).to_have_text('Nested research · economic validation')
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.screenshot(path=str(tmp_path / 'narrow-economic-report.png'), full_page=True)
    page.locator('.robust-economic-result h3').first.scroll_into_view_if_needed()
    page.screenshot(path=str(tmp_path / 'narrow-earlier-forecast-viewport.png'))
    page.locator('#robust-outer-summary-1 tbody tr').nth(2).scroll_into_view_if_needed()
    page.screenshot(path=str(tmp_path / 'narrow-received-cash-viewport.png'))
    with ResearchHTTPClient(base_url=portal['url'], timeout=300) as client:
        for filename, content in snapshots.items():
            assert client.get(f'/api/research-campaigns/robust/{record["campaign_id"]}/exports/{filename}').content == content
    (tmp_path / 'browser-evidence.json').write_text(json.dumps(dict(
        campaign_id=record['campaign_id'], analysis_id=record['analysis_id'], source_ids=[source['id'], neighbor['id']],
        expected_evaluation_exact_ties=[10, 20], expected_paid_acquisition_fees='70',
        expected_funded_gross_request='1500', expected_receipt_delay_calendar_days=2,
        complete_phase_candidates=16, reopen_posts=posts,
        child_analysis_ids=[phase['analysis_id'] for fold in record['result']['folds'] for phase in fold['economic_selection']['phases']],
        outer_run_ids=[item['outer_run_id'] for fold in record['result']['folds'] for item in fold['chronological_replay']['items']],
        downloads={name: sha256(content).hexdigest() for name, content in snapshots.items()},
        server='Owned temporary uvicorn server stopped by the portal fixture.'), indent=2))


def test_receipt_at_outer_cutoff_remains_pending(page, portal, tmp_path):
    with ResearchHTTPClient(base_url=portal['url'], timeout=300) as client:
        source = save_source(client, days=30)
    configure_nested(page, portal, source, name='SYNTHETIC receipt at exclusive outer cutoff')
    enable_phase(page, 'funded', '3', receipt_delay=3)
    record = finished_record(page, portal, source)
    for fold in record['result']['folds']:
        items = fold['chronological_replay']['items']
        assert len(items) == 1
        result = items[0]['result']
        assert float(result['gross_account_deductions']) == 1500
        assert float(result['cash_received']) == 0
        assert float(result['pending_cash']) == 1500
        event = result['payout_events'][0]
        package = fold['economic_selection']['phases'][0]['frozen_packages'][0]
        assert event['receipt_date'] == package['outer_window']['cutoff_date_exclusive']
        assert event['received_within_horizon'] is False
    page.locator('.robust-payouts > summary').first.click()
    playwright.expect(page.locator('.robust-payouts').first).to_contain_text('kernel_entitlement_unrounded')
    page.screenshot(path=str(tmp_path / 'receipt-at-cutoff-pending.png'), full_page=True)
    page.locator('.robust-payouts').first.screenshot(path=str(tmp_path / 'receipt-at-cutoff-detail.png'))
    with ResearchHTTPClient(base_url=portal['url'], timeout=300) as client:
        snapshots = preserve_evidence(client, record, tmp_path)
    (tmp_path / 'browser-evidence.json').write_text(json.dumps(dict(
        campaign_id=record['campaign_id'], analysis_id=record['analysis_id'], source_ids=[source['id']],
        expected_account_deduction='1500', expected_cash_received='0', expected_pending_cash='1500',
        expected_receipt_timing='exact exclusive cutoff, therefore not received',
        downloads={name: sha256(content).hexdigest() for name, content in snapshots.items()},
        server='Owned temporary uvicorn server stopped by the portal fixture.'), indent=2))


def test_no_qualified_configuration_abstains_before_outer_execution(page, portal, tmp_path):
    with ResearchHTTPClient(base_url=portal['url'], timeout=300) as client:
        source = save_source(client, days=30)
    configure_nested(page, portal, source, name='SYNTHETIC no qualified economic policy')
    page.locator('#robust-qualification-minimum_mean_session_net').fill('4000')
    enable_phase(page, 'funded', '3')
    record = finished_record(page, portal, source)
    for fold in record['result']['folds']:
        assert fold['economic_selection']['status'] == 'NO_QUALIFIED_CONFIGURATION'
        assert fold['economic_selection']['phases'] == []
        assert fold['economic_selection']['outer_test_status'] == 'selection_abstained'
    assert all(item['kind'] == 'selection_seal' for item in record['result']['event_journal'])
    playwright.expect(page.locator('#robust-result')).to_contain_text('No outer account outcome is fabricated')
    assert page.locator('.robust-chronological-result').count() == 0
    page.screenshot(path=str(tmp_path / 'no-qualified-abstention.png'), full_page=True)
    with ResearchHTTPClient(base_url=portal['url'], timeout=300) as client:
        snapshots = preserve_evidence(client, record, tmp_path)
    (tmp_path / 'browser-evidence.json').write_text(json.dumps(dict(
        campaign_id=record['campaign_id'], analysis_id=record['analysis_id'], source_ids=[source['id']],
        expected_status='NO_QUALIFIED_CONFIGURATION', outer_execution='abstained',
        downloads={name: sha256(content).hexdigest() for name, content in snapshots.items()},
        server='Owned temporary uvicorn server stopped by the portal fixture.'), indent=2))
