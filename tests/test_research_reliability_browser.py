"""Saved native reports -> predeclared references -> honest outer reliability.

The product runs real calculations. Hand-priced source expectations stay here.
"""
from hashlib import sha256
import json

import pytest

from alphaquest.strategies.registry import get_strategy
from research_fixtures import ResearchHTTPClient
from test_backtests_browser import browser, page, playwright, portal
from test_nested_economics_browser import configure_nested, enable_phase, finished_record, preserve_evidence
from test_prop_phases import save_source


def save_inadequate_vwap(client, source):
    # The same four bars at noon Chicago contain no opening-range setup.
    # The second strategy therefore has no trades, not an invented edge.
    parameters = {item['name']: item['default'] for item in get_strategy(
        'vwap_pullback_risk_sizing').description()['parameters']}
    parameters.update(use_eod_flat=False, plot_trade_levels=False)
    response = client.post('/api/backtests', json=dict(
        dataset_id=source['run_metadata']['dataset']['id'],
        strategy_id='vwap_pullback_risk_sizing', strategy_parameters=parameters,
        execution_settings=dict(initial_capital='10000', tick_size='.25', point_value='20',
                                slippage_ticks=0, commission_per_contract_per_side='0')))
    assert response.status_code == 201, response.text
    result = response.json()
    assert result['summary']['trades_taken'] == 0
    return result


def preserved(client, record, tmp_path):
    snapshots = preserve_evidence(client, record, tmp_path)
    for filename in ['baseline_results.json', 'reliability.json', 'reliability_folds.csv', 'baseline_comparison.csv']:
        response = client.get(f'/api/research-campaigns/robust/{record["campaign_id"]}/exports/{filename}')
        assert response.status_code == 200, response.text
        snapshots[filename] = response.content
        (tmp_path / filename).write_bytes(response.content)
    return snapshots


def save_evidence(page, portal, record, source_ids, tmp_path, expected):
    page.locator('#robust-reliability-result').screenshot(path=str(tmp_path / 'consolidated-outer-evidence.png'))
    page.screenshot(path=str(tmp_path / 'complete-research-report.png'), full_page=True)
    with ResearchHTTPClient(base_url=portal['url'], timeout=300) as client:
        snapshots = preserved(client, record, tmp_path)
    page.locator('#robust-result').get_by_role('link', name='Open the saved analysis report', exact=True).click()
    playwright.expect(page.locator('#robust-reliability-result')).to_contain_text('Consolidated outer evidence')
    posts = []
    page.on('request', lambda request: posts.append(request.url) if request.method == 'POST' else None)
    page.reload()
    playwright.expect(page.locator('#robust-reliability-result')).to_contain_text('INSUFFICIENT_EVIDENCE')
    assert not posts
    page.set_viewport_size({'width': 390, 'height': 844})
    page.locator('#robust-reliability-result h3').scroll_into_view_if_needed()
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.screenshot(path=str(tmp_path / 'narrow-reliability-viewport.png'))
    page.locator('.robust-baseline-comparisons').first.scroll_into_view_if_needed()
    page.screenshot(path=str(tmp_path / 'narrow-reference-viewport.png'))
    with ResearchHTTPClient(base_url=portal['url'], timeout=300) as client:
        for filename, content in snapshots.items():
            assert client.get(f'/api/research-campaigns/robust/{record["campaign_id"]}/exports/{filename}').content == content
    (tmp_path / 'browser-evidence.json').write_text(json.dumps(dict(
        campaign_id=record['campaign_id'], analysis_id=record['analysis_id'], source_ids=source_ids,
        expected=expected, reopen_posts=posts,
        child_analysis_ids=[phase['analysis_id'] for fold in record['result']['folds'] for phase in fold['economic_selection']['phases']],
        baseline_analysis_ids=[item['analysis_id'] for fold in record['result']['folds'] for item in fold['baseline_results']],
        outer_run_ids=[item['outer_run_id'] for fold in record['result']['folds'] for item in fold['chronological_replay']['items']],
        baseline_outer_run_ids=[item['outer_run_id'] for fold in record['result']['folds'] for item in fold['baseline_results']],
        downloads={name: sha256(content).hexdigest() for name, content in snapshots.items()},
        additional_downloads={item.name: sha256(item.read_bytes()).hexdigest()
                              for item in [tmp_path / 'historical_mean_cash.json'] if item.exists()},
        server='Owned temporary uvicorn server stopped by the portal fixture.'), indent=2))


