/* Campaign controls live inside the ordinary saved-backtest prop workflow. */
(() => {
  const $ = s => document.querySelector(s);
  const node = (tag, text) => {const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
  const link = (text, href) => {const a=node('a',text);a.href=href;return a;};
  async function api(url, body) {
    const response=await fetch(url,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const result=await response.json();if(!response.ok)throw Error(typeof result.detail==='string'?result.detail:JSON.stringify(result.detail));return result;
  }
  function details(parent,title,value){const d=node('details');d.append(node('summary',title),node('pre',JSON.stringify(value,null,2)));parent.append(d);}
  function field(parent,label,id,value,type='text') {
    const l=node('label',label),i=node('input');i.id=id;i.type=type;i.value=value;i.required=true;l.append(i);parent.append(l);return i;
  }
  function select(parent,label,id,options){const l=node('label',label),s=node('select');s.id=id;for(const [v,t]of options){const o=node('option',t);o.value=v;s.append(o);}l.append(s);parent.append(l);return s;}
  function button(parent,text,id){const b=node('button',text);b.type='button';b.id=id;b.className='button secondary';parent.append(b);return b;}
  function number(id){const v=Number($('#'+id).value);if(!Number.isFinite(v))throw Error('Enter a finite number.');return v;}
  function integers(value){return value.split(',').map(s=>{if(!/^\d+$/.test(s.trim()))throw Error('Use comma-separated whole numbers.');return Number(s.trim());});}
  async function configure(source) {
    const panel=$('#prop-campaigns');panel.replaceChildren();
    panel.append(node('h2','Independent phase research campaigns'));
    if(source.run_metadata.research?.phase!=='is'){panel.append(node('p','Select a declared IS backtest to create a research campaign.'));return;}
    const defaults=await api('/api/research-campaigns/defaults');
    const saved=await api('/api/research-campaigns?source_id='+source.id);
    const history=node('div');for(const c of saved.items){history.append(link(`${c.phase} · ${c.status}${c.frozen?' · frozen':''} · ${c.campaign_id}`,`#backtests/prop/campaign/${c.campaign_id}`),node('br'));}panel.append(history);
    const d=node('details');d.id='campaign-configure';d.append(node('summary','Configure a phase campaign'));panel.append(d);
    const form=node('form');form.id='campaign-form';d.append(form);
    form.append(node('p','Compare saved IS strategies and optimization trials. Every source × MNQ size counts toward the budget. Sources must share the dataset, research split and execution costs.'));
    const phase=select(form,'Phase','campaign-phase',[['evaluation','Evaluation · acquisition cost/time'],['funded','Funded · trader cash received']]);
    const profile=select(form,'Account profile','campaign-profile',[['apex-50k-eod','Apex 50K EOD'],['lucidflex-50k','LucidFlex 50K · funded only']]);
    const sources=node('div');sources.id='campaign-sources';form.append(sources);
    const anchor={id:source.id,created_at:source.created_at_utc,status:source.status,
      strategy_id:source.run_metadata.strategy.id,parameters:source.run_metadata.strategy.parameters,
      dataset_name:source.run_metadata.dataset.name,is_start:source.run_metadata.research.plan.is_start,
      is_end:source.run_metadata.research.plan.is_end,total_trials:1,selectable:true};
    const brief=(value,max=100)=>{const text=String(value??'');return text.length>max?text.slice(0,max-1)+'…':text;};
    function parametersLabel(item,kind){return Object.entries(item.parameters||{}).map(([key,value])=>{
      if(kind==='optimization_id'&&value&&typeof value==='object')return `${key}=${value.start}…${value.end}`;
      return `${key}=${value}`;
    }).join(', ');}
    function sourceLabel(item,kind){return `${(item.strategy_id||'Strategy').replaceAll('_',' ')} · ${brief(item.dataset_name,45)} · ${brief(parametersLabel(item,kind))} · ${item.created_at?.slice(0,10)||''} · ${item.status}${kind==='optimization_id'?` · ${item.total_trials} trials`:''} · ${item.id.slice(0,8)}`;}
    function addSource(id=''){
      const row=node('fieldset');row.className='prop-fields';sources.append(row);
      const kind=select(row,'Saved source type','',[['backtest_id','Backtest'],['optimization_id','Optimization job']]);kind.className='campaign-kind';
      const search=field(row,'Search saved sources','','','search');search.required=false;search.maxLength=200;
      search.className='campaign-source-search';search.placeholder='Strategy, parameters, dataset, date or ID';
      const ref=select(row,'Saved backtest report','',[['','Choose a saved backtest…']]);ref.required=true;
      ref.className='campaign-reference';ref.parentElement.style.gridColumn='1 / -1';ref.style.minWidth='0';ref.style.width='100%';
      const information=node('p');information.className='campaign-source-info';information.style.gridColumn='1 / -1';row.append(information);
      const more=button(row,'Load more sources','');more.className+=' campaign-source-more';
      const listing=node('p');listing.className='campaign-source-status';listing.setAttribute('role','status');row.append(listing);
      const sizes=field(row,'MNQ sizes, separated by commas','','1,3');sizes.className='campaign-sizes';
      const trials=field(row,'Trial numbers (blank: entire job)','','');trials.required=false;trials.className='campaign-trials';trials.disabled=true;
      const hint=node('p');hint.style.gridColumn='1 / -1';row.append(hint);
      let entries=new Map(),matches=[],offset=0,requestVersion=0,timer=null,loading=false;
      if(id===source.id){entries.set(id,anchor);const o=node('option',sourceLabel(anchor,'backtest_id'));o.value=id;ref.append(o);ref.value=id;}
      function describe(){const item=entries.get(ref.value);information.replaceChildren();if(!item)return;
        information.append(node('span',`${item.strategy_id} · ${parametersLabel(item,kind.value)} · IS ${item.is_start} → ${item.is_end} · ${item.status} · `),
          link('Open saved '+(kind.value==='backtest_id'?'report':'job'),kind.value==='backtest_id'?`#backtests/report/${item.id}`:`#backtests/batches/${item.id}`));}
      function paint(){const selected=ref.value,placeholder=node('option',kind.value==='backtest_id'?'Choose a saved backtest…':'Choose a saved optimization job…');placeholder.value='';ref.replaceChildren(placeholder);
        for(const key of new Set([...(selected?[selected]:[]),...matches])){const item=entries.get(key);if(!item)continue;
          const o=node('option',sourceLabel(item,kind.value));o.value=item.id;o.disabled=!item.selectable;ref.append(o);}
        ref.value=entries.get(selected)?.selectable?selected:'';describe();}
      async function load(reset=false){const version=++requestVersion;const query=search.value.trim(),type=kind.value;
        loading=true;more.disabled=true;more.hidden=false;listing.textContent='Loading saved sources…';
        try{const page=await api(`/api/research-campaigns/sources?${new URLSearchParams({kind:type,q:query,offset:reset?0:offset,limit:50})}`);
          if(version!==requestVersion||!row.isConnected)return;
          if(reset){matches=[];offset=0;const selected=entries.get(ref.value);entries=new Map(selected?[[selected.id,selected]]:[]);}
          for(const item of page.items){entries.set(item.id,item);if(!matches.includes(item.id))matches.push(item.id);}
          offset=page.offset+page.items.length;paint();more.hidden=offset>=page.total;more.textContent='Load more sources';
          listing.textContent=page.total?`${matches.length} of ${page.total} matching sources.${type==='optimization_id'?' Incomplete jobs cannot be selected.':''}`:(query?'No matching sources. Try another search.':type==='backtest_id'?'No completed IS backtests in this library.':'No IS optimization jobs in this library. Choose Backtest to use an individual report.');
        }catch(e){if(version===requestVersion&&row.isConnected){listing.textContent='Could not load sources: '+e.message;more.hidden=false;more.textContent='Retry loading sources';}}
        finally{if(version===requestVersion){loading=false;more.disabled=false;}}
      }
      function changedKind(){++requestVersion;clearTimeout(timer);entries.clear();matches=[];offset=0;search.value='';ref.value='';paint();
        const backtest=kind.value==='backtest_id';trials.disabled=backtest;trials.value='';ref.parentElement.firstChild.textContent=backtest?'Saved backtest report':'Saved optimization job';
        hint.textContent=backtest?'Choose a completed IS backtest, including an individual saved trial.':'Choose a completed IS optimization job. Individual trial reports are listed under Backtest.';
        load(true);}
      kind.onchange=changedKind;ref.onchange=describe;
      hint.textContent='Choose a completed IS backtest, including an individual saved trial.';
      search.addEventListener('input',()=>{++requestVersion;clearTimeout(timer);timer=setTimeout(()=>load(true),200);});
      more.onclick=()=>{if(!loading)load(more.textContent.startsWith('Retry'));};
      button(row,'Remove source','').onclick=()=>{++requestVersion;clearTimeout(timer);row.remove();invalidate();};
      describe();load(true);
    }
    addSource(source.id);button(form,'Add saved source','campaign-add-source').onclick=()=>{addSource();invalidate();};
    const grid=node('div');grid.className='prop-fields';form.append(grid);
    const plan=source.run_metadata.research.plan;
    field(grid,'Maximum candidate count','campaign-budget','128','number');
    field(grid,'IS first session','campaign-is-start',plan.is_start,'date');field(grid,'IS last session','campaign-is-end',plan.is_end,'date');
    field(grid,'Simulated paths per candidate','campaign-paths','1000','number');field(grid,'Simulation seed','campaign-seed','42','number');
    select(grid,'Resampling block · weekdays','campaign-block',[['5','5'],['1','1'],['10','10']]);
    field(grid,'Scenario start date · Chicago','campaign-start',plan.is_start,'date');field(grid,'Calendar coverage end','campaign-calendar-end','2037-01-01','date');
    const evalFields=node('div');evalFields.className='prop-fields';form.append(evalFields);
    field(evalFields,'Evaluation price · USD','campaign-price','30','number');field(evalFields,'Activation fee · USD','campaign-activation','40','number');
    field(evalFields,'Acquisition chains','campaign-chains','1000','number');field(evalFields,'Acquisition seed','campaign-chain-seed','45','number');
    const fundedFields=node('div');fundedFields.className='prop-fields';form.append(fundedFields);
    field(fundedFields,'Receipt horizon · calendar days','campaign-horizon','90','number');field(fundedFields,'Receipt delay · calendar days','campaign-delay','0','number');
    field(fundedFields,'Maximum breach probability (0–1)','campaign-breach','1','number').step='any';
    const note=node('p','Uses captured source costs and fixed-quantity linear MNQ scenarios. The declared weekday calendar, prices and settlement delays are assumptions, not verified provider forecasts. Advanced calendars, costs and constraints are available through the campaign API.');form.append(note);
    const changePhase=()=>{evalFields.hidden=phase.value!=='evaluation';fundedFields.hidden=phase.value!=='funded';};phase.onchange=changePhase;changePhase();
    const check=button(form,'Save and check candidates','campaign-check'),run=button(form,'Run campaign','campaign-run');run.disabled=true;
    const status=node('p');status.id='campaign-status';status.setAttribute('role','status');form.append(status);
    let campaignId=null,revision=0;
    function invalidate(){revision++;campaignId=null;run.disabled=true;status.textContent='Configuration changed; save and check candidates.';}
    form.addEventListener('input',invalidate);form.addEventListener('change',invalidate);form.onsubmit=e=>e.preventDefault();
    check.onclick=async()=>{if(!form.reportValidity())return;const version=revision;check.disabled=true;run.disabled=true;
      try{
        const isEval=phase.value==='evaluation',p={profile_id:profile.value,rule_version:defaults.profiles[profile.value]};
        if(isEval)Object.assign(p,{evaluation_price:$('#campaign-price').value,activation_fee:$('#campaign-activation').value});
        const sampling={block_weekdays:number('campaign-block')};if(isEval)Object.assign(sampling,{chain_simulations:number('campaign-chains'),chain_seed:number('campaign-chain-seed')});
        const search_settings={calendar:{start_dates:[$('#campaign-start').value],coverage_end:$('#campaign-calendar-end').value}};
        if(!isEval)Object.assign(search_settings,{horizon_calendar_days:number('campaign-horizon'),receipt_delay_calendar_days:number('campaign-delay'),constraints:{maximum_account_breach_probability:number('campaign-breach')}});
        const body={campaign_id:crypto.randomUUID().replaceAll('-',''),phase:phase.value,profile:p,
          sources:[...sources.children].map(row=>{const kind=row.querySelector('.campaign-kind').value;const value={[kind]:row.querySelector('.campaign-reference').value.trim(),sizes:integers(row.querySelector('.campaign-sizes').value)};const t=row.querySelector('.campaign-trials').value;if(kind==='optimization_id'&&t.trim())value.trials=integers(t);return value;}),
          maximum_candidates:number('campaign-budget'),is_window:{first_session:$('#campaign-is-start').value,last_session:$('#campaign-is-end').value},
          simulation:{simulations:number('campaign-paths'),seed:number('campaign-seed')},sampling,costs:{mode:'source'},search_settings};
        status.textContent='Checking saved source identity, costs, risk and candidate budget…';
        const c=await api('/api/research-campaigns',body);const checks=await api(`/api/research-campaigns/${c.campaign_id}/check`,{});
        if(version!==revision)return;
        campaignId=c.campaign_id;run.disabled=false;status.textContent=`${checks.candidate_search_count} compatible candidates · ${c.manifest.selection_objective} · IS only. Ready to run.`;
        const prior=form.querySelector('.campaign-checks');if(prior)prior.remove();const checkDetails=node('div');checkDetails.className='campaign-checks';details(checkDetails,'Source checks and saved candidate definitions',checks);form.append(checkDetails);
      }catch(e){status.textContent=e.message;}finally{check.disabled=false;}
    };
    run.onclick=async()=>{if(!campaignId)return;run.disabled=true;try{await api(`/api/research-campaigns/${campaignId}/run`,{});location.hash=`#backtests/prop/campaign/${campaignId}`;}catch(e){status.textContent=e.message;run.disabled=false;}};
  }
  function renderAnalysis(report,campaign=null){
    $('#prop-config').hidden=true;$('#prop-report').hidden=false;$('#prop-delete').hidden=true;$('#prop-downloads').replaceChildren();
    $('#prop-heading-title').textContent=campaign?'Research campaign':'Independent phase analysis';
    $('#prop-heading-note').textContent=report.phase==='evaluation'?'Evaluation · minimize acquisition cost and calendar time':'Funded · maximize expected trader cash received';
    $('#prop-back').href=`#backtests/report/${report.source.backtest.id}`;
    const target=$('#prop-report-content');target.replaceChildren();target.className='';
    const calc=report.calculations;
    const panel=node('section');panel.className='panel prop-panel';target.append(panel);
    panel.append(node('h2',campaign?.frozen?'Frozen IS selection':'IS candidate results'),node('p',`${calc.candidates.length} candidates · ${report.model_version}. Estimated results; no provider parity or certified optimum. OOS has not been run by this campaign.`));
    const table=node('table');table.className='prop-table';const head=node('tr');
    for(const label of ['Freeze','Saved strategy / source','MNQ','Status',...(report.phase==='evaluation'?['Cost · USD','Calendar days','Frontier']:['Expected receipts · USD','Pending · USD','Rank'])])head.append(node('th',label));table.append(head);panel.append(table);
    const allowed=report.phase==='evaluation'?calc.frontier:calc.ranking;
    const displayed=[...calc.candidates].sort((a,b)=>report.phase==='funded'?(a.rank??Infinity)-(b.rank??Infinity):Number(b.pareto_member)-Number(a.pareto_member));
    for(const r of displayed){const row=node('tr'),cell=node('td'),box=node('input');box.type='checkbox';box.value=r.candidate_id;box.className='campaign-pick';box.disabled=!campaign||!!campaign.frozen||!allowed.includes(r.candidate_id);box.checked=!!campaign?.frozen?.candidate_ids.includes(r.candidate_id);cell.append(box);row.append(cell);
      const s=node('td');s.append(link(r.manifest.strategy.id,`#backtests/report/${r.manifest.configuration.source.source_backtest_id}`));s.append(node('p',Object.entries(r.manifest.strategy.parameters).map(([k,v])=>`${k}=${v}`).join(', ')));details(s,'Source identity and provenance',r.manifest);row.append(s);
      const m=r.metrics;for(const value of [r.manifest.configuration.micros,report.phase==='funded'&&r.status==='estimated'&&!r.feasible?'infeasible':r.status,...(report.phase==='evaluation'?[m.cost_per_funded,m.expected_calendar_days_to_funded,r.pareto_member]:[m.expected_payouts,m.expected_pending_cash,r.rank??'Not ranked'])])row.append(node('td',value===null?'Unresolved':String(value)));table.append(row);
    }
    details(panel,report.phase==='evaluation'?'Frontier and marginal acceleration costs':'Ranking, constraints and uncertainty',{...calc,candidates:undefined});
    details(panel,'Candidate metrics, risk, uncertainty and assumptions',calc.candidates.map(r=>({candidate_id:r.candidate_id,metrics:r.metrics,status:r.status,feasible:r.feasible,constraint_violations:r.constraint_violations,rank:r.rank,pareto_member:r.pareto_member,dominated:r.dominated,censoring:r.censoring,uncertainty:r.uncertainty,assumptions:r.assumptions})));
    panel.append(node('p','Full path observations are retained in the JSON and ZIP downloads.'));
    if(campaign){
      const actions=node('div');panel.append(actions);
      if(!campaign.frozen){const rationale=field(actions,'Selection rationale','campaign-rationale','');const freeze=button(actions,'Freeze selected candidates','campaign-freeze');const status=node('p');actions.append(status);
        freeze.onclick=async()=>{try{if(!rationale.reportValidity())return;freeze.disabled=true;await api(`/api/research-campaigns/${campaign.campaign_id}/freeze`,{candidate_ids:[...table.querySelectorAll('.campaign-pick:checked')].map(i=>i.value),rationale:rationale.value});await watch(campaign.campaign_id,()=>location.hash===`#backtests/prop/campaign/${campaign.campaign_id}`);}catch(e){status.textContent=e.message;freeze.disabled=false;}};
      }else details(actions,'Frozen package',campaign.frozen);
      for(const kind of ['campaign.json','results.csv','results.json','source_checks.json','analysis.zip',...(campaign.frozen?['frozen_package.json']:[])])actions.append(link('Download '+kind,`/api/research-campaigns/${campaign.campaign_id}/exports/${kind}`),node('br'));
      details(panel,'Campaign declaration and numerical identity',campaign.manifest);
    }else panel.append(link('Download analysis ZIP',`/api/prop-analyses/${report.id}/downloads/analysis.zip`));
  }
  async function watch(id,current){
    $('#prop-config').hidden=true;$('#prop-report').hidden=true;$('#prop-downloads').replaceChildren();
    while(current()){
      const c=await api('/api/research-campaigns/'+id);if(!current())return;
      $('#prop-status').textContent=`${c.manifest.phase} campaign · ${c.status} · ${c.campaign_id}`;
      if(c.status==='complete'){const r=await api(`/api/prop-analyses/${c.analysis_id}/downloads/report.json`);if(current())renderAnalysis(r,c);return;}
      if(['validated','error'].includes(c.status)){
        $('#prop-report').hidden=false;const p=$('#prop-report-content');p.replaceChildren();p.append(node('p',c.analysis?.error||'Sources validated. Run the saved campaign to calculate results.'));
        button(p,c.status==='error'?'Retry interrupted or failed calculation':'Run saved campaign','campaign-resume').onclick=async()=>{try{await api(`/api/research-campaigns/${id}/run`,{});await watch(id,current);}catch(e){$('#prop-status').textContent=e.message;}};return;
      }
      await new Promise(resolve=>setTimeout(resolve,700));
    }
  }
  window.phaseCampaigns={configure,watch,renderAnalysis};
})();
