"use strict";
(() => {
  const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
  const fmt=v=>v==null?'Unavailable':Number(v).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
  const pct=v=>v==null?'Unavailable':fmt(Number(v)*100)+'%';
  const read=async(url,method='GET',body)=>{const r=await fetch(url,{method,cache:'no-store',...(body?{headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})});const value=await r.json();if(!r.ok)throw Error(typeof value.detail==='string'?value.detail:JSON.stringify(value.detail));return value;};
  const link=(parent,text,href)=>{const a=node('a',text,'workflow-inline-link');a.href=href;parent.append(a);};
  const detail=(parent,title,value)=>{const d=node('details');d.append(node('summary',title),node('pre',JSON.stringify(value,null,2)));parent.append(d);return d;};
  let generation=0,timer;
  async function render(){
    ++generation;clearTimeout(timer);if(location.hash.split('?')[0]!=='#prop-sim')return;
    const version=generation,alive=()=>version===generation&&location.hash.split('?')[0]==='#prop-sim',host=document.querySelector('#prop-sim-content');
    const query=new URLSearchParams(location.hash.split('?')[1]||''),selectedId=query.get('analysis'),sourceId=query.get('source');
    host.replaceChildren(node('p','Loading qualified configurations…'));
    try{
      const [sources,defaults,history]=await Promise.all([read('/api/prop-sim/candidates'),read('/api/prop-sim/defaults'),read('/api/prop-sim')]);if(!alive())return;
      host.replaceChildren();const form=node('form',undefined,'panel broad-panel');form.id='prop-sim-form';host.append(form);
      form.append(node('h2','1. Choose one qualified configuration'),node('p','Only configurations with confirmed mechanics, IS Broad, IS Narrow, OOS and the current Monte Carlo check can enter this analysis. Select one configuration; multiple-source portfolio allocation will be added later.'));
      const label=node('label','Qualified configuration'),picker=node('select');picker.id='prop-sim-source';picker.add(new Option('Choose a configuration',''));
      sources.items.forEach((item,i)=>picker.add(new Option(`${item.strategy_id.replaceAll('_',' ')} · ${item.dataset.name} · Broad ${item.broad_trial} / Narrow ${item.narrow_trial} · OOS candidate ${item.selection.candidate}`,String(i))));label.append(picker);form.append(label);
      if(!sources.items.length)form.append(node('p','No qualified, compatible configurations are available. Complete the campaign phases and current Monte Carlo assessment first.'));
      if(sources.unavailable.length)detail(form,'Unavailable sources and reasons',sources.unavailable);
      const sourceInfo=node('div');sourceInfo.id='prop-sim-source-details';form.append(sourceInfo);
      form.append(node('h2','2. Configure independent sizing searches'),node('p',`APEX › 50K EOD · local model ${defaults.rule_version}`));
      const grid=node('div',undefined,'prop-sim-settings');form.append(grid);const fields={};
      const names=[['minimum_micros','Minimum size · whole MNQ contracts','number'],['maximum_micros','Maximum size · whole MNQ contracts','number'],['simulations','Simulated paths per size, per phase','number'],['seed','Random seed','number'],['block_weekdays','History block length · weekdays','select'],['evaluation_price','Evaluation purchase fee · USD','text'],['activation_fee','Activation fee · USD','text'],['commission_per_mnq_side','MNQ commission per contract per side · USD','text'],['start_date','Scenario start date · America/Chicago','date'],['funded_horizon_calendar_days','Funded horizon · calendar days','number'],['receipt_delay_calendar_days','Payout receipt delay · calendar days','number'],['maximum_funded_breach_probability','Maximum funded breach probability · 0 to 1','number'],['closures','Full-session closures · comma-separated YYYY-MM-DD','text']];
      for(const [name,text,type] of names){const label=node('label',text),input=node(type==='select'?'select':'input');input.id='prop-sim-'+name;fields[name]=input;
        if(type==='select'){for(const n of [1,5,10])input.add(new Option(String(n),String(n)));}else input.type=type;
        if(type==='number'){input.step=name==='maximum_funded_breach_probability'?'.01':'1';input.min='0';}
        input.value=name==='start_date'?new Date().toLocaleDateString('en-CA',{timeZone:'America/Chicago'}):name==='closures'?'':String(defaults.defaults[name]);
        label.append(input);grid.append(label);
      }
      detail(form,'Account rules, source assumptions and interpretation',{evaluation:defaults.evaluation_rules,funded:defaults.funded_rules,rule_provenance:defaults.rule_provenance,disclosure:defaults.disclosure});
      form.append(node('p','The preserved local model uses 21-session expiry/inactivity clocks and permits exactly 50% funded consistency. Published calendar-day/boundary rules differ; inspect the rule provenance above before relying on account outcomes.','field-help'));
      form.append(node('p','Fees are editable scenario inputs. Receipt timing and the weekday/closure calendar are assumptions. Position sizes use MNQ units: 10 MNQ equals one NQ in point exposure. Costs replace the source commission; they are not charged twice.','field-help'));
      const buttons=node('div',undefined,'mechanic-downloads'),check=node('button','Check source and settings','button secondary'),run=node('button','Run Evaluation and Funded','button primary');check.type=run.type='button';check.id='prop-sim-check';run.id='prop-sim-run';run.disabled=true;buttons.append(check,run);form.append(buttons);
      const notice=node('p');notice.id='prop-sim-status';notice.setAttribute('role','status');form.append(notice);
      const help=node('p',defaults.disclosure,'field-help');host.append(help);
      const historyLabel=node('label','Saved prop simulations'),historySelect=node('select');historySelect.id='prop-sim-history';historySelect.add(new Option('Choose saved results',''));
      for(const old of history.items)historySelect.add(new Option(`${new Date(old.created_at_utc).toLocaleString()} · ${old.qualification.strategy_id} · sizes ${old.configuration.minimum_micros}–${old.configuration.maximum_micros} MNQ`,old.id));historySelect.value=selectedId||'';historyLabel.append(historySelect);host.append(historyLabel);
      historySelect.onchange=()=>{location.hash=historySelect.value?'#prop-sim?analysis='+historySelect.value:'#prop-sim';};
      const results=node('div');results.id='prop-sim-results';host.append(results);
      let checked=false,busy=false,requestId=crypto.randomUUID(),saved;
      const update=()=>{check.disabled=busy||picker.value==='';run.disabled=busy||!checked;};
      function select(){checked=false;sourceInfo.replaceChildren();const item=sources.items[Number(picker.value)];if(picker.value!==''&&item){sourceInfo.append(node('p',`${item.qualification}. IS sizing window ${item.plan.is_start} → ${item.plan.is_end}.`));detail(sourceInfo,'Frozen strategy parameters',item.parameters);const links=node('div',undefined,'mechanic-downloads');link(links,'Open IS source backtest',`#backtests/report/${item.source_backtest_id}`);link(links,'Open campaign and OOS evidence',`#campaigns/workflows/${item.selection.workflow_id.replaceAll('-','')}/oos?job=${item.selection.oos_job_id.replaceAll('-','')}`);sourceInfo.append(links);}update();}
      picker.onchange=select;form.oninput=()=>{checked=false;notice.textContent='Settings changed. Check source and settings before running.';update();};form.onsubmit=e=>e.preventDefault();
      function body(){const source=sources.items[Number(picker.value)];if(picker.value===''||!source)throw Error('Choose one qualified configuration.');const value={request_id:requestId,selections:[source.selection]};
        for(const [name,,type] of names)value[name]=name==='closures'?fields[name].value.split(',').map(s=>s.trim()).filter(Boolean):type==='number'||name==='block_weekdays'?Number(fields[name].value):fields[name].value;return value;}
      check.onclick=async()=>{busy=true;update();notice.textContent='Validating campaign evidence, sizing, costs and native trade risk…';try{const data=await read('/api/prop-sim/check','POST',body());if(alive()){checked=true;notice.textContent=`Source compatible · ${data.phases.evaluation.candidate_search_count} Evaluation sizes and ${data.phases.funded.candidate_search_count} Funded sizes. Both phases use IS only.`;}}catch(error){if(alive()){checked=false;notice.textContent=error.message;}}finally{busy=false;if(alive())update();}};
      run.onclick=async()=>{busy=true;update();notice.textContent='Starting independent Evaluation and Funded jobs…';try{const data=await read('/api/prop-sim','POST',body());if(alive())location.hash='#prop-sim?analysis='+data.id;}catch(error){if(alive())notice.textContent=error.message;}finally{busy=false;if(alive())update();}};
      const phasePanels={};const loaded={};
      function table(parent,phase,report){const c=report.calculations,rows=[...c.candidates].sort((a,b)=>a.manifest.configuration.micros-b.manifest.configuration.micros);
        const summary=node('p');summary.id='prop-sim-'+phase+'-summary';summary.textContent=phase==='evaluation'?`${c.frontier.length} cost/time Pareto sizing points. All nondominated points remain; no combined score or automatic Evaluation winner. ${rows.filter(r=>r.status!=='estimated').length} unresolved/censored sizes: the frontier covers resolved estimates only.`:c.winner?`Best estimated cash size: ${rows.find(r=>r.candidate_id===c.winner).manifest.configuration.micros} MNQ. ${c.near_ties.length} tied/near-tied alternatives. This is a point estimate, not a certified optimum.`:'No Funded winner: inspect infeasible or unresolved candidates below.';parent.append(summary);
        const wrap=node('div',undefined,'optimization-scroll'),t=node('table',undefined,'library-table');t.id='prop-sim-'+phase+'-table';const head=node('tr');
        const labels=phase==='evaluation'?['MNQ size','Status','Pareto frontier','Attempt pass %','Expected acquisition cost · USD','Expected calendar days to funded','P90 calendar days','Expected attempts','Details']:['MNQ size','Status','Rank','Expected trader receipts · USD','Median receipts','P10 receipts','Breach %','Inactivity %','First payout %','Pending cash','Account deductions','Details'];for(const text of labels)head.append(node('th',text));const th=node('thead');th.append(head);t.append(th);const tb=node('tbody');
        for(const row of rows){const tr=node('tr');tr.dataset.size=row.manifest.configuration.micros;const m=row.metrics;
          const values=phase==='evaluation'?[row.manifest.configuration.micros,row.status,row.pareto_member?'Yes':'No',pct(m.pass_probability),fmt(m.cost_per_funded),fmt(m.expected_calendar_days_to_funded),fmt(m.p90_calendar_days_to_funded),fmt(m.expected_attempts_per_funded)]:[row.manifest.configuration.micros,row.feasible?'Eligible':row.status==='unresolved'?'Unresolved':'Constraint failed',row.rank??'—',fmt(m.expected_funded_cash_payouts_within_horizon),fmt(m.median_payouts),fmt(m.p10_payouts),pct(m.account_breach_probability),pct(m.probability_inactivity),pct(m.probability_first_payout),fmt(m.expected_pending_cash),fmt(m.expected_gross_account_deductions)];
          values.forEach(v=>tr.append(node('td',String(v))));const td=node('td');detail(td,'Measurements and assumptions',{metrics:m,uncertainty:row.uncertainty,censoring:row.censoring,reason:row.reason,constraint_violations:row.constraint_violations,assumptions:row.assumptions,sample_path:row.paths?.[0]});tr.append(td);tb.append(tr);
        }t.append(tb);wrap.append(t);parent.append(wrap);
        const links=node('div',undefined,'mechanic-downloads');for(const [kind,text] of [['results.csv','Results CSV ↓'],['results.json','Calculations JSON ↓'],['report.json','Saved report JSON ↓'],['analysis.zip','Evidence ZIP ↓'],['source_checks.json','Source checks ↓']])link(links,text,`/api/research-campaigns/${saved.campaign_ids[phase]}/exports/${kind}`);parent.append(links);
      }
      async function refresh(){clearTimeout(timer);try{const current=await read('/api/prop-sim/'+selectedId);if(!alive())return;saved=current;
          for(const phase of ['evaluation','funded']){const job=saved.phases[phase];let panel=phasePanels[phase];if(!panel){panel=node('section',undefined,'panel broad-panel');panel.id='prop-sim-'+phase+'-results';panel.append(node('h2',phase==='evaluation'?'Evaluation · acquisition cost/time frontier':'Funded · independent cash-receipt sizing'));const state=node('p');state.id='prop-sim-'+phase+'-progress';state.setAttribute('role','status');panel.append(state);results.append(panel);phasePanels[phase]=panel;}
            panel.querySelector('[role=status]').textContent=`${job.status.toUpperCase()} · ${job.progress||'Ready'}${job.error?' · '+job.error:''}`;
            if(job.analysis_id){let links=panel.querySelector('.prop-sim-job-link');if(!links){links=node('div',undefined,'mechanic-downloads prop-sim-job-link');panel.append(links);}links.replaceChildren();link(links,'Job history / progress',`#jobs/prop_analysis/${job.analysis_id}`);}
            if(job.status==='complete'&&loaded[phase]!==job.analysis_id){const report=await read(`/api/prop-sim/${selectedId}/results/${phase}`);if(!alive())return;table(panel,phase,report);loaded[phase]=job.analysis_id;}
          }
          let controls=results.querySelector('#prop-sim-job-controls');if(!controls){controls=node('div',undefined,'mechanic-downloads');controls.id='prop-sim-job-controls';results.prepend(controls);}controls.replaceChildren();
          const active=Object.values(saved.phases).some(p=>['queued','running'].includes(p.status));
          if(active){const stop=node('button','Stop running analyses','button secondary');stop.type='button';stop.id='prop-sim-stop';stop.onclick=async()=>{stop.disabled=true;try{await read('/api/prop-sim/'+selectedId+'/cancel','POST');if(alive())await refresh();}catch(error){if(alive())notice.textContent=error.message;}};controls.append(stop);timer=setTimeout(refresh,2500);}
          else if(Object.values(saved.phases).some(p=>p.status!=='complete')){const retry=node('button','Retry incomplete phases','button secondary');retry.type='button';retry.onclick=async()=>{try{await read('/api/prop-sim','POST',saved.configuration);if(alive())await refresh();}catch(error){if(alive())notice.textContent=error.message;}};controls.append(retry);}
        }catch(error){if(alive())notice.textContent=error.message;}}
      if(selectedId){await refresh();if(!alive())return;if(saved){const index=sources.items.findIndex(s=>JSON.stringify(s.selection)===JSON.stringify(saved.configuration.selections[0]));if(index>=0)picker.value=String(index);for(const [name] of names)fields[name].value=name==='closures'?saved.configuration[name].join(','):String(saved.configuration[name]);select();}}
      else if(sourceId){const index=sources.items.findIndex(s=>[s.source_backtest_id,s.oos_report_id].includes(sourceId));if(index>=0){picker.value=String(index);select();}else{notice.textContent='This backtest has no currently qualified configuration. Complete all campaign phases and Monte Carlo before selecting it.';update();}}
      else update();
    }catch(error){if(alive())host.replaceChildren(node('p',error.message));}
  }
  window.addEventListener('hashchange',render);render();
})();
