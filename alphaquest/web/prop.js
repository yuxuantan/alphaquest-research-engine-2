/* Existing portal report → configuration → durable notebook report. */
(() => {
  const $ = s => document.querySelector(s);
  let sourceId, checked = false, busy = false, token = 0;
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
    rows.forEach(r=>{const tr=el('tr');columns.forEach(k=>tr.append(el('td',display(r[k]))));body.append(tr);});wrap.append(t);parent.append(wrap);
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
  function histogram(parent,title,h) {if(!h)return;chart(parent,title,[{name:'frequency',values:h.counts}],h.edges.map(String));details(parent,`${title}: inspect bins`,h);}
  function payload() {
    const overrides=JSON.parse($('#prop-overrides').value||'{}');
    overrides.PROP_MC_SIMS=Number($('#prop-sims').value);overrides.NUM_CONTRACTS=Number($('#prop-size').value);overrides.ENGINE=$('#prop-engine').value;
    return {source_backtest_id:sourceId,overrides,preset:$('#prop-preset').value,pricing:$('#prop-pricing').value,increment:Number($('#prop-increment').value)};
  }
  function setBusy(v){busy=v;$('#prop-check').disabled=v;$('#prop-run').disabled=v||!checked;$('#prop-form').querySelectorAll('input,select,textarea').forEach(n=>n.disabled=v);}
  function invalidate(){checked=false;$('#prop-check-output').replaceChildren();$('#prop-run').disabled=true;$('#prop-status').textContent='Settings changed. Check source costs and filtering before running.';}
  $('#prop-form').addEventListener('input',invalidate);
  $('#prop-check').addEventListener('click',async()=>{try{setBusy(true);const data=await post('/api/prop-analyses/check',payload());checked=true;const p=$('#prop-check-output');p.replaceChildren(el('h3','Source check passed'));metrics(p,{requested_engine:data.requested_engine,effective_engine:data.effective_engine,...data.source.reconciliation});details(p,'Cost reconciliation, excluded trades and provenance',data.source);details(p,'Every resolved setting and override origin',data);$('#prop-status').textContent='Source arithmetic reconciled. Ready to run.';}catch(e){checked=false;$('#prop-status').textContent=e.message;}finally{setBusy(false);}});
  $('#prop-form').addEventListener('submit',async e=>{e.preventDefault();if(busy||!checked)return;try{setBusy(true);const job=await post('/api/prop-analyses',payload());location.hash=`#backtests/prop/job/${job.id}`;}catch(e){$('#prop-status').textContent=e.message;setBusy(false);}});
  async function configure(id,t) {
    sourceId=id;checked=false;$('#prop-config').hidden=false;$('#prop-report').hidden=true;
    const [data,defaults]=await Promise.all([read(`/api/prop-analyses/sources/${id}`),read('/api/prop-analyses/defaults')]);if(t!==token)return;
    $('#prop-back').href=`#backtests/report/${id}`;$('#prop-source').textContent=`${data.source.run_metadata.strategy.id} · ${data.source.run_metadata.dataset.name} · ${data.source.summary.trades_taken} saved trades · ${id}`;
    $('#prop-form').reset();$('#prop-overrides').value='{}';$('#prop-sims').value=defaults.defaults.PROP_MC_SIMS;$('#prop-size').value=defaults.defaults.NUM_CONTRACTS;
    $('#prop-increment').replaceChildren();const names=['Main evaluation','Evaluation + sizing and attempts','Through funded first payout','Complete lifetime and economics'];for(let i=1;i<=defaults.available_increment;i++){const o=el('option',names[i-1]);o.value=i;$('#prop-increment').append(o);}$('#prop-increment').value=defaults.available_increment;
    $('#prop-saved').replaceChildren();for(const a of data.analyses){const link=el('a',`${a.created} · ${a.status} · ${a.id}`);link.href=`#backtests/prop/job/${a.id}`;$('#prop-saved').append(link,el('br'));}
    $('#prop-check-output').replaceChildren();$('#prop-defaults').textContent=JSON.stringify(defaults.defaults,null,2);$('#prop-status').textContent='Configure analytical settings, then check source. Full bar coverage and MAE are not required.';setBusy(false);
  }
  function render(r) {
    $('#prop-config').hidden=true;$('#prop-report').hidden=false;$('#prop-report-content').replaceChildren();$('#prop-back').href=`#backtests/report/${r.source.backtest.id}`;
    $('#prop-status').textContent=`Saved analysis ${r.id} · ${r.created_at_utc} · increment ${r.increment}. Reload reads saved results.`;
    const links=$('#prop-downloads');links.replaceChildren();for(const kind of ['report.json','trades.csv','daily.csv','analysis.zip']){const a=el('a',kind+' ↓','button secondary');a.href=`/api/prop-analyses/${r.id}/downloads/${kind}`;links.append(a);}
    let p=section('Source, costs and trade statistics');metrics(p,r.statistics);metrics(p,r.engine);details(p,'Source cost arithmetic and filtering',r.source);details(p,'Bootstrap confidence intervals',r.statistics);
    p=section('Evaluation Monte Carlo');metrics(p,r.evaluation);details(p,'Pass probability interval and full metrics',r.evaluation);table(p,['passed','fail_dd','fail_daily','fail_time'].map(outcome=>({outcome,count:r.evaluation[outcome]})));histogram(p,'Days to pass',r.charts.days_to_pass);histogram(p,'Maximum drawdown',r.charts.drawdown);
    p=section('Saved equity path samples');chart(p,'Evaluation profit paths',r.paths.equity.map((values,i)=>({values,color:{pass:'#14734b',fail_dd:'#ad2929',fail_time:'#999'}[r.paths.outcomes[i]]})));metrics(p,{sample:r.paths.sample,seed:r.paths.seed,retained_paths:r.paths.equity.length});details(p,'Inspect saved path values and outcomes',r.paths);
    p=section('Weekday dataset');metrics(p,{weekdays:r.daily.length,zero_trade_weekdays:r.daily.filter(d=>d.n_trades===0).length});table(p,r.daily.slice(0,20));p.append(el('p','First 20 weekdays; complete grid and ordered trades are in CSV downloads.'));
    if(r.sizing){p=section('Evaluation sizing and staged sizing');table(p,r.sizing.sweep);metrics(p,r.sizing.selected);metrics(p,r.sizing.validation);table(p,r.sizing.staged);details(p,'Sample switching and staged comparison',r.sizing);p.append(el('p','Staged sizing uses the validation sample and omits DLL. Notebook CI tie language and selection behavior are preserved.'));chart(p,'Evaluation pass rate by size',[{name:'train pass rate',values:r.sizing.sweep.map(v=>v.pr)}],r.sizing.sweep.map(v=>String(v.nc)));p=section('Repeated attempts');table(p,r.attempts.independent);table(p,r.attempts.correlated);details(p,'Attempt assumptions and budget',r.attempts);}
    if(r.funded){p=section('Funded first payout');metrics(p,r.funded.detail);table(p,r.funded.sweep);details(p,'Selected funded size and full saved metrics',r.funded);chart(p,'Expected first payout by size',[{name:'expected payout',values:r.funded.sweep.map(v=>v.expected_payout)},{name:'net EV',values:r.funded.sweep.map(v=>v.net_ev)}],r.funded.sweep.map(v=>String(v.n_contracts)));histogram(p,'First payout distribution',r.charts.first_payout);histogram(p,'Time to qualify',r.charts.qualifying_days);p.append(el('p','Selection uses the holdout again. If no size meets the blown ceiling, the notebook selects from all sizes. Horizon outcomes are still-open simulations.'));}
    if(r.lifetime){p=section('Lifetime extraction and account survival');metrics(p,r.lifetime.selected);table(p,r.lifetime.sweep);histogram(p,'Lifetime extraction',r.charts.lifetime_total);histogram(p,'Payout counts',r.charts.payout_count);details(p,'Lifetime distributions and horizon disclosure',r.lifetime);p=section('Sizing funnel and economics');table(p,r.economics.funnel);metrics(p,r.economics);details(p,'Acquisition formula and recommendation',r.economics);p=section('Block-length robustness');table(p,r.robustness);}
    p=section('Versioned model assumptions and reproducibility');p.append(el('p','Analytical notebook model; no current provider-rule certification. Fractional minis and micro equivalents are scaling labels. Known behavior: holdout reused for downstream selections; staged DLL omitted; daily evaluation differs; exact-DLL clipping; weekday/inactivity approximations; selection fallbacks; acquisition and repeated-attempt shortcuts. Missing excursions are never measured MAE.'));
    details(p,'All resolved settings, literal notebook defaults and override origins',{settings:r.settings,literal_defaults:r.literal_notebook_defaults,origins:r.setting_origins,rules:r.rules});details(p,'Hashes, runtime and seed streams',{model:r.model_version,notebook:r.notebook_sha256,input:r.input_sha256,runtime:r.runtime,seeds:r.seed_streams,commit:r.application_commit,implementation:r.implementation_sha256,samples:r.samples});
  }
  async function watch(id,t){$('#prop-config').hidden=true;$('#prop-report').hidden=true;while(t===token){const j=await read(`/api/prop-analyses/${id}`);if(t!==token)return;$('#prop-status').textContent=`${j.status} · ${j.progress}`;if(j.status==='error'){throw Error(j.error);}if(j.status==='complete'){const r=await read(`/api/prop-analyses/${id}/downloads/report.json`);if(t===token)render(r);return;}await new Promise(resolve=>setTimeout(resolve,700));}}
  async function navigate(){const t=++token;const match=location.hash.match(/^#backtests\/prop\/(new|job)\/([a-f0-9]{32})$/);const active=location.hash.startsWith('#backtests/prop/');$('#prop-screen').hidden=!active;if(!active)return;$('#datasets-screen').hidden=true;$('#backtests-screen').hidden=true;$('#current-screen').textContent='Prop analysis';document.title='Prop analysis · AlphaQuest';try{if(!match)throw Error('This legacy prop URL is retired. Open a completed backtest report to configure a notebook analysis.');if(match[1]==='new')await configure(match[2],t);else await watch(match[2],t);}catch(e){if(t===token)$('#prop-status').textContent=e.message;}}
  window.addEventListener('hashchange',navigate);navigate();
})();
