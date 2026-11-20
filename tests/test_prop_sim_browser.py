"""Final product: qualified campaign -> check -> both phase engines -> saved results."""
from prop_sim_fixtures import manual_prop_requests
import json
import os
from pathlib import Path
import shutil

import httpx
import pytest
from test_backtests_browser import browser,page,portal,playwright
from test_prop_sim import qualified_source


def test_daily_loss_limit_amount_tracks_account_profile(page,portal,tmp_path):
    """Show both phase limits before running, including optional Lucid DLL."""
    page.goto(portal['url']+'/#prop-sim')
    label=page.locator('.prop-sim-dll')
    checkbox=page.locator('#prop-sim-daily-loss-limit')
    playwright.expect(label).to_contain_text('$1,000 Evaluation; $1,000–$3,000 Funded, by tier')
    playwright.expect(checkbox).to_be_checked()
    playwright.expect(checkbox).to_be_disabled()
    page.locator('#prop-sim-profile').select_option('lucidflex-50k')
    playwright.expect(label).to_have_text('$1,200 daily loss limit — Evaluation and Funded')
    playwright.expect(checkbox).to_be_enabled()
    checkbox.uncheck()
    playwright.expect(checkbox).not_to_be_checked()
    playwright.expect(label).to_contain_text('$1,200')
    checkbox.check()
    page.locator('#prop-sim-form').screenshot(path=str(tmp_path/'lucid-dll-amount.png'))
    page.locator('#prop-sim-profile').select_option('apex-50k-eod')
    playwright.expect(label).to_contain_text('$1,000 Evaluation; $1,000–$3,000 Funded, by tier')
    playwright.expect(checkbox).to_be_checked()
    playwright.expect(checkbox).to_be_disabled()


def test_strategy_sizing_capability_is_visible_before_running(page,portal,tmp_path):
    """A real qualified no-stop campaign permits fixed size, explains risk rejection."""
    with httpx.Client(base_url=portal['url'],timeout=120) as client:
        workflow,source=qualified_source(client)
    page.goto(portal['url']+'/#prop-sim')
    page.locator('#prop-sim-source').select_option('0')
    playwright.expect(page.locator('#prop-sim-source-details')).to_contain_text('Fixed contracts: supported')
    playwright.expect(page.locator('#prop-sim-source-details')).to_contain_text('no pre-entry protective stop')
    page.locator('#prop-sim-search-kind').select_option('percentage_risk')
    playwright.expect(page.locator('#prop-sim-status')).to_contain_text('no pre-entry protective stop')
    playwright.expect(page.locator('#prop-sim-run')).to_be_disabled()
    playwright.expect(page.locator('#prop-sim-check')).to_be_disabled()
    page.screenshot(path=str(tmp_path/'unsupported-percentage.png'),full_page=True)
    page.locator('#prop-sim-search-kind').select_option('fixed_contracts')
    playwright.expect(page.locator('#prop-sim-check')).to_be_enabled()
    if destination:=os.environ.get('ALPHAQUEST_STRATEGY_SIZING_EVIDENCE_DIR'):
        target=Path(destination);target.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(tmp_path/'unsupported-percentage.png',target/'unsupported-percentage.png')
        (target/'portal-source.json').write_text(json.dumps(source,indent=2))


@pytest.mark.parametrize('profile_id,evaluation_sizes,funded_sizes',[
    ('apex-50k-eod',(1,2,3),(1,2,3)),('apex-50k-eod',(58,59,60),(38,39,40)),
    ('lucidflex-50k',(1,2,3),(1,2,3))],ids=['shared-range','phase-limits','lucidflex'])
