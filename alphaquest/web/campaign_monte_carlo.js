"use strict";
(() => {
  const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
  const fmt=value=>value==null?'N/A':Number(value).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
  let generation=0,timer;
  function dispose(){++generation;clearTimeout(timer);}
  async function read(url,method='GET',body){
    const response=await window.portalLoading.fetch(url,{method,cache:'no-store',...(body?{headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})});
    const data=await response.json();if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'Monte Carlo request rejected.');return data;
  }
  function link(parent,text,href){const a=node('a',text,'workflow-inline-link');a.href=href;parent.append(a);}
  async function render(parent,workflowId,oosJobId,{isCurrent,eligible,mtmCandidates=[]}){
    dispose();const version=generation,alive=()=>version===generation&&isCurrent(),base=`/api/campaign-workflows/${workflowId}/oos/monte-carlo`;
    parent.replaceChildren(node('h2','Final Monte Carlo sanity check'));
    if(!oosJobId){parent.append(node('p','Complete OOS to check passing configurations across the full IS + OOS period.'));return;}
    const intro=node('p','Resample the saved daily net P&L across IS + OOS. 5,000 full-length paths at each of two mean block lengths (5 and 20 observed days), fixed seed 42. No strategy replay, parameter changes or extra cost deduction.');parent.append(intro);
    const rules=node('ul');rules.id='monte-carlo-rules';parent.append(rules);
    const workerLabel=node('label','Parallel workers'),workers=node('select');workers.id='monte-carlo-workers';workerLabel.append(workers);parent.append(workerLabel);
    const run=node('button','Run final Monte Carlo check','button primary');run.type='button';run.id='monte-carlo-run';run.disabled=true;parent.append(run);
    const stop=node('button','Stop Monte Carlo','button secondary');stop.type='button';stop.id='monte-carlo-stop';stop.hidden=true;parent.append(stop);
    const status=node('p');status.id='monte-carlo-status';status.setAttribute('role','status');parent.append(status);
    const error=node('p',undefined,'mechanic-error');error.setAttribute('role','alert');parent.append(error);
    const actions=node('div',undefined,'mechanic-downloads');parent.append(actions);
    const output=node('div');output.id='monte-carlo-results';parent.append(output);
    const diagnostics=node('p',undefined,'field-help');diagnostics.id='monte-carlo-diagnostics';parent.append(diagnostics);
    const caveat=node('p',undefined,'field-help');parent.append(caveat);
    let data,busy=false;
    function paint(){
      const job=data.job,active=['queued','running'].includes(job?.status),legacy=data.report&&data.report.policy.version!==data.policy.version;
      workers.disabled=busy||active;run.disabled=busy||active||!eligible||(job?.status==='complete'&&!legacy);stop.hidden=!active;stop.disabled=busy;
      run.textContent=legacy?'Apply updated policy to saved paths':job?.status==='complete'?'Saved Monte Carlo check':job?'Run final Monte Carlo check again':'Run final Monte Carlo check';
      status.textContent=job?`${job.status.toUpperCase()} · ${job.progress}${job.error?' · '+job.error:''}`:eligible?'Ready. Checks only verified OOS-passing configurations.':'No completed, qualifying OOS configurations are available.';
      if(!workers.options.length){for(let n=1;n<=(data.max_workers||4);n++)workers.add(new Option(String(n),String(n)));workers.value=String(data.default_workers||4);}
      rules.replaceChildren(...data.rules.map(text=>node('li',text)));caveat.textContent=data.limitations;diagnostics.textContent=data.diagnostics;
      actions.replaceChildren();if(job)link(actions,'Monte Carlo job history / progress',`#jobs/monte_carlo/${job.id}`);
      output.replaceChildren();if(!data.report)return;
      const report=data.report;
      status.textContent=`COMPLETE · ${report.passed} / ${report.total} configurations passed ${legacy?'the historical policy':'the final sanity check'}. OOS verdicts and IS selections are unchanged.`;
      if(legacy)output.append(node('p','This saved assessment used the earlier drawdown rejection rule. Apply the updated policy above to the same saved paths; no backtest or Monte Carlo rerun is needed. The original report is retained.'));
      for(const [format,label] of [['json','Monte Carlo report JSON ↓'],['zip','Monte Carlo evidence ZIP ↓'],['daily','Full-period daily P&L CSV ↓'],['paths','Simulated path outcomes CSV ↓']])link(actions,label,`${base}/jobs/${job.id}/download?format=${format}`);
      if(report.reused_population){output.append(node('p','Updated assessment uses the original saved path outcomes. No new simulation was run.'));link(actions,'Original assessment JSON ↓',`${base}/jobs/${report.reused_population.analysis_id}/download`);}
      output.append(node('p',`IS ${report.plan.is_start} → ${report.plan.is_end}; OOS ${report.plan.oos_start} → ${report.plan.oos_end}. Gap between windows: ${report.unobserved_split_gap_calendar_days} calendar days. Paths contain exactly the saved observed dates; missing dates are not filled.`));
      const scroll=node('div',undefined,'optimization-scroll'),table=node('table',undefined,'library-table');table.id='monte-carlo-table';
      output.append(node('p','IS/OOS drawdowns below use every bar close, including open-position P&L, from the frozen backtests. Daily-close Monte Carlo drawdowns are available in the optional details below. Mean/median profit and drawdown metrics add no Monte Carlo pass/fail gates.','field-help'));
      const mtmByCandidate=new Map(mtmCandidates.map(item=>[item.trial,item]));
      const headers=[['candidate','Candidate'],['status','Final status'],['evidence','Evidence'],['block','Mean block · observed days'],['p05','5th %ile net profit'],['is_mtm_dd','IS max drawdown · bar-close MTM'],['oos_mtm_dd','OOS max drawdown · bar-close MTM'],['historical_net','Historical net profit'],['mean_net','Mean net profit'],['median_net','Median net profit'],['profitable','Profitable paths %'],['checks','Required checks']];
      const head=node('tr');for(const [key,text] of headers){const th=node('th',text);th.dataset.column=key;head.append(th);}const thead=node('thead');thead.append(head);table.append(thead);
      const body=node('tbody');
      const drawdownDetails=node('details',undefined,'optimization-freeze');drawdownDetails.id='monte-carlo-drawdown-details';
      drawdownDetails.append(node('summary','Daily-close Monte Carlo drawdown diagnostics (optional)'),node('p','These diagnostics sample equity only at the last observed bar of each source-local calendar date. They describe the daily-P&L bootstrap, can miss intraday peaks and losses, and are not the stitched every-bar MTM maximum drawdown. Daily-close risk is not sufficient to assess intraday account-rule breaches.','field-help'));
      const dailyScroll=node('div',undefined,'optimization-scroll'),dailyTable=node('table',undefined,'library-table');dailyTable.id='monte-carlo-drawdown-table';
      const dailyHeaders=[['candidate','Candidate'],['block','Mean block · observed days'],['historical_dd','Historical daily-close DD'],['median_dd','Median daily-close DD'],['p95_dd','95th %ile daily-close DD'],['dd_multiple','95th %ile DD / historical DD'],['dd_percentile','Historical DD percentile %']];
      const dailyHead=node('tr');for(const [key,text] of dailyHeaders){const th=node('th',text);th.dataset.column=key;dailyHead.append(th);}const dailyThead=node('thead');dailyThead.append(dailyHead);dailyTable.append(dailyThead);
      const dailyBody=node('tbody');
      for(const candidate of report.candidates)for(const scenario of candidate.scenarios){
        const row=node('tr');row.dataset.candidate=candidate.candidate;
        if(!candidate.qualifies)row.className='broad-ineligible';
        const mtm=mtmByCandidate.get(candidate.candidate);
        const values=[String(candidate.candidate),candidate.qualifies?'Passed':'Failed',`${candidate.observed.days} observed dates · ${candidate.observed.closed_trades} trades`,String(scenario.mean_block_days),fmt(scenario.net_profit_p05),fmt(mtm?.is_reference?.metrics?.is_mtm_max_drawdown),fmt(mtm?.metrics?.oos_mtm_max_drawdown),fmt(candidate.observed.net_profit),fmt(scenario.net_profit_mean),fmt(scenario.net_profit_median),`${fmt(scenario.profitable_paths_pct)} (MC SE ${fmt(scenario.profitable_paths_mc_se_pp)} pp)`];
        values.forEach((text,i)=>{const td=node('td',text);td.dataset.column=headers[i][0];row.append(td);});
        const details=node('td'),list=node('ul');details.dataset.column='checks';list.append(node('li',`${candidate.evidence_passed?'PASS':'FAIL'} · Minimum evidence`));for(const check of scenario.checks)list.append(node('li',`${check.passed?'PASS':'FAIL'} · ${check.label}: ${fmt(check.actual)}. Required: ${check.required}`));details.append(list);row.append(details);body.append(row);
        const dailyRow=node('tr');dailyRow.dataset.candidate=candidate.candidate;
        const dailyValues=[String(candidate.candidate),String(scenario.mean_block_days),fmt(candidate.observed.daily_close_max_drawdown),fmt(scenario.max_drawdown_median),fmt(scenario.max_drawdown_p95),scenario.max_drawdown_p95_over_observed==null?'N/A':fmt(scenario.max_drawdown_p95_over_observed)+'×',fmt(scenario.historical_drawdown_percentile_pct)];
        dailyValues.forEach((text,i)=>{const td=node('td',text);td.dataset.column=dailyHeaders[i][0];dailyRow.append(td);});dailyBody.append(dailyRow);
      }
      table.append(body);scroll.append(table);dailyTable.append(dailyBody);dailyScroll.append(dailyTable);drawdownDetails.append(dailyScroll);output.append(scroll,drawdownDetails);
    }
    async function refresh(){
      clearTimeout(timer);
      const finishLoading=!data?window.portalLoading.begin(status,{label:'Loading Monte Carlo evidence…'}):()=>{};
      try{const next=await read(base+'?job='+oosJobId);if(!alive())return;data=next;paint();if(['queued','running'].includes(data.job?.status))timer=setTimeout(refresh,2500);}
      catch(exc){if(alive()){error.textContent=exc.message;status.textContent='Could not load Monte Carlo evidence.';}}finally{finishLoading();}
    }
    run.onclick=async()=>{if(busy)return;busy=true;paint();error.textContent='';try{await read(base+'/run','POST',{job_id:oosJobId,workers:Number(workers.value)});if(alive())await refresh();}catch(exc){if(alive())error.textContent=exc.message;}finally{busy=false;if(alive()&&data)paint();}};
    stop.onclick=async()=>{if(busy||!data.job)return;busy=true;paint();try{await read(`/api/prop-analyses/${data.job.id}/cancel`,'POST');if(alive())await refresh();}catch(exc){if(alive())error.textContent=exc.message;}finally{busy=false;if(alive())paint();}};
    await refresh();
  }
  window.campaignMonteCarlo={render,dispose};
})();