def test_predeclared_reference_compares_two_outer_blocks_without_claiming_reliability(page, portal, tmp_path):
    with ResearchHTTPClient(base_url=portal['url'], timeout=300) as client:
        source = save_source(client, days=30)
        other = save_inadequate_vwap(client, source)
    configure_nested(page, portal, source, neighbor=other, name='SYNTHETIC two-strategy research with one-MNQ reference')
    # Cross-strategy membership is not a numeric parameter neighborhood.
    page.locator('#robust-qualification-minimum_neighbors').fill('0')
    enable_phase(page, 'funded', '3')
    page.locator('#robust-baselines-configure > summary').click()
    playwright.expect(page.locator('#robust-baseline-add')).to_be_disabled()
    page.locator('#robust-preview').click()
    playwright.expect(page.locator('#robust-run')).to_be_enabled()
    page.locator('#robust-baseline-add').click()
    playwright.expect(page.locator('#robust-run')).to_be_disabled()
    page.locator('#robust-baseline-1-id').fill('One MNQ same-signal reference')
    options = page.locator('#robust-baseline-1-source option').evaluate_all('(rows) => rows.map(row => ({value: row.value, label: row.textContent}))')
    choice = next(row['value'] for row in options if 'consecutive green hold' in row['label'])
    page.locator('#robust-baseline-1-source').select_option(choice)
    page.locator('#robust-baseline-1-micros').fill('1')
    page.locator('#robust-preview').click()
    playwright.expect(page.locator('#robust-baseline-plan')).to_contain_text('One MNQ same-signal reference')
    playwright.expect(page.locator('#robust-plan')).to_contain_text('36 new backtest tasks')
    playwright.expect(page.locator('#robust-run')).to_be_enabled()
    page.locator('#robust-plan').screenshot(path=str(tmp_path / 'predeclared-reference-preview.png'))
    record = finished_record(page, portal, source)
    assert len(record['plan']['candidates']) == 2
    assert record['plan']['estimated_backtests'] == 36  #24 inner +6 training +6 worst-case outer.
    assert record['plan']['economic_plan']['maximum_phase_candidates'] == 6  #4 policies +2 references.
    for fold in record['result']['folds']:
        by_strategy = {next(c['strategy_id'] for c in record['plan']['candidates'] if c['id'] == row['candidate_id']): row
                       for row in fold['qualification']['candidates']}
        assert by_strategy['consecutive_green_hold']['status'] == 'PASS'
        assert by_strategy['vwap_pullback_risk_sizing']['status'] == 'INSUFFICIENT_EVIDENCE'
        assert by_strategy['vwap_pullback_risk_sizing']['metrics']['validation_trades'] == 0
        assert len(fold['economic_selection']['membership']['configuration_ids']) == 1
        assert float(fold['chronological_replay']['items'][0]['result']['cash_received']) == 1500
        reference = fold['baseline_results'][0]
        assert reference['recommendation_eligible'] is False
        assert float(reference['chronological_replay']['cash_received']) == 0
    evidence = record['result']['reliability']; phase = evidence['phases']['funded']
    assert evidence['status'] == 'INSUFFICIENT_EVIDENCE' and evidence['production_qualified'] is False
    assert evidence['settings']['minimum_outer_blocks'] == 5
    assert phase['coverage']['declared_outer_folds'] == phase['coverage']['scalar_eligible_folds'] == 2
    assert phase['scalar_metrics']['mean_cash_received'] == 1500
    comparison = phase['baseline_comparisons'][0]
    assert comparison['paired_mean_improvement'] == 1500
    assert comparison['paired_outer_folds'] == 2
    assert comparison['historical_interval']['interval'] is None
    assert comparison['decision'] == 'INSUFFICIENT_EVIDENCE'
    journal = record['result']['event_journal']
    for access in (item for item in journal if item['kind'] == 'outer_access'):
        selection = next(item for item in journal if item['kind'] == 'selection_seal' and item['selection_seal_sha256'] == access['selection_seal_sha256'])
        reference = next(item for item in journal if item['kind'] == 'baseline_seal' and item['reference_seal_sha256'] == access['reference_seal_sha256'])
        assert max(selection['sequence'], reference['sequence']) < access['sequence']
    playwright.expect(page.locator('#robust-reliability-result')).to_contain_text('2 declared outer folds; 5 required')
    playwright.expect(page.locator('.robust-baseline-comparisons').first).to_contain_text('1500')
    page.locator('.robust-baseline-results details > summary').first.click()
    page.locator('.robust-baseline-results').first.screenshot(path=str(tmp_path / 'reference-forecast-and-observation.png'))
    save_evidence(page, portal, record, [source['id'], other['id']], tmp_path,
                  dict(selected_received_cash_per_fold=1500, reference_received_cash_per_fold=0,
                       paired_mean_improvement=1500, observed_outer_blocks=2, required_outer_blocks=5,
                       no_trade_strategy='vwap_pullback_risk_sizing', production_qualified=False))


