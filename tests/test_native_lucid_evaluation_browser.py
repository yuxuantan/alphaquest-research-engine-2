"""Lucid Evaluation uses the existing native campaign and nested research forms."""
from prop_setup_helpers import open_prop_task
from decimal import Decimal
from hashlib import sha256
import io
import json
import zipfile

import httpx

from test_backtests_browser import browser, page, playwright, portal
from test_native_campaign_browser import run_campaign
from test_native_lucid_evaluation import lucid_source
from test_research_workspace_browser import open_controls, save_draft


def _source(portal):
    with httpx.Client(base_url=portal['url'], timeout=300) as client:
        return lucid_source(client)


def _download(page, portal, tmp_path, urls):
    hashes = {}
    for name, url in urls.items():
        response = page.request.get(portal['url'] + url)
        assert response.ok, response.text()
        (tmp_path / name).write_bytes(response.body())
        hashes[name] = sha256(response.body()).hexdigest()
    return hashes


def test_native_lucid_evaluation_configuration_results_download_and_reopen(page, portal, tmp_path):
    original = _source(portal)
    source_url = portal['url'] + '/api/backtests/' + original['id']
    source_before = page.request.get(source_url).body()
    page.goto(portal['url'] + '/#backtests/report/' + original['id'])
    page.locator('#report-prop-setup').click()
    open_prop_task(page, 'compare', close_outer=True)
    page.locator('#campaign-new-evaluation').click()
    assert page.locator('#campaign-profile option[value="lucidflex-50k"]').evaluate('(option) => option.disabled')
    playwright.expect(page.locator('#campaign-retry-delay')).to_have_value('0')
    playwright.expect(page.locator('#campaign-activation-delay')).to_have_value('1')
    page.locator('#campaign-execution').select_option('native')
    page.locator('#campaign-profile').select_option('lucidflex-50k')
    page.locator('.campaign-sizes').fill('3,10')
    page.locator('#campaign-paths').fill('4')
    page.locator('#campaign-seed').fill('1729')
    page.locator('#campaign-block').select_option('1')
    page.locator('#campaign-native-horizon').fill('7')
    page.locator('#campaign-native-capture').fill('1')
    page.locator('#campaign-native-calendar-version').fill('explicit-synthetic-lucid-evaluation-v1')
    page.locator('.campaign-native-start').fill('2026-01-12')
    page.locator('#campaign-native-coverage-end').fill('2026-01-20')
    page.locator('#campaign-price').fill('80.5')
    page.locator('#campaign-activation').fill('0')
    page.locator('#campaign-activation-delay').fill('0')
    playwright.expect(page.locator('#campaign-rule-summary')).to_contain_text('40%')
    playwright.expect(page.locator('#campaign-rule-summary')).to_contain_text('no modeled evaluation expiry')
    playwright.expect(page.locator('#campaign-rule-summary')).not_to_contain_text('21-session expiry')
    # An incompatible execution method cannot silently substitute another profile.
    requests = []
    page.on('request', lambda request: requests.append(request.url) if request.method == 'POST' else None)
    page.locator('#campaign-execution').select_option('trade_path')
    playwright.expect(page.locator('#campaign-profile')).to_have_value('lucidflex-50k')
    playwright.expect(page.locator('#campaign-price')).to_have_value('80.5')
    playwright.expect(page.locator('#campaign-activation-delay')).to_have_value('0')
    playwright.expect(page.locator('#campaign-profile-status')).to_contain_text('profile and fees are retained')
    assert page.locator('#campaign-profile').evaluate('(input) => input.validity.customError')
    playwright.expect(page.locator('#campaign-check')).to_be_enabled(timeout=30000)
    requests.clear()
    page.locator('#campaign-check').click()
    assert not [url for url in requests if url.endswith('/api/research-campaigns')]
    page.locator('#campaign-profile-status').screenshot(path=str(tmp_path / 'saved-path-lucid-rejected.png'))
    page.locator('#campaign-execution').select_option('native')
    playwright.expect(page.locator('#campaign-paths')).to_have_value('4')
    playwright.expect(page.locator('#campaign-profile')).to_have_value('lucidflex-50k')
    assert not page.locator('#campaign-profile').evaluate('(input) => input.validity.customError')
    campaign, report = run_campaign(page, portal, tmp_path, 2)
    assert campaign['declaration']['retry'] == dict(retry_delay_calendar_days=0, activation_delay_sessions=0)
    rows = {row['manifest']['configuration']['micros']: row for row in report['calculations']['candidates']}
    assert set(rows) == {3, 10}
    for quantity, pass_date, ready_date, elapsed in [(3, '2026-01-15', '2026-01-16', 4), (10, '2026-01-14', '2026-01-15', 3)]:
        row = rows[quantity]
        assert Decimal(str(row['metrics']['cost_per_funded'])) == Decimal('80.5')
        assert row['metrics']['expected_calendar_days_to_funded'] == elapsed
        forecast = row['native_forecast']
        assert forecast['metrics']['completed_paths'] == 4 and forecast['metrics']['censored_paths'] == 0
        for path in forecast['paths']:
            assert (path['pass_date'], path['ready_date']) == (pass_date, ready_date)
            assert Decimal(path['paid_fees']) == Decimal('80.5')
            assert Decimal(path['paid_activation_fees']) == 0
    assert report['calculations']['frontier'] == [rows[10]['candidate_id']]
    assert report['calculations']['winner'] is None
    states = rows[10]['native_forecast']['captures'][0]['result']['trace']
    assert [Decimal(row['state_after']['equity_from_initial']) for row in states[:3]] == [2990, 5980, 8970]
    assert [row['state_after']['outcome'] for row in states[:3]] == ['open', 'open', 'activation_pending']
    page.locator('#campaign-inspect').select_option(rows[10]['candidate_id'])
    playwright.expect(page.locator('#campaign-native-forecast-result')).to_contain_text('not an observed historical outcome')
    page.locator('#campaign-native-forecast-metrics').screenshot(path=str(tmp_path / 'lucid-evaluation-forecast.png'))
    page.locator('#campaign-native-forecast-captures-detail > summary').click()
    page.locator('#campaign-native-forecast-clock-mapping').screenshot(path=str(tmp_path / 'source-and-modeled-clocks.png'))
    page.set_viewport_size(dict(width=390, height=844))
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.locator('#campaign-native-forecast-decisions').screenshot(path=str(tmp_path / 'native-lucid-decisions-narrow.png'))
    analysis_id = report['id']
    hashes = _download(page, portal, tmp_path, {
        'report.json': f'/api/prop-analyses/{analysis_id}/downloads/report.json',
        'analysis.zip': f'/api/prop-analyses/{analysis_id}/downloads/analysis.zip',
        'campaign.json': '/api/research-campaigns/' + campaign['campaign_id'],
        'source-report.json': '/api/backtests/' + original['id'],
        'SYNTHETIC-complete-MNQ-IS-OOS.csv': '/api/datasets/' + original['run_metadata']['dataset']['id'] + '/csv',
    })
    assert hashes['SYNTHETIC-complete-MNQ-IS-OOS.csv'] == original['run_metadata']['dataset']['sha256']
    with zipfile.ZipFile(io.BytesIO((tmp_path / 'analysis.zip').read_bytes())) as archive:
        for name, entry in report['files'].items():
            assert sha256(archive.read(name)).hexdigest() == entry['sha256']
        assert 'native_forecasts.json' in archive.namelist()
    requests.clear()
    page.reload()
    playwright.expect(page.locator('#campaign-candidates tbody tr')).to_have_count(2, timeout=60000)
    assert requests == []
    assert page.request.get(portal['url'] + f'/api/prop-analyses/{analysis_id}/downloads/report.json').body() == (tmp_path / 'report.json').read_bytes()
    assert page.request.get(source_url).body() == source_before
    (tmp_path / 'evidence.json').write_text(json.dumps(dict(
        source_id=original['id'], campaign_id=campaign['campaign_id'], analysis_id=analysis_id,
        engine_identity=report['implementation'], downloads=hashes, reopen_posts=requests,
        source_research=original['run_metadata']['research'], synthetic=True,
        expected=dict(net_per_mnq_trade=299, fee_per_acquisition='80.5', quantity_3_days=4, quantity_10_days=3,
                      quantity_10_session_profits=[2990, 2990, 2990], second_day_consistency_rejected=True),
        source_fixture='Synthetic complete-minute MNQ IS January 5–9 and separate ordinary manual OOS January 26–30; this campaign reads IS only.',
        server='Owned temporary portal server stopped and joined in fixture teardown.'), indent=2))