def test_prop_sim_qualified_single_configuration_real_results_and_downloads(page,portal,tmp_path,profile_id,evaluation_sizes,funded_sizes):
    with httpx.Client(base_url=portal['url'],timeout=120) as client:workflow,source=qualified_source(client)
    page.goto(portal['url']+'/#prop-sim')
    playwright.expect(page.locator('#prop-sim-source option')).to_have_count(5)
    assert page.locator('#prop-sim-source').get_attribute('multiple') is None
    page.locator('#prop-sim-source').select_option('0')
    page.get_by_role('link',name='Open IS source backtest',exact=True).click()
    playwright.expect(page.locator('#report-prop-setup')).to_have_attribute('href','#prop-sim?source='+source['source_backtest_id'])
    page.locator('#report-prop-setup').click()
    playwright.expect(page.locator('#prop-sim-source')).to_have_value('0')
    page.locator('#prop-sim-profile').select_option(profile_id)
    assert page.locator('#prop-sim-evaluation_maximum_micros').get_attribute('max')==('40' if profile_id=='lucidflex-50k' else '60')
    if profile_id=='lucidflex-50k':
        playwright.expect(page.locator('#prop-sim-evaluation_price')).to_have_value('80.50')
        playwright.expect(page.locator('#prop-sim-activation_fee')).to_have_value('0')
    assert page.locator('#prop-sim-funded_maximum_micros').get_attribute('max')=='40'
    for phase,sizes in [('evaluation',evaluation_sizes),('funded',funded_sizes)]:
        page.locator('#prop-sim-'+phase+'_minimum_micros').fill(str(sizes[0]))
        page.locator('#prop-sim-'+phase+'_maximum_micros').fill(str(sizes[-1]))
    playwright.expect(page.locator('#prop-sim-maximum_funded_breach_probability')).to_have_value('')
    page.locator('#prop-sim-simulations').fill('32')
    page.get_by_text('Costs, calendar and optional risk settings',exact=True).click()
    page.locator('#prop-sim-start_date').fill('2026-11-16')
    page.locator('#prop-sim-form').screenshot(path=str(tmp_path/'configuration-portal.png'))
    page.locator('#prop-sim-check').click()
    playwright.expect(page.locator('#prop-sim-status')).to_contain_text('Source compatible',timeout=30000)
    with page.expect_response(lambda r:r.url.endswith('/api/prop-sim') and r.request.method=='POST') as response:
        page.locator('#prop-sim-run').click()
    record=response.value.json();assert response.value.status==202
    assert len(record['configuration']['selections'])==1
    assert record['configuration']['maximum_funded_breach_probability'] is None
    assert record['configuration']['profile_id']==profile_id
    page.get_by_role('navigation',name='Main navigation',exact=True).get_by_role('link',name='Dataset',exact=True).click()
    page.goto(portal['url']+'/#prop-sim?analysis='+record['id'])
    # A final phase refresh replaces both charts. Inspect after both settle.
    for phase in ('evaluation','funded'):
        playwright.expect(page.locator('#prop-sim-'+phase+'-progress')).to_contain_text('COMPLETE',timeout=90000)
    for phase in ('evaluation','funded'):
        page.get_by_role('button',name='View '+phase.title(),exact=True).click()
        playwright.expect(page.locator('#prop-sim-'+phase+'-progress')).to_contain_text('COMPLETE',timeout=90000)
        playwright.expect(page.locator('#prop-sim-'+phase+'-table tbody tr')).to_have_count(3)
        assert page.locator('#prop-sim-'+phase+'-table tbody tr').evaluate_all('(rows)=>rows.map(r=>Number(r.dataset.size))')==list(evaluation_sizes if phase=='evaluation' else funded_sizes)
        if phase=='evaluation':
            page.get_by_text('Explore the cost / time trade-off',exact=True).click()
            chart=page.locator('#prop-sim-evaluation-pareto')
            playwright.expect(chart).to_have_attribute('data-candidate-count','3')
            point=chart.locator('circle').first;point.focus()
            playwright.expect(page.locator('#prop-sim-pareto-readout')).to_contain_text('MNQ')
            with page.expect_download() as download:page.get_by_role('link',name='Pareto chart SVG ↓',exact=True).click()
            download.value.save_as(tmp_path/'evaluation-pareto.svg')
            assert 'Expected acquisition cost' in (tmp_path/'evaluation-pareto.svg').read_text()
        page.locator('#prop-sim-'+phase+'-table th button').first.click()
        assert page.locator('#prop-sim-'+phase+'-table tbody tr').evaluate_all('(rows)=>rows.map(r=>Number(r.dataset.size))')==list(reversed(evaluation_sizes if phase=='evaluation' else funded_sizes))
        page.locator('#prop-sim-'+phase+'-table th button').first.click()
        parent=page.locator('#prop-sim-'+phase+'-results')
        with page.expect_download() as download:parent.get_by_role('link',name='Saved report JSON ↓',exact=True).click()
        download.value.save_as(tmp_path/(phase+'-report.json'))
        with page.expect_download() as download:parent.get_by_role('link',name='Results CSV ↓',exact=True).click()
        download.value.save_as(tmp_path/(phase+'-results.csv'))
        with page.expect_download() as download:parent.get_by_role('link',name='Evidence ZIP ↓',exact=True).click()
        download.value.save_as(tmp_path/(phase+'-analysis.zip'))
        parent.screenshot(path=str(tmp_path/(phase+'-portal.png')))
    from hashlib import sha256
    from zipfile import ZipFile
    from alphaquest.prop.store import sealed_checks
    from alphaquest.prop_report_storage import restore,compact
    storage=[]
    for phase in ('evaluation','funded'):
        report=json.loads((tmp_path/(phase+'-report.json')).read_text())
        folder=portal['app'].state.prop_analyses.root/report['id']
        before=sealed_checks(folder)
        assert not (folder/'calculations.json').exists()
        with ZipFile(tmp_path/(phase+'-analysis.zip')) as z:expected=z.read('calculations.json')
        download=page.request.get(portal['url']+f"/api/research-campaigns/{record['campaign_ids'][phase]}/exports/results.json")
        assert download.ok and download.body()==expected
        assert sha256(expected).hexdigest()==report['files']['calculations.json']['sha256']
        # Simulate an older unpacked report, then perform the same compatible
        # migration and reopen through the unchanged normal download routes.
        restore(folder,before);assert (folder/'calculations.json').read_bytes()==expected
        compact(folder,before);assert sealed_checks(folder)==before
        assert portal['app'].state.prop_analyses.fingerprint(report['id'])
        with pytest.raises(ValueError,match='immutable research campaign'):
            portal['app'].state.prop_analyses.delete(report['id'])
        repeated=page.request.get(portal['url']+f"/api/research-campaigns/{record['campaign_ids'][phase]}/exports/results.json")
        assert repeated.body()==expected
        storage.append(dict(phase=phase,analysis_id=report['id'],original_seals=before,
            logical_json_sha256=sha256(expected).hexdigest(),unpacked_bytes_avoided=len(expected),
            migration_preserved_bytes=True,dependency_deletion_guard=True))
    (tmp_path/'storage-verification.json').write_text(json.dumps(storage,indent=2))
    evaluation=json.loads((tmp_path/'evaluation-report.json').read_text())['calculations']
    funded=json.loads((tmp_path/'funded-report.json').read_text())['calculations']
    assert evaluation['frontier'] and funded['winner']
    for row in evaluation['candidates']:
        if row['metrics']['cost_per_funded'] is not None:
            expected=(sum(p['paid_fees'] for p in row['paths'])/len(row['paths']) if profile_id=='lucidflex-50k' else 49/row['metrics']['pass_probability']+129)
            assert abs(row['metrics']['cost_per_funded']-expected)<1e-8
    for row in funded['candidates']:
        assert row['metrics']['expected_funded_cash_payouts_within_horizon']==sum(p['cash_received'] for p in row['paths'])/len(row['paths'])
    page.locator('#prop-sim-funded-results').get_by_role('link',name='Job history / progress',exact=True).click()
    playwright.expect(page.get_by_role('link',name='Open Prop Sim',exact=True)).to_be_visible()
    page.get_by_role('link',name='Open Prop Sim',exact=True).click()
    playwright.expect(page.locator('#prop-sim-funded-table tbody tr')).to_have_count(3)
    page.reload()
    playwright.expect(page.locator('#prop-sim-funded-table tbody tr')).to_have_count(3)
    saved=page.request.get(portal['url']+'/api/prop-sim/'+record['id']).json()
    (tmp_path/'prop-sim.json').write_text(json.dumps(saved,indent=2))
    dataset=source['dataset']['id'];(tmp_path/'SYNTHETIC-source.csv').write_bytes(page.request.get(portal['url']+'/api/datasets/'+dataset+'/csv').body())
    (tmp_path/'journey.json').write_text(json.dumps(dict(synthetic=True,simulation_id=record['id'],workflow_id=workflow['id'],
        qualification=source['qualification'],source_backtest_id=source['source_backtest_id'],profile_id=profile_id,
        sizes=dict(evaluation=evaluation_sizes,funded=funded_sizes),paths_per_size_per_phase=32,
        expected_evaluation_cost_formula='mean paid fees across all completed calendar paths' if profile_id=='lucidflex-50k' else '49 / empirical_attempt_pass_probability + 129',
        expected_funded_receipts_formula='sum(path.cash_received for all starts) / 32',
        evaluation=[dict(micros=r['manifest']['configuration']['micros'],metrics=r['metrics'],pareto=r['pareto_member']) for r in evaluation['candidates']],
        funded=[dict(micros=r['manifest']['configuration']['micros'],metrics=r['metrics'],rank=r['rank']) for r in funded['candidates']],
        portfolio_optimization=False,provider_parity='Not claimed; local rule snapshot and held-OHLC bounds',server='Temporary server stopped by fixture teardown.'),indent=2))
    if destination:=os.environ.get('ALPHAQUEST_PROP_SIM_EVIDENCE_DIR'):
        target=Path(destination);target.mkdir(parents=True,exist_ok=True)
        for file in tmp_path.iterdir():
            if file.is_file() and file.suffix in ('.json','.csv','.zip','.png','.svg'):shutil.copyfile(file,target/file.name)


