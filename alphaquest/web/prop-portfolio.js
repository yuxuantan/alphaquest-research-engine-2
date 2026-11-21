"use strict";
(() => {
  const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
  const money=v=>Number(v??0).toLocaleString('en-US',{style:'currency',currency:'USD'});
  const phases=['evaluation','funded'];
  const sizeLabel=p=>p.kind==='percentage_risk'?p.risk_percent+'%':p.kind==='fixed_dollar_risk'?money(p.risk_dollars):p.contracts+' MNQ';
  const sourceName=s=>s.strategy_id.replaceAll('_',' ')+` · Broad ${s.broad_trial} / Narrow ${s.narrow_trial}`;
  function tableOf(headers,rows){
    const table=node('table',undefined,'library-table'),head=node('thead'),top=node('tr'),body=node('tbody');
    for(const label of headers){const th=node('th',label);th.scope='col';top.append(th);}
    head.append(top);table.append(head,body);
    for(const values of rows){const row=node('tr');for(const value of values)row.append(node('td',value));body.append(row);}
    const wrap=node('div',undefined,'optimization-scroll');wrap.append(table);return wrap;
  }
  const read=async(url,method='GET',body)=>{const r=await window.portalLoading.fetch(url,{method,cache:'no-store',...(body?{headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})});const value=await r.json();if(!r.ok)throw Error(typeof value.detail==='string'?value.detail:JSON.stringify(value.detail));return value;};
  const link=(p,text,href)=>{const a=node('a',text,'workflow-inline-link');a.href=href;p.append(a);};
  let generation=0,timer;
  window.propPortfolio={async render(host,saved=null){
    const turn=++generation;clearTimeout(timer);const alive=()=>turn===generation&&location.hash.startsWith('#prop-sim');
    host.replaceChildren();const head=node('section',undefined,'panel prop-portfolio-panel');head.append(node('h2','Portfolio allocation & replacement cash flow'));
    host.append(head);
    if(saved){
      link(head,'New portfolio analysis','#prop-sim?mode=portfolio');const windows=saved.portfolio.windows;head.append(node('p',`${saved.configuration.profile_id==='lucidflex-50k'?'LucidFlex 50K':'Apex 50K EOD'} · IS ${windows.is.start} → ${windows.is.end} · OOS ${windows.oos.start} → ${windows.oos.end}`,'field-help'));const body=node('section',undefined,'panel prop-portfolio-panel'),state=node('p');state.id='portfolio-status';state.setAttribute('role','status');body.append(state);host.append(body);
      const progress=node('progress'),jobLink=node('a','Open job details','workflow-inline-link');
      progress.hidden=true;progress.setAttribute('aria-label','Portfolio plans completed');
      body.append(progress,jobLink);
      const remove=node('button','Delete saved simulation','button danger');remove.type='button';head.append(remove);
      remove.onclick=async()=>{remove.disabled=true;try{const plan=await read('/api/prop-sim/'+saved.id+'/deletion');if(!plan.deletable)throw Error('Stop running jobs before deleting this simulation. Protected reports are retained.');if(!confirm(`Delete this saved simulation and ${plan.analysis_ids_to_delete.length} unshared reports? Source datasets, backtests and campaign results are kept.`))return;await read('/api/prop-sim/'+saved.id,'DELETE',{confirmation_sha256:plan.confirmation_sha256});location.hash='#prop-sim?deleted='+saved.id;}catch(e){state.textContent=e.message;}finally{remove.disabled=false;}};
      let loaded=false;
      async function refresh(){
        if(!alive())return;
        try{
          const current=await read('/api/prop-sim/'+saved.id);if(!alive())return;
          const job=current.portfolio.job,summary=`${job.status.toUpperCase()} · ${job.progress}${job.error?' · '+job.error:''}`;
          if(state.textContent!==summary)state.textContent=summary;
          jobLink.href='#jobs/prop_analysis/'+job.id;
          const count=job.progress?.match(/Portfolio IS search · (\d+)\/(\d+) plans/);
          progress.hidden=job.status!=='running'||!count;
          if(count){progress.max=Number(count[2]);progress.value=Number(count[1]);}
          if(['queued','running'].includes(job.status)){body.querySelector('#portfolio-retry')?.remove();
            let stop=body.querySelector('#portfolio-stop');if(!stop){stop=node('button','Stop analysis','button secondary');stop.id='portfolio-stop';stop.onclick=async()=>{stop.disabled=true;try{await read('/api/prop-sim/'+saved.id+'/cancel','POST');await refresh();}catch(e){state.textContent=e.message;stop.disabled=false;}};body.append(stop);}
            timer=setTimeout(refresh,2000);return;
          }
          body.querySelector('#portfolio-stop')?.remove();
          if(job.status!=='complete'){if(!body.querySelector('#portfolio-retry')){const retry=node('button','Retry this saved configuration','button secondary');retry.id='portfolio-retry';retry.onclick=async()=>{retry.disabled=true;try{await read('/api/prop-sim/portfolio','POST',saved.portfolio.request);refresh();}catch(e){state.textContent=e.message;retry.disabled=false;}};body.append(retry);}return;}if(loaded)return;
          const report=await read('/api/prop-sim/portfolio/'+saved.id+'/results');if(!alive())return;loaded=true;
          const r=report.results,f=report.frozen,a=f.allocation,empty=a.placement==='separate'&&a.counts.every(n=>!n);
          body.append(node('h3',empty?'IS selected no account purchases':Number(r.oos.cash.net_cash)>0?'Positive observed OOS cash flow':'OOS receipts did not cover fees'));
          const cards=node('div',undefined,'prop-portfolio-metrics');
          for(const [name,title,note] of [['is','IS selection','Used to choose the allocation'],['oos','OOS · fresh start','Same allocation, starting unfunded'],['combined','Full period','Carries open accounts through the IS/OOS boundary']]){
            const c=r[name].cash,card=node('section',undefined,'prop-sim-insight');card.append(node('span',title,'pill neutral'),node('h3',money(c.net_cash)),node('p',`${money(c.received_trader_cash)} received − ${money(c.paid_fees)} fees`),node('small',note));cards.append(card);
          }body.append(cards);if(empty)body.append(node('p','The zero-purchase plan ranked first on IS. Open the tested plans to review the best invested alternative.','field-help'));
          const coverage=report.source_coverage;
          if(coverage?.affected_sessions){
            const note=node('section',undefined,'prop-sim-insight');
            note.append(node('h3','Missing bars in the source'),
              node('p',`${coverage.missing_holding_minutes} missing tradable minutes across ${coverage.affected_sessions} sessions in the possible holding window. Replay continued at the next observed bar. Fills and account breaches inside the gaps are unknown.`),
              node('p',`The full-period frozen allocation encountered ${coverage.exposed_account_encounters} gaps across accounts with a position open or an entry pending.`,'field-help'));
            link(note,'Download source coverage','/api/prop-analyses/'+report.id+'/files/source_checks.json');body.append(note);
          }
          const allocation=node('section');allocation.id='portfolio-allocation';allocation.append(node('h3',f.search?'Frozen sizes and account allocation':'Frozen allocation'));
          const names=saved.portfolio_sources.map(sourceName);
          if(f.search){
            const method=f.search.method==='full_grid'?'Full grid':'Best tested plan';
            allocation.append(node('p',`${method} · ${f.search.tested.toLocaleString()} of ${f.search.grid_size.toLocaleString()} IS plans tested. OOS used these same choices.`,'field-help'));
            const values=names.map((name,i)=>{
              const sizing=a.sizing[i];
              return [name,sizing?(a.placement==='separate'?String(a.counts[i]):`Shared × ${a.accounts}`):'Excluded',
                ...phases.map(phase=>sizing?sizeLabel(sizing[phase]):'—')];
            });
            allocation.append(tableOf(['Configuration','Accounts','Evaluation size','Funded size'],values));
            const policy=a.sizing.find(Boolean)?.evaluation;
            if(policy?.kind==='percentage_risk')allocation.append(node('p',`Planned risk per trade based on ${policy.reference.replaceAll('_',' ')}. Filled MNQ quantity varies with the stop distance.`,'field-help'));
          }else{
            if(a.placement==='separate')a.counts.forEach((count,i)=>allocation.append(node('p',`${count} ${count===1?'account':'accounts'} · ${names[i]}`)));
            else{allocation.append(node('p',`${a.accounts} shared ${a.accounts===1?'account':'accounts'}`));a.weights.forEach((weight,i)=>allocation.append(node('p',`${25*weight}% risk share · ${names[i]}`)));}
            for(const phase of phases)allocation.append(node('p',`${phase==='evaluation'?'Evaluation':'Funded'} base size · ${sizeLabel(f[phase+'_sizing'])}`));
          }
          allocation.append(node('p',`Monthly fee ceiling of ${money(f.monthly_cap)}`,'field-help'));
          body.append(allocation);
          const totals=r.combined,counts=totals.counts;body.append(node('h3','What drove the cash result'),node('p',`${counts.evaluation_attempts} evaluations purchased · ${counts.funded_accounts} Funded accounts started · ${counts.funded_breaches} Funded breaches · ${counts.funded_inactivity_closures||0} inactivity closures · ${counts.funded_payout_completions} payout-limit completions.`),node('p',`${money(totals.cash.pending_receipts)} in pending receipts is excluded from net cash. ${money(totals.cash.outstanding_activation_reservations)} remains reserved for activation.`));
          const table=node('table',undefined,'library-table');table.id='portfolio-yearly-cash';const tr=node('tr');['Year','Received cash','Paid fees','Net cash'].forEach(x=>tr.append(node('th',x)));const th=node('thead');th.append(tr);table.append(th);const years={};
          for(const m of totals.cash.monthly){const y=m.month.slice(0,4);years[y]??={received:0,fees:0};years[y].received+=Number(m.trader_receipts);years[y].fees+=Number(m.paid_fees);}
          const tb=node('tbody');for(const [year,c] of Object.entries(years)){const tr=node('tr');[year,money(c.received),money(c.fees),money(c.received-c.fees)].forEach(v=>tr.append(node('td',v)));tb.append(tr);}table.append(tb);const wrap=node('div',undefined,'optimization-scroll');wrap.append(table);body.append(wrap);
          const comparison=node('details');comparison.append(node('summary','Compare tested IS plans'));
          for(const placement of ['separate','shared']){const rows=report.allocation_search.filter(r=>r.allocation.placement===placement);if(rows.length){const best=rows.reduce((a,b)=>Number(a.cash.net_cash)>=Number(b.cash.net_cash)?a:b);comparison.append(node('p',`${placement==='shared'?'Shared accounts':'Separate accounts'} · best observed IS net ${money(best.cash.net_cash)} · ${rows.length} allocations tested`));}}
          if(report.abstention_alternative){const alt=report.abstention_alternative;comparison.append(node('p',`Best invested alternative returned ${money(alt.cash.net_cash)} after fees on IS.`));for(const file of ['is_alternative_sizing_decisions.csv','is_alternative_cash_ledger.csv'])link(comparison,file+' ↓','/api/prop-analyses/'+report.id+'/files/'+file);}
          const ranked=[...report.allocation_search].sort((x,y)=>Number(y.cash.net_cash)-Number(x.cash.net_cash));
          comparison.append(tableOf(['Account placement','Evaluation / Funded per strategy','IS net cash'],
            ranked.slice(0,10).map(({allocation,cash})=>[
              allocation.placement==='shared'?`${allocation.accounts} shared`:`${allocation.counts.reduce((x,y)=>x+y,0)} separate`,
              allocation.sizing?.map((s,i)=>s?`${names[i]} · ${sizeLabel(s.evaluation)} / ${sizeLabel(s.funded)}`:null).filter(Boolean).join(' | ')||'—',
              money(cash.net_cash)
            ])));
          link(comparison,'Download all tested plans','/api/prop-analyses/'+report.id+'/files/allocation_results.json');body.append(comparison);
          const downloads=node('div',undefined,'mechanic-downloads');for(const [name,label] of [['combined_cash_ledger.csv','Full cash ledger CSV ↓'],['portfolio_frozen.json','Frozen allocation and policies ↓'],['analysis.zip','Evidence ZIP ↓']])link(downloads,label,'/api/prop-analyses/'+report.id+(name==='analysis.zip'?'/downloads/':'/files/')+name);body.append(downloads);
          const evidence=node('details');evidence.append(node('summary','Execution, sizing decisions and assumptions'));for(const name of ['combined_trades.csv','combined_sizing_decisions.csv','combined_transitions.csv','oos_cash_ledger.csv','allocation_results.json','source_checks.json'])link(evidence,name+' ↓','/api/prop-analyses/'+report.id+'/files/'+name);for(const text of report.assumptions)evidence.append(node('p',text,'field-help'));body.append(evidence);
        }catch(e){if(alive())state.textContent=e.message;}
      }await refresh();return;
    }
    const loading=node('p','Checking qualified configurations…','field-help');
    const spinner=node('span',undefined,'portal-spinner');spinner.setAttribute('aria-hidden','true');
    loading.prepend(spinner,' ');
    loading.setAttribute('role','status');head.append(loading);
    let sources,defaults,history;
    try{
      [sources,defaults,history]=await Promise.all([read('/api/prop-sim/portfolio/candidates'),read('/api/prop-sim/defaults'),read('/api/prop-sim')]);
    }catch(error){
      if(alive()){loading.textContent='Could not load Portfolio settings. '+error.message;
        const retry=node('button','Try again','button secondary');retry.onclick=()=>window.propPortfolio.render(host);head.append(retry);}
      return;
    }
    if(!alive())return;
    loading.remove();
    const form=node('form',undefined,'panel prop-portfolio-panel');form.id='portfolio-form';host.append(form);
    const choices=node('fieldset',undefined,'portfolio-picks');
    choices.append(node('legend','Strategies to compare'),node('p','Choose up to four configurations from the same dataset. Shared-account signal ties follow the order shown.','field-help'));
    const picks=sources.items.map((source,index)=>{
      const label=node('label',undefined,'portfolio-pick'),input=node('input'),copy=node('span'),reason=node('small');
      input.type='checkbox';input.id='portfolio-source-'+index;input.className='portfolio-source';
      reason.id=input.id+'-reason';input.setAttribute('aria-describedby',reason.id);
      copy.append(node('strong',sourceName(source)),node('small',source.dataset.name),reason);
      if(source.portfolio_parity)copy.append(node('small','Replay parity verified against the qualified campaign.'));
      label.append(input,copy);choices.append(label);
      if(source.portfolio_ineligible_reason?.includes('current strategy implementation'))
        link(choices,'View saved campaign',
          '#campaigns/workflows/'+source.selection.workflow_id.replaceAll('-','')+'/oos');
      return {input,source,reason};
    });
    if(!picks.length)choices.append(node('p','No campaign configurations have qualified for Prop Sim yet.'));
    form.append(choices);
    const grid=node('div',undefined,'prop-sim-settings');form.append(node('h3','Account and budget'),grid);
    const fields={};
    function field(name,label,type,value,options,parent=grid){
      const l=node('label',label),input=node(options?'select':'input');input.id='portfolio-'+name;
      if(options)for(const [v,text] of options)input.append(new Option(text,v));
      else{input.type=type;if(type==='number')input.step='any';}
      input.value=String(value);fields[name]=input;l.append(input);parent.append(l);return input;
    }
    field('profile_id','Prop account','select','lucidflex-50k',Object.entries(defaults.profiles).map(([id,p])=>[id,p.name]));
    field('monthly_cap','Monthly Evaluation + activation fee ceiling · USD','number',500).min='0';
    field('maximum_accounts','Maximum concurrent accounts','number',2).min='1';fields.maximum_accounts.max='4';
    field('placement','Account placement','select','both',[['both','Compare separate and shared'],['separate','Separate accounts'],['shared','Shared account · one open trade at a time']]);
    const method=node('div',undefined,'prop-sim-settings');
    form.append(node('h3','Sizing search'),node('p','Each strategy gets its own Evaluation and Funded size from these ranges. The search ranks plans by cash received after fees on IS.','field-help'),method);
    field('sizing_kind','Trade sizing','select','percentage_risk',[['percentage_risk','Percentage at risk'],['fixed_contracts','Fixed contracts']],method);
    field('reference','Percentage risk basis','select','initial_configured_capital',[['initial_configured_capital','Initial prop capital · $50,000'],['current_account_balance','Current prop account balance'],['available_drawdown_cushion','Remaining drawdown cushion']],method);
    const ranges=node('div',undefined,'portfolio-ranges');
    for(const phase of phases){
      const box=node('fieldset'),inputs=node('div',undefined,'portfolio-range-inputs');
      box.append(node('legend',phase==='evaluation'?'Evaluation':'Funded'),inputs);ranges.append(box);
      for(const [name,label,value] of [['minimum','Minimum','0.1'],['maximum','Maximum','0.3'],['step','Step','0.1'],['cap','MNQ ceiling','40']]){
        const input=field(phase+'_'+name,label,'number',value,null,inputs);input.required=true;
      }
    }
    form.append(ranges);
    const workload=node('p',undefined,'portfolio-workload');workload.id='portfolio-workload';workload.setAttribute('aria-live','polite');form.append(workload);
    const advanced=node('details');advanced.append(node('summary','Fees, settlement and historical windows'));const advancedGrid=node('div',undefined,'prop-sim-settings');advanced.append(advancedGrid);form.append(advanced);
    const ruleInfo=node('p',defaults.profiles[fields.profile_id.value].notes,'field-help');advanced.append(ruleInfo);const secondary=(name,label,type,value)=>field(name,label,type,value,null,advancedGrid);
    const consistency=secondary('evaluation_consistency_percent','LucidFlex Evaluation consistency · %','number',40);consistency.min='40';consistency.max='50';consistency.step='10';secondary('evaluation_price','Evaluation purchase fee · USD','number','80.50').step='.01';secondary('activation_fee','Activation fee · USD','number',0).step='.01';secondary('commission_per_mnq_side','MNQ commission per side · USD','number','.50').step='.01';secondary('receipt_delay_calendar_days','Receipt delay · calendar days','number',2);
    for(const role of ['is','oos'])for(const bound of ['start','end'])secondary(role+'_'+bound,role.toUpperCase()+' '+bound+' · blank uses common qualified coverage','date','');
    const effort=secondary('replay_budget','Maximum IS replays','number',24);
    effort.min='8';effort.max='128';effort.step='1';effort.required=true;
    const status=node('p');status.id='portfolio-form-status';status.setAttribute('role','status');
    const run=node('button','Run portfolio search','button primary');run.type='submit';run.id='portfolio-run';
    form.append(run,status);
    const chosen=()=>picks.filter(p=>p.input.checked);
    const isFixed=()=>fields.sizing_kind.value==='fixed_contracts';
    const limits=()=>defaults.profiles[fields.profile_id.value].size_limits;
    const placements=()=>fields.placement.value==='both'?['separate','shared']:[fields.placement.value];
    let busy=false;
    function phaseGrid(phase){
      const keys=['minimum','maximum','step'];
      const raw=keys.map(key=>fields[phase+'_'+key].value);
      const scaled=raw.map(value=>/^(?:\d+(?:\.\d{1,8})?|\.\d{1,8})$/.test(value)?BigInt(Math.round(Number(value)*1e8)):0n);
      const [lo,hi,step]=scaled;
      const cap=Number(fields[phase+'_cap'].value);
      if(!lo||hi<lo||!step||(hi-lo)%step||hi>10000000000n)return null;
      const count=(hi-lo)/step+1n;
      if(count>60n)return null;
      if(isFixed()){
        if(raw.some(value=>!Number.isInteger(Number(value)))||Number(raw[1])>limits()[phase])return null;
      }else if(!Number.isInteger(cap)||cap<1||cap>limits()[phase])return null;
      const grid=Object.fromEntries(keys.map((key,i)=>[key,isFixed()?Number(raw[i]):raw[i]]));
      if(!isFixed())Object.assign(grid,{reference:fields.reference.value,maximum_contracts:cap});
      return {grid,count};
    }
    function choose(n,k){
      let result=1n;for(let i=1;i<=k;i++)result=result*BigInt(n-i+1)/BigInt(i);return result;
    }
    function update(){
      const selected=chosen(),n=selected.length,dataset=selected[0]?.source.dataset.id;
      for(const {input,source,reason} of picks){
        const why=source.portfolio_ineligible_reason||
          (dataset&&source.dataset.id!==dataset?'Uses a different dataset.':!input.checked&&n===4?'Four configurations selected.':'');
        input.disabled=Boolean(why);reason.textContent=why.includes('current strategy implementation')?
          'This saved source predates the current strategy implementation. A new qualified campaign source is required.':why;
      }
      const grids=phases.map(phaseGrid),accountCount=Number(fields.maximum_accounts.value),cap=Number(effort.value);
      const valid=grids.every(Boolean)&&Number.isInteger(accountCount)&&accountCount>=1&&accountCount<=4&&Number.isInteger(cap)&&cap>=8&&cap<=128;
      let count=1n;
      if(n&&valid){
        const axis=grids[0].count*grids[1].count,options=placements();
        for(let k=1;k<=n;k++){
          const layouts=(options.includes('separate')&&k<=accountCount?choose(accountCount,k):0n)
            +(options.includes('shared')&&(k>1||!options.includes('separate'))?BigInt(accountCount):0n);
          count+=choose(n,k)*layouts*axis**BigInt(k);
        }
      }
      workload.textContent=!valid?'Enter positive, aligned sizing ranges and valid account and replay limits.':
        !n?'Select configurations to preview the search.':count<=BigInt(cap)?
          `Full grid · ${count.toLocaleString()} IS plans including the zero-purchase baseline.`:
          `Bounded search · up to ${cap} of ${count.toLocaleString()} IS plans. Results show the best tested plan.`;
      run.disabled=busy||!n||!valid;
    }
    function syncSizing(reset){
      const fixed=isFixed();
      fields.reference.disabled=fixed;fields.reference.parentElement.hidden=fixed;
      for(const phase of phases){
        for(const [name,number,risk] of [['minimum',1,'0.1'],['maximum',5,'0.3'],['step',2,'0.1']]){
          const input=fields[phase+'_'+name];
          if(reset)input.value=fixed?number:risk;
          input.min=fixed?'1':'0.00000001';input.max=fixed?limits()[phase]:100;
          input.step=fixed?'1':'any';
        }
        const ceiling=fields[phase+'_cap'];ceiling.min='1';ceiling.max=limits()[phase];ceiling.step='1';
        ceiling.disabled=fixed;ceiling.parentElement.hidden=fixed;
        fields[phase+'_minimum'].parentElement.firstChild.textContent=fixed?'Minimum MNQ':'Minimum risk %';
        fields[phase+'_maximum'].parentElement.firstChild.textContent=fixed?'Maximum MNQ':'Maximum risk %';
        fields[phase+'_step'].parentElement.firstChild.textContent=fixed?'Step MNQ':'Step %';
      }
      update();
    }
    function syncAccount(){
      const profile=defaults.profiles[fields.profile_id.value];
      ruleInfo.textContent=profile.notes;
      fields.evaluation_consistency_percent.value='40';
      fields.evaluation_consistency_percent.disabled=fields.profile_id.value!=='lucidflex-50k';
      fields.evaluation_price.required=true;
      fields.evaluation_price.value=profile.defaults.evaluation_price;
      fields.activation_fee.value=profile.defaults.activation_fee;
      fields.commission_per_mnq_side.value=profile.defaults.commission_per_mnq_side;
      for(const phase of phases)fields[phase+'_cap'].value=limits()[phase];
      syncSizing(false);
    }
    fields.profile_id.onchange=syncAccount;
    fields.evaluation_consistency_percent.onchange=()=>{
      fields.evaluation_price.value=fields.evaluation_consistency_percent.value==='50'?'':defaults.profiles[fields.profile_id.value].defaults.evaluation_price;
    };
    fields.sizing_kind.onchange=()=>syncSizing(true);
    form.addEventListener('input',update);form.addEventListener('change',update);
    fields.monthly_cap.required=true;fields.maximum_accounts.required=true;fields.maximum_accounts.step='1';
    syncAccount();
    form.onsubmit=async event=>{
      event.preventDefault();
      if(busy||run.disabled||!form.reportValidity())return;
      busy=true;update();run.textContent='Starting…';status.textContent='Checking campaign evidence and queueing the search.';
      const body={request_id:crypto.randomUUID(),selections:chosen().map(p=>p.source.selection),
        profile_id:fields.profile_id.value,placements:placements(),replay_budget:Number(effort.value)};
      for(const key of ['maximum_accounts','evaluation_consistency_percent','receipt_delay_calendar_days'])body[key]=Number(fields[key].value);
      for(const key of ['monthly_cap','evaluation_price','activation_fee','commission_per_mnq_side','is_start','is_end','oos_start','oos_end']){
        if(fields[key].value)body[key]=fields[key].value;
      }
      for(const phase of phases)body[phase+'_grid']=phaseGrid(phase).grid;
      try{
        const result=await read('/api/prop-sim/portfolio','POST',body);
        if(alive())location.hash='#prop-sim?analysis='+result.id;
      }catch(error){
        if(alive())status.textContent=error.message;
      }finally{busy=false;run.textContent='Run portfolio search';update();}
    };
    const previous=history.items.filter(r=>r.configuration.mode==='portfolio');if(previous.length){const list=node('details',undefined,'panel prop-portfolio-panel');list.append(node('summary','Saved portfolio analyses'));for(const item of previous)link(list,new Date(item.created_at_utc).toLocaleString()+' · '+item.configuration.profile_id,'#prop-sim?analysis='+item.id);host.append(list);}
  }};
  window.addEventListener('hashchange',()=>{++generation;clearTimeout(timer);});
})();
