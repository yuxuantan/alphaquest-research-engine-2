"use strict";
(() => {
  const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
  const fmt=v=>v==null?'Unavailable':Number(v).toLocaleString('en-US',{maximumFractionDigits:2,minimumFractionDigits:2});
  const pct=v=>v==null?'Unavailable':fmt(v*100)+'%';
  const label=row=>window.propSimConclusion.candidate(row).label;
  const link=(host,text,href)=>{const a=node('a',text,'button secondary');a.href=href;host.append(a);};
  function tabs(host,items,prefix,name,onSelect=()=>{}){
    const bar=node('div',undefined,'prop-workspace-tabs');bar.setAttribute('role','tablist');bar.setAttribute('aria-label',name);host.append(bar);
    const buttons=new Map();let active;
    function show(key,focus=false){
      if(!buttons.has(key))return;active=key;
      for(const item of items){const button=buttons.get(item.key),selected=item.key===key;button.setAttribute('aria-selected',String(selected));button.tabIndex=selected?0:-1;item.panel.hidden=!selected;}
      if(focus)buttons.get(key).focus();onSelect(key);
    }
    for(const item of items){
      const b=node('button',item.title);b.type='button';b.id=prefix+'-'+item.key+'-tab';b.setAttribute('role','tab');b.setAttribute('aria-controls',item.panel.id);b.onclick=()=>show(item.key);bar.append(b);buttons.set(item.key,b);
      item.panel.setAttribute('role','tabpanel');item.panel.setAttribute('aria-labelledby',b.id);item.panel.tabIndex=0;
      b.onkeydown=e=>{const i=items.findIndex(v=>v.key===item.key);let next;
        if(e.key==='ArrowRight')next=(i+1)%items.length;else if(e.key==='ArrowLeft')next=(i+items.length-1)%items.length;else if(e.key==='Home')next=0;else if(e.key==='End')next=items.length-1;
        if(next!==undefined){e.preventDefault();show(items[next].key,true);}
      };
    }
    show(items[0].key);return {show,buttons,get active(){return active;}};
  }
  function table(host,headers,rows){
    const scroll=node('div',undefined,'optimization-scroll'),t=node('table',undefined,'library-table prop-result-table'),thead=node('thead'),tr=node('tr'),body=node('tbody');
    for(const title of headers)tr.append(node('th',title));thead.append(tr);
    for(const cells of rows){const row=node('tr');for(const value of cells){const td=node('td');if(value instanceof Node)td.append(value);else td.textContent=String(value??'Unavailable');row.append(td);}body.append(row);}
    t.append(thead,body);scroll.append(t);host.append(scroll);return t;
  }
  function create(host,{tradeBehavior}={}){
    const root=node('section',undefined,'prop-workspace');root.id='prop-sim-workspace';root.append(node('h2','Simulation results'));
    const panes=node('div',undefined,'prop-workspace-panes'),phases={};
    for(const [phase,name,purpose] of [['evaluation','Evaluation','Acquisition cost and time to funding'],['funded','Funded','Cash received from a fresh Funded account']]){
      const panel=node('section',undefined,'prop-workspace-phase');panel.id='prop-sim-'+phase+'-results';panel.dataset.phase=phase;
      const heading=node('header',undefined,'prop-workspace-phase-heading'),identity=node('div');identity.append(node('span',phase==='evaluation'?'01 · EVALUATION':'02 · FUNDED','prop-workspace-phase-kicker'),node('h2',purpose));
      const status=node('p','Loading saved results…','prop-workspace-stage');status.setAttribute('role','status');status.id='prop-sim-'+phase+'-progress';heading.append(identity,status);panel.append(heading);
      const live=node('div');live.id='prop-sim-'+phase+'-live-progress';panel.append(live);
      const jobLinks=node('div',undefined,'prop-workspace-job-link');panel.append(jobLinks);
      const views={};for(const key of ['overview','sizing','evidence','tools']){views[key]=node('section',undefined,'prop-workspace-view');views[key].id=`prop-sim-${phase}-${key}-view`;}
      const navigation=tabs(panel,Object.entries(views).map(([key,panel])=>({key,panel,title:{overview:'Overview',sizing:'IS sizing',evidence:'Evidence',tools:'Tools & downloads'}[key]})),'prop-'+phase,'Views for '+name);
      for(const view of Object.values(views))panel.append(view);
      const conclusion=node('div');conclusion.id='prop-sim-'+phase+'-conclusion';views.overview.append(conclusion);
      const metrics=node('div',undefined,'prop-workspace-outcomes');views.overview.append(metrics);window.propSimConclusion.render(conclusion,{current:true,tone:'hold',title:'Loading saved outcome…',next:'Loading results independently for each phase.'},{compact:true});
      const evidence=node('div'),evidenceNote=node('p',undefined,'field-help');views.evidence.append(node('h3','Review the frozen configurations'),node('p','These results assess the IS choices. OOS does not select replacement sizes.','field-help'),evidenceNote,evidence);
      const downloads=node('section',undefined,'prop-workspace-downloads');downloads.append(node('h3','Download saved evidence'));views.tools.append(downloads);
      const controls=node('section',undefined,'prop-workspace-controls');views.tools.append(controls);
      views.sizing.append(node('h3','In-sample sizing results'),node('p',phase==='evaluation'?'Compare acquisition cost and time. Selection uses IS results only.':'Compare expected receipts over the configured horizon. Selection uses IS results only.','field-help'));
      phases[phase]={root:panel,views,navigation,conclusion,metrics,evidence,evidenceNote,downloads,controls,status,live,jobLinks};panes.append(panel);
    }
    const phaseTabs=tabs(root,Object.entries(phases).map(([key,p])=>({key,panel:p.root,title:key==='evaluation'?'Evaluation':'Funded'})),'prop-phase','Simulation phase');root.append(panes);host.append(root);
    function show(phase,view='overview'){phaseTabs.show(phase);phases[phase]?.navigation.show(view);}
    function update(saved){
      for(const [phase,p] of Object.entries(phases)){
        const job=saved.phases[phase],state=saved.automation?.phases[phase],active=['queued','running'].includes(job?.status);
        p.status.textContent=({is_running:'IS search running',oos_running:'OOS assessment running',complete:'Complete',no_eligible_candidates:'No eligible IS configuration',error:'Needs attention',cancelled:'Stopped'}[state?.stage])||state?.stage?.replaceAll('_',' ')||job?.status||'Waiting';
        p.root.setAttribute('aria-busy',String(active||state?.stage==='oos_running'));
        const b=phaseTabs.buttons.get(phase);b.setAttribute('aria-label',(phase==='evaluation'?'Evaluation':'Funded')+' · '+p.status.textContent);
      }
    }
    function present(phase,study,model,{onForward}={}){
      const p=phases[phase],rows=study?.calculations?.candidates||[];
      p.evidenceNote.textContent=model.current?'':'Historical version: the original findings below do not establish current qualification.';
      window.propSimConclusion.render(p.conclusion,model,{compact:true,onEvidence:()=>show(phase,rows.length?'evidence':'sizing'),onForward});
      const counts=p.conclusion.querySelector('p.field-help');if(counts&&model.counts)counts.textContent=model.counts.split(' · ').filter(v=>!v.startsWith('0 ')).join(' · ');
      p.conclusion.querySelector('.mechanic-downloads button')?.replaceChildren(document.createTextNode(rows.length?'Review evidence':'View IS sizing'));
      p.metrics.replaceChildren();
      if(!rows.length){p.metrics.append(node('p','The saved assessment will appear here when it is available.','field-help'));return;}
      p.metrics.append(node('h3',rows.some(r=>r.prop_qualification?.account_comparison)?'Frozen choices · observed OOS outcomes':'Frozen choices'));
      const evaluation=phase==='evaluation',summaries=rows.map(r=>r.prop_qualification?.account_comparison?.oos?.at(-1));
      const horizons=[...new Set(summaries.map(s=>s?.horizon_calendar_days).filter(Boolean))],horizon=horizons.length===1?horizons[0]:null;
      const state=r=>{const view=window.propSimConclusion.candidate(r);const badge=node('span',model.current?view.action:'Historical · '+view.action,'prop-workspace-verdict');badge.dataset.state=view.status;return badge;};
      if(!summaries.some(Boolean)){table(p.metrics,['Frozen sizing','Next step'],rows.map(r=>[label(r),state(r)]));p.metrics.append(node('p','Account-level measurements are unavailable in this saved assessment. Review its evidence and original report.','field-help'));renderEvidence(p.evidence,rows,study.calculations.qualification_policy?.start_plan,tradeBehavior);return;}
      table(p.metrics,evaluation?['Sizing',horizon?`Funded within ${horizon} days`:'Funded within window','Mean fees spent · USD','Next step']:['Sizing',horizon?`Mean receipts · ${horizon} days`:'Mean receipts · saved horizon','No receipts','Next step'],rows.map((r,i)=>{const s=summaries[i];return evaluation?[label(r),pct(s?.funded_probability?.mean),fmt(s?.fees_spent?.mean),state(r)]:[label(r),fmt(s?.received_cash?.mean),pct(s?.zero_receipts?.mean),state(r)];}));
      p.metrics.append(node('p',evaluation?'Fees include unfunded paths and retries. The funding window is a diagnostic, not a provider deadline.':'Receipts include zero-payout paths. This starts one fresh Funded account, without replacement or acquisition costs.','field-help'));
      renderEvidence(p.evidence,rows,study.calculations.qualification_policy?.start_plan,tradeBehavior);
    }
    function assessmentProgress(phase,attempt){
      const p=phases[phase];if(!attempt||!['launching','queued','running'].includes(attempt.status))return;
      window.renderPropProgress(p.live,attempt.analysis?.progress_details,attempt.status);
      p.status.textContent='OOS assessment running';p.jobLinks.replaceChildren();if(attempt.analysis_id)link(p.jobLinks,'View running job',`#jobs/prop_analysis/${attempt.analysis_id}`);
    }
    return {root,phases,show,update,present,assessmentProgress};
  }
  function renderEvidence(host,rows,startPlan,tradeBehavior){
    const prior=host.querySelector('[data-evidence-candidate]')?.value,priorSupport=host.querySelector('[aria-label="Supporting evidence table"]')?.value;host.replaceChildren();
    const toolbar=node('div',undefined,'prop-evidence-toolbar'),label=node('label','Sizing configuration'),select=node('select');select.dataset.evidenceCandidate='';select.setAttribute('aria-label','Evidence sizing configuration');
    rows.forEach((r,i)=>select.add(new Option(window.propSimConclusion.candidate(r).label,String(i))));if(prior!=null&&Number(prior)<rows.length)select.value=prior;label.append(select);toolbar.append(label);host.append(toolbar);
    const body=node('div');host.append(body);
    function paint(){
      const row=rows[Number(select.value)],q=row.prop_qualification;body.replaceChildren();
      if(!q||q.version!=='prop-complementary-evidence-v2'){body.append(node('p','This report uses an earlier assessment format. Download its original report from Tools & downloads.'));return;}
      const staging=node('div');window.propSimConclusion.renderEvidence(staging,row,{startPlan});
      const findings=staging.querySelector('.prop-evidence-findings');
      if(findings){const list=node('div',undefined,'prop-evidence-checklist');list.setAttribute('aria-label','Evidence checks');
        for(const card of findings.children){const line=node('section',undefined,'prop-evidence-check '+card.className),text=node('div');line.append(card.querySelector('h5'),card.querySelector('.prop-evidence-state'));const paragraphs=[...card.querySelectorAll('p')];for(const paragraph of paragraphs){if(paragraph.classList.contains('field-help')&&card.classList.contains('pass'))continue;text.append(paragraph);}line.append(text);list.append(line);}body.append(list);}
      const sections=[];
      if(tradeBehavior){const handling=node('section');tradeBehavior(handling,[row],'OOS / assessment');const d=handling.querySelector('[data-trade-behavior]');if(d){const section=node('section');section.dataset.tradeBehavior='OOS / assessment';for(const child of [...d.children])if(child.tagName!=='SUMMARY')section.append(child);sections.push(['Trade handling',section]);}}
      const gaps=row.observed_bar_diagnostics||row.native_forecast?.observed_bar_diagnostics;
      if(gaps){const section=node('section');window.nativeReplay.renderCoverage(section,gaps);sections.push(['Source coverage',section]);}

      const comparison=staging.querySelector('.prop-evidence-comparison');if(comparison)sections.push(['IS / OOS comparison',comparison]);
      for(const d of staging.querySelectorAll('.prop-evidence-details')){const title=d.querySelector('summary')?.textContent||'Details',section=node('section');for(const child of [...d.children])if(child.tagName!=='SUMMARY')section.append(child);sections.push([title,section]);}
      if(!sections.length)return;
      const choiceLabel=node('label','Supporting data'),choice=node('select');choice.setAttribute('aria-label','Supporting evidence table');sections.forEach(([title],i)=>choice.add(new Option(title,String(i))));if(priorSupport!=null&&Number(priorSupport)<sections.length)choice.value=priorSupport;choiceLabel.append(choice);toolbar.append(choiceLabel);
      const support=node('section',undefined,'prop-evidence-support');body.append(support);
      const draw=()=>{support.replaceChildren(sections[Number(choice.value)][1]);};choice.onchange=draw;draw();
    }
    select.onchange=()=>{toolbar.querySelectorAll('label:not(:first-child)').forEach(n=>n.remove());paint();};paint();
  }
  function inspect(title,value){
    const dialog=node('dialog',undefined,'prop-sim-detail-dialog'),heading=node('h2',title),close=node('button','Close','button secondary');
    heading.id='prop-detail-title';dialog.setAttribute('aria-labelledby',heading.id);close.type='button';close.onclick=()=>dialog.close();
    dialog.append(heading,close,node('pre',JSON.stringify(value,null,2)));document.body.append(dialog);dialog.onclose=()=>dialog.remove();dialog.showModal();close.focus();
  }
  window.propSimWorkspace={create,inspect};
})();
