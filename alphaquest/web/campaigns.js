/* Campaign controls live inside the ordinary saved-backtest prop workflow. */
(() => {
  const $ = s => document.querySelector(s);
  const node = (tag, text) => {const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
  const link = (text, href) => {const a=node('a',text);a.href=href;return a;};
  async function api(url, body, method='POST') {
    const response=await fetch(url,body===undefined?{}:{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const result=await response.json();if(!response.ok){const error=Error(typeof result.detail==='string'?result.detail:JSON.stringify(result.detail));error.detail=result.detail;error.status=response.status;throw error;}return result;
  }
  function details(parent,title,value){const d=node('details');d.append(node('summary',title),node('pre',JSON.stringify(value,null,2)));parent.append(d);}
  function field(parent,label,id,value,type='text') {
    const l=node('label',label),i=node('input');i.id=id;i.type=type;i.value=value;i.required=true;l.append(i);parent.append(l);return i;
  }
  function select(parent,label,id,options){const l=node('label',label),s=node('select');s.id=id;for(const [v,t]of options){const o=node('option',t);o.value=v;s.append(o);}l.append(s);parent.append(l);return s;}
  function button(parent,text,id){const b=node('button',text);b.type='button';b.id=id;b.className='button secondary';parent.append(b);return b;}
  function number(id){const v=Number($('#'+id).value);if(!Number.isFinite(v))throw Error('Enter a finite number.');return v;}
  function integers(value){return value.split(',').map(s=>{if(!/^\d+$/.test(s.trim()))throw Error('Use comma-separated whole numbers.');return Number(s.trim());});}
  function checkbox(parent,label,cls){const l=node('label'),i=node('input');i.type='checkbox';i.className=cls;l.append(i,document.createTextNode(' '+label));parent.append(l);return i;}
  const referenceLabels={initial_configured_capital:'Initial configured capital',current_account_balance:'Current account balance',available_drawdown_cushion:'Available drawdown cushion'};
  function canonical(value){return JSON.stringify(value,(_,v)=>v&&typeof v==='object'&&!Array.isArray(v)?Object.fromEntries(Object.keys(v).sort().map(k=>[k,v[k]])):v);}
  function frozenName(assessment,candidate){
    if(!assessment)return undefined;const config=candidate.manifest.configuration;
    return assessment.sources.find(mapping=>{if(mapping.source_id!==config.source.source_backtest_id)return false;
      if(candidate.frozen_candidate_id)return mapping.frozen_candidate_id===candidate.frozen_candidate_id;
      const expected=structuredClone(mapping.frozen_manifest.configuration);expected.source.source_backtest_id=config.source.source_backtest_id;expected.period=config.period;
      return canonical(expected)===canonical(config);})?.name;
  }
  function sizingLabel(config){
    const p=config.sizing?.policy;if(!p)return `${config.micros} MNQ`;
    const label=p.kind==='fixed_contracts'?`${p.contracts} fixed MNQ`:p.kind==='fixed_dollar_risk'?`$${p.risk_dollars} planned risk`:`${p.risk_percent}% of ${(referenceLabels[p.reference]||p.reference).toLowerCase()}`;
    return `${label} · cap ${config.micros} MNQ`;
  }
  function profileRuleSummary(phase,profileId){
    if(phase==='evaluation')return profileId==='lucidflex-50k'
      ?'LucidFlex Evaluation: $3,000 profit target; $2,000 EOD trailing drawdown; 40% best-day consistency; no modeled evaluation expiry. The local model requires zero activation fee and uses a $1,200 soft daily stop and 30-calendar-day activity rule. Declared forecast and retry guards can still censor acquisition.'
      :'Apex Evaluation: $3,000 profit target; $2,000 EOD trailing drawdown; $1,000 daily loss limit; 21-session expiry.';
    return profileId==='apex-50k-eod'
      ?'Fresh funded account: $2,000 trailing drawdown; $2,100 safety net; five qualifying days at $250; 50% payout consistency; six modeled payout caps ($1,500/$1,500/$2,000/$2,500/$2,500/$3,000). Size tiers and daily stops still apply.'
      :'Fresh LucidFlex funded account: $2,000 drawdown; five winning days at $150; no funded consistency requirement; 50% withdrawal limit, $500 minimum/$2,000 maximum gross request; 90% trader share; five modeled payouts; $1,200 daily stop and 20/30/40-MNQ tiers.';
  }
  function sizingControls(row,sizes,options={}){
    const native=options.native===true,prefix=options.prefix||(native?'native-':'campaign-'),maximumContracts=options.maximumContracts||(native?40:60);
    const mode=select(row,native?'Sizing mode':'Sizing comparison','',native?[['legacy','Fixed MNQ quantity'],['policies','Account-state sizing policy']]:options.riskOnly?[['legacy','No additional risk policies'],['policies','Compare dollar and percentage policies']]:[['legacy','Fixed MNQ sizes · existing'],['policies','Compare sizing policies']]);mode.className=prefix+'sizing-mode';
    const box=node('div');box.className=prefix+'sizing-controls';box.style.gridColumn='1 / -1';row.append(box);
    box.append(node('p',native?'Rerun the original MNQ bars. One policy chooses quantity at each real strategy opportunity from the account state, decision close and known stop. A skipped opportunity does not consume the daily accepted-entry allowance.':'Each selected source or trial × hard MNQ cap × policy is a separate candidate. Quantities are chosen before each trade from the policy, current account state and declared stop when required. Imported source replay needs an exporter-declared size-invariant path; native dynamic policies require a suitable native rerun.'));
    const policies=node('div');policies.className=prefix+'sizing-policies';box.append(policies);
    const add=button(box,'Add sizing policy','');add.classList.add(prefix+'add-policy');add.hidden=native;
    const planning=node('details');planning.open=true;planning.append(node('summary','MNQ planning capital and execution assumptions'));box.append(planning);
    const grid=node('div');grid.className='prop-fields';planning.append(grid);
    function planningField(label,key,value,type='number'){const i=field(grid,label,'',value,type);i.className=prefix+'planning-'+key;i.step='any';return i;}
    for(const [label,key,value]of [['Initial configured capital · USD','capital','50000'],['MNQ tick size · points','tick','0.25'],['MNQ point value · USD','point','2']])planningField(label,key,value).readOnly=true;
    for(const [label,key]of [['Planned entry slippage · ticks','entry-slip'],['Planned stop-exit slippage · ticks','stop-slip']]){const i=planningField(label,key,native?options.execution.slippage_ticks:'0');i.step='1';i.min='0';}
    const commission=planningField('Planned commission per MNQ per side · USD','commission',native?options.execution.commission_per_contract_per_side:'');commission.min='0';commission.placeholder='Enter an explicit assumption';
    planning.append(node('p','These declared costs size the planned stop loss only. They are not charged again to source net P&L. Actual source costs remain authoritative. Observed gaps can exceed the planned loss; cushion guards do not guarantee a stop fill. Supported account profiles use $50,000 initial capital and simulated MNQ ($2/point, 0.25 tick).'));
    function addPolicy(){
      const group=node('section');group.className=prefix+'sizing-policy prop-fields';group.setAttribute('role','group');policies.append(group);
      const legend=node('h4','Sizing policy');legend.className=prefix+'policy-label';legend.style.gridColumn='1 / -1';group.append(legend);
      const kind=select(group,'Policy kind','',[['fixed_dollar_risk','Fixed dollar risk'],['percentage_risk','Percentage risk'],...(!options.riskOnly?[['fixed_contracts','Fixed contracts']]:[])]);kind.className=prefix+'policy-kind';
      const contracts=field(group,'Requested MNQ contracts','','1','number');contracts.className=prefix+'policy-contracts';contracts.min='1';contracts.max=String(maximumContracts);
      const dollars=field(group,'Planned risk per trade · USD','','50','number');dollars.className=prefix+'policy-dollars';dollars.step='any';dollars.min='0.00000001';
      const percent=field(group,'Risk percent (0.5 means 0.5%)','','0.5','number');percent.className=prefix+'policy-percent';percent.step='any';percent.min='0.00000001';percent.max='100';
      const reference=select(group,'Percentage reference','',Object.entries(referenceLabels));reference.className=prefix+'policy-reference';
      const advanced=node('details');advanced.style.gridColumn='1 / -1';advanced.append(node('summary','Quantity bounds and cushion guards'));group.append(advanced);
      const limits=node('div');limits.className='prop-fields';advanced.append(limits);
      const minimum=field(limits,'Minimum tradable MNQ','','1','number'),maximum=field(limits,'Policy maximum MNQ','','40','number');minimum.className=prefix+'policy-minimum';maximum.className=prefix+'policy-maximum';
      for(const input of [minimum,maximum]){input.min='1';input.max=String(maximumContracts);}
      const account=checkbox(limits,'Keep planned loss strictly inside account cushion',prefix+'policy-account'),daily=checkbox(limits,'Keep planned loss strictly inside daily cushion',prefix+'policy-daily');
      advanced.append(node('p','The smallest policy, user and provider cap applies. If the resulting quantity is below the minimum, the trade is skipped; it is never rounded up. Cushion guards are optional and use the state known at the decision.'));
      const remove=button(group,'Remove policy','');remove.classList.add(prefix+'remove-policy');remove.hidden=native;remove.onclick=()=>{group.remove();refresh();row.dispatchEvent(new Event('input',{bubbles:true}));};
      group.refresh=()=>{const active=mode.value==='policies';for(const [input,visible]of [[contracts,kind.value==='fixed_contracts'],[dollars,kind.value==='fixed_dollar_risk'],[percent,kind.value==='percentage_risk'],[reference,kind.value==='percentage_risk']]){input.closest('label').hidden=!visible;input.disabled=!active||!visible;}};
      let loadedPolicy=null;
      group.read=()=>{const policy={...(loadedPolicy?.kind===kind.value?loadedPolicy:{}),kind:kind.value,minimum_contracts:Number(minimum.value),maximum_contracts:Number(maximum.value),constrain_to_account_cushion:account.checked,constrain_to_daily_cushion:daily.checked};
        if(kind.value==='fixed_contracts')policy.contracts=Number(contracts.value);else if(kind.value==='fixed_dollar_risk')policy.risk_dollars=dollars.value;else Object.assign(policy,{risk_percent:percent.value,reference:reference.value});return policy;};
      group.load=policy=>{if(![...kind.options].some(option=>option.value===policy.kind))throw Error('Saved sizing kind cannot be represented by these controls: '+policy.kind);loadedPolicy=structuredClone(policy);kind.value=policy.kind;contracts.value=policy.contracts??1;dollars.value=policy.risk_dollars??'50';percent.value=policy.risk_percent??'0.5';reference.value=policy.reference??'initial_configured_capital';minimum.value=policy.minimum_contracts??1;maximum.value=policy.maximum_contracts??40;account.checked=policy.constrain_to_account_cushion===true;daily.checked=policy.constrain_to_daily_cushion===true;group.refresh();};
      kind.onchange=group.refresh;refresh();return group;
    }
    function refresh(){const active=mode.value==='policies';box.hidden=!active;sizes.closest('label').firstChild.textContent=options.riskOnly?'Hard MNQ caps for additional risk policies · comma-separated':native?(active?'Hard user cap · MNQ':'Fixed quantity · MNQ'):(active?'Hard MNQ caps, separated by commas':'MNQ sizes, separated by commas');if(options.riskOnly){sizes.disabled=!active;sizes.required=active;}
      box.querySelectorAll('input,select,button').forEach(i=>i.disabled=!active);for(const group of policies.children)group.refresh();add.disabled=!active||policies.children.length>=60;
      [...policies.children].forEach((group,index)=>{const label='Sizing policy '+(index+1);group.querySelector('.'+prefix+'policy-label').textContent=label;group.setAttribute('aria-label',label);group.querySelector('.'+prefix+'remove-policy').disabled=!active||policies.children.length===1;});}
    add.onclick=()=>{addPolicy();row.dispatchEvent(new Event('input',{bubbles:true}));};mode.onchange=refresh;addPolicy();refresh();
    const read=()=>mode.value==='legacy'?undefined:[...policies.children].map(group=>({policy:group.read(),initial_configured_capital:grid.querySelector('.'+prefix+'planning-capital').value,planning_execution:{tick_size:grid.querySelector('.'+prefix+'planning-tick').value,point_value:grid.querySelector('.'+prefix+'planning-point').value,entry_slippage_ticks:Number(grid.querySelector('.'+prefix+'planning-entry-slip').value),stop_exit_slippage_ticks:Number(grid.querySelector('.'+prefix+'planning-stop-slip').value),commission_per_contract_per_side:commission.value}}));
    read.load=values=>{if(!values?.length){mode.value='legacy';refresh();return;}if(values.length>60||(native&&values.length!==1))throw Error('Saved sizing policy count is unsupported by these controls.');const common=({initial_configured_capital,planning_execution})=>canonical({initial_configured_capital,planning_execution});if(values.some(value=>common(value)!==common(values[0])))throw Error('Saved policies have distinct planning assumptions; these grouped controls cannot silently combine them.');if(values.some(value=>options.riskOnly&&value.policy.kind==='fixed_contracts'))throw Error('An explicit fixed sizing object cannot be silently converted to a bare quantity.');mode.value='policies';policies.replaceChildren();for(const value of values)addPolicy().load(value.policy);const value=values[0];for(const[key,v]of Object.entries({capital:value.initial_configured_capital,tick:value.planning_execution.tick_size,point:value.planning_execution.point_value,'entry-slip':value.planning_execution.entry_slippage_ticks,'stop-slip':value.planning_execution.stop_exit_slippage_ticks,commission:value.planning_execution.commission_per_contract_per_side}))grid.querySelector('.'+prefix+'planning-'+key).value=v;refresh();};
    return read;
  }
  async function configure(source) {
    const panel=$('#prop-campaigns');panel.replaceChildren();
    panel.append(node('h2','Independent phase research campaigns'));
    const external=source.run_metadata.source?.kind==='external_trade_export';
    if(external&&source.capabilities?.phase_selection!==true){panel.append(node('p','This imported source is not eligible for independent phase selection. Use the source check below to inspect supported analysis and source limitations. Native strategy and OOS reruns remain unavailable.'));return;}
    if(source.run_metadata.research?.phase!=='is'){panel.append(node('p','Select a declared IS backtest to create a research campaign.'));return;}
    const defaults=await api('/api/research-campaigns/defaults');
    const saved=await api('/api/research-campaigns?source_id='+source.id);
    const history=node('div');for(const c of saved.items){history.append(link(`${c.phase} · ${c.status}${c.frozen?' · frozen':''} · ${c.campaign_id}`,`#backtests/prop/campaign/${c.campaign_id}`),node('br'));}panel.append(history);
    const d=node('details');d.id='campaign-configure';d.append(node('summary','Configure a phase campaign'));panel.append(d);
    const form=node('form');form.id='campaign-form';d.append(form);
    form.append(node('p','Compare saved IS sources and optimization trials. Each trial × fixed MNQ size, or trial × hard cap × declared sizing policy, is one candidate. The full count is calculated when checking; searches above 128 candidates require confirmation. Source identity, research coverage and costs must be compatible.'));
    if(external)form.append(node('p','Imported IS coverage and size-invariant execution paths are exporter declarations. The source check verifies preserved evidence and causal stop metadata; it does not certify market completeness or broker fills. Native strategy reruns and automatic frozen OOS launches are unavailable.'));
    const phase=select(form,'Phase','campaign-phase',[['evaluation','Evaluation · acquisition cost/time'],['funded','Funded · trader cash received']]);
    const execution=select(form,'Forecast execution','campaign-execution',[['trade_path','Saved trade-path scenarios · existing'],['native','Actual native strategy reruns · MNQ']]);
    execution.options[1].disabled=external||!defaults.native_execution;
    form.append(node('p','Native forecasts rerun strategy opportunities, sizing and fills for every account path. Source admission checks the supported strategy, actual MNQ instrument, causal stops and complete observed sessions. Existing trade-path scenarios retain their saved execution assumptions.'));
    const profile=select(form,'Account profile','campaign-profile',[['apex-50k-eod','Apex 50K EOD'],['lucidflex-50k','LucidFlex 50K']]);
    const entry=node('div');panel.insertBefore(entry,d);
    for(const [value,title]of [['evaluation','Create Evaluation campaign'],['funded','Create Funded campaign']])button(entry,title,'campaign-new-'+value).onclick=()=>{d.open=true;phase.value=value;phase.dispatchEvent(new Event('change',{bubbles:true}));phase.focus();};
    const ruleNote=node('p');ruleNote.id='campaign-rule-summary';form.append(ruleNote);
    const profileStatus=node('p');profileStatus.id='campaign-profile-status';profileStatus.setAttribute('role','status');form.append(profileStatus);
    const showRule=()=>{ruleNote.textContent=`Local rule snapshot: ${profile.value} · ${defaults.profiles[profile.value]}. ${profileRuleSummary(phase.value,profile.value)} These are local model rules, not newly verified provider terms. Fees remain your explicit declarations. Source parameters, costs, sizes and the research window are saved by the compatibility check.`;};
    function syncProfile(){
      const unavailable=phase.value==='evaluation'&&execution.value!=='native';
      profile.options[1].disabled=unavailable;profile.options[1].textContent=unavailable?'LucidFlex 50K · Evaluation requires native reruns':'LucidFlex 50K';
      const blocked=unavailable&&profile.value==='lucidflex-50k';
      const reason=blocked?'LucidFlex Evaluation requires actual native strategy reruns. Your profile and fees are retained; choose native execution or explicitly choose another profile.':'';
      profile.setCustomValidity(reason);profileStatus.textContent=reason;showRule();
    }
    profile.addEventListener('change',syncProfile);syncProfile();
    const sources=node('div');sources.id='campaign-sources';form.append(sources);
    const anchor={id:source.id,created_at:source.created_at_utc,status:source.status,
      strategy_id:source.run_metadata.strategy.id,parameters:source.run_metadata.strategy.parameters,
      dataset_name:source.run_metadata.dataset.name,is_start:source.run_metadata.research.plan?.is_start||source.run_metadata.external_manifest?.coverage.sessions[0],
      is_end:source.run_metadata.research.plan?.is_end||source.run_metadata.external_manifest?.coverage.sessions.at(-1),total_trials:1,selectable:true};
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
      row.readSizing=sizingControls(row,sizes);
      const hint=node('p');hint.style.gridColumn='1 / -1';row.append(hint);
      let entries=new Map(),matches=[],offset=0,requestVersion=0,timer=null,loading=false;
      if(id===source.id){entries.set(id,anchor);const o=node('option',sourceLabel(anchor,'backtest_id'));o.value=id;ref.append(o);ref.value=id;}
      function describe(){const item=entries.get(ref.value);information.replaceChildren();if(!item)return;
        const first=item.is_start||(item.id===source.id?anchor.is_start:null),last=item.is_end||(item.id===source.id?anchor.is_end:null);
        information.append(node('span',`${item.strategy_id} · ${parametersLabel(item,kind.value)} · ${first&&last?'IS '+first+' → '+last:'IS coverage resolved by source check'} · ${item.status} · `),
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
      button(row,'Remove source','').onclick=()=>{++requestVersion;clearTimeout(timer);row.remove();invalidate();refreshWindow();};
      describe();load(true);
    }
    addSource(source.id);button(form,'Add saved source','campaign-add-source').onclick=()=>{addSource();invalidate();refreshWindow();};
    const grid=node('div');grid.className='prop-fields';form.append(grid);
    const plan=source.run_metadata.research.plan||{is_start:anchor.is_start,is_end:anchor.is_end};
    const isFirst=field(grid,'IS first session','campaign-is-start','','date'),isLast=field(grid,'IS last session','campaign-is-end','','date');
    const windowStatus=node('p','Finding common saved IS coverage…');windowStatus.id='campaign-window-status';form.append(windowStatus);
    button(form,'Use full common IS window','campaign-window-reset').onclick=()=>{invalidate();refreshWindow();};
    field(grid,'Simulated paths per candidate','campaign-paths','1000','number');field(grid,'Simulation seed','campaign-seed','42','number');
    select(grid,'Resampling block · weekdays','campaign-block',[['5','5'],['1','1'],['10','10']]);
    field(grid,'Scenario start date · Chicago','campaign-start',plan.is_start,'date');
    const calendarNote=node('p','Calendar coverage is calculated automatically from the scenario start and the Evaluation chain limit or Funded receipt horizon. It does not require future market data; the derived dates are saved with the campaign.');form.append(calendarNote);
    const nativeFields=node('fieldset');nativeFields.id='campaign-native-fields';nativeFields.className='prop-fields';nativeFields.hidden=nativeFields.disabled=true;form.append(nativeFields);
    nativeFields.append(node('legend','Native source-block forecast declaration'));
    const nativeDefaults=defaults.native_execution;
    let nativeHorizon,nativeCapture,readNativeCalendar;
    if(nativeDefaults){
      const law=node('p','Each draw uses complete observed contiguous source sessions. Strategy state resets once per block with prior-only source warmup and disabled entries; provider account state continues. Target dates use the separately declared modeled calendar. All source prices and timestamps remain original.');law.style.gridColumn='1 / -1';nativeFields.append(law);
      nativeHorizon=field(nativeFields,'Native forecast horizon · calendar days','campaign-native-horizon',nativeDefaults.horizon_calendar_days,'number');nativeHorizon.min='1';nativeHorizon.max='365';
      nativeCapture=field(nativeFields,'Retained detailed paths per candidate · first IDs','campaign-native-capture',nativeDefaults.capture_paths,'number');nativeCapture.min='1';nativeCapture.max='20';
      readNativeCalendar=window.nativeReplay.calendarControls(nativeFields,nativeDefaults,{prefix:'campaign-native'});
      const note=node('p','Native account size ceiling: 40 MNQ, with lower user, policy and provider limits still applied. Total paths are divided equally across declared start dates. Every start must follow the admitted source IS window. Capture limits affect retained detail only; all paths enter candidate metrics. Evaluation acquisition means remain unresolved when any path is censored.');note.style.gridColumn='1 / -1';nativeFields.append(note);
    }
    const evalFields=node('div');evalFields.className='prop-fields';form.append(evalFields);
    for(const [label,id,value]of [['Evaluation price · USD','campaign-price','30'],['Activation fee · USD','campaign-activation','40']]){const input=field(evalFields,label,id,value,'number');input.min='0';input.step='0.01';}
    field(evalFields,'Retry delay after failure · calendar days','campaign-retry-delay','0','number');
    field(evalFields,'Activation delay after pass · eligible sessions','campaign-activation-delay','1','number');
    field(evalFields,'Acquisition chains','campaign-chains','1000','number');field(evalFields,'Acquisition seed','campaign-chain-seed','45','number');
    const fundedFields=node('div');fundedFields.className='prop-fields';form.append(fundedFields);
    field(fundedFields,'Receipt horizon · calendar days','campaign-horizon','90','number');field(fundedFields,'Receipt delay · calendar days','campaign-delay','0','number');
    field(fundedFields,'Maximum breach probability (0–1)','campaign-breach','1','number').step='any';
    const note=node('p','Uses captured source costs. Fixed sizes preserve the existing linear MNQ scenarios; explicit sizing policies use causal stop and account state subject to source admission. The declared weekday calendar, prices and settlement delays are assumptions, not verified provider forecasts.');form.append(note);
    const changePhase=()=>{evalFields.hidden=phase.value!=='evaluation';fundedFields.hidden=phase.value!=='funded';syncProfile();};phase.onchange=changePhase;changePhase();
    for(const [id,min,max]of [['campaign-paths',1,20000],['campaign-chains',1,20000],['campaign-horizon',1,3650],['campaign-delay',0,365],['campaign-breach',0,1],['campaign-retry-delay',0,365],['campaign-activation-delay',0,365]]){const input=$('#'+id);input.min=min;input.max=max;}
    let previousExecution='trade_path';const executionValues={};
    function nativeMode(){return execution.value==='native';}
    function synchronizeNativePaths(){if(nativeMode()){$('#campaign-chains').value=$('#campaign-paths').value;$('#campaign-chain-seed').value=$('#campaign-seed').value;}}
    function changeExecution(){
      const active=nativeMode();executionValues[previousExecution]=Object.fromEntries(['campaign-paths','campaign-seed','campaign-block','campaign-chains','campaign-chain-seed'].map(id=>[id,$('#'+id).value]));
      const values=executionValues[execution.value]||(active?{'campaign-paths':nativeDefaults.simulations,'campaign-seed':nativeDefaults.seed,'campaign-block':nativeDefaults.block_sessions,'campaign-chains':nativeDefaults.simulations,'campaign-chain-seed':nativeDefaults.seed}:{});
      for(const [id,value]of Object.entries(values))$('#'+id).value=value;
      previousExecution=execution.value;nativeFields.hidden=nativeFields.disabled=!active;calendarNote.hidden=active;
      for(const id of ['campaign-start','campaign-chains','campaign-chain-seed','campaign-horizon']){const input=$('#'+id);input.closest('label').hidden=active;input.disabled=active;}
      $('#campaign-paths').min=active?'2':'1';$('#campaign-paths').max=active?'512':'20000';
      $('#campaign-block').closest('label').firstChild.textContent=active?'Contiguous observed source sessions per block':'Resampling block · weekdays';
      note.textContent=active?'Actual native strategy reruns use the declared policy at each causal opportunity. Source costs are charged once; planning costs must match the admitted source. Modeled target calendar and settlement assumptions remain unverified.':'Uses captured source costs. Fixed sizes preserve the existing linear MNQ scenarios; explicit sizing policies use causal stop and account state subject to source admission. The declared weekday calendar, prices and settlement delays are assumptions, not verified provider forecasts.';
      synchronizeNativePaths();syncProfile();
    }
    execution.addEventListener('change',changeExecution);$('#campaign-paths').addEventListener('input',synchronizeNativePaths);$('#campaign-seed').addEventListener('input',synchronizeNativePaths);
    const count=node('p','Candidate count will be calculated from the selected saved trials and sizes.');count.id='campaign-count';form.append(count);
    const check=button(form,'Save and check candidates','campaign-check'),run=button(form,'Run campaign','campaign-run');run.disabled=true;
    const status=node('p');status.id='campaign-status';status.setAttribute('role','status');form.append(status);
    let campaignId=null,revision=0,windowVersion=0,windowPending=false,automaticWindow=null,windowTimer=null;
    function selectedSources(forWindow=false){
      return [...sources.children].map(row=>{const kind=row.querySelector('.campaign-kind').value;
        const id=row.querySelector('.campaign-reference').value.trim();if(!id)throw Error('Choose a saved source in every row to derive the IS window.');
        const value={[kind]:id,sizes:forWindow?[1]:integers(row.querySelector('.campaign-sizes').value)};
        if(!forWindow){const policies=row.readSizing();if(policies)value.sizing_policies=policies;}
        const trials=row.querySelector('.campaign-trials').value;if(kind==='optimization_id'&&trials.trim())value.trials=integers(trials);
        return value;});
    }
    async function refreshWindow(){
      clearTimeout(windowTimer);const version=++windowVersion;windowPending=true;automaticWindow=null;
      check.disabled=true;run.disabled=true;isFirst.disabled=true;isLast.disabled=true;
      windowStatus.textContent='Finding common saved IS coverage…';
      try{
        const result=await api('/api/research-campaigns/source-window',{sources:selectedSources(true)});
        if(version!==windowVersion||!form.isConnected)return;
        automaticWindow=result.is_window;
        for(const input of [isFirst,isLast]){input.min=automaticWindow.first_session;input.max=automaticWindow.last_session;}
        isFirst.value=automaticWindow.first_session;isLast.value=automaticWindow.last_session;
        windowStatus.textContent=`IS window derived from all selected sources: ${isFirst.value} → ${isLast.value} (CME session dates). You may narrow it; observed zero-trade sessions are included.`;
      }catch(e){if(version!==windowVersion||!form.isConnected)return;isFirst.value='';isLast.value='';windowStatus.textContent=e.message;}
      finally{if(version===windowVersion&&form.isConnected){windowPending=false;isFirst.disabled=false;isLast.disabled=false;check.disabled=!automaticWindow;}}
    }
    function queueWindow(){
      ++windowVersion;clearTimeout(windowTimer);windowPending=true;automaticWindow=null;check.disabled=true;run.disabled=true;
      isFirst.disabled=true;isLast.disabled=true;windowStatus.textContent='Finding common saved IS coverage…';
      windowTimer=setTimeout(refreshWindow,200);
    }
    function invalidate(){revision++;campaignId=null;run.disabled=true;count.textContent='Candidate count will be recalculated when checking.';status.textContent='Configuration changed; save and check candidates.';}
    form.addEventListener('input',invalidate);form.addEventListener('change',invalidate);form.onsubmit=e=>e.preventDefault();
    form.addEventListener('change',e=>{if(e.target.matches('.campaign-kind,.campaign-reference'))refreshWindow();});
    form.addEventListener('input',e=>{if(e.target.matches('.campaign-trials'))queueWindow();
      else if(e.target===isFirst||e.target===isLast)windowStatus.textContent=`Custom IS window within available coverage ${automaticWindow?.first_session} → ${automaticWindow?.last_session}. Use full common IS window to reset.`;});
    check.onclick=async()=>{if(!form.reportValidity())return;const version=revision;check.disabled=true;run.disabled=true;
      try{
        const isEval=phase.value==='evaluation',p={profile_id:profile.value,rule_version:defaults.profiles[profile.value]};
        if(isEval)Object.assign(p,{evaluation_price:$('#campaign-price').value,activation_fee:$('#campaign-activation').value});
        const sampling={block_weekdays:number('campaign-block')};if(isEval)Object.assign(sampling,{chain_simulations:number(nativeMode()?'campaign-paths':'campaign-chains'),chain_seed:number(nativeMode()?'campaign-seed':'campaign-chain-seed')});
        const search_settings={calendar:{start_dates:[$('#campaign-start').value]}};
        if(nativeMode()){const declared=readNativeCalendar();search_settings.calendar=declared.calendar;search_settings.native_execution={model:nativeDefaults.model,horizon_calendar_days:Number(nativeHorizon.value),capture_paths:Number(nativeCapture.value),early_closes:declared.early_closes};}
        if(!isEval)Object.assign(search_settings,{horizon_calendar_days:nativeMode()?Number(nativeHorizon.value):number('campaign-horizon'),receipt_delay_calendar_days:number('campaign-delay'),constraints:{maximum_account_breach_probability:number('campaign-breach')}});
        const body={campaign_id:crypto.randomUUID().replaceAll('-',''),phase:phase.value,profile:p,
          sources:selectedSources(),
          is_window:{first_session:$('#campaign-is-start').value,last_session:$('#campaign-is-end').value},
          simulation:{simulations:number('campaign-paths'),seed:number('campaign-seed'),...(nativeMode()?{max_micros:40}:{})},sampling,costs:{mode:'source'},search_settings,
          ...(isEval?{retry:{retry_delay_calendar_days:number('campaign-retry-delay'),activation_delay_sessions:number('campaign-activation-delay')}}:{})};
        status.textContent='Counting candidates and checking saved source identity, costs and risk…';
        let c;
        try{c=await api('/api/research-campaigns',body);}
        catch(e){
          if(e.detail?.code!=='candidate_confirmation_required')throw e;
          if(version!==revision)return;
          const total=e.detail.candidate_count;count.textContent=`${total} candidates selected.`;
          if(!window.confirm(`This campaign contains ${total} candidates, above the 128-candidate confirmation threshold. Every candidate will be evaluated. Larger searches require more time and storage. Continue?`)){
            status.textContent=`Cancelled: ${total} candidates require confirmation. No campaign was saved.`;return;
          }
          if(version!==revision)return;
          body.confirmed_candidate_count=total;
          c=await api('/api/research-campaigns',body);
        }
        if(version!==revision)return;
        const checks=await api(`/api/research-campaigns/${c.campaign_id}/check`,{});
        if(version!==revision)return;
        campaignId=c.campaign_id;count.textContent=`${checks.candidate_search_count} candidates selected${c.manifest.candidate_confirmation?.confirmed_count?' · confirmed':''}.`;run.disabled=false;status.textContent=`${checks.candidate_search_count} compatible candidates · ${c.manifest.selection_objective} · IS only. Calendar automatically covered through ${c.manifest.request.calendar.coverage_end}. Ready to run.`;
        const prior=form.querySelector('.campaign-checks');if(prior)prior.remove();const checkDetails=node('div');checkDetails.className='campaign-checks';
        const nativeCandidates=(checks.candidates||[]).filter(row=>row.manifest.native_source_check?.native_forecast_plan);
        if(nativeCandidates.length){
          checkDetails.append(node('h3','Native candidate work'),node('p','Every declared candidate reruns actual strategy bars. These server-derived work bounds include source validation and prior-only warmup; modeled target dates are not observed future data.'));
          dataTable(checkDetails,['Strategy / policy','Paths','Observed source sessions','Total bar work','Estimated retained bytes'],nativeCandidates.map(row=>{const plan=row.manifest.native_source_check.native_forecast_plan;return [row.manifest.strategy.id+' · '+sizingLabel(row.manifest.configuration),plan.simulations,plan.catalogue.source_sessions,plan.work.total_bar_work,plan.work.estimated_capture_bytes];}),'campaign-native-work');
          const inspect=select(checkDetails,'Inspect native source pools · presentation only','campaign-native-check-inspect',nativeCandidates.map(row=>[row.candidate_id,row.manifest.strategy.id+' · '+sizingLabel(row.manifest.configuration)])),view=node('div');checkDetails.append(view);
          const show=()=>{view.replaceChildren();const row=nativeCandidates.find(row=>row.candidate_id===inspect.value);if(row)window.nativeReplay.forecastPlan(view,row.manifest.native_source_check.native_forecast_plan,{prefix:'campaign-native-plan'});};inspect.onchange=show;show();
          status.textContent=`${checks.candidate_search_count} compatible native candidates · IS only. Review the saved source-block law, modeled calendar and full work before running.`;
        }
        if(checks.candidates?.some(row=>row.manifest.configuration.sizing)){checkDetails.append(node('h3','Declared sizing candidates'));dataTable(checkDetails,['Source','Sizing policy / hard cap','Quantity bounds','Cushion guards'],checks.candidates.map(row=>{const c=row.manifest.configuration,p=c.sizing?.policy;return [row.manifest.strategy.id,sizingLabel(c),p?`${p.minimum_contracts}–${p.maximum_contracts} MNQ`:'Fixed size',p?[p.constrain_to_account_cushion?'Account':'',p.constrain_to_daily_cushion?'Daily':''].filter(Boolean).join(', ')||'Not imposed':'Not imposed'];}));checkDetails.append(node('p','Every declared candidate is retained. Planned stop loss determines quantity only; source costs and observed paths are preserved under the admitted source assumptions.'));}
        details(checkDetails,'Source checks and saved candidate definitions',checks);form.append(checkDetails);
      }catch(e){status.textContent=e.message;}finally{check.disabled=windowPending||!automaticWindow;}
    };
    run.onclick=async()=>{if(!campaignId)return;run.disabled=true;try{await api(`/api/research-campaigns/${campaignId}/run`,{});location.hash=`#backtests/prop/campaign/${campaignId}`;}catch(e){status.textContent=e.message;run.disabled=false;}};
    refreshWindow();
  }
  const format = value => value===null||value===undefined?'Unresolved / unavailable':typeof value==='number'?value.toLocaleString(undefined,{maximumFractionDigits:3}):String(value);
  const pct = value => value==null?'Unresolved / unavailable':format(value*100)+'%';
  function dataTable(parent,labels,rows,id=''){
    const wrap=node('div');wrap.className='campaign-table-scroll';wrap.tabIndex=0;
    const table=node('table');table.className='prop-table';table.id=id;const head=node('thead'),tr=node('tr');
    for(const label of labels){const th=node('th',label);th.scope='col';tr.append(th);}head.append(tr);table.append(head);
    const body=node('tbody');for(const values of rows){const row=node('tr');for(const value of values){const cell=node('td');cell.append(value instanceof Node?value:node('span',format(value)));row.append(cell);}body.append(row);}table.append(body);wrap.append(table);parent.append(wrap);return table;
  }
  function renderSizing(parent,candidate){
    parent.replaceChildren();const config=candidate.manifest.configuration;if(!config.sizing)return;
    if(candidate.native_forecast){parent.append(node('h3','Native sizing policy'),node('p',sizingLabel(config)),node('p','Actual strategy opportunities, fills and account transitions are rerun for each modeled path. Inspect retained native paths below for causal stops, decision quantities, skipped opportunities and source versus target dates. All paths remain in complete candidate metrics.'));return;}
    const evidence=candidate.component?.provenance?.sizing||candidate.provenance?.sizing;
    parent.append(node('h3','Sizing decisions'),node('p',sizingLabel(config)));
    const external=candidate.manifest.source?.backtest.run_metadata.source?.kind==='external_trade_export';
    parent.append(node('p','Quantities use the state available at each decision. Planned stop risk includes declared planning costs; it is not an additional P&L deduction. '+(external?'Source execution invariance and observation completeness remain exporter declarations.':'Native fixed-contract scenarios retain the saved source scaling assumptions; native risk-based policies require a new strategy replay.')+' Gaps can exceed planned risk.'));
    if(!evidence){parent.append(node('p','Detailed sizing decisions are unavailable in this saved report.'));return;}
    const summary=evidence.summary||{};
    dataTable(parent,['Decisions','Executed trades','Skipped trades','Minimum MNQ','Maximum MNQ'],[[summary.decision_count,summary.trade_count,summary.skipped_count,summary.min_quantity,summary.max_quantity]],'campaign-sizing-summary');
    const quantities=Object.entries(summary.quantity_counts||{}).map(([quantity,count])=>`${quantity} MNQ: ${count}`).join(' · '),reasons=Object.entries(summary.reason_counts||{}).map(([reason,count])=>`${reason.replaceAll('_',' ')}: ${count}`).join(' · ');
    parent.append(node('p','Quantity counts · '+(quantities||'No decisions')),node('p','Cap and skip reasons · '+(reasons||'No limits or skips recorded')));
    const observations=evidence.decisions||[];
    parent.append(node('p',`${observations.length} retained decisions of ${summary.decision_count??'unknown'} total. ${evidence.trace_complete?'The saved trace is complete.':'The saved trace is limited; aggregate counts cover the full calculation.'} ${evidence.trace_limit!=null?'Retention limit: '+evidence.trace_limit+'. ':''}Trace retention never removes candidates or simulated opportunities.`));
    const disclosure=node('details');disclosure.append(node('summary','Inspect retained trade decisions'));parent.append(disclosure);
    disclosure.append(node('p','Scroll the table horizontally for planned risk, cap reasons and account state. Path and session labels refer to the simulation; source trade IDs identify the sampled observations.'));
    const buttons=node('div');buttons.className='prop-inline-actions';disclosure.append(buttons);const previous=button(buttons,'Previous decisions','campaign-sizing-previous'),next=button(buttons,'Next decisions','campaign-sizing-next'),position=node('p'),table=node('div');disclosure.append(position,table);let offset=0;
    function draw(){table.replaceChildren();previous.disabled=offset===0;next.disabled=offset+25>=observations.length;position.textContent=observations.length?`${offset+1}–${Math.min(offset+25,observations.length)} of ${observations.length} retained decisions`:'No retained trade decisions.';
      dataTable(table,['Source trade','Path / session','Action','Requested MNQ','Chosen MNQ','Reference value · USD','Risk budget · USD','Planned risk / MNQ · USD','Planned total risk · USD','Caps / reasons','Account state'],observations.slice(offset,offset+25).map(observation=>{const d={...observation.decision,...observation},state=node('details');state.append(node('summary','Before / after decision'));for(const [label,value]of [['Before',d.state_before],['After',d.state_after]]){if(value){state.append(node('h4',label));dataTable(state,['State','Value'],Object.entries(value).map(([k,v])=>[k.replaceAll('_',' '),v]));}}
        const caps=Object.entries(d.caps||{}).map(([key,value])=>`${key.replaceAll('_',' ')}: ${value}`).join(' · '),reasons=(d.reasons||[]).map(value=>value.replaceAll('_',' ')).join(', ');
        const context=[d.path_index!=null?'Path '+d.path_index:null,d.attempt!=null?'attempt '+d.attempt:null,d.calendar_date||d.session_date||(d.session_index!=null?'session '+d.session_index:null)].filter(Boolean).join(' · ');
        return [d.source_trade_id??d.trade_id,context||'Unavailable',d.action,d.requested_contracts,d.quantity,d.denominator_value,d.risk_budget,d.planned_risk_per_mnq,d.planned_total_risk,[caps,reasons].filter(Boolean).join('; '),state];}),'campaign-sizing-decisions');}
    previous.onclick=()=>{offset=Math.max(0,offset-25);draw();};next.onclick=()=>{offset+=25;draw();};draw();
    details(parent,'Saved sizing policy and planning assumptions',evidence.configuration||config.sizing);
  }
  function svgNode(tag,attrs={},text){const n=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v]of Object.entries(attrs))n.setAttribute(k,String(v));if(text!==undefined)n.textContent=text;return n;}
  function chart(parent,rows,phase,frontier,assessment=false){
    const box=node('div');box.id='campaign-chart';parent.append(box);
    if(phase==='evaluation'){
      box.append(node('h3','Acquisition cost vs calendar time'),node('p',assessment?'Frozen OOS family only; no OOS frontier or selection is computed.':'Orange rings mark the saved IS Pareto frontier. Filters hide points without recomputing dominance. Unresolved points remain in the table.'));
      const points=rows.filter(r=>r.metrics.cost_per_funded!=null&&r.metrics.expected_calendar_days_to_funded!=null);
      if(!points.length){box.append(node('p','No resolved cost/time points to plot.'));return;}
      const svg=svgNode('svg',{viewBox:'0 0 820 340',role:'img','aria-label':'Acquisition cost versus calendar time with Pareto frontier'});
      const maxC=Math.max(1,...points.map(r=>r.metrics.cost_per_funded))*1.1,maxT=Math.max(1,...points.map(r=>r.metrics.expected_calendar_days_to_funded))*1.1;
      const x=r=>80+r.metrics.expected_calendar_days_to_funded/maxT*710,y=r=>285-r.metrics.cost_per_funded/maxC*250;
      svg.append(svgNode('path',{d:'M80 25 V285 H795',fill:'none',stroke:'#657783'}),svgNode('text',{x:350,y:330},'Expected calendar days to funding'),svgNode('text',{x:5,y:18},'Cost · USD'));
      for(let i=0;i<=4;i++){const t=i/4;svg.append(svgNode('text',{x:75,y:289-t*250,'text-anchor':'end'},format(t*maxC)),svgNode('text',{x:80+t*710,y:306,'text-anchor':'middle'},format(t*maxT)));}
      const edge=points.filter(r=>frontier.includes(r.candidate_id)).sort((a,b)=>x(a)-x(b));
      if(edge.length>1)svg.append(svgNode('polyline',{points:edge.map(r=>`${x(r)},${y(r)}`).join(' '),fill:'none',stroke:'#c75a08','stroke-width':2}));
      for(const r of points){const isFrontier=frontier.includes(r.candidate_id),c=svgNode('circle',{cx:x(r),cy:y(r),r:isFrontier?8:5,fill:isFrontier?'#fff4e8':'#367781',stroke:isFrontier?'#c75a08':'#367781','stroke-width':3,'data-candidate-id':r.candidate_id,'data-frontier':isFrontier});c.append(svgNode('title',{},`${r.manifest.strategy.id} · ${sizingLabel(r.manifest.configuration)} · $${format(r.metrics.cost_per_funded)} · ${format(r.metrics.expected_calendar_days_to_funded)} days${isFrontier?' · Pareto frontier':''}`));svg.append(c);}box.append(svg);
    }else{
      box.append(node('h3','Funded payout distribution'),node('p','All-start received cash, including zero-payout paths. Choose a visible strategy/size; selection here only changes this chart.'));
      if(!rows.length){box.append(node('p','No matching candidates.'));return;}
      const choose=select(box,'Distribution candidate','campaign-distribution',rows.map(r=>[r.candidate_id,`${r.manifest.strategy.id} · ${sizingLabel(r.manifest.configuration)} · ${r.candidate_id.slice(0,8)}`]));
      const plot=node('div');box.append(plot);
      function draw(){plot.replaceChildren();const r=rows.find(r=>r.candidate_id===choose.value),values=r.distribution?.values;
        if(r.status!=='estimated')plot.append(node('p',r.uncertainty?.historical_mean?.status==='insufficient_evidence'&&r.censoring?.unresolved_horizon_paths===0?'Historical mean evidence is unresolved. These conditional account simulations do not supply sufficient historical evidence for selection.':'Incomplete horizon: plotted values are accrued cash lower bounds, not completed payout estimates.'));if(!values?.length){plot.append(node('p','Distribution unavailable for this saved report.'));return;}
        const max=Math.max(1,...values),bins=Array(10).fill(0);for(const value of values)bins[Math.min(9,Math.floor(value/max*10))]++;
        const svg=svgNode('svg',{viewBox:'0 0 820 280',role:'img','aria-label':'Funded cash receipt histogram including zero paths'}),peak=Math.max(...bins);
        bins.forEach((count,i)=>{const bar=svgNode('rect',{x:70+i*72,y:220-count/peak*185,width:64,height:count/peak*185,fill:'#367781','data-count':count});bar.append(svgNode('title',{},`$${format(i*max/10)}–$${format((i+1)*max/10)}: ${count} paths`));svg.append(bar,svgNode('text',{x:70+i*72,y:242},format(i*max/10)));});svg.append(svgNode('text',{x:290,y:275},'Trader cash received · USD'));plot.append(svg,node('p',`${values.length} paths · Median $${format(r.metrics.median_payouts)} · P10 $${format(r.metrics.p10_payouts)} · P90 $${format(r.metrics.p90_payouts)}`));
      }choose.onchange=draw;draw();
    }
  }
  function metricOverview(parent,rows,phase){
    if(!rows.length)return;
    const choose=select(parent,'Inspect candidate metrics · presentation only','campaign-inspect',rows.map(r=>[r.candidate_id,`${r.manifest.strategy.id} · ${sizingLabel(r.manifest.configuration)} · ${r.candidate_id.slice(0,8)}`]));
    const text=node('p'),cards=node('div'),sizing=node('section'),native=node('div');sizing.id='campaign-sizing-evidence';cards.className='campaign-metric-grid';parent.append(text,cards,sizing,native);
    function show(){const r=rows.find(r=>r.candidate_id===choose.value),m=r.metrics,u=r.uncertainty||{};cards.replaceChildren();
      text.textContent=Object.entries(r.manifest.strategy.parameters).map(([k,v])=>`${k}=${v}`).join(', ')+` · ${r.manifest.configuration.profile.profile_id} · ${r.status}. Inspection does not choose or freeze a winner.`;
      const values=phase==='evaluation'?[['Cost per funded account · USD',m.cost_per_funded],['Expected calendar days',m.expected_calendar_days_to_funded],['Pass probability',pct(m.pass_probability)],['Median funding days',m.median_calendar_days_to_funded],['P90 funding days',m.p90_calendar_days_to_funded],['Funded within 30 days',pct(m.probability_funded_by_day_30)],['Funded within 60 days',pct(m.probability_funded_by_day_60)],['Acquisition throughput · accounts/30d',m.funded_accounts_per_30_calendar_days],['MC cost SE · USD',u.cost_se],['MC mean time SE · days',u.calendar_mean_se],['Censoring status',r.reason||r.status]]:[['Expected payout cash · USD',m.expected_payouts],['Median / P10 / P90 · USD',`${format(m.median_payouts)} / ${format(m.p10_payouts)} / ${format(m.p90_payouts)}`],['Probability of first payout',pct(m.probability_first_payout)],['First payout days · conditional on payout',(m.probability_first_payout===0?'No payout observed':m.expected_days_to_first_payout_conditional_on_payout)],['Breach probability',pct(m.account_breach_probability)],['Survival to horizon',pct(m.probability_surviving_to_horizon)],['Risk constraint status',r.feasible?'Meets empirical limits':(r.constraint_violations||[]).join(', ')||'Unresolved'],['Pending cash · USD',m.expected_pending_cash],['MC mean cash SE · USD',u.mean_monte_carlo_se],['Unresolved horizon paths',r.censoring?.unresolved_horizon_paths],['Open lifetimes · censored',r.censoring?.lifetime_censored_paths]];
      for(const [label,value]of values){const card=node('div');card.append(node('span',label),node('strong',format(value)));cards.append(card);}
      if(u.historical_mean){const h=u.historical_mean;for(const [label,value]of [['Historical lower expected cash · USD',h.lower_mean_cash],['Historical mean evidence',h.status.replaceAll('_',' ')],['Observed historical sessions / blocks',`${h.history_session_count} / ${h.history_block_count}`],['Required historical sessions / blocks',`${h.configuration.minimum_history_sessions} / ${h.configuration.minimum_history_blocks}`],['Declared family / lower-tail rank',`${h.family_size} / ${h.tail_rank}`],['Maximum inner MC standard error · USD',h.mc_noise?.maximum_observed_standard_error],['Unresolved historical requirements',(h.reasons||[]).map(value=>value.replaceAll('_',' ')).join('; ')||'None']]){const card=node('div');card.append(node('span',label),node('strong',format(value)));cards.append(card);}}
      renderSizing(sizing,r);
      native.replaceChildren();if(r.native_forecast)window.nativeReplay.renderForecast(native,{native_forecast:r.native_forecast,source:{native_forecast_plan:r.manifest.native_source_check?.native_forecast_plan}},{prefix:'campaign-native-forecast',candidate:true,downloads:false});
    }choose.onchange=show;show();
  }
  function renderRuleReview(parent,review,readiness,analysisId){
    if(!review)return;
    const section=node('details');section.className='phase-provider-review';section.append(node('summary',`Provider rules and deployment limits · ${readiness?.status||review.status||'UNVERIFIED'}`));
    section.append(node('p','VERIFIED_DOCUMENT means published wording was checked on the saved review date. It does not establish numerical model parity, account entitlement, execution quality or deployment approval. Historical reports retain their captured review.'));
    const display=value=>value===null||value===undefined?'Not specified':Array.isArray(value)?value.map(display).join(', '):typeof value==='object'?Object.entries(value).map(([key,item])=>`${key.replaceAll('_',' ')}: ${display(item)}`).join('; '):String(value);
    for(const profile of review.profiles||[]){
      const detail=node('details');detail.append(node('summary',`${profile.profile?.profile_id||'Profile'} · ${profile.phase} · reviewed ${profile.reviewed_at||'unknown'} · ${(profile.fields||[]).filter(row=>row.gap).length} declared gaps`));
      const gaps=node('ul');for(const item of profile.fields||[])if(item.gap)gaps.append(node('li',`${item.field.replaceAll('_',' ')}: ${item.gap}`));detail.append(gaps);
      const evidence=node('details');evidence.append(node('summary','Compare saved model values and published wording'));
      dataTable(evidence,['Field','Saved model value','Primary-document observation','Review status / gap','Primary source / review date'],(profile.fields||[]).map(item=>{
        const source=node('div');if(item.source_url)source.append(link('Open primary source',item.source_url));else source.append(node('span','Model assumption; no provider source'));
        source.append(node('p',item.reviewed_at||'Review date unavailable'));
        return [item.field.replaceAll('_',' '),display(item.model_value),item.primary_observation,`${item.status}${item.gap?`: ${item.gap}`:''}`,source];
      }));detail.append(evidence);section.append(detail);
    }
    section.append(node('p',`Deployment readiness: ${readiness?.status||'UNVERIFIED'}; production qualified: ${readiness?.production_qualified===true?'yes':'no'}.`));
    if(analysisId)section.append(link('Download captured provider rule review',`/api/prop-analyses/${analysisId}/files/provider_rules.json`));
    parent.append(section);
  }
  function renderNativeAssessment(parent,report){
    const rows=report.calculations.candidates;
    $('#prop-heading-title').textContent='Frozen native chronological OOS';
    $('#prop-heading-note').textContent='Actual later strategy bars · frozen account-state policies · no OOS selection';
    parent.append(node('h3','Actual chronological native OOS observations'),node('p','Each frozen policy reruns the original later bars once with its own strategy and provider account state. These are historical scenario outcomes, not Monte Carlo means. No OOS ranking, frontier or replacement choice is computed.'));
    dataTable(parent,['Frozen strategy / sizing policy','Actual OOS backtest','Account outcome','Actual trading profit · USD','Evaluation / activation fees · USD','Received / pending trader cash · USD'],rows.map(row=>{const c=row.native_chronological_replay;return [row.manifest.strategy.id+' · '+sizingLabel(row.manifest.configuration),row.native_backtest_id?link('Open actual controlled backtest',`#backtests/report/${row.native_backtest_id}`):'Unavailable',c?.outcome,c?.trading_profit,report.phase==='evaluation'?`${format(c?.paid_evaluation_fees)} / ${format(c?.paid_activation_fees)}`:'Not an Evaluation account',report.phase==='funded'?`${format(c?.cash_received)} / ${format(c?.pending_cash)}`:'Not a Funded account'];}),'campaign-native-oos-outcomes');
    const choice=select(parent,'Inspect frozen native outcome · presentation only','campaign-native-oos-inspect',rows.map(row=>[row.candidate_id,row.manifest.strategy.id+' · '+sizingLabel(row.manifest.configuration)])),view=node('div');parent.append(view);
    const show=()=>{view.replaceChildren();const row=rows.find(row=>row.candidate_id===choice.value);if(!row?.native_chronological_replay)return;const backtest=report.native_backtests?.[row.native_backtest_id]?.record;window.nativeReplay.renderChronologicalEvidence(view,row.native_chronological_replay,{phase:report.phase,backtest,receiptDelay:report.request.receipt_delay_calendar_days,prefix:'campaign-native-oos'});};choice.onchange=show;show();
    const downloads=node('div');downloads.className='campaign-downloads';parent.append(downloads);
    for(const [label,path]of [['Download chronological report','downloads/report.json'],['Download analysis ZIP','downloads/analysis.zip']])downloads.append(link(label,`/api/prop-analyses/${report.id}/${path}`),node('br'));
  }
  function renderAnalysis(report,campaign=null){
    $('#prop-config').hidden=true;$('#prop-report').hidden=false;$('#prop-delete').hidden=true;$('#prop-downloads').replaceChildren();
    const assessment=report.assessment,isEval=report.phase==='evaluation',conservative=report.calculations.candidates.some(r=>r.uncertainty?.historical_mean);
    $('#prop-heading-title').textContent=assessment?'Frozen OOS assessment':campaign?'Research campaign':'Independent phase analysis';
    $('#prop-heading-note').textContent=isEval?'Evaluation · minimize acquisition cost and calendar time':conservative?'Funded · maximize the historical lower bound on expected cash':'Funded · maximize expected trader cash received';
    $('#prop-back').href=`#backtests/report/${report.source.backtest.id}`;
    const target=$('#prop-report-content');target.replaceChildren();target.className='';const calc=report.calculations;
    const panel=node('section');panel.className='panel prop-panel';target.append(panel);
    panel.append(node('h2',assessment?'OOS assessment · frozen settings':campaign?.frozen?'Frozen IS selection':'IS candidate results'));
    panel.append(node('p',`${calc.candidates.length} completed candidates · ${report.model_version}. ${assessment?'Assessment only; no OOS ranking, frontier selection or replacement of IS choices.':isEval?'Selection uses IS only. Evaluation has no automatic winner.':conservative?'Selection uses IS only. Resolved Funded candidates are ranked by the declared historical lower bound on expected trader cash received.':'Selection uses IS only. Funded candidates are ranked by expected trader cash received.'} Estimated results; no provider parity or certified optimum.`));
    if(conservative)panel.append(node('p','Historical session blocks are resampled and expected cash is re-estimated for each history. The family-adjusted lower empirical percentile concerns the mean estimate; account P10 and Monte Carlo mean standard error describe different quantities. Unresolved history, tail-resolution or simulation-noise gates cannot supply a winner. This is not a future-performance guarantee.'),link('Download historical mean re-estimations',`/api/prop-analyses/${report.id}/files/historical_mean_cash.json`));
    renderRuleReview(panel,report.provider_rules,report.deployment_readiness,report.id);
    if(assessment){panel.append(link('Return to frozen IS campaign',`#backtests/prop/campaign/${assessment.campaign_id}`),node('p',assessment.interpretation));details(panel,'Pre-launch OOS access history',assessment.prior_access);}
    if(assessment&&calc.candidates.some(row=>row.native_chronological_replay)){renderNativeAssessment(panel,report);return;}
    const filters=node('div');filters.className='prop-fields';panel.append(filters);
    const opts=(key,label)=>[['',label],...[...new Set(calc.candidates.map(key))].sort().map(v=>[String(v),String(v)])];
    const strategy=select(filters,'Filter by strategy','campaign-filter-strategy',opts(r=>r.manifest.strategy.id,'All strategies'));
    const hasPolicies=calc.candidates.some(r=>r.manifest.configuration.sizing);
    const size=select(filters,hasPolicies?'Filter by fixed size / hard cap':'Filter by size','campaign-filter-size',opts(r=>r.manifest.configuration.micros,hasPolicies?'All sizes / caps':'All sizes'));
    const profile=select(filters,'Filter by account profile','campaign-filter-profile',opts(r=>r.manifest.configuration.profile.profile_id,'All profiles'));
    const count=node('p');count.id='campaign-visible-count';panel.append(count);
    const graph=node('div'),comparison=node('div');panel.append(graph,comparison);
    const allowed=assessment?[]:isEval?calc.frontier:calc.ranking;
    const picked=new Set(campaign?.frozen?.candidate_ids||[]),names=new Map(Object.entries(campaign?.frozen?.names||{}));
    const displayed=[...calc.candidates].sort((a,b)=>isEval?Number(b.pareto_member)-Number(a.pareto_member):(a.rank??Infinity)-(b.rank??Infinity));
    function draw(){
      const rows=displayed.filter(r=>(!strategy.value||r.manifest.strategy.id===strategy.value)&&(!size.value||String(r.manifest.configuration.micros)===size.value)&&(!profile.value||r.manifest.configuration.profile.profile_id===profile.value));
      graph.replaceChildren();comparison.replaceChildren();count.textContent=`${rows.length} of ${calc.candidates.length} candidates shown. Saved frontier/ranks stay fixed.`;
      metricOverview(graph,rows,report.phase);chart(graph,rows,report.phase,assessment?[]:calc.frontier,!!assessment);
      const labels=['Freeze / name','Saved strategy / source',`Account / rules / ${assessment?'OOS':'IS'} window`,hasPolicies?'Sizing policy / hard cap':'MNQ','Status',...(isEval?['Cost per funded · USD','Expected calendar days','Pass probability','Median days','P90 days','Funded by 30d','Funded by 60d','Accounts / 30d','Pareto frontier','MC cost SE / days SE','Censoring']:['Expected cash · USD','Median cash','P10 cash','P90 cash','First payout probability','Days to first payout · conditional','Breach probability','Survival to horizon','Risk constraints','Pending cash · USD','Rank','MC mean SE','Censoring'])];
      const values=rows.map(r=>{
        const config=r.manifest.configuration,m=r.metrics,u=r.uncertainty||{},pick=node('div'),box=node('input');box.type='checkbox';box.value=r.candidate_id;box.className='campaign-pick';box.setAttribute('aria-label','Freeze '+r.candidate_id.slice(0,12));box.disabled=!campaign||!!campaign.frozen||!allowed.includes(r.candidate_id);box.checked=picked.has(r.candidate_id);box.onchange=()=>box.checked?picked.add(r.candidate_id):picked.delete(r.candidate_id);pick.append(box);
        const name=field(pick,'Candidate name','',names.get(r.candidate_id)||frozenName(assessment,r)||`${r.manifest.strategy.id} · ${sizingLabel(config)} · ${r.candidate_id.slice(0,8)}`);names.set(r.candidate_id,name.value);name.className='campaign-candidate-name';name.maxLength=120;name.disabled=box.disabled;name.oninput=()=>names.set(r.candidate_id,name.value);
        const s=node('div');s.append(link(r.manifest.strategy.id,`#backtests/report/${config.source.source_backtest_id}`),node('p',Object.entries(r.manifest.strategy.parameters).map(([k,v])=>`${k}=${v}`).join(', ')));details(s,'Source identity and provenance',r.manifest);
        const rules=node('div',`${config.profile.profile_id} · ${config.profile.rule_version}`);rules.append(node('p',`${assessment?'OOS':'IS'} ${config.period?.first_session} → ${config.period?.last_session}`));details(rules,'Saved rules, costs and search settings',{profile:config.profile,account_rules:r.provenance?.rules,costs:config.costs,sampling:config.sampling,simulation:config.simulation,calendar:report.request?.calendar,horizon:report.request?.horizon_calendar_days});
        const status=report.phase==='funded'&&r.status==='estimated'&&!r.feasible?'infeasible':r.status;
        const cells=isEval?[m.cost_per_funded,m.expected_calendar_days_to_funded,pct(m.pass_probability),m.median_calendar_days_to_funded,m.p90_calendar_days_to_funded,pct(m.probability_funded_by_day_30),pct(m.probability_funded_by_day_60),m.funded_accounts_per_30_calendar_days,assessment?'Assessment only':r.pareto_member? 'Frontier':'Outside frontier',`${format(u.cost_se)} / ${format(u.calendar_mean_se)}`,`${r.censoring?.chain_paths??'Unknown'} unresolved chains · ${r.reason||r.status}`]:[m.expected_payouts,m.median_payouts,m.p10_payouts,m.p90_payouts,pct(m.probability_first_payout),(m.probability_first_payout===0?'No payout observed':m.expected_days_to_first_payout_conditional_on_payout),pct(m.account_breach_probability),pct(m.probability_surviving_to_horizon),r.feasible?'Meets empirical limits':(r.constraint_violations||[]).join(', ')||'Unresolved',m.expected_pending_cash,r.rank??(assessment?'Assessment only':'Not ranked'),u.mean_monte_carlo_se,`${r.censoring?.unresolved_horizon_paths??0} incomplete horizons; ${r.censoring?.lifetime_censored_paths??0} open lifetimes`];
        if(conservative)cells.push(m.historical_lower_mean_cash,u.historical_mean?.status);
        return [pick,s,rules,hasPolicies?sizingLabel(config):config.micros,status,...cells];
      });if(conservative)labels.push('Historical lower mean · USD','Historical mean evidence');dataTable(comparison,labels,values,'campaign-candidates');
      if(!rows.length)comparison.append(node('p','No candidates match these filters.'));
    }
    for(const filter of [strategy,size,profile])filter.onchange=draw;draw();
    if(isEval&&!assessment){panel.append(node('h3','Marginal acceleration costs'));
      dataTable(panel,['Slower frontier candidate','Faster frontier candidate','USD / calendar day saved'],(calc.marginal_acceleration_cost||[]).map(r=>[r.slow_candidate_id.slice(0,12),r.fast_candidate_id.slice(0,12),r.usd_per_calendar_day_saved??r.reason]),'campaign-marginal');
      if(!calc.marginal_acceleration_cost?.length)panel.append(node('p','No adjacent distinct frontier trade-offs to compare.'));
    }
    details(panel,isEval?'Frontier and marginal acceleration costs':'Ranking, constraints and uncertainty',{...calc,candidates:undefined});
    details(panel,'Candidate metrics, risk, uncertainty and assumptions',calc.candidates.map(r=>({candidate_id:r.candidate_id,metrics:r.metrics,status:r.status,feasible:r.feasible,constraint_violations:r.constraint_violations,rank:r.rank,pareto_member:r.pareto_member,censoring:r.censoring,uncertainty:r.uncertainty,assumptions:r.assumptions})));
    panel.append(node('p','Monte Carlo uncertainty is conditional on the saved source/model; it does not measure future market or provider-rule uncertainty. Open funded lifetimes can be censored while horizon cash is complete. Full observations and intervals are in JSON/ZIP.'));
    if(campaign){
      const actions=node('div');panel.append(actions);
      if(!campaign.frozen){const rationale=field(actions,'Selection rationale','campaign-rationale','');const freeze=button(actions,'Freeze selected candidates','campaign-freeze');const status=node('p');actions.append(status);
        freeze.onclick=async()=>{try{if(!rationale.reportValidity())return;freeze.disabled=true;await api(`/api/research-campaigns/${campaign.campaign_id}/freeze`,{candidate_ids:[...picked],names:Object.fromEntries([...picked].map(id=>[id,names.get(id)||`${id.slice(0,12)}`])),rationale:rationale.value});await watch(campaign.campaign_id,()=>location.hash===`#backtests/prop/campaign/${campaign.campaign_id}`);}catch(e){status.textContent=e.message;freeze.disabled=false;}};
      }else {details(actions,'Frozen package',campaign.frozen);if(calc.candidates.some(r=>r.manifest.source?.backtest.run_metadata.source?.kind==='external_trade_export'))actions.append(node('p','Frozen settings are saved. Automatic OOS launch is unavailable for imported trades: no native strategy or untouched native split exists. Exporter research declarations do not establish an unseen OOS test.'));else assessmentControls(actions,campaign);}
      for(const kind of ['campaign.json','results.csv','results.json','source_checks.json','analysis.zip',...(campaign.frozen?['frozen_package.json']:[])])actions.append(link('Download '+kind,`/api/research-campaigns/${campaign.campaign_id}/exports/${kind}`),node('br'));
      details(panel,'Campaign declaration and numerical identity',campaign.manifest);
    }else {const downloads=node('div');downloads.className='campaign-downloads';for(const [label,path]of [['Download analysis ZIP','downloads/analysis.zip'],['Download metrics CSV','files/phase_metrics.csv'],['Download metrics JSON','files/phase_metrics.json']]){const a=link(label,`/api/prop-analyses/${report.id}/${path}`);a.className='button secondary';downloads.append(a);}panel.append(downloads);}
    if(hasPolicies)panel.append(link('Download retained sizing decisions (CSV)',`/api/prop-analyses/${report.id}/files/sizing_decisions.csv`));
    if(calc.candidates.some(row=>row.native_forecast))for(const name of ['native_forecasts.json','native_forecast_paths.json','native_forecast_schedules.json','native_forecast_captures.json'])panel.append(node('br'),link('Download '+name,`/api/prop-analyses/${report.id}/files/${name}`));
  }
  async function assessmentControls(parent,campaign){
    const section=node('section');section.id='campaign-assessments';parent.append(section);const native=Boolean(campaign.declaration?.search_settings?.native_execution);section.append(node('h3','Manual final OOS assessment'),node('p',native?'Rerun the actual OOS bars under each frozen native strategy, sizing policy and account profile. Actual chronological fees, deductions and trader receipts are separate from the earlier modeled forecasts. Results append without ranking or replacing IS selections. Previously accessed data is not untouched final OOS.':'Runs ordinary OOS backtests from the frozen IS parents, then assesses this named family at its frozen sizes, profiles, costs, horizon, seeds and scenario calendar. Results append without ranking or changing IS selections. Previously accessed data is not untouched final OOS.'));
    details(section,'OOS access recorded at freeze',campaign.frozen.prior_access);
    const launch=button(section,'Launch OOS with frozen settings','campaign-launch-oos'),status=node('p'),history=node('div');status.id='campaign-oos-status';status.setAttribute('role','status');section.append(status,history);
    let requestId=null;
    async function refresh(){try{const data=await api(`/api/research-campaigns/${campaign.campaign_id}/assessments`);if(!section.isConnected)return;history.replaceChildren();
      for(const a of data.items){const row=node('div');row.append(node('p',`${a.created_at_utc} · ${a.status} · ${a.analysis?.progress||a.error||a.interpretation}`));
        for(const [parent,id]of Object.entries(a.oos_sources||{}))row.append(link(`OOS backtest · ${parent.slice(0,8)}`,`#backtests/report/${id}`),node('br'));
        if(a.analysis_id&&a.status==='complete')row.append(link('Open frozen OOS assessment',`#backtests/prop/job/${a.analysis_id}`),node('br'),link('Download assessment ZIP',`/api/prop-analyses/${a.analysis_id}/downloads/analysis.zip`));
        details(row,'Pre-launch access history',a.prior_access);history.append(row);}
      if(data.items.some(a=>['queued','running','launching'].includes(a.status)))setTimeout(refresh,700);
    }catch(e){status.textContent=e.message;}}
    launch.onclick=async()=>{launch.disabled=true;requestId??=crypto.randomUUID().replaceAll('-','');status.textContent='Launching ordinary OOS backtests with frozen parameters…';
      try{const a=await api(`/api/research-campaigns/${campaign.campaign_id}/assessments`,{request_id:requestId});requestId=null;status.textContent=`Assessment ${a.status}. IS selection remains frozen.`;await refresh();}catch(e){status.textContent=e.message;}finally{launch.disabled=false;}};
    await refresh();
  }
  function renderDeleted(receipt){
    $('#prop-config').hidden=true;$('#prop-report').hidden=false;$('#prop-delete').hidden=true;
    $('#prop-heading-title').textContent='Campaign deleted';$('#prop-heading-note').textContent='Backtests, reports and research-access history retained';
    $('#prop-status').textContent=`Campaign ${receipt.campaign_id} deleted. ${receipt.source_reference_count} source reference${receipt.source_reference_count===1?'':'s'} released.`;
    const target=$('#prop-report-content');target.replaceChildren();const panel=node('section');panel.className='panel prop-panel';target.append(panel);
    const result=node('p',`${receipt.source_reference_count} campaign source reference${receipt.source_reference_count===1?'':'s'} released. Backtests and completed reports were kept. Other workflows may still protect a source.`);result.id='campaign-deletion-result';result.setAttribute('role','status');panel.append(result);
    panel.append(link('Open research workspace','#backtests/research'),node('br'),link('Download campaign deletion record',`/api/research-campaigns/${receipt.campaign_id}/exports/deletion_record.json`));
    for(const analysis of receipt.retained_analyses)if(analysis.status==='complete')panel.append(node('br'),link('Open retained report '+analysis.id.slice(0,12),`#backtests/prop/job/${analysis.id}`));
    const sources=node('details');sources.append(node('summary','Retained source backtests'));
    for(const source of receipt.source_ids)sources.append(link('Open source '+source.slice(0,12),`#backtests/report/${source}`),node('br'));
    panel.append(sources);
  }
  async function deletionControls(c,current){
    const panel=node('section');panel.className='panel prop-panel';panel.id='campaign-deletion';panel.append(node('h2','Remove an unused campaign'));
    const notice=node('p');notice.id='campaign-delete-status';notice.setAttribute('role','status');panel.append(notice);
    const remove=button(panel,'Delete campaign','campaign-delete');remove.disabled=true;
    let allowed=false;
    $('#prop-report-content').append(panel);
    function show(preview){
      allowed=preview.deletable;
      remove.disabled=!preview.deletable;
      notice.textContent=preview.deletable?`${preview.source_reference_count} source reference${preview.source_reference_count===1?'':'s'} will be released. All source backtests, ${preview.retained_analyses.length} calculation record${preview.retained_analyses.length===1?'':'s'} and research-access history will be kept.`:preview.blockers.map(b=>b.message).join(' ');
      if(preview.other_source_references?.length)notice.textContent+=` Source backtests still protected by other workflows: ${preview.other_source_references.length}.`;
    }
    try{const preview=await api(`/api/research-campaigns/${c.campaign_id}/deletion`);if(!current())return;show(preview);}catch(error){notice.textContent=error.message;return;}
    remove.onclick=async()=>{
      remove.disabled=true;
      try{
        const fresh=await api(`/api/research-campaigns/${c.campaign_id}/deletion`);if(!current())return;
        if(fresh.deleted){renderDeleted(fresh);return;}show(fresh);if(!fresh.deletable)return;
        if(!window.confirm(`Delete ${fresh.phase} campaign ${c.campaign_id}?\n\nRelease ${fresh.source_reference_count} campaign source reference(s). Keep all backtests, ${fresh.retained_analyses.length} calculation record${fresh.retained_analyses.length===1?'':'s'} and research-access history.\n\nFrozen, assessed, running or dependent campaigns cannot be deleted.`))return;
        remove.disabled=true;
        const receipt=await api(`/api/research-campaigns/${c.campaign_id}`,{confirmation_sha256:fresh.confirmation_sha256},'DELETE');
        if(current())renderDeleted(receipt);
      }catch(error){
        notice.textContent=error.message;
        try{const latest=await api(`/api/research-campaigns/${c.campaign_id}/deletion`);if(!current())return;if(latest.deleted){renderDeleted(latest);return;}show(latest);notice.textContent=error.message+' '+notice.textContent;}catch(_){/* Keep the original failure visible. */}
      }
      finally{if(panel.isConnected)remove.disabled=!allowed;}
    };
  }
  async function watch(id,current){
    $('#prop-config').hidden=true;$('#prop-report').hidden=true;$('#prop-downloads').replaceChildren();$('#prop-report-content').replaceChildren();
    let stopping=false;
    while(current()){
      let c;
      try{c=await api('/api/research-campaigns/'+id);}catch(error){
        if(error.status!==404)throw error;
        const deleted=await api(`/api/research-campaigns/${id}/deletion`);
        if(current()&&deleted.deleted)renderDeleted(deleted);return;
      }
      if(!current())return;
      $('#prop-status').textContent=`${c.manifest.phase} campaign · ${c.status} · ${c.analysis?.progress||'Sources checked'} · ${c.status==='complete'?c.manifest.candidate_search_count+' / '+c.manifest.candidate_search_count+' completed candidates':c.manifest.candidate_search_count+' declared candidates'} · ${c.campaign_id}`;
      if(c.status==='complete'){const r=await api(`/api/prop-analyses/${c.analysis_id}/downloads/report.json`);if(current()){renderAnalysis(r,c);await deletionControls(c,current);}return;}
      if(['validated','error','cancelled'].includes(c.status)){
        $('#prop-report').hidden=false;const p=$('#prop-report-content');p.replaceChildren();p.append(node('p',c.analysis?.error||'Sources validated. Run the saved campaign to calculate results.'));
        if(c.status==='cancelled')p.append(node('p','The phase search stopped at a safe checkpoint. No partial candidate population is published. Running again restarts the full saved deterministic declaration; it does not select from completed candidates only.'));
        details(p,'Retained calculation attempts',await api(`/api/research-campaigns/${id}/attempts`));
        button(p,c.status==='error'?'Retry interrupted or failed calculation':c.status==='cancelled'?'Run saved declaration again':'Run saved campaign','campaign-resume').onclick=async()=>{try{await api(`/api/research-campaigns/${id}/run`,{});await watch(id,current);}catch(e){$('#prop-status').textContent=e.message;}};await deletionControls(c,current);return;
      }
      if(['queued','running'].includes(c.status)&&!$('#campaign-cancel')){
        $('#prop-report').hidden=false;const p=$('#prop-report-content');p.replaceChildren();p.append(node('p','The complete declared candidate population is retained. A stop request takes effect at the next safe calculation checkpoint; a finishing report may complete before the request arrives.'));
        const stop=button(p,'Request stop at next checkpoint','campaign-cancel');stop.disabled=stopping;
        stop.onclick=async()=>{stop.disabled=true;try{await api(`/api/research-campaigns/${id}/cancel`,{});stopping=true;}catch(e){$('#prop-status').textContent=e.message;stop.disabled=false;}};
        await deletionControls(c,current);
      }
      await new Promise(resolve=>setTimeout(resolve,700));
    }
  }
  window.phaseCampaigns={configure,watch,renderAnalysis,renderRuleReview,sizingControls,profileRuleSummary};
})();