def test_conservative_mean_retains_exact_family_without_scalar_weights(page, portal, tmp_path):
    with ResearchHTTPClient(base_url=portal['url'], timeout=300) as client:
        source = save_source(client, days=30)
    configure_nested(page, portal, source, name='SYNTHETIC historical mean objective and exact policy family')
    enable_phase(page, 'funded', '3, 10')
    page.locator('#robust-economic-funded-selector').select_option('conservative_expected_received_cash')
    for key, value in dict(minimum_history_sessions=10, block_sessions=1, minimum_history_blocks=10,
                           replicates=200, simulations_per_replicate=8, maximum_mc_standard_error=0).items():
        page.locator('#robust-economic-funded-historical-' + key).fill(str(value))
    record = finished_record(page, portal, source)
    for fold in record['result']['folds']:
        phase = fold['economic_selection']['phases'][0]
        assert len(phase['frozen_packages']) == 2
        assert {item['configuration']['micros'] for item in phase['frozen_packages']} == {3, 10}
        for row in phase['training_forecasts']:
            historical = row['uncertainty']['historical_mean']
            assert historical['status'] == 'estimated'
            assert historical['lower_mean_cash'] == row['metrics']['historical_lower_mean_cash'] == 1500
            assert historical['history_session_count'] == historical['history_block_count'] == 10
            assert historical['mc_noise']['maximum_observed_standard_error'] == 0
    phase = record['result']['reliability']['phases']['funded']
    assert phase['coverage']['selected_family_folds'] == 2
    assert all(row['family_size'] == 2 and row['action'] == 'selected_family' for row in phase['folds'])
    assert phase['scalar_metrics']['mean_cash_received'] is None
    assert phase['scalar_metrics']['total_observed_cash_received'] is None
    assert phase['forecast_errors']['mean_error'] is None
    assert phase['calibration']['brier_score'] is None
    assert 'predeclared_baseline_missing' in phase['reasons']
    playwright.expect(page.locator('#robust-reliability-result')).to_contain_text('Family ambiguity')
    playwright.expect(page.locator('#robust-reliability-result')).to_contain_text('No baseline was predeclared')
    page.locator('.robust-economic-result').first.screenshot(path=str(tmp_path / 'historical-mean-family.png'))
    # The normal child report must retain and correctly label the new objective.
    child = record['result']['folds'][0]['economic_selection']['phases'][0]['analysis_id']
    child_page = page.context.new_page()
    child_page.goto(portal['url'] + '/#backtests/prop/job/' + child)
    playwright.expect(child_page.locator('#prop-heading-note')).to_contain_text('historical lower bound')
    playwright.expect(child_page.locator('#campaign-candidates')).to_contain_text('Historical lower mean')
    child_page.screenshot(path=str(tmp_path / 'normal-conservative-phase-report.png'), full_page=True)
    with ResearchHTTPClient(base_url=portal['url'], timeout=300) as client:
        raw = client.get(f'/api/prop-analyses/{child}/files/historical_mean_cash.json')
        assert raw.status_code == 200, raw.text
        (tmp_path / 'historical_mean_cash.json').write_bytes(raw.content)
        assert all(len(row['replicates']) == 200 for row in raw.json())
    child_page.close()
    save_evidence(page, portal, record, [source['id']], tmp_path,
                  dict(frozen_quantities=[3, 10], historical_lower_mean_cash=1500, inner_mc_se=0,
                       selected_family_folds=2, scalar_mean=None, baseline_missing=True))