def test_evaluation_pareto_chart_tradeoffs_ties_and_unresolved_rows(page,portal):
    """Presentation-only oracle; real calculation/download journeys are above."""
    from uuid import uuid4
    id=uuid4().hex
    defaults=page.request.get(portal['url']+'/api/prop-sim/defaults').json()['defaults']
    saved=dict(id=id,configuration=dict(defaults,start_date='2026-11-16',closures=[],selections=[]),
        campaign_ids={p:uuid4().hex for p in ('evaluation','funded')},
        phases={p:dict(status='complete',analysis_id=uuid4().hex,progress='Fixture display only',error=None) for p in ('evaluation','funded')})
    rows=[]
    for size,cost,days,frontier in [(1,100,10,True),(2,200,5,True),(3,300,12,False),(4,None,None,False),(5,100,10,True)]:
        rows.append(dict(candidate_id=str(size),manifest=dict(configuration=dict(micros=size)),
            status='estimated' if cost is not None else 'unresolved',pareto_member=frontier,
            quantity_summary=dict(mean_requested_risk_budget=str(50*size)),
            metrics=dict(cost_per_funded=cost,expected_calendar_days_to_funded=days)))
    report=dict(calculations=dict(candidates=rows,frontier=['1','2','5']))
    page.route('**/api/prop-sim',lambda route:route.fulfill(json=dict(items=[])))
    page.route('**/api/prop-sim/'+id,lambda route:route.fulfill(json=saved))
    page.route('**/api/prop-sim/'+id+'/results/evaluation',lambda route:route.fulfill(json=report))
    page.route('**/api/prop-sim/'+id+'/results/funded',lambda route:route.fulfill(json=dict(calculations=dict(candidates=[],winner=None))))
    page.goto(portal['url']+'/#prop-sim?analysis='+id)
    page.locator('#prop-sim-evaluation-results .prop-sim-chart-details > summary').click()
    chart=page.locator('#prop-sim-evaluation-pareto')
    playwright.expect(chart).to_have_attribute('data-candidate-count','4')
    playwright.expect(chart).to_have_attribute('data-view','frontier')
    playwright.expect(chart.locator('circle')).to_have_count(2)
    page.locator('#prop-sim-pareto-all').click()
    playwright.expect(chart).to_have_attribute('data-view','all')
    playwright.expect(chart.locator('circle')).to_have_count(3)
    playwright.expect(chart.locator('circle[data-pareto="true"]')).to_have_count(2)
    points=chart.locator('polyline').get_attribute('points').split()
    assert len(points)==2
    first,last=[tuple(map(float,p.split(','))) for p in points]
    assert first[0]<last[0] and first[1]<last[1]  # Faster is left, greater cost is up.
    chart.locator('circle[data-sizes="1,5"]').focus()
    page.keyboard.press('Enter')
    playwright.expect(page.locator('#prop-sim-pareto-readout')).to_contain_text('1 MNQ / 5 MNQ')
    playwright.expect(page.locator('#prop-sim-evaluation-table tr.prop-sim-chart-highlight')).to_have_count(2)
    page.locator('#prop-sim-evaluation-table th button').filter(has_text='Mean requested risk').click()
    playwright.expect(page.locator('#prop-sim-evaluation-table tbody tr').first).to_have_attribute('data-size','1')
    rows[:]=[rows[0],rows[4]];report['calculations']['frontier']=['1','5']
    page.reload()
    page.locator('#prop-sim-evaluation-results .prop-sim-chart-details > summary').click()
    playwright.expect(chart).to_have_attribute('data-visible-count','2')
    playwright.expect(chart.locator('circle')).to_have_count(1)
    playwright.expect(chart.locator('polyline')).to_have_count(0)
    # Dense tradeoff frontier with two distant dominated outliers: no label pileup.
    rows[:]=[dict(candidate_id=str(size),manifest=dict(configuration=dict(micros=size)),
        status='estimated',pareto_member=True,metrics=dict(cost_per_funded=300-size*.5,
        expected_calendar_days_to_funded=40+size*.3)) for size in range(1,41)]
    for size,cost,days in [(99,600,200),(100,1000,500)]:
        rows.append(dict(candidate_id=str(size),manifest=dict(configuration=dict(micros=size)),
            status='estimated',pareto_member=False,metrics=dict(cost_per_funded=cost,expected_calendar_days_to_funded=days)))
    report['calculations']['frontier']=[str(size) for size in range(1,41)]
    page.reload()
    page.locator('#prop-sim-evaluation-results .prop-sim-chart-details > summary').click()
    playwright.expect(chart).to_have_attribute('data-visible-count','40')
    playwright.expect(chart).to_have_attribute('data-candidate-count','42')
    assert not any('MNQ' in text for text in chart.locator('text').all_text_contents())
    playwright.expect(chart.locator('title')).to_have_count(0)
    page.locator('#prop-sim-pareto-size').select_option('39')
    playwright.expect(page.locator('#prop-sim-pareto-readout')).to_contain_text('40 MNQ')
    playwright.expect(page.locator('.pareto-metrics')).to_contain_text('$280.00')
    playwright.expect(page.locator('.pareto-metrics')).to_contain_text('52.00 days')
    page.locator('#prop-sim-pareto-size').select_option('41')
    playwright.expect(chart).to_have_attribute('data-view','all')
    playwright.expect(chart).to_have_attribute('data-visible-count','42')
    assert chart.locator('circle').last.get_attribute('data-pareto')=='true'
    page.locator('#prop-sim-pareto-focus').click()
    playwright.expect(chart).to_have_attribute('data-visible-count','40')
    page.set_viewport_size(dict(width=390,height=844))
    playwright.expect(chart).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    with page.expect_download() as download:page.get_by_role('link',name='Pareto chart SVG ↓',exact=True).click()
    assert b'Frontier detail' in download.value.path().read_bytes()
    for row in rows:row['pareto_member']=False
    report['calculations']['frontier']=[]
    page.reload()
    page.locator('#prop-sim-evaluation-results .prop-sim-chart-details > summary').click()
    playwright.expect(chart).to_have_attribute('data-view','all')
    playwright.expect(page.locator('#prop-sim-pareto-focus')).to_be_disabled()
    playwright.expect(chart.locator('polyline')).to_have_count(0)
    for row in rows:
        row['status']='unresolved';row['metrics'].update(cost_per_funded=None,expected_calendar_days_to_funded=None)
    page.reload()
    page.locator('#prop-sim-evaluation-results .prop-sim-chart-details > summary').click()
    playwright.expect(page.locator('.prop-sim-pareto')).to_contain_text('No resolved cost/time points')
    playwright.expect(page.locator('#prop-sim-evaluation-pareto')).to_have_count(0)
    playwright.expect(page.locator('#prop-sim-evaluation-table tbody tr')).to_have_count(42)


