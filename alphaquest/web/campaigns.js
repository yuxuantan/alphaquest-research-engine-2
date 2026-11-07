/* Campaign controls live inside the ordinary saved-backtest prop workflow. */
(() => {
  const $ = s => document.querySelector(s);
  const node = (tag, text) => {const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
  const link = (text, href) => {const a=node('a',text);a.href=href;return a;};
  async function api(url, body) {
    const response=await fetch(url,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const result=await response.json();if(!response.ok){const error=Error(typeof result.detail==='string'?result.detail:JSON.stringify(result.detail));error.detail=result.detail;throw error;}return result;
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
    if(source.run_metadata.source?.kind==='external_trade_export'){panel.append(node('p','Imported sources retain their exporter’s research declaration. Native campaign search and OOS reruns are unavailable; use the source check below for supported prop analysis.'));return;}
    if(source.run_metadata.research?.phase!=='is'){panel.append(node('p','Select a declared IS backtest to create a research campaign.'));return;}
    const defaults=await api('/api/research-campaigns/defaults');
    const saved=await api('/api/research-campaigns?source_id='+source.id);
    const history=node('div');for(const c of saved.items){history.append(link(`${c.phase} · ${c.status}${c.frozen?' · frozen':''} · ${c.campaign_id}`,`#backtests/prop/campaign/${c.campaign_id}`),node('br'));}panel.append(history);
    const d=node('details');d.id='campaign-configure';d.append(node('summary','Configure a phase campaign'));panel.append(d);
    const form=node('form');form.id='campaign-form';d.append(form);
    form.append(node('p','Compare saved IS strategies and optimization trials. Each saved trial × MNQ size is one candidate. The full count is calculated when checking; searches above 128 candidates require confirmation. Sources must share the dataset, research split and execution costs.'));
    const phase=select(form,'Phase','campaign-phase',[['evaluation','Evaluation · acquisition cost/time'],['funded','Funded · trader cash received']]);
    const profile=select(form,'Account profile','campaign-profile',[['apex-50k-eod','Apex 50K EOD'],['lucidflex-50k','LucidFlex 50K · funded only']]);
    const entry=node('div');panel.insertBefore(entry,d);
    for(const [value,title]of [['evaluation','Create Evaluation campaign'],['funded','Create Funded campaign']])button(entry,title,'campaign-new-'+value).onclick=()=>{d.open=true;phase.value=value;phase.dispatchEvent(new Event('change',{bubbles:true}));phase.focus();};
    const ruleNote=node('p');form.append(ruleNote);
    const ruleSummary=()=>phase.value==='evaluation'?'Evaluation: $3,000 profit target; $2,000 EOD trailing drawdown; $1,000 daily loss limit; 21-session expiry.':profile.value==='apex-50k-eod'?'Fresh funded account: $2,000 trailing drawdown; $2,100 safety net; five qualifying days at $250; 50% payout consistency; six modeled payout caps ($1,500/$1,500/$2,000/$2,500/$2,500/$3,000). Size tiers and daily stops still apply.':'Fresh LucidFlex funded account: $2,000 drawdown; five winning days at $150; no funded consistency requirement; 50% withdrawal limit, $500 minimum/$2,000 maximum gross request; 90% trader share; five modeled payouts; $1,200 daily stop and 20/30/40-MNQ tiers.';
    const showRule=()=>{ruleNote.textContent=`Local rule snapshot: ${profile.value} · ${defaults.profiles[profile.value]}. ${ruleSummary()} These are local model rules, not newly verified provider terms. Source parameters, costs, sizes and the research window are saved by the compatibility check.`;};profile.addEventListener('change',showRule);showRule();
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
      button(row,'Remove source','').onclick=()=>{++requestVersion;clearTimeout(timer);row.remove();invalidate();refreshWindow();};
      describe();load(true);
    }
    addSource(source.id);button(form,'Add saved source','campaign-add-source').onclick=()=>{addSource();invalidate();refreshWindow();};
    const grid=node('div');grid.className='prop-fields';form.append(grid);
    const plan=source.run_metadata.research.plan;
    const isFirst=field(grid,'IS first session','campaign-is-start','','date'),isLast=field(grid,'IS last session','campaign-is-end','','date');
    const windowStatus=node('p','Finding common saved IS coverage…');windowStatus.id='campaign-window-status';form.append(windowStatus);
    button(form,'Use full common IS window','campaign-window-reset').onclick=()=>{invalidate();refreshWindow();};
    field(grid,'Simulated paths per candidate','campaign-paths','1000','number');field(grid,'Simulation seed','campaign-seed','42','number');
    select(grid,'Resampling block · weekdays','campaign-block',[['5','5'],['1','1'],['10','10']]);
    field(grid,'Scenario start date · Chicago','campaign-start',plan.is_start,'date');
    form.append(node('p','Calendar coverage is calculated automatically from the scenario start and the Evaluation chain limit or Funded receipt horizon. It does not require future market data; the derived dates are saved with the campaign.'));
    const evalFields=node('div');evalFields.className='prop-fields';form.append(evalFields);
    field(evalFields,'Evaluation price · USD','campaign-price','30','number');field(evalFields,'Activation fee · USD','campaign-activation','40','number');
    field(evalFields,'Acquisition chains','campaign-chains','1000','number');field(evalFields,'Acquisition seed','campaign-chain-seed','45','number');
    const fundedFields=node('div');fundedFields.className='prop-fields';form.append(fundedFields);
    field(fundedFields,'Receipt horizon · calendar days','campaign-horizon','90','number');field(fundedFields,'Receipt delay · calendar days','campaign-delay','0','number');
    field(fundedFields,'Maximum breach probability (0–1)','campaign-breach','1','number').step='any';
    const note=node('p','Uses captured source costs and fixed-quantity linear MNQ scenarios. The declared weekday calendar, prices and settlement delays are assumptions, not verified provider forecasts. Advanced calendars, costs and constraints are available through the campaign API.');form.append(note);
    const changePhase=()=>{evalFields.hidden=phase.value!=='evaluation';fundedFields.hidden=phase.value!=='funded';profile.options[1].disabled=phase.value==='evaluation';if(phase.value==='evaluation')profile.value='apex-50k-eod';showRule();};phase.onchange=changePhase;changePhase();
    for(const [id,min,max]of [['campaign-paths',1,20000],['campaign-chains',1,20000],['campaign-horizon',1,3650],['campaign-delay',0,365],['campaign-breach',0,1]]){const input=$('#'+id);input.min=min;input.max=max;}
    const count=node('p','Candidate count will be calculated from the selected saved trials and sizes.');count.id='campaign-count';form.append(count);
    const check=button(form,'Save and check candidates','campaign-check'),run=button(form,'Run campaign','campaign-run');run.disabled=true;
    const status=node('p');status.id='campaign-status';status.setAttribute('role','status');form.append(status);
    let campaignId=null,revision=0,windowVersion=0,windowPending=false,automaticWindow=null,windowTimer=null;
    function selectedSources(forWindow=false){
      return [...sources.children].map(row=>{const kind=row.querySelector('.campaign-kind').value;
        const id=row.querySelector('.campaign-reference').value.trim();if(!id)throw Error('Choose a saved source in every row to derive the IS window.');
        const value={[kind]:id,sizes:forWindow?[1]:integers(row.querySelector('.campaign-sizes').value)};
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
        const sampling={block_weekdays:number('campaign-block')};if(isEval)Object.assign(sampling,{chain_simulations:number('campaign-chains'),chain_seed:number('campaign-chain-seed')});
        const search_settings={calendar:{start_dates:[$('#campaign-start').value]}};
        if(!isEval)Object.assign(search_settings,{horizon_calendar_days:number('campaign-horizon'),receipt_delay_calendar_days:number('campaign-delay'),constraints:{maximum_account_breach_probability:number('campaign-breach')}});
        const body={campaign_id:crypto.randomUUID().replaceAll('-',''),phase:phase.value,profile:p,
          sources:selectedSources(),
          is_window:{first_session:$('#campaign-is-start').value,last_session:$('#campaign-is-end').value},
          simulation:{simulations:number('campaign-paths'),seed:number('campaign-seed')},sampling,costs:{mode:'source'},search_settings};
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
        const prior=form.querySelector('.campaign-checks');if(prior)prior.remove();const checkDetails=node('div');checkDetails.className='campaign-checks';details(checkDetails,'Source checks and saved candidate definitions',checks);form.append(checkDetails);
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
      for(const r of points){const isFrontier=frontier.includes(r.candidate_id),c=svgNode('circle',{cx:x(r),cy:y(r),r:isFrontier?8:5,fill:isFrontier?'#fff4e8':'#367781',stroke:isFrontier?'#c75a08':'#367781','stroke-width':3,'data-candidate-id':r.candidate_id,'data-frontier':isFrontier});c.append(svgNode('title',{},`${r.manifest.strategy.id} · ${r.manifest.configuration.micros} MNQ · $${format(r.metrics.cost_per_funded)} · ${format(r.metrics.expected_calendar_days_to_funded)} days${isFrontier?' · Pareto frontier':''}`));svg.append(c);}box.append(svg);
    }else{
      box.append(node('h3','Funded payout distribution'),node('p','All-start received cash, including zero-payout paths. Choose a visible strategy/size; selection here only changes this chart.'));
      if(!rows.length){box.append(node('p','No matching candidates.'));return;}
      const choose=select(box,'Distribution candidate','campaign-distribution',rows.map(r=>[r.candidate_id,`${r.manifest.strategy.id} · ${r.manifest.configuration.micros} MNQ · ${r.candidate_id.slice(0,8)}`]));
      const plot=node('div');box.append(plot);
      function draw(){plot.replaceChildren();const r=rows.find(r=>r.candidate_id===choose.value),values=r.distribution?.values;
        if(r.status!=='estimated')plot.append(node('p','Incomplete horizon: plotted values are accrued cash lower bounds, not completed payout estimates.'));if(!values?.length){plot.append(node('p','Distribution unavailable for this saved report.'));return;}
        const max=Math.max(1,...values),bins=Array(10).fill(0);for(const value of values)bins[Math.min(9,Math.floor(value/max*10))]++;
        const svg=svgNode('svg',{viewBox:'0 0 820 280',role:'img','aria-label':'Funded cash receipt histogram including zero paths'}),peak=Math.max(...bins);
        bins.forEach((count,i)=>{const bar=svgNode('rect',{x:70+i*72,y:220-count/peak*185,width:64,height:count/peak*185,fill:'#367781','data-count':count});bar.append(svgNode('title',{},`$${format(i*max/10)}–$${format((i+1)*max/10)}: ${count} paths`));svg.append(bar,svgNode('text',{x:70+i*72,y:242},format(i*max/10)));});svg.append(svgNode('text',{x:290,y:275},'Trader cash received · USD'));plot.append(svg,node('p',`${values.length} paths · Median $${format(r.metrics.median_payouts)} · P10 $${format(r.metrics.p10_payouts)} · P90 $${format(r.metrics.p90_payouts)}`));
      }choose.onchange=draw;draw();
    }
  }
  function metricOverview(parent,rows,phase){
    if(!rows.length)return;
    const choose=select(parent,'Inspect candidate metrics · presentation only','campaign-inspect',rows.map(r=>[r.candidate_id,`${r.manifest.strategy.id} · ${r.manifest.configuration.micros} MNQ · ${r.candidate_id.slice(0,8)}`]));
    const text=node('p'),cards=node('div');cards.className='campaign-metric-grid';parent.append(text,cards);
    function show(){const r=rows.find(r=>r.candidate_id===choose.value),m=r.metrics,u=r.uncertainty||{};cards.replaceChildren();
      text.textContent=Object.entries(r.manifest.strategy.parameters).map(([k,v])=>`${k}=${v}`).join(', ')+` · ${r.manifest.configuration.profile.profile_id} · ${r.status}. Inspection does not choose or freeze a winner.`;
      const values=phase==='evaluation'?[['Cost per funded account · USD',m.cost_per_funded],['Expected calendar days',m.expected_calendar_days_to_funded],['Pass probability',pct(m.pass_probability)],['Median funding days',m.median_calendar_days_to_funded],['P90 funding days',m.p90_calendar_days_to_funded],['Funded within 30 days',pct(m.probability_funded_by_day_30)],['Funded within 60 days',pct(m.probability_funded_by_day_60)],['Acquisition throughput · accounts/30d',m.funded_accounts_per_30_calendar_days],['MC cost SE · USD',u.cost_se],['MC mean time SE · days',u.calendar_mean_se],['Censoring status',r.reason||r.status]]:[['Expected payout cash · USD',m.expected_payouts],['Median / P10 / P90 · USD',`${format(m.median_payouts)} / ${format(m.p10_payouts)} / ${format(m.p90_payouts)}`],['Probability of first payout',pct(m.probability_first_payout)],['First payout days · conditional on payout',(m.probability_first_payout===0?'No payout observed':m.expected_days_to_first_payout_conditional_on_payout)],['Breach probability',pct(m.account_breach_probability)],['Survival to horizon',pct(m.probability_surviving_to_horizon)],['Risk constraint status',r.feasible?'Meets empirical limits':(r.constraint_violations||[]).join(', ')||'Unresolved'],['Pending cash · USD',m.expected_pending_cash],['MC mean cash SE · USD',u.mean_monte_carlo_se],['Unresolved horizon paths',r.censoring?.unresolved_horizon_paths],['Open lifetimes · censored',r.censoring?.lifetime_censored_paths]];
      for(const [label,value]of values){const card=node('div');card.append(node('span',label),node('strong',format(value)));cards.append(card);}
    }choose.onchange=show;show();
  }
  function renderAnalysis(report,campaign=null){
    $('#prop-config').hidden=true;$('#prop-report').hidden=false;$('#prop-delete').hidden=true;$('#prop-downloads').replaceChildren();
    const assessment=report.assessment,isEval=report.phase==='evaluation';
    $('#prop-heading-title').textContent=assessment?'Frozen OOS assessment':campaign?'Research campaign':'Independent phase analysis';
    $('#prop-heading-note').textContent=isEval?'Evaluation · minimize acquisition cost and calendar time':'Funded · maximize expected trader cash received';
    $('#prop-back').href=`#backtests/report/${report.source.backtest.id}`;
    const target=$('#prop-report-content');target.replaceChildren();target.className='';const calc=report.calculations;
    const panel=node('section');panel.className='panel prop-panel';target.append(panel);
    panel.append(node('h2',assessment?'OOS assessment · frozen settings':campaign?.frozen?'Frozen IS selection':'IS candidate results'));
    panel.append(node('p',`${calc.candidates.length} completed candidates · ${report.model_version}. ${assessment?'Assessment only; no OOS ranking, frontier selection or replacement of IS choices.':'Selection uses IS only. Evaluation has no automatic winner.'} Estimated results; no provider parity or certified optimum.`));
    if(assessment){panel.append(link('Return to frozen IS campaign',`#backtests/prop/campaign/${assessment.campaign_id}`),node('p',assessment.interpretation));details(panel,'Pre-launch OOS access history',assessment.prior_access);}
    const filters=node('div');filters.className='prop-fields';panel.append(filters);
    const opts=(key,label)=>[['',label],...[...new Set(calc.candidates.map(key))].sort().map(v=>[String(v),String(v)])];
    const strategy=select(filters,'Filter by strategy','campaign-filter-strategy',opts(r=>r.manifest.strategy.id,'All strategies'));
    const size=select(filters,'Filter by size','campaign-filter-size',opts(r=>r.manifest.configuration.micros,'All sizes'));
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
      const labels=['Freeze / name','Saved strategy / source',`Account / rules / ${assessment?'OOS':'IS'} window`,'MNQ','Status',...(isEval?['Cost per funded · USD','Expected calendar days','Pass probability','Median days','P90 days','Funded by 30d','Funded by 60d','Accounts / 30d','Pareto frontier','MC cost SE / days SE','Censoring']:['Expected cash · USD','Median cash','P10 cash','P90 cash','First payout probability','Days to first payout · conditional','Breach probability','Survival to horizon','Risk constraints','Pending cash · USD','Rank','MC mean SE','Censoring'])];
      const values=rows.map(r=>{
        const config=r.manifest.configuration,m=r.metrics,u=r.uncertainty||{},pick=node('div'),box=node('input');box.type='checkbox';box.value=r.candidate_id;box.className='campaign-pick';box.setAttribute('aria-label','Freeze '+r.candidate_id.slice(0,12));box.disabled=!campaign||!!campaign.frozen||!allowed.includes(r.candidate_id);box.checked=picked.has(r.candidate_id);box.onchange=()=>box.checked?picked.add(r.candidate_id):picked.delete(r.candidate_id);pick.append(box);
        const name=field(pick,'Candidate name','',names.get(r.candidate_id)||assessment?.sources.find(s=>s.source_id===config.source.source_backtest_id&&s.frozen_manifest.configuration.micros===config.micros)?.name||`${r.manifest.strategy.id} · ${config.micros} MNQ · ${r.candidate_id.slice(0,8)}`);names.set(r.candidate_id,name.value);name.className='campaign-candidate-name';name.maxLength=120;name.disabled=box.disabled;name.oninput=()=>names.set(r.candidate_id,name.value);
        const s=node('div');s.append(link(r.manifest.strategy.id,`#backtests/report/${config.source.source_backtest_id}`),node('p',Object.entries(r.manifest.strategy.parameters).map(([k,v])=>`${k}=${v}`).join(', ')));details(s,'Source identity and provenance',r.manifest);
        const rules=node('div',`${config.profile.profile_id} · ${config.profile.rule_version}`);rules.append(node('p',`${assessment?'OOS':'IS'} ${config.period?.first_session} → ${config.period?.last_session}`));details(rules,'Saved rules, costs and search settings',{profile:config.profile,account_rules:r.provenance?.rules,costs:config.costs,sampling:config.sampling,simulation:config.simulation,calendar:report.request?.calendar,horizon:report.request?.horizon_calendar_days});
        const status=report.phase==='funded'&&r.status==='estimated'&&!r.feasible?'infeasible':r.status;
        const cells=isEval?[m.cost_per_funded,m.expected_calendar_days_to_funded,pct(m.pass_probability),m.median_calendar_days_to_funded,m.p90_calendar_days_to_funded,pct(m.probability_funded_by_day_30),pct(m.probability_funded_by_day_60),m.funded_accounts_per_30_calendar_days,assessment?'Assessment only':r.pareto_member? 'Frontier':'Outside frontier',`${format(u.cost_se)} / ${format(u.calendar_mean_se)}`,`${r.censoring?.chain_paths??'Unknown'} unresolved chains · ${r.reason||r.status}`]:[m.expected_payouts,m.median_payouts,m.p10_payouts,m.p90_payouts,pct(m.probability_first_payout),(m.probability_first_payout===0?'No payout observed':m.expected_days_to_first_payout_conditional_on_payout),pct(m.account_breach_probability),pct(m.probability_surviving_to_horizon),r.feasible?'Meets empirical limits':(r.constraint_violations||[]).join(', ')||'Unresolved',m.expected_pending_cash,r.rank??(assessment?'Assessment only':'Not ranked'),u.mean_monte_carlo_se,`${r.censoring?.unresolved_horizon_paths??0} incomplete horizons; ${r.censoring?.lifetime_censored_paths??0} open lifetimes`];
        return [pick,s,rules,config.micros,status,...cells];
      });dataTable(comparison,labels,values,'campaign-candidates');
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
      }else {details(actions,'Frozen package',campaign.frozen);assessmentControls(actions,campaign);}
      for(const kind of ['campaign.json','results.csv','results.json','source_checks.json','analysis.zip',...(campaign.frozen?['frozen_package.json']:[])])actions.append(link('Download '+kind,`/api/research-campaigns/${campaign.campaign_id}/exports/${kind}`),node('br'));
      details(panel,'Campaign declaration and numerical identity',campaign.manifest);
    }else {const downloads=node('div');downloads.className='campaign-downloads';for(const [label,path]of [['Download analysis ZIP','downloads/analysis.zip'],['Download metrics CSV','files/phase_metrics.csv'],['Download metrics JSON','files/phase_metrics.json']]){const a=link(label,`/api/prop-analyses/${report.id}/${path}`);a.className='button secondary';downloads.append(a);}panel.append(downloads);}
  }
  async function assessmentControls(parent,campaign){
    const section=node('section');section.id='campaign-assessments';parent.append(section);section.append(node('h3','Manual final OOS assessment'),node('p','Runs ordinary OOS backtests from the frozen IS parents, then assesses this named family at its frozen sizes, profiles, costs, horizon, seeds and scenario calendar. Results append without ranking or changing IS selections. Previously accessed data is not untouched final OOS.'));
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
  async function watch(id,current){
    $('#prop-config').hidden=true;$('#prop-report').hidden=true;$('#prop-downloads').replaceChildren();
    while(current()){
      const c=await api('/api/research-campaigns/'+id);if(!current())return;
      $('#prop-status').textContent=`${c.manifest.phase} campaign · ${c.status} · ${c.analysis?.progress||'Sources checked'} · ${c.status==='complete'?c.manifest.candidate_search_count+' / '+c.manifest.candidate_search_count+' completed candidates':c.manifest.candidate_search_count+' declared candidates'} · ${c.campaign_id}`;
      if(c.status==='complete'){const r=await api(`/api/prop-analyses/${c.analysis_id}/downloads/report.json`);if(current())renderAnalysis(r,c);return;}
      if(['validated','error'].includes(c.status)){
        $('#prop-report').hidden=false;const p=$('#prop-report-content');p.replaceChildren();p.append(node('p',c.analysis?.error||'Sources validated. Run the saved campaign to calculate results.'));
        details(p,'Retained calculation attempts',await api(`/api/research-campaigns/${id}/attempts`));
        button(p,c.status==='error'?'Retry interrupted or failed calculation':'Run saved campaign','campaign-resume').onclick=async()=>{try{await api(`/api/research-campaigns/${id}/run`,{});await watch(id,current);}catch(e){$('#prop-status').textContent=e.message;}};return;
      }
      await new Promise(resolve=>setTimeout(resolve,700));
    }
  }
  window.phaseCampaigns={configure,watch,renderAnalysis};
})();