def test_native_lucid_nested_draft_template_and_explicit_execution_switch(page, portal, tmp_path):
    original = _source(portal)
    page.goto(portal['url'] + '/#backtests/report/' + original['id'])
    page.locator('#report-prop-setup').click()
    open_prop_task(page, 'research', close_outer=True)
    page.locator('#robust-configure > summary').click()
    for key, value in dict(outer_train_sessions=3, outer_test_sessions=1, inner_train_sessions=1,
            inner_validation_sessions=1, purge_sessions=0, embargo_sessions=0,
            minimum_inner_folds=2, minimum_outer_folds=2).items():
        page.locator('#robust-' + key).fill(str(value))
    page.locator('#robust-economic-configure > summary').click()
    page.locator('#robust-economic-evaluation').check()
    prefix = '#robust-economic-evaluation-'
    lucid = page.locator(prefix + 'lucidflex-50k')
    playwright.expect(lucid).to_be_disabled()
    playwright.expect(page.locator(prefix + 'retry_delay_calendar_days')).to_have_value('0')
    playwright.expect(page.locator(prefix + 'activation_delay_sessions')).to_have_value('1')
    page.locator(prefix + 'execution').select_option('native')
    lucid.check()
    page.locator(prefix + 'apex-50k-eod').uncheck()
    page.locator(prefix + 'lucidflex-50k-evaluation_price').fill('90.25')
    page.locator(prefix + 'lucidflex-50k-activation_fee').fill('0')
    page.locator(prefix + 'retry_delay_calendar_days').fill('2')
    page.locator(prefix + 'activation_delay_sessions').fill('0')
    page.locator(prefix + 'quantities').fill('3,10')
    page.locator(prefix + 'fields').get_by_text('Forecast sampling, seeds and model guards', exact=True).click()
    page.locator(prefix + 'simulations').fill('4')
    page.locator(prefix + 'block_weekdays').fill('1')
    open_controls(page)
    draft = save_draft(page, portal, 'SYNTHETIC native Lucid declared assumptions')
    study, = draft['declaration']['economic_studies']
    assert study['profiles'][0]['profile_id'] == 'lucidflex-50k'
    assert study['profiles'][0]['evaluation_price'] == '90.25'
    assert study['profiles'][0]['activation_fee'] == '0'
    assert study['retry']['retry_delay_calendar_days'] == 2 and study['retry']['activation_delay_sessions'] == 0
    assert study['sampling']['chain_simulations'] == study['simulation']['simulations'] == 4
    assert 'native_execution' in study['search_settings']
    page.goto(portal['url'] + '/#backtests/research?draft=' + draft['id'])
    playwright.expect(page.locator('#workspace-form-status')).to_contain_text('revision 1 loaded', timeout=30000)
    open_prop_task(page, 'research')
    playwright.expect(page.locator('#robust-run')).to_be_disabled()
    # The form reads the saved declaration; the catalogues do not upgrade legacy Lucid.
    defaults = page.request.get(portal['url'] + '/api/research-campaigns/robust/defaults').json()
    assert [p['profile_id'] for p in defaults['economic_profiles']['evaluation']] == ['apex-50k-eod']
    assert 'lucidflex-50k' in [p['profile_id'] for p in defaults['economic_native_profiles']['evaluation']]
    playwright.expect(page.locator(prefix + 'execution')).to_have_value('native')
    playwright.expect(lucid).to_be_checked()
    playwright.expect(page.locator(prefix + 'apex-50k-eod')).not_to_be_checked()
    playwright.expect(page.locator(prefix + 'lucidflex-50k-evaluation_price')).to_have_value('90.25')
    page.locator('#robust-economic-configure > summary').click()
    page.locator(prefix + 'execution').select_option('trade_path')
    playwright.expect(lucid).to_be_checked()
    playwright.expect(page.locator(prefix + 'profile-status')).to_contain_text('selected profiles and fees are retained')
    playwright.expect(page.locator(prefix + 'retry_delay_calendar_days')).to_have_value('2')
    playwright.expect(page.locator(prefix + 'activation_delay_sessions')).to_have_value('0')
    page.locator('#workspace-draft-save').click()
    playwright.expect(page.locator('#workspace-form-status')).to_contain_text('requires actual native strategy reruns')
    saved = page.request.get(portal['url'] + '/api/research-workspace/drafts/' + draft['id']).json()
    assert saved['revision'] == 1 and saved['declaration'] == draft['declaration']
    page.locator(prefix + 'profile-status').screenshot(path=str(tmp_path / 'nested-profile-switch-blocked.png'))
    page.locator(prefix + 'execution').select_option('native')
    page.locator('#workspace-draft-save').click()
    playwright.expect(page.locator('#workspace-form-status')).to_contain_text('revision 2 saved')
    saved = page.request.get(portal['url'] + '/api/research-workspace/drafts/' + draft['id']).json()
    assert saved['declaration'] == draft['declaration']
    page.locator('#workspace-save-name').fill('SYNTHETIC reusable native Lucid assumptions')
    page.locator('#workspace-template-save').click()
    playwright.expect(page.locator('#workspace-form-status')).to_contain_text('Settings template saved')
    template, = page.request.get(portal['url'] + '/api/research-workspace/templates').json()['items']
    assert template['settings']['economic_studies'] == draft['declaration']['economic_studies']
    page.goto(portal['url'] + '/#backtests/prop/new/' + original['id'])
    open_prop_task(page, 'research', close_outer=True)
    page.locator('#robust-configure > summary').click()
    open_controls(page)
    page.locator('#workspace-template-select').select_option(template['id'])
    page.locator('#workspace-template-apply').click()
    playwright.expect(page.locator('#workspace-form-status')).to_contain_text('Template applied')
    playwright.expect(page.locator(prefix + 'execution')).to_have_value('native')
    playwright.expect(lucid).to_be_checked()
    playwright.expect(page.locator(prefix + 'lucidflex-50k-evaluation_price')).to_have_value('90.25')
    playwright.expect(page.locator(prefix + 'lucidflex-50k-activation_fee')).to_have_value('0')
    playwright.expect(page.locator(prefix + 'retry_delay_calendar_days')).to_have_value('2')
    playwright.expect(page.locator(prefix + 'activation_delay_sessions')).to_have_value('0')
    playwright.expect(page.locator('#robust-run')).to_be_disabled()
    # Draft syntax preserves assumptions; real compatibility preview enforces rules.
    page.locator('#robust-economic-configure > summary').click()
    page.locator(prefix + 'lucidflex-50k-activation_fee').fill('7.5')
    page.locator('#robust-preview').click()
    playwright.expect(page.locator('#robust-status')).to_contain_text('zero activation fee', timeout=30000)
    playwright.expect(page.locator('#robust-run')).to_be_disabled()
    page.locator(prefix + 'lucidflex-50k-activation_fee').fill('0')
    page.locator('#robust-preview').click()
    try:
        playwright.expect(page.locator('#robust-run')).to_be_enabled(timeout=90000)
    except AssertionError:
        (tmp_path / 'preview-failure.txt').write_text(page.locator('#robust-status').inner_text())
        page.locator('#robust-configure').screenshot(path=str(tmp_path / 'preview-failure.png'))
        raise
    page.locator(prefix + 'fields').screenshot(path=str(tmp_path / 'native-lucid-template-restored.png'))
    page.set_viewport_size(dict(width=390, height=844))
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.locator(prefix + 'fields').screenshot(path=str(tmp_path / 'native-lucid-template-narrow.png'))
    # Explicitly choosing Apex and legacy execution creates a new declaration only.
    page.locator(prefix + 'execution').select_option('trade_path')
    lucid.uncheck()
    page.locator(prefix + 'apex-50k-eod').check()
    page.locator('#workspace-save-name').fill('SYNTHETIC explicit legacy Apex declaration')
    page.locator('#workspace-draft-copy').click()
    playwright.expect(page.locator('#workspace-form-status')).to_contain_text('revision 1 saved')
    docs = page.request.get(portal['url'] + '/api/research-workspace/drafts').json()['items']
    legacy = next(doc for doc in docs if doc['name'] == 'SYNTHETIC explicit legacy Apex declaration')
    legacy_study, = legacy['declaration']['economic_studies']
    assert 'native_execution' not in legacy_study['search_settings']
    assert legacy_study['profiles'][0]['profile_id'] == 'apex-50k-eod'
    assert legacy_study['retry']['retry_delay_calendar_days'] == 2
    assert page.request.get(portal['url'] + '/api/research-workspace/templates/' + template['id']).json() == template
    assert page.request.get(portal['url'] + '/api/research-workspace/drafts/' + draft['id']).json()['declaration'] == draft['declaration']
    hashes = _download(page, portal, tmp_path, {
        'native-draft.json': '/api/research-workspace/drafts/' + draft['id'],
        'native-template.json': '/api/research-workspace/templates/' + template['id'],
        'explicit-legacy-draft.json': '/api/research-workspace/drafts/' + legacy['id'],
        'source-report.json': '/api/backtests/' + original['id'],
        'SYNTHETIC-complete-MNQ-IS-OOS.csv': '/api/datasets/' + original['run_metadata']['dataset']['id'] + '/csv',
    })
    assert hashes['SYNTHETIC-complete-MNQ-IS-OOS.csv'] == original['run_metadata']['dataset']['sha256']
    assert page.request.get(portal['url'] + '/api/research-campaigns/robust').json()['items'] == []
    (tmp_path / 'evidence.json').write_text(json.dumps(dict(
        source_id=original['id'], draft_id=draft['id'], template_id=template['id'], explicit_legacy_draft_id=legacy['id'],
        downloads=hashes, exact_native_roundtrip=True, unsupported_profile_retained_and_blocked=True,
        fresh_preview_completed=True, no_research_run=True, synthetic=True,
        expected=dict(profile='lucidflex-50k', evaluation_fee='90.25', activation_fee='0', retry_calendar_days=2, activation_sessions=0),
        server='Owned temporary portal server stopped and joined in fixture teardown.'), indent=2))
