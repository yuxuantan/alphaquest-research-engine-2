"""Goal-led configuration uses the existing saved backtest, owners and reports."""
from hashlib import sha256
import json
import httpx
from test_backtests_browser import browser,page,playwright
from test_research_procedure_browser import portal
from test_robust_research_api import save_grid


def test_guided_comparison_lazy_configuration_preservation_and_durable_results(page,portal,tmp_path):
    with httpx.Client(base_url=portal['url'],timeout=300) as client:dataset,job,records=save_grid(client)
    requests=[];errors=[]
    page.on('request',lambda r:requests.append([r.method,r.url]))
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(portal['url']+'/#backtests/report/'+records[0]['id'])
    page.locator('#report-prop-setup').click()
    playwright.expect(page.locator('#setup-goals')).to_be_visible()
    playwright.expect(page.locator('#prop-form')).to_be_hidden()
    assert not any('/robust/defaults' in url or '/research-campaigns/source-window' in url for _,url in requests)
    playwright.expect(page.locator('#setup-goal-inspect')).to_be_disabled()
    playwright.expect(page.locator('#setup-source-compatibility')).to_contain_text('not established')
    page.screenshot(path=str(tmp_path/'goals.png'),full_page=True)
    page.locator('#setup-goal-compare').click()
    playwright.expect(page.locator('#campaign-is-start')).to_have_value('2026-01-05')
    playwright.expect(page.locator('#campaign-phase')).to_be_hidden()
    page.locator('#setup-next').click()
    playwright.expect(page.locator('#campaign-phase')).to_be_visible()
    page.locator('#campaign-phase').select_option('funded')
    page.locator('#campaign-horizon').fill('');page.locator('#campaign-phase').select_option('evaluation')
    playwright.expect(page.locator('#campaign-horizon')).to_be_disabled()
    page.locator('#campaign-phase').select_option('funded')
    page.locator('#campaign-horizon').fill('14');page.locator('#campaign-delay').fill('4');page.locator('#campaign-breach').fill('0')
    page.get_by_text('Historical sampling and reproducible seeds',exact=True).click()
    page.locator('#campaign-paths').fill('8');page.locator('#campaign-block').select_option('1')
    page.locator('#setup-back').click();playwright.expect(page.locator('#campaign-phase')).to_be_hidden()
    page.locator('#setup-next').click();playwright.expect(page.locator('#campaign-horizon')).to_have_value('14')
    page.locator('#setup-next').click()
    playwright.expect(page.locator('#campaign-check')).to_be_visible()
    playwright.expect(page.locator('#campaign-run')).to_be_disabled()
    page.locator('#campaign-check').click();playwright.expect(page.locator('#campaign-run')).to_be_enabled(timeout=30000)
    page.locator('#setup-step-accounts').click();page.locator('#campaign-delay').fill('5')
    page.locator('#setup-step-review').click();playwright.expect(page.locator('#campaign-run')).to_be_disabled()
    page.locator('#setup-step-accounts').click();page.locator('#campaign-delay').fill('4');page.locator('#setup-step-review').click()
    page.locator('#campaign-check').click();playwright.expect(page.locator('#campaign-run')).to_be_enabled(timeout=30000)
    page.screenshot(path=str(tmp_path/'checked-review.png'),full_page=True)
    page.set_viewport_size(dict(width=390,height=844));page.screenshot(path=str(tmp_path/'review-narrow.png'),full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth+1')
    page.locator('#campaign-run').click();playwright.expect(page.locator('#campaign-delete')).to_be_enabled(timeout=120000)
    cid=page.url.rsplit('/',1)[-1];campaign=page.request.get(portal['url']+'/api/research-campaigns/'+cid).json();aid=campaign['analysis_id']
    response=page.request.get(portal['url']+f'/api/prop-analyses/{aid}/downloads/report.json');raw=response.body();result=json.loads(raw)
    assert sorted(c['metrics']['expected_payouts'] for c in result['calculations']['candidates'])==[0,1500]
    (tmp_path/'report.json').write_bytes(raw)
    # Revisiting configuration rebuilds the shell without losing/removing form owners.
    page.goto(portal['url']+'/#backtests/prop/new/'+records[0]['id'])
    playwright.expect(page.locator('#setup-goals')).to_be_visible()
    page.locator('#setup-goal-compare').click();playwright.expect(page.locator('#campaign-is-start')).to_have_value('2026-01-05')
    page.locator('#setup-step-accounts').click();page.locator('#campaign-phase').select_option('funded');page.locator('#campaign-horizon').fill('21')
    page.locator('#setup-goal-picker > summary').click();page.locator('#setup-goal-research').click();playwright.expect(page.locator('#robust-source-choices')).to_be_visible()
    page.locator('#setup-goal-picker > summary').click();page.locator('#setup-goal-compare').click();page.locator('#setup-step-accounts').click()
    playwright.expect(page.locator('#campaign-horizon')).to_have_value('21')
    assert not errors,errors
    (tmp_path/'evidence.json').write_text(json.dumps(dict(synthetic=True,campaign_id=cid,analysis_id=aid,source_id=records[0]['id'],expected_cash=[0,1500],report_sha256=sha256(raw).hexdigest(),browser_errors=errors,requests=requests,temporary_server='Stopped by fixture.'),indent=2)+'\n')


def test_guided_full_research_sources_design_economics_and_saved_outputs(page,portal,tmp_path):
    with httpx.Client(base_url=portal['url'],timeout=300) as client:dataset,job,records=save_grid(client)
    page.goto(portal['url']+'/#backtests/report/'+records[0]['id']);page.locator('#report-prop-setup').click()
    page.locator('#setup-goal-research').click()
    playwright.expect(page.locator('#robust-name')).to_be_visible()
    page.locator('#robust-name').fill('SYNTHETIC guided robustness and Funded study')
    page.locator('#robust-source-search').fill(records[1]['id'][:8])
    import re
    page.get_by_role('checkbox',name=re.compile(records[1]['id'][:8])).check()
    page.locator('#setup-next').click()
    playwright.expect(page.locator('#robust-outer_train_sessions')).to_be_visible()
    for key,v in dict(outer_train_sessions=8,outer_test_sessions=2,inner_train_sessions=2,inner_validation_sessions=2).items():page.locator('#robust-'+key).fill(str(v))
    page.get_by_text('Window buffers and minimum fold counts',exact=True).click()
    for key,v in dict(purge_sessions=1,embargo_sessions=1,minimum_inner_folds=2,minimum_outer_folds=2).items():page.locator('#robust-'+key).fill(str(v))
    page.locator('#robust-qualification-configure > summary').click()
    for key,v in dict(minimum_folds=2,minimum_sessions=4,minimum_trades=4,minimum_trades_per_fold=2,minimum_positive_fold_fraction=1,maximum_profit_concentration=.6,additional_round_trip_cost=10,minimum_neighbors=1,bootstrap_replicates=400,bootstrap_block_sessions=1,confidence_level=.95,minimum_bootstrap_tail_samples=5).items():page.locator('#robust-qualification-'+key).fill(str(v))
    page.locator('#setup-next').click()
    page.locator('#setup-next').click()
    playwright.expect(page.locator('#setup-message')).to_contain_text('Enable Evaluation or Funded')
    page.locator('#robust-economic-funded').check()
    playwright.expect(page.locator('#setup-summary')).to_contain_text('Funded accounts: Apex 50K EOD')
    page.locator('#robust-economic-funded-quantities').fill('10,20')
    page.locator('#robust-economic-funded-fields').get_by_text('Forecast sampling, seeds and model guards',exact=True).click()
    page.locator('#robust-economic-funded-simulations').fill('8');page.locator('#robust-economic-funded-block_weekdays').fill('1')
    page.locator('#setup-next').click()
    page.locator('#robust-preview').click();playwright.expect(page.locator('#robust-run')).to_be_enabled(timeout=60000)
    page.screenshot(path=str(tmp_path/'research-checked.png'),full_page=True)
    page.locator('#robust-run').click();playwright.expect(page.locator('#robust-result')).to_contain_text('Readiness:',timeout=180000)
    row,=page.request.get(portal['url']+'/api/research-campaigns/robust?source_id='+records[0]['id']).json()['items']
    record=page.request.get(portal['url']+'/api/research-campaigns/robust/'+row['campaign_id']).json()
    for fold in record['result']['folds']:assert sorted(float(c['metrics']['mean_session_net']) for c in fold['qualification']['candidates'])==[100,300]
    raw=page.request.get(portal['url']+'/api/research-campaigns/robust/'+row['campaign_id']+'/exports/report.json').body()
    (tmp_path/'report.json').write_bytes(raw)
    page.screenshot(path=str(tmp_path/'research-results.png'),full_page=True)
    (tmp_path/'evidence.json').write_text(json.dumps(dict(synthetic=True,campaign_id=row['campaign_id'],analysis_id=record['analysis_id'],source_ids=[r['id'] for r in records],expected_inner_mean_session_net=[100,300],report_sha256=sha256(raw).hexdigest(),temporary_server='Stopped by fixture.'),indent=2)+'\n')


def test_guided_native_source_check_and_legacy_tools_remain_explicit(page,portal,tmp_path):
    from research_fixtures import ResearchHTTPClient
    from test_native_replay_api import source
    with ResearchHTTPClient(base_url=portal['url'],timeout=300) as client:record=source(client)
    page.goto(portal['url']+'/#backtests/report/'+record['id']);page.locator('#report-prop-setup').click()
    playwright.expect(page.locator('#setup-goal-inspect')).to_be_enabled()
    page.locator('#setup-goal-inspect').click();page.locator('#setup-next').click()
    page.locator('#native-micros').fill('3');page.locator('#setup-next').click()
    page.locator('#native-check').click();playwright.expect(page.locator('#native-run')).to_be_enabled(timeout=30000)
    playwright.expect(page.locator('#native-check-output')).to_contain_text('Native source compatible')
    page.locator('#setup-goal-picker > summary').click();page.locator('#setup-other-tools > summary').click()
    page.locator('#setup-goal-legacy').click();page.locator('#setup-step-accounts').click()
    playwright.expect(page.locator('#prop-model')).to_be_visible()
    playwright.expect(page.locator('#prop-overrides')).to_be_hidden()
    page.screenshot(path=str(tmp_path/'explicit-legacy-tool.png'),full_page=True)
    page.locator('#setup-goal-picker > summary').click();page.locator('#setup-goal-inspect').click();page.locator('#setup-step-accounts').click()
    playwright.expect(page.locator('#native-micros')).to_have_value('3')
    page.set_viewport_size(dict(width=390,height=844));page.screenshot(path=str(tmp_path/'native-accounts-narrow.png'),full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth+1')


def test_task_load_failure_retry_and_explicit_qualification_only(page,portal,tmp_path):
    with httpx.Client(base_url=portal['url'],timeout=300) as client:dataset,job,records=save_grid(client)
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(portal['url']+'/#backtests/prop/new/'+records[0]['id'])
    page.route('**/api/research-campaigns/robust/defaults',lambda route:route.fulfill(status=503,json=dict(detail='Temporary settings outage')))
    page.locator('#setup-goal-research').click()
    playwright.expect(page.locator('#setup-message')).to_contain_text('Choose the task again to retry')
    playwright.expect(page.locator('#setup-next')).to_be_disabled()
    page.unroute('**/api/research-campaigns/robust/defaults')
    page.locator('#setup-goal-research').click()
    playwright.expect(page.locator('#robust-name')).to_be_visible()
    page.locator('#setup-step-review').click();page.locator('#robust-preview').click()
    playwright.expect(page.locator('#setup-message')).to_contain_text('Enable Evaluation or Funded')
    playwright.expect(page.locator('#setup-qualification-only')).to_be_visible()
    page.locator('#setup-qualification-only').check();page.locator('#setup-next').click()
    playwright.expect(page.locator('#setup-review')).to_contain_text('will not select a position size or prop account')
    assert not errors,errors
    page.screenshot(path=str(tmp_path/'recovered-qualification-only.png'),full_page=True)