def test_delete_saved_simulation_confirmation_and_source_preservation(page,portal,tmp_path):
    """Actual qualified product run -> cancel/confirm deletion -> retained sources."""
    import hashlib
    from test_prop_sim import body,wait_prop
    with httpx.Client(base_url=portal['url'],timeout=120) as client:
        workflow,source=qualified_source(client)
        request=dict(body(source),evaluation_maximum_micros=1,funded_maximum_micros=1,simulations=8)
        response=client.post('/api/prop-sim',json=request);assert response.status_code==202,response.text
        saved=wait_prop(client,response.json()['id'])
        source_before=client.get('/api/backtests/'+source['source_backtest_id']).json()
        mc_id=source['selection']['monte_carlo_id'].replace('-','')
        mc_before=client.get('/api/prop-analyses/'+mc_id+'/downloads/report.json').content
        plan=client.get('/api/prop-sim/'+saved['id']+'/deletion').json()
    page.goto(portal['url']+'/#prop-sim?analysis='+saved['id'])
    button=page.get_by_role('button',name='Delete simulation',exact=True)
    playwright.expect(button).to_be_enabled()
    page.locator('.prop-sim-run-heading').screenshot(path=str(tmp_path/'delete-action.png'))
    page.once('dialog',lambda dialog:dialog.dismiss());button.click()
    assert page.request.get(portal['url']+'/api/prop-sim/'+saved['id']).status==200
    page.once('dialog',lambda dialog:dialog.accept())
    with page.expect_response(lambda r:r.url.endswith('/api/prop-sim/'+saved['id']) and r.request.method=='DELETE') as response:button.click()
    receipt=response.value.json();assert response.value.status==200 and receipt['deleted']
    assert len(receipt['analysis_ids_to_delete'])==2 and not receipt['retained_analyses']
    playwright.expect(page).to_have_url(portal['url']+'/#prop-sim?deleted='+saved['id'])
    playwright.expect(page.locator('.prop-sim-deleted')).to_contain_text('Saved simulation deleted')
    playwright.expect(page.locator('#prop-sim-history option[value="'+saved['id']+'"]')).to_have_count(0)
    assert page.request.get(portal['url']+'/api/prop-sim/'+saved['id']).status==404
    source_after=page.request.get(portal['url']+'/api/backtests/'+source['source_backtest_id']).json()
    assert source_after==source_before
    assert page.request.get(portal['url']+'/api/prop-analyses/'+mc_id+'/downloads/report.json').body()==mc_before
    assert page.request.get(portal['url']+'/api/campaign-workflows/'+workflow['id']).json()['narrow']==workflow['narrow']
    for phase in saved['phases'].values():
        assert page.request.get(portal['url']+'/api/jobs/prop_analysis/'+phase['analysis_id']).status==404
    page.reload();playwright.expect(page.locator('.prop-sim-deleted')).to_contain_text('Saved simulation deleted')
    page.set_viewport_size(dict(width=390,height=844))
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.locator('.prop-sim-deleted').screenshot(path=str(tmp_path/'deleted-mobile.png'))
    (tmp_path/'deletion-preview.json').write_text(json.dumps(plan,indent=2))
    (tmp_path/'deletion-receipt.json').write_text(json.dumps(receipt,indent=2))
    (tmp_path/'preservation-verification.json').write_text(json.dumps(dict(synthetic=True,simulation_id=saved['id'],
        cancelled_confirmation_kept_simulation=True,deleted_reports=2,retained_reports=0,
        source_backtest_id=source['source_backtest_id'],source_report_unchanged=True,frozen_narrow_unchanged=True,
        monte_carlo_report_sha256=hashlib.sha256(mc_before).hexdigest(),monte_carlo_report_unchanged=True,
        deleted_job_links_absent=True,deleted_entry_absent=True,reload_receipt=True,mobile_no_page_overflow=True,
        server='Temporary isolated server stopped by fixture teardown.'),indent=2))
    if destination:=os.environ.get('ALPHAQUEST_PROP_DELETE_EVIDENCE_DIR'):
        target=Path(destination);target.mkdir(parents=True,exist_ok=True)
        for name in ('delete-action.png','deleted-mobile.png','deletion-preview.json','deletion-receipt.json','preservation-verification.json'):
            shutil.copyfile(tmp_path/name,target/name)


