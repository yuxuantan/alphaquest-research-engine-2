"""Risk evidence through an ordinary saved source/report and download."""
import json,os,shutil
from pathlib import Path
from decimal import Decimal
from test_backtests_browser import browser,page,portal,playwright
from research_fixtures import ResearchHTTPClient
from test_native_replay_api import source


def test_normal_report_risk_panel_and_durable_download(page,portal,tmp_path):
 with ResearchHTTPClient(base_url=portal['url'],timeout=180) as client:record=source(client)
 page.goto(portal['url']+'/#backtests/report/'+record['id'])
 panel=page.locator('#report-summary .research-risk-diagnostics')
 playwright.expect(panel).to_be_visible(timeout=30000)
 panel.locator('summary').click()
 playwright.expect(panel).to_contain_text('3 / 3 trades have valid causal risk evidence')
 playwright.expect(panel).to_contain_text('Mean 0.67R')
 assert panel.locator('input[type=checkbox]').count()==0
 with page.expect_download() as download:panel.get_by_role('link',name='Risk diagnostics JSON ↓',exact=True).click()
 path=tmp_path/'risk_metrics.json';download.value.save_as(path);data=json.loads(path.read_text())
 assert [Decimal(r['planned_net_r']) for r in data['trades']]==[-1,2,1]
 panel.screenshot(path=str(tmp_path/'risk-panel.png'))
 page.reload();panel=page.locator('#report-summary .research-risk-diagnostics');panel.locator('summary').click()
 playwright.expect(panel).to_contain_text('3 / 3 trades')
 page.set_viewport_size(dict(width=390,height=844));panel.screenshot(path=str(tmp_path/'risk-mobile.png'))
 assert page.locator('body').evaluate('(e)=>e.scrollWidth<=window.innerWidth+1')
 (tmp_path/'journey.json').write_text(json.dumps(dict(synthetic=True,source_id=record['id'],expected_r=[-1,2,1],expected_mean_r='2/3',same_original_dollar_results=True,qualification_effect='diagnostic only',server='Temporary browser server stopped by fixture teardown'),indent=2))
 if target:=os.environ.get('ALPHAQUEST_RISK_EVIDENCE_DIR'):
  p=Path(target);p.mkdir(parents=True,exist_ok=True)
  for f in tmp_path.iterdir():
   if f.is_file() and f.suffix in ('.json','.png'):shutil.copyfile(f,p/f.name)
