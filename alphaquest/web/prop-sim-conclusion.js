"use strict";
(() => {
  // Presentation of saved server verdicts only; no qualification is recalculated.
  const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
  const fmt=v=>v==null?'unavailable':Number(v).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
  function candidate(row){
    const configuration=row.configuration??row.manifest?.configuration??{},q=row.prop_qualification,size=configuration.micros;
    const policy=configuration.sizing?.policy,label=policy?.kind==='percentage_risk'?`${policy.risk_percent}% · ${policy.reference.replaceAll('_',' ')} (cap ${size} MNQ)`:`${size} MNQ`;
    const result={size,label,status:q?.status||'NOT_ASSESSED',reasons:[],next:'Complete OOS qualification for this frozen size.',action:'Await qualification'};
    if(!q)return result;
    if(q.version==='prop-complementary-evidence-v2'){
      result.reasons=(q.findings||[]).filter(f=>f.state!=='PASS').map(f=>`${f.title} · ${f.state}: ${f.summary} ${f.next_step}`);
      result.action=q.status==='GO'?'Paper execution review':q.status==='REVIEW_REQUIRED'?'Investigate sensitivity':q.status==='NO_GO'?'Review account fit':'Resolve evidence gaps';
      if(q.forward_execution?.status==='GO')result.action='Review deployment controls';
      else if(q.forward_execution?.status==='NO_GO')result.action='Resolve execution issues';
      for(const e of q.forward_execution?.checks||[])if(e.passed!==true)result.reasons.push(`Forward execution · ${e.label}: ${e.actual??'unavailable'}; required ${e.required}.`);
      return result;
    }
    for(const e of q.evidence||[])if(e.passed!==true)result.reasons.push(`${e.label}: ${e.actual??'unavailable'}; required ${e.required}.`);
    for(const c of q.checks||[]){
      const boundary=c.direction==='maximum'?`upper bound ≤ ${fmt(c.limit)}`:`lower bound ≥ ${fmt(c.limit)}`;
      if(c.status==='FAIL')result.reasons.push(`${c.label} failed the saved limit: OOS / IS ${fmt(c.point_ratio)}, historical interval [${fmt(c.lower)}, ${fmt(c.upper)}]; required ${boundary}.`);
      else if(c.status!=='PASS')result.reasons.push(`${c.label} check is inconclusive: OOS / IS ${fmt(c.point_ratio)}, historical interval [${fmt(c.lower)}, ${fmt(c.upper)}]; required ${boundary}.`);
    }
    if(q.inner_precision_ok===false)result.reasons.push('Account-simulation precision is insufficient: the saved inner Monte Carlo relative standard error requirement was not met.');
    if(q.prerequisites?.passed===false)result.reasons.push('The saved campaign admission prerequisites were not met.');
    if(q.status==='INSUFFICIENT_EVIDENCE'){
      result.action='Gather evidence';result.next='Hold live deployment of this size. Review the blockers below; this assessment has not established acceptable stability.';
    }else if(q.status==='NO_GO'){
      result.action='Do not deploy';result.next='Do not deploy this size under the saved policy. Investigate the failed checks and account economics; keep this freeze and report as evidence.';
    }else if(q.status==='GO'){
      const forward=q.forward_execution;
      if(forward?.status==='GO'){
        result.action='Review deployment controls';result.next='Historical and supplied paper execution checks passed. Review replacement cash flow, the loss budget and provider/broker controls before considering a limited live pilot.';
      }else if(forward?.status==='NO_GO'){
        result.action='Resolve execution issues';result.next='Hold live deployment. Historical stability passed, but the supplied forward execution review failed. Resolve the recorded discrepancies and review new evidence.';
      }else{
        result.action='Paper execution review';result.next='Continue with paper execution and signal/fill parity review for this frozen size. Historical GO alone does not establish live readiness.';
      }
      for(const e of forward?.checks||[])if(e.passed!==true)result.reasons.push(`Forward review · ${e.label}: ${e.actual??'unavailable'}; required ${e.required}.`);
    }
    return result;
  }
  function describe(rows,{current=true}={}){
    const candidates=rows.map(candidate),passed=candidates.filter(c=>c.status==='GO'),failed=candidates.filter(c=>c.status==='NO_GO'),uncertain=candidates.filter(c=>c.status==='INSUFFICIENT_EVIDENCE'),watch=candidates.filter(c=>c.status==='REVIEW_REQUIRED');
    const forwardReady=passed.filter(c=>c.action==='Review deployment controls');
    const model={candidates,passed:passed.length,failed:failed.length,uncertain:uncertain.length,current,
      campaignPassed:rows.length>0&&rows.every(r=>r.prop_qualification?.prerequisites?.passed===true),
      forwardEligible:passed.length>0,tone:'hold',title:'Hold live deployment · qualification incomplete',
      next:'Complete the OOS assessment before making a deployment decision.',
      counts:`${passed.length} historical GO · ${uncertain.length} inconclusive · ${failed.length} NO-GO · ${candidates.length-passed.length-uncertain.length-failed.length} not assessed`};
    const complementary=rows.some(r=>r.prop_qualification?.version==='prop-complementary-evidence-v2');
    model.complementary=complementary;
    if(complementary){
      model.counts=`${passed.length} ready for paper review · ${watch.length} need investigation · ${uncertain.length} evidence gaps · ${failed.length} account-fit failures`;
    }
    if(!current){
      model.title='Hold live deployment · historical assessment only';
      const outcome=passed.length?'some sizes passed the historical checks':uncertain.length?'qualification was inconclusive':failed.length?'the selected sizes did not qualify':'qualification was incomplete';
      model.next=`Saved outcome: ${outcome}. This result belongs to an earlier numerical or policy version and does not establish current qualification. Preserve it; a current assessment requires a compatible new simulation.`;
      model.forwardEligible=false;
    }else if(passed.length){
      model.tone='review';
      if(forwardReady.length){model.title='Paper checks passed · deployment review next';model.next='Only sizes with both historical GO and forward GO reached this step. Review cash-flow economics and deployment controls; these checks do not authorize live trading.';}
      else if(passed.every(c=>c.action==='Resolve execution issues')){model.title='Hold live deployment · resolve execution issues';model.next='The historical checks passed for some sizes, but their supplied execution reviews failed. Resolve those issues before proceeding.';model.tone='hold';}
      else{model.title='Historical checks passed · paper review next';model.next='Use only historical GO sizes for the existing paper execution review. Complete signal/fill parity checks and review replacement cash flow before considering live deployment.';}
      if(passed.length!==candidates.length)model.next+=' Other frozen sizes remain on hold or rejected; OOS does not select replacements.';
    }else if(uncertain.length){
      model.title='Hold live deployment · qualification inconclusive';
      model.next='Keep this campaign in research. The prop-sizing evidence is not sufficient for deployment under the saved policy; review confidence, precision and account economics before deciding the next study.';
      if(failed.length)model.next+=' Some sizes also have a saved NO-GO verdict.';
    }else if(failed.length===candidates.length&&failed.length){
      model.tone='reject';model.title='Do not deploy these sizes · assessment failed';
      model.next='Investigate the failed checks and replacement-account economics. Any revised sizing research needs a new IS plan; do not choose replacement sizes from OOS.';
    }
    if(current&&complementary){
      if(passed.length&&passed.every(c=>c.action==='Resolve execution issues')){model.title='Hold deployment · resolve execution issues';model.next='The complementary evidence was ready, but supplied execution checks failed. Resolve the recorded issues and review new paper observations.';}
      else if(passed.length){model.title=forwardReady.length?'Execution checks passed · review deployment controls':'Evidence ready · paper execution review next';model.next='The complementary checks found no unresolved blockers for the ready sizes. Validate signals, sizing and fills with supplied paper observations. These checks do not establish future-market confidence or authorize live trading.';}
      else if(watch.length&&!uncertain.length){model.title='Assessment complete · investigate sensitivity';model.next='The estimates are usable, but account-start or stress results need investigation. Review the named scenarios below; more simulated paths do not repair historical instability. Keep the frozen choices.';}
      else if(uncertain.length){model.title='Assessment complete · resolve evidence gaps';model.next='Review the specific coverage, early-guard or numerical-precision blocker below. Additional paths can reduce simulation noise; additional market history is needed for coverage gaps.';}
      else if(failed.length){model.title='Assessment complete · account fit not supported';model.next='The modeled account outcomes did not support progressing these frozen sizes. Review the failed economic or declared-constraint checks; any replacement size must come from a new IS study.';}
    }
    return model;
  }
  function render(host,model,{compact=false,onEvidence,onDiagnostics,onForward}={}){
    host.replaceChildren();host.className='prop-sim-conclusion '+model.tone;host.dataset.conclusionState=model.current?(model.passed?'review':model.uncertain?'inconclusive':model.failed?'failed':'pending'):'historical';
    host.append(node(compact?'h4':'h3',model.title),node('p',model.next));
    if(model.counts)host.append(node('p',model.counts,'field-help'));
    if(!compact&&model.candidates){
      const issues=model.candidates.some(c=>c.reasons.length),precision=model.candidates.some(c=>c.reasons.some(r=>r.startsWith('Account-simulation precision')));
      if(model.campaignPassed)host.append(node('p','Campaign checks passed at assessment time. An inconclusive or failed prop-sizing result does not revoke those campaign results.','prop-sim-campaign-standing'));
      if(issues){
        const why=node('details',undefined,'prop-sim-conclusion-reasons');why.open=!model.passed;why.append(node('summary','Why this is the next step'));
        for(const c of model.candidates){if(!c.reasons.length)continue;why.append(node('h4',`${c.label} · ${c.action}`));const list=node('ul');for(const reason of c.reasons)list.append(node('li',reason));why.append(list);}
        if(precision)why.append(node('p','More account paths may improve numerical precision. More historical refits do not add market history. An extra-path diagnostic does not automatically update this saved OOS verdict.','field-help'));
        if(model.uncertain&&!model.complementary)why.append(node('p','A confidence interval crossing the limit is inconclusive, not a demonstrated failure. More account paths cannot guarantee that historical uncertainty will disappear.','field-help'));
        host.append(why);
      }
      host.append(node('p','Decision scope: this is an account-sizing research conclusion, not a guarantee about future profitability. Keep frozen choices and original verdicts; do not relax limits just to obtain a pass.','field-help'));
    }
    const actions=node('div',undefined,'mechanic-downloads');
    for(const [label,callback] of [[compact?'View reasons and next steps':'Inspect saved evidence',onEvidence],['Review diagnostic options',onDiagnostics],['Open paper execution review',model.current&&model.forwardEligible?onForward:null]]){
      if(!callback)continue;const button=node('button',label,'button secondary');button.type='button';button.onclick=callback;actions.append(button);
    }
    if(!compact){const a=node('a','Review replacement cash flow','workflow-inline-link');a.href='#prop-sim?mode=portfolio';actions.append(a);}
    if(actions.children.length)host.append(actions);
  }
  function startWindow(row,startPlan){
    // Read frozen policy/observations only. Never substitute today's defaults.
    const observations=row.prop_qualification?.start_sensitivity?.observations||[];
    const durations=observations.map(p=>{
      if(!/^\d{4}-\d{2}-\d{2}$/.test(p.start_date||'')||!/^\d{4}-\d{2}-\d{2}$/.test(p.cutoff_exclusive||''))return null;
      const days=(Date.parse(p.cutoff_exclusive+'T00:00:00Z')-Date.parse(p.start_date+'T00:00:00Z'))/86400000;
      return Number.isInteger(days)&&days>0?days:null;
    });
    const declared=startPlan?.horizon_calendar_days;
    const horizon=Number.isInteger(declared)&&declared>0?declared:
      durations.length&&durations.every(v=>v===durations[0])?durations[0]:null;
    return horizon&&durations.every(v=>v===horizon)?horizon:null;
  }
  function renderEvidence(host,row,{startPlan}={}){
    const q=row.prop_qualification,phase=q.account_comparison?.oos?.[0]?.funded_probability?'evaluation':'funded',evaluation=phase==='evaluation';
    const title=node('h4',candidate(row).label+' · '+candidate(row).action);if(host.tagName!=='DETAILS')host.append(title);host.append(node('p',q.interpretation,'field-help'));
    const grid=node('div',undefined,'prop-evidence-findings');grid.setAttribute('aria-label','Evidence findings');
    const startDays=startWindow(row,startPlan),windowText=startDays?`${startDays} calendar days per start`:'Window unavailable in saved evidence';
    for(const f of q.findings||[]){
      const card=node('section',undefined,'prop-evidence-finding '+f.state.toLowerCase());
      card.append(node('h5',f.title),node('span',f.state==='PASS'?'Checked':f.state==='WATCH'?'Review':f.state==='FAIL'?'Not supported':'Evidence needed','prop-evidence-state'),node('p',f.summary));
      if(f.key==='starts'){const window=node('p',(startDays?'Window: ':'')+windowText+'.');window.dataset.accountStartWindow='';card.append(window);}
      card.append(node('p',f.next_step,'field-help'));grid.append(card);
    }host.append(grid);
    const percent=v=>v==null?'Unavailable':fmt(v*100)+'%';
    const measure=(v,probability=false)=>!v?'Unavailable':`${probability?percent(v.mean):fmt(v.mean)}${v.interval?' ['+v.interval.map(x=>probability?percent(x):fmt(x)).join(', ')+']':''}`;
    function table(parent,headers,values){const scroll=node('div',undefined,'optimization-scroll'),t=node('table',undefined,'library-table prop-result-table'),thead=node('thead'),tr=node('tr'),body=node('tbody');for(const h of headers)tr.append(node('th',h));thead.append(tr);for(const cells of values){const r=node('tr');for(const value of cells)r.append(node('td',String(value??'Unavailable')));body.append(r);}t.append(thead,body);scroll.append(t);parent.append(scroll);}
    if(q.account_comparison){
      const comparison=node('section',undefined,'prop-evidence-comparison');comparison.append(node('h5','IS / OOS account comparison'),node('p','5,000 paths per history and deadline. Brackets show pointwise 95% simulation intervals, conditional on the saved history/model. They are not historical uncertainty or future-market confidence.','field-help'));
      const cells=[];
      for(const role of ['is','oos'])for(const v of q.account_comparison[role])cells.push(evaluation?[role.toUpperCase(),v.horizon_calendar_days,measure(v.funded_probability,true),measure(v.fees_spent),measure(v.capped_wait),v.median_days==null?'Not reached':fmt(v.median_days),v.p90_days==null?'Not reached':fmt(v.p90_days),v.early_guard_paths]:[role.toUpperCase(),v.horizon_calendar_days,measure(v.received_cash),fmt(v.median_cash),fmt(v.p10_cash),measure(v.zero_receipts,true),measure(v.breach,true),measure(v.pending_cash)]);
      table(comparison,evaluation?['History','Deadline · days','Funded by deadline','Fees spent · USD','Capped waiting · days','Median funding · days','P90 funding · days','Early guards']:['History','Horizon · days','Mean received · USD','Median received · USD','P10 received · USD','No receipts','Breach','Pending · USD'],cells);
      comparison.append(node('p',evaluation?'Fees and capped waiting include every account, including those still unfunded. Capped waiting ends at funding or the deadline; it is not eventual funding time. “Not reached” means the funding quantile was not identifiable.':'Receipts include zero-payout accounts. Pending amounts are separate and excluded from received cash. Each path starts one fresh Funded account; no replacement is assumed.','field-help'));host.append(comparison);
    }
    if(q.stress_scenarios?.length){const d=node('details',undefined,'prop-evidence-details');d.append(node('summary','Stress scenarios · '+q.stress_scenarios.length+' predefined checks'));
      table(d,['Scenario','History',evaluation?'Funding by 365 days':'Mean receipts · USD',...(evaluation?['Fees spent · USD','Capped waiting · days']:['No receipts','Breach']),'Baseline outcome retained','Observation'],q.stress_scenarios.map(s=>[s.name,s.role.toUpperCase(),evaluation?percent(s.summary.funded_probability.mean):fmt(s.summary.received_cash.mean),...(evaluation?[fmt(s.summary.fees_spent.mean),fmt(s.summary.capped_wait.mean)]:[percent(s.summary.zero_receipts.mean),percent(s.summary.breach.mean)]),percent(s.retention_ratio),s.summary.observation_complete?'Complete':'Early guard / incomplete']));
      d.append(node('p','Blocks 1 and 10 test clustering. The cost scenario adds $0.50 per MNQ per side; it does not simulate shifted fill prices. Earlier/later halves use IS only. Below 70% retention triggers review, not a statistical failure. No new size is selected.','field-help'));host.append(d);}
    if(q.start_sensitivity){const d=node('details',undefined,'prop-evidence-details'),v=q.start_sensitivity;d.append(node('summary','Chronological account starts · '+v.summary.starts+' observed windows'+(startDays?' · '+startDays+' calendar days each':'')),node('p','Coverage-only starts preserve actual session order. '+(evaluation?'The window is a fixed diagnostic, not a provider deadline; not funded means funding was not reached before its cutoff. ':'')+'Overlapping windows are dependent scenarios; their outcome fraction is not an independent probability estimate.','field-help'));
      table(d,evaluation?['Start','Cutoff (exclusive)','Outcome','Paid fees · USD','Funding · days']:['Start','Cutoff (exclusive)','Outcome','Received · USD','Pending · USD'],(v.observations||[]).map(p=>evaluation?[p.start_date,p.cutoff_exclusive,p.acquisition_completed?'Funded':'Not funded within window',fmt(p.paid_fees),p.calendar_days_to_funded==null?'Not reached':fmt(p.calendar_days_to_funded)]:[p.start_date,p.cutoff_exclusive,p.outcome,fmt(p.cash_received),fmt(p.pending_cash)]));host.append(d);}
    const details=node('details',undefined,'prop-evidence-details');details.append(node('summary','Policy, evidence and interpretation'),node('p','No nested historical refits were run. The former historical non-inferiority interval gate is not applied.','field-help'));
    for(const e of q.evidence||[])details.append(node('p',`${e.passed?'Met':'Insufficient'} · ${e.label}: ${e.actual} / ${e.required}`));
    for(const f of q.findings||[])if(f.outcome_ratio!==undefined)details.append(node('p',`${f.title} · OOS / IS outcome ${fmt(f.outcome_ratio)}${f.capped_wait_ratio!=null?' · capped wait '+fmt(f.capped_wait_ratio):''}. ${f.interpretation||''}`));
    for(const limitation of q.limitations||[])details.append(node('p',limitation,'field-help'));
    details.append(node('p','Forward execution · '+(q.forward_execution?.status||'PENDING')));host.append(details);
  }
  window.propSimConclusion={candidate,describe,render,renderEvidence};
})();