@pytest.mark.parametrize('action', ['unmeasured', 'no_account_no_fee'])
def test_insufficient_historical_mean_uses_only_predeclared_abstention(page, portal, tmp_path, action):
    with ResearchHTTPClient(base_url=portal['url'], timeout=300) as client:
        source = save_source(client, days=30)
    configure_nested(page, portal, source, name='SYNTHETIC unresolved historical objective · ' + action)
    enable_phase(page, 'funded', '3')
    page.locator('#robust-economic-funded-selector').select_option('conservative_expected_received_cash')
    page.locator('#robust-reliability-configure > summary').click()
    page.locator('#robust-reliability-abstention_action').select_option(action)
    record = finished_record(page, portal, source)
    for fold in record['result']['folds']:
        phase = fold['economic_selection']['phases'][0]
        assert phase['decision']['status'] == 'INSUFFICIENT_EVIDENCE'
        assert phase['frozen_packages'] == []
        assert fold['chronological_replay']['items'] == []
    assert not any(row['kind'] == 'outer_access' for row in record['result']['event_journal'])
    phase = record['result']['reliability']['phases']['funded']
    expected_action = 'unmeasured_abstention' if action == 'unmeasured' else action
    assert [row['action'] for row in phase['folds']] == [expected_action] * 2
    assert phase['coverage']['declared_outer_folds'] == 2
    assert phase['scalar_metrics']['mean_cash_received'] == (None if action == 'unmeasured' else 0)
    assert phase['calibration']['historical_block_count'] == 0
    assert phase['status'] == 'INSUFFICIENT_EVIDENCE'
    playwright.expect(page.locator('#robust-reliability-result')).to_contain_text(expected_action.replace('_', ' ').capitalize())
    child = record['result']['folds'][0]['economic_selection']['phases'][0]['analysis_id']
    child_page = page.context.new_page()
    child_page.goto(portal['url'] + '/#backtests/prop/job/' + child)
    playwright.expect(child_page.locator('#prop-report-content')).to_contain_text('Historical mean evidence is unresolved.')
    playwright.expect(child_page.locator('#prop-report-content')).not_to_contain_text('Incomplete horizon: plotted values')
    child_page.screenshot(path=str(tmp_path / 'unresolved-historical-child-report.png'), full_page=True)
    child_page.close()
    save_evidence(page, portal, record, [source['id']], tmp_path,
                  dict(default_history_requirement=60, observed_training_sessions=10,
                       economic_choice='INSUFFICIENT_EVIDENCE', action=action,
                       mean_cash=None if action == 'unmeasured' else 0, actual_outer_account_created=False))
