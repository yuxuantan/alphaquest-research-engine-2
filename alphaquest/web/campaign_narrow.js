"use strict";
(() => {
  const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
  const label=value=>value.replaceAll('_',' ').replace(/^./,c=>c.toUpperCase());
  const number=new Intl.NumberFormat('en-US',{minimumFractionDigits:2,maximumFractionDigits:2,useGrouping:false});
  const metric=(key,value)=>value==null||value===''?'N/A':Number.isFinite(Number(value))?number.format(key==='max_drawdown_duration_seconds'?Number(value)/86400:value):String(value);
  const title=key=>key==='max_drawdown_duration_seconds'?'Max drawdown duration · calendar days':label(key);
  const read=async(url,method='GET',body)=>{const response=await fetch(url,{method,cache:'no-store',...(body===undefined?{}:{headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});const data=await response.json();if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'The saved Narrow request was rejected.');return data;};
  const action=(parent,text,href)=>{const a=node('a',text,'workflow-inline-link');a.href=href;parent.append(a);return a;};
  let generation=0,timer,columns;
  function dispose(){++generation;clearTimeout(timer);columns?.destroy();columns=null;}
  async function render(parent,workflow,{isCurrent,broadTrial}){
    dispose();const version=generation,alive=()=>version===generation&&isCurrent();
    const base=`/api/campaign-workflows/${workflow.id}/narrow`;
    const branches=workflow.narrow||[];
    if(!branches.length){parent.replaceChildren(node('p','Confirm IS Broad configurations before opening IS Narrow.'));return;}
    const trial=Number(broadTrial)||branches[0].broad_trial;
    const url=(path='',params={})=>base+path+'?'+new URLSearchParams({broad_trial:trial,...params});
    parent.replaceChildren(node('p','Loading IS Narrow…'));
    try{
      const detail=await read(url());if(!alive())return;
      let {state,job}=detail,preview=null,busy=false,sort='trial',direction='asc',offset=0,fetching=0,saving=false;
      parent.replaceChildren();
      const chooser=node('section',undefined,'panel broad-panel');chooser.id='narrow-chooser';
      chooser.append(node('h2','One Narrow search per confirmed Broad configuration'),node('p','Choose a Broad configuration. Broad values are locked by default. Where a finer numeric step exists, explicitly choose Refine in Narrow to search around the confirmed value. Run a separate Narrow grid for each choice.'));
      const chooseLabel=node('label','Broad configuration'),choose=node('select');choose.id='narrow-broad-trial';
      for(const branch of detail.branches)choose.add(new Option(`Broad trial ${branch.broad_trial} · ${branch.status.replaceAll('_',' ')}`,String(branch.broad_trial)));
      choose.value=String(trial);choose.onchange=()=>{location.hash=`#campaigns/workflows/${workflow.id}/is_narrow?broad_trial=${choose.value}`;};chooseLabel.append(choose);chooser.append(chooseLabel);
      const frozenBroad=node('pre',JSON.stringify(state.broad_selection.parameters,null,2));chooser.append(frozenBroad);parent.append(chooser);
      const config=node('section',undefined,'panel broad-panel');config.id='narrow-config';
      config.append(node('h2','IS Narrow parameter search'),node('p','Choose ranges for parameters fixed in IS Broad, or opt into a finer numeric range around a selected Broad value. Include that value in the range. The validated dataset, IS dates and costs stay frozen.'));
      const form=node('form'),fieldset=node('fieldset');form.append(fieldset);
      const region=node('div',undefined,'optimization-scroll'),grid=node('table',undefined,'library-table optimization-grid');grid.innerHTML='<thead><tr><th>Parameter</th><th>Narrow treatment</th><th>Start</th><th>End</th><th>Step</th><th>Count</th></tr></thead><tbody></tbody>';region.append(grid);fieldset.append(region);config.append(form);parent.append(config);
      const ranges=new Map(),parameters=detail.strategy.parameters,fixed=new Set(detail.fixed_parameters),refinable=detail.refinable_parameters||{};
      let draft;try{draft=JSON.parse(sessionStorage.getItem('narrow-grid:'+workflow.id+':'+trial));}catch{}
      const initial=job?.request.parameter_ranges||draft?.parameter_ranges||draft;
      const refined=new Set((job?job.research?.refined_broad_parameters||[]:draft?.refine_broad_parameters||[]).filter(name=>Object.hasOwn(refinable,name)));
      const invalidate=message=>{preview=null;run.disabled=true;count.textContent=message;try{sessionStorage.setItem('narrow-grid:'+workflow.id+':'+trial,JSON.stringify({parameter_ranges:values(),refine_broad_parameters:[...refined]}));}catch{}};
      for(const parameter of parameters){
        const row=node('tr');row.dataset.parameter=parameter.name;
        const isBroad=fixed.has(parameter.name),canRefine=Object.hasOwn(refinable,parameter.name);
        const name=node('th',label(parameter.name));name.scope='row';name.append(node('small',isBroad?`Selected Broad value: ${state.broad_selection.parameters[parameter.name]}`:parameter.description||'','field-help'));row.append(name);
        const treatment=node('td');
        if(canRefine){const choice=node('label'),toggle=node('input');toggle.type='checkbox';toggle.setAttribute('aria-label',`Refine ${label(parameter.name)} in Narrow`);toggle.checked=refined.has(parameter.name);choice.append(toggle,document.createTextNode(' Refine in Narrow'));treatment.append(choice,node('small',`Broad minimum step ${refinable[parameter.name].broad_min_step}; use a finer step and include the selected value.`,'field-help'));toggle.onchange=()=>{if(toggle.checked)refined.add(parameter.name);else refined.delete(parameter.name);for(const part of ['start','end','step']){const input=ranges.get(parameter.name)[part];input.disabled=!toggle.checked;input.value=part==='step'?'0':String(state.broad_selection.parameters[parameter.name]);}invalidate('Refinement changed. Calculate iterations again.');};}
        else treatment.textContent=isBroad?'Locked from IS Broad':'Choose range';
        row.append(treatment);
        const inputs={};
        for(const part of ['start','end','step']){
          const cell=node('td'),input=node(parameter.type==='bool'&&part!=='step'?'select':'input');
          if(input.tagName==='SELECT'){input.add(new Option('False','false'));input.add(new Option('True','true'));}
          else{input.type='text';input.inputMode=parameter.type==='Decimal'?'decimal':'numeric';input.maxLength=128;}
          input.required=true;input.setAttribute('aria-label',`${label(parameter.name)} ${part}`);
          const baseline=isBroad?state.broad_selection.parameters[parameter.name]:parameter.default;
          input.value=String(isBroad&&!refined.has(parameter.name)?part==='step'?0:baseline:initial?.[parameter.name]?.[part]??(part==='step'?0:baseline));
          input.disabled=isBroad&&!refined.has(parameter.name);inputs[part]=input;cell.append(input);row.append(cell);
          input.oninput=()=>{if(part!=='step'){if(inputs.start.value===inputs.end.value)inputs.step.value='0';else if(inputs.step.value==='0')inputs.step.value='1';}invalidate('Grid changed. Calculate iterations again.');};
        }
        inputs.count=node('td','—');row.append(inputs.count);grid.tBodies[0].append(row);ranges.set(parameter.name,inputs);
      }
      const workerLabel=node('label','Parallel backtests'),workers=node('select');workers.id='narrow-workers';for(let i=1;i<=detail.max_workers;i++)workers.add(new Option(i===detail.default_workers?`${i} · default`:String(i),String(i)));workers.value=String(job?.request.workers??detail.default_workers);workers.onchange=()=>{preview=null;run.disabled=true;count.textContent='Worker setting changed. Calculate iterations again.';};workerLabel.append(workers);fieldset.append(workerLabel);
      const count=node('p','Calculate the number of Narrow combinations.','optimization-count');count.id='narrow-count';fieldset.append(count);
      const calculate=node('button','Calculate iterations','button secondary');calculate.type='button';calculate.id='narrow-preview';
      const run=node('button','Run IS Narrow →','button primary');run.type='submit';run.id='narrow-run';run.disabled=true;
      const controls=node('div',undefined,'mechanic-downloads');controls.append(calculate,run);fieldset.append(controls);
      const notice=node('p');notice.id='narrow-status';notice.setAttribute('role','status');config.append(notice);
      const integer=value=>{if(!/^-?\d+$/.test(value)||!Number.isSafeInteger(Number(value)))throw Error('Enter safe whole numbers.');return Number(value);};
      function values(){return Object.fromEntries(parameters.map(p=>{const r=ranges.get(p.name);return [p.name,{start:p.type==='bool'?r.start.value==='true':p.type==='int'?integer(r.start.value):r.start.value.trim(),end:p.type==='bool'?r.end.value==='true':p.type==='int'?integer(r.end.value):r.end.value.trim(),step:p.type==='Decimal'?r.step.value.trim():integer(r.step.value)}];}));}
      const requestGrid=()=>({broad_trial:trial,parameter_ranges:values(),refine_broad_parameters:[...refined],workers:Number(workers.value)});
      calculate.onclick=async()=>{if(!form.reportValidity()||busy)return;busy=true;calculate.disabled=true;try{preview=await read(base+'/preview','POST',requestGrid());if(!alive())return;for(const [name,r] of ranges)r.count.textContent=preview.step_counts[name];count.textContent=`${preview.total_trials.toLocaleString()} iterations · IS only`;run.disabled=false;notice.textContent='Grid checked. Native reports include the extra-slippage rerun and daily equity evidence.';}catch(error){if(alive()){preview=null;run.disabled=true;notice.textContent=error.message;}}finally{busy=false;if(alive())calculate.disabled=false;}};
      form.onsubmit=async event=>{event.preventDefault();if(busy||!preview||!form.reportValidity())return;busy=true;fieldset.disabled=true;try{job=await read(base+'/run','POST',{...requestGrid(),revision:preview.revision,preview_token:preview.preview_token});if(!alive())return;preview=null;run.disabled=true;notice.textContent='IS Narrow job started. It continues in Job history if you leave this page.';await refresh();}catch(error){if(alive())notice.textContent=error.message;}finally{busy=false;if(alive())fieldset.disabled=!!job&&['queued','running','complete'].includes(job.status);}};
      const outputs=node('section',undefined,'panel broad-panel');outputs.id='narrow-output';outputs.append(node('h2',`IS Narrow results · Broad trial ${trial}`),node('p','A configuration passes only after both Broad and Narrow checks pass. All selected Broad branches must finish before final screening. Select at most two qualifying rows for this Broad configuration.'),node('p','Statistical check: at least 100 observed source dates; a one-sided 95% lower bound on daily net P&L using a five-observation Bartlett HAC variance and Bonferroni correction across all attempted Broad and Narrow trials. Open each row’s eligibility details for measured values.','field-help'));
      parent.append(outputs);
      const progress=node('p');progress.id='narrow-progress';progress.setAttribute('role','status');outputs.append(progress);
      const links=node('div',undefined,'mechanic-downloads');outputs.append(links);
      const jobControls=node('div',undefined,'mechanic-downloads'),resume=node('button','Resume remaining trials','button secondary'),cancel=node('button','Cancel queued run','button secondary');resume.type=cancel.type='button';resume.hidden=cancel.hidden=true;jobControls.append(resume,cancel);outputs.append(jobControls);
      const settings=node('details');settings.append(node('summary','Saved grid, source and statistical method'));const settingsText=node('pre');settings.append(settingsText);outputs.append(settings);
      async function jobAction(kind){if(busy||!job)return;if(kind==='cancel'&&job.status==='running'&&!window.confirm('Stop this running IS Narrow backtest at the next checkpoint? Completed trials will remain available for resuming.'))return;busy=true;try{const response=await read(`/api/backtests/batches/${job.id}/${kind}`,'POST');if(alive())notice.textContent=kind==='resume'?'Resuming saved Narrow trials.':response.status==='running'?'Stop requested. Active trials are stopping; completed results are retained.':'Queued run cancelled.';}catch(error){if(alive())notice.textContent=error.message;}finally{busy=false;if(alive())await refresh();}}
      resume.onclick=()=>jobAction('resume');cancel.onclick=()=>jobAction('cancel');
      const panel=node('details',undefined,'optimization-freeze');panel.id='narrow-columns';panel.innerHTML='<summary>Columns <span class="optimization-column-count small muted"></span><span class="optimization-freeze-count small muted"></span></summary><div class="optimization-freeze-body"><p class="field-help">Varied Narrow parameters are shown and frozen by default; fixed inputs are hidden. Show, hide, freeze or reorder columns. Choices are saved for this run in this browser.</p><div class="optimization-freeze-actions"><label>Find a column<input type="search" placeholder="Search columns…" /></label><button class="button secondary" type="button" data-columns="all">Show all</button><button class="button secondary" type="button" data-columns="hide">Hide all</button><button class="button secondary" type="button" data-columns="reset">Reset layout</button><button class="button secondary" type="button" data-freeze="none">Unfreeze all</button></div><p role="status" class="field-help"></p><div class="optimization-column-choices" role="group" aria-label="IS Narrow column layout"></div><p class="optimization-column-empty field-help" hidden>No matching columns.</p></div>';
      const empty=node('p','No columns selected. Open Columns to choose what to show.');empty.hidden=true;
      const scroll=node('div',undefined,'optimization-scroll');scroll.id='narrow-results-scroll';scroll.tabIndex=0;scroll.setAttribute('aria-label','IS Narrow results, scroll horizontally or vertically');
      const table=node('table',undefined,'library-table');table.id='narrow-results';table.innerHTML='<thead></thead><tbody></tbody>';scroll.append(table);outputs.append(panel,empty,scroll);
      columns=new window.OptimizationColumns(table,scroll,panel,{empty,defaultFrozen:['select','trial']});
      const pages=node('div',undefined,'report-pagination'),previous=node('button','Previous','button secondary'),next=node('button','Next','button secondary'),pageInfo=node('span');previous.type=next.type='button';previous.onclick=()=>{offset=Math.max(0,offset-50);refresh();};next.onclick=()=>{offset+=50;refresh();};pages.append(previous,pageInfo,next);outputs.append(pages);
      const selected=node('p');selected.id='narrow-selected';outputs.append(selected);
      const confirm=node('button','Confirm this Broad branch’s Narrow configs →','button primary');confirm.id='narrow-confirm';confirm.type='button';outputs.append(confirm);
      const selectionNotice=node('p');selectionNotice.id='narrow-selection-status';selectionNotice.setAttribute('role','status');outputs.append(selectionNotice);
      const frozen=node('div');outputs.append(frozen);
      function selectionState(){selected.textContent=`${state.selected_trials.length} / 2 selected for Broad trial ${trial} · maximum four across both branches`;
        confirm.disabled=!!state.confirmed_at_utc||!state.selected_trials.length||job?.status!=='complete'||saving||!detail.all_branches_complete;
        confirm.textContent=state.confirmed_at_utc?'Narrow choices confirmed':'Confirm this Broad branch’s Narrow configs →';
        for(const input of table.querySelectorAll('input[data-select-trial]'))input.disabled=saving||!!state.confirmed_at_utc||job?.status!=='complete'||input.dataset.eligible!=='true'||(!input.checked&&state.selected_trials.length>=2);
      }
      async function select(rowTrial,checked){if(saving)return;const trials=checked?[...state.selected_trials,rowTrial]:state.selected_trials.filter(t=>t!==rowTrial);if(trials.length>2)return;saving=true;selectionState();try{state=await read(base+'/selection','PATCH',{broad_trial:trial,job_id:job.id,revision:state.revision,trials});if(alive())selectionNotice.textContent='Narrow selection saved.';}catch(error){if(alive())selectionNotice.textContent=error.message;}finally{saving=false;if(alive())await refresh();}}
      confirm.onclick=async()=>{if(saving)return;saving=true;selectionState();try{state=await read(base+'/confirm','POST',{broad_trial:trial,job_id:job.id,revision:state.revision});if(alive()){selectionNotice.textContent='This Narrow selection is confirmed and locked.';await refresh();}}catch(error){if(alive())selectionNotice.textContent=error.message;}finally{saving=false;if(alive())selectionState();}};
      async function refresh(){clearTimeout(timer);if(!alive())return;if(saving){timer=setTimeout(refresh,500);return;}const attempt=++fetching;
        try{const latest=await read(url());if(!alive()||attempt!==fetching)return;state=latest.state;job=latest.job;detail.all_branches_complete=latest.all_branches_complete;
          const page=await read(url('/results',{sort,direction,offset,limit:50}));if(!alive()||attempt!==fetching)return;
          fieldset.disabled=!!job&&['queued','running','complete'].includes(job.status)||!!state.confirmed_at_utc;
          progress.textContent=job?`${job.status.toUpperCase()} · ${job.completed_trials} / ${job.total_trials} trials · ${job.stage} · ${job.worker_count||1} workers${job.error?' · '+job.error:''}${job.active_trials?.length?' · Active: '+job.active_trials.map(t=>`${t.trial} (${t.stage}, ${t.bars_processed}/${t.total_bars} bars)`).join(', '):''}`:'No Narrow grid for this Broad configuration yet.';
          settings.hidden=!job;settingsText.textContent=job?JSON.stringify({job_id:job.id,request:job.request,axes:job.axes,research:job.research,engine_identity:job.engine_identity,all_branches_complete:page.all_branches_complete,attempted_family_size:page.family_size,method:latest.policy},null,2):'';
          resume.hidden=!!state.confirmed_at_utc||(!['failed','interrupted'].includes(job?.status)&&!(job?.status==='cancelled'&&job.stop_requested_at_utc));
          cancel.hidden=!['queued','running'].includes(job?.status);cancel.disabled=busy||!!job?.stop_requested_at_utc;
          cancel.textContent=job?.stop_requested_at_utc?'Stop requested':job?.status==='running'?'Stop running backtest':'Cancel queued run';
          links.replaceChildren();if(job){action(links,'Job history / progress',`#jobs/backtest_batch/${job.id}`);action(links,'Results CSV ↓',`/api/backtests/batches/${job.id}/exports/results`);action(links,'Saved IS Narrow package ↓',url('/download'));}
          if(!job){panel.hidden=true;table.tHead.replaceChildren();table.tBodies[0].replaceChildren();previous.disabled=next.disabled=true;pageInfo.textContent='No results yet';selectionState();return;}
          const varying=Object.keys(job.axes).filter(name=>job.axes[name].length>1);
          const headers=[['select','Select'],['eligible','Eligibility'],['trial','Trial'],...Object.keys(job.axes).map(name=>['param.'+name,label(name)]),...job.metric_columns.map(name=>[name,title(name)]),['run_id','Backtest report']];
          const head=node('tr');for(const [key,text] of headers){const th=node('th');th.dataset.column=key;th.scope='col';if(['select','eligible'].includes(key))th.textContent=text;else{const button=node('button',text+(sort===key?(direction==='asc'?' ↑':' ↓'):' ↕'));button.type='button';button.onclick=()=>{direction=sort===key&&direction==='asc'?'desc':'asc';sort=key;offset=0;refresh();};th.append(button);}head.append(th);}table.tHead.replaceChildren(head);table.tBodies[0].replaceChildren();
          for(const row of page.items){const tr=node('tr');tr.dataset.trial=row.trial;if(!row.qualifies)tr.className='broad-ineligible';for(const [key] of headers){const td=node('td');td.dataset.column=key;
            if(key==='select'){const input=node('input');input.type='checkbox';input.dataset.selectTrial=row.trial;input.dataset.eligible=String(row.qualifies);input.setAttribute('aria-label',`Select Narrow trial ${row.trial}`);input.checked=state.selected_trials.includes(row.trial);input.onchange=()=>select(row.trial,input.checked);td.append(input);}
            else if(key==='eligible'){const info=node('details',undefined,'broad-row-criteria'),admission=row.admission;info.append(node('summary',admission?.error?admission.error:admission?.provisional?`Provisional · ${admission.checks.filter(c=>c.passed).length} / 9 checks passed · finish all branches`:row.qualifies?'Qualified · 9 / 9 checks passed':`Not qualified · ${admission?.checks.filter(c=>c.passed).length||0} / 9 checks passed`));if(admission?.checks?.length){const list=node('ul');for(const check of admission.checks){const item=node('li',`${check.passed?'PASS':'FAIL'} · ${check.label}: ${check.actual}. Required: ${check.required}`);item.dataset.passed=String(check.passed);list.append(item);}info.append(list);}td.append(info);}
            else if(key==='run_id'){if(row.backtest_deleted)td.textContent='Report unavailable';else{action(td,'Open report',`#backtests/report/${row.run_id}`);if(row.screening){td.append(node('br'));action(td,'Cost-stress report',`#backtests/report/${row.screening.cost_stress.run_id}`);td.append(node('br'));action(td,'Screening measurements ↓',`/api/backtests/${row.run_id}/exports/is_screening`);}}}
            else td.textContent=key==='trial'?String(row.trial):key.startsWith('param.')?String(row.parameters[key.slice(6)]):metric(key,row.metrics[key]);tr.append(td);}table.tBodies[0].append(tr);}
          columns.defaultFrozen=['select','trial',...varying.map(name=>'param.'+name)];columns.configure('campaign-narrow:'+workflow.id+':'+job.id,headers,headers.filter(([key])=>!key.startsWith('param.')||varying.includes(key.slice(6))).map(([key])=>key));
          previous.disabled=!offset;next.disabled=offset+page.items.length>=page.total;pageInfo.textContent=page.total?`${offset+1}–${offset+page.items.length} of ${page.total}`:'No saved results yet';
          frozen.replaceChildren();if(state.confirmed_at_utc){frozen.append(node('p','This Broad branch’s Narrow configurations are confirmed and locked.'));for(const item of state.selection)frozen.append(node('pre',JSON.stringify(item.parameters,null,2)));}
          const pending=latest.branches.filter(b=>!b.confirmed_at_utc);if(!pending.length){action(frozen,'Continue to OOS →',`#campaigns/workflows/${workflow.id}/oos`);}else if(state.confirmed_at_utc)action(frozen,`Confirm Broad trial ${pending[0].broad_trial} →`,`#campaigns/workflows/${workflow.id}/is_narrow?broad_trial=${pending[0].broad_trial}`);
          selectionState();if(['queued','running'].includes(job.status))timer=setTimeout(refresh,1000);
        }catch(error){if(alive())notice.textContent=error.message;}}
      await refresh();
    }catch(error){if(alive())parent.replaceChildren(node('p',error.message));}
  }
  window.campaignNarrow={render,dispose};
})();
