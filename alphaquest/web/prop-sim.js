"use strict";
(() => {
  const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
  const fmt=v=>v==null?'Unavailable':Number(v).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
  const pct=v=>v==null?'Unavailable':fmt(Number(v)*100)+'%';
  const read=async(url,method='GET',body)=>{const r=await fetch(url,{method,cache:'no-store',...(body?{headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})});const value=await r.json();if(!r.ok)throw Error(typeof value.detail==='string'?value.detail:JSON.stringify(value.detail));return value;};
  const link=(parent,text,href)=>{const a=node('a',text,'workflow-inline-link');a.href=href;parent.append(a);};
  const detail=(parent,title,value)=>{const d=node('details');d.append(node('summary',title),node('pre',JSON.stringify(value,null,2)));parent.append(d);return d;};
  const range=(settings,phase)=>({minimum:settings[phase+'_minimum_micros']??settings.minimum_micros,maximum:settings[phase+'_maximum_micros']??settings.maximum_micros});
  const chartDisposers=[];
  function evaluationChart(parent,rows){
    const plotted=rows.filter(r=>r.status==='estimated'&&['cost_per_funded','expected_calendar_days_to_funded'].every(k=>r.metrics[k]!=null&&Number.isFinite(Number(r.metrics[k]))));
    const section=node('section',undefined,'prop-sim-pareto');
    section.append(node('h3','Evaluation cost/time Pareto curve'));parent.append(section);
    if(!plotted.length){section.append(node('p','No resolved cost/time points are available. Unresolved and censored sizes remain in the table below.'));return;}
    const groups=new Map();
    for(const row of plotted){
      const x=Number(row.metrics.expected_calendar_days_to_funded),y=Number(row.metrics.cost_per_funded),key=`${x}|${y}`;
      if(!groups.has(key))groups.set(key,{x,y,rows:[]});groups.get(key).rows.push(row);
    }
    const points=[...groups.values()].sort((a,b)=>Math.min(...a.rows.map(r=>r.manifest.configuration.micros))-Math.min(...b.rows.map(r=>r.manifest.configuration.micros)));
    points.forEach(p=>{p.sizes=p.rows.map(r=>r.manifest.configuration.micros);p.frontier=p.rows.some(r=>r.pareto_member);});
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
    points.forEach((p,i)=>picker.add(new Option(`${p.sizes.join(', ')} MNQ · ${p.frontier?'Frontier':'Other size'}`,String(i))));label.append(picker);
    const readout=node('p','Hover, focus or click a point to see its exact results.','pareto-readout');readout.id='prop-sim-pareto-readout';readout.setAttribute('aria-live','polite');
    const metrics=node('dl',undefined,'pareto-metrics'),values={};
    for(const [key,title] of [['cost','Expected acquisition cost'],['days','Calendar days to Funded']]){const item=node('div');values[key]=node('dd','—');item.append(node('dt',title),values[key]);metrics.append(item);}
    inspector.append(label,metrics,readout);section.append(inspector);
    const caption=node('p',undefined,'field-help');caption.id='prop-sim-pareto-caption';section.append(caption);
    const download=node('a','Pareto chart SVG ↓','workflow-inline-link');download.download='evaluation-pareto.svg';section.append(download);
    const updateDownload=()=>{
      const copy=svg.cloneNode(true),[,,width,height]=svg.getAttribute('viewBox').split(' ').map(Number);
      copy.setAttribute('viewBox',`0 0 ${width} ${height+44}`);copy.setAttribute('height',String(height+44));
      const lines=[`${view==='frontier'?'Frontier detail':'All sizes'} · Green: Pareto frontier. Grey: other resolved sizes.`,selected?`${selected.sizes.length>6?selected.sizes.length+' tied sizes':selected.sizes.join(', ')+' MNQ'} · $${fmt(selected.y)} · ${fmt(selected.x)} calendar days`:'Inspection chart; no Evaluation winner is selected.'];
      lines.forEach((text,i)=>{const label=document.createElementNS(ns,'text');for(const [key,value] of Object.entries({x:12,y:height+16+i*16,fill:'#526b62','font-size':11}))label.setAttribute(key,String(value));label.textContent=text;copy.append(label);});
      download.href='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(new XMLSerializer().serializeToString(copy));
    };
    const inside=p=>p.x>=bounds.x[0]&&p.x<=bounds.x[1]&&p.y>=bounds.y[0]&&p.y<=bounds.y[1];
    function updateSelection(){
      picker.value=selected?String(points.indexOf(selected)):'';
      readout.textContent=selected?`${selected.sizes.join(', ')} MNQ · ${selected.frontier?'Pareto frontier':'Other resolved size'}${selected.sizes.length>1?' · Exact performance tie':''}`:'Hover, focus or click a point to see its exact results.';
      values.cost.textContent=selected?'$'+fmt(selected.y):'—';values.days.textContent=selected?fmt(selected.x)+' days':'—';
      svg.querySelectorAll('circle[data-point]').forEach(circle=>{const p=points[Number(circle.dataset.point)],active=p===selected;circle.setAttribute('r',active?8:p.frontier?6:4);circle.setAttribute('stroke',active?'#20313b':'#fff');circle.setAttribute('stroke-width',active?2.5:1.25);circle.setAttribute('aria-pressed',String(active));});
      parent.querySelectorAll('tbody tr').forEach(row=>row.classList.toggle('prop-sim-chart-highlight',!!selected&&selected.sizes.includes(Number(row.dataset.size))));
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
        const text=`${p.sizes.join(', ')} MNQ · ${fmt(p.x)} calendar days · $${fmt(p.y)} acquisition cost · ${p.frontier?'Pareto frontier':'other resolved size'}`;
        const circle=draw('circle',{cx:x(p.x),cy:y(p.y),r:p.frontier?6:4,fill:p.frontier?'#008675':'#a7b3bc',stroke:'#fff','stroke-width':1.25,tabindex:0,role:'button','aria-label':text,'data-point':points.indexOf(p),'data-sizes':p.sizes.join(','),'data-pareto':p.frontier});
        circle.onmouseenter=circle.onfocus=circle.onclick=()=>inspect(p);circle.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();inspect(p);}};
      }
      focus.setAttribute('aria-pressed',String(view==='frontier'));all.setAttribute('aria-pressed',String(view==='all'));
      caption.textContent=`${svg.dataset.visibleCount} of ${plotted.length} resolved sizes in view · ${rows.length-plotted.length} unresolved/censored sizes remain in the table. Axes fit the selected view. ${frontier.length===0?'No frontier was supplied for these resolved estimates.':frontier.length===1?'One distinct frontier point; tied sizes share a marker.':'The line connects tested frontier points.'} Point estimates; no untested intermediate sizes inferred.`;
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
      const [sources,defaults,history]=await Promise.all([read('/api/prop-sim/candidates'),read('/api/prop-sim/defaults'),read('/api/prop-sim')]);if(!alive())return;
      const profiles=defaults.profiles;host.replaceChildren();
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
      const dllLabel=node('label',undefined,'prop-sim-dll'),dll=node('input');dll.type='checkbox';dll.id='prop-sim-daily-loss-limit';dll.checked=true;dllLabel.append(dll,node('span','Daily loss limit enabled'));accountBox.append(dllLabel);
      const consistencyLabel=node('label','Evaluation consistency'),consistency=node('select');consistency.id='prop-sim-consistency';consistency.add(new Option('40% · standard','40'));consistency.add(new Option('50% · paid add-on','50'));consistencyLabel.append(consistency);accountBox.append(consistencyLabel);
      const ruleNote=node('p',undefined,'field-help');accountBox.append(ruleNote);sourceGrid.append(sourceBox,accountBox);
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
        if(type==='select')for(const n of [1,5,10])input.add(new Option(String(n),String(n)));else input.type=type;
        if(type==='number'){input.step=name==='maximum_funded_breach_probability'?'.01':'1';input.min='0';}
        if(name.endsWith('_micros'))input.min='1';if(name==='simulations'){input.min='8';input.max='20000';}
        if(name==='funded_horizon_calendar_days'){input.min='1';input.max='365';}
        input.value=name==='start_date'?new Date().toLocaleDateString('en-CA',{timeZone:'America/Chicago'}):name==='closures'?'':String(defaults.defaults[name]??'');
        if(name==='maximum_funded_breach_probability'){input.max='1';input.placeholder='No cap';label.append(node('span','Blank = no extra eligibility cap. Measures breach within the Funded horizon, not years of IS history.','field-help'));}
        label.append(input);grids[group].append(label);
      }
      const rules=node('div');advanced.append(rules);
      advanced.append(node('p',defaults.disclosure,'field-help'));
      const preview=node('p',undefined,'prop-sim-preflight');preview.id='prop-sim-preflight';preview.setAttribute('role','status');form.append(preview);
      const buttons=node('div',undefined,'mechanic-downloads'),check=node('button','Check source and settings','button secondary'),run=node('button','Run Evaluation and Funded','button primary');check.type=run.type='button';check.id='prop-sim-check';run.id='prop-sim-run';run.disabled=true;buttons.append(check,run);form.append(buttons);
      const notice=node('p');notice.id='prop-sim-status';notice.setAttribute('role','status');form.append(notice);
      let checked=false,busy=false,resourceOK=true,requestId=crypto.randomUUID(),saved;
      let deleting=false;
      async function requestDelete(id){
        if(deleting)return;deleting=true;
        host.querySelectorAll('[data-delete-simulation]').forEach(button=>button.disabled=true);
        try{
          const plan=await read('/api/prop-sim/'+id+'/deletion');
          if(!alive())return;
          if(!plan.deleted&&!plan.deletable){notice.textContent='This simulation has queued or running jobs. Stop them or wait before deleting.';setup.open=true;return;}
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

      const update=()=>{check.disabled=busy||picker.value===''||!resourceOK;run.disabled=busy||!checked||!resourceOK;};
      function resourcePreview(){
        const p=profiles[accountPicker.value],paths=Number(fields.simulations.value),counts={};const errors=[];
        for(const phase of ['evaluation','funded']){
          counts[phase]=Math.max(0,Number(fields[phase+'_maximum_micros'].value)-Number(fields[phase+'_minimum_micros'].value)+1);
          if(counts[phase]*paths*p.report_limits[phase+'_bytes_per_path']>p.report_limits.capture_bytes)
            errors.push(`${phase==='evaluation'?'Evaluation':'Funded'} report is too large. For ${counts[phase]} sizes, use at most ${Math.floor(p.report_limits.capture_bytes/(counts[phase]*p.report_limits[phase+'_bytes_per_path']))} paths, or narrow the range.`);
        }
        resourceOK=!errors.length;preview.classList.toggle('prop-sim-preflight-error',!resourceOK);
        preview.textContent=errors.length?errors.join(' '):`${counts.evaluation} Evaluation sizes + ${counts.funded} Funded sizes · ${paths.toLocaleString()} paths per size, per phase. Both searches use IS history only.`;update();
      }
      function applyAccount(reset){
        const id=accountPicker.value,p=profiles[id];
        consistencyLabel.hidden=id!=='lucidflex-50k';if(reset||id!=='lucidflex-50k')consistency.value='40';
        for(const phase of ['evaluation','funded'])for(const bound of ['minimum','maximum']){const input=fields[phase+'_'+bound+'_micros'];input.max=String(p.size_limits[phase]);if(Number(input.value)>p.size_limits[phase]){input.value=String(p.size_limits[phase]);notice.textContent='Size range adjusted to the selected account limit.';}}
        if(reset)for(const name of ['evaluation_price','activation_fee','commission_per_mnq_side'])fields[name].value=p.defaults[name];
        if(id==='apex-50k-eod')dll.checked=true;dll.disabled=id==='apex-50k-eod';fields.activation_fee.readOnly=id==='lucidflex-50k';
        accountInfo.textContent=`$3,000 target · $2,000 maximum drawdown · Evaluation up to ${p.size_limits.evaluation} MNQ / Funded up to ${p.size_limits.funded} MNQ.`;
        ruleNote.textContent=id==='lucidflex-50k'?`${consistency.value}% Evaluation consistency${consistency.value==='50'?' · add-on price must be included in your purchase fee':''}. No activation fee. Funded has a 90% trader share and no consistency rule. Set your actual purchase price for the chosen options.`:'Funded sizes follow account scaling tiers. Scenario purchase and activation fees are editable.';
        rules.replaceChildren();detail(rules,'Account rules and model assumptions',{selection:{profile_id:id,daily_loss_limit:dll.checked},evaluation:{...p.evaluation_rules,consistency:id==='lucidflex-50k'?Number(consistency.value)/100:null,daily_loss_limit:dll.checked?p.evaluation_rules.daily_loss_limit:null},funded:id==='lucidflex-50k'?{...p.funded_rules,daily_loss:dll.checked?1200:null}:p.funded_rules,notes:p.notes,default_profile_review:p.rule_provenance});
        checked=false;resourcePreview();
      }
      accountPicker.onchange=()=>applyAccount(true);dll.onchange=()=>applyAccount(false);
      consistency.onchange=()=>{fields.evaluation_price.value='';fields.evaluation_price.required=true;fields.evaluation_price.placeholder='Enter your checkout price including add-on';applyAccount(false);notice.textContent='Enter the actual purchase fee for this account variant, then check again.';};
      function select(){
        checked=false;sourceInfo.replaceChildren();const item=sources.items[Number(picker.value)];
        if(picker.value!==''&&item){sourceInfo.append(node('p',`IS sizing window ${item.plan.is_start} → ${item.plan.is_end}.`,'field-help'));detail(sourceInfo,'Frozen parameters',item.parameters);const links=node('div',undefined,'mechanic-downloads');link(links,'Open IS source backtest',`#backtests/report/${item.source_backtest_id}`);link(links,'Open campaign and OOS evidence',`#campaigns/workflows/${item.selection.workflow_id.replaceAll('-','')}/oos?job=${item.selection.oos_job_id.replaceAll('-','')}`);sourceInfo.append(links);}update();
      }
      picker.onchange=select;form.oninput=()=>{checked=false;notice.textContent='Settings changed. Check source and settings before running.';resourcePreview();};form.onsubmit=e=>e.preventDefault();
      function body(){
        const source=sources.items[Number(picker.value)];if(picker.value===''||!source)throw Error('Choose one qualified configuration.');
        const value={request_id:requestId,profile_id:accountPicker.value,daily_loss_limit:dll.checked,evaluation_consistency_percent:Number(consistency.value),selections:[source.selection]};
        for(const [name,,type] of names)value[name]=name==='maximum_funded_breach_probability'&&fields[name].value.trim()===''?null:name==='closures'?fields[name].value.split(',').map(s=>s.trim()).filter(Boolean):type==='number'||name==='block_weekdays'?Number(fields[name].value):fields[name].value;return value;
      }
      check.onclick=async()=>{if(!form.reportValidity())return;busy=true;update();notice.textContent='Checking qualification, costs and source compatibility…';try{const data=await read('/api/prop-sim/check','POST',body());if(alive()){checked=true;notice.textContent=`Source compatible · ${data.phases.evaluation.candidate_search_count} Evaluation sizes and ${data.phases.funded.candidate_search_count} Funded sizes.`;}}catch(error){if(alive()){checked=false;notice.textContent=error.message;}}finally{busy=false;if(alive())update();}};
      run.onclick=async()=>{busy=true;update();notice.textContent='Starting independent phase jobs…';try{const data=await read('/api/prop-sim','POST',body());if(alive())location.hash='#prop-sim?analysis='+data.id;}catch(error){if(alive())notice.textContent=error.message;}finally{busy=false;if(alive())update();}};
      const results=node('div');results.id='prop-sim-results';host.append(results);
      if(history.items.length){const historyLabel=node('label','Saved simulations'),historySelect=node('select');historySelect.id='prop-sim-history';historySelect.add(new Option('Choose saved results',''));for(const old of history.items){const p=profiles[old.configuration.profile_id||'apex-50k-eod'],e=range(old.configuration,'evaluation'),f=range(old.configuration,'funded');historySelect.add(new Option(`${new Date(old.created_at_utc).toLocaleString()} · ${p.name} · Eval ${e.minimum}–${e.maximum} / Funded ${f.minimum}–${f.maximum} MNQ`,old.id));}historySelect.value=selectedId||'';historyLabel.append(historySelect,deleteButton(selectedId,'Delete selected simulation'));historyLabel.className='prop-sim-history';host.append(historyLabel);historySelect.onchange=()=>{location.hash=historySelect.value?'#prop-sim?analysis='+historySelect.value:'#prop-sim';};}
      const phasePanels={},loaded={},validationControllers={};
      function validationControls(parent,phase,report){
        const root=node('section',undefined,'prop-sim-validation');root.id='prop-sim-'+phase+'-validation';parent.append(root);
        root.append(node('h3','Freeze choices and validate'),node('p','Choose up to four sizes using IS results. Freezing is permanent for this run. Assess those same choices on already-accessed OOS data, inspect IS sensitivity, or refine their estimates with more paths. These checks do not select new sizes.','field-help'));
        const choices=node('div',undefined,'prop-sim-choice-grid'),rationale=node('textarea');rationale.placeholder='Why these sizes?';rationale.setAttribute('aria-label',phase+' freeze rationale');
        const frozenNotice=node('p'),message=node('p');message.setAttribute('role','status');const selected=new Set(),inputs=[];
        const calc=report.calculations,eligible=new Set(phase==='evaluation'?calc.frontier:calc.ranking);
        for(const row of [...calc.candidates].sort((a,b)=>a.manifest.configuration.micros-b.manifest.configuration.micros)){
          const label=node('label',undefined,'prop-sim-choice'),input=node('input');input.type='checkbox';input.value=row.candidate_id;input.disabled=!eligible.has(row.candidate_id);input.dataset.freezeCandidate=row.candidate_id;
          label.append(input,node('span',`${row.manifest.configuration.micros} MNQ${input.disabled?' · not eligible':''}`));choices.append(label);inputs.push(input);
          input.onchange=()=>{if(input.checked&&selected.size>=4){input.checked=false;message.textContent='Choose at most four sizes.';return;}if(input.checked)selected.add(input.value);else selected.delete(input.value);};
        }
        const freeze=node('button','Freeze selected sizes','button primary');freeze.type='button';freeze.id='prop-sim-'+phase+'-freeze';
        const actions=node('div',undefined,'mechanic-downloads'),pathLabel=node('label','Diagnostic paths per frozen size'),paths=node('input');paths.type='number';paths.min='8';paths.max='20000';paths.step='1';paths.value=String(Math.min(20000,Math.max(1000,saved.configuration.simulations*2)));paths.setAttribute('aria-label',phase+' diagnostic paths');pathLabel.append(paths);
        const history=node('div'),buttons=[];let frozen=null,busy=false,active=false;
        root.append(frozenNotice,choices,rationale,freeze,pathLabel,actions,message,history);
        const url=`/api/prop-sim/${selectedId}/validation/${phase}`;
        freeze.onclick=async()=>{if(!selected.size||!rationale.value.trim()){message.textContent='Choose sizes and enter a rationale before freezing.';return;}freeze.disabled=true;try{await read(url+'/freeze','POST',{candidate_ids:[...selected],rationale:rationale.value});await refreshValidation();}catch(e){message.textContent=e.message;freeze.disabled=false;}};
        for(const [kind,text] of [['oos','Assess frozen sizes on OOS'],['is_robustness','Check IS blocks and subperiods'],['precision','Run more paths for frozen sizes']]){
          const button=node('button',text,'button secondary');button.type='button';button.disabled=true;button.dataset.studyKind=kind;buttons.push(button);actions.append(button);
          button.onclick=async()=>{if(busy)return;if(kind!=='oos'&&!paths.reportValidity())return;busy=true;buttons.forEach(b=>b.disabled=true);message.textContent='Submitting saved assessment…';try{const body={request_id:crypto.randomUUID(),kind};if(kind!=='oos')body.paths=Number(paths.value);await read(url,'POST',body);message.textContent='Assessment queued. You can navigate away and return here or use Job history.';await refreshValidation();timer=setTimeout(refresh,2000);}catch(e){message.textContent=e.message;}finally{busy=false;buttons.forEach(b=>b.disabled=!frozen||active);}};
        }
        function studyTable(box,study){
          const rows=study.calculations.candidates,isEval=phase==='evaluation',oos=study.calculations.assessment_kind==='oos';
          const columns=[['MNQ',r=>r.configuration.micros],['Scenario',r=>r.scenario],['Status',r=>r.status]];
          if(isEval){
            if(oos)columns.push(['IS cost · USD',r=>fmt(r.is_comparison.cost_per_funded.is_value)],['IS mean days',r=>fmt(r.is_comparison.expected_calendar_days_to_funded.is_value)]);
            columns.push(['Mean cost · USD',r=>fmt(r.metrics.cost_per_funded)],['Mean calendar days',r=>fmt(r.metrics.expected_calendar_days_to_funded)],['Median days',r=>fmt(r.metrics.median_calendar_days_to_funded)],['P90 days',r=>fmt(r.metrics.p90_calendar_days_to_funded)],['First-account pass',r=>pct(r.metrics.pass_probability)]);
            if(oos)columns.push(['Days / IS',r=>fmt(r.is_comparison.expected_calendar_days_to_funded.oos_over_is)],['Cost / IS',r=>fmt(r.is_comparison.cost_per_funded.oos_over_is)]);
          }else{
            if(oos)columns.push(['IS mean receipts',r=>fmt(r.is_comparison.expected_funded_cash_payouts_within_horizon.is_value)]);
            columns.push(['Mean receipts · USD',r=>fmt(r.metrics.expected_funded_cash_payouts_within_horizon)],['Breach',r=>pct(r.metrics.account_breach_probability)],['First payout',r=>pct(r.metrics.probability_first_payout)]);
            if(oos)columns.push(['Receipts / IS',r=>fmt(r.is_comparison.expected_funded_cash_payouts_within_horizon.oos_over_is)]);
          }
          const wrap=node('div',undefined,'optimization-scroll'),table=node('table',undefined,'library-table prop-result-table'),head=node('tr'),body=node('tbody');columns.forEach(([name])=>head.append(node('th',name)));
          for(const row of rows){const tr=node('tr');columns.forEach(([,get])=>tr.append(node('td',String(get(row)??'—'))));body.append(tr);
            if(row.chronological_replay){const actual=row.chronological_replay;const tr=node('tr'),td=node('td');td.colSpan=columns.length;
              td.append(node('p',isEval?`Chronological OOS · ${actual.acquisition_completed?'funded in '+actual.calendar_days_to_funded+' calendar days':'not funded within observed window'} · ${fmt(actual.paid_fees)} USD paid · ${actual.attempts_started} evaluations`:`Chronological OOS · ${fmt(actual.cash_received)} USD received · ${actual.outcome} · ${actual.observed_calendar_days} observed calendar days`,'field-help'));
              detail(td,'Saved chronological events and uncertainty',{chronological:actual,uncertainty:row.uncertainty});tr.append(td);body.append(tr);}
          }
          const thead=node('thead');thead.append(head);table.append(thead,body);wrap.append(table);box.append(wrap);
          if(study.calculations.precision_interpretation)box.append(node('p',study.calculations.precision_interpretation,'field-help'));
          if(study.calculations.paired_comparisons?.length)detail(box,'Paired differences between frozen sizes',study.calculations.paired_comparisons);
        }
        async function refreshValidation(){
          const data=await read(url);if(!alive())return false;frozen=data.frozen;
          const compatible=data.numerical_implementation_compatible;
          frozenNotice.textContent=!compatible?'Historical numerical version: saved results remain readable. Start a new simulation to use the current freeze and validation tools.':frozen?`Choices frozen ${new Date(frozen.created_at_utc).toLocaleString()}. OOS was already used in strategy qualification; this is not an untouched holdout.`:'IS selection is not frozen yet.';
          freeze.disabled=!compatible;
          for(const input of inputs){if(frozen)input.checked=frozen.candidate_ids.includes(input.value);input.disabled=!compatible||!!frozen||!eligible.has(input.value);}
          freeze.hidden=rationale.hidden=!!frozen;
          if(frozen&&!root.querySelector('.prop-sim-freeze-link')){const links=node('div',undefined,'mechanic-downloads prop-sim-freeze-link');link(links,'Frozen choices JSON ↓',`/api/research-campaigns/${data.campaign_id}/exports/frozen_package.json`);root.insertBefore(links,pathLabel);}
          active=data.assessments.some(a=>['launching','queued','running'].includes(a.status));buttons.forEach(b=>b.disabled=!compatible||!frozen||busy||active);
          for(const attempt of data.assessments){
            let box=history.querySelector(`[data-assessment="${attempt.request_id}"]`);
            if(!box){box=node('section',undefined,'prop-sim-assessment panel');box.dataset.assessment=attempt.request_id;box.append(node('h4',({oos:'Frozen-size OOS assessment',is_robustness:'IS block and subperiod robustness',precision:'More-path precision assessment'})[attempt.kind]||'Saved assessment'));const status=node('p');status.setAttribute('role','status');box.append(status);history.prepend(box);}
            box.querySelector('[role=status]').textContent=`${attempt.status.toUpperCase()} · ${attempt.analysis?.progress||attempt.error||'Preparing inputs'}`;
            if(attempt.analysis_id&&!box.querySelector('.prop-sim-study-links')){const links=node('div',undefined,'mechanic-downloads prop-sim-study-links');link(links,'Job history / progress',`#jobs/prop_analysis/${attempt.analysis_id}`);link(links,'Assessment report JSON ↓',`/api/prop-analyses/${attempt.analysis_id}/downloads/report.json`);link(links,'Assessment evidence ZIP ↓',`/api/prop-analyses/${attempt.analysis_id}/downloads/analysis.zip`);box.append(links);}
            if(['queued','running'].includes(attempt.status)&&!box.querySelector('[data-stop-study]')){const stop=node('button','Stop assessment','button secondary');stop.type='button';stop.dataset.stopStudy='true';stop.onclick=async()=>{stop.disabled=true;try{await read(`/api/prop-analyses/${attempt.analysis_id}/cancel`,'POST');}catch(e){message.textContent=e.message;}await refreshValidation();};box.append(stop);}
            if(!['queued','running'].includes(attempt.status))box.querySelector('[data-stop-study]')?.remove();
            if(attempt.status==='complete'&&!box.dataset.loaded){const study=await read(url+'/'+attempt.request_id+'?summary=true');if(!alive())return false;studyTable(box,study);box.dataset.loaded='true';}
          }
          return active;
        }
        return {refresh:async()=>{try{return await refreshValidation();}catch(e){message.textContent='Validation: '+e.message;return false;}}};
      }
      function table(parent,phase,report){
        const c=report.calculations,rows=[...c.candidates].sort((a,b)=>a.manifest.configuration.micros-b.manifest.configuration.micros),isEval=phase==='evaluation';
        const summary=node('p');summary.id='prop-sim-'+phase+'-summary';summary.textContent=isEval?`${c.frontier.length} Pareto configurations · ${rows.filter(r=>r.status!=='estimated').length} unresolved/censored. Compare cost and calendar time; all nondominated configurations remain.`:c.winner?`Best estimated cash size: ${rows.find(r=>r.candidate_id===c.winner).manifest.configuration.micros} MNQ · ${c.near_ties.length} tied/near-tied alternatives. This is a point estimate.`:'No Funded winner. Inspect unresolved results or constraints below.';parent.append(summary);
        if(isEval&&c.precision_interpretation){parent.append(node('p',c.precision_interpretation,'field-help'));if(c.paired_comparisons?.length)detail(parent,'Paired funding-time and cost comparisons',c.paired_comparisons);}
        if(isEval&&saved.configuration.profile_id==='lucidflex-50k')parent.append(node('p','Calendar-aware acquisition: cost and time average every simulated retry chain. A 3,650-calendar-day computation guard leaves open paths unresolved; it is not a provider deadline.','field-help'));
        if(isEval){const dispose=evaluationChart(parent,rows);if(dispose)chartDisposers.push(dispose);}
        const wrap=node('div',undefined,'optimization-scroll'),t=node('table',undefined,'library-table prop-result-table');t.id='prop-sim-'+phase+'-table';const head=node('tr'),tb=node('tbody');
        const specs=isEval?[['MNQ size',r=>r.manifest.configuration.micros],['Status',r=>r.status],['Pareto frontier',r=>r.pareto_member?'Yes':'No'],['First-attempt pass %',r=>r.metrics.pass_probability,'pct'],['Acquisition cost · USD',r=>r.metrics.cost_per_funded,'number'],['Calendar days to Funded',r=>r.metrics.expected_calendar_days_to_funded,'number'],['P90 calendar days',r=>r.metrics.p90_calendar_days_to_funded,'number'],['Expected attempts',r=>r.metrics.expected_attempts_per_funded,'number']]:[['MNQ size',r=>r.manifest.configuration.micros],['Status',r=>r.feasible?'Eligible':r.status==='unresolved'?'Unresolved':'Constraint failed'],['Rank',r=>r.rank],['Mean trader receipts · USD',r=>r.metrics.expected_funded_cash_payouts_within_horizon,'number'],['Median receipts',r=>r.metrics.median_payouts,'number'],['P10 receipts',r=>r.metrics.p10_payouts,'number'],['Breach %',r=>r.metrics.account_breach_probability,'pct'],['Inactivity %',r=>r.metrics.probability_inactivity,'pct'],['First payout %',r=>r.metrics.probability_first_payout,'pct'],['Pending cash',r=>r.metrics.expected_pending_cash,'number'],['Account deductions',r=>r.metrics.expected_gross_account_deductions,'number']];
        if(isEval)specs.push(['Median calendar days',r=>r.metrics.median_calendar_days_to_funded,'number'],['Mean time MC SE · days',r=>r.uncertainty?.calendar_mean_se,'number'],['Funded within 60 days',r=>r.metrics.probability_funded_by_day_60,'pct'],['Funding-time near ties',r=>r.funding_time_near_ties?.map(id=>rows.find(x=>x.candidate_id===id)?.manifest.configuration.micros).join(', ')||'—']);
        if(isEval&&rows.some(r=>r.metrics.mean_final_attempt_days_after_target!=null)){
          parent.append(node('p','Time breakdown: earlier attempts + final account to first target + further trading after target + funded readiness = mean calendar days. Consistency requires additional net profit; elapsed time alone does not improve the ratio. Failed-after-target accounts increase retries.','field-help'));
          for(const [text,key] of [['Earlier attempts · days','days_before_final_attempt'],['Final: reach target · days','final_attempt_days_before_target'],['Final: after target · days','final_attempt_days_after_target'],['Readiness · days','pass_to_ready_days'],['Failures after target','failed_attempts_after_target'],['Consistency-blocked sessions','consistency_blocked_sessions']])specs.push([text,r=>r.metrics['mean_'+key],'number']);
        }
        let sort=0,direction=1;
        function paint(){const selected=new Set([...tb.querySelectorAll('.prop-sim-chart-highlight')].map(r=>r.dataset.size));tb.replaceChildren();const get=specs[sort][1];const ordered=[...rows].sort((a,b)=>{const av=get(a),bv=get(b);if(av==null||bv==null)return av==null?(bv==null?0:1):-1;return (typeof av==='number'?av-bv:String(av).localeCompare(String(bv)))*direction;});
          for(const row of ordered){const tr=node('tr');tr.dataset.size=row.manifest.configuration.micros;if(selected.has(tr.dataset.size))tr.classList.add('prop-sim-chart-highlight');for(const [,get,type] of specs){const v=get(row);tr.append(node('td',type==='pct'?pct(v):type==='number'?fmt(v):v==null?'—':String(v)));}const td=node('td');detail(td,'Details',{metrics:row.metrics,uncertainty:row.uncertainty,censoring:row.censoring,reason:row.reason,constraint_violations:row.constraint_violations,assumptions:row.assumptions,sample_path:row.paths?.[0]});tr.append(td);tb.append(tr);}
          [...head.children].forEach((th,i)=>{th.setAttribute('aria-sort',i===sort?(direction===1?'ascending':'descending'):'none');const button=th.querySelector('button');if(button)button.textContent=specs[i][0]+' '+(i===sort?(direction===1?'↑':'↓'):'↕');});
        }
        specs.forEach(([text],i)=>{const th=node('th'),button=node('button',text+' ↕');button.type='button';button.onclick=()=>{direction=sort===i?-direction:1;sort=i;paint();};th.append(button);head.append(th);});head.append(node('th','Details'));const th=node('thead');th.append(head);t.append(th,tb);paint();wrap.append(t);parent.append(wrap);
        const links=node('div',undefined,'mechanic-downloads prop-sim-exports');for(const [kind,text] of [['results.csv','Results CSV ↓'],['results.json','Calculations JSON ↓'],['report.json','Saved report JSON ↓'],['analysis.zip','Evidence ZIP ↓'],['source_checks.json','Source checks ↓']])link(links,text,`/api/research-campaigns/${saved.campaign_ids[phase]}/exports/${kind}`);parent.append(links);
        validationControllers[phase]=validationControls(parent,phase,report);
      }
      async function refresh(){clearTimeout(timer);try{
        const current=await read('/api/prop-sim/'+selectedId);if(!alive())return;saved=current;
        if(!results.querySelector('.prop-sim-run-heading')){const title=node('section',undefined,'panel prop-sim-run-heading'),p=profiles[saved.configuration.profile_id||'apex-50k-eod'];title.append(node('span',p.name,'pill neutral'),node('h2',saved.qualification?.strategy_id?.replaceAll('_',' ')||'Saved simulation'),node('p',`Evaluation and Funded are independent searches · ${saved.configuration.simulations.toLocaleString()} paths per size · ${saved.configuration.funded_horizon_calendar_days}-day Funded horizon`,'field-help'));if(saved.qualification?.plan){const q=saved.qualification;title.append(node('p',`${q.dataset.name} · Broad ${q.broad_trial} / Narrow ${q.narrow_trial} · IS ${q.plan.is_start} → ${q.plan.is_end}`,'field-help'));detail(title,'Frozen strategy parameters',q.parameters);}const actions=node('div',undefined,'mechanic-downloads');link(actions,'New simulation','#prop-sim');const edit=node('button','Adjust settings','button secondary');edit.type='button';edit.onclick=()=>{setup.open=true;setup.scrollIntoView({behavior:'smooth',block:'start'});};actions.append(edit);for(const phase of ['evaluation','funded']){const jump=node('button',phase==='evaluation'?'View Evaluation':'View Funded','button secondary');jump.type='button';jump.onclick=()=>document.querySelector('#prop-sim-'+phase+'-results')?.scrollIntoView({behavior:'smooth',block:'start'});actions.append(jump);}actions.append(deleteButton(selectedId));title.append(actions);results.append(title);host.insertBefore(results,setup);}
        let validationActive=false;
        for(const phase of ['evaluation','funded']){const job=saved.phases[phase];let panel=phasePanels[phase];if(!panel){panel=node('section',undefined,'panel broad-panel');panel.id='prop-sim-'+phase+'-results';panel.append(node('h2',phase==='evaluation'?'Evaluation · acquisition cost and time':'Funded · cash-receipt sizing'));const state=node('p');state.id='prop-sim-'+phase+'-progress';state.setAttribute('role','status');panel.append(state);results.append(panel);phasePanels[phase]=panel;}
          panel.querySelector('[role=status]').textContent=`${job.status.toUpperCase()} · ${job.progress||'Ready'}${job.error?' · '+job.error:''}`;
          if(job.analysis_id){let links=panel.querySelector('.prop-sim-job-link');if(!links){links=node('div',undefined,'mechanic-downloads prop-sim-job-link');panel.append(links);}links.replaceChildren();link(links,'Job history / progress',`#jobs/prop_analysis/${job.analysis_id}`);}
          if(job.status==='complete'&&loaded[phase]!==job.analysis_id){const report=await read(`/api/prop-sim/${selectedId}/results/${phase}`);if(!alive())return;table(panel,phase,report);loaded[phase]=job.analysis_id;}
          if(validationControllers[phase])validationActive=await validationControllers[phase].refresh()||validationActive;
        }
        let controls=results.querySelector('#prop-sim-job-controls');if(!controls){controls=node('div',undefined,'mechanic-downloads');controls.id='prop-sim-job-controls';results.querySelector('.prop-sim-run-heading').append(controls);}controls.replaceChildren();const active=Object.values(saved.phases).some(p=>['queued','running'].includes(p.status));results.querySelectorAll('[data-delete-simulation]').forEach(button=>{button.disabled=active||deleting;button.title=active?'Stop running jobs before deleting this simulation.':'';});
        if(active){const stop=node('button','Stop running analyses','button secondary');stop.type='button';stop.id='prop-sim-stop';stop.onclick=async()=>{stop.disabled=true;try{await read('/api/prop-sim/'+selectedId+'/cancel','POST');if(alive())await refresh();}catch(error){if(alive())notice.textContent=error.message;}};controls.append(stop);timer=setTimeout(refresh,2500);}
        else if(Object.values(saved.phases).some(p=>p.status!=='complete')){const retry=node('button','Retry incomplete phases','button secondary');retry.type='button';retry.onclick=async()=>{try{await read('/api/prop-sim','POST',saved.configuration);if(alive())await refresh();}catch(error){if(alive())notice.textContent=error.message;}};controls.append(retry);}
        if(validationActive&&!active)timer=setTimeout(refresh,2500);
      }catch(error){if(alive())notice.textContent=error.message;}}
      applyAccount(false);
      if(selectedId){await refresh();if(!alive())return;if(saved){accountPicker.value=saved.configuration.profile_id||'apex-50k-eod';dll.checked=saved.configuration.daily_loss_limit??true;consistency.value=String(saved.configuration.evaluation_consistency_percent??40);const index=sources.items.findIndex(s=>JSON.stringify(s.selection)===JSON.stringify(saved.configuration.selections[0]));if(index>=0)picker.value=String(index);for(const [name] of names){const value=name.endsWith('_micros')?range(saved.configuration,name.split('_')[0])[name.includes('_minimum_')?'minimum':'maximum']:saved.configuration[name];fields[name].value=name==='closures'?value.join(','):String(value??'');}applyAccount(false);select();}}
      else if(sourceId){const index=sources.items.findIndex(s=>[s.source_backtest_id,s.oos_report_id].includes(sourceId));if(index>=0){picker.value=String(index);select();}else{notice.textContent='This backtest has no currently qualified configuration. Complete all campaign phases and Monte Carlo before selecting it.';update();}}
      else update();
    }catch(error){if(alive())host.replaceChildren(node('p',error.message));}
  }
  window.addEventListener('hashchange',render);render();
})();