def test_prop_sim_variants_frozen_assessment_robustness_precision_product_journey(page,portal,tmp_path):
    from uuid import uuid4
    from test_prop_evaluation_validation import wait_assessment
    with httpx.Client(base_url=portal['url'],timeout=120) as client:
        workflow,source=qualified_source(client)
    page.goto(portal['url']+'/#prop-sim?source='+source['source_backtest_id'])
    page.locator('#prop-sim-profile').select_option('lucidflex-50k')
    page.locator('#prop-sim-consistency').select_option('50')
    playwright.expect(page.locator('#prop-sim-evaluation_price')).to_have_value('')
    page.locator('#prop-sim-evaluation_price').fill('99.50')
    for phase in ('evaluation','funded'):
        page.locator('#prop-sim-'+phase+'_minimum_micros').fill('12')
        page.locator('#prop-sim-'+phase+'_maximum_micros').fill('13' if phase=='evaluation' else '12')
    page.locator('#prop-sim-simulations').fill('16')
    page.get_by_text('Costs, calendar and optional risk settings',exact=True).click()
    page.locator('#prop-sim-start_date').fill('2026-11-16')
    page.locator('#prop-sim-check').click()
    playwright.expect(page.locator('#prop-sim-status')).to_contain_text('Source compatible',timeout=30000)
    page.locator('#prop-sim-form').screenshot(path=str(tmp_path/'variant-configuration.png'))
    with page.expect_response(lambda r:r.url.endswith('/api/prop-sim') and r.request.method=='POST') as response:
        page.locator('#prop-sim-run').click()
    saved=response.value.json();assert response.value.status==202
    assert saved['configuration']['evaluation_consistency_percent']==50
    summary={}
    with httpx.Client(base_url=portal['url'],timeout=120) as client:
        for phase in ('evaluation','funded'):
            playwright.expect(page.locator('#prop-sim-'+phase+'-progress')).to_contain_text('COMPLETE',timeout=90000)
            root=page.locator('#prop-sim-'+phase+'-validation')
            table=page.locator('#prop-sim-'+phase+'-table')
            assert root.locator('[data-freeze-candidate]').count()==0
            chosen=table.locator('[data-freeze-candidate]:enabled').first
            chosen_id=chosen.get_attribute('value');chosen.check()
            playwright.expect(root.locator('.prop-sim-selection-summary')).to_contain_text('Selected: 12 MNQ · 1 of 4 sizes')
            table.locator('th button').first.click()
            playwright.expect(table.locator('[data-freeze-candidate="'+chosen_id+'"]')).to_be_checked()
            table.locator('th button').first.click()
            root.screenshot(path=str(tmp_path/(phase+'-selection-summary.png')))
            root.get_by_label(phase+' freeze rationale',exact=True).fill('Synthetic product journey: preserve this declared size across every assessment.')
            root.get_by_role('button',name='Freeze selected sizes',exact=True).click()
            playwright.expect(root).to_contain_text('Choices frozen',timeout=30000)
            assert table.locator('[data-freeze-candidate]:enabled').count()==0
            playwright.expect(root.locator('.prop-sim-selection-summary')).to_contain_text('Frozen choices: 12 MNQ')
            diagnostics=root.locator('.prop-sim-diagnostics')
            assert diagnostics.get_attribute('open') is None
            playwright.expect(root.get_by_role('button',name='Run OOS assessment',exact=True)).to_have_class('button primary')
            prefix='/api/prop-sim/'+saved['id']+'/validation/'+phase
            frozen=client.get(prefix).json()['frozen']
            assert frozen['candidate_ids']==[chosen_id]
            playwright.expect(root.get_by_role('button',name='Run OOS assessment',exact=True)).to_be_disabled()
            limits=dict(maximum_cost_per_funded='500',maximum_calendar_days_to_funded='180') if phase=='evaluation' else dict(minimum_funded_receipts='100')
            for name,value in limits.items():root.get_by_label(phase+' '+name,exact=True).fill(value)
            root.get_by_role('button',name='Save assessment limits',exact=True).click()
            playwright.expect(root).to_contain_text('Declared before the first Prop Sim OOS result',timeout=30000)
            playwright.expect(root.get_by_role('button',name='Check account-start sensitivity',exact=True)).to_be_disabled()
            results=[]
            for kind,text,paths in [('oos','Run OOS assessment',None),('account_starts','Check account-start sensitivity',None),('is_robustness','Check IS blocks and subperiods',8),('precision','Run more paths for frozen sizes',64)]:
                if paths is not None:
                    if diagnostics.get_attribute('open') is None:diagnostics.locator('summary').click()
                    root.get_by_label(phase+' diagnostic paths',exact=True).fill(str(paths))
                with page.expect_response(lambda r:r.url.endswith(prefix) and r.request.method=='POST') as started:
                    root.get_by_role('button',name=text,exact=True).click()
                assert started.value.status==202,started.value.text()
                attempt=started.value.json()
                _,report=wait_assessment(client,prefix,attempt['request_id'])
                box=root.locator('[data-assessment="'+attempt['request_id']+'"]')
                playwright.expect(box.locator('[role=status]')).to_contain_text('COMPLETE',timeout=30000)
                playwright.expect(box.locator('table').first).to_be_visible()
                assert report['calculations']['winner'] is None
                assert {r['frozen_candidate_id'] for r in report['calculations']['candidates']}=={chosen_id}
                if kind=='oos':assert all(r['chronological_replay'] for r in report['calculations']['candidates'])
                if kind in ('oos','account_starts'):
                    for row in report['calculations']['candidates']:
                        assert row['economic_assessment']['verdict']=='PASS'
                        if phase=='funded':
                            values=sorted(p['cash_received'] for p in row['paths'])
                            assert row['outcome_summary']['cash_quantiles']['median']==values[(len(values)+1)//2-1]
                            assert row['outcome_summary']['probability_zero_received_cash']==values.count(0)/len(values)
                    if kind=='account_starts':
                        sensitivity=report['calculations']['account_start_sensitivity']
                        assert sensitivity['status']=='COMPLETE' and sensitivity['simulations']==5
                        scenarios=sensitivity['candidates'][0]['paths'];assert len(scenarios)==5
                        if phase=='evaluation':
                            assert [p['start_date'] for p in scenarios]==['2026-01-01','2026-02-17','2026-04-03','2026-05-19','2026-07-03']
                            assert [p['result']['calendar_days_to_funded'] for p in scenarios]==[6,20,5,21,5]
                            assert all(p['result']['paid_fees']==99.5 and p['result']['attempts_started']==1 for p in scenarios)
                        else:
                            assert [p['start_date'] for p in scenarios]==['2026-01-01','2026-03-11','2026-05-19','2026-07-27','2026-10-02']
                            # Each full payout is $2,000 gross × 90% = $1,800;
                            # the March start's second receipt falls after cutoff.
                            assert [p['result']['cash_received'] for p in scenarios]==[3600,1800,3600,0,3600]
                            assert [p['result']['pending_cash'] for p in scenarios]==[0,1800,0,0,0]
                            assert scenarios[3]['result']['outcome']=='inactive'
                        root.screenshot(path=str(tmp_path/(phase+'-account-starts.png')))
                    else:
                        box.locator('.prop-sim-review-details > summary').first.click()
                        box.screenshot(path=str(tmp_path/(phase+'-economic-assessment.png')))
                if kind=='is_robustness':assert {r['scenario'] for r in report['calculations']['candidates']}=={'block_1','block_5','block_20','first_half','second_half'}
                if kind=='precision':assert all(len(r['paths'])==64 for r in report['calculations']['candidates'])
                (tmp_path/(phase+'-'+kind+'-report.json')).write_text(json.dumps(report,indent=2))
                with page.expect_download() as download:box.get_by_role('link',name='Assessment evidence ZIP ↓',exact=True).click()
                download.value.save_as(tmp_path/(phase+'-'+kind+'-evidence.zip'))
                results.append(dict(kind=kind,request_id=attempt['request_id'],analysis_id=attempt['analysis_id'],rows=len(report['calculations']['candidates'])))
            assert client.get(prefix).json()['frozen']==frozen
            baseline=client.get('/api/prop-sim/'+saved['id']+'/results/'+phase).json()
            if phase=='evaluation':
                for row in baseline['calculations']['candidates']:
                    if row['status']=='estimated':
                        m=row['metrics'];assert abs(m['cost_per_funded']-sum(p['paid_fees'] for p in row['paths'])/16)<1e-8
                        assert abs(m['expected_calendar_days_to_funded']-sum(p['calendar_days_to_funded'] for p in row['paths'])/16)<1e-8
                        assert abs(sum(m['mean_'+key] for key in ['days_before_final_attempt','final_attempt_days_before_target','final_attempt_days_after_target','pass_to_ready_days'])-m['expected_calendar_days_to_funded'])<1e-8
                assert 'paired_comparisons' in baseline['calculations']
            else:
                for row in baseline['calculations']['candidates']:assert row['metrics']['expected_funded_cash_payouts_within_horizon']==sum(p['cash_received'] for p in row['paths'])/16
            (tmp_path/(phase+'-baseline-report.json')).write_text(json.dumps(baseline,indent=2))
            diagnostics.locator('summary').click()
            page.locator('#prop-sim-'+phase+'-results').screenshot(path=str(tmp_path/(phase+'-validation.png')))
            summary[phase]=dict(frozen=frozen,studies=results,baseline_metrics=[r['metrics'] for r in baseline['calculations']['candidates']])
            # A changed business decision creates a new version and reuses OOS
            # paths while retaining the earlier PASS report untouched.
            current=client.get(prefix).json()['assessment_policy']
            root.get_by_role('button',name='Revise assessment limits',exact=True).click()
            field='maximum_cost_per_funded' if phase=='evaluation' else 'minimum_funded_receipts'
            root.get_by_label(phase+' '+field,exact=True).fill('1')
            root.get_by_role('button',name='Cancel revision',exact=True).click()
            playwright.expect(root.get_by_label(phase+' '+field,exact=True)).to_have_value(limits[field])
            root.get_by_role('button',name='Revise assessment limits',exact=True).click()
            root.get_by_label(phase+' '+field,exact=True).fill('50' if phase=='evaluation' else '5000')
            root.get_by_label(phase+' policy revision reason',exact=True).fill('SYNTHETIC: test a stricter corrected business limit without rerunning MC.')
            with page.expect_response(lambda r:r.url.endswith(prefix+'/policy/revisions') and r.request.method=='POST') as revised:
                root.get_by_role('button',name='Save new policy version',exact=True).click()
            assert revised.value.status==200,revised.value.text()
            revision=revised.value.json();assert revision['revision']==2 and revision['previous_policy_sha256']==current['policy_sha256']
            playwright.expect(root).to_contain_text('Policy version 2 · Retrospectively declared',timeout=30000)
            playwright.expect(root.get_by_role('button',name='Check account-start sensitivity',exact=True)).to_be_disabled()
            old_attempt=next(a for a in results if a['kind']=='oos')
            old_report=client.get(prefix+'/'+old_attempt['request_id']).json()
            old_box=root.locator('[data-assessment="'+old_attempt['request_id']+'"]')
            playwright.expect(old_box.locator('[data-policy-version]')).to_contain_text('superseded; retains its original verdict')
            with page.expect_response(lambda r:r.url.endswith(prefix) and r.request.method=='POST') as reapplied:
                root.get_by_role('button',name='Run OOS assessment',exact=True).click()
            assert reapplied.value.status==202,reapplied.value.text()
            attempt=reapplied.value.json();_,updated=wait_assessment(client,prefix,attempt['request_id'])
            new_box=root.locator('[data-assessment="'+attempt['request_id']+'"]')
            playwright.expect(new_box.locator('[role=status]')).to_contain_text('COMPLETE',timeout=30000)
            playwright.expect(new_box.locator('.prop-sim-review-details > summary')).to_contain_text('FAIL')
            assert all(r['economic_assessment']['verdict']=='FAIL' for r in updated['calculations']['candidates'])
            assert [r['paths'] for r in updated['calculations']['candidates']]==[r['paths'] for r in old_report['calculations']['candidates']]
            assert client.get(prefix+'/'+old_attempt['request_id']).json()==old_report
            assert client.get(prefix).json()['assessment_policy_history']==[current,revision]
            (tmp_path/(phase+'-revised-report.json')).write_text(json.dumps(updated,indent=2))
            with page.expect_download() as download:new_box.get_by_role('link',name='Assessment evidence ZIP ↓',exact=True).click()
            download.value.save_as(tmp_path/(phase+'-revised-evidence.zip'))
            root.get_by_text('Policy history · 2 versions',exact=True).click()
            root.screenshot(path=str(tmp_path/(phase+'-policy-revision.png')))
            summary[phase]['policy_revision']=dict(policy=revision,original_verdict='PASS',new_verdict='FAIL',mc_paths_unchanged=True,old_report_unchanged=True)
    page.reload()
    for phase in ('evaluation','funded'):
        root=page.locator('#prop-sim-'+phase+'-validation')
        playwright.expect(root).to_contain_text('Choices frozen',timeout=30000)
        playwright.expect(root.locator('[data-assessment]')).to_have_count(5,timeout=30000)
        playwright.expect(root).to_contain_text('Policy version 2 · Retrospectively declared')
        assert root.locator('.prop-sim-diagnostics').get_attribute('open') is None
        playwright.expect(root.get_by_role('button',name='Check IS blocks and subperiods',exact=True)).not_to_be_visible()
    page.set_viewport_size(dict(width=390,height=844))
    assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
    page.locator('#prop-sim-evaluation-validation').screenshot(path=str(tmp_path/'validation-mobile.png'))
    (tmp_path/'verification.json').write_text(json.dumps(dict(synthetic=True,simulation_id=saved['id'],source_backtest_id=source['source_backtest_id'],
        model='Local AlphaQuest; no Bridge runtime',consistency_percent=50,purchase_fee='99.50 user scenario',paths_per_size=16,
        expected='Fee/calendar means independently summed from all paths; time components sum to total. Explicit economic limits PASS; cash median/zero probability independently recomputed. Five covered chronological starts reuse the OOS MC results. Frozen IDs unchanged; five robustness scenarios; 64 precision paths; durable reload.',
        phases=summary,temporary_server='Stopped by fixture teardown',prior_access='OOS already accessed during strategy qualification; no untouched holdout claim'),indent=2))
    if destination:=os.environ.get('ALPHAQUEST_PROP_VALIDATION_EVIDENCE_DIR'):
        target=Path(destination);target.mkdir(parents=True,exist_ok=True)
        for file in tmp_path.iterdir():
            if file.is_file() and file.suffix in ('.json','.zip','.png'):shutil.copyfile(file,target/file.name)


def test_is_table_size_selection_limits_exclusions_sorting_and_compact_summary(page,portal,tmp_path):
    """Presentation-only 40-size oracle; the real qualified journey above proves execution."""
    from uuid import uuid4
    id=uuid4().hex
    defaults=page.request.get(portal['url']+'/api/prop-sim/defaults').json()['defaults']
    saved=dict(id=id,configuration=dict(defaults,start_date='2026-11-16',closures=[],selections=[]),
        campaign_ids={p:uuid4().hex for p in ('evaluation','funded')},
        phases={p:dict(status='complete',analysis_id=uuid4().hex,progress='UI fixture only',error=None) for p in ('evaluation','funded')})
    rows=[dict(candidate_id=str(size),manifest=dict(configuration=dict(micros=size)),
        status='unresolved' if size==40 else 'estimated',pareto_member=3<=size<=12,
        metrics=dict(cost_per_funded=100+size,expected_calendar_days_to_funded=200-size)) for size in range(1,41)]
    report=dict(calculations=dict(candidates=rows,frontier=[str(n) for n in range(3,13)],unresolved_candidates=['40']))
    funded=dict(calculations=dict(candidates=[dict(candidate_id='funded-1',manifest=dict(configuration=dict(micros=1)),
        status='estimated',feasible=False,rank=None,constraint_violations=['maximum_account_breach_probability'],metrics={})],winner=None,ranking=[]))
    page.route('**/api/prop-sim',lambda route:route.fulfill(json=dict(items=[])))
    page.route('**/api/prop-sim/'+id,lambda route:route.fulfill(json=saved))
    page.route('**/api/prop-sim/'+id+'/results/evaluation',lambda route:route.fulfill(json=report))
    page.route('**/api/prop-sim/'+id+'/results/funded',lambda route:route.fulfill(json=funded))
    for phase in ('evaluation','funded'):
        page.route('**/api/prop-sim/'+id+'/validation/'+phase,lambda route:route.fulfill(json=dict(
            numerical_implementation_compatible=True,campaign_id=uuid4().hex,frozen=None,assessments=[])))
    page.goto(portal['url']+'/#prop-sim?analysis='+id)
    table=page.locator('#prop-sim-evaluation-table');root=page.locator('#prop-sim-evaluation-validation')
    playwright.expect(table.locator('[data-freeze-candidate]:enabled')).to_have_count(10)
    assert root.locator('[data-freeze-candidate]').count()==0
    assert page.locator('.prop-sim-choice-grid').count()==0
    for size in [1,2,13,39]:
        row=table.locator('tr[data-size="'+str(size)+'"]')
        assert row.locator('input').count()==0
        playwright.expect(row.locator('[data-selection-status]')).to_have_text('Outside Pareto frontier')
    playwright.expect(table.locator('tr[data-size="40"] [data-selection-status]')).to_have_text('Unresolved')
    playwright.expect(page.locator('#prop-sim-funded-table [data-selection-status]')).to_have_text('Constraint failed: maximum account breach probability')
    for size in range(3,7):table.locator('[data-freeze-candidate="'+str(size)+'"]').check()
    playwright.expect(root.locator('.prop-sim-selection-summary')).to_have_text('Selected: 3, 4, 5, 6 MNQ · 4 of 4 sizes')
    playwright.expect(page.locator('#prop-sim-evaluation-summary')).to_contain_text('among resolved candidates only')
    playwright.expect(page.locator('#prop-sim-pareto-caption')).to_contain_text('compares resolved candidates only')
    playwright.expect(root).to_contain_text('You can freeze resolved, eligible sizes')
    root.get_by_label('evaluation freeze rationale',exact=True).fill('Resolve only the selected frontier sizes.')
    playwright.expect(root.get_by_role('button',name='Freeze selected sizes',exact=True)).to_be_enabled()
    playwright.expect(table.locator('[data-freeze-candidate="7"]')).to_be_disabled()
    table.locator('th button').first.click()
    for size in range(3,7):playwright.expect(table.locator('[data-freeze-candidate="'+str(size)+'"]')).to_be_checked()
    table.locator('[data-freeze-candidate="6"]').uncheck()
    playwright.expect(table.locator('[data-freeze-candidate="7"]')).to_be_enabled()
    playwright.expect(root.locator('.prop-sim-selection-summary')).to_have_text('Selected: 3, 4, 5 MNQ · 3 of 4 sizes')
    assert root.locator('[data-study-kind="oos"]').is_hidden()
    assert root.locator('.prop-sim-diagnostics').is_hidden()
    table.locator('th button').first.click()
    root.screenshot(path=str(tmp_path/'compact-selection.png'))
    page.set_viewport_size(dict(width=390,height=844))
    assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
    wrap=table.locator('..');wrap.evaluate('(el)=>el.scrollLeft=600')
    # Both the checkbox and MNQ size remain visible while comparing later metrics.
    positions=table.evaluate("(el)=>{const r=[...el.tBodies[0].rows].find(row=>row.dataset.size==='3');return [el.parentElement.getBoundingClientRect().left,r.children[0].getBoundingClientRect().left,r.children[1].getBoundingClientRect().left];}")
    assert positions[1]>=positions[0] and positions[2]>positions[1]


def test_forty_sizes_keep_one_thousand_paths_through_saved_product_results(page,portal,tmp_path):
    """Real source/check/workers/report path beyond the former 524-path cap."""
    import time
    from zipfile import ZipFile
    with httpx.Client(base_url=portal['url'],timeout=180) as client:
        workflow,source=qualified_source(client)
    page.goto(portal['url']+'/#backtests/report/'+source['source_backtest_id'])
    page.locator('#report-prop-setup').click()
    for phase in ('evaluation','funded'):
        page.locator('#prop-sim-'+phase+'_minimum_micros').fill('1')
        page.locator('#prop-sim-'+phase+'_maximum_micros').fill('40')
    page.locator('#prop-sim-funded_horizon_calendar_days').fill('10')
    page.locator('#prop-sim-simulations').fill('1000')
    playwright.expect(page.locator('#prop-sim-simulations')).to_have_value('1000')
    playwright.expect(page.locator('#prop-sim-preflight')).to_contain_text('80,000 total paths')
    playwright.expect(page.locator('#prop-sim-check')).to_be_enabled()
    page.get_by_text('Costs, calendar and optional risk settings',exact=True).click()
    page.locator('#prop-sim-start_date').fill('2026-11-16')
    page.locator('#prop-sim-form').screenshot(path=str(tmp_path/'forty-size-configuration.png'))
    with page.expect_response(lambda r:r.url.endswith('/api/prop-sim/check'),timeout=180000) as checked:
        page.locator('#prop-sim-check').click()
    assert checked.value.status==200,checked.value.text()
    check=checked.value.json()
    for phase in ('evaluation','funded'):
        assert check['phases'][phase]['candidate_search_count']==40
        assert all(c['simulation']['simulations']==1000 for c in check['phases'][phase]['request']['candidates'])
    playwright.expect(page.locator('#prop-sim-run')).to_be_enabled()
    with page.expect_response(lambda r:r.url.endswith('/api/prop-sim') and r.request.method=='POST',timeout=180000) as launched:
        page.locator('#prop-sim-run').click()
    assert launched.value.status==202,launched.value.text()
    saved=launched.value.json();outputs={}
    with httpx.Client(base_url=portal['url'],timeout=180) as client:
        deadline=time.monotonic()+900
        while True:
            saved=client.get('/api/prop-sim/'+saved['id']).json()
            if all(p['status'] not in ('queued','running') for p in saved['phases'].values()):break
            assert time.monotonic()<deadline,saved['phases']
            time.sleep(.5)
        assert all(p['status']=='complete' for p in saved['phases'].values()),saved['phases']
        for phase in ('evaluation','funded'):
            aid=saved['phases'][phase]['analysis_id']
            response=client.get('/api/prop-analyses/'+aid+'/downloads/analysis.zip')
            assert response.status_code==200,response.text
            archive=tmp_path/(phase+'-forty-size-evidence.zip');archive.write_bytes(response.content)
            with ZipFile(archive) as z:report=json.loads(z.read('report.json'))
            rows=report['calculations']['candidates'];assert len(rows)==40
            assert sorted(r['manifest']['configuration']['micros'] for r in rows)==list(range(1,41))
            for row in rows:
                assert row['manifest']['configuration']['simulation']['simulations']==1000
                assert len(row['paths'])==1000
                if phase=='funded':
                    assert abs(row['metrics']['expected_funded_cash_payouts_within_horizon']-sum(p['cash_received'] for p in row['paths'])/1000)<1e-8
                elif row['metrics']['cost_per_funded'] is not None:
                    assert abs(row['metrics']['cost_per_funded']-(49/row['metrics']['pass_probability']+129))<1e-8
            outputs[phase]=dict(analysis_id=aid,candidates=40,paths_per_candidate=1000,total_paths=40000,
                recorded_artifact_bytes=sum(f['bytes'] for f in report['files'].values()),zip_bytes=archive.stat().st_size)
            playwright.expect(page.locator('#prop-sim-'+phase+'-progress')).to_contain_text('COMPLETE',timeout=90000)
            playwright.expect(page.locator('#prop-sim-'+phase+'-table tbody tr')).to_have_count(40,timeout=90000)
    page.locator('#prop-sim-funded-results').screenshot(path=str(tmp_path/'forty-size-funded-results.png'))
    page.reload()
    playwright.expect(page.locator('#prop-sim-funded-table tbody tr')).to_have_count(40,timeout=90000)
    (tmp_path/'forty-size-verification.json').write_text(json.dumps(dict(synthetic=True,simulation_id=saved['id'],
        workflow_id=workflow['id'],source_backtest_id=source['source_backtest_id'],phases=outputs,
        funded_horizon_calendar_days=10,
        source_checked=True,paths_not_clipped=True,durable_reload=True,
        expected='40 candidates × 1000 paths per phase; Funded mean includes all 1000 path receipts; Evaluation cost = 49 / attempt pass probability + 129.',
        server='Isolated temporary server stops at fixture teardown; no user job submitted.'),indent=2))
    if destination:=os.environ.get('ALPHAQUEST_PROP_PATH_EVIDENCE_DIR'):
        target=Path(destination);target.mkdir(parents=True,exist_ok=True)
        for p in tmp_path.iterdir():
            if p.is_file() and p.suffix in ('.json','.zip','.png'):shutil.copyfile(p,target/p.name)
