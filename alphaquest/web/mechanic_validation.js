"use strict";

(() => {
  const get = selector => document.querySelector(selector);
  const node = (tag, text, className) => {
    const item = document.createElement(tag);
    if (text !== undefined) item.textContent = text;
    if (className) item.className = className;
    return item;
  };
  const labels = {consecutive_green_hold:'Consecutive Green Hold',vwap_pullback_risk_sizing:'ORB + VWAP pullback',twin_continuation:'Twin continuation'};
  let token = 0, current, saving = false, timer;
  const route = () => location.hash.match(/^#campaigns\/workflows\/([a-f0-9]{32})\/(mechanic_validation|is_broad|is_narrow|oos)(?:\?(?:job=([a-f0-9]{32})|broad_trial=(\d+)))?$/);
  const endpoint = id => `/api/campaign-workflows/${id}`;
  const read = async (url, method = 'GET', body) => {
    const response = await fetch(url, {method, cache:'no-store', ...(body === undefined ? {} : {headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});
    const data = await response.json();
    if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : 'The request was rejected. Review your saved source and settings.');
    return data;
  };
  function link(parent, text, href) {
    const item = node('a',text,'workflow-inline-link'); item.href = href; parent.append(item); return item;
  }
  function message(text) { get('#mechanic-status').textContent = text; }
  function table(title, headers) {
    const section = node('section',undefined,'panel mechanic-results');
    section.append(node('h2',title));
    section.append(node('p','Scroll horizontally to see every value and review checkbox.','mechanic-scroll-help muted'));
    const scroll = node('div',undefined,'mechanic-table-scroll'), table = node('table',undefined,'library-table');
    scroll.tabIndex = 0; scroll.setAttribute('aria-label',`${title}, scroll horizontally`);
    const head = node('thead'), row = node('tr'); headers.forEach(text => row.append(node('th',text))); head.append(row);
    const body = node('tbody'); table.append(head,body); scroll.append(table); section.append(scroll);
    return {section, body};
  }
  function checkbox(key, id, title, workflow, completed) {
    const cell = node('td'), label = node('label',undefined,'mechanic-check'), input = node('input');
    input.type = 'checkbox'; input.checked = workflow.review[key][id]; input.disabled = completed || saving;
    input.dataset.reviewGroup = key; input.dataset.reviewId = id; input.setAttribute('aria-label',title);
    input.onchange = () => saveChecks(workflow);
    label.append(input,node('span','Confirmed')); cell.append(label); return cell;
  }
  async function saveChecks(workflow) {
    if (saving) return;
    const review = workflow.review;
    const body = {revision:review.revision};
    for (const key of ['metric_checks','trade_parity','trade_correctness']) body[key] = {...review[key]};
    for (const input of get('#mechanic-content').querySelectorAll('[data-review-group]')) body[input.dataset.reviewGroup][input.dataset.reviewId] = input.checked;
    saving = true;
    get('#mechanic-content').querySelectorAll('input,button').forEach(input => input.disabled = true);
    const active = token, id = workflow.id;
    message('Saving review checks…');
    try {
      const saved = await read(endpoint(id)+'/review','PATCH',body);
      if (active === token) { current = saved; render(saved,'mechanic_validation'); message('Review checks saved.'); }
    } catch (error) {
      if (active === token) { message(error.message+' Reload this workflow to recover the saved checks.'); recovery(id); }
    } finally { if (active === token) { saving = false; if (current?.id === id) enableChecks(); } }
  }
  function enableChecks() {
    const passed = current.status === 'passed';
    get('#mechanic-content').querySelectorAll('[data-review-group]').forEach(input => input.disabled = passed);
    const confirm = get('#mechanic-confirm');
    if (confirm) confirm.disabled = passed || !canConfirm(current);
  }
  function canConfirm(workflow) {
    const review = workflow.review;
    return review && ['metric_checks','trade_parity','trade_correctness'].every(key => Object.keys(review[key]).length > 0 && Object.values(review[key]).every(Boolean));
  }
  function recovery(id) {
    const button = node('button','Reload saved review','button secondary');
    button.onclick = () => navigate(); get('#mechanic-content').append(button);
  }
  function render(workflow, phase) {
    const saved = workflow.declaration, passed = workflow.status === 'passed';
    get('#mechanic-title').textContent = labels[saved.strategy_id] || saved.strategy_id;
    get('#mechanic-source').textContent = `${saved.dataset.name} · ${saved.dataset.symbol || 'Unspecified instrument'} · IS ${saved.plan.is_start} → ${saved.plan.is_end} · ${saved.dataset.source_timezone}`;
    get('#mechanic-back').href = `#campaigns/${saved.strategy_id}`;
    const navigation = get('#mechanic-phases'); navigation.replaceChildren();
    for (const [index,item] of workflow.phases.entries()) {
      const button = node('button',undefined,'mechanic-phase'); button.type = 'button'; button.dataset.phase = item.id;
      button.dataset.status = item.status;
      const number = node('span',String(index+1).padStart(2,'0'),'mechanic-step-index');
      number.setAttribute('aria-hidden','true');
      const copy = node('span',undefined,'mechanic-phase-copy');
      copy.append(node('strong',item.label),node('span',item.status.replaceAll('_',' '),'mechanic-phase-state'));
      button.append(number,copy);
      button.setAttribute('aria-label',`Step ${index+1} of ${workflow.phases.length}: ${item.label}, ${item.status.replaceAll('_',' ')}`);
      button.disabled = item.status === 'locked';
      if (phase === item.id) button.setAttribute('aria-current','step');
      button.onclick = () => { location.hash = `#campaigns/workflows/${workflow.id}/${item.id}`; };
      navigation.append(button);
    }
    const host = get('#mechanic-content'); host.replaceChildren();
    const activeCriteria = token, criteriaHost = get('#workflow-stage-criteria');
    criteriaHost.replaceChildren(node('h2','Passing criteria by stage'));
    read('/api/campaign-workflow-criteria').then(data => {
      if(activeCriteria!==token)return;
      criteriaHost.append(node('p','Rules are fixed before the search. Insufficient evidence cannot qualify. IS calculations use bar-close equity including open P&L; this is not tick-level drawdown.'));
      for(const stage of data.stages){
        const details=node('details');details.dataset.stage=stage.id;details.open=stage.id===phase;
        details.append(node('summary',`${stage.label} · ${stage.implemented?'Implemented':'Agreed plan · not implemented'}`));
        const list=node('ol');for(const rule of stage.rules)list.append(node('li',rule));details.append(list);criteriaHost.append(details);
      }
    }).catch(error=>{if(activeCriteria===token)criteriaHost.append(node('p',error.message));});
    if (phase === 'is_broad') {
      const active=token;
      window.campaignBroad.render(host,workflow,{isCurrent:()=>active===token,jobId:route()?.[3]});
      return;
    }
    if (phase === 'is_narrow') {
      const active=token;
      window.campaignNarrow.render(host,workflow,{isCurrent:()=>active===token,broadTrial:route()?.[4]});
      return;
    }
    if (phase !== 'mechanic_validation') {
      const intro = node('section',undefined,'panel mechanic-results');
      intro.append(node('h2',workflow.phases.find(p => p.id === phase).label),node('p','Navigation is ready. Running and passing this phase will be added in a later update.'));
      host.append(intro); return;
    }
    if (!workflow.review) {
      const intro = node('section',undefined,'panel mechanic-launch');
      intro.append(node('p', 'Run one backtest on the declared IS range using the strategy’s default parameters and your saved costs. Then compare every metric and sampled trade with MultiCharts.'));
      const run = node('button',workflow.status === 'running' ? 'Running default-parameter backtest…' : 'Run validation · default parameters →','button primary');
      run.id = 'mechanic-run'; run.disabled = workflow.status === 'running'; run.onclick = () => runValidation(workflow);
      intro.append(run); host.append(intro);
      if (workflow.run_id) { const actions=node('div',undefined,'mechanic-downloads');link(actions,'View job progress / history',`#jobs/mechanic_validation/${workflow.run_id}`);host.append(actions); }
      if (workflow.error) intro.append(node('p',workflow.error,'mechanic-error'));
      const settings = node('details',undefined,'mechanic-settings'); settings.append(node('summary','Saved source, default parameters and execution settings'));
      settings.append(node('pre',JSON.stringify({dataset:saved.dataset,parameters:saved.default_parameters,costs:saved.execution_settings,split:saved.plan},null,2))); host.append(settings);
      return;
    }
    const outputs = node('div',undefined,'mechanic-downloads');
    link(outputs,'Job progress / history',`#jobs/mechanic_validation/${workflow.run_id}`);
    link(outputs,'Open backtest report',`#backtests/report/${workflow.run_id}`);
    link(outputs,'Trades CSV ↓',`/api/backtests/${workflow.run_id}/exports/trades`);
    link(outputs,'Saved review JSON ↓',endpoint(workflow.id)+'/download'); host.append(outputs);
    host.append(node('p', passed ? `Mechanics and MC parity confirmed by the user on ${workflow.review.confirmed_at_utc}. IS Broad is now available.` : 'Compare against MultiCharts using the same data, dates, timezone, parameters and costs. Confirm MC parity for each outcome, then MC parity and execution correctness for each sampled trade.','workflow-notice'));
    const metrics = table('Outcome metrics',['Metric','AlphaQuest value','Same as MultiCharts?']); metrics.section.id = 'mechanic-metrics';
    for (const metric of workflow.metrics) {
      const row = node('tr'); row.dataset.metric = metric.id;
      row.append(node('td',metric.label),node('td',metric.value == null ? 'N/A' : String(metric.value)),checkbox('metric_checks',metric.id,`MC parity · ${metric.label}`,workflow,passed)); metrics.body.append(row);
    }
    host.append(metrics.section);
    const samples = table('Trade samples',['Why chosen','Trade details · UTC','P&L and costs · CU','Same as MultiCharts?','Execution correct?']); samples.section.id = 'mechanic-trades';
    for (const sample of workflow.trade_samples) {
      const trade = sample.trade, row = node('tr'); row.dataset.tradeNumber = trade.trade_number;
      const details = node('td');
      details.append(node('strong',`Trade ${trade.trade_number} · ${trade.side} · ${trade.contracts} contract(s)`),node('div',`Entry: ${trade.entry_time_utc} @ ${trade.entry_fill_price}`),node('div',`Exit: ${trade.exit_time_utc} @ ${trade.exit_fill_price}`),node('div',`Duration: ${trade.actual_holding_minutes} minutes`),node('div',`Entry reason: ${trade.entry_reason}`),node('div',`Exit reason: ${trade.exit_reason}`));
      const extra = node('details'); extra.append(node('summary','All recorded execution fields'),node('pre',JSON.stringify(trade,null,2))); details.append(extra);
      const costs = node('td'); costs.append(node('strong',`Net: ${trade.net_pnl}`),node('div',`Gross after slippage: ${trade.gross_pnl}`),node('div',`Slippage cost: ${trade.slippage_cost}`),node('div',`Commissions: ${trade.total_commissions}`));
      row.append(node('td',sample.reasons.join(' · ')),details,costs,checkbox('trade_parity',sample.id,`MC parity · trade ${sample.id}`,workflow,passed),checkbox('trade_correctness',sample.id,`Execution correct · trade ${sample.id}`,workflow,passed)); samples.body.append(row);
    }
    if (!workflow.trade_samples.length) samples.section.append(node('p','No closed trades. Mechanics cannot pass without trade execution evidence.'));
    if (workflow.missing_samples.length) samples.section.append(node('p',`No qualifying trade for: ${workflow.missing_samples.join(', ')}. Zero or negative P&L is not labeled a win; zero or positive P&L is not labeled a loss.`,'muted'));
    samples.section.append(node('p','A trade selected for several reasons appears once, with all reasons listed. Ties use the earliest trade number. Values come from this saved backtest.','muted'));
    host.append(samples.section);
    const footer = node('section',undefined,'panel mechanic-confirmation');
    footer.append(node('p','Your confirmation records your review of this exact saved run. AlphaQuest does not automatically verify MultiCharts parity.'));
    const confirm = node('button',passed ? 'Mechanics confirmed' : 'Confirm all mechanics correct and parity with MC →','button primary');
    confirm.id = 'mechanic-confirm'; confirm.disabled = passed || !canConfirm(workflow) || saving;
    confirm.onclick = async () => {
      confirm.disabled = true; const active = token;
      try { const result = await read(endpoint(workflow.id)+'/confirm','POST',{revision:workflow.review.revision}); if (active === token) { current=result; render(result,phase); message('Mechanic validation passed. You can open IS Broad.'); } }
      catch (error) { if (active === token) { message(error.message); recovery(workflow.id); } }
    };
    footer.append(confirm);
    if (passed) link(footer,'Continue to IS Broad →',`#campaigns/workflows/${workflow.id}/is_broad`);
    host.append(footer);
  }
  async function runValidation(workflow) {
    const active = token; get('#mechanic-run').disabled = true; message('Starting the local validation job…');
    try {
      const saved = await read(endpoint(workflow.id)+'/run?background=true','POST');
      if (active === token) {
        current=saved; render(saved,'mechanic_validation');
        message(saved.status === 'running' ? 'Job started. You can leave this page and follow it in Job history.' : 'Backtest saved. Review the outcomes and trade samples below.');
        if (saved.status === 'running') timer=setTimeout(navigate,500);
      }
    } catch (error) {
      if (active === token) { message(error.message+' Reload the saved workflow to check its status before retrying.'); recovery(workflow.id); }
    }
  }
  async function navigate() {
    const active = ++token; clearTimeout(timer); saving=false; window.campaignBroad?.dispose(); window.campaignNarrow?.dispose();
    const match = route();
    if (!match) {
      if (location.hash.startsWith('#campaigns/workflows/')) {
        message('Unknown campaign phase or workflow URL.');
        get('#mechanic-title').textContent='Campaign workflow';
        get('#mechanic-source').textContent='';
        get('#mechanic-phases').replaceChildren();
        get('#mechanic-content').replaceChildren();
      }
      return;
    }
    const [,id,phase] = match; message('Loading saved workflow…'); get('#mechanic-content').replaceChildren();
    try {
      const workflow = await read(endpoint(id));
      await read(endpoint(id)+'/phases/'+phase);
      if (active !== token) return;
      current=workflow; render(workflow,phase); message('');
      if (workflow.status === 'running') timer=setTimeout(navigate,1500);
    } catch (error) {
      if (active !== token) return;
      message(error.message);
      const host=get('#mechanic-content');
      link(host,'Return to mechanic validation',`#campaigns/workflows/${id}/mechanic_validation`); recovery(id);
    }
  }
  window.addEventListener('hashchange',navigate);
  navigate();
})();
