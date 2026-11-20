"use strict";
(() => {
  const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
  const fmt=v=>v==null?'Unavailable':Number(v).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
  const pct=v=>v==null?'Unavailable':fmt(Number(v)*100)+'%';
  const read=async(url,method='GET',body)=>{const r=await fetch(url,{method,cache:'no-store',...(body?{headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})});const value=await r.json();if(!r.ok)throw Error(typeof value.detail==='string'?value.detail:JSON.stringify(value.detail));return value;};
  const link=(parent,text,href)=>{const a=node('a',text,'workflow-inline-link');a.href=href;parent.append(a);};
  const detail=(parent,title,value)=>{const d=node('details');d.append(node('summary',title),node('pre',JSON.stringify(value,null,2)));parent.append(d);return d;};
  const policyLabel=c=>c.sizing?.policy?.kind==='percentage_risk'?`${c.sizing.policy.risk_percent}% · ${c.sizing.policy.reference.replaceAll('_',' ')} (cap ${c.sizing.policy.maximum_contracts} MNQ)`:`${c.micros} MNQ`;
  const policyValue=c=>Number(c.sizing?.policy?.risk_percent??c.micros);
  const comparePolicy=(a,b)=>{const values=[a,b].map(c=>String(c.sizing?.policy?.risk_percent??c.micros)),digits=Math.max(...values.map(v=>(v.split('.')[1]||'').length)),numbers=values.map(v=>{const [whole,fraction='']=v.split('.');return BigInt(whole+fraction.padEnd(digits,'0'));});return numbers[0]<numbers[1]?-1:numbers[0]>numbers[1]?1:0;};
  const policyKey=c=>c.sizing?.policy?.kind==='percentage_risk'?String(c.sizing.policy.risk_percent):String(c.micros);
  const range=(settings,phase)=>({minimum:settings[phase+'_minimum_micros']??settings.minimum_micros,maximum:settings[phase+'_maximum_micros']??settings.maximum_micros});
  const chartDisposers=[];
  function tradeBehavior(parent,rows,role){
    const modeled=rows.filter(r=>r.simulation_model?.model==='saved-trade-account-policies-v2'&&r.quantity_summary);
    if(!modeled.length)return;
    const box=node('details',undefined,'prop-trade-behavior');box.dataset.tradeBehavior=role;
    const warnings=modeled.filter(r=>r.quantity_summary.skipped_entries||r.quantity_summary.account_limit_exit_count||r.quantity_summary.risk_budget_override_count).length;
    box.append(node('summary',`${role} trade handling · ${warnings?warnings+' sizing '+(warnings===1?'policy has':'policies have')+' deviations to review':'No skips, account-limit exits or budget overrides'}`));
    box.open=warnings>0;
    box.append(node('p','Any skip, account-limit exit or budget override is flagged for review; these warnings do not add a pass/fail gate. Rates cover sampled eligible opportunities, not unique historical trades. After a pass, account termination or mandatory pause, later opportunities are excluded.','field-help'));
    const wrap=node('div',undefined,'table-scroll'),table=node('table',undefined,'library-table prop-result-table'),head=node('thead'),hr=node('tr'),body=node('tbody');
    for(const title of ['Sizing policy','Skipped opportunities','Account-limit exits','Over-budget entries','Actual planned risk % · mean / max'])hr.append(node('th',title));
    head.append(hr);table.append(head,body);wrap.append(table);box.append(wrap);
    for(const row of modeled){const q=row.quantity_summary,tr=node('tr');tr.dataset.candidateId=row.candidate_id;
      for(const text of [policyLabel(row.manifest?.configuration||row.configuration),`${pct(q.skipped_rate)} · ${q.skipped_entries} / ${q.opportunities}`,q.admitted_entries?`${pct(q.account_limit_exit_rate)} · ${q.account_limit_exit_count||0} / ${q.admitted_entries} (${q.daily_limit_exit_count||0} daily, ${q.account_breach_exit_count||0} account)`:'— · no admitted entries',q.admitted_entries?`${pct(q.risk_budget_override_rate)} · ${q.risk_budget_override_count||0} / ${q.admitted_entries}`:'— · no admitted entries',q.admitted_entries?`${fmt(q.mean_actual_risk_percent)}% / ${fmt(q.maximum_actual_risk_percent)}%`:'— · no admitted entries'])tr.append(node('td',text));
      body.append(tr);
      const details=node('tr'),cell=node('td');cell.colSpan=5;
      detail(cell,'Reasons and trade examples · '+policyLabel(row.manifest?.configuration||row.configuration),{frozen_handling:row.simulation_model.trade_handling,source_trade_count:q.source_trade_count,excursion_coverage:row.simulation_model.excursion_coverage,skip_reasons:q.skip_reason_counts||q.reason_counts,examples:q.behavior_examples,scope:q.scope});details.append(cell);body.append(details);
    }
    parent.append(box);
  }
  function evaluationChart(parent,rows,tableScope=parent){
    const plotted=rows.filter(r=>r.status==='estimated'&&['cost_per_funded','expected_calendar_days_to_funded'].every(k=>r.metrics[k]!=null&&Number.isFinite(Number(r.metrics[k]))));
    const section=node('section',undefined,'prop-sim-pareto');
    section.append(node('h3','Evaluation cost/time Pareto curve'));parent.append(section);
    if(!plotted.length){section.append(node('p','No resolved cost/time points are available. Unresolved and censored sizes remain in the table below.'));return;}
    const groups=new Map();
    for(const row of plotted){
      const x=Number(row.metrics.expected_calendar_days_to_funded),y=Number(row.metrics.cost_per_funded),key=`${x}|${y}`;
      if(!groups.has(key))groups.set(key,{x,y,rows:[]});groups.get(key).rows.push(row);
    }
    const points=[...groups.values()].sort((a,b)=>Math.min(...a.rows.map(r=>policyValue(r.manifest.configuration)))-Math.min(...b.rows.map(r=>policyValue(r.manifest.configuration))));
    points.forEach(p=>{p.sizes=p.rows.map(r=>policyKey(r.manifest.configuration));p.labels=p.rows.map(r=>policyLabel(r.manifest.configuration));p.frontier=p.rows.some(r=>r.pareto_member);});
    const frontier=points.filter(p=>p.frontier).sort((a,b)=>a.x-b.x||a.y-b.y);
    let view=frontier.length?'frontier':'all',selected=null,bounds,lastWidth;
    const toolbar=node('div',undefined,'pareto-toolbar'),views=node('div',undefined,'pareto-views');views.setAttribute('role','group');views.setAttribute('aria-label','Chart view');
    const focus=node('button','Frontier detail'),all=node('button','All sizes');focus.id='prop-sim-pareto-focus';all.id='prop-sim-pareto-all';
    for(const button of [focus,all]){button.type='button';views.append(button);}focus.disabled=!frontier.length;
    const legend=node('div',undefined,'pareto-legend');
    for(const [text,cls] of [['Pareto frontier','frontier'],['Other resolved sizes','other']]){const item=node('span',text),dot=node('i',undefined,cls);dot.setAttribute('aria-hidden','true');item.prepend(dot);legend.append(item);}
    toolbar.append(views,legend);section.append(toolbar);
    const wrap=node('div',undefined,'pareto-plot'),ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');
    svg.id='prop-sim-evaluation-pareto';svg.setAttribute('role','group');svg.setAttribute('aria-label','Evaluation Pareto chart: calendar days horizontally, acquisition cost vertically; lower and left is better.');svg.dataset.candidateCount=plotted.length;
    wrap.append(svg);section.append(wrap);
    const inspector=node('div',undefined,'pareto-inspector'),label=node('label','Inspect size'),picker=node('select');picker.id='prop-sim-pareto-size';picker.add(new Option('Choose a size or point…',''));
    points.forEach((p,i)=>picker.add(new Option(`${p.labels.join(' / ')} · ${p.frontier?'Frontier':'Other size'}`,String(i))));label.append(picker);
    const readout=node('p','Hover, focus or click a point to see its exact results.','pareto-readout');readout.id='prop-sim-pareto-readout';readout.setAttribute('aria-live','polite');
    const metrics=node('dl',undefined,'pareto-metrics'),values={};
    for(const [key,title] of [['cost','Expected acquisition cost'],['days','Calendar days to Funded']]){const item=node('div');values[key]=node('dd','—');item.append(node('dt',title),values[key]);metrics.append(item);}
    inspector.append(label,metrics,readout);section.append(inspector);
    const caption=node('p',undefined,'field-help');caption.id='prop-sim-pareto-caption';section.append(caption);
    const download=node('a','Pareto chart SVG ↓','workflow-inline-link');download.download='evaluation-pareto.svg';section.append(download);
    const updateDownload=()=>{
      const copy=svg.cloneNode(true),[,,width,height]=svg.getAttribute('viewBox').split(' ').map(Number);
      copy.setAttribute('viewBox',`0 0 ${width} ${height+44}`);copy.setAttribute('height',String(height+44));
      const lines=[`${view==='frontier'?'Frontier detail':'All sizes'} · Green: frontier among resolved candidates only. Grey: other resolved sizes.`,selected?`${selected.sizes.length>6?selected.sizes.length+' tied sizes':selected.labels.join(' / ')} · $${fmt(selected.y)} · ${fmt(selected.x)} calendar days`:'Inspection chart; no Evaluation winner is selected.'];
      lines.forEach((text,i)=>{const label=document.createElementNS(ns,'text');for(const [key,value] of Object.entries({x:12,y:height+16+i*16,fill:'#526b62','font-size':11}))label.setAttribute(key,String(value));label.textContent=text;copy.append(label);});
      download.href='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(new XMLSerializer().serializeToString(copy));
    };
    const inside=p=>p.x>=bounds.x[0]&&p.x<=bounds.x[1]&&p.y>=bounds.y[0]&&p.y<=bounds.y[1];
    function updateSelection(){
      picker.value=selected?String(points.indexOf(selected)):'';
      readout.textContent=selected?`${selected.labels.join(' / ')} · ${selected.frontier?'Pareto frontier':'Other resolved size'}${selected.sizes.length>1?' · Exact performance tie':''}`:'Hover, focus or click a point to see its exact results.';
      values.cost.textContent=selected?'$'+fmt(selected.y):'—';values.days.textContent=selected?fmt(selected.x)+' days':'—';
      svg.querySelectorAll('circle[data-point]').forEach(circle=>{const p=points[Number(circle.dataset.point)],active=p===selected;circle.setAttribute('r',active?8:p.frontier?6:4);circle.setAttribute('stroke',active?'#20313b':'#fff');circle.setAttribute('stroke-width',active?2.5:1.25);circle.setAttribute('aria-pressed',String(active));});
      tableScope.querySelectorAll('tbody tr').forEach(row=>row.classList.toggle('prop-sim-chart-highlight',!!selected&&selected.sizes.includes(row.dataset.size)));
      updateDownload();
    }
    function inspect(point){selected=point;if(!inside(point)){view='all';drawPlot();}else updateSelection();}
    picker.onchange=()=>{if(picker.value===''){selected=null;updateSelection();}else inspect(points[Number(picker.value)]);};
    function extent(values,count){
      const low=Math.min(...values),high=Math.max(...values),span=high-low,padding=Math.max(span*.14,Math.max(1,Math.abs(low)*.06));
      const first=Math.max(0,low-padding),last=high+padding,raw=(last-first)/count,power=10**Math.floor(Math.log10(raw)),fraction=raw/power;
      const step=([1,2,2.5,5,10].find(n=>n>=fraction)||10)*power;
      const min=Math.floor(first/step)*step,max=Math.ceil(last/step)*step;
      return [min,max,Array.from({length:Math.round((max-min)/step)+1},(_,i)=>min+i*step)];
    }
    const tick=v=>Number(v).toLocaleString('en-US',{maximumFractionDigits:2});
    function drawPlot(){
      const width=Math.max(300,Math.round(wrap.clientWidth||800)),height=width<560?300:360;lastWidth=width;
      const scope=view==='frontier'?frontier:points,xt=extent(scope.map(p=>p.x),width<560?3:5),yt=extent(scope.map(p=>p.y),4);bounds={x:xt,y:yt};
      const left=Math.min(110,Math.max(70,...yt[2].map(v=>tick(v).length*7+35))),right=width-22,top=22,bottom=height-58;
      const x=v=>left+(right-left)*(v-xt[0])/(xt[1]-xt[0]),y=v=>bottom-(bottom-top)*(v-yt[0])/(yt[1]-yt[0]);
      svg.replaceChildren();svg.setAttribute('viewBox',`0 0 ${width} ${height}`);svg.setAttribute('height',String(height));svg.dataset.view=view;
      const draw=(tag,attrs,text)=>{const item=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs))item.setAttribute(k,String(v));if(text!==undefined)item.textContent=text;svg.append(item);return item;};
      draw('desc',{},`${view==='frontier'?'Frontier detail':'All resolved sizes'}. Axes fit this view. Lower acquisition cost and shorter time are preferred. Exact ties share a marker.`);
      draw('rect',{width,height,fill:'#fff'});
      for(const v of xt[2]){draw('line',{x1:x(v),x2:x(v),y1:top,y2:bottom,stroke:'#edf1f3'});draw('text',{x:x(v),y:bottom+23,'text-anchor':'middle',fill:'#657681','font-size':12},tick(v));}
      for(const v of yt[2]){draw('line',{x1:left,x2:right,y1:y(v),y2:y(v),stroke:'#e5ecef'});draw('text',{x:left-12,y:y(v)+4,'text-anchor':'end',fill:'#657681','font-size':12},tick(v));}
      draw('text',{x:(left+right)/2,y:height-10,'text-anchor':'middle',fill:'#344953','font-size':13},'Expected calendar days to Funded');
      draw('text',{x:16,y:(top+bottom)/2,transform:`rotate(-90 16 ${(top+bottom)/2})`,'text-anchor':'middle',fill:'#344953','font-size':13},'Expected acquisition cost · USD');
      if(frontier.length>1)draw('polyline',{points:frontier.map(p=>`${x(p.x)},${y(p.y)}`).join(' '),fill:'none',stroke:'#008675','stroke-width':2.5,'data-frontier':'true'});
      const visible=points.filter(inside);svg.dataset.visibleCount=visible.reduce((n,p)=>n+p.rows.length,0);
      // Draw the frontier last so nearby grey markers cannot conceal it.
      for(const p of [...visible].sort((a,b)=>Number(a.frontier)-Number(b.frontier))){
        const text=`${p.labels.join(' / ')} · ${fmt(p.x)} calendar days · $${fmt(p.y)} acquisition cost · ${p.frontier?'Pareto frontier':'other resolved size'}`;
        const circle=draw('circle',{cx:x(p.x),cy:y(p.y),r:p.frontier?6:4,fill:p.frontier?'#008675':'#a7b3bc',stroke:'#fff','stroke-width':1.25,tabindex:0,role:'button','aria-label':text,'data-point':points.indexOf(p),'data-sizes':p.sizes.join(','),'data-pareto':p.frontier});
        circle.onmouseenter=circle.onfocus=circle.onclick=()=>inspect(p);circle.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();inspect(p);}};
      }
      focus.setAttribute('aria-pressed',String(view==='frontier'));all.setAttribute('aria-pressed',String(view==='all'));
      caption.textContent=`${svg.dataset.visibleCount} of ${plotted.length} resolved sizes in view · ${rows.length-plotted.length} unresolved/censored sizes remain in the table. The Pareto frontier compares resolved candidates only. Axes fit the selected view. ${frontier.length===0?'No frontier was supplied for these resolved estimates.':frontier.length===1?'One distinct frontier point; tied sizes share a marker.':'The line connects tested frontier points.'} Point estimates; no untested intermediate sizes inferred.`;
      if(selected&&!inside(selected))selected=null;updateSelection();
    }
    focus.onclick=()=>{view='frontier';drawPlot();};all.onclick=()=>{view='all';drawPlot();};
    drawPlot();const observer=new ResizeObserver(()=>{if(Math.max(300,Math.round(wrap.clientWidth||800))!==lastWidth)drawPlot();});observer.observe(wrap);
    return ()=>observer.disconnect();
  }
  let generation=0,timer;
  async function render(){
    ++generation;clearTimeout(timer);chartDisposers.splice(0).forEach(dispose=>dispose());
    if(location.hash.split('?')[0]!=='#prop-sim')return;
    const version=generation,alive=()=>version===generation&&location.hash.split('?')[0]==='#prop-sim',host=document.querySelector('#prop-sim-content');
    const query=new URLSearchParams(location.hash.split('?')[1]||''),selectedId=query.get('analysis'),sourceId=query.get('source'),deletedId=query.get('deleted');
    host.replaceChildren(node('p','Loading qualified configurations…'));
    try{
      if(query.get('mode')==='portfolio'){await window.propPortfolio.render(host);return;}
      if(selectedId){const parent=await read('/api/prop-sim/'+selectedId);if(!alive())return;if(parent.configuration.mode==='portfolio'){await window.propPortfolio.render(host,parent);return;}}
      const [sources,defaults,history]=await Promise.all([read('/api/prop-sim/candidates'),read('/api/prop-sim/defaults'),read('/api/prop-sim')]);if(!alive())return;
      const profiles=defaults.profiles;host.replaceChildren();const choice=node('section',undefined,'panel prop-sim-mode-choice');choice.append(node('h2','What do you want to learn?'),node('p','Use this view for independent Evaluation and Funded sizing. Choose fixed contracts or independently optimized risk percentages. For multiple strategies and replacement economics, compare portfolios.'));link(choice,'Portfolio allocation, percentage risk & full cash flow','#prop-sim?mode=portfolio');host.append(choice);
      const setup=node('details',undefined,'panel prop-sim-setup');setup.id='prop-sim-setup';setup.open=!selectedId;
      setup.append(node('summary',selectedId?'Adjust settings and start a new simulation':'Configure a prop simulation'));
      const form=node('form');form.id='prop-sim-form';setup.append(form);host.append(setup);
      const sourceGrid=node('div',undefined,'prop-sim-source-grid');form.append(sourceGrid);
      const sourceBox=node('section');sourceBox.append(node('h2','1. Qualified configuration'));
      const label=node('label','Campaign configuration'),picker=node('select');picker.id='prop-sim-source';picker.add(new Option('Choose a configuration',''));
      sources.items.forEach((item,i)=>picker.add(new Option(`${item.strategy_id.replaceAll('_',' ')} · ${item.dataset.name} · Broad ${item.broad_trial} / Narrow ${item.narrow_trial}`,String(i))));label.append(picker);sourceBox.append(label);
      sourceBox.append(node('p','Only confirmed mechanics, IS Broad, IS Narrow, OOS and current Monte Carlo passes are selectable. One configuration per simulation.','field-help'));
      if(!sources.items.length)sourceBox.append(node('p','No qualified, compatible configurations are available. Complete the campaign phases and Monte Carlo first.'));
      if(sources.unavailable.length)detail(sourceBox,'Unavailable sources and reasons',sources.unavailable);
      const sourceInfo=node('div');sourceInfo.id='prop-sim-source-details';sourceBox.append(sourceInfo);
      const accountBox=node('section');accountBox.append(node('h2','2. Prop account'));
      const accountLabel=node('label','Account profile'),accountPicker=node('select');accountPicker.id='prop-sim-profile';
      for(const [id,p] of Object.entries(profiles))accountPicker.add(new Option(p.name,id));accountLabel.append(accountPicker);accountBox.append(accountLabel);
      const accountInfo=node('p',undefined,'prop-sim-account-info');accountBox.append(accountInfo);
      const dllLabel=node('label',undefined,'prop-sim-dll'),dll=node('input'),dllText=node('span');dll.type='checkbox';dll.id='prop-sim-daily-loss-limit';dll.checked=true;dllLabel.append(dll,dllText);accountBox.append(dllLabel);
      const consistencyLabel=node('label','Evaluation consistency'),consistency=node('select');consistency.id='prop-sim-consistency';consistency.add(new Option('40% · standard','40'));consistency.add(new Option('50% · paid add-on','50'));consistencyLabel.append(consistency);accountBox.append(consistencyLabel);
      const ruleNote=node('p',undefined,'field-help');accountBox.append(ruleNote);sourceGrid.append(sourceBox,accountBox);
      const modeLabel=node('label','Position sizing search'),sizingMode=node('select');sizingMode.id='prop-sim-search-kind';sizingMode.add(new Option('Fixed MNQ contracts','fixed_contracts'));sizingMode.add(new Option('Percentage of account risk','percentage_risk'));modeLabel.append(sizingMode);form.append(modeLabel);
      const modeHelp=node('p','Fixed and percentage modes reuse saved opportunities. Choose how each phase handles positions whose stop risk exceeds an account allowance; exact stop/limit fills are assumed.','field-help');form.append(modeHelp);
      const phaseGrid=node('div',undefined,'prop-sim-phase-grid');form.append(phaseGrid);
      const grids={};
      for(const [key,title,note] of [['evaluation','Evaluation sizing','Minimize acquisition cost and calendar time; retain every Pareto configuration.'],['funded','Funded sizing','Maximize cash received from one fresh account over the chosen horizon.']]){
        const box=node('section',undefined,'prop-sim-phase-config');box.append(node('h3',title),node('p',note,'field-help'));grids[key]=node('div',undefined,'prop-sim-settings');box.append(grids[key]);phaseGrid.append(box);
      }
      const quality=node('section',undefined,'prop-sim-quality');quality.append(node('h3','Simulation sample'));grids.quality=node('div',undefined,'prop-sim-settings');quality.append(grids.quality);form.append(quality);
      const advanced=node('details',undefined,'prop-sim-advanced');advanced.append(node('summary','Costs, calendar and optional risk settings'));grids.advanced=node('div',undefined,'prop-sim-settings');advanced.append(grids.advanced);form.append(advanced);
      const fields={};
      const names=[['evaluation_minimum_micros','Minimum MNQ','number','evaluation'],['evaluation_maximum_micros','Maximum MNQ','number','evaluation'],['evaluation_price','Purchase fee · USD','text','evaluation'],['activation_fee','Activation fee · USD','text','evaluation'],['funded_minimum_micros','Minimum MNQ','number','funded'],['funded_maximum_micros','Maximum MNQ','number','funded'],['funded_horizon_calendar_days','Funded horizon · calendar days','number','funded'],['simulations','Paths per size, per phase','number','quality'],['block_weekdays','Historical block · weekdays','select','quality'],['seed','Random seed','number','advanced'],['commission_per_mnq_side','MNQ commission per contract per side · USD','text','advanced'],['start_date','Scenario start · America/Chicago','date','advanced'],['receipt_delay_calendar_days','Receipt delay · calendar days','number','advanced'],['maximum_funded_breach_probability','Optional Funded breach cap · 0 to 1','number','advanced'],['closures','Closed sessions · comma-separated YYYY-MM-DD','text','advanced']];
      for(const [name,text,type,group] of names){
        const label=node('label',text),input=node(type==='select'?'select':'input');input.id='prop-sim-'+name;fields[name]=input;
        input.required=!['closures','maximum_funded_breach_probability'].includes(name);
        if(type==='select')for(const n of [1,5,10])input.add(new Option(String(n),String(n)));else input.type=type;
        if(type==='number'){input.step=name==='maximum_funded_breach_probability'?'.01':'1';input.min='0';}
        if(name.endsWith('_micros'))input.min='1';if(name==='simulations'){input.min='8';input.max='20000';}
        if(name==='funded_horizon_calendar_days'){input.min='1';input.max='365';}
        input.value=name==='start_date'?new Date().toLocaleDateString('en-CA',{timeZone:'America/Chicago'}):name==='closures'?'':String(defaults.defaults[name]??'');
        if(name==='maximum_funded_breach_probability'){input.max='1';input.placeholder='No cap';label.append(node('span','Blank = no extra eligibility cap. Measures breach within the Funded horizon, not years of IS history.','field-help'));}
        label.append(input);grids[group].append(label);
      }
      const riskFields={},riskGroups={},tradeFields={};
      for(const phase of ['evaluation','funded']){
        const handling=node('section',undefined,'prop-sim-trade-handling');handling.style.gridColumn='1 / -1';
        const actionLabel=node('label','When position stop risk reaches an account limit'),action=node('select');action.id=`prop-sim-${phase}-account-limit-action`;
        action.add(new Option('Skip trade (default)','skip'));action.add(new Option('Enter with account-limit exit','exit_at_limit'));actionLabel.append(action);
        const minimumLabel=node('label'),minimum=node('input');minimum.type='checkbox';minimum.id=`prop-sim-${phase}-minimum-one-contract`;minimumLabel.append(minimum,node('span','Trade one MNQ when the percentage budget cannot afford one'));
        const handlingHelp=node('p',undefined,'field-help');handling.append(actionLabel,minimumLabel,handlingHelp);grids[phase].append(handling);tradeFields[phase]={action,minimum,minimumLabel,help:handlingHelp};
        const group=node('div',undefined,'prop-sim-settings');group.style.gridColumn='1 / -1';riskGroups[phase]=group;grids[phase].prepend(group);riskFields[phase]={};
        for(const [key,title,value] of [['minimum','Minimum risk %','0.1'],['maximum','Maximum risk %','0.5'],['step','Risk increment %','0.1'],['maximum_contracts','Whole-MNQ ceiling',String(profiles[accountPicker.value].size_limits[phase])]]){
          const label=node('label',title),input=node('input');input.type=key==='maximum_contracts'?'number':'text';input.required=true;input.value=value;input.id=`prop-sim-${phase}-risk-${key}`;if(key==='maximum_contracts'){input.min='1';input.step='1';}label.append(input);group.append(label);riskFields[phase][key]=input;
        }
        const options=node('details');options.style.gridColumn='1 / -1';options.append(node('summary','Risk reference'));
        const label=node('label','Percentage reference'),reference=node('select');reference.id=`prop-sim-${phase}-risk-reference`;
        for(const [value,title] of [['initial_configured_capital','Initial $50,000 capital (stable dollar budget)'],['current_account_balance','Current balance (changes with P&L and deductions)'],['available_drawdown_cushion','Available account drawdown cushion']])reference.add(new Option(title,value));label.append(reference);options.append(label);riskFields[phase].reference=reference;
        options.append(node('p','Account-limit handling below applies to the actual position risk after quantity caps.','field-help'));
        const budget=node('p',undefined,'field-help');budget.style.gridColumn='1 / -1';budget.dataset.initialRiskBudget=phase;group.append(budget);
        const help=node('p','0.20 means 0.20%. Quantity rounds down to whole MNQ. The optional one-contract override below can exceed this budget. Caps still apply.','field-help');help.style.gridColumn='1 / -1';group.append(options,help);
      }
      function expandedGrid(phase){
        const fields=riskFields[phase],raw=['minimum','maximum','step'].map(k=>fields[k].value.startsWith('.')?'0'+fields[k].value:fields[k].value);
        if(raw.some(v=>! /^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$/.test(v)))throw Error('Use plain positive decimal percentages.');
        const digits=Math.max(...raw.map(v=>(v.split('.')[1]||'').length));if(digits>64)throw Error('Percentage precision exceeds 64 decimal places.');
        const numbers=raw.map(v=>{const [whole,frac='']=v.split('.');return BigInt(whole+frac.padEnd(digits,'0'));});const [lo,hi,step]=numbers;
        if(lo<=0n||step<=0n||hi<lo||hi>100n*10n**BigInt(digits)||(hi-lo)%step!==0n)throw Error('Declare positive, aligned minimum, maximum and step (at most 100%).');
        const count=(hi-lo)/step+1n;if(count>60n)throw Error('At most 60 percentage policies per phase.');
        return Array.from({length:Number(count)},(_,i)=>{const v=String(lo+step*BigInt(i)).padStart(digits+1,'0');return digits?(v.slice(0,-digits)+'.'+v.slice(-digits)).replace(/0+$/,'').replace(/\.$/,''):v;});
      }
      const disclosure=node('p',defaults.disclosure,'field-help');
      function updateTradeHandling(){
        const percentage=sizingMode.value==='percentage_risk';
        for(const phase of ['evaluation','funded']){const f=tradeFields[phase];f.minimum.disabled=!percentage;f.minimumLabel.hidden=!percentage;
          f.help.textContent=(f.action.value==='skip'?'Skip if the intended position’s stop risk reaches the remaining daily or account allowance.':'Use captured source MAE to detect an account-limit exit, assuming an exact fill at the limit. Daily hits stop the session; account breaches terminate the account. Missing excursion evidence blocks launch.')+(percentage&&f.minimum.checked?' One-contract override is enabled: actual planned risk can exceed the selected percentage.':'')+' Settings freeze before OOS; deviations are reported, not hidden.';
        }
      }
      function toggleSizing(){
        disclosure.textContent='Saved opportunities · Size from the causal protective stop, never MAE. Choose account-limit handling independently per phase. Exact stop/limit fills exclude gap overshoot. Skips and early exits retain the original opportunity schedule; no alternative setups are generated. IS selects independently; frozen OOS never reselects.';
        const percentage=sizingMode.value==='percentage_risk';
        for(const phase of ['evaluation','funded']){riskGroups[phase].hidden=!percentage;for(const field of Object.values(riskFields[phase]))field.disabled=!percentage;for(const bound of ['minimum','maximum']){const field=fields[phase+'_'+bound+'_micros'];field.disabled=percentage;field.closest('label').hidden=percentage;}}
        updateTradeHandling();
      }
      sizingMode.onchange=()=>{toggleSizing();resourcePreview();};toggleSizing();
      const rules=node('div');advanced.append(rules);
      advanced.append(disclosure);
      const preview=node('p',undefined,'prop-sim-preflight');preview.id='prop-sim-preflight';preview.setAttribute('role','status');form.append(preview);
      form.append(node('p','Run checks the source, executes both IS searches, automatically freezes up to three Evaluation sizes and two Funded sizes, then runs OOS qualification. No follow-up selection or confirmation is required.','field-help'));if(defaults.automatic_selection_policy)detail(form,'Automatic sizing rules',defaults.automatic_selection_policy);
      const buttons=node('div',undefined,'mechanic-downloads'),check=node('button','Check source and settings','button secondary'),run=node('button','Run IS and OOS','button primary');check.type=run.type='button';check.id='prop-sim-check';run.id='prop-sim-run';run.disabled=true;buttons.append(check,run);form.append(buttons);
      const notice=node('p');notice.id='prop-sim-status';notice.setAttribute('role','status');form.append(notice);
      run.setAttribute('aria-describedby',notice.id);check.setAttribute('aria-describedby',notice.id);
      let checked=false,busy=false,gridError='',requestId=crypto.randomUUID(),saved;
      let deleting=false;
      async function requestDelete(id){
        if(deleting)return;deleting=true;
        host.querySelectorAll('[data-delete-simulation]').forEach(button=>button.disabled=true);
        try{
          const plan=await read('/api/prop-sim/'+id+'/deletion');
          if(!alive())return;
          if(!plan.deleted&&!plan.deletable){notice.textContent=plan.dependent_forward_monitors?.length?'This simulation is retained by forward observation monitors. Their frozen policy and reports must remain available.':'This simulation has queued or running jobs. Stop them or wait before deleting.';setup.open=true;return;}
          if(!plan.deleted&&!window.confirm(`Delete saved simulation?\n${profiles[plan.profile_id]?.name||plan.profile_id} · ${plan.strategy_id.replaceAll('_',' ')}\nSaved ${new Date(plan.created_at_utc).toLocaleString()}\n\nRemove ${plan.analysis_ids_to_delete.length} unshared phase reports. Keep ${plan.retained_analyses.length} shared/protected reports.\nDatasets, source backtests, campaign phases, OOS and Monte Carlo results are kept.`))return;
          await read('/api/prop-sim/'+id,'DELETE',{confirmation_sha256:plan.confirmation_sha256});
          if(alive()){if(location.hash==='#prop-sim?deleted='+id)await render();else location.hash='#prop-sim?deleted='+id;}
        }catch(error){if(alive()){notice.textContent='Could not delete simulation: '+error.message;setup.open=true;}}
        finally{deleting=false;if(alive())host.querySelectorAll('[data-delete-simulation]').forEach(button=>button.disabled=!button.dataset.deleteSimulation||Object.values(saved?.phases||{}).some(p=>['queued','running'].includes(p.status)));}
      }
      function deleteButton(id,text='Delete simulation'){
        const button=node('button',text,'button danger');button.type='button';button.dataset.deleteSimulation=id||'';button.disabled=!id;button.onclick=()=>requestDelete(id);return button;
      }
      if(deletedId){
        const receipt=await read('/api/prop-sim/'+deletedId+'/deletion');if(!alive())return;if(!receipt.deleted)throw Error('This simulation is still saved. Open it from Saved simulations.');
        const message=node('section',undefined,'panel prop-sim-deleted');message.setAttribute('role','status');
        message.append(node('p',`Saved simulation deleted. ${receipt.analysis_ids_to_delete.length} unshared reports removed; ${receipt.retained_analyses.length} shared/protected reports kept. Source datasets and campaign results are unchanged.`));
        if(receipt.cleanup_pending?.length){message.append(node('p','Some report files still need cleanup.'));message.append(deleteButton(deletedId,'Retry file cleanup'));}
        host.prepend(message);
      }

      const update=()=>{
        const item=picker.value===''?null:sources.items[Number(picker.value)],support=item?.sizing_support?.[sizingMode.value];
        const invalid=[...form.elements].find(field=>field.willValidate&&!field.validity.valid);
        let reason=!item?'Choose a qualified campaign configuration.':support?.supported===false?(support.reason||'Selected configuration does not support this sizing mode.'):gridError;
        if(!reason&&invalid){
          const label=[...(invalid.closest('label')?.childNodes||[])].filter(n=>n.nodeType===Node.TEXT_NODE).map(n=>n.textContent).join('').trim()||invalid.id;
          const phase=invalid.id.startsWith('prop-sim-evaluation')?'Evaluation sizing · ':invalid.id.startsWith('prop-sim-funded')?'Funded sizing · ':'';
          reason=`${phase}${label}: ${invalid.validationMessage}`;
        }
        check.disabled=run.disabled=busy||!!reason;
        if(reason&&!busy){notice.textContent='Cannot run: '+reason;notice.dataset.blocked='true';}
        else if(!reason&&notice.dataset.blocked){notice.textContent='Ready. Run will check the source and execute both IS and OOS phases automatically.';delete notice.dataset.blocked;}
      };
      function resourcePreview(){
        gridError='';const paths=Number(fields.simulations.value),counts={};
        for(const phase of ['evaluation','funded']){
          try{const values=sizingMode.value==='percentage_risk'?expandedGrid(phase):null;if(!values&&Number(fields[phase+'_maximum_micros'].value)<Number(fields[phase+'_minimum_micros'].value))throw Error('Maximum MNQ must be at least Minimum MNQ.');counts[phase]=values?values.length:Math.max(0,Number(fields[phase+'_maximum_micros'].value)-Number(fields[phase+'_minimum_micros'].value)+1);riskGroups[phase].dataset.expanded=values?.join(', ')||'';if(values){const base=riskFields[phase].reference.value==='available_drawdown_cushion'?2000:50000,amounts=values.map(v=>Number(v)*base/100),money=v=>v>0&&v<.01?'less than $0.01':'$'+fmt(v);riskGroups[phase].querySelector('[data-initial-risk-budget]').textContent=`Initial planned budget: ${money(amounts[0])}${amounts.length>1?'–'+money(amounts.at(-1)):''} · ${fmt(amounts[0]/2000*100)}${amounts.length>1?'–'+fmt(amounts.at(-1)/2000*100):''}% of the initial $2,000 account drawdown. ${riskFields[phase].reference.value==='initial_configured_capital'?'The declared dollar budget stays fixed.':'This reference changes with account state and deductions.'}`;}}catch(error){gridError=`${phase==='evaluation'?'Evaluation':'Funded'} sizing: ${error.message}`;preview.textContent=gridError;update();return;}
        }
        preview.textContent=`${counts.evaluation} Evaluation sizes + ${counts.funded} Funded sizes · ${paths.toLocaleString()} paths per size, per phase · ${((counts.evaluation+counts.funded)*paths).toLocaleString()} total paths. The path count does not shrink with the size range. Both searches use IS history only. Automatic frozen-size assessment adds 5,000 IS/OOS account paths per history/deadline, five 1,000-path stress checks and up to 24 chronological starts; no nested historical refits.${sizingMode.value==='percentage_risk'?` Evaluation: ${riskGroups.evaluation.dataset.expanded}%. Funded: ${riskGroups.funded.dataset.expanded}%. Exact grids; frozen OOS choices receive account Monte Carlo, chronological starts and predefined stress checks. No nested historical refits.`:''}`;update();
      }
      function applyAccount(reset){
        const id=accountPicker.value,p=profiles[id];
        consistencyLabel.hidden=id!=='lucidflex-50k';if(reset||id!=='lucidflex-50k')consistency.value='40';
        for(const phase of ['evaluation','funded'])for(const bound of ['minimum','maximum']){const input=fields[phase+'_'+bound+'_micros'];input.max=String(p.size_limits[phase]);if(Number(input.value)>p.size_limits[phase]){input.value=String(p.size_limits[phase]);notice.textContent='Size range adjusted to the selected account limit.';}}
        for(const phase of ['evaluation','funded']){riskFields[phase].maximum_contracts.max=String(p.size_limits[phase]);if(reset)riskFields[phase].maximum_contracts.value=String(p.size_limits[phase]);}
        if(reset)for(const name of ['evaluation_price','activation_fee','commission_per_mnq_side'])fields[name].value=p.defaults[name];
        if(id==='apex-50k-eod')dll.checked=true;dll.disabled=id==='apex-50k-eod';fields.activation_fee.readOnly=id==='lucidflex-50k';
        const dollars=value=>Number(value).toLocaleString('en-US',{style:'currency',currency:'USD',maximumFractionDigits:0}),evaluationDll=dollars(p.evaluation_rules.daily_loss_limit);
        if(p.funded_rules.daily_loss===p.evaluation_rules.daily_loss_limit)dllText.textContent=`${evaluationDll} daily loss limit — Evaluation and Funded`;
        else{const limits=p.funded_rules.levels.map(level=>level[2]);dllText.textContent=`Daily loss limit — ${evaluationDll} Evaluation; ${dollars(Math.min(...limits))}–${dollars(Math.max(...limits))} Funded, by tier`;}
        accountInfo.textContent=`$3,000 target · $2,000 maximum drawdown · Evaluation up to ${p.size_limits.evaluation} MNQ / Funded up to ${p.size_limits.funded} MNQ.`;
        ruleNote.textContent=id==='lucidflex-50k'?`${consistency.value}% Evaluation consistency${consistency.value==='50'?' · add-on price must be included in your purchase fee':''}. No activation fee. Funded has a 90% trader share and no consistency rule. Set your actual purchase price for the chosen options.`:'Funded sizes follow account scaling tiers. Scenario purchase and activation fees are editable.';
        rules.replaceChildren();detail(rules,'Account rules and model assumptions',{selection:{profile_id:id,daily_loss_limit:dll.checked},evaluation:{...p.evaluation_rules,consistency:id==='lucidflex-50k'?Number(consistency.value)/100:null,daily_loss_limit:dll.checked?p.evaluation_rules.daily_loss_limit:null},funded:id==='lucidflex-50k'?{...p.funded_rules,daily_loss:dll.checked?1200:null}:p.funded_rules,notes:p.notes,default_profile_review:p.rule_provenance});
        checked=false;resourcePreview();
      }
      accountPicker.onchange=()=>applyAccount(true);dll.onchange=()=>applyAccount(false);
      consistency.onchange=()=>{fields.evaluation_price.value='';fields.evaluation_price.required=true;fields.evaluation_price.placeholder='Enter your checkout price including add-on';applyAccount(false);notice.textContent='Enter the actual purchase fee for this account variant, then check again.';};
      function select(){
        checked=false;sourceInfo.replaceChildren();const item=sources.items[Number(picker.value)];
        if(picker.value!==''&&item){sourceInfo.append(node('p',`IS sizing window ${item.plan.is_start} → ${item.plan.is_end}.`,'field-help'));if(item.sizing_support){for(const [mode,label] of [['fixed_contracts','Fixed contracts'],['percentage_risk','Percentage risk']]){const support=item.sizing_support[mode];sourceInfo.append(node('p',`${label}: ${support.supported?'supported':support.reason}`,'field-help'));}}detail(sourceInfo,'Frozen parameters',item.parameters);const links=node('div',undefined,'mechanic-downloads');link(links,'Open IS source backtest',`#backtests/report/${item.source_backtest_id}`);link(links,'Open campaign and OOS evidence',`#campaigns/workflows/${item.selection.workflow_id.replaceAll('-','')}/oos?job=${item.selection.oos_job_id.replaceAll('-','')}`);sourceInfo.append(links);}update();
      }
      picker.onchange=select;form.oninput=()=>{updateTradeHandling();checked=false;notice.textContent='Settings changed. Run will check the source and execute both IS and OOS phases automatically.';resourcePreview();};form.onsubmit=e=>e.preventDefault();
      function body(){
        const source=sources.items[Number(picker.value)];if(picker.value===''||!source)throw Error('Choose one qualified configuration.');
        const value={request_id:requestId,automatic:true,profile_id:accountPicker.value,daily_loss_limit:dll.checked,evaluation_consistency_percent:Number(consistency.value),selections:[source.selection]};
        for(const [name,,type] of names){if(sizingMode.value==='percentage_risk'&&name.endsWith('_micros'))continue;value[name]=name==='maximum_funded_breach_probability'&&fields[name].value.trim()===''?null:name==='closures'?fields[name].value.split(',').map(s=>s.trim()).filter(Boolean):type==='number'||name==='block_weekdays'?Number(fields[name].value):fields[name].value;}
        for(const phase of ['evaluation','funded'])value[phase+'_trade_handling']={account_limit_action:tradeFields[phase].action.value,minimum_one_contract:sizingMode.value==='percentage_risk'&&tradeFields[phase].minimum.checked};
        if(sizingMode.value==='percentage_risk'){value.search_kind='percentage_risk';for(const phase of ['evaluation','funded']){expandedGrid(phase);value[phase+'_percentage_grid']=Object.fromEntries(Object.entries(riskFields[phase]).map(([key,input])=>[key,input.type==='checkbox'?input.checked:key==='maximum_contracts'?Number(input.value):input.value]));}}return value;
      }
      check.onclick=async()=>{if(!form.reportValidity())return;busy=true;update();notice.textContent='Checking qualification, costs and source compatibility…';try{const data=await read('/api/prop-sim/check','POST',body());if(alive()){checked=true;notice.textContent=`Source compatible · ${data.phases.evaluation.candidate_search_count} Evaluation sizes and ${data.phases.funded.candidate_search_count} Funded sizes.`;}}catch(error){if(alive()){checked=false;notice.textContent=error.message;}}finally{busy=false;if(alive())update();}};
      run.onclick=async()=>{if(!form.reportValidity())return;busy=true;update();notice.textContent='Checking source and starting automatic IS → selection → OOS…';try{const data=await read('/api/prop-sim','POST',body());if(alive())location.hash='#prop-sim?analysis='+data.id;}catch(error){if(alive())notice.textContent=error.message;}finally{busy=false;if(alive())update();}};
      const results=node('div');results.id='prop-sim-results';host.append(results);
      if(history.items.length){const historyLabel=node('label','Saved simulations'),historySelect=node('select');historySelect.id='prop-sim-history';historySelect.add(new Option('Choose saved results',''));for(const old of history.items){const p=profiles[old.configuration.profile_id||'apex-50k-eod'],e=range(old.configuration,'evaluation'),f=range(old.configuration,'funded');historySelect.add(new Option(old.configuration.mode==='portfolio'?`${new Date(old.created_at_utc).toLocaleString()} · Portfolio cash flow · ${p.name}`:`${new Date(old.created_at_utc).toLocaleString()} · ${p.name} · ${old.configuration.search_kind==='percentage_risk'?`Eval ${old.configuration.evaluation_percentage_grid.minimum}–${old.configuration.evaluation_percentage_grid.maximum}% / Funded ${old.configuration.funded_percentage_grid.minimum}–${old.configuration.funded_percentage_grid.maximum}%`:`Eval ${e.minimum}–${e.maximum} / Funded ${f.minimum}–${f.maximum} MNQ`}`,old.id));}historySelect.value=selectedId||'';historyLabel.append(historySelect,deleteButton(selectedId,'Delete selected simulation'));historyLabel.className='prop-sim-history';host.append(historyLabel);historySelect.onchange=()=>{location.hash=historySelect.value?'#prop-sim?analysis='+historySelect.value:'#prop-sim';};}
      const phasePanels={},loaded={},validationControllers={},phaseConclusions={};
      function paintConclusions(){
        const title=results.querySelector('.prop-sim-run-heading');if(!title)return;
        let overview=results.querySelector('#prop-sim-conclusions');
        if(!overview){overview=node('section',undefined,'panel');overview.id='prop-sim-conclusions';overview.setAttribute('aria-label','Conclusion and next steps');title.after(overview);}
        overview.replaceChildren(node('h2','Conclusion & next steps'),node('p','These conclusions apply to the prop sizing plans. Campaign results remain preserved; a completed calculation is not the same as a passing qualification.','field-help'));
        const grid=node('div',undefined,'prop-sim-conclusion-overview');overview.append(grid);
        for(const phase of ['evaluation','funded']){
          const item=node('div'),summary=node('div');item.append(node('h3',phase==='evaluation'?'Evaluation':'Funded'),summary);grid.append(item);
          window.propSimConclusion.render(summary,phaseConclusions[phase]||{current:true,tone:'hold',title:'Qualification pending',next:'Wait for this phase’s saved OOS assessment. Completed calculations alone do not mean qualification passed.'},{compact:true,onEvidence:()=>phasePanels[phase]?.querySelector('.prop-sim-conclusion')?.scrollIntoView({behavior:'smooth',block:'start'})});
        }
      }
      function validationControls(parent,phase,report,selection){
        const automatic=!!saved.automation;const root=node('section',undefined,'prop-sim-validation');root.id='prop-sim-'+phase+'-validation';parent.append(root);
        const conclusion=node('section');conclusion.id='prop-sim-'+phase+'-conclusion';conclusion.setAttribute('aria-label',phase+' conclusion and next step');parent.insertBefore(conclusion,parent.querySelector('.prop-sim-insight'));
        const heading=node('h3','Selected sizes and validation'),intro=node('p','Select up to four sizes in the IS results table above, then freeze them before OOS assessment.','field-help');root.append(heading,intro);
        const autoStatus=node('div',undefined,'prop-sim-auto-status');if(automatic)root.append(autoStatus);
        const selected=selection.selected,selectionSummary=node('p',undefined,'prop-sim-selection-summary');selectionSummary.id='prop-sim-'+phase+'-selection';selectionSummary.setAttribute('aria-live','polite');
        const noteLabel=node('label','Selection note (required)'),rationale=node('input');rationale.type='text';rationale.required=true;rationale.maxLength=4000;rationale.placeholder='Why these sizes?';rationale.setAttribute('aria-label',phase+' freeze rationale');noteLabel.append(rationale);
        const frozenNotice=node('p',undefined,'field-help'),message=node('p');message.setAttribute('role','status');
        const freeze=node('button','Freeze selected sizes','button primary');freeze.type='button';freeze.id='prop-sim-'+phase+'-freeze';
        const primaryActions=node('div',undefined,'mechanic-downloads'),additional=node('details',undefined,'prop-sim-diagnostics');additional.id='prop-sim-'+phase+'-diagnostics';const diagnosticsTitle=node('summary','Additional diagnostics');additional.append(diagnosticsTitle,node('p','Optional IS robustness and extra-path checks. These preserve the frozen sizes and do not select new choices.','field-help'));
        const actions=node('div',undefined,'mechanic-downloads'),pathLabel=node('label','Diagnostic paths per frozen size'),paths=node('input');paths.type='number';paths.min='8';paths.max='20000';paths.step='1';paths.value=String(Math.min(20000,Math.max(1000,saved.configuration.simulations*2)));paths.setAttribute('aria-label',phase+' diagnostic paths');pathLabel.append(paths);
        const history=node('div',undefined,'prop-sim-current-assessment'),diagnosticHistory=node('div'),buttons=[],cards=new Map(),archives=new Map(),summaries=new Map();const past=node('details',undefined,'prop-sim-history'),pastTitle=node('summary','Assessment history'),pastRows=node('div');past.append(pastTitle,pastRows);let currentByKind={},currentMain=null,displayAttempt=null,displayCurrent=false,conclusionKey=null;let frozen=null,busy=false,active=false,policy=null,reviewCompatible=true,hasOOS=false,hasQualification=false,editingPolicy=false,editHash=null;
        const policyBox=node('details',undefined,'prop-sim-policy'),policyForm=node('form'),policyStatus=node('p',undefined,'field-help'),policyFields={};
        policyBox.append(node('summary','Optional business limits and historical policies'),node('h4','Declare OOS assessment limits'),node('p','Saved versions remain in history. Use Revise assessment limits to change your decision; earlier jobs keep their original limits and verdicts. IS deterioration is a separate warning, not an automatic failure.','field-help'),policyStatus);
        const policyGrid=node('div',undefined,'prop-sim-settings');policyForm.append(policyGrid);
        const policySpecs=phase==='evaluation'?[['maximum_cost_per_funded','Maximum mean acquisition cost · USD','0.01',''],['maximum_calendar_days_to_funded','Maximum mean calendar days to funded','1','']]:[['minimum_funded_receipts','Minimum mean trader receipts · USD','0.01','']];
        policySpecs.push(['minimum_history_calendar_days','Minimum historical coverage · calendar days','1','90'],['minimum_closed_trades','Minimum closed source trades','1','30'],['account_start_count','Prespecified account starts','1','5']);
        for(const [name,text,step,value] of policySpecs){const label=node('label',text),input=node('input');input.type='number';input.step=step;input.min=step;input.required=true;input.value=value;input.setAttribute('aria-label',phase+' '+name);if(name==='account_start_count'){input.min='2';input.max='12';}policyFields[name]=input;label.append(input);policyGrid.append(label);}
        const reasonLabel=node('label','Reason for revising limits'),reason=node('textarea');reason.required=true;reason.maxLength=2000;reason.setAttribute('aria-label',phase+' policy revision reason');reasonLabel.append(reason);reasonLabel.hidden=true;reason.disabled=true;policyForm.append(reasonLabel);
        const policyActions=node('div',undefined,'mechanic-downloads'),savePolicy=node('button','Save assessment limits','button secondary'),revisePolicy=node('button','Revise assessment limits','button secondary'),cancelPolicy=node('button','Cancel revision','button secondary');savePolicy.type='submit';revisePolicy.type=cancelPolicy.type='button';revisePolicy.hidden=cancelPolicy.hidden=true;policyActions.append(savePolicy,revisePolicy,cancelPolicy);policyForm.append(policyActions);const policyHistory=node('details'),policyHistoryTitle=node('summary','Policy history'),policyHistoryRows=node('div');policyHistory.append(policyHistoryTitle,policyHistoryRows);policyHistory.hidden=true;policyBox.append(policyForm,policyHistory);additional.append(policyBox);
        const rules=node('details',undefined,'prop-sim-policy');rules.append(node('summary','OOS evidence checks'),node('p','Frozen choices receive 5,000 account paths per IS/OOS history, up to 24 chronological account starts, and five predefined stress scenarios at 1,000 paths each. Evaluation measures funding and expenditure at 90, 180 and 365 days. Funded retains its configured receipt horizon.'),node('p','Requires 12 complete OOS months and 100 closed source trades. Simulation precision targets: relative standard error ≤ 5% for monetary/waiting means and probability interval half-width ≤ 2.5 percentage points. These are conditional numerical tolerances, not future confidence.','field-help'),node('p','Point-estimate changes below 70% of IS funding probability/receipts, or Evaluation capped waiting above 1.5× IS, require investigation. Chronological failures and stress retention below 70% also trigger review. They are not historical confidence-interval failures. No nested refits or required dollar declarations.','field-help'),node('p','Evidence ready for paper review still requires supplied signal, sizing and fill observations: 20 recorded sessions, 30 closed trades and zero unexplained discrepancies. Historical reports retain their original policy and verdict.','field-help'));additional.append(rules);
        additional.append(pathLabel,actions,diagnosticHistory);
        const steps=node('ol',undefined,'prop-sim-steps');steps.setAttribute('aria-label',phase+' simulation workflow');for(const text of (automatic?['IS sizing','Automatic sizes frozen','OOS results']:['IS sizing','Frozen choices','OOS assessment','Forward review']))steps.append(node('li',text));root.prepend(steps);
        root.append(selectionSummary,frozenNotice,noteLabel,freeze,primaryActions,message,history,past,additional);
        const url=`/api/prop-sim/${selectedId}/validation/${phase}`;
        function updateSelection(){
          const sizes=report.calculations.candidates.filter(r=>selected.has(r.candidate_id)).map(r=>policyLabel(r.manifest.configuration));
          selectionSummary.textContent=sizes.length?`${frozen?'Frozen choices':'Selected'}: ${sizes.join(' / ')} · ${sizes.length}${frozen?' size'+(sizes.length===1?'':'s'):' of 4 sizes'}`:automatic?'Automatic IS size selection pending.':'No sizes selected · choose up to four in the IS results table.';
          freeze.disabled=!selection.ready||!selection.compatible||busy||!selected.size||!rationale.value.trim();
          for(const button of buttons){const kind=button.dataset.studyKind,existing=kind==='qualification'&&currentMain?.kind==='forward_review'?currentMain:currentByKind[kind],view=['qualification','oos','account_starts'].includes(kind)&&existing;button.dataset.viewRequest=view?existing.request_id:'';button.textContent=view?(existing.status==='complete'?(kind==='qualification'?'View OOS results':kind==='account_starts'?'View account-start sensitivity':'View business assessment'):'View assessment progress'):button.dataset.runLabel;if(automatic){button.hidden=kind==='qualification'&&!view&&saved.automation.phases[phase].stage!=='complete';if(kind==='qualification'&&!view&&saved.automation.phases[phase].stage==='complete')button.textContent='Run current evidence review';}button.disabled=view?busy:!selection.compatible||!frozen||busy||active||(kind==='oos'&&(!policy||!reviewCompatible||editingPolicy))||(kind==='account_starts'&&!hasQualification&&!hasOOS);}

          savePolicy.disabled=busy||!!policy&&!editingPolicy||!selection.compatible;
          revisePolicy.disabled=cancelPolicy.disabled=busy||!selection.compatible;
          selection.syncRows();
        }
        selection.onChange=updateSelection;rationale.oninput=updateSelection;updateSelection();
        function policyEditing(edit){editingPolicy=edit;editHash=edit?policy.policy_sha256:null;for(const [name,input] of Object.entries(policyFields)){if(!edit&&policy)input.value=String(policy.limits[name]);input.disabled=!!policy&&!edit;}reasonLabel.hidden=!edit;reason.disabled=!edit;reason.value='';savePolicy.hidden=!!policy&&!edit;savePolicy.textContent=edit?'Save new policy version':'Save assessment limits';revisePolicy.hidden=!policy||edit;cancelPolicy.hidden=!edit;updateSelection();}
        revisePolicy.onclick=()=>policyEditing(true);cancelPolicy.onclick=()=>policyEditing(false);
        policyForm.onsubmit=async event=>{event.preventDefault();if(!policyForm.reportValidity())return;busy=true;updateSelection();try{const declaration={};for(const [name,input] of Object.entries(policyFields))declaration[name]=['maximum_cost_per_funded','minimum_funded_receipts'].includes(name)?input.value:Number(input.value);if(editingPolicy){declaration.previous_policy_sha256=editHash;declaration.reason=reason.value;}await read(url+(editingPolicy?'/policy/revisions':'/policy'),'POST',declaration);editingPolicy=false;editHash=null;reason.value='';message.textContent='Policy saved. Run OOS assessment to apply it; compatible saved Monte Carlo results will be reused.';await refreshValidation();}catch(e){message.textContent=e.message;}finally{busy=false;updateSelection();}};
        freeze.onclick=async()=>{if(!selected.size||!rationale.value.trim())return;busy=true;updateSelection();try{await read(url+'/freeze','POST',{candidate_ids:[...selected],rationale:rationale.value});await refreshValidation();}catch(e){message.textContent=e.message;}finally{busy=false;updateSelection();}};
        for(const [kind,text] of [['qualification','Run OOS qualification'],['oos','Run optional business assessment'],['is_robustness','Check IS blocks and subperiods'],['precision','Run more IS paths for frozen sizes']]){
          const button=node('button',text,kind==='qualification'?'button primary':'button secondary');button.type='button';button.disabled=true;button.dataset.studyKind=kind;button.dataset.runLabel=text;buttons.push(button);(kind==='qualification'?primaryActions:kind==='oos'?policyActions:actions).append(button);
          button.onclick=async()=>{if(busy)return;if(button.dataset.viewRequest){await reveal(button.dataset.viewRequest);return;}const diagnostic=['is_robustness','precision'].includes(kind);if(diagnostic&&!paths.reportValidity())return;busy=true;updateSelection();message.textContent='Submitting saved assessment…';try{const body={request_id:crypto.randomUUID(),kind};if(diagnostic)body.paths=Number(paths.value);const attempt=await read(url,'POST',body);message.textContent=attempt.reused?'Opened the existing assessment; no duplicate job or report was created.':'Assessment queued. You can navigate away and return here or use Job history.';await refreshValidation();if(attempt.reused)await reveal(attempt.request_id);timer=setTimeout(refresh,2000);}catch(e){message.textContent=e.message;}finally{busy=false;updateSelection();}};
        }
        function studyTable(box,study){
          tradeBehavior(box,study.calculations.candidates,'OOS / assessment');
          for(const row of study.calculations.candidates){
            const d=row.observed_bar_diagnostics||row.native_forecast?.observed_bar_diagnostics;
            if(d){box.append(node('h4',policyLabel(row.configuration)));window.nativeReplay.renderCoverage(box,d);}
          }
          if(study.calculations.candidates.some(r=>r.prop_qualification?.version==='prop-complementary-evidence-v2')){
            for(const [index,row] of study.calculations.candidates.entries()){const evidence=node('details',undefined,'prop-evidence-candidate');evidence.open=index===0;evidence.append(node('summary',policyLabel(row.configuration)+' · '+window.propSimConclusion.candidate(row).action));window.propSimConclusion.renderEvidence(evidence,row);box.append(evidence);}
            return;
          }
          const rows=study.calculations.candidates,isEval=phase==='evaluation',oos=['oos','account_starts','qualification','forward_review'].includes(study.calculations.assessment_kind);
          const columns=[[rows.some(r=>r.configuration?.sizing?.policy?.kind==='percentage_risk')?'Sizing policy':'MNQ',r=>policyLabel(r.configuration)],['Scenario',r=>r.scenario],['Status',r=>r.status]];
          if(rows.some(r=>r.prop_qualification))columns.push(['OOS qualification',r=>r.prop_qualification?.status||'—'],['Forward execution',r=>r.prop_qualification?.forward_execution?.status||'PENDING']);
          if(rows.some(r=>r.prop_qualification))columns.push(['Next step',r=>displayCurrent&&displayAttempt?.analysis_id===study.id?window.propSimConclusion.candidate(r).action:'Inspect historical verdict']);
          if(oos&&!rows.some(r=>r.prop_qualification))columns.push(['Economic verdict',r=>r.economic_assessment?.verdict||'Historical · not assessed'],['IS change warning',r=>r.economic_assessment?(r.economic_assessment.watch?'Review deterioration':'None'):'—']);
          if(isEval){
            if(oos)columns.push(['IS cost · USD',r=>fmt(r.is_comparison.cost_per_funded.is_value)],['IS mean days',r=>fmt(r.is_comparison.expected_calendar_days_to_funded.is_value)]);
            columns.push(['Mean cost · USD',r=>fmt(r.metrics.cost_per_funded)],['Mean calendar days',r=>fmt(r.metrics.expected_calendar_days_to_funded)],['Median days',r=>fmt(r.metrics.median_calendar_days_to_funded)],['P90 days',r=>fmt(r.metrics.p90_calendar_days_to_funded)],['First-account pass',r=>pct(r.metrics.pass_probability)]);
            if(oos)columns.push(['Days / IS',r=>fmt(r.is_comparison.expected_calendar_days_to_funded.oos_over_is)],['Cost / IS',r=>fmt(r.is_comparison.cost_per_funded.oos_over_is)]);
          }else{
            if(oos)columns.push(['IS mean receipts',r=>fmt(r.is_comparison.expected_funded_cash_payouts_within_horizon.is_value)]);
            columns.push(['Mean receipts · USD',r=>fmt(r.metrics.expected_funded_cash_payouts_within_horizon)],['Breach',r=>pct(r.metrics.account_breach_probability)],['First payout',r=>pct(r.metrics.probability_first_payout)],['Pending cash · USD',r=>fmt(r.metrics.expected_pending_cash)],['Account deductions · USD',r=>fmt(r.metrics.expected_gross_account_deductions)]);
            if(oos)columns.push(['Receipts / IS',r=>fmt(r.is_comparison.expected_funded_cash_payouts_within_horizon.oos_over_is)]);
          }
          if(automatic){
            const keep=new Set(isEval?['MNQ','Sizing policy','OOS qualification','Next step','Economic verdict','Mean cost · USD','Mean calendar days','Days / IS','Cost / IS']:['MNQ','Sizing policy','OOS qualification','Next step','Economic verdict','Mean receipts · USD','Receipts / IS','Breach','First payout']);
            for(let i=columns.length-1;i>=0;i--)if(!keep.has(columns[i][0]))columns.splice(i,1);
          }
          const wrap=node('div',undefined,'optimization-scroll'),table=node('table',undefined,'library-table prop-result-table'),head=node('tr'),body=node('tbody');columns.forEach(([name])=>head.append(node('th',name)));
          for(const row of rows){const tr=node('tr');columns.forEach(([,get])=>tr.append(node('td',String(get(row)??'—'))));body.append(tr);
            if(row.prop_qualification){const q=row.prop_qualification,tr=node('tr'),td=node('td');td.colSpan=columns.length;const panel=node('details',undefined,'prop-sim-review-details');panel.append(node('summary',`${policyLabel(row.configuration)} · ${q.status.replaceAll('_',' ')}`),node('p',q.interpretation,'field-help'));const list=node('ul');for(const c of q.evidence)list.append(node('li',`${c.passed?'PASS':'INSUFFICIENT'} · ${c.label}: ${c.actual} · required ${c.required}`));for(const c of q.checks)list.append(node('li',`${c.status.replaceAll('_',' ')} · ${c.label}: OOS / IS ${fmt(c.point_ratio)} · historical interval [${fmt(c.lower)}, ${fmt(c.upper)}] · required ${c.direction==='maximum'?'upper ≤':'lower ≥'} ${fmt(c.limit)}`));list.append(node('li',`${q.inner_precision_ok?'PASS':'INSUFFICIENT'} · Inner Monte Carlo relative standard error ≤ 5%`));panel.append(list,node('p',`${q.historical_replicates.toLocaleString()} historical replicates · nominal simultaneous ${pct(q.confidence)} confidence · family budget ${q.family_test_budget} metric tests. Undefined replicate ratios are retained as insufficient evidence.`,'field-help'));const f=q.forward_execution;panel.append(node('h4','Forward execution · '+f.status));if(f.checks){const items=node('ul');for(const c of f.checks)items.append(node('li',`${c.passed?'PASS':'NOT MET'} · ${c.label}: ${c.actual} · required ${c.required}`));panel.append(items,node('p',f.notes));if(f.source)link(panel,'Open captured forward assessment',`#backtests/prop/job/${f.source.analysis_id}`);}else panel.append(node('p','Paper observations and closed-trade parity review are required before a limited live pilot.'));for(const text of q.limitations||[])panel.append(node('p',text,'field-help'));detail(panel,'Saved prerequisites and Monte Carlo precision',{prerequisites:q.prerequisites,uncertainty:row.uncertainty});td.append(panel);tr.append(td);body.append(tr);}
            if(row.economic_assessment){const review=row.economic_assessment,detailRow=node('tr'),cell=node('td');cell.colSpan=columns.length;
              const panel=node('details',undefined,'prop-sim-review-details');panel.append(node('summary',`${policyLabel(row.configuration)} · ${review.verdict}${review.watch?' · review IS deterioration':''}`));
              panel.append(node('p',review.interpretation,'field-help'));
              const checks=node('ul');for(const c of [...review.evidence,...review.economic_checks])checks.append(node('li',`${c.passed===null?'UNKNOWN':c.passed?'PASS':'FAIL'} · ${c.label}: ${typeof c.actual==='number'?fmt(c.actual):c.actual??'unavailable'} · required ${c.comparison||'≥'} ${typeof (c.limit??c.required)==='number'?fmt(c.limit??c.required):c.limit??c.required??'frozen constraint'}`));panel.append(checks);
              for(const c of review.is_changes){const probability=c.percentage_points!==null;panel.append(node('p',`${c.metric.replaceAll('_',' ')} · IS ${probability?pct(c.is_value):fmt(c.is_value)} → OOS ${probability?pct(c.oos_value):fmt(c.oos_value)} · ${probability?fmt(c.percentage_points)+' percentage points':fmt(c.delta)+' ('+(c.relative_change_pct===null?'relative change unavailable':fmt(c.relative_change_pct)+'%')+')'}${c.adverse?' · watch':''}`,'field-help'));}
              const summary=row.outcome_summary;
              if(isEval)panel.append(node('p',`Funding-time P90: ${fmt(summary.p90_calendar_days)} calendar days · ${summary.unresolved_paths} unresolved paths. Quantile uses all paths; unavailable if any path is unresolved.`,'field-help'));
              else{panel.append(node('p',`No cash received: ${pct(summary.probability_zero_received_cash)} · cash P10 / median / P90: ${fmt(summary.cash_quantiles?.p10)} / ${fmt(summary.cash_quantiles?.median)} / ${fmt(summary.cash_quantiles?.p90)} USD. Includes zero-receipt accounts.`));const timing=summary.first_receipt_calendar_days_conditional_on_receipt;panel.append(node('p',`First receipt timing, conditional on receipt (${summary.first_receipt_observations} paths): median ${fmt(timing?.median)}, P75 ${fmt(timing?.p75)}, P90 ${fmt(timing?.p90)} calendar days.`, 'field-help'));const milestones=node('ul');for(const p of summary.payout_milestones)milestones.append(node('li',`Payout ${p.payout} · requested ${pct(p.probability_requested)} · received within horizon ${pct(p.probability_received)}`));panel.append(milestones);}
              detail(panel,'Monte Carlo uncertainty (not future uncertainty)',row.uncertainty||{});cell.append(panel);detailRow.append(cell);body.append(detailRow);}
            if(row.chronological_replay){const actual=row.chronological_replay;const tr=node('tr'),td=node('td');td.colSpan=columns.length;
              td.append(node('p',isEval?`Chronological OOS · ${actual.acquisition_completed?'funded in '+actual.calendar_days_to_funded+' calendar days':'not funded within observed window'} · ${fmt(actual.paid_fees)} USD paid · ${actual.attempts_started??actual.attempts?.length??'Unavailable'} evaluations`:`Chronological OOS · ${fmt(actual.cash_received)} USD received · ${actual.outcome} · ${actual.observed_calendar_days} observed calendar days`,'field-help'));
              detail(td,'Saved chronological events and uncertainty',{chronological:actual,uncertainty:row.uncertainty});tr.append(td);body.append(tr);}
          }
          const thead=node('thead');thead.append(head);table.append(thead,body);wrap.append(table);if(study.calculations.assessment_kind!=='account_starts')box.append(wrap);
          const sensitivity=study.calculations.account_start_sensitivity;
          if(sensitivity){box.append(node('h4','Prespecified chronological account starts'),node('p',`${sensitivity.status} · ${sensitivity.simulations} chronological accounts · ${sensitivity.plan.horizon_calendar_days}-calendar-day window per start. ${sensitivity.interpretation}`,'field-help'));
            if(!sensitivity.plan.starts.length)box.append(node('p','Insufficient coverage for the declared number of full windows. No shorter windows or replacement starts were substituted.'));
            const scroll=node('div',undefined,'optimization-scroll'),t=node('table',undefined,'library-table prop-result-table'),header=node('tr');for(const title of ['MNQ','Start','Cutoff (exclusive)','Outcome',...(isEval?['Paid fees · USD','Calendar days to funded','Evaluations purchased']:['Received · USD','Pending · USD','Receipts'])])header.append(node('th',title));const thead=node('thead');thead.append(header);t.append(thead);const tbody=node('tbody');for(const candidate of sensitivity.candidates){for(const p of candidate.paths){const r=p.result,tr=node('tr');for(const value of [candidate.sizing?policyLabel({micros:candidate.micros,sizing:candidate.sizing}):candidate.micros,p.start_date,p.cutoff_exclusive,isEval?(r.acquisition_completed?'Funded':'Window censored · '+r.outcome):r.outcome,...(isEval?[fmt(r.paid_fees),fmt(r.calendar_days_to_funded),r.attempts_started]:[fmt(r.cash_received),fmt(r.pending_cash),r.number_of_payouts])])tr.append(node('td',String(value)));tbody.append(tr);}const s=candidate.summary,ranges=isEval?[['Paid fees · USD',s.paid_fees],['Calendar days to funded',s.calendar_days_to_funded]]:[['Cash received · USD',s.cash_received],['Pending cash · USD',s.pending_cash]];box.append(node('p',`${candidate.sizing?policyLabel({micros:candidate.micros,sizing:candidate.sizing}):candidate.micros+' MNQ'} · ${isEval?s.funded+' funded / '+s.window_censored+' window-censored':s.zero_receipt_starts+' starts with no receipts'}`));for(const [name,range] of ranges)box.append(node('p',`${name} · ${range?'min '+fmt(range.minimum)+' / median '+fmt(range.median)+' / max '+fmt(range.maximum):'unavailable: includes censored or missing outcomes'}`,'field-help'));box.append(node('p',s.interpretation,'field-help'));}t.append(tbody);scroll.append(t);box.append(scroll);}
          if(!sensitivity&&study.calculations.precision_interpretation)box.append(node('p',study.calculations.precision_interpretation,'field-help'));
          if(!sensitivity&&study.calculations.paired_comparisons?.length)detail(box,'Paired differences between frozen sizes',study.calculations.paired_comparisons);
        }
        const forwardBox=node('details'),forwardTitle=node('summary','Paper execution and parity review'),forwardBody=node('div');forwardBox.append(forwardTitle,forwardBody);forwardBox.hidden=true;root.append(forwardBox);
        forwardBox.ontoggle=async()=>{if(!forwardBox.open)return;forwardBody.replaceChildren();try{const launch=await read(url+'/forward');if(!launch.calculations.recommendation[0].selected_packages.length){forwardBody.append(node('p','No historical GO size is available for forward review.'));return;}const start=node('button','Configure paper observation','button secondary'),launchView=node('div');start.type='button';forwardBody.append(node('p','Use timestamped paper events from the frozen strategy and size. Supplied records and manual review are retained in the existing forward-monitor workflow. No fabricated observations are generated.'),start,launchView);start.onclick=async()=>{document.getElementById('forward-launcher')?.remove();await window.forwardMonitoring.configureLauncher(launchView,launch);const configured=launchView.querySelector('details');if(configured)configured.open=true;};const monitors=await read('/api/forward-monitors?application_id='+selectedId);const select=node('select');select.setAttribute('aria-label',phase+' forward assessment');select.append(new Option('Choose a completed paper observation assessment',''));for(const m of monitors.items||[]){if(m.last_completed_analysis_id)select.append(new Option(m.name+' · '+m.observation_kind,m.last_completed_analysis_id));}const preview=node('button','Load closed trades for parity review','button secondary'),view=node('div');preview.type='button';forwardBody.append(select,preview,view);preview.onclick=async()=>{view.replaceChildren();try{const data=await read(url+'/forward-review/'+select.value);const checks=node('ul');for(const c of data.preview.checks)checks.append(node('li',`${c.passed?'PASS':'NOT MET'} · ${c.label}: ${c.actual} / ${c.required}`));view.append(checks);const reviewed=new Set();for(const e of data.episodes){const label=node('label'),input=node('input');input.type='checkbox';input.onchange=()=>input.checked?reviewed.add(e.id):reviewed.delete(e.id);label.append(input,document.createTextNode(` ${e.trade.start_utc} → ${e.trade.end_utc} · net ${e.trade.net_pnl} · signal and execution parity checked`));view.append(label);}const note=node('textarea');note.placeholder='Describe the signal, sizing and execution parity review, including any explained incidents.';note.setAttribute('aria-label',phase+' forward parity notes');const save=node('button','Save forward execution review','button primary');save.type='button';view.append(note,save);save.onclick=async()=>{save.disabled=true;try{await read(url+'/forward-review','POST',{request_id:crypto.randomUUID(),analysis_id:select.value,reviewed_episode_ids:[...reviewed],notes:note.value});await refreshValidation();timer=setTimeout(refresh,2000);}catch(e){message.textContent=e.message;}finally{save.disabled=false;}};}catch(e){view.append(node('p',e.message));}};}catch(e){forwardBody.append(node('p',e.message));}};
        const studyNames={qualification:'OOS qualification',forward_review:'OOS results and forward execution review',oos:'Business OOS assessment',account_starts:'Account-start sensitivity',is_robustness:'IS block and subperiod robustness',precision:'More-path precision assessment'};
        function showConclusion(){
          const key=displayAttempt?`${displayAttempt.request_id}:${displayAttempt.status}:${displayCurrent}`:'pending';
          const study=displayAttempt&&summaries.get(displayAttempt.request_id);
          if(conclusionKey===key)return;
          let model;
          if(study?.calculations.candidates.some(r=>r.prop_qualification))model=window.propSimConclusion.describe(study.calculations.candidates,{current:displayCurrent});
          else{
            const running=displayAttempt&&['launching','queued','running'].includes(displayAttempt.status);
            model={current:true,tone:'hold',title:running?'Assessment running · hold live deployment':'Qualification pending · hold live deployment',next:running?'Wait for the saved OOS verdict. A running job has not established historical qualification.':'Complete a compatible OOS qualification for the frozen sizes. Job completion and IS profitability alone do not establish live readiness.'};
            if(displayAttempt?.status==='complete'&&!study)return; // Load its saved verdict before interpreting it.
          }
          conclusionKey=key;phaseConclusions[phase]=model;
          window.propSimConclusion.render(conclusion,model,{onEvidence:()=>displayAttempt&&reveal(displayAttempt.request_id),onDiagnostics:()=>{additional.open=true;additional.scrollIntoView({behavior:'smooth',block:'start'});},onForward:()=>{forwardBox.open=true;forwardBox.scrollIntoView({behavior:'smooth',block:'start'});}});
          forwardBox.hidden=!hasQualification||!model.current||!model.forwardEligible;
          paintConclusions();
        }
        async function loadCard(attempt,box){if(attempt.status!=='complete'||box.dataset.loaded||box.dataset.loading)return;box.dataset.loading='true';try{const study=await read(url+'/'+attempt.request_id+'?summary=true');if(!alive())return;summaries.set(attempt.request_id,study);studyTable(box,study);box.dataset.loaded='true';if(attempt===displayAttempt)showConclusion();}finally{delete box.dataset.loading;}}
        function card(attempt){let box=cards.get(attempt.request_id);if(!box){box=node('section',undefined,'prop-sim-assessment panel');box.dataset.assessment=attempt.request_id;box.append(node('h4',attempt.report_options?.policy?.version==='prop-complementary-evidence-v2'?'OOS evidence review':studyNames[attempt.kind]||'Saved assessment'));const status=node('p');status.setAttribute('role','status');box.append(status);const confidence=node('div');confidence.className='prop-confidence-progress';box.append(confidence);const links=node('div',undefined,'mechanic-downloads prop-sim-study-links');if(attempt.analysis_id){link(links,'Job history / progress',`#jobs/prop_analysis/${attempt.analysis_id}`);link(links,'Assessment report JSON ↓',`/api/prop-analyses/${attempt.analysis_id}/downloads/report.json`);link(links,'Assessment evidence ZIP ↓',`/api/prop-analyses/${attempt.analysis_id}/downloads/analysis.zip`);}box.append(links);cards.set(attempt.request_id,box);}box.querySelector('[role=status]').textContent=`${attempt.status.toUpperCase()} · ${attempt.analysis?.progress||attempt.error||'Preparing inputs'}`;window.renderPropProgress(box.querySelector('.prop-confidence-progress'),attempt.analysis?.progress_details,attempt.status);if(['queued','running'].includes(attempt.status)&&!box.querySelector('[data-stop-study]')){const stop=node('button','Stop assessment','button secondary');stop.type='button';stop.dataset.stopStudy='true';stop.onclick=async()=>{stop.disabled=true;try{await read(`/api/prop-analyses/${attempt.analysis_id}/cancel`,'POST');}catch(e){message.textContent=e.message;}await refreshValidation();};box.append(stop);}if(!['queued','running'].includes(attempt.status))box.querySelector('[data-stop-study]')?.remove();return box;}
        async function reveal(id){const attempt=lastAttempts.find(a=>a.request_id===id),box=cards.get(id);if(!attempt||!box)return;for(let p=box.parentElement;p&&p!==root;p=p.parentElement)if(p.tagName==='DETAILS')p.open=true;try{await loadCard(attempt,box);box.scrollIntoView({behavior:'smooth',block:'start'});}catch(e){message.textContent=e.message;}}
        let lastAttempts=[];
        async function refreshValidation(){
          const data=await read(url);if(!alive())return false;frozen=data.frozen;lastAttempts=data.assessments;currentByKind=Object.fromEntries(Object.entries(data.current_assessments||{}).map(([kind,id])=>[kind,data.assessments.find(a=>a.request_id===id)]));currentMain=currentByKind.forward_review||currentByKind.qualification||currentByKind.oos||null;
          const currentQualification=currentByKind.forward_review||currentByKind.qualification;
          displayAttempt=currentQualification||[...data.assessments].reverse().find(a=>['qualification','forward_review'].includes(a.kind)&&a.status==='complete')||null;
          displayCurrent=!!currentQualification&&data.numerical_implementation_compatible!==false;
          policy=data.assessment_policy||null;reviewCompatible=data.review_implementation_compatible!==false;
          hasQualification=currentByKind.qualification?.status==='complete';forwardBox.hidden=!hasQualification||!phaseConclusions[phase]?.current||!phaseConclusions[phase]?.forwardEligible;
          hasOOS=data.assessments.some(a=>a.kind==='oos'&&a.status==='complete'&&a.report_options?.policy?.policy_sha256===policy?.policy_sha256);
          policyStatus.textContent=policy?`Policy version ${policy.revision||1} · ${policy.declaration_timing==='retrospective'?'Retrospectively declared after prior Prop Sim OOS access':'Declared before the first Prop Sim OOS result'} · saved limits. ${reviewCompatible?'':'Review implementation changed; save a new policy version. '}Account starts: ${policy.start_plan.starts.join(', ')||'insufficient coverage for full windows'} · ${policy.start_plan.horizon_calendar_days} calendar days each. Dates use coverage only, not performance. Overlapping starts are dependent scenarios.${hasOOS?'':' Run OOS assessment to apply this version before account-start sensitivity.'}`:'Optional business constraints. The default assessment uses complementary evidence checks without requiring dollar limits.';
          if(!editingPolicy){for(const [name,input] of Object.entries(policyFields)){if(policy)input.value=String(policy.limits[name]);input.disabled=!!policy;}reasonLabel.hidden=true;reason.disabled=true;savePolicy.hidden=!!policy;savePolicy.textContent='Save assessment limits';revisePolicy.hidden=!policy;cancelPolicy.hidden=true;}
          const versions=data.assessment_policy_history||[];policyHistory.hidden=!versions.length;policyHistoryTitle.textContent=`Policy history · ${versions.length} version${versions.length===1?'':'s'}`;policyHistoryRows.replaceChildren();for(const version of versions){const item=node('div');item.append(node('p',`Version ${version.revision||1}${version.policy_sha256===policy?.policy_sha256?' · current':' · superseded'} · ${new Date(version.declared_at_utc).toLocaleString()} · ${version.declaration_timing==='retrospective'?'retrospective':'before first Prop Sim OOS result'}`));if(version.revision_reason)item.append(node('p',version.revision_reason));detail(item,'Saved limits and provenance',version);policyHistoryRows.append(item);}
          if(selection.isPanel&&!selection.frozen&&frozen)selection.isPanel.open=false;
          for(const [i,step] of [...steps.children].entries()){const complete=i<2?!!frozen:i===2?currentMain?.status==='complete':currentByKind.forward_review?.status==='complete';step.classList.toggle('complete',!!complete);step.setAttribute('aria-current',!complete&&(i===0&&!frozen||i===2&&frozen&&!currentMain||i===3&&currentMain?.status==='complete')?'step':'false');}
          selection.ready=true;selection.compatible=data.numerical_implementation_compatible;selection.frozen=frozen;
          if(frozen){selected.clear();frozen.candidate_ids.forEach(id=>selected.add(id));}
          heading.textContent=automatic?'Selected sizes and OOS outcome':frozen?'OOS validation':'Freeze IS choices';
          intro.textContent=automatic?'Sizes were selected using IS data. OOS checks those same choices; it does not pick replacements.':frozen?'Only the frozen sizes below enter OOS assessment. IS choices remain unchanged.':'Select up to four sizes in the IS results table above, then freeze them before OOS assessment.';
          frozenNotice.textContent=!selection.compatible?'Historical numerical version: saved results remain readable. Start a new simulation to use the current freeze and validation tools.':frozen?`Choices frozen ${new Date(frozen.created_at_utc).toLocaleString()}. OOS was already used in strategy qualification; this is not an untouched holdout.`:selection.unresolved?'Unresolved sizes cannot be selected. You can freeze resolved, eligible sizes; comparisons cover resolved candidates only.':'Freezing permanently locks these choices for this run.';
          freeze.hidden=noteLabel.hidden=automatic||!!frozen;primaryActions.hidden=additional.hidden=!frozen;
          if(automatic){const state=saved.automation.phases[phase];autoStatus.replaceChildren(node('p',`Workflow: ${state.stage.replaceAll('_',' ')}${state.error?' · '+state.error:''}`));if(state.selection){const list=node('ul');for(const c of state.selection.candidates)list.append(node('li',`${c.sizing_label||c.micros+' MNQ'} · ${c.roles.join(' / ')}`));autoStatus.append(list);if(!state.selection.candidates.length)autoStatus.append(node('p','No resolved eligible IS size was available. OOS was not run.'));}}
          updateSelection();
          if(frozen&&!root.querySelector('.prop-sim-freeze-link')){const links=node('div',undefined,'mechanic-downloads prop-sim-freeze-link');link(links,'Frozen choices JSON ↓',`/api/research-campaigns/${data.campaign_id}/exports/frozen_package.json`);additional.append(links);}
          active=data.assessments.some(a=>['launching','queued','running'].includes(a.status));updateSelection();
          const diagnosticAttempts=data.assessments.filter(a=>['is_robustness','precision'].includes(a.kind)),diagnosticActive=diagnosticAttempts.filter(a=>['launching','queued','running'].includes(a.status)).length;
          diagnosticsTitle.textContent='Additional diagnostics'+(diagnosticActive?` · ${diagnosticActive} running`:diagnosticAttempts.length?` · ${diagnosticAttempts.length} saved`:'');
          history.hidden=!currentMain;past.hidden=!data.assessments.some(a=>a!==currentMain&&['qualification','forward_review','oos'].includes(a.kind));let oldCount=0;
          for(const attempt of data.assessments){const box=card(attempt);if(attempt===currentMain){archives.get(attempt.request_id)?.remove();if(box.parentElement!==history)history.replaceChildren(box);await loadCard(attempt,box);continue;}const old=['qualification','forward_review','oos'].includes(attempt.kind),container=old?pastRows:diagnosticHistory;if(old)oldCount++;let archived=archives.get(attempt.request_id);if(!archived){archived=node('details',undefined,'prop-sim-history-entry');const title=node('summary');archived.append(title);archived.ontoggle=()=>{if(archived.open)loadCard(lastAttempts.find(a=>a.request_id===attempt.request_id),box).catch(e=>{message.textContent=e.message;});};archives.set(attempt.request_id,archived);}archived.querySelector('summary').textContent=`${studyNames[attempt.kind]||'Assessment'} · ${attempt.status.replaceAll('_',' ')} · ${new Date(attempt.created_at_utc).toLocaleString()}`;if(box.parentElement!==archived)archived.append(box);if(archived.parentElement!==container)container.prepend(archived);if(archived.open)await loadCard(attempt,box);}
          // If versions changed, read just the latest saved qualification summary
          // for its original conclusion. Other historical reports stay lazy.
          if(displayAttempt?.status==='complete')await loadCard(displayAttempt,cards.get(displayAttempt.request_id));
          showConclusion();
          pastTitle.textContent=`Assessment history · ${oldCount} previous${data.assessments.some(a=>a!==currentMain&&['qualification','forward_review','oos'].includes(a.kind)&&['queued','running'].includes(a.status))?' · jobs running':''}`;
          if(!active&&message.textContent.startsWith('Assessment queued.'))message.textContent='Saved assessments are ready below.';
          return active;
        }
        additional.ontoggle=()=>{if(additional.open)refreshValidation().catch(e=>{message.textContent=e.message;});};
        return {refresh:async()=>{try{return await refreshValidation();}catch(e){message.textContent='Validation: '+e.message;return false;}}};
      }
      function table(parent,phase,report){
        const resultsParent=parent,isPanel=node('details',undefined,'prop-sim-is-panel');isPanel.open=!saved.automation;isPanel.append(node('summary','Explore all IS sizing results'));parent.append(isPanel);parent=isPanel;
        const c=report.calculations,rows=[...c.candidates].sort((a,b)=>comparePolicy(a.manifest.configuration,b.manifest.configuration)),isEval=phase==='evaluation';
        const eligible=new Set(rows.filter(r=>r.status==='estimated'&&((isEval?c.frontier:c.ranking)||[]).includes(r.candidate_id)).map(r=>r.candidate_id)),selection={selected:new Set(),eligible,ready:false,compatible:false,frozen:null,unresolved:!!c.unresolved_candidates?.length,onChange:()=>{},isPanel};
        function exclusionReason(row){
          if(eligible.has(row.candidate_id))return selection.frozen?.candidate_ids.includes(row.candidate_id)?'Frozen choice':'Selectable';
          if(row.status!=='estimated')return row.status==='unresolved'||row.status==='censored'?'Unresolved':row.status;
          if(isEval)return row.feasible===false?'Constraint failed':'Outside Pareto frontier';
          return row.constraint_violations?.length?'Constraint failed: '+row.constraint_violations.map(s=>s.replaceAll('_',' ')).join(', '):'Not feasible';
        }
        selection.syncRows=()=>{for(const input of tb.querySelectorAll('[data-freeze-candidate]')){const id=input.value;input.checked=selection.selected.has(id);input.disabled=!selection.ready||!selection.compatible||!!selection.frozen||selection.selected.size>=4&&!input.checked;input.closest('tr').classList.toggle('prop-sim-selected',input.checked);}for(const row of tb.children){const item=rows.find(r=>policyKey(r.manifest.configuration)===row.dataset.size);if(item){row.querySelector('[data-selection-status]').textContent=exclusionReason(item);if(saved.automation){const chosen=selection.frozen?.candidate_ids.includes(item.candidate_id);row.querySelector('.prop-sim-select-cell').textContent=chosen?'Selected':'—';row.classList.toggle('prop-sim-selected',!!chosen);}}}};
        const summary=node('p');summary.id='prop-sim-'+phase+'-summary';summary.textContent=isEval?`${c.frontier.length} Pareto configurations among resolved candidates only · ${rows.filter(r=>r.status!=='estimated').length} unresolved/censored. Unresolved sizes are excluded from comparisons and cannot be selected.`:c.winner?`Best estimated cash policy: ${policyLabel(rows.find(r=>r.candidate_id===c.winner).manifest.configuration)} · ${c.near_ties.length} tied/near-tied alternatives. This is a point estimate.`:'No Funded winner. Inspect unresolved results or constraints below.';parent.append(summary);
        tradeBehavior(parent,rows,'IS');
        if(rows.some(r=>r.simulation_model?.model==='saved-trade-stop-budget-v1'))parent.append(node('p','Historical stop-budget model · MAE was not used. Requested risk had to fit both limits. Ideal stop fills excluded gap overshoot.','field-help'));
        if(isEval&&c.precision_interpretation){parent.append(node('p',c.precision_interpretation,'field-help'));if(c.paired_comparisons?.length)detail(parent,'Paired funding-time and cost comparisons',c.paired_comparisons);}
        if(isEval&&saved.configuration.profile_id==='lucidflex-50k')parent.append(node('p','Calendar-aware acquisition: cost and time average every simulated retry chain. A 3,650-calendar-day computation guard leaves open paths unresolved; it is not a provider deadline.','field-help'));
        if(isEval){const chart=node('details',undefined,'prop-sim-chart-details');chart.append(node('summary','Explore the cost / time trade-off'));parent.append(chart);const dispose=evaluationChart(chart,rows,parent);if(dispose)chartDisposers.push(dispose);}
        parent.append(node('p',saved.automation?'IS results · eligible sizes are selected and frozen automatically.':'IS results · select up to four eligible sizes here. Excluded sizes remain visible for comparison.','field-help'));
        const wrap=node('div',undefined,'optimization-scroll'),t=node('table',undefined,'library-table prop-result-table prop-sim-is-results');t.id='prop-sim-'+phase+'-table';const head=node('tr'),tb=node('tbody');head.append(node('th',saved.automation?'IS choice':'Select'));
        let specs=isEval?[['MNQ size',r=>policyLabel(r.manifest.configuration)],['Status',r=>r.status],['Pareto frontier',r=>r.pareto_member?'Yes':'No'],['First-attempt pass %',r=>r.metrics.pass_probability,'pct'],['Acquisition cost · USD',r=>r.metrics.cost_per_funded,'number'],['Calendar days to Funded',r=>r.metrics.expected_calendar_days_to_funded,'number'],['P90 calendar days',r=>r.metrics.p90_calendar_days_to_funded,'number'],['Expected attempts',r=>r.metrics.expected_attempts_per_funded,'number']]:[['MNQ size',r=>policyLabel(r.manifest.configuration)],['Status',r=>r.feasible?'Eligible':r.status==='unresolved'?'Unresolved':'Constraint failed'],['Rank',r=>r.rank],['Mean trader receipts · USD',r=>r.metrics.expected_funded_cash_payouts_within_horizon,'number'],['Median receipts',r=>r.metrics.median_payouts,'number'],['P10 receipts',r=>r.metrics.p10_payouts,'number'],['Breach %',r=>r.metrics.account_breach_probability,'pct'],['Inactivity %',r=>r.metrics.probability_inactivity,'pct'],['First payout %',r=>r.metrics.probability_first_payout,'pct'],['Pending cash',r=>r.metrics.expected_pending_cash,'number'],['Account deductions',r=>r.metrics.expected_gross_account_deductions,'number']];
        specs[1][1]=exclusionReason;
        if(rows.some(r=>r.quantity_summary)){specs[0][0]='Risk policy';specs.push(['Mean admitted MNQ',r=>r.quantity_summary?.mean_quantity,'number'],['Median admitted MNQ',r=>r.quantity_summary?.median_quantity,'number'],['P95 admitted MNQ',r=>r.quantity_summary?.p95_quantity,'number'],['Quantity range',r=>r.quantity_summary?`${r.quantity_summary.minimum_quantity??'—'}–${r.quantity_summary.maximum_quantity??'—'}`:'—'],['Skipped entries %',r=>r.quantity_summary?.skipped_rate,'pct'],['Sizing opportunities',r=>r.quantity_summary?.opportunities],['Account-halted opportunities',r=>r.quantity_summary?.account_halted_opportunities],['Cap-binding %',r=>r.quantity_summary?.cap_binding_rate,'pct'],['Mean requested risk · USD',r=>r.quantity_summary?.mean_requested_risk_budget,'number'],['Mean admitted planned risk per opportunity · USD',r=>r.quantity_summary?.mean_admitted_planned_risk,'number']);}
        if(isEval)specs.push(['Median calendar days',r=>r.metrics.median_calendar_days_to_funded,'number'],['Mean time MC SE · days',r=>r.uncertainty?.calendar_mean_se,'number'],['Funded within 60 days',r=>r.metrics.probability_funded_by_day_60,'pct'],['Funding-time near ties',r=>r.funding_time_near_ties?.map(id=>policyLabel(rows.find(x=>x.candidate_id===id)?.manifest.configuration||{})).join(', ')||'—']);
        if(isEval&&rows.some(r=>r.metrics.mean_final_attempt_days_after_target!=null)){
          parent.append(node('p','Time breakdown: earlier attempts + final account to first target + further trading after target + funded readiness = mean calendar days. Consistency requires additional net profit; elapsed time alone does not improve the ratio. Failed-after-target accounts increase retries.','field-help'));
          for(const [text,key] of [['Earlier attempts · days','days_before_final_attempt'],['Final: reach target · days','final_attempt_days_before_target'],['Final: after target · days','final_attempt_days_after_target'],['Readiness · days','pass_to_ready_days'],['Failures after target','failed_attempts_after_target'],['Consistency-blocked sessions','consistency_blocked_sessions']])specs.push([text,r=>r.metrics['mean_'+key],'number']);
        }
        const allSpecs=[...specs];
        if(saved.automation){
          const keep=new Set(isEval?['MNQ size','Risk policy','Status','Acquisition cost · USD','Calendar days to Funded','Funded within 60 days']:['MNQ size','Risk policy','Status','Mean trader receipts · USD','Breach %','First payout %']);
          for(let i=specs.length-1;i>=0;i--)if(!keep.has(specs[i][0]))specs.splice(i,1);
        }
        const compactSpecs=[...specs];let expandedMetrics=false;
        let sort=0,direction=1;
        function paint(){const selected=new Set([...tb.querySelectorAll('.prop-sim-chart-highlight')].map(r=>r.dataset.size));tb.replaceChildren();const get=specs[sort][1];const ordered=[...rows].sort((a,b)=>{if(sort===0)return comparePolicy(a.manifest.configuration,b.manifest.configuration)*direction;const av=get(a),bv=get(b);if(av==null||bv==null)return av==null?(bv==null?0:1):-1;return (typeof av==='number'||['number','pct'].includes(specs[sort][2])?Number(av)-Number(bv):String(av).localeCompare(String(bv)))*direction;});
          for(const row of ordered){const tr=node('tr');tr.dataset.size=policyKey(row.manifest.configuration);if(selected.has(tr.dataset.size))tr.classList.add('prop-sim-chart-highlight');const choice=node('td',undefined,'prop-sim-select-cell');
            if(saved.automation){choice.textContent=selection.frozen?.candidate_ids.includes(row.candidate_id)?'Selected':'—';choice.title='Selected automatically from IS results';}else if(eligible.has(row.candidate_id)){const input=node('input');input.type='checkbox';input.value=row.candidate_id;input.dataset.freezeCandidate=row.candidate_id;input.setAttribute('aria-label',`Select ${policyLabel(row.manifest.configuration)} for ${phase} validation`);input.onchange=()=>{if(input.checked){if(selection.selected.size>=4){input.checked=false;return;}selection.selected.add(input.value);}else selection.selected.delete(input.value);selection.onChange();};choice.append(input);}else{choice.textContent='—';choice.title=exclusionReason(row);}tr.append(choice);
            for(const [index,[,get,type]] of specs.entries()){const v=get(row),cell=node('td',type==='pct'?pct(v):type==='number'?fmt(v):v==null?'—':String(v));if(index===1)cell.dataset.selectionStatus='true';tr.append(cell);}const td=node('td');detail(td,'Details',{metrics:row.metrics,uncertainty:row.uncertainty,censoring:row.censoring,reason:row.reason,constraint_violations:row.constraint_violations,assumptions:row.assumptions,sizing_policy:row.manifest.configuration.sizing,quantity_summary:row.quantity_summary,simulation_model:row.simulation_model,observed_bar_diagnostics:row.native_forecast?.observed_bar_diagnostics,sample_path:row.paths?.[0]});tr.append(td);tb.append(tr);}
          [...head.children].forEach((th,i)=>{const index=i-1;th.setAttribute('aria-sort',index===sort?(direction===1?'ascending':'descending'):'none');const button=th.querySelector('button');if(button)button.textContent=specs[index][0]+' '+(index===sort?(direction===1?'↑':'↓'):'↕');});selection.syncRows();
        }
        function headers(){head.replaceChildren(node('th',saved.automation?'IS choice':'Select'));specs.forEach(([text],i)=>{const th=node('th'),button=node('button',text+' ↕');button.type='button';button.onclick=()=>{direction=sort===i?-direction:1;sort=i;paint();};th.append(button);head.append(th);});head.append(node('th','Details'));}
        headers();const th=node('thead');th.append(head);t.append(th,tb);paint();wrap.append(t);parent.append(wrap);
        if(saved.automation){const metricsToggle=node('button','Show all metrics','button secondary');metricsToggle.type='button';metricsToggle.onclick=()=>{expandedMetrics=!expandedMetrics;specs=expandedMetrics?[...allSpecs]:[...compactSpecs];sort=0;direction=1;metricsToggle.textContent=expandedMetrics?'Show key metrics':'Show all metrics';headers();paint();};parent.insertBefore(metricsToggle,wrap);}
        if(rows.some(r=>r.native_forecast?.execution_preparation?.market_features_reused))parent.append(node('p','Twin market calculations cached · account eligibility, sizing, fills and limits remain independent.','field-help'));
        for(const row of rows){const d=row.observed_bar_diagnostics||row.native_forecast?.observed_bar_diagnostics;if(d){const gap=node('details');gap.append(node('summary',policyLabel(row.manifest.configuration)+' · source-gap diagnostics'));window.nativeReplay.renderCoverage(gap,d);parent.append(gap);}}
        const links=node('div',undefined,'mechanic-downloads prop-sim-exports');for(const [kind,text] of [['results.csv','Results CSV ↓'],['results.json','Calculations JSON ↓'],['report.json','Saved report JSON ↓'],['analysis.zip','Evidence ZIP ↓'],['source_checks.json','Source checks ↓']])link(links,text,`/api/research-campaigns/${saved.campaign_ids[phase]}/exports/${kind}`);parent.append(links);
        const insight=node('section',undefined,'prop-sim-insight');insight.id='prop-sim-'+phase+'-insight';
        resultsParent.insertBefore(insight,isPanel);
        const selectedRows=rows.filter(r=>(isEval?c.frontier:c.ranking).includes(r.candidate_id)&&r.status==='estimated');
        if(selectedRows.length){
          const best=[...selectedRows].sort((a,b)=>isEval?a.metrics.cost_per_funded-b.metrics.cost_per_funded:b.metrics.expected_funded_cash_payouts_within_horizon-a.metrics.expected_funded_cash_payouts_within_horizon)[0];
          insight.append(node('span','IS finding','pill neutral'),node('h3',isEval?'Lowest acquisition cost: $'+fmt(best.metrics.cost_per_funded):'Highest expected receipts: $'+fmt(best.metrics.expected_funded_cash_payouts_within_horizon)),node('p',isEval?`${policyLabel(best.manifest.configuration)} · ${fmt(best.metrics.expected_calendar_days_to_funded)} expected calendar days to funding, including retries.`:`${policyLabel(best.manifest.configuration)} · ${saved.configuration.funded_horizon_calendar_days} calendar days · ${pct(best.metrics.probability_first_payout)} chance of receiving a payout · ${pct(best.metrics.account_breach_probability)} breach risk.`));
          insight.append(node('small',isEval?'Evaluation cost and time are independent of Funded payout results.':'Fresh Funded account only. Evaluation and replacement fees are not deducted here.'));
          if(best.quantity_summary){const q=best.quantity_summary;insight.append(node('p',`Admitted quantity: ${fmt(q.mean_quantity)} MNQ mean · ${q.minimum_quantity??'—'}–${q.maximum_quantity??'—'} range · ${pct(q.skipped_rate)} of ${Number(q.opportunities).toLocaleString()} eligible opportunities skipped · ${pct(q.cap_binding_rate)} cap-bound. ${best.simulation_model?'Saved opportunities; no alternative setups are generated.':'Actual fills and cancellations remain in the evidence.'}`,'field-help'));}
        }else insight.append(node('h3','No eligible IS sizing result'),node('p','Review unresolved estimates or constraints below.'));
        const flagged=rows.filter(r=>{const q=r.quantity_summary;return r.simulation_model?.model==='saved-trade-account-policies-v2'&&q&&(q.skipped_entries||q.account_limit_exit_count||q.risk_budget_override_count);});
        if(flagged.length){
          const warning=node('p',`${flagged.length} IS sizing ${flagged.length===1?'policy needs':'policies need'} trade-handling review: skipped trades, account-limit exits or risk-budget overrides change campaign participation or exits.`);warning.dataset.tradeHandlingWarning=phase;insight.append(warning);
          const review=node('button','Review trade-handling impact','button secondary');review.type='button';review.onclick=()=>{isPanel.open=true;const target=parent.querySelector('[data-trade-behavior]');if(target){target.open=true;target.scrollIntoView({behavior:'smooth',block:'start'});}};insight.append(review);
        }
        validationControllers[phase]=validationControls(resultsParent,phase,report,selection);
      }
      async function refresh(){clearTimeout(timer);try{
        const current=await read('/api/prop-sim/'+selectedId);if(!alive())return;saved=current;
        if(!results.querySelector('.prop-sim-run-heading')){const title=node('section',undefined,'panel prop-sim-run-heading'),p=profiles[saved.configuration.profile_id||'apex-50k-eod'];if(saved.configuration.evaluation_trade_handling||saved.configuration.funded_trade_handling)detail(title,'Frozen trade handling', {evaluation:saved.configuration.evaluation_trade_handling,funded:saved.configuration.funded_trade_handling,assumptions:'Causal stop-distance sizing; captured excursions detect account-limit exits only. Exact limit fills, frozen opportunities, no gap overshoot.'});else if(saved.configuration.search_kind==='percentage_risk')title.append(node('p','Historical stop-budget model · MAE was not used. Requested risk had to fit both limits; ideal fills excluded gap overshoot.','field-help'));title.append(node('span',p.name,'pill neutral'),node('h2',saved.qualification?.strategy_id?.replaceAll('_',' ')||'Saved simulation'),node('p',`Evaluation and Funded are independent searches · ${saved.configuration.simulations.toLocaleString()} paths per size · ${saved.configuration.funded_horizon_calendar_days}-day Funded horizon${saved.automation?' · Automatic IS and OOS':''}`,'field-help'));if(saved.qualification?.plan){const q=saved.qualification;title.append(node('p',`${q.dataset.name} · Broad ${q.broad_trial} / Narrow ${q.narrow_trial} · IS ${q.plan.is_start} → ${q.plan.is_end}`,'field-help'));detail(title,'Frozen strategy parameters',q.parameters);}const actions=node('div',undefined,'mechanic-downloads');link(actions,'New simulation','#prop-sim');const edit=node('button','Adjust settings','button secondary');edit.type='button';edit.onclick=()=>{setup.open=true;setup.scrollIntoView({behavior:'smooth',block:'start'});};actions.append(edit);for(const phase of ['evaluation','funded']){const jump=node('button',phase==='evaluation'?'View Evaluation':'View Funded','button secondary');jump.type='button';jump.onclick=()=>document.querySelector('#prop-sim-'+phase+'-results')?.scrollIntoView({behavior:'smooth',block:'start'});actions.append(jump);}actions.append(deleteButton(selectedId));title.append(actions);results.append(title);host.insertBefore(results,setup);}
        paintConclusions();
        let validationActive=false;
        for(const phase of ['evaluation','funded']){const job=saved.phases[phase];let panel=phasePanels[phase];if(!panel){panel=node('section',undefined,'panel broad-panel');panel.id='prop-sim-'+phase+'-results';panel.append(node('h2',phase==='evaluation'?'Evaluation · acquisition cost and time':'Funded · cash-receipt sizing'));const state=node('p');state.id='prop-sim-'+phase+'-progress';state.setAttribute('role','status');panel.append(state);const live=node('div');live.id='prop-sim-'+phase+'-live-progress';panel.append(live);results.append(panel);phasePanels[phase]=panel;}
          const state=panel.querySelector('[role=status]');state.textContent=`${job.status.toUpperCase()} · ${job.progress||'Ready'}${job.error?' · '+job.error:''}`;
          state.hidden=job.status==='running'&&!!job.progress_details;
          window.renderPropProgress(panel.querySelector('#prop-sim-'+phase+'-live-progress'),job.progress_details,job.status);
          if(job.analysis_id){let links=panel.querySelector('.prop-sim-job-link');if(!links){links=node('div',undefined,'mechanic-downloads prop-sim-job-link');panel.append(links);}links.replaceChildren();link(links,'Job history / progress',`#jobs/prop_analysis/${job.analysis_id}`);}
          if(job.status==='complete'&&loaded[phase]!==job.analysis_id){const report=await read(`/api/prop-sim/${selectedId}/results/${phase}`);if(!alive())return;table(panel,phase,report);loaded[phase]=job.analysis_id;}
          if(validationControllers[phase])validationActive=await validationControllers[phase].refresh()||validationActive;
        }
        let controls=results.querySelector('#prop-sim-job-controls');if(!controls){controls=node('div',undefined,'mechanic-downloads');controls.id='prop-sim-job-controls';results.querySelector('.prop-sim-run-heading').append(controls);}controls.replaceChildren();const pipelineActive=saved.automation&&!saved.automation.stop_requested&&Object.values(saved.automation.phases).some(p=>!['complete','no_eligible_candidates','error','cancelled'].includes(p.stage));const active=!saved.automation?.stop_requested&&(pipelineActive||Object.values(saved.phases).some(p=>['queued','running'].includes(p.status)));results.querySelectorAll('[data-delete-simulation]').forEach(button=>{button.disabled=active||deleting;button.title=active?'Stop running jobs before deleting this simulation.':'';});
        if(active){const stop=node('button','Stop running analyses','button secondary');stop.type='button';stop.id='prop-sim-stop';stop.onclick=async()=>{stop.disabled=true;try{await read('/api/prop-sim/'+selectedId+'/cancel','POST');if(alive())await refresh();}catch(error){if(alive())notice.textContent=error.message;}};controls.append(stop);timer=setTimeout(refresh,2500);}
        else if(Object.values(saved.phases).some(p=>p.status!=='complete')||saved.automation&&Object.values(saved.automation.phases).some(p=>['error','cancelled'].includes(p.stage))){const retry=node('button','Retry incomplete phases','button secondary');retry.type='button';retry.onclick=async()=>{try{await read('/api/prop-sim','POST',saved.configuration);if(alive())await refresh();}catch(error){if(alive())notice.textContent=error.message;}};controls.append(retry);}
        if(validationActive&&!active)timer=setTimeout(refresh,2500);
      }catch(error){if(alive())notice.textContent=error.message;}}
      applyAccount(false);
      if(selectedId){await refresh();if(!alive())return;if(saved){sizingMode.value=saved.configuration.search_kind||'fixed_contracts';for(const phase of ['evaluation','funded']){const handling=saved.configuration[phase+'_trade_handling'];if(handling){tradeFields[phase].action.value=handling.account_limit_action;tradeFields[phase].minimum.checked=handling.minimum_one_contract;}const grid=saved.configuration[phase+'_percentage_grid'];if(grid)for(const [key,input] of Object.entries(riskFields[phase])){if(input.type==='checkbox')input.checked=grid[key];else input.value=String(grid[key]);}}toggleSizing();accountPicker.value=saved.configuration.profile_id||'apex-50k-eod';dll.checked=saved.configuration.daily_loss_limit??true;consistency.value=String(saved.configuration.evaluation_consistency_percent??40);const index=sources.items.findIndex(s=>JSON.stringify(s.selection)===JSON.stringify(saved.configuration.selections[0]));if(index>=0)picker.value=String(index);for(const [name] of names){const value=name.endsWith('_micros')?range(saved.configuration,name.split('_')[0])[name.includes('_minimum_')?'minimum':'maximum']:saved.configuration[name];fields[name].value=name==='closures'?value.join(','):String(value??'');}applyAccount(false);select();}}
      else if(sourceId){const index=sources.items.findIndex(s=>[s.source_backtest_id,s.oos_report_id].includes(sourceId));if(index>=0){picker.value=String(index);select();}else{notice.textContent='This backtest has no currently qualified configuration. Complete all campaign phases and Monte Carlo before selecting it.';update();}}
      else update();
    }catch(error){if(alive())host.replaceChildren(node('p',error.message));}
  }
  window.addEventListener('hashchange',render);render();
})();
