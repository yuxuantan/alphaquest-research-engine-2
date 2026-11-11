"use strict";
(() => {
  const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
  const label=value=>value.replaceAll('_',' ').replace(/^./,c=>c.toUpperCase());
  const twoDecimals=new Intl.NumberFormat('en-US',{minimumFractionDigits:2,maximumFractionDigits:2,useGrouping:false});
  const displayMetric=value=>value==null||value===''?'N/A':Number.isFinite(Number(value))?twoDecimals.format(value):String(value);
  const metricLabel=name=>name==='max_drawdown_duration_seconds'?'Max drawdown duration · calendar days':label(name);
  const metricValue=(name,value)=>name==='max_drawdown_duration_seconds'&&value!=null&&value!==''?displayMetric(Number(value)/86400):displayMetric(value);
  const read=async(url,method='GET',body)=>{const response=await fetch(url,{method,cache:'no-store',...(body===undefined?{}:{headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});const data=await response.json();if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'Check the parameter grid and saved selection.');return data;};
  let generation=0,timer,columns;
  function dispose(){++generation;clearTimeout(timer);columns?.destroy();columns=null;}
  function action(parent,text,href){const a=node('a',text,'workflow-inline-link');a.href=href;parent.append(a);return a;}
  async function render(parent,workflow,{isCurrent,jobId:requestedJob}) {
    dispose();const version=generation,alive=()=>version===generation&&isCurrent();
    const base=`/api/campaign-workflows/${workflow.id}/broad`;
    const forRun=(path='',params={})=>{const query=new URLSearchParams({...params,...(requestedJob?{job_id:requestedJob}:{})});return base+path+(query.size?'?'+query:'');};
    parent.replaceChildren(node('p','Loading IS Broad…'));
    try {
      let data=await read(forRun());if(!alive())return;
      let state=data.state,job=data.job,preview=null,busy=false,sort='trial',direction='asc',offset=0;
      parent.replaceChildren();
      if(state.archived){const archived=node('section',undefined,'panel broad-panel');archived.id='broad-archived';archived.append(node('h2','Earlier IS Broad run'),node('p','This saved run is read-only. Its results and downloads stay available; selections belong to the current run.'));action(archived,'Open current IS Broad →',`#campaigns/workflows/${workflow.id}/is_broad`);parent.append(archived);}
      if(data.legacy)parent.append(node('p',state.confirmed_at_utc?'Historical selection: confirmed under the earlier profitability-only rule. Preserved unchanged; it is not certified against the current four criteria.':'This earlier grid has no measured screening evidence. Calculate and run a new grid before selecting configurations.','broad-legacy-note'));
      if(data.reassessed)parent.append(node('p','This saved grid was measured under an earlier screening policy. Selection uses the four current rules from its saved measurements; the original reports and verdicts remain unchanged.','broad-legacy-note'));
      if(state.confirmed_at_utc&&state.screening_policy?.version==='is-broad-v2'&&!state.selection_policy)parent.append(node('p','Historical selection: confirmed under the earlier six-rule policy and preserved unchanged.','broad-legacy-note'));
      const config=node('section',undefined,'panel broad-panel');config.id='broad-config';
      config.append(node('h2','IS Broad parameter search'),node('p','Choose start, end and step for each parameter. Source, IS dates and execution costs stay bound to the validated workflow.'));
      const form=node('form'),fieldset=node('fieldset');form.append(fieldset);
      const region=node('div',undefined,'optimization-scroll'),grid=node('table',undefined,'library-table optimization-grid');
      grid.innerHTML='<thead><tr><th>Parameter</th><th>Start</th><th>End</th><th>Step</th><th>Count</th></tr></thead><tbody></tbody>';
      region.append(grid);fieldset.append(region);config.append(form);parent.append(config);
      const ranges=new Map();
      let draft;
      try {draft=JSON.parse(sessionStorage.getItem('broad-grid:'+workflow.id));}catch{}
      const parameters=data.strategy.parameters;
      const initial=state.confirmed_at_utc||state.archived?job?.request.parameter_ranges:draft || job?.request.parameter_ranges;
      for(const parameter of parameters) {
        const row=node('tr');row.dataset.parameter=parameter.name;
        const title=node('th',label(parameter.name));title.scope='row';title.append(node('small',parameter.description || '', 'field-help'));row.append(title);
        const inputs={};
        for(const part of ['start','end','step']) {
          const cell=node('td'),input=node(parameter.type==='bool'&&part!=='step'?'select':'input');
          if(input.tagName==='SELECT'){input.add(new Option('False','false'));input.add(new Option('True','true'));}
          else{input.type='text';input.inputMode=parameter.type==='Decimal'?'decimal':'numeric';input.maxLength=128;}
          input.required=true;input.setAttribute('aria-label',`${label(parameter.name)} ${part}`);
          input.value=String(initial?.[parameter.name]?.[part] ?? (part==='step'?0:parameter.default));
          inputs[part]=input;cell.append(input);row.append(cell);
          input.oninput=()=>{
            if(part!=='step') {
              const equal=inputs.start.value===inputs.end.value;
              if(equal)inputs.step.value='0';else if(inputs.step.value==='0')inputs.step.value='1';
            }
            preview=null;run.disabled=true;count.textContent='Grid changed. Calculate iterations before running.';
            try{sessionStorage.setItem('broad-grid:'+workflow.id,JSON.stringify(values()));}catch{}
          };
        }
        inputs.count=node('td','—');row.append(inputs.count);grid.tBodies[0].append(row);ranges.set(parameter.name,inputs);
      }
      const workerLabel=node('label','Parallel backtests'),workers=node('select');workers.id='broad-workers';
      for(let i=1;i<=data.max_workers;i++)workers.add(new Option(i===data.default_workers?`${i} · default`:String(i),String(i)));workers.value=String(job?.request.workers ?? data.default_workers);workerLabel.append(workers);fieldset.append(workerLabel);
      workers.onchange=()=>{preview=null;run.disabled=true;count.textContent='Worker setting changed. Calculate iterations again.';};
      const count=node('p','Calculate the number of parameter combinations.','optimization-count');count.id='broad-count';fieldset.append(count);
      const calculate=node('button','Calculate iterations','button secondary');calculate.type='button';calculate.id='broad-preview';
      const run=node('button','Run IS Broad →','button primary');run.type='submit';run.id='broad-run';run.disabled=true;
      const controls=node('div',undefined,'mechanic-downloads');controls.append(calculate,run);fieldset.append(controls);
      const notice=node('p');notice.id='broad-status';notice.setAttribute('role','status');config.append(notice);
      const integer=value=>{if(!/^-?\d+$/.test(value)||!Number.isSafeInteger(Number(value)))throw Error('Enter whole numbers within the safe integer range.');return Number(value);};
      function values(){return Object.fromEntries(parameters.map(p=>{const r=ranges.get(p.name);return [p.name,{start:p.type==='bool'?r.start.value==='true':p.type==='int'?integer(r.start.value):r.start.value.trim(),end:p.type==='bool'?r.end.value==='true':p.type==='int'?integer(r.end.value):r.end.value.trim(),step:p.type==='Decimal'?r.step.value.trim():integer(r.step.value)}];}));}
      function requestGrid(){return {parameter_ranges:values(),workers:Number(workers.value)};}
      calculate.onclick=async()=>{
        if(!form.reportValidity()||busy)return;busy=true;calculate.disabled=true;
        try{preview=await read(base+'/preview','POST',requestGrid());if(!alive())return;for(const [name,r] of ranges)r.count.textContent=preview.step_counts[name];count.textContent=`${preview.total_trials.toLocaleString()} iterations · IS only`;run.disabled=false;notice.textContent='Grid validated. Each configuration runs at normal costs and with +1 tick of slippage per fill.';}
        catch(error){if(alive()){preview=null;run.disabled=true;notice.textContent=error.message;}}
        finally{busy=false;if(alive())calculate.disabled=false;}
      };
      form.onsubmit=async event=>{
        event.preventDefault();if(busy||!preview||!form.reportValidity())return;busy=true;fieldset.disabled=true;
        try{job=await read(base+'/run','POST',{...requestGrid(),preview_token:preview.preview_token,revision:preview.revision});if(!alive())return;preview=null;run.disabled=true;if(requestedJob&&requestedJob!==job.id){location.replace(`#campaigns/workflows/${workflow.id}/is_broad?job=${job.id}`);return;}notice.textContent='IS Broad job started. You can leave this page and follow it in Job history.';await refresh();}
        catch(error){if(alive())notice.textContent=error.message;}
        finally{busy=false;if(alive())fieldset.disabled=!!state.archived||!!state.confirmed_at_utc||['queued','running'].includes(job?.status);}
      };
      const outputs=node('section',undefined,'panel broad-panel');outputs.append(node('h2','IS Broad results'),node('p',`Eligibility: ${data.criterion} Choose one or two qualified configurations, then confirm to continue. Open a row’s eligibility details to see every measured check.`));parent.append(outputs);
      const progress=node('p');progress.id='broad-progress';progress.setAttribute('role','status');outputs.append(progress);
      const links=node('div',undefined,'mechanic-downloads');outputs.append(links);
      const jobControls=node('div',undefined,'mechanic-downloads'),resume=node('button','Resume remaining trials','button secondary'),cancel=node('button','Cancel queued run','button secondary');
      resume.id='broad-resume';cancel.id='broad-cancel';resume.type=cancel.type='button';resume.hidden=cancel.hidden=true;jobControls.append(resume,cancel);outputs.append(jobControls);
      const settings=node('details');settings.id='broad-run-settings';settings.append(node('summary','Saved run settings'));const settingsText=node('pre');settings.append(settingsText);outputs.append(settings);
      async function jobAction(kind){
        if(busy||state.archived||!job)return;
        if(kind==='cancel'&&job.status==='running'&&!window.confirm('Stop this running IS Broad backtest at the next checkpoint? Completed trials will remain available for resuming.'))return;
        busy=true;fieldset.disabled=true;resume.disabled=cancel.disabled=true;
        try{const response=await read(`/api/backtests/batches/${job.id}/${kind}`,'POST');if(alive())notice.textContent=kind==='resume'?'Resuming the saved IS Broad run.':response.status==='running'?'Stop requested. Active trials are stopping; completed results are retained.':'Queued run cancelled.';}
        catch(error){if(alive())notice.textContent=error.message;}
        finally{busy=false;if(alive())await refresh();}
      }
      resume.onclick=()=>jobAction('resume');cancel.onclick=()=>jobAction('cancel');
      const panel=node('details',undefined,'optimization-freeze');panel.id='broad-columns';
      panel.innerHTML='<summary>Columns <span class="optimization-column-count small muted"></span><span class="optimization-freeze-count small muted"></span></summary><div class="optimization-freeze-body"><p class="field-help">Varied parameters are shown and frozen by default; fixed parameters are hidden. Show, hide, freeze or reorder columns. Choices are saved for this run in this browser.</p><div class="optimization-freeze-actions"><label>Find a column<input type="search" placeholder="Search columns…" /></label><button class="button secondary" type="button" data-columns="all">Show all</button><button class="button secondary" type="button" data-columns="hide">Hide all</button><button class="button secondary" type="button" data-columns="reset">Reset layout</button><button class="button secondary" type="button" data-freeze="none">Unfreeze all</button></div><p id="broad-column-status" role="status" class="field-help"></p><div class="optimization-column-choices" role="group" aria-label="IS Broad column layout"></div><p class="optimization-column-empty field-help" hidden>No matching columns.</p></div>';
      const empty=node('p','No columns selected. Open Columns to choose what to show.');empty.hidden=true;
      const scroll=node('div',undefined,'optimization-scroll');scroll.id='broad-results-scroll';scroll.tabIndex=0;scroll.setAttribute('aria-label','IS Broad results, scroll horizontally or vertically');
      const table=node('table',undefined,'library-table');table.id='broad-results';table.innerHTML='<thead></thead><tbody></tbody>';scroll.append(table);outputs.append(panel,empty,scroll);
      columns=new window.OptimizationColumns(table,scroll,panel,{empty,defaultFrozen:['select','trial']});
      const pages=node('div',undefined,'report-pagination'),previous=node('button','Previous','button secondary'),next=node('button','Next','button secondary'),pageInfo=node('span');
      previous.type=next.type='button';previous.onclick=()=>{offset=Math.max(0,offset-50);refresh();};next.onclick=()=>{offset+=50;refresh();};pages.append(previous,pageInfo,next);outputs.append(pages);
      const selected=node('p');selected.id='broad-selected';outputs.append(selected);
      const confirm=node('button','Confirm configs and continue to IS Narrow →','button primary');confirm.id='broad-confirm';confirm.type='button';outputs.append(confirm);
      const selectionNotice=node('p');selectionNotice.id='broad-selection-status';selectionNotice.setAttribute('role','status');outputs.append(selectionNotice);
      const frozen=node('div');frozen.id='broad-frozen';outputs.append(frozen);
      let fetching=0,saving=false;
      function selectionState(){
        selected.textContent=`${state.selected_trials.length} / 2 configurations selected${state.selected_trials.length?' · trials '+state.selected_trials.join(', '):''}`;
        confirm.disabled=!!state.archived||!!state.confirmed_at_utc||!state.selected_trials.length||job?.status!=='complete'||saving;
        confirm.textContent=state.confirmed_at_utc?'Configurations confirmed': 'Confirm configs and continue to IS Narrow →';
        for(const input of table.querySelectorAll('input[data-select-trial]'))input.disabled=!!state.archived||saving||!!state.confirmed_at_utc||job?.status!=='complete'||input.dataset.eligible!=='true'||(!input.checked&&state.selected_trials.length>=2);
      }
      async function select(trial,checked){
        if(saving)return;const chosen=checked?[...state.selected_trials,trial]:state.selected_trials.filter(id=>id!==trial);
        if(chosen.length>2)return;++fetching;saving=true;selectionState();
        try{state=await read(base+'/selection','PATCH',{job_id:job.id,revision:state.revision,trials:chosen});if(!alive())return;selectionNotice.textContent='Selection saved.';}
        catch(error){if(alive())selectionNotice.textContent=error.message;}
        finally{saving=false;if(alive()){await refresh();selectionState();}}
      }
      confirm.onclick=async()=>{
        if(saving)return;saving=true;selectionState();
        try{state=await read(base+'/confirm','POST',{job_id:job.id,revision:state.revision});if(alive())location.hash=`#campaigns/workflows/${workflow.id}/is_narrow`;}
        catch(error){if(alive())selectionNotice.textContent=error.message;}
        finally{saving=false;if(alive())selectionState();}
      };
      async function refresh(){
        clearTimeout(timer);if(!alive())return;
        if(saving){timer=setTimeout(refresh,500);return;}
        const attempt=++fetching;
        try{
          const updated=await read(forRun());if(!alive()||attempt!==fetching)return;
          state=updated.state;job=updated.job;
          const page=await read(forRun('/results',{sort,direction,offset,limit:50}));if(!alive()||attempt!==fetching)return;
          fieldset.disabled=!!state.archived||!!state.confirmed_at_utc||['queued','running'].includes(job?.status);
          const phaseButton=document.querySelector('#mechanic-phases [data-phase="is_broad"]');
          if(phaseButton&&!state.archived){phaseButton.dataset.status=state.status;phaseButton.querySelector('.mechanic-phase-state').textContent=state.status.replaceAll('_',' ');}
          progress.textContent=job?`${job.status.toUpperCase()} · ${job.completed_trials} / ${job.total_trials} trials · ${job.stage} · ${job.worker_count||1} workers${job.elapsed_seconds==null?'':` · ${job.elapsed_seconds.toFixed(1)}s elapsed`} · ${job.reused_trials||0} reused${job.error?' · '+job.error:''}${job.cancellation_reason?' · '+job.cancellation_reason:''}${job.active_trials?.length?' · Active: '+job.active_trials.map(t=>`${t.trial} (${t.stage}, ${t.bars_processed}/${t.total_bars} bars)`).join(', '):''}`:'No IS Broad job yet.';
          settings.hidden=!job;settingsText.textContent=job?JSON.stringify({run_id:job.id,created_at_utc:job.created_at_utc,started_at_utc:job.started_at_utc,finished_at_utc:job.finished_at_utc,request:job.request,axes:job.axes,execution_settings:job.execution_settings,worker_count:job.worker_count,engine_identity:job.engine_identity,screening_policy:job.research?.screening_policy,previous_attempts:job.previous_attempts||[]},null,2):'';
          resume.hidden=!!state.archived||!!state.confirmed_at_utc||(!['failed','interrupted'].includes(job?.status)&&!(job?.status==='cancelled'&&job.stop_requested_at_utc));resume.disabled=busy;
          resume.textContent=job?.completed_trials<job?.total_trials?`Resume remaining ${job.total_trials-job.completed_trials} trials`:'Finalize saved results';
          cancel.hidden=!!state.archived||!['queued','running'].includes(job?.status);
          cancel.disabled=busy||!!job?.stop_requested_at_utc;
          cancel.textContent=job?.stop_requested_at_utc?'Stop requested':job?.status==='running'?'Stop running backtest':'Cancel queued run';
          links.replaceChildren();
          if(job){action(links,'Job history / progress',`#jobs/backtest_batch/${job.id}`);action(links,'Results CSV ↓',`/api/backtests/batches/${job.id}/exports/results`);action(links,'Saved IS Broad package ↓',forRun('/download'));}
          if(!job){panel.hidden=true;table.tHead.replaceChildren();table.tBodies[0].replaceChildren();previous.disabled=next.disabled=true;pageInfo.textContent='No results yet';selectionState();return;}
          const varying=Object.keys(job.axes).filter(name=>job.axes[name].length>1);
          const headers=[['select','Select'],['eligible','Eligibility'],['trial','Trial'],...Object.keys(job.axes).map(name=>['param.'+name,label(name)]),...job.metric_columns.map(name=>[name,metricLabel(name)]),['run_id','Backtest report']];
          const head=node('tr');
          for(const [key,title] of headers){const th=node('th');th.dataset.column=key;th.scope='col';
            if(['select','eligible'].includes(key))th.textContent=title;else{const button=node('button',title+(sort===key?(direction==='asc'?' ↑':' ↓'):' ↕'));button.type='button';button.onclick=()=>{direction=sort===key&&direction==='asc'?'desc':'asc';sort=key;offset=0;refresh();};th.append(button);}head.append(th);}
          table.tHead.replaceChildren(head);table.tBodies[0].replaceChildren();
          for(const row of page.items){const tr=node('tr');tr.dataset.trial=row.trial;if(!row.qualifies)tr.className='broad-ineligible';
            for(const [key] of headers){const td=node('td');td.dataset.column=key;
              if(key==='select'){const input=node('input');input.type='checkbox';input.dataset.selectTrial=row.trial;input.dataset.eligible=String(row.qualifies);input.setAttribute('aria-label',`Select trial ${row.trial}`);input.checked=state.selected_trials.includes(row.trial);input.onchange=()=>select(row.trial,input.checked);td.append(input);}
              else if(key==='eligible'){
                const info=node('details',undefined,'broad-row-criteria'),measured=row.admission||row.screening;
                info.append(node('summary',row.legacy_screening?'Historical rule':!measured?'Not qualified · rerun required':measured.status==='insufficient_evidence'?'Insufficient evidence':row.qualifies?`Qualified · ${measured.checks.length} / ${measured.checks.length} passed`:`Not qualified · ${measured.checks.filter(c=>c.passed).length} / ${measured.checks.length} passed`));
                if(measured){const list=node('ul');for(const check of measured.checks){const item=node('li',`${check.passed?'PASS':'FAIL'} · ${check.label}: ${check.actual}. Required: ${check.required}`);item.dataset.passed=String(check.passed);list.append(item);}info.append(list);}
                else info.append(node('p','This historical grid only checked positive net profit. New selections require a grid with measured screening evidence.'));
                td.append(info);
              }
              else if(key==='run_id'){if(row.backtest_deleted)td.textContent='Report unavailable';else{action(td,'Open report',`#backtests/report/${row.run_id}`);if(row.screening){td.append(node('br'));action(td,'Cost-stress report',`#backtests/report/${row.screening.cost_stress.run_id}`);td.append(node('br'));action(td,'Screening measurements ↓',`/api/backtests/${row.run_id}/exports/is_screening`);}}}
              else td.textContent=key==='trial'?String(row.trial):key.startsWith('param.')?String(row.parameters[key.slice(6)]):metricValue(key,row.metrics[key]);tr.append(td);
            }table.tBodies[0].append(tr);}
          columns.defaultFrozen=['select','trial',...varying.map(name=>'param.'+name)];
          columns.configure('campaign-broad:'+workflow.declaration.strategy_id+':'+job.id,headers,
            headers.filter(([key])=>!key.startsWith('param.')||varying.includes(key.slice(6))).map(([key])=>key));
          previous.disabled=!offset;next.disabled=offset+page.items.length>=page.total;pageInfo.textContent=page.total?`${offset+1}–${offset+page.items.length} of ${page.total}`:'No saved results yet';
          frozen.replaceChildren();
          if(state.confirmed_at_utc){frozen.append(node('p','Selection is confirmed and locked.'));for(const item of state.selection){frozen.append(node('pre',JSON.stringify(item.parameters,null,2)));}action(frozen,'Continue to IS Narrow →',`#campaigns/workflows/${workflow.id}/is_narrow`);}
          selectionState();
          if(['queued','running'].includes(job.status))timer=setTimeout(refresh,1000);
        }catch(error){if(alive())notice.textContent=error.message;}
      }
      await refresh();
    }catch(error){if(alive())parent.replaceChildren(node('p',error.message));}
  }
  window.campaignBroad={render,dispose};
})();
