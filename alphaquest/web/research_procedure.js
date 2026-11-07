/* Whole-procedure freeze and terminal applications in the existing research report. */
(() => {
  const node=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;},uuid=()=>crypto.randomUUID().replaceAll('-','');
  const display=value=>value===undefined||value===null?'Unavailable':typeof value==='boolean'?(value?'Yes':'No'):Array.isArray(value)?value.join(', '):String(value);
  const link=(title,url)=>{const a=node('a',title);a.href=url;return a;};
  function button(parent,title,id){const b=node('button',title);b.type='button';b.id=id;b.className='button secondary';parent.append(b);return b;}
  function select(parent,title,id){const label=node('label',title),input=node('select');input.id=id;label.append(input);parent.append(label);return input;}
  function option(input,value,title){const o=node('option',title);o.value=value;input.append(o);}
  function table(parent,headers,rows,id){const wrap=node('div');wrap.className='robust-table-scroll';const t=node('table');if(id)t.id=id;const head=node('thead'),tr=node('tr');for(const label of headers)tr.append(node('th',label));head.append(tr);t.append(head);const body=node('tbody');for(const row of rows){const tr=node('tr');row.forEach((value,index)=>{const td=node('td');td.dataset.label=headers[index];value instanceof Node?td.append(value):td.textContent=display(value);tr.append(td);});body.append(tr);}t.append(body);wrap.append(t);parent.append(wrap);}
  async function api(path,body){const response=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),result=await response.json();if(!response.ok)throw Error(typeof result.detail==='string'?result.detail:JSON.stringify(result.detail));return result;}
  function list(parent,values){if(!values?.length)return;const ul=node('ul');for(const text of values)ul.append(node('li',text));parent.append(ul);}
  function windowEvidence(parent,plan){
    table(parent,['Information window','First session','Last session','Observed / declared sessions'],[['Terminal training',plan.train.first_session,plan.train.last_session,plan.train.sessions.length],['Final or next modeled target',plan.test.first_session,plan.test.last_session,plan.test.sessions.length]],'procedure-terminal-window');
    table(parent,['Inner fold','Training','Validation'],plan.inner.map((fold,index)=>[index+1,`${fold.train.first_session} → ${fold.train.last_session}`,`${fold.validation.first_session} → ${fold.validation.last_session}`]));
    parent.append(node('p',`Information cutoff: ${plan.information_cutoff_session}. Target cutoff: ${plan.target_cutoff_date_exclusive} exclusive. Purged sessions: ${display(plan.excluded?.purge_sessions)}. Embargoed sessions: ${display(plan.excluded?.embargo_sessions)}.`));
  }
  function recommendation(parent,rows){
    for(const row of rows||[]){const section=node('section');section.className='procedure-recommendation';section.dataset.phase=row.phase;section.append(node('h3',`${row.phase==='evaluation'?'Evaluation':'Funded'} · ${row.status.replaceAll('_',' ')}`));
      section.append(node('p','Production qualified: no. Historical research, model/provider verification and live operational readiness are separate decisions.'));
      for(const [title,key]of [['Research evidence blockers','evidence_blockers'],['Model and provider limitations','model_blockers'],['Operational limitations','operational_blockers']]){if(row[key]?.length){section.append(node('h4',title));list(section,row[key]);}}
      const packages=row.selected_packages||[];if(packages.length)table(section,['Current strategy / parameters','Account','Sizing policy','Frozen policy SHA-256'],packages.map(p=>[`${p.strategy.id} · ${Object.entries(p.strategy.parameters).map(([k,v])=>`${k}=${v}`).join(', ')}`,p.configuration.profile.profile_id,window.robustResearch.policyLabel(p.configuration),p.package_sha256]));
      if(packages.length>1)section.append(node('p','The complete selected family remains alternatives. No implicit allocation or deployment winner is created.'));
      parent.append(section);
    }
  }
  async function configure(parent,initial){
    const section=node('section');section.id='robust-procedure';section.className='panel prop-panel';parent.append(section);section.append(node('h3','Final verification and current development selection'));
    const body=node('div'),status=node('p');status.id='robust-procedure-status';status.setAttribute('role','status');section.append(status,body);
    const base=`/api/research-campaigns/robust/${initial.campaign_id}`;
    let current=initial,watchVersion=0;
    async function refresh(){current=await api(base);if(section.isConnected)await draw();}
    async function watch(application){const version=++watchVersion;const progress=node('div');progress.id='procedure-application-progress';body.append(progress);const stop=button(progress,'Request stop at next checkpoint','procedure-application-cancel');stop.disabled=application.cancel_requested;
      stop.onclick=async()=>{stop.disabled=true;try{await api(`${base}/applications/${application.application_id}/cancel`,{});}catch(error){status.textContent=error.message;stop.disabled=false;}};
      while(section.isConnected&&version===watchVersion){const saved=await api(`${base}/applications/${application.application_id}`);status.textContent=`${saved.purpose.replaceAll('_',' ')} · ${saved.status} · ${saved.progress||saved.error||''}`;if(saved.cancel_requested)stop.disabled=true;
        if(!['queued','running'].includes(saved.status)){await refresh();return;}await new Promise(resolve=>setTimeout(resolve,750));}
    }
    function applications(){
      const history=node('section');history.id='procedure-applications';body.append(history);history.append(node('h4','Saved procedure applications'));
      if(!current.applications?.length){history.append(node('p','No terminal application has run.'));return;}
      for(const application of current.applications){const row=node('details');row.append(node('summary',`${application.purpose.replaceAll('_',' ')} · ${application.status}`));history.append(row);row.append(node('p',`${application.progress||application.error||''} · ${application.application_id}`));
        if(application.status==='complete'){row.append(link('Open saved terminal report',`#backtests/prop/job/${application.analysis_id}`),node('br'),link('Download terminal report ZIP',`${base}/applications/${application.application_id}/exports/analysis.zip`));recommendation(row,application.result?.recommendation);}
        else if(['queued','running'].includes(application.status))button(row,'View running application','procedure-watch-'+application.application_id).onclick=()=>watch(application).catch(error=>{status.textContent=error.message;});
        else if(['error','cancelled','interrupted'].includes(application.status))button(row,'Retry saved application and checkpoints','procedure-retry-'+application.application_id).onclick=async()=>{try{const {purpose,...declaration}=application.declaration;const next=await api(`${base}/${purpose==='final_verification'?'final-verification':'development-selection'}/run`,declaration);await watch(next);}catch(error){status.textContent=error.message;}};
      }
    }
    async function draw(){
      body.replaceChildren();status.textContent='';
      body.append(node('p','Freeze the complete qualification and independent policy-selection procedure. Final observations cannot choose a replacement. Current policy selection reruns the frozen procedure on its pinned eligible development history; it does not copy the last outer-fold winner.'));
      if(current.procedure){
        const saved=current.procedure;body.append(node('h4','Complete procedure frozen'));
        table(body,['Saved identity','Value'],[['Procedure SHA-256',saved.procedure_sha256],['Algorithm SHA-256',saved.algorithm_sha256],['Development dataset',saved.development.dataset.name],['Final reservation',saved.reservation_id||'None'],['Current selection scope',saved.current_selection_scope]]);
        windowEvidence(body,saved.terminal_plan);
        const currentRun=button(body,'Run frozen selection on current development','procedure-current-run');
        currentRun.onclick=async()=>{currentRun.disabled=true;try{await watch(await api(`${base}/development-selection/run`,{request_id:uuid(),procedure_sha256:saved.procedure_sha256}));}catch(error){status.textContent=error.message;currentRun.disabled=false;}};
        if(saved.reservation_id){
          const finalCheck=button(body,'Check frozen final holdout access','procedure-final-check'),finalRun=button(body,'Run frozen final verification','procedure-final-run');finalRun.disabled=true;
          const evidence=node('div');evidence.id='procedure-final-checks';body.append(evidence);let checked=null;
          finalCheck.onclick=async()=>{finalCheck.disabled=true;finalRun.disabled=true;try{const request={procedure_sha256:saved.procedure_sha256,reservation_id:saved.reservation_id,source_snapshot_id:saved.development.dataset.id},preview=await api(`${base}/final-verification/preview`,request);evidence.replaceChildren();window.researchReservations.accessEvidence(evidence,preview.access);windowEvidence(evidence,preview.terminal_plan);checked=preview.available?{...request,request_id:uuid(),expected_preview_sha256:preview.preview_sha256}:null;finalRun.disabled=!checked;status.textContent=preview.available?'Final access check passed within the recorded local scope. Review the frozen information boundary before execution.':'Final verification is unavailable: '+preview.access.status;}catch(error){status.textContent=error.message;}finally{finalCheck.disabled=false;}};
          finalRun.onclick=async()=>{if(!checked)return;finalRun.disabled=true;try{await watch(await api(`${base}/final-verification/run`,checked));}catch(error){status.textContent=error.message;}};
        }else body.append(node('p','No final reservation was bound to this procedure. Current development may be evaluated, but no untouched final assessment is available for this frozen package.'));
        applications();return;
      }
      const form=node('form');form.id='procedure-freeze-form';form.onsubmit=event=>event.preventDefault();body.append(form);const grid=node('div');grid.className='prop-fields';form.append(grid);
      const snapshot=select(grid,'Dataset snapshot · same frozen development history','procedure-source-snapshot'),reservation=select(grid,'Optional protected final-session reservation','procedure-reservation');
      const datasets=await api('/api/datasets');if(!section.isConnected)return;
      for(const dataset of datasets)option(snapshot,dataset.id,`${dataset.name} · ${dataset.start.slice(0,10)} → ${dataset.end.slice(0,10)} · ${dataset.id.slice(0,8)}`);snapshot.value=current.plan.dataset.id;
      form.append(node('p','A replacement snapshot must preserve all frozen development sessions exactly. Appended final history is checked by source lineage and per-session content, not by filename. Reserve final sessions from the dataset details before exposing their prices.'));
      const preview=button(form,'Preview complete procedure and final feasibility','procedure-preview'),freeze=button(form,'Freeze reviewed complete procedure','procedure-freeze');freeze.disabled=true;const evidence=node('div');evidence.id='procedure-preview-evidence';form.append(evidence);let checked=null,revision=0;
      function invalidate(){revision++;checked=null;freeze.disabled=true;evidence.replaceChildren();}
      async function reservations(){invalidate();reservation.replaceChildren();option(reservation,'','No final holdout reservation');const result=await api(`/api/datasets/${snapshot.value}/research-reservations`);if(!section.isConnected)return;for(const item of result.items)if(['RESERVED','BOUND'].includes(item.status))option(reservation,item.id,`${item.status} · ${item.sessions[0]} → ${item.sessions.at(-1)} · ${item.id.slice(0,8)}`);}
      snapshot.onchange=()=>reservations().catch(error=>{status.textContent=error.message;});reservation.onchange=invalidate;await reservations();
      preview.onclick=async()=>{if(!form.reportValidity())return;const version=revision;preview.disabled=true;freeze.disabled=true;try{const request={reservation_id:reservation.value||null,source_snapshot_id:snapshot.value},result=await api(`${base}/procedure/preview`,request);if(version!==revision||!section.isConnected)return;evidence.replaceChildren();windowEvidence(evidence,result.terminal_plan);window.researchReservations.accessEvidence(evidence,result.access);table(evidence,['Reviewed procedure fact','Value'],[['Complete declared strategy configurations',result.complete_configuration_count],['Final verification available',result.final_verification_available],['Current development selection available',result.current_development_available],['Maximum terminal phase candidates',result.economic_plan.maximum_phase_candidates],['Preview SHA-256',result.preview_sha256]]);evidence.append(node('p',result.interpretation));checked={...request,procedure_id:uuid(),expected_preview_sha256:result.preview_sha256};freeze.disabled=false;status.textContent='Review the exact terminal windows and evidence before freezing.';}catch(error){status.textContent=error.message;}finally{preview.disabled=false;}};
      freeze.onclick=async()=>{if(!checked)return;freeze.disabled=true;try{await api(`${base}/procedure/freeze`,checked);await refresh();}catch(error){status.textContent=error.message;freeze.disabled=false;}};
      applications();
    }
    try{await refresh();}catch(error){status.textContent='Final procedure controls unavailable: '+error.message;}
  }
  async function renderAnalysis(report){
    const result=report.calculations;document.querySelector('#prop-config').hidden=true;document.querySelector('#prop-report').hidden=false;document.querySelector('#prop-delete').hidden=true;
    document.querySelector('#prop-heading-title').textContent=result.purpose==='final_verification'?'Frozen procedure · final verification':'Frozen procedure · current development';
    document.querySelector('#prop-heading-note').textContent='Complete terminal qualification and independent selection · no holdout-driven reselection';
    const target=document.querySelector('#prop-report-content');target.replaceChildren();const panel=node('section');panel.className='panel prop-panel';panel.id='procedure-application-result';target.append(panel);
    document.querySelector('#prop-downloads').replaceChildren(link('Report JSON',`/api/prop-analyses/${report.id}/downloads/report.json`),link('Analysis ZIP',`/api/prop-analyses/${report.id}/downloads/analysis.zip`));
    panel.append(node('h2',result.purpose==='final_verification'?'Final observations under the frozen procedure':'Current selection on eligible development'),node('p',result.interpretation),node('p',`Procedure SHA-256: ${result.procedure_sha256}. Production qualified: no.`));windowEvidence(panel,result.terminal_plan);
    try{const procedure=await api(`/api/prop-analyses/${report.id}/files/procedure.json`);if(!panel.isConnected)return;
      document.querySelector('#prop-back').href=`#backtests/prop/new/${procedure.original_declaration.source_backtest_id}`;document.querySelector('#prop-back').textContent='← Back to research configuration';
      const configurations=new Map(procedure.algorithm.configurations.map(row=>[row.id,row]));
      table(panel,['Terminal configuration','Qualification','Reasons'],result.qualification.candidates.map(row=>{const config=configurations.get(row.candidate_id);return [config?`${config.strategy_id} · ${Object.entries(config.parameters).map(([k,v])=>`${k}=${v}`).join(', ')}`:row.candidate_id,row.status,row.reasons.join('; ')];}),'procedure-terminal-qualification');
    }catch(error){panel.append(node('p','Captured procedure identity unavailable: '+error.message));}
    window.robustResearch.showEconomicSelection(panel,{index:'terminal',economic_selection:result.economic_selection});
    panel.append(node('h3','Final verification evidence'),node('p',`${result.final_verification.status}. Selection repeated on final outcomes: ${display(result.final_verification.selection_repeated_on_final)}.`));
    if(result.final_verification.replay)window.robustResearch.showChronologicalFamily(panel,{index:'final',economic_selection:result.economic_selection,chronological_replay:result.final_verification.replay},{title:'Frozen-procedure final observations',periodLabel:'final'});
    window.robustResearch.showBaselines(panel,{baseline_results:result.baseline_results});
    if(result.final_verification.access)window.researchReservations.accessEvidence(panel,result.final_verification.access.access_at_reservation||result.final_verification.access);
    recommendation(panel,result.recommendation);
    if(result.purpose==='current_development'&&window.forwardMonitoring){await window.forwardMonitoring.configureLauncher(panel,report);if(panel.isConnected)await window.forwardMonitoring.renderCatalogue(panel,{applicationId:result.application_id,allowSynthetic:false});}
    const files=node('details');files.append(node('summary','Download immutable procedure evidence'));panel.append(files);for(const name of Object.keys(report.files||{}).sort())files.append(link(name,`/api/prop-analyses/${report.id}/files/${name}`),node('br'));
  }
  window.researchProcedure={configure,renderAnalysis};
})();
