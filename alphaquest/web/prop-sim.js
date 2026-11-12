"use strict";
(() => {
  const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
  const fmt=v=>v==null?'Unavailable':Number(v).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
  const pct=v=>v==null?'Unavailable':fmt(Number(v)*100)+'%';
  const read=async(url,method='GET',body)=>{const r=await fetch(url,{method,cache:'no-store',...(body?{headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})});const value=await r.json();if(!r.ok)throw Error(typeof value.detail==='string'?value.detail:JSON.stringify(value.detail));return value;};
  const link=(parent,text,href)=>{const a=node('a',text,'workflow-inline-link');a.href=href;parent.append(a);};
  const detail=(parent,title,value)=>{const d=node('details');d.append(node('summary',title),node('pre',JSON.stringify(value,null,2)));parent.append(d);return d;};
  const range=(settings,phase)=>({minimum:settings[phase+'_minimum_micros']??settings.minimum_micros,maximum:settings[phase+'_maximum_micros']??settings.maximum_micros});
  function evaluationChart(parent,rows){
    const plotted=rows.filter(r=>r.status==='estimated'&&['cost_per_funded','expected_calendar_days_to_funded'].every(k=>r.metrics[k]!=null&&Number.isFinite(Number(r.metrics[k]))));
    const section=node('section',undefined,'prop-sim-pareto');section.append(node('h3','Evaluation cost/time Pareto curve'));parent.append(section);
    if(!plotted.length){section.append(node('p','No resolved cost/time points are available. Unresolved and censored sizes remain in the table below.'));return;}
    const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.id='prop-sim-evaluation-pareto';svg.setAttribute('viewBox','0 0 900 390');svg.setAttribute('role','group');svg.setAttribute('aria-label','Evaluation Pareto chart: calendar days horizontally, acquisition cost vertically; lower and left is better.');svg.dataset.candidateCount=plotted.length;
    const draw=(tag,attrs,text)=>{const item=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs))item.setAttribute(k,String(v));if(text!==undefined)item.textContent=text;svg.append(item);return item;};
    draw('rect',{width:900,height:390,fill:'#fff'});draw('title',{},'Evaluation cost/time Pareto curve');
    const groups=new Map();for(const row of plotted){const x=Number(row.metrics.expected_calendar_days_to_funded),y=Number(row.metrics.cost_per_funded),key=`${x}|${y}`;if(!groups.has(key))groups.set(key,{x,y,rows:[]});groups.get(key).rows.push(row);}
    const points=[...groups.values()],frontier=points.filter(p=>p.rows.some(r=>r.pareto_member)).sort((a,b)=>a.x-b.x||a.y-b.y);
    const xmax=Math.max(1,...points.map(p=>p.x))*1.1,ymax=Math.max(1,...points.map(p=>p.y))*1.1;
    const x=v=>115+755*v/xmax,y=v=>315-280*v/ymax;
    for(let i=0;i<=4;i++){const xv=xmax*i/4,yv=ymax*i/4;
      draw('line',{x1:x(xv),x2:x(xv),y1:35,y2:315,stroke:'#e3e9ed'});draw('line',{x1:115,x2:870,y1:y(yv),y2:y(yv),stroke:'#e3e9ed'});
      draw('text',{x:x(xv),y:338,'text-anchor':'middle',fill:'#52616c','font-size':12},fmt(xv));draw('text',{x:102,y:y(yv)+4,'text-anchor':'end',fill:'#52616c','font-size':12},fmt(yv));
    }
    draw('line',{x1:115,x2:870,y1:315,y2:315,stroke:'#52616c'});draw('line',{x1:115,x2:115,y1:35,y2:315,stroke:'#52616c'});
    draw('text',{x:490,y:377,'text-anchor':'middle',fill:'#21313b','font-size':14},'Expected calendar days to Funded');draw('text',{x:22,y:180,transform:'rotate(-90 22 180)','text-anchor':'middle',fill:'#21313b','font-size':14},'Expected acquisition cost · USD');
    if(frontier.length>1)draw('polyline',{points:frontier.map(p=>`${x(p.x)},${y(p.y)}`).join(' '),fill:'none',stroke:'#007f73','stroke-width':3,'data-frontier':'true'});
    section.append(node('p','Green = Pareto frontier; grey = other resolved sizes. Lower and left is better.','field-help'));
    const readout=node('p','Hover, focus or click a point to inspect its sizes.','field-help');readout.id='prop-sim-pareto-readout';readout.setAttribute('aria-live','polite');
    for(const point of points){const sizes=point.rows.map(r=>r.manifest.configuration.micros),onFrontier=point.rows.some(r=>r.pareto_member),label=`${sizes.join(', ')} MNQ · ${fmt(point.x)} calendar days · $${fmt(point.y)} acquisition cost · ${onFrontier?'Pareto frontier':'outside frontier'}`;
      const circle=draw('circle',{cx:x(point.x),cy:y(point.y),r:onFrontier?7:5,fill:onFrontier?'#007f73':'#7b8b96',stroke:'#fff','stroke-width':2,tabindex:0,role:'button','aria-label':label,'data-sizes':sizes.join(','),'data-pareto':onFrontier});
      const title=document.createElementNS(ns,'title');title.textContent=label;circle.append(title);
      const inspect=()=>{readout.textContent=label;parent.querySelectorAll('tbody tr').forEach(row=>row.classList.toggle('prop-sim-chart-highlight',sizes.includes(Number(row.dataset.size))));};
      circle.onmouseenter=circle.onfocus=circle.onclick=inspect;circle.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();inspect();}};
      if(onFrontier){const right=x(point.x)>700;draw('text',{x:x(point.x)+(right?-11:11),y:y(point.y)-12,'text-anchor':right?'end':'start',fill:'#00685e','font-size':12},sizes.length<=3?`${sizes.join(', ')} MNQ`:`${sizes[0]} + ${sizes.length-1} sizes`);}
    }
    const wrap=node('div',undefined,'optimization-scroll');wrap.append(svg);section.append(wrap,readout,node('p',`Shows ${plotted.length} resolved sizes. ${rows.length-plotted.length} unresolved/censored sizes are excluded from the plot. ${frontier.length===1?'The frontier has one distinct point; tied sizes can share it.':'The line connects tested frontier points; intermediate sizes are not inferred.'} These are point estimates, not certified dominance.`,'field-help'));
    const download=node('a','Pareto chart SVG ↓','workflow-inline-link');download.download='evaluation-pareto.svg';download.href='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(new XMLSerializer().serializeToString(svg));section.append(download);
  }
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
      form.append(node('p',`Evaluation supports up to ${defaults.size_limits.evaluation} MNQ; Funded supports up to ${defaults.size_limits.funded} MNQ, subject to its account scaling tiers. Configure each range independently.`,'field-help'));
      const grid=node('div',undefined,'prop-sim-settings');form.append(grid);const fields={};
      const names=[['evaluation_minimum_micros','Evaluation minimum size · MNQ','number'],['evaluation_maximum_micros','Evaluation maximum size · MNQ','number'],['funded_minimum_micros','Funded minimum size · MNQ','number'],['funded_maximum_micros','Funded maximum size · MNQ','number'],['simulations','Simulated paths per size, per phase','number'],['seed','Random seed','number'],['block_weekdays','History block length · weekdays','select'],['evaluation_price','Evaluation purchase fee · USD','text'],['activation_fee','Activation fee · USD','text'],['commission_per_mnq_side','MNQ commission per contract per side · USD','text'],['start_date','Scenario start date · America/Chicago','date'],['funded_horizon_calendar_days','Funded horizon · calendar days','number'],['receipt_delay_calendar_days','Payout receipt delay · calendar days','number'],['maximum_funded_breach_probability','Optional Funded breach cap · 0 to 1','number'],['closures','Full-session closures · comma-separated YYYY-MM-DD','text']];
      for(const [name,text,type] of names){const label=node('label',text),input=node(type==='select'?'select':'input');input.id='prop-sim-'+name;fields[name]=input;
        if(type==='select'){for(const n of [1,5,10])input.add(new Option(String(n),String(n)));}else input.type=type;
        if(type==='number'){input.step=name==='maximum_funded_breach_probability'?'.01':'1';input.min='0';}
        if(name.endsWith('_micros')){input.min='1';input.max=String(defaults.size_limits[name.split('_')[0]]);}
        input.value=name==='start_date'?new Date().toLocaleDateString('en-CA',{timeZone:'America/Chicago'}):name==='closures'?'':String(defaults.defaults[name]??'');
        if(name==='maximum_funded_breach_probability'){input.max='1';input.placeholder='No cap';const help=node('span','Blank = no eligibility cap. A value of 0.25 caps drawdown-breach probability at 25% within the Funded horizon, not the historical IS period.','field-help');help.id='prop-sim-breach-help';input.setAttribute('aria-describedby',help.id);label.append(help);}
        label.append(input);grid.append(label);
      }
      form.append(node('p','Funded ranks expected cash received over the chosen horizon. Breach risk remains visible and already reduces cash when accounts stop; its additional eligibility cap is optional and off by default.','field-help'));
      detail(form,'Account rules, source assumptions and interpretation',{evaluation:defaults.evaluation_rules,funded:defaults.funded_rules,rule_provenance:defaults.rule_provenance,disclosure:defaults.disclosure});
      form.append(node('p','The preserved local model uses 21-session expiry/inactivity clocks and permits exactly 50% funded consistency. Published calendar-day/boundary rules differ; inspect the rule provenance above before relying on account outcomes.','field-help'));
      form.append(node('p','Fees are editable scenario inputs. Receipt timing and the weekday/closure calendar are assumptions. Position sizes use MNQ units: 10 MNQ equals one NQ in point exposure. Costs replace the source commission; they are not charged twice.','field-help'));
      const buttons=node('div',undefined,'mechanic-downloads'),check=node('button','Check source and settings','button secondary'),run=node('button','Run Evaluation and Funded','button primary');check.type=run.type='button';check.id='prop-sim-check';run.id='prop-sim-run';run.disabled=true;buttons.append(check,run);form.append(buttons);
      const notice=node('p');notice.id='prop-sim-status';notice.setAttribute('role','status');form.append(notice);
      const help=node('p',defaults.disclosure,'field-help');host.append(help);
      const historyLabel=node('label','Saved prop simulations'),historySelect=node('select');historySelect.id='prop-sim-history';historySelect.add(new Option('Choose saved results',''));
      for(const old of history.items){const e=range(old.configuration,'evaluation'),f=range(old.configuration,'funded');historySelect.add(new Option(`${new Date(old.created_at_utc).toLocaleString()} · ${old.qualification.strategy_id} · Evaluation ${e.minimum}–${e.maximum} / Funded ${f.minimum}–${f.maximum} MNQ`,old.id));}historySelect.value=selectedId||'';historyLabel.append(historySelect);host.append(historyLabel);
      historySelect.onchange=()=>{location.hash=historySelect.value?'#prop-sim?analysis='+historySelect.value:'#prop-sim';};
      const results=node('div');results.id='prop-sim-results';host.append(results);
      let checked=false,busy=false,requestId=crypto.randomUUID(),saved;
      const update=()=>{check.disabled=busy||picker.value==='';run.disabled=busy||!checked;};
      function select(){checked=false;sourceInfo.replaceChildren();const item=sources.items[Number(picker.value)];if(picker.value!==''&&item){sourceInfo.append(node('p',`${item.qualification}. IS sizing window ${item.plan.is_start} → ${item.plan.is_end}.`));detail(sourceInfo,'Frozen strategy parameters',item.parameters);const links=node('div',undefined,'mechanic-downloads');link(links,'Open IS source backtest',`#backtests/report/${item.source_backtest_id}`);link(links,'Open campaign and OOS evidence',`#campaigns/workflows/${item.selection.workflow_id.replaceAll('-','')}/oos?job=${item.selection.oos_job_id.replaceAll('-','')}`);sourceInfo.append(links);}update();}
      picker.onchange=select;form.oninput=()=>{checked=false;notice.textContent='Settings changed. Check source and settings before running.';update();};form.onsubmit=e=>e.preventDefault();
      function body(){const source=sources.items[Number(picker.value)];if(picker.value===''||!source)throw Error('Choose one qualified configuration.');const value={request_id:requestId,selections:[source.selection]};
        for(const [name,,type] of names)value[name]=name==='maximum_funded_breach_probability'&&fields[name].value.trim()===''?null:name==='closures'?fields[name].value.split(',').map(s=>s.trim()).filter(Boolean):type==='number'||name==='block_weekdays'?Number(fields[name].value):fields[name].value;return value;}
      check.onclick=async()=>{if(!form.reportValidity())return;busy=true;update();notice.textContent='Validating campaign evidence, sizing, costs and native trade risk…';try{const data=await read('/api/prop-sim/check','POST',body());if(alive()){checked=true;notice.textContent=`Source compatible · ${data.phases.evaluation.candidate_search_count} Evaluation sizes and ${data.phases.funded.candidate_search_count} Funded sizes. Both phases use IS only.`;}}catch(error){if(alive()){checked=false;notice.textContent=error.message;}}finally{busy=false;if(alive())update();}};
      run.onclick=async()=>{busy=true;update();notice.textContent='Starting independent Evaluation and Funded jobs…';try{const data=await read('/api/prop-sim','POST',body());if(alive())location.hash='#prop-sim?analysis='+data.id;}catch(error){if(alive())notice.textContent=error.message;}finally{busy=false;if(alive())update();}};
      const phasePanels={};const loaded={};
      function table(parent,phase,report){const c=report.calculations,rows=[...c.candidates].sort((a,b)=>a.manifest.configuration.micros-b.manifest.configuration.micros);
        const summary=node('p');summary.id='prop-sim-'+phase+'-summary';summary.textContent=phase==='evaluation'?`${c.frontier.length} cost/time Pareto sizing points. All nondominated points remain; no combined score or automatic Evaluation winner. ${rows.filter(r=>r.status!=='estimated').length} unresolved/censored sizes: the frontier covers resolved estimates only.`:c.winner?`Best estimated cash size: ${rows.find(r=>r.candidate_id===c.winner).manifest.configuration.micros} MNQ. ${c.near_ties.length} tied/near-tied alternatives. This is a point estimate, not a certified optimum.`:'No Funded winner: inspect infeasible or unresolved candidates below.';parent.append(summary);
        if(phase==='evaluation')evaluationChart(parent,rows);
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
      if(selectedId){await refresh();if(!alive())return;if(saved){const index=sources.items.findIndex(s=>JSON.stringify(s.selection)===JSON.stringify(saved.configuration.selections[0]));if(index>=0)picker.value=String(index);for(const [name] of names){const value=name.endsWith('_micros')?range(saved.configuration,name.split('_')[0])[name.includes('_minimum_')?'minimum':'maximum']:saved.configuration[name];fields[name].value=name==='closures'?value.join(','):String(value??'');}select();}}
      else if(sourceId){const index=sources.items.findIndex(s=>[s.source_backtest_id,s.oos_report_id].includes(sourceId));if(index>=0){picker.value=String(index);select();}else{notice.textContent='This backtest has no currently qualified configuration. Complete all campaign phases and Monte Carlo before selecting it.';update();}}
      else update();
    }catch(error){if(alive())host.replaceChildren(node('p',error.message));}
  }
  window.addEventListener('hashchange',render);render();
})();
