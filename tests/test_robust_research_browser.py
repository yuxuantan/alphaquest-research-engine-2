"""Actual saved-report -> nested qualification -> durable AnalysisStore report."""
from hashlib import sha256
import json
import re

from research_fixtures import ResearchHTTPClient
from test_backtests_browser import browser, page, playwright, portal
from test_prop_phases import save_source


def test_nested_research_preview_qualification_download_reopen(page, portal, tmp_path):
    with ResearchHTTPClient(base_url=portal['url'], timeout=300) as client:
        first = save_source(client, days=20)
        neighbor = save_source(client, days=20, green=2)
    page.goto(portal['url'] + '/#backtests/report/' + first['id'])
    page.locator('#report-prop-setup').click()
    page.locator('#robust-configure > summary').click()
    playwright.expect(page.locator('#robust-form')).to_be_visible()
    page.locator('#robust-name').fill('SYNTHETIC neighboring configurations · inner research')
    page.locator('#robust-source-search').fill(neighbor['id'][:8])
    page.get_by_role('checkbox', name=re.compile(neighbor['id'][:8])).check()
    page.locator('#robust-preview').click()
    playwright.expect(page.locator('#robust-status')).to_contain_text('Plan needs attention')
    playwright.expect(page.locator('#robust-run')).to_be_disabled()
    page.screenshot(path=str(tmp_path / 'insufficient-session-rejection.png'), full_page=True)

    for key, value in dict(outer_train_sessions=10, outer_test_sessions=3,
                           inner_train_sessions=2, inner_validation_sessions=2,
                           purge_sessions=1, embargo_sessions=0,
                           minimum_inner_folds=2, minimum_outer_folds=2).items():
        page.locator('#robust-' + key).fill(str(value))
    page.locator('#robust-form details > summary').click()
    for key, value in dict(minimum_sessions=6, minimum_trades=6,
                           minimum_trades_per_fold=1, bootstrap_block_sessions=1).items():
        page.locator('#robust-qualification-' + key).fill(str(value))
    page.locator('#robust-preview').click()
    playwright.expect(page.locator('#robust-run')).to_be_enabled()
    playwright.expect(page.locator('#robust-fold-plan tbody tr')).to_have_count(3)
    playwright.expect(page.locator('#robust-plan')).to_contain_text('36 new backtest tasks')
    playwright.expect(page.locator('#robust-plan')).to_contain_text('2026-01-05 → 2026-01-16 (10 sessions)')
    page.screenshot(path=str(tmp_path / 'checked-nested-plan.png'), full_page=True)
    page.locator('#robust-run').click()
    playwright.expect(page.locator('#robust-result')).to_contain_text('Readiness: INCOMPLETE', timeout=90000)
    playwright.expect(page.locator('#robust-result .robust-pass')).to_have_count(6)
    page.screenshot(path=str(tmp_path / 'inner-qualification.png'), full_page=True)
    with ResearchHTTPClient(base_url=portal['url'], timeout=300) as client:
        saved = client.get('/api/research-campaigns/robust', params={'source_id': first['id']}).json()['items']
        assert len(saved) == 1
        id = saved[0]['campaign_id']
        record = client.get('/api/research-campaigns/robust/' + id).json()
        report = client.get(f'/api/prop-analyses/{record["analysis_id"]}/downloads/report.json').json()
        assert len(report['calculations']['folds']) == 3
        for fold in report['calculations']['folds']:
            assert fold['outer_test_status'] == fold['policy_selection_status'] == 'not_run'
            assert sorted(float(candidate['metrics']['mean_session_net']) for candidate in fold['qualification']['candidates']) == [1000, 3000]
            assert all(candidate['metrics']['validation_sessions'] == 6 for candidate in fold['qualification']['candidates'])
            assert all(candidate['status'] == 'PASS' for candidate in fold['qualification']['candidates'])
        assert report['calculations']['readiness']['status'] == 'INCOMPLETE'
        snapshots = {}
        for kind in ['campaign.json', 'report.json', 'analysis.zip', 'qualification.csv', 'research_plan.json']:
            response = client.get(f'/api/research-campaigns/robust/{id}/exports/{kind}')
            assert response.status_code == 200, response.text
            snapshots[kind] = response.content
            (tmp_path / kind).write_bytes(response.content)

    page.locator('#robust-result').get_by_role('link', name='Open the saved analysis report').click()
    playwright.expect(page.locator('#prop-heading-title')).to_have_text('Nested research · inner qualification')
    playwright.expect(page.locator('#prop-report-content')).to_contain_text('Readiness: INCOMPLETE')
    assert page.locator('#prop-report-content a[href$="/files/qualification.csv"]').count() == 1
    posts = []
    page.on('request', lambda request: posts.append(request.url) if request.method == 'POST' else None)
    page.reload()
    playwright.expect(page.locator('#prop-heading-title')).to_have_text('Nested research · inner qualification')
    assert not posts
    page.set_viewport_size({'width': 390, 'height': 844})
    page.reload()
    playwright.expect(page.locator('#prop-report-content')).to_contain_text('Readiness: INCOMPLETE')
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.screenshot(path=str(tmp_path / 'narrow-saved-report.png'), full_page=True)
    report_reopen_posts = list(posts)
    assert not report_reopen_posts
    page.locator('#prop-back').click()
    page.get_by_role('button', name='SYNTHETIC neighboring configurations · inner research · complete').click()
    playwright.expect(page.locator('#robust-result')).to_contain_text('Readiness: INCOMPLETE')
    # Opening the existing prop configuration performs its read-only common-
    # source-window POST. Neither report/history reopen may start calculations.
    assert all(url.endswith('/api/research-campaigns/source-window') for url in posts)
    with ResearchHTTPClient(base_url=portal['url'], timeout=300) as client:
        for kind, content in snapshots.items():
            assert client.get(f'/api/research-campaigns/robust/{id}/exports/{kind}').content == content
    (tmp_path / 'browser-evidence.json').write_text(json.dumps(dict(
        campaign_id=id, analysis_id=record['analysis_id'], source_ids=[first['id'], neighbor['id']],
        expected_outer_folds=3, expected_inner_validation_sessions=6,
        expected_inner_mean_net_usd=[1000, 3000], expected_statuses=['PASS'] * 6,
        outer_tests='not_run', readiness='INCOMPLETE', reopen_posts=report_reopen_posts,
        configuration_metadata_posts=posts,
        downloads={key: sha256(value).hexdigest() for key, value in snapshots.items()},
        server='Owned temporary uvicorn server stopped by the portal fixture.'), indent=2))
