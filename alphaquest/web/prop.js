/* Existing portal report → configuration → durable local report; historical notebook reports remain readable. */
(() => {
  const $ = s => document.querySelector(s);
  const deletingReports=new Set();
  let sourceId, checked = false, busy = false, token = 0, holdoutSource=false,nativeRiskSource=false;
  const el = (tag, text, cls) => {const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
  const display = v => v === null || v === undefined ? 'Unavailable' : typeof v === 'number' ? String(v) : String(v);
  async function read(url, options) {const r=await fetch(url,options);const j=await r.json();if(!r.ok)throw Error(typeof j.detail==='string'?j.detail:JSON.stringify(j.detail));return j;}
  const post = (url, data) => read(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  function details(parent,title,data) {const d=el('details');d.append(el('summary',title),el('pre',JSON.stringify(data,null,2)));parent.append(d);}
  function table(parent,rows,columns) {
    if(!rows.length){parent.append(el('p','No observations available.'));return;}
    const wrap=el('div',undefined,'prop-scroll'),t=el('table',undefined,'prop-table'),head=el('tr'),body=el('tbody');
    columns=columns||Object.keys(rows[0]).filter(k=>!Array.isArray(rows[0][k])&&typeof rows[0][k]!=='object');
    columns.forEach(k=>head.append(el('th',k)));t.append(head,body);
    rows.forEach(r=>{const tr=el('tr');columns.forEach(k=>tr.append(el('td',display(r[k]))));body.append(tr);});wrap.append(t);parent.append(wrap);return t;
  }
  function metrics(parent,data) {table(parent,Object.entries(data).filter(([,v])=>!Array.isArray(v)&& (v===null||typeof v!=='object')).map(([metric,value])=>({metric,value})));}
  function section(title) {const n=el('section',undefined,'panel prop-panel');n.append(el('h2',title));$('#prop-report-content').append(n);return n;}
  const svgNode = (tag,attrs) => {const n=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v]of Object.entries(attrs))n.setAttribute(k,v);return n;};
  function chart(parent,title,series,labels=[]) {
    parent.append(el('h3',title));const svg=svgNode('svg',{viewBox:'0 0 1000 280',role:'img','aria-label':title,class:'prop-chart'});
    const vals=series.flatMap(s=>s.values).filter(v=>v!==null&&Number.isFinite(v));
    if(!vals.length){parent.append(el('p','No observations available.'));return;}
    const low=Math.min(0,...vals),high=Math.max(1,...vals),maxLength=Math.max(...series.map(s=>s.values.length));
    const colors=['#14734b','#ad2929','#2563eb','#b57919','#7139a4'];
    series.forEach((s,i)=>{let d='';let connected=false;s.values.forEach((v,j)=>{if(v===null){connected=false;return;}d+=`${connected?'L':'M'}${50+j*900/Math.max(1,maxLength-1)},${230-(v-low)*200/(high-low)} `;connected=true;});svg.append(svgNode('path',{d,fill:'none',stroke:s.color||colors[i%colors.length],'stroke-width':series.length>30?'.7':'2',opacity:series.length>30?'.35':'1'}));});
    [[50,18,display(high)],[50,250,display(low)],[100,275,labels[0]||'First observation'],[730,275,labels.at(-1)||'Last observation']].forEach(([x,y,t])=>{const n=svgNode('text',{x,y,'font-size':12,fill:'#333'});n.textContent=t;svg.append(n);});parent.append(svg);
    parent.append(el('p',series.length<=10?series.map((s,i)=>`${s.name} (${colors[i%colors.length]})`).join(' · '):`${series.length} retained paths; green=pass, red=drawdown, gray=deadline. Sample is stated below.`));
  }
  function bars(parent,title,values,labels) {
    parent.append(el('h3',title));const svg=svgNode('svg',{viewBox:'0 0 1000 280',role:'img','aria-label':title,class:'prop-chart'});
    const high=Math.max(1,...values);values.forEach((v,i)=>{const x=40+i*920/values.length,w=Math.min(100,800/values.length),height=v*200/high;svg.append(svgNode('rect',{x,y:230-height,width:w,height,fill:['#14734b','#ad2929','#b57919','#999'][i%4]}));const text=svgNode('text',{x,y:252,'font-size':13});text.textContent=labels[i]+' '+v;svg.append(text);});parent.append(svg);
  }
  function histogram(parent,title,h) {if(!h)return;chart(parent,title,[{name:'frequency',values:h.counts}],h.edges.map(String));details(parent,`${title}: inspect bins`,h);}
  function payload() {
    const settings=JSON.parse($('#prop-overrides').value||'{}');
    Object.assign(settings,{EVAL_PRICE:$('#prop-eval-fee').value,ACTIVATION_FEE:$('#prop-activation').value,
      BLOCK_DAYS:$('#prop-block').value,SLOTS:$('#prop-slots').value,MAX_TOTAL_NQ:$('#prop-max-nq').value,
      OUT_OF_SAMPLE_FROM:$('#prop-holdout').value});
    return {source_backtest_id:sourceId,trade_file:holdoutSource?'':$('#prop-trade-file').value||(nativeRiskSource?'':null),
      export_timezone:$('#prop-export-timezone').value,settings};
  }
  function setBusy(v){busy=v;$('#prop-check').disabled=v;$('#prop-run').disabled=v||!checked;$('#prop-form').querySelectorAll('input,select,textarea').forEach(n=>n.disabled=v||holdoutSource);}
  function invalidate(){checked=false;$('#prop-check-output').replaceChildren();$('#prop-run').disabled=true;$('#prop-status').textContent='Settings changed. Check source costs and filtering before running.';}
  $('#prop-form').addEventListener('input',invalidate);
  $('#prop-check').addEventListener('click',async()=>{try{setBusy(true);const data=await post('/api/prop-analyses/check',payload());checked=true;const p=$('#prop-check-output');p.replaceChildren(el('h3','Source check passed'));metrics(p,{matched_trades:data.matched_trades,measured_MAE:data.source.excursion_input.measured_mae_count,measured_MFE:data.source.excursion_input.measured_mfe_count,held_OHLC_trades:data.source.excursion_input.native_ohlc_count||0,ambiguous_adverse_bounds:data.source.excursion_input.ambiguous_mae_count||0,source_net_PnL:data.source.reconciliation.source_totals.net_pnl,engine:'AlphaQuest local calculations'});details(p,'Cost reconciliation, excluded trades and provenance',data.source);details(p,'Every resolved setting and override origin',data);$('#prop-status').textContent='Trade IDs, UTC times, quantities and net costs match. Ready to run locally.';}catch(e){checked=false;$('#prop-status').textContent=e.message;}finally{setBusy(false);}});
  $('#prop-form').addEventListener('submit',async e=>{e.preventDefault();if(busy||!checked)return;try{setBusy(true);const job=await post('/api/prop-analyses',payload());location.hash=`#backtests/prop/job/${job.id}`;}catch(e){$('#prop-status').textContent=e.message;setBusy(false);}});
  async function configure(id,t) {
    $('#prop-heading-title').textContent='Configure prop analysis';$('#prop-heading-note').textContent='Choose assumptions, check the source, then run locally.';
    sourceId=id;checked=false;$('#prop-config').hidden=true;$('#prop-report').hidden=true;$('#prop-status').textContent='Loading source and matching exports…';
    const [data,defaults]=await Promise.all([read(`/api/prop-analyses/sources/${id}`),read('/api/prop-analyses/defaults')]);if(t!==token)return;
    holdoutSource=data.source.run_metadata.research?.phase==='oos';nativeRiskSource=!!data.source.intratrade_risk;
    $('#prop-back').href=`#backtests/report/${id}`;$('#prop-source').textContent=`${data.source.run_metadata.strategy.id} · ${data.source.run_metadata.dataset.name} · ${data.source.summary.trades_taken} saved trades · ${id}`;
    $('#prop-form').reset();$('#prop-overrides').value='{}';
    $('#prop-trade-file').value=!holdoutSource&&!nativeRiskSource&&data.matched_exports?.length===1?data.matched_exports[0].path:'';
    $('#prop-eval-fee').value=defaults.defaults.EVAL_PRICE;$('#prop-activation').value=defaults.defaults.ACTIVATION_FEE;
    $('#prop-block').value=defaults.defaults.BLOCK_DAYS;$('#prop-slots').value=defaults.defaults.SLOTS;
    $('#prop-max-nq').value=defaults.defaults.MAX_TOTAL_NQ;$('#prop-holdout').value='';
    $('#prop-saved').replaceChildren();for(const a of data.analyses){const row=el('div',undefined,'strategy-saved-prop-row'),link=el('a',`${a.created} · ${a.status} · ${a.id}`);link.href=`#backtests/prop/job/${a.id}`;const remove=el('button','Delete','button danger');remove.type='button';remove.disabled=['queued','running'].includes(a.status);remove.setAttribute('aria-label',`Delete prop report ${a.id}`);remove.onclick=()=>deleteProp(a.id,row);row.append(link,remove);$('#prop-saved').append(row);}
    $('#prop-check-output').replaceChildren();$('#prop-defaults').textContent=JSON.stringify(defaults.defaults,null,2);$('#prop-status').textContent=holdoutSource?'OOS source · Reopen the verified saved automatic analysis. New calculations require another budgeted selection from an IS report.':'AlphaQuest local calculations · selected backtest period, internal 30% validation, block 5, standard simulation counts. Check the source before running.';$('#prop-config').hidden=false;setBusy(false);
  }
  function render(r) {
    $('#prop-delete').hidden=false;$('#prop-delete').disabled=deletingReports.has(r.id);$('#prop-delete').onclick=()=>deleteProp(r.id);
    $('#prop-heading-title').textContent='Prop analysis';$('#prop-heading-note').textContent='Saved analysis report';$('#prop-report-content').className='';
    if(r.format_version===3){renderNative(r);return;}
    if(r.format_version===2){renderExternalHistory(r);return;}
    $('#prop-config').hidden=true;$('#prop-report').hidden=false;$('#prop-report-content').replaceChildren();$('#prop-back').href=`#backtests/report/${r.source.backtest.id}`;
    $('#prop-status').textContent=`Saved analysis ${r.id} · ${r.created_at_utc} · increment ${r.increment}. Reload reads saved results.`;
    const links=$('#prop-downloads');links.replaceChildren();for(const kind of ['report.json','trades.csv','daily.csv','analysis.zip']){const a=el('a',kind+' ↓','button secondary');a.href=`/api/prop-analyses/${r.id}/downloads/${kind}`;links.append(a);}
    let notice=section('Historical notebook report');notice.append(el('p','This saved report uses the previous notebook model. New prop analyses use AlphaQuest local calculations and can reproduce its reports.'));const rerun=el('a','Configure a local analysis','button primary');rerun.href=`#backtests/prop/new/${r.source.backtest.id}`;notice.append(rerun);
    let p=section('Source, costs and trade statistics');metrics(p,r.statistics);metrics(p,r.engine);details(p,'Source cost arithmetic and filtering',r.source);details(p,'Bootstrap confidence intervals',r.statistics);
    p=section('Source net equity on notebook $100,000 base');if(r.source_equity){chart(p,'Source cumulative net equity',[{name:'net equity',values:r.source_equity.equity}],r.source_equity.dates);metrics(p,r.source_equity);}
    p=section('Evaluation Monte Carlo');metrics(p,r.evaluation);details(p,'Pass probability interval and full metrics',r.evaluation);table(p,r.evaluation_probabilities||['passed','fail_dd','fail_daily','fail_time'].map(outcome=>({outcome,count:r.evaluation[outcome]})),r.evaluation_probabilities?['outcome','count','probability','ci']:undefined);if(r.charts.evaluation_outcomes)bars(p,'Evaluation outcomes',r.charts.evaluation_outcomes.counts,r.charts.evaluation_outcomes.labels);histogram(p,'Days to pass',r.charts.days_to_pass);histogram(p,'Maximum drawdown',r.charts.drawdown);
    p=section('Saved equity path samples');chart(p,'Evaluation profit paths',r.paths.equity.map((values,i)=>({values,color:{pass:'#14734b',fail_dd:'#ad2929',fail_time:'#999'}[r.paths.outcomes[i]]})));metrics(p,{sample:r.paths.sample,seed:r.paths.seed,retained_paths:r.paths.equity.length});details(p,'Inspect saved path values and outcomes',r.paths);
    p=section('Weekday dataset');metrics(p,r.daily_summary||{weekdays:r.daily.length,zero_trade_weekdays:r.daily.filter(d=>d.n_trades===0).length});table(p,r.daily.slice(0,20));p.append(el('p','First 20 weekdays; complete grid and ordered trades are in CSV downloads.'));
    if(r.sizing){p=section('Evaluation sizing and staged sizing');table(p,r.sizing.sweep);metrics(p,r.sizing.selected);metrics(p,r.sizing.validation);table(p,r.sizing.staged);details(p,'Sample switching and staged comparison',r.sizing);p.append(el('p','Staged sizing uses the validation sample and omits DLL. Notebook CI tie language and selection behavior are preserved.'));chart(p,'Evaluation pass rate by size',[{name:'train pass rate',values:r.sizing.sweep.map(v=>v.pr)}],r.sizing.sweep.map(v=>String(v.nc)));p=section('Repeated attempts');table(p,r.attempts.independent);table(p,r.attempts.correlated);details(p,'Attempt assumptions and budget',r.attempts);}
    if(r.funded){p=section('Funded first payout');metrics(p,r.funded.detail);bars(p,'Funded outcomes',['qualified','blown','closed_inactive','timeout'].map(k=>r.funded.detail[k]),['payout','blown','inactive','horizon']);table(p,r.funded.sweep);details(p,'Selected funded size and full saved metrics',r.funded);chart(p,'Expected first payout by size',[{name:'expected payout',values:r.funded.sweep.map(v=>v.expected_payout)},{name:'net EV',values:r.funded.sweep.map(v=>v.net_ev)}],r.funded.sweep.map(v=>String(v.n_contracts)));histogram(p,'First payout distribution',r.charts.first_payout);histogram(p,'Time to qualify',r.charts.qualifying_days);p.append(el('p','Selection uses the holdout again. If no size meets the blown ceiling, the notebook selects from all sizes. Horizon outcomes are still-open simulations.'));}
    if(r.lifetime){p=section('Lifetime extraction and account survival');metrics(p,r.lifetime.selected);table(p,r.lifetime.sweep);chart(p,'Lifetime extraction by size',[{name:'mean extraction',values:r.lifetime.sweep.map(v=>v.expected_total)},{name:'median extraction',values:r.lifetime.sweep.map(v=>v.median_total)}],r.lifetime.sweep.map(v=>String(v.n_contracts)));bars(p,'Lifetime account outcomes',Object.values(r.lifetime.selected.outcome_ct),Object.keys(r.lifetime.selected.outcome_ct));histogram(p,'Lifetime extraction',r.charts.lifetime_total);histogram(p,'Payout counts',r.charts.payout_count);histogram(p,'Account lifetimes',r.charts.account_lifetimes);details(p,'Lifetime distributions and horizon disclosure',r.lifetime);p=section('Sizing funnel and economics');table(p,r.economics.funnel);metrics(p,r.economics);details(p,'Acquisition formula and recommendation',r.economics);p=section('Block-length robustness');table(p,r.robustness);}
    p=section('Versioned model assumptions and reproducibility');p.append(el('p','Analytical notebook model; no current provider-rule certification. Fractional minis and micro equivalents are scaling labels. Known behavior: holdout reused for downstream selections; staged DLL omitted; daily evaluation differs; exact-DLL clipping; weekday/inactivity approximations; selection fallbacks; acquisition and repeated-attempt shortcuts. Missing excursions are never measured MAE.'));
    details(p,'All resolved settings, literal notebook defaults and override origins',{settings:r.settings,literal_defaults:r.literal_notebook_defaults,origins:r.setting_origins,rules:r.rules});details(p,'Hashes, runtime and seed streams',{model:r.model_version,notebook:r.notebook_sha256,input:r.input_sha256,runtime:r.runtime,seeds:r.seed_streams,commit:r.application_commit,implementation:r.implementation_sha256,samples:r.samples});
  }
  function nativeFrame(r) {
    $('#prop-config').hidden=true;$('#prop-report').hidden=false;$('#prop-report-content').replaceChildren();$('#prop-report-content').className='';
    $('#prop-back').href=`#backtests/report/${r.source.backtest.id}`;
    const links=$('#prop-downloads');links.replaceChildren();
    for(const kind of ['report.json','trades.csv','analysis.zip']){const a=el('a',kind+' ↓','button secondary');a.href=`/api/prop-analyses/${r.id}/downloads/${kind}`;links.append(a);}
  }
  function renderExternalHistory(r) {
    nativeFrame(r);$('#prop-status').textContent=`Historical analysis ${r.id}`;
    const p=section('Historical external-engine report');
    p.append(el('p','This report was created by the retired external-engine integration. Its saved downloads are preserved. Run a new local analysis to see AlphaQuest calculations.'));
    const a=el('a','Configure a local analysis','button primary');a.href=`#backtests/prop/new/${r.source.backtest.id}`;p.append(a);
  }
  // Presentation only: every statistic below comes from the saved local report.
  const available = v => v !== null && v !== undefined && v !== '' && Number.isFinite(Number(v));
  const number = (v,digits=0) => available(v) ? Number(v).toLocaleString('en-US',{maximumFractionDigits:digits}) : 'Unavailable';
  const money = (v,digits=2) => available(v) ? Number(v).toLocaleString('en-US',{style:'currency',currency:'USD',minimumFractionDigits:digits,maximumFractionDigits:digits}) : 'Unavailable';
  const percent = v => available(v) ? Number(v).toLocaleString('en-US',{style:'percent',minimumFractionDigits:1,maximumFractionDigits:1}) : 'Unavailable';
  const days = v => available(v) ? `${number(v,1)} trading days` : 'Not reached';
  const dateRange = range => (range||[]).join(' → ');
  function reportBlock(parent,title,caption,cls='') {
    const block=el('section',undefined,`prop-insight-block ${cls}`);block.append(el('h2',title));
    if(caption)block.append(el('p',caption,'prop-explainer'));
    parent.append(block);return block;
  }
  function facts(parent,items,cls='') {
    const list=el('dl',undefined,`prop-facts ${cls}`);
    for(const [label,value,note] of items){const item=el('div');item.append(el('dt',label),el('dd',value));if(note)item.append(el('p',note));list.append(item);}
    parent.append(list);return list;
  }
  function metricCard(parent,label,value,note,exact,tone='') {
    const card=el('div',undefined,`prop-metric ${tone}`),metric=el('strong',value);
    if(exact!==undefined&&exact!==null)metric.title=`Saved value: ${exact}`;
    card.append(el('span',label,'prop-metric-label'),metric,el('p',note));parent.append(card);
  }
  function probabilityRows(parent,rows) {
    const list=el('div',undefined,'prop-probabilities');
    for(const [label,value,tone] of rows){
      const row=el('div',undefined,`prop-probability ${tone||''}`),heading=el('div');
      heading.append(el('span',label),el('strong',percent(value)));row.append(heading);
      if(available(value)){const meter=el('meter');meter.min=0;meter.max=1;meter.value=value;meter.setAttribute('aria-label',label);meter.setAttribute('aria-valuetext',percent(value));row.append(meter);}
      list.append(row);
    }
    parent.append(list);
  }
  function readableTable(parent,rows,columns,{caption,selected}={}) {
    const wrap=el('div',undefined,'prop-readable-scroll');wrap.tabIndex=0;wrap.setAttribute('role','region');wrap.setAttribute('aria-label',caption||'Results table');
    const t=el('table',undefined,'prop-readable-table');
    const cap=el('caption',caption,'prop-visually-hidden');t.append(cap);
    const thead=el('thead'),head=el('tr'),body=el('tbody');
    for(const column of columns){const th=el('th',column.label);th.scope='col';if(column.numeric)th.className='prop-numeric';head.append(th);}
    thead.append(head);t.append(thead,body);
    for(const row of rows){
      const tr=el('tr');if(selected?.(row)){tr.className='prop-selected-row';tr.setAttribute('aria-label',`Selected size: ${row.micros} MNQ`);}
      columns.forEach((column,index)=>{
        const cell=el(index===0?'th':'td');if(index===0)cell.scope='row';if(column.numeric)cell.className='prop-numeric';
        const v=row[column.key];cell.append(column.render?column.render(v,row):el('span',column.format?column.format(v):display(v)));
        if(typeof v==='number')cell.title=`Saved value: ${v}`;
        if(column.tone&&available(v)&&v<0)cell.classList.add('prop-negative');tr.append(cell);
      });body.append(tr);
    }
    wrap.append(t);parent.append(el('p','Scroll the table sideways to see all columns.','prop-table-hint'),wrap);return t;
  }
  function explanation(parent,title,text) {
    const d=el('details',undefined,'prop-help');d.append(el('summary',title),el('p',text));parent.append(d);return d;
  }
  function renderNative(r) {
    nativeFrame(r);
    $('#prop-heading-title').textContent='Funded simulation';document.title='Funded simulation · AlphaQuest';
    $('#prop-heading-note').textContent='Apex 50K EOD · AlphaQuest local model';
    const created=new Date(r.created_at_utc);
    $('#prop-status').textContent=`Saved ${Number.isNaN(created.getTime())?r.created_at_utc:created.toLocaleString(undefined,{dateStyle:'medium',timeStyle:'short'})}`;
    const downloadNames=['Report data (JSON)','Source trades (CSV)','Download all results (ZIP)'];
    [...$('#prop-downloads').children].forEach((link,i)=>{link.textContent=downloadNames[i];if(i===2)link.className='button primary';});
    const rerun=el('a','Configure new analysis','button secondary');rerun.href=`#backtests/prop/new/${r.source.backtest.id}`;$('#prop-downloads').append(rerun);
    const root=$('#prop-report-content'),c=r.calculations,e=c.evaluation,f=c.funded,s=f?.selected,source=r.source;
    root.className='prop-insight-report';
    const context=el('div',undefined,'prop-report-context');
    const sourceLink=el('a',`Strategy: ${source.backtest.run_metadata.strategy.id.replaceAll('_',' ')}`);sourceLink.href=`#backtests/report/${source.backtest.id}`;context.append(sourceLink);
    context.append(el('span',`${number(source.reconciliation.source_count)} source trades`),el('span',`Holdout: ${dateRange(c.samples.validation)}`),el('span',`${number(e.simulations)} evaluation paths`));root.append(context);
    if(source.excursion_input.native_ohlc_count){root.append(el('p',source.excursion_provenance,'prop-assumption-note'));}else if(source.excursion_input.measured_mae_count<source.reconciliation.source_count){root.append(el('p',`Excursion coverage: ${number(source.excursion_input.measured_mae_count)} of ${number(source.reconciliation.source_count)} trades have measured MAE. Remaining trades use a close-only fallback, which may understate intratrade risk.`,'prop-assumption-note'));}
    if(r.model_version!=='alphaquest-apex50k-eod-v3-training-economics')root.append(el('p',`Saved earlier model: ${r.model_version}. Its results are preserved. Configure a new analysis on an IS report to use the current training-calibrated model.`, 'prop-assumption-note'));
    if(f&&e.pass_rate===0)root.append(el('p','No holdout evaluation passed. Funded outcomes are conditional on starting with a funded account; training-selected size and replay economics remain frozen.','prop-assumption-note'));
    const nav=el('div',undefined,'prop-report-tabs');nav.setAttribute('role','tablist');nav.setAttribute('aria-label','Simulation report views');
    root.append(nav);
    const views={},buttons={},definitions=[['overview','Overview'],['evaluation','Evaluation'],...(f?[['sizing','Sizing'],['history','Historical replay']]:[]),['model','Source & model']];
    function selectView(key,moveFocus=false){
      for(const [name] of definitions){const active=name===key;views[name].hidden=!active;buttons[name].setAttribute('aria-selected',String(active));buttons[name].tabIndex=active?0:-1;}
      if(moveFocus){buttons[key].focus({preventScroll:true});root.scrollIntoView({block:'start'});buttons[key].scrollIntoView({block:'nearest',inline:'nearest'});}
    }
    for(const [key,label] of definitions){
      const button=el('button',label);button.type='button';button.id=`prop-tab-${key}`;button.setAttribute('role','tab');button.setAttribute('aria-controls',`prop-view-${key}`);
      const panel=el('div',undefined,'prop-report-view');panel.id=`prop-view-${key}`;panel.setAttribute('role','tabpanel');panel.setAttribute('aria-labelledby',button.id);panel.tabIndex=0;
      buttons[key]=button;views[key]=panel;nav.append(button);root.append(panel);
      button.addEventListener('click',()=>selectView(key,true));
      button.addEventListener('keydown',event=>{
        const keys=definitions.map(d=>d[0]),index=keys.indexOf(key);let next;
        if(event.key==='ArrowRight')next=(index+1)%keys.length;if(event.key==='ArrowLeft')next=(index+keys.length-1)%keys.length;
        if(event.key==='Home')next=0;if(event.key==='End')next=keys.length-1;
        if(next!==undefined){event.preventDefault();selectView(keys[next],true);}
      });
    }
    function viewButton(parent,label,key){const b=el('button',label,'button secondary');b.type='button';b.addEventListener('click',()=>selectView(key,true));parent.append(b);}
    const fileBase=`/api/prop-analyses/${r.id}/files/`;
    function fileLink(parent,path,label){if(!r.files[path])return;const a=el('a',label,'prop-file-link');a.href=fileBase+path.split('/').map(encodeURIComponent).join('/');a.title=path;parent.append(a);}

    // The overview deliberately keeps one funded account separate from slot history.
    if(f){
      let p=reportBlock(views.overview,'What happens to one funded account?',`${s.micros} MNQ · ${number(s.sims)} simulated accounts on holdout days. Payouts are before evaluation and activation costs.`);
      const kpis=el('div',undefined,'prop-metric-grid');p.append(kpis);
      metricCard(kpis,'Average lifetime payout',money(s['E[payout]']),'Average across every funded account, including those paid $0.',s['E[payout]']);
      metricCard(kpis,'Median lifetime payout',money(s['median life']),'The middle account in the simulated outcomes.',s['median life']);
      metricCard(kpis,'Receives a payout',percent(s['P(>=1 payout)']),'At least one payout over the account’s lifetime.',s['P(>=1 payout)']);
      metricCard(kpis,'Fails the drawdown limit',percent(s.blown),'May have received payouts before the account failed.',s.blown,'prop-risk-metric');
      const takeaway=el('div',undefined,'prop-takeaway');
      if(f.outcomes.never_paid>=.5){takeaway.append(el('strong','Most accounts receive no payout.'),el('p',`${percent(f.outcomes.never_paid)} finish without a payout. Read the ${money(s['E[payout]'])} average alongside the ${money(s['median life'])} median.`));}
      else{takeaway.append(el('strong','The average and the typical account can differ.'),el('p',`${percent(f.outcomes.never_paid)} receive no payout. The lifetime average is ${money(s['E[payout]'])}; the median is ${money(s['median life'])}.`));}
      p.insertBefore(takeaway,kpis);
      const split=el('div',undefined,'prop-two-column');views.overview.append(split);
      p=reportBlock(split,'How far do accounts get?','These three payout outcomes are mutually exclusive.');
      probabilityRows(p,[['No payouts',f.outcomes.never_paid,'prop-neutral'],['1–5 payouts',f.outcomes.paid_partial,''],['All 6 payouts',f.outcomes.paid_all,'prop-complete']]);
      p.append(el('p','Drawdown failure is a separate measure: an account can be paid and later fail. Do not add the failure rate to these payout outcomes.','prop-explainer'));
      p=reportBlock(split,'When is the first payout?','Among accounts that receive at least one payout.');
      facts(p,[['Median',days(s['T1 median'])],['75th percentile',days(s['T1 p75'])],['90th percentile',days(s['T1 p90'])]]);
      p.append(el('p','Trading days include zero-trade weekdays; they are not calendar days.','prop-explainer'));
      p=reportBlock(views.overview,'First year and account lifetime','Gross payouts per funded account, not the net profit of a slot portfolio.');
      readableTable(p,[{horizon:'First year · 261 trading days',average:s['E[P] 12m'],median:s['median 12m'],chance:s['P(>=1) 12m']},{horizon:'Lifetime · up to 2,000 trading days',average:s['E[payout]'],median:s['median life'],chance:s['P(>=1 payout)']}],[{key:'horizon',label:'Horizon'},{key:'average',label:'Average payout',format:money,numeric:true},{key:'median',label:'Median payout',format:money,numeric:true},{key:'chance',label:'Receives a payout',format:percent,numeric:true}],{caption:'First-year and lifetime payout comparison'});
      explanation(p,'Why can the payout chances differ slightly?','First-year and lifetime outcomes come from independent simulation runs. Each is an estimate from its own random draws; the first-year chance can be slightly higher or lower.');
      p=reportBlock(views.overview,'Getting to this funded account','Evaluation costs and timing are shown separately from funded payouts.');
      facts(p,[['Evaluation size',`${e.selected_micros} MNQ`],['Funded size',`${s.micros} MNQ`],['Average acquisition cost',money(e.cost_per_funded),'Repeated evaluation fees plus one activation fee.']],'prop-facts-inline');
      const actions=el('div',undefined,'prop-inline-actions');p.append(actions);viewButton(actions,'Inspect evaluation & costs','evaluation');viewButton(actions,`Why ${s.micros} MNQ? Compare sizes`,'sizing');
    }else{
      const p=reportBlock(views.overview,'Funded outcomes are unavailable',c.unavailable||'The saved analysis does not contain funded-account results.');
      p.classList.add('prop-unavailable');p.append(el('p','A failed evaluation path is a simulation outcome, not an application error. No acquisition cost or funded payout is substituted.'));
      facts(p,[['Evaluation pass rate',percent(e.pass_rate)],['Evaluation size',`${e.selected_micros} MNQ`],['Source net P&L',money(source.reconciliation.source_totals.net_pnl)]]);
      viewButton(p,'Inspect evaluation outcomes','evaluation');
    }

    let p=reportBlock(views.evaluation,'Can the strategy reach funded status?',`${e.selected_micros} MNQ · ${number(e.simulations)} evaluation paths · holdout ${dateRange(c.samples.validation)}.`);
    const evalCards=el('div',undefined,'prop-metric-grid prop-three-metrics');p.append(evalCards);
    metricCard(evalCards,'Passes evaluation',percent(e.pass_rate),`${number(e.passed)} of ${number(e.simulations)} paths.`,e.pass_rate);
    metricCard(evalCards,'Average cost to get funded',money(e.cost_per_funded),'Across repeated evaluations, including activation.',e.cost_per_funded);
    metricCard(evalCards,'Average time to get funded',days(e.days_to_funded),'Failed attempts plus the activation day.',e.days_to_funded);
    probabilityRows(p,[['Pass',e.pass_rate,''],['Fails drawdown',e.fail_drawdown,'prop-risk'],['Deadline reached',e.timeout,'prop-neutral']]);
    p.append(el('p',`95% simulation interval for the pass rate: ${e.pass_rate_ci.map(percent).join(' – ')}. This describes sampling uncertainty within the model.`, 'prop-explainer'));
    p=reportBlock(views.evaluation,'Acquisition cost and timing','The pass-rate estimate determines the expected number of paid evaluations.');
    facts(p,[['One evaluation',money(r.settings.EVAL_PRICE)],['Activation fee',money(r.settings.ACTIVATION_FEE)],['Evaluations per funded account',number(e.evaluations_per_funded,2)],['Median time to funded',days(e.days_to_funded_median)],['Median time to pass',days(e.median_days_to_pass),'Among successful evaluation attempts.']]);
    explanation(p,'How is acquisition cost calculated?',available(e.cost_per_funded)?`${money(r.settings.EVAL_PRICE)} evaluation fee ÷ ${percent(e.pass_rate)} pass rate + ${money(r.settings.ACTIVATION_FEE)} activation fee = approximately ${money(e.cost_per_funded)}. Calculations use the unrounded saved pass rate.`:'No evaluation passed, so a finite acquisition cost and replacement time are unavailable.');
    const evalDetails=el('details',undefined,'prop-help');evalDetails.append(el('summary','Evaluation sizes tried on training days'));p.append(evalDetails);
    readableTable(evalDetails,c.evaluation_sweep,[{key:'micros',label:'Size',format:v=>`${v} MNQ`},{key:'passed',label:'Passed paths',format:number,numeric:true},{key:'simulations',label:'Paths simulated',format:number,numeric:true}],{caption:'Training evaluation size sweep',selected:row=>row.micros===e.selected_micros});
    details(p,'Full-precision evaluation metrics',e);
    if(c.training_economics){
      const t=c.training_economics;p=reportBlock(views.evaluation,'Training calibration used for selection','Estimated before holdout testing; the holdout figures above do not choose or rescore the funded size.');
      facts(p,[['Training evaluation size',`${t.evaluation_micros} MNQ`],['Training pass rate',percent(t.pass_rate)],['Training acquisition cost',money(t.cost_per_funded)],['Training replacement time',days(t.replacement_days)]]);
      if(t.reason)p.append(el('p',t.reason,'prop-assumption-note'));
      details(p,'Training calibration and sample identity',t);fileLink(p,'training_economics.json','Download training calibration (JSON)');
    }


    if(f){
      p=reportBlock(views.sizing,`Why was ${s.micros} MNQ selected?`,'The highest estimated annual net per slot on training days selects the funded size. It is then tested on separate holdout days.');
      facts(p,[['Chosen funded size',`${s.micros} MNQ`],['Training window',dateRange(c.samples.train)],['Simulations per size',number(f.sweep[0]?.sims)]],'prop-facts-inline');
      if(f.search_range){const g=f.search_range;p.append(el('p',`Tried every size from ${g.min_micros} to ${g.max_micros} MNQ in increments of ${g.step}. Funded scaling limits actual orders to 20, 30 or 40 MNQ from the prior closing balance. ${g.selected_at_limit ? 'The selected size is at the search limit; no size above the permitted or user cap was tested.' : ''}`,'prop-assumption-note'));}
      const assumptions=f.selection_economics;
      if(assumptions?.method==='training_simulation'){
        facts(p,[['Training evaluation pass rate',percent(assumptions.pass_rate)],['Training acquisition cost',money(assumptions.cost_per_funded)],['Training replacement time',days(assumptions.replacement_days)]],'prop-facts-inline');
        p.append(el('p',`Funded sizing uses training-derived acquisition economics at ${assumptions.evaluation_micros} MNQ: ${percent(assumptions.pass_rate)} evaluation pass rate, ${number(assumptions.replacement_days,2)} replacement trading days including activation, and ${money(assumptions.cost_per_funded)} per funded account. Frozen before holdout testing; Evaluation shows separate holdout estimates.`, 'prop-assumption-note'));
        details(p,'Inspect training calibration, samples and seeds',assumptions);
      }else if(assumptions)p.append(el('p',`Training selection assumes a ${percent(assumptions.pass_rate)} evaluation pass rate and ${number(assumptions.replacement_days)} replacement trading days. Acquisition figures in Evaluation use the holdout evaluation simulation.`, 'prop-assumption-note'));
      const control=el('div',undefined,'prop-table-control'),label=el('label','Sort sizes by'),sort=el('select');sort.id='prop-sweep-sort';label.htmlFor=sort.id;
      for(const [value,text] of [['slot_year','Annual net per slot · highest first'],['micros','Size · smallest first'],['E[payout]','Average lifetime payout · highest first'],['blown','Drawdown failure · lowest first']]){const option=el('option',text);option.value=value;sort.append(option);}
      control.append(label,sort);p.append(control);const target=el('div');p.append(target);
      function drawSweep(){
        const rows=[...f.sweep].sort((a,b)=>['micros','blown'].includes(sort.value)?a[sort.value]-b[sort.value]:b[sort.value]-a[sort.value]);target.replaceChildren();
        readableTable(target,rows,[{key:'micros',label:'Size',render:(v)=>{const cell=el('span',`${v} MNQ`);if(v===s.micros)cell.append(el('span','Selected','prop-selected-badge'));return cell;}},{key:'slot_year',label:'Annual net / slot',format:money,numeric:true,tone:true},{key:'E[payout]',label:'Avg. lifetime payout',format:money,numeric:true},{key:'P(>=1 payout)',label:'Any payout',format:percent,numeric:true},{key:'blown',label:'Drawdown failure',format:percent,numeric:true},{key:'days alive',label:'Avg. lifetime · days',format:v=>number(v,1),numeric:true}],{caption:'Training funded size comparison',selected:row=>row.micros===s.micros});
      }
      sort.addEventListener('change',drawSweep);drawSweep();
      p.append(el('p',assumptions?.method==='training_simulation'?'All rows use training-derived acquisition cost and replacement time. Annual net / slot is an annualized renewal estimate, not the lifetime payout of one account.':'All rows are training estimates. “Annual net / slot” includes the fixed acquisition assumptions and replacement delay; it is not the lifetime payout of one account.','prop-explainer'));
      fileLink(p,'funded_sizing.csv','Download all sizing metrics (CSV)');
      details(p,'All training metrics at full precision',f.sweep);
      details(p,`Full-precision holdout metrics at ${s.micros} MNQ`,s);

      p=reportBlock(views.history,'What did the slots earn in the observed history?',`${r.settings.SLOTS} slots taking the same trades · full history ${dateRange(c.samples.data)} · not an annual forecast.`);
      if(c.history.acquisition_economics?.source==='training')p.append(el('p','Historical acquisition costs and replacement delays use the frozen training calibration. Evaluation holdout estimates are reserved for validation.','prop-assumption-note'));
      const totals=c.history.totals,historyCards=el('div',undefined,'prop-metric-grid prop-three-metrics');p.append(historyCards);
      metricCard(historyCards,'Historical net',money(totals.net,0),'Total payouts minus acquisition costs, over the full history.',totals.net);
      metricCard(historyCards,'Total payouts',money(totals.payouts,0),'Across all historical slots.',totals.payouts);
      metricCard(historyCards,'Acquisition costs',money(totals.costs,0),`${number(totals.new_funded_accounts)} funded account starts across all slots.`,totals.costs);
      p.append(el('p','All slots share one strategy’s trade path; multiplying the slot count does not diversify it. Training years also supplied the sizing choice.','prop-assumption-note'));
      readableTable(p,c.history.years,[{key:'year',label:'Year'},{key:'out_of_sample_share',label:'Holdout share',format:percent,numeric:true},{key:'payouts',label:'Payouts',format:v=>money(v,0),numeric:true},{key:'costs',label:'Acquisition costs',format:v=>money(v,0),numeric:true},{key:'net',label:'Net',format:v=>money(v,0),numeric:true,tone:true},{key:'new_funded_accounts',label:'Funded starts',format:number,numeric:true}],{caption:'Historical cash by year for all slots'});
      p.append(el('p','A 0% holdout share means the year is entirely in the training sample. Partial first/last years are shown in the data window above. Quarterly rounding is applied before annual cash totals are added.','prop-explainer'));
      fileLink(p,'slots_year_by_year.csv','Download yearly cash (CSV)');fileLink(p,'slots_by_quarter.csv','Inspect quarter-by-quarter cash (CSV)');
      p=reportBlock(views.history,'Follow each historical account','A single slot’s chronological account trace. The cash totals above scale that shared trace to all slots.');
      const trace=el('details',undefined,'prop-help');trace.append(el('summary',`Inspect ${number(c.history.accounts.length)} ${c.history.accounts.length===1?'account lifecycle':'account lifecycles'} and payout dates`));p.append(trace);
      const outcome={blown:'Drawdown failure',inactive:'Closed for inactivity',paid_all:'All 6 payouts paid',open:'Open at end of data'};
      readableTable(trace,c.history.accounts,[{key:'account',label:'Account'},{key:'start',label:'Funded on'},{key:'end',label:'Ended on'},{key:'outcome',label:'Outcome',format:v=>outcome[v]||v},{key:'payouts',label:'Payouts',format:number,numeric:true},{key:'payout_days',label:'Payout dates',format:v=>v.length?v.join(', '):'No payouts'}],{caption:'Historical account lifecycles'});
      fileLink(p,'slot_accounts.csv','Download the account trace (CSV)');
    }

    p=reportBlock(views.model,'Source and sample checks','The backtest supplies trade identity, quantities, UTC fills and net costs.');
    facts(p,[['Source trades',number(source.reconciliation.source_count)],['Source net P&L',money(source.reconciliation.source_totals.net_pnl)],['Measured MAE',`${number(source.excursion_input.measured_mae_count)} trades`],['Held OHLC risk',`${number(source.excursion_input.native_ohlc_count||0)} trades`],['Training',`${dateRange(c.samples.train)} · ${number(c.samples.weekdays[0])} weekdays`],['Holdout',`${dateRange(c.samples.validation)} · ${number(c.samples.weekdays[1])} weekdays`]]);
    p.append(el('p',source.excursion_provenance,'prop-assumption-note'));
    explanation(p,'How are training, holdout and session days used?','Sizes are selected on the training sample; reported account simulations use the holdout sample. Entries are grouped by Chicago session date, with zero-trade weekdays retained. The historical replay includes both samples and is labelled separately.');
    details(p,'Source identity and exact cost reconciliation',source);
    p=reportBlock(views.model,'Read the model correctly','Saved statistics describe this versioned analytical model.');
    explanation(p,'Average payout, median payout and acquisition cost','The average includes all simulated funded accounts. The median describes the middle account; a $0 median means at least half receive $0. Payouts do not subtract evaluation and activation fees. Acquisition cost is shown separately, while historical net subtracts it.');
    explanation(p,'Drawdown failures can also receive payouts','Payout outcomes partition accounts by how many payouts they received. Drawdown failure describes how an account closed. An account can belong to a paid group and later fail its drawdown limit.');
    explanation(p,'Simulation and historical replay answer different questions','Simulation resamples historical days to estimate account outcomes. Historical replay follows the one observed sequence of trades. Slots share that sequence, and training years influenced the size choice.');
    explanation(p,'Model limits and missing excursions','Measured adverse excursions do not reveal the exact intratrade price path. New native reports use conservative held-OHLC bounds and observed opening/cost jumps; target-exit ordering can be ambiguous. Cross-session native inputs reject. Legacy sources without capture use a disclosed close-only fallback that may understate risk. The model supports one strategy with nonoverlapping positions; payouts, costs and delays are model estimates.');
    details(p,'Account rules',c.rules);details(p,'Resolved settings',r.settings);details(p,'Random streams and samples',{samples:c.samples,seeds:c.seeds});
    details(p,'Report identity and reproducibility',{id:r.id,created_at_utc:r.created_at_utc,model:r.model_version,application_commit:r.application_commit,implementation:r.implementation_sha256,runtime:r.runtime});
    p=reportBlock(views.model,'Downloads and full precision','Display values are rounded. The original saved values remain in the report data and exports.');
    const names={'calculations.json':'All calculated metrics (JSON)','training_economics.json':'Training acquisition calibration (JSON)','evaluation_sizing.csv':'Evaluation size sweep (CSV)','funded_sizing.csv':'Funded size sweep (CSV)','slot_accounts.csv':'Historical account trace (CSV)','slots_by_quarter.csv':'Quarterly cash (CSV)','slots_year_by_year.csv':'Yearly cash (CSV)','trades.csv':'Source trade reconciliation (CSV)','charts/data.json':'Saved chart values (JSON)','inputs/settings.json':'Run settings (JSON)','inputs/intratrade_risk.csv':'Captured OHLC risk bounds (CSV)'};
    for(const path of Object.keys(r.files).sort())fileLink(p,path,names[path]||(path.startsWith('charts/')?`Original ${path.split('/').pop().replace('.svg','')} chart (SVG)`:path.endsWith('.xlsx')?'Original measured-excursion export (XLSX)':path));
    selectView('overview');window.scrollTo(0,0);
  }
  async function watch(id,t){$('#prop-config').hidden=true;$('#prop-report').hidden=true;while(t===token){const j=await read(`/api/prop-analyses/${id}`);if(t!==token)return;$('#prop-status').textContent=`${j.status} · ${j.progress}`;if(['error','incompatible'].includes(j.status)){throw Error(j.error);}if(j.status==='complete'){const r=await read(`/api/prop-analyses/${id}/downloads/report.json`);if(t===token)render(r);return;}await new Promise(resolve=>setTimeout(resolve,700));}}
  async function navigate(){const t=++token;$('#prop-delete').hidden=true;$('#prop-delete-status').hidden=true;const match=location.hash.match(/^#backtests\/prop\/(new|job)\/([a-f0-9]{32})$/);const active=location.hash.startsWith('#backtests/prop/');$('#prop-screen').hidden=!active;if(!active)return;$('#datasets-screen').hidden=true;$('#backtests-screen').hidden=true;$('#current-screen').textContent='Prop analysis';document.title='Prop analysis · AlphaQuest';try{if(!match)throw Error('This legacy prop URL is retired. Open a completed backtest report to configure a local analysis.');if(match[1]==='new')await configure(match[2],t);else await watch(match[2],t);}catch(e){if(t===token)$('#prop-status').textContent=e.message;}}

  async function deleteProp(id,row){
    if(deletingReports.has(id)||!confirm(`Delete prop report ${id}?\n\nThis permanently removes this analysis and its downloads. Backtest reports, source datasets, saved optimization metrics and OOS budget usage are kept. This cannot be undone.`))return;
    deletingReports.add(id);const hash=location.hash,status=$('#prop-delete-status');status.hidden=false;status.textContent='Deleting selected prop report…';$('#prop-delete').disabled=true;if(row)row.querySelector('button').disabled=true;
    try{
      const response=await fetch(`/api/prop-analyses/${id}`,{method:'DELETE'});
      if(!response.ok&&response.status!==404){const error=await response.json();throw Error(error.detail||`HTTP ${response.status}`);}
      if(location.hash===hash){
        status.textContent='Prop report deleted. Backtests, datasets and OOS budget usage kept.';
        if(row)row.remove();else{const notice=document.querySelector('#strategy-delete-status')||document.querySelector('#backtest-delete-status');if(notice){notice.hidden=false;notice.textContent=status.textContent;}location.hash='#strategies';}
      }
    }catch(error){if(location.hash===hash)status.textContent=`Could not delete prop report: ${error.message}`;}
    finally{deletingReports.delete(id);$('#prop-delete').disabled=false;if(row?.isConnected)row.querySelector('button').disabled=false;}
  }
  window.addEventListener('hashchange',navigate);navigate();
})();
