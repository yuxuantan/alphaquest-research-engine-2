"""Canonical file -> existing saved report -> prop source checks and downloads."""
from hashlib import sha256
from decimal import Decimal
import csv
import io
import json
import re

from research_fixtures import ResearchHTTPClient
from test_backtests_browser import browser, page, playwright, portal
from test_canonical_trades import envelope, raw


def choose_export(page, content, filename='SYNTHETIC-external-trades.json'):
    page.locator('#trade-import-file').set_input_files({'name': filename, 'mimeType': 'application/json', 'buffer': content})
    page.locator('#trade-import-check').click()


def test_import_review_rejection_saved_report_catalogue_and_source_check(page, portal, tmp_path):
    url = portal['url']
    with ResearchHTTPClient(base_url=url) as client:
        datasets = client.get('/api/datasets').json()
        assert client.get('/api/backtests').json()['total'] == 0
    page.goto(url + '/#backtests/new?import=external')
    partial = envelope(); partial['completion']['status'] = 'partial'
    choose_export(page, raw(partial), 'SYNTHETIC-incomplete.json')
    playwright.expect(page.locator('#trade-import-status')).to_contain_text('Partial/incomplete')
    playwright.expect(page.locator('#trade-import-save')).to_be_disabled()
    page.screenshot(path=str(tmp_path / 'incomplete-export-rejected.png'), full_page=True)

    content = raw(indent=2)
    (tmp_path / 'SYNTHETIC-external-trades.json').write_bytes(content)
    choose_export(page, content)
    playwright.expect(page.locator('#trade-import-save')).to_be_enabled()
    playwright.expect(page.locator('#trade-import-preview')).to_contain_text('Trade counts, completion hash and cost arithmetic reconcile')
    playwright.expect(page.locator('#trade-import-preview')).to_contain_text('Risk coverage · exporter declaration')
    page.locator('#trade-import-preview details > summary').click()
    playwright.expect(page.locator('#trade-import-preview')).to_contain_text(sha256(content).hexdigest())
    page.screenshot(path=str(tmp_path / 'checked-import-provenance.png'), full_page=True)
    with ResearchHTTPClient(base_url=url) as client:
        assert client.get('/api/datasets').json() == datasets
        assert client.get('/api/backtests').json()['total'] == 0
    page.locator('#trade-import-save').click()
    playwright.expect(page).to_have_url(re.compile(r'/#backtests/report/[a-f0-9]{32}$'))
    id = page.url.rsplit('/', 1)[1]
    playwright.expect(page.locator('#backtest-completion')).to_be_visible()
    playwright.expect(page.locator('#backtest-completion-title')).to_have_text('Imported trade report.')
    playwright.expect(page.locator('#report-net')).to_have_text('4')
    playwright.expect(page.locator('#report-balances')).to_contain_text('10000 USD → Final equity 10004 USD')
    playwright.expect(page.locator('#report-trades-body')).to_contain_text('mc-42')
    playwright.expect(page.locator('#report-storage-note')).to_contain_text('Imported trade report')
    playwright.expect(page.locator('#market-benchmark-status')).to_contain_text('completed trades without the market bars')
    playwright.expect(page.locator('#report-research-title')).to_have_text('External research declaration')
    for selector in ['#report-run-oos', '#report-capture-risk', '#report-generate-detail']:
        playwright.expect(page.locator(selector)).to_be_hidden()
    page.screenshot(path=str(tmp_path / 'saved-external-report.png'), full_page=True)

    with ResearchHTTPClient(base_url=url) as client:
        record = client.get('/api/backtests/' + id).json()
        assert record['summary']['total_net_pnl'] == '4'
        assert record['summary']['total_gross_pnl'] == '6'
        assert record['summary']['total_slippage_cost'] == record['summary']['total_commissions'] == '2'
        assert record['run_metadata']['dataset']['id'] is None
        assert record['reconciliation']['observed_bar_count'] is None
        assert 'plan' not in record['run_metadata']['research']
        assert client.get('/api/datasets').json() == datasets
        snapshots = {}
        for kind in ['source', 'canonical_source', 'trades', 'equity', 'report']:
            response = client.get(f'/api/backtests/{id}/exports/{kind}')
            assert response.status_code == 200, response.text
            snapshots[kind] = response.content
            (tmp_path / (kind + ('.csv' if kind in ('trades', 'equity') else '.json'))).write_bytes(response.content)
        assert snapshots['source'] == content
        canonical = json.loads(snapshots['canonical_source'])
        assert canonical['trades'][0]['net_pnl'] == '4'
        assert canonical['trades'][0]['excursions']['mae'] == '6'
        assert canonical['manifest']['coverage']['sessions'] == ['2026-01-05', '2026-01-06']

    posts = []
    page.on('request', lambda request: posts.append(request.url) if request.method == 'POST' else None)
    page.reload()
    playwright.expect(page.locator('#backtest-completion')).to_be_visible()
    assert posts == []
    page.set_viewport_size({'width': 390, 'height': 844})
    page.reload()
    playwright.expect(page.locator('#backtest-completion')).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.screenshot(path=str(tmp_path / 'narrow-external-report.png'), full_page=True)
    page.set_viewport_size({'width': 1440, 'height': 1100})
    page.locator('#report-prop-setup').click()
    playwright.expect(page.locator('#prop-source')).to_contain_text('Imported external trades')
    playwright.expect(page.locator('#robust-configure')).to_have_count(0)
    playwright.expect(page.locator('#campaign-configure')).to_have_count(0)
    page.locator('#prop-check').click()
    playwright.expect(page.locator('#prop-check-output')).to_contain_text('invariance', ignore_case=True)
    playwright.expect(page.locator('#prop-run')).to_be_disabled()
    page.screenshot(path=str(tmp_path / 'unsupported-source-check.png'), full_page=True)

    page.goto(url + '/#strategies/SYNTHETIC')
    playwright.expect(page.locator('#strategy-datasets')).to_contain_text('Imported trade source · no local market dataset')
    assert 'Source dataset deleted' not in page.locator('#strategy-datasets').inner_text()
    page.locator('#strategy-datasets a.instrument-link').click()
    playwright.expect(page.locator('#strategy-new-run')).to_be_hidden()
    playwright.expect(page.locator('#strategy-full-period')).to_contain_text('Imported source: Declared')
    playwright.expect(page.locator('#strategy-results')).to_contain_text('EXPORTED IS')
    page.screenshot(path=str(tmp_path / 'external-source-catalogue.png'), full_page=True)

    page.goto(url + '/#backtests/new?import=external')
    choose_export(page, content)
    playwright.expect(page.locator('#trade-import-save')).to_be_enabled()
    page.locator('#trade-import-save').click()
    playwright.expect(page).to_have_url(url + '/#backtests/report/' + id)
    with ResearchHTTPClient(base_url=url) as client:
        assert client.get('/api/backtests').json()['total'] == 1
        assert client.get('/api/datasets').json() == datasets
        for kind, original in snapshots.items():
            assert client.get(f'/api/backtests/{id}/exports/{kind}').content == original
    (tmp_path / 'browser-evidence.json').write_text(json.dumps(dict(source_id=id,
        raw_sha256=sha256(content).hexdigest(), expected_net='4', expected_gross='6',
        expected_slippage='2', expected_commissions='2', expected_equity=['10000', '10004'],
        declared_sessions=['2026-01-05', '2026-01-06'], external_mae='6', dataset_rows_created=0,
        native_replay=False, native_oos=False, source_check='unverified sizing path rejected',
        duplicate_import='same saved report',
        downloads={kind: sha256(value).hexdigest() for kind, value in snapshots.items()},
        server='Owned temporary uvicorn server stopped by the portal fixture.'), indent=2))


