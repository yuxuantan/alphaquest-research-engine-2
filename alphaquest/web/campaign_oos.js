"use strict";
(() => {
  const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
  const label=value=>value.replaceAll('_',' ').replace(/^./,c=>c.toUpperCase());
  const number=new Intl.NumberFormat('en-US',{minimumFractionDigits:2,maximumFractionDigits:2,useGrouping:false});
  const format=value=>value==null?'N/A':Number.isFinite(Number(value))?number.format(value):String(value);
  const read=async(url,method='GET',body)=>{const response=await fetch(url,{method,cache:'no-store',...(body===undefined?{}:{headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});const data=await response.json();if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'OOS request rejected.');return data;};
  const link=(parent,text,href)=>{const n=node('a',text,'workflow-inline-link');n.href=href;parent.append(n);};
  let generation=0,timer,columns;
  function dispose(){++generation;clearTimeout(timer);columns?.destroy();columns=null;}
  async function render(parent,workflow,{isCurrent,jobId}){
    dispose();const version=generation,alive=()=>version===generation&&isCurrent(),base=`/api/campaign-workflows/${workflow.id}/oos`;
    const url=path=>base+path+(jobId?'?job='+jobId:'');
    let detail,job,busy=false,requestId=crypto.randomUUID(),items=[],sort='candidate',ascending=true;
    parent.replaceChildren(node('p','Loading frozen OOS candidates…'));
    try{
      detail=await read(url(''));if(!alive())return;job=detail.job;parent.replaceChildren();
      const panel=node('section',undefined,'panel broad-panel');panel.id='oos-panel';parent.append(panel);
      panel.append(node('h2','OOS assessment · all frozen configurations'),node('p',`OOS ${detail.plan.oos_start} → ${detail.plan.oos_end}. Assess all ${detail.candidates.length} confirmed Narrow configurations with the same parameters, dataset and execution costs. Each can pass independently; no IS choices are changed.`));
      const controls=node('div',undefined,'mechanic-downloads'),workerLabel=node('label','Parallel backtests'),workers=node('select');workers.id='oos-workers';
      for(let i=1;i<=detail.max_workers;i++)workers.add(new Option(i===detail.default_workers?`${i} · default`:String(i),String(i)));
      workers.value=String(detail.default_workers);workerLabel.append(workers);controls.append(workerLabel);
      const run=node('button','Run all frozen OOS configurations','button primary');run.id='oos-run';run.type='button';controls.append(run);panel.append(controls);
      const access=node('p',undefined,'field-help');access.id='oos-access';panel.append(access);
      const historyLabel=node('label','Saved OOS assessments'),history=node('select');history.id='oos-history';historyLabel.append(history);panel.append(historyLabel);
      history.onchange=()=>{location.hash=`#campaigns/workflows/${workflow.id}/oos?job=${history.value}`;};
      const progress=node('p');progress.id='oos-progress';progress.setAttribute('role','status');panel.append(progress);
      const active=node('section',undefined,'jobs-active-trials');active.id='oos-active-trials';panel.append(active);
      const actions=node('div',undefined,'mechanic-downloads'),stop=node('button','Stop running backtest','button secondary'),resume=node('button','Resume remaining configurations','button secondary');stop.type=resume.type='button';stop.id='oos-stop';resume.id='oos-resume';actions.append(stop,resume);panel.append(actions);
      const notice=node('p');notice.id='oos-status';notice.setAttribute('role','status');panel.append(notice);
      const downloads=node('div',undefined,'mechanic-downloads');panel.append(downloads);
      const outcome=node('p');outcome.id='oos-outcome';panel.append(outcome);
      const chooser=node('details',undefined,'optimization-freeze');chooser.id='oos-columns';chooser.innerHTML='<summary>Columns <span class="optimization-column-count small muted"></span><span class="optimization-freeze-count small muted"></span></summary><div class="optimization-freeze-body"><p class="field-help">Varied frozen parameters are shown and frozen by default. Show, hide, freeze or reorder columns.</p><div class="optimization-freeze-actions"><label>Find a column<input type="search" /></label><button class="button secondary" type="button" data-columns="all">Show all</button><button class="button secondary" type="button" data-columns="hide">Hide all</button><button class="button secondary" type="button" data-columns="reset">Reset layout</button><button class="button secondary" type="button" data-freeze="none">Unfreeze all</button></div><p role="status" class="field-help"></p><div class="optimization-column-choices" role="group" aria-label="OOS column layout"></div><p class="optimization-column-empty field-help" hidden>No matching columns.</p></div>';
      const empty=node('p','No columns selected.');empty.hidden=true;
      const scroll=node('div',undefined,'optimization-scroll');scroll.id='oos-results-scroll';scroll.tabIndex=0;
      const table=node('table',undefined,'library-table');table.id='oos-results';table.innerHTML='<thead></thead><tbody></tbody>';scroll.append(table);panel.append(chooser,empty,scroll);
      columns=new window.OptimizationColumns(table,scroll,chooser,{empty,defaultFrozen:['candidate']});
      const names=Object.keys(detail.candidates[0].parameters),varied=names.filter(name=>new Set(detail.candidates.map(c=>String(c.parameters[name]))).size>1);
      const headers=[['candidate','Candidate'],['broad','Broad trial'],['narrow','Narrow trial'],...names.map(name=>['param.'+name,label(name)]),['eligibility','OOS eligibility'],['is_annual','IS net / year'],['oos_annual','OOS net / year'],['annual_retention','Annual profit retained %'],['is_average','IS net / trade'],['oos_average','OOS net / trade'],['trade_retention','Profit / trade retained %'],['is_dd','IS MTM max drawdown'],['oos_dd','OOS MTM max drawdown'],['net','OOS net profit'],['trades','OOS trades'],['months','OOS profitable months %'],['stress','OOS extra-slippage net'],['dd_days','OOS MTM DD duration · calendar days'],['parameters','All frozen parameters'],['report','Reports']];
      const value=(item,key)=>{const m=item.metrics||{},b=item.is_reference,a=item.admission||{};return key.startsWith('param.')?item.parameters[key.slice(6)]:({candidate:item.trial,broad:item.broad_trial,narrow:item.narrow_trial,is_annual:b.metrics.is_annual_net_profit,oos_annual:m.oos_annual_net_profit,annual_retention:a.annual_profit_retention_pct,is_average:Number(b.total_net_pnl)/b.closed_trades,oos_average:m.trades_taken?Number(m.total_net_pnl)/m.trades_taken:null,trade_retention:a.profit_per_trade_retention_pct,is_dd:b.metrics.is_mtm_max_drawdown,oos_dd:m.oos_mtm_max_drawdown,net:m.total_net_pnl,trades:m.trades_taken,months:m.oos_profitable_months_pct,stress:m.oos_stress_net_profit,dd_days:item.measurements?.mtm_drawdown_duration_seconds==null?null:Number(item.measurements.mtm_drawdown_duration_seconds)/86400})[key];};
      function paintTable(){
        const head=node('tr');for(const [key,text] of headers){const th=node('th');th.dataset.column=key;th.scope='col';if(['eligibility','parameters','report'].includes(key))th.textContent=text;else{const button=node('button',text+(sort===key?(ascending?' ↑':' ↓'):' ↕'));button.type='button';button.onclick=()=>{ascending=sort===key?!ascending:true;sort=key;paintTable();};th.append(button);}head.append(th);}table.tHead.replaceChildren(head);
        const ordered=[...items].sort((a,b)=>{const x=value(a,sort),y=value(b,sort);if(x==null||y==null)return x==null?(y==null?0:1):-1;const result=Number.isFinite(Number(x))&&Number.isFinite(Number(y))?Number(x)-Number(y):String(x).localeCompare(String(y));return ascending?result:-result;});
        table.tBodies[0].replaceChildren();for(const item of ordered){const tr=node('tr');tr.dataset.trial=item.trial;if(item.status!=='pending'&&!item.qualifies)tr.className='broad-ineligible';
          for(const [key] of headers){const td=node('td');td.dataset.column=key;
            if(key==='eligibility'){const info=node('details',undefined,'broad-row-criteria'),passed=item.admission?.checks.filter(c=>c.passed).length||0;info.append(node('summary',item.error?`Unavailable: ${item.error}`:item.status==='pending'?'Not completed':`${label(item.status)} · ${passed} / 7 checks passed`));if(item.admission){const list=node('ul');for(const c of item.admission.checks){const li=node('li',`${c.passed?'PASS':'FAIL'} · ${c.label}: ${c.actual}. Required: ${c.required}`);li.dataset.passed=String(c.passed);list.append(li);}info.append(list);}td.append(info);}
            else if(key==='parameters'){const d=node('details');d.append(node('summary','Frozen parameters'),node('pre',JSON.stringify(item.parameters,null,2)));td.append(d);}
            else if(key==='report'){link(td,'IS report',`#backtests/report/${item.is_run_id}`);if(item.run_id){td.append(node('br'));link(td,'OOS report',`#backtests/report/${item.run_id}`);td.append(node('br'));link(td,'OOS cost-stress report',`#backtests/report/${item.cost_stress_run_id}`);td.append(node('br'));link(td,'OOS measurements ↓',`/api/backtests/${item.run_id}/exports/oos_screening`);}}
            else{const v=value(item,key);td.textContent=key.startsWith('param.')||['candidate','broad','narrow','trades'].includes(key)?v==null?'N/A':String(v):format(v);}tr.append(td);
          }table.tBodies[0].append(tr);
        }
        columns.defaultFrozen=['candidate',...varied.map(name=>'param.'+name)];columns.configure(`campaign-oos:${workflow.id}:${job?.id||detail.identity}`,headers,headers.filter(([key])=>!key.startsWith('param.')||varied.includes(key.slice(6))).map(([key])=>key));
      }
      function paintPhase(status){
        if(job&&detail.history[0]?.id!==job.id)return;
        const step=document.querySelector('#mechanic-phases [data-phase="oos"]');
        if(step){step.dataset.status=status;step.querySelector('.mechanic-phase-state').textContent=status.replaceAll('_',' ');step.setAttribute('aria-label',`Step 4 of 4: OOS, ${status.replaceAll('_',' ')}`);}
      }
      function paintProgress(){
        const running=['queued','running'].includes(job?.status);run.disabled=busy||running;workers.disabled=busy||running;
        run.textContent=job?'Run another manual OOS assessment':'Run all frozen OOS configurations';
        progress.textContent=job?`${job.status.toUpperCase()} · ${job.completed_trials} / ${job.total_trials} configurations · ${job.stage}${job.error?' · '+job.error:''}`:'Ready to assess the frozen family. Opening this page does not run OOS.';
        if(job?.status!=='complete')paintPhase(job?.status||'ready');
        stop.hidden=!running;stop.disabled=busy||!!job?.stop_requested_at_utc;stop.textContent=job?.stop_requested_at_utc?'Stop requested':'Stop running backtest';
        resume.hidden=!job||(!['interrupted','failed'].includes(job.status)&&!(job.status==='cancelled'&&job.stop_requested_at_utc));resume.disabled=busy;
        active.replaceChildren();active.hidden=job?.status!=='running'||!job?.active_trials?.length;
        if(!active.hidden){active.append(node('h3',`Active configurations · ${job.active_trials.length} workers`));const list=node('ul');for(const trial of job.active_trials){const item=node('li');item.append(node('span',`Candidate ${trial.trial} · ${trial.stage} · ${Number(trial.bars_processed||0).toLocaleString()} / ${Number(trial.total_bars||0).toLocaleString()} bars`));if(trial.total_bars){const bar=node('progress');bar.max=trial.total_bars;bar.value=trial.bars_processed||0;item.append(bar);}list.append(item);}active.append(list);}
      }
      async function refresh(){
        clearTimeout(timer);const latest=await read(url(''));if(!alive())return;detail=latest;job=detail.job;paintProgress();
        history.replaceChildren();history.add(new Option('Choose an assessment',''));for(const old of detail.history)history.add(new Option(`${new Date(old.created_at_utc).toLocaleString()} · ${old.status} · ${old.completed_trials}/${old.total_trials}`,old.id));history.value=job?.id||'';
        access.textContent=job?`Prior OOS attempts before this batch: ${job.research.prior_oos_attempts}. Local access status before launch: ${job.research.prior_access.status}. This is a manual historical assessment; no untouched-data certificate is claimed. Repeated runs remain in history.`:'All candidates and acceptance thresholds are frozen before launch. Previous local or external access can affect how OOS evidence should be interpreted.';
        const data=await read(url('/results'));if(!alive())return;
        items=data.items.length?data.items:detail.candidates.map((c,i)=>({trial:i+1,broad_trial:c.broad_trial,narrow_trial:c.trial,parameters:c.parameters,is_run_id:c.run_id,is_reference:c.is_reference,status:'pending',qualifies:false}));
        paintTable();if(job?.status==='complete')paintPhase(data.passed?'passed':'not_qualified');outcome.textContent=job?.status==='complete'?`${data.passed} / ${data.total} configurations passed OOS. Each passing configuration remains eligible independently; OOS does not revise the IS selections.`:job?'Completed results remain visible while remaining configurations run.':'Seven checks will be shown per completed configuration.';
        downloads.replaceChildren();if(job){link(downloads,'Job history / progress',`#jobs/backtest_batch/${job.id}`);link(downloads,'OOS assessment JSON ↓',url('/download'));link(downloads,'OOS results CSV ↓',url('/download')+(jobId?'&':'?')+'format=csv');}
        if(['queued','running'].includes(job?.status))timer=setTimeout(poll,2500);
      }
      async function poll(){try{const previous=job,updated=await read(`/api/optimizations/${job.id}`);if(!alive())return;job=updated;paintProgress();if(job.completed_trials!==previous.completed_trials||job.status!==previous.status){await refresh();return;}}catch(error){if(alive())notice.textContent=`Progress update failed: ${error.message}`;}if(alive()&&['queued','running'].includes(job?.status))timer=setTimeout(poll,2500);}
      run.onclick=async()=>{if(busy)return;busy=true;paintProgress();notice.textContent='Starting frozen OOS candidates…';try{const created=await read(base+'/run','POST',{request_id:requestId,workers:Number(workers.value)});if(!alive())return;requestId=crypto.randomUUID();location.hash=`#campaigns/workflows/${workflow.id}/oos?job=${created.id}`;}catch(error){if(alive())notice.textContent=error.message;}finally{busy=false;if(alive())paintProgress();}};
      async function jobAction(kind){if(busy||!job)return;busy=true;paintProgress();try{await read(kind==='stop'?`/api/backtests/batches/${job.id}/cancel`:`${base}/jobs/${job.id}/resume`,'POST');if(alive()){notice.textContent=kind==='stop'?'Stop requested; completed reports are retained.':'Resuming remaining frozen configurations.';await refresh();}}catch(error){if(alive())notice.textContent=error.message;}finally{busy=false;if(alive())paintProgress();}}
      stop.onclick=()=>jobAction('stop');resume.onclick=()=>jobAction('resume');await refresh();
    }catch(error){if(alive())parent.replaceChildren(node('p',error.message));}
  }
  window.campaignOOS={render,dispose};
})();
