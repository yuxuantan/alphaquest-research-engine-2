"use strict";
(() => {
  // Presentation of saved server verdicts only; no qualification is recalculated.
  const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
  const fmt=v=>v==null?'unavailable':Number(v).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
  function candidate(row){
    const q=row.prop_qualification,size=row.configuration?.micros??row.manifest?.configuration?.micros;
    const result={size,status:q?.status||'NOT_ASSESSED',reasons:[],next:'Complete OOS qualification for this frozen size.',action:'Await qualification'};
    if(!q)return result;
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
    const candidates=rows.map(candidate),passed=candidates.filter(c=>c.status==='GO'),failed=candidates.filter(c=>c.status==='NO_GO'),uncertain=candidates.filter(c=>c.status==='INSUFFICIENT_EVIDENCE');
    const forwardReady=passed.filter(c=>c.action==='Review deployment controls');
    const model={candidates,passed:passed.length,failed:failed.length,uncertain:uncertain.length,current,
      campaignPassed:rows.length>0&&rows.every(r=>r.prop_qualification?.prerequisites?.passed===true),
      forwardEligible:passed.length>0,tone:'hold',title:'Hold live deployment · qualification incomplete',
      next:'Complete the OOS assessment before making a deployment decision.',
      counts:`${passed.length} historical GO · ${uncertain.length} inconclusive · ${failed.length} NO-GO · ${candidates.length-passed.length-uncertain.length-failed.length} not assessed`};
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
        for(const c of model.candidates){if(!c.reasons.length)continue;why.append(node('h4',`${c.size} MNQ · ${c.action}`));const list=node('ul');for(const reason of c.reasons)list.append(node('li',reason));why.append(list);}
        if(precision)why.append(node('p','More account paths may improve numerical precision. More historical refits do not add market history. An extra-path diagnostic does not automatically update this saved OOS verdict.','field-help'));
        if(model.uncertain)why.append(node('p','A confidence interval crossing the limit is inconclusive, not a demonstrated failure. More account paths cannot guarantee that historical uncertainty will disappear.','field-help'));
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
  window.propSimConclusion={candidate,describe,render};
})();