def test_supported_external_source_runs_normal_prop_and_reopens_saved_evidence(page, portal, tmp_path):
    url = portal['url']
    document = envelope()
    document['export_id'] = 'SYNTHETIC-declared-path-invariance'
    document['manifest']['execution']['sizing_path_invariance'] = 'exporter_declared'
    document['manifest']['execution']['assumptions'] = ['SYNTHETIC arithmetic only: exporter declares the fixed signal path invariant under requested contract scaling.']
    content = raw(document, indent=2)
    (tmp_path / 'SYNTHETIC-supported-external-trades.json').write_bytes(content)
    with ResearchHTTPClient(base_url=url) as client:
        datasets = client.get('/api/datasets').json()
    page.goto(url + '/#backtests/new?import=external')
    choose_export(page, content, 'SYNTHETIC-supported-external-trades.json')
    playwright.expect(page.locator('#trade-import-save')).to_be_enabled()
    page.locator('#trade-import-save').click()
    playwright.expect(page).to_have_url(re.compile(r'/#backtests/report/[a-f0-9]{32}$'))
    source_id = page.url.rsplit('/', 1)[1]
    playwright.expect(page.locator('#backtest-completion')).to_be_visible()
    page.locator('#report-prop-setup').click()
    playwright.expect(page.locator('#prop-config')).to_be_visible()
    playwright.expect(page.locator('#prop-method option[value="budgeted_lifecycle"]')).to_have_js_property('disabled', True)
    page.locator('#prop-advanced > summary').click()
    page.locator('#prop-commission-mode').select_option('source')
    page.locator('#prop-slots').fill('1')
    page.locator('#prop-max-nq').fill('0.1')
    page.locator('#prop-block').select_option('1')
    with page.expect_response(lambda response: response.url.endswith('/api/prop-analyses/check') and response.request.method == 'POST') as checking:
        page.locator('#prop-check').click()
    check_response = checking.value
    assert check_response.status == 200, check_response.text()
    checked = check_response.json()
    assert checked['source']['reconciliation']['source_totals']['net_pnl'] == '4'
    assert checked['source']['reconciliation']['source_totals']['total_commissions'] == '2'
    assert checked['source']['reconciliation']['source_totals']['slippage_cost'] == '2'
    assert checked['source']['session_grid']['train'] == checked['source']['session_grid']['validation'] == 1
    (tmp_path / 'source-check.json').write_text(json.dumps(checked, indent=2))
    playwright.expect(page.locator('#prop-run')).to_be_enabled()
    playwright.expect(page.locator('#prop-check-output')).to_contain_text('source net P&L $4')
    playwright.expect(page.locator('#prop-check-output')).to_contain_text('5 observed ordered marks across 1 trades')
    page.screenshot(path=str(tmp_path / 'checked-external-prop-source.png'), full_page=True)
    page.locator('#prop-run').click()
    playwright.expect(page.locator('#prop-report')).to_be_visible(timeout=90000)
    playwright.expect(page.locator('#prop-report-content')).to_contain_text('Funded outcomes are unavailable')
    analysis_id = page.url.rsplit('/', 1)[1]
    page.screenshot(path=str(tmp_path / 'external-prop-result.png'), full_page=True)
    page.get_by_role('tab', name='Source & model').click()
    playwright.expect(page.locator('#prop-report-content')).to_contain_text('Observed ordered marks')
    playwright.expect(page.locator('#prop-report-content')).to_contain_text('5 events')
    page.screenshot(path=str(tmp_path / 'external-prop-observed-risk.png'), full_page=True)

    with ResearchHTTPClient(base_url=url) as client:
        snapshots = {}
        for kind in ['report.json', 'analysis.zip', 'trades.csv']:
            response = client.get(f'/api/prop-analyses/{analysis_id}/downloads/{kind}')
            assert response.status_code == 200, response.text
            snapshots[kind] = response.content
            (tmp_path / kind).write_bytes(response.content)
        report = json.loads(snapshots['report.json'])
        calc = report['calculations']
        assert calc['samples']['data'] == ['2026-01-05', '2026-01-06']
        assert calc['samples']['weekdays'] == [1, 1]
        assert calc['samples']['validation'] == ['2026-01-06', '2026-01-06']
        assert calc['evaluation']['pass_rate'] == 0
        assert calc['funded'] is None
        assert calc['unavailable']
        rows = list(csv.DictReader(io.StringIO(snapshots['trades.csv'].decode())))
        assert len(rows) == 1
        assert Decimal(rows[0]['simulation_net_per_nq']) / 10 == Decimal('2')
        assert Decimal(rows[0]['simulation_mae_per_nq']) / 10 == Decimal('3')
        assert report['settings']['COMMISSION_MODE'] == 'source'
        assert client.get('/api/datasets').json() == datasets
        source_response = client.get(f'/api/backtests/{source_id}/exports/source')
        assert source_response.content == content
        (tmp_path / 'source.json').write_bytes(source_response.content)
        source_record = client.get('/api/backtests/' + source_id).json()
        (tmp_path / 'source-report.json').write_text(json.dumps(source_record, indent=2))
    posts = []
    page.on('request', lambda request: posts.append(request.url) if request.method == 'POST' else None)
    page.reload()
    playwright.expect(page.locator('#prop-report-content')).to_contain_text('Funded outcomes are unavailable')
    assert posts == []
    page.set_viewport_size({'width': 390, 'height': 844})
    page.reload()
    playwright.expect(page.locator('#prop-report')).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.screenshot(path=str(tmp_path / 'narrow-external-prop.png'), full_page=True)
    with ResearchHTTPClient(base_url=url) as client:
        for kind, original in snapshots.items():
            assert client.get(f'/api/prop-analyses/{analysis_id}/downloads/{kind}').content == original
    (tmp_path / 'browser-evidence.json').write_text(json.dumps(dict(source_id=source_id, analysis_id=analysis_id,
        raw_sha256=sha256(content).hexdigest(), expected_source_net='4', expected_source_commission='2', expected_source_slippage='2',
        expected_per_mnq_net='2', expected_observed_per_mnq_mae='3', declared_sessions=['2026-01-05', '2026-01-06'],
        train_validation_sessions=[1, 1], validation_trades=0, evaluation_pass_rate=0, funded=None,
        qualification_scope='Synthetic source arithmetic and local annualized model only; exporter declarations are not independent market or provider certification.',
        reopen_posts=posts, downloads={kind: sha256(value).hexdigest() for kind, value in snapshots.items()},
        server='Owned temporary uvicorn server stopped by the portal fixture.'), indent=2))
