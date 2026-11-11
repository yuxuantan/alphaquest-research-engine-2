"use strict";
(() => {
  const get = s => document.querySelector(s);
  const node = (tag,text,cls) => { const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n; };
  const kinds = {mechanic_validation:'Mechanic validation',backtest_batch:'Backtest batch',backtest:'Saved backtest',prop_analysis:'Prop analysis'};
  const words = value => String(value || '').replaceAll('_',' ');
  const stamp = value => value ? new Date(value).toLocaleString(undefined,{timeZoneName:'short'}) : 'Not recorded';
  let generation=0,timer,offset=0,lastList='',lastListData='',lastDetailData='';
  const read = async (url,method='GET') => {
    const response=await fetch(url,{method,cache:'no-store'}), body=await response.json();
    if(!response.ok) throw Error(typeof body.detail==='string' ? body.detail : 'Could not load job history.');
    return body;
  };
  function link(parent,text,href) {const a=node('a',text,'workflow-inline-link');a.href=href;parent.append(a);return a;}
  function progress(job) {
    const p=job.progress;
    if(!p) return 'Progress not recorded';
    const known=p.completed!==null && p.completed!==undefined;
    return `${words(p.stage)}${known ? ` · ${p.completed.toLocaleString()}${p.total>0 ? ' / '+p.total.toLocaleString() : ''} ${p.unit || ''}` : ''}`;
  }
  function status(job) {
    const label=job.status==='complete'?'Completed':job.status==='cancelled'?(job.stop_requested_at_utc?'Stopped':'Cancelled'):job.status==='running'&&job.stop_requested_at_utc?'Stopping':words(job.status);
    const pill=node('span',label,'pill '+(job.status==='complete'?'success':'neutral'));
    if(['failed','interrupted'].includes(job.status))pill.classList.add('jobs-error-status');
    return pill;
  }
  function query() {return new URLSearchParams(location.hash.split('?')[1] || '');}
  function filters() {
    const params=new URLSearchParams({status:get('#jobs-filter-status').value,kind:get('#jobs-filter-kind').value});
    if(get('#jobs-search').value.trim())params.set('q',get('#jobs-search').value.trim());
    location.hash='#jobs?'+params;
  }
  async function stop(job) {
    if(!job.stop_url||job.stop_requested_at_utc)return;
    if(!window.confirm(job.status==='queued'?'Cancel this queued backtest job?':'Stop this running backtest at its next checkpoint? Completed reports will remain available.'))return;
    try {await read(job.stop_url,'POST');await refresh();}
    catch(error){const target=get('#jobs-detail-view').hidden?'#jobs-list-status':'#jobs-detail-status';get(target).textContent=error.message;}
  }
  function stopButton(parent,job) {
    if(!job.stop_url)return;
    const button=node('button',job.status==='queued'?'Cancel queued job':'Stop running job','button secondary');
    button.type='button';button.disabled=!!job.stop_requested_at_utc;
    if(button.disabled)button.textContent='Stop requested';
    button.onclick=()=>stop(job);parent.append(button);
  }
  async function refresh() {
    clearTimeout(timer);
    if(!/^#jobs(?:[/?]|$)/.test(location.hash))return;
    const attempt=++generation, detail=location.hash.match(/^#jobs\/([^/]+)\/([a-f0-9]{32})$/);
    get('#jobs-list-view').hidden=!!detail;get('#jobs-detail-view').hidden=!detail;
    try {
      if(detail) {
        const job=await read(`/api/jobs/${detail[1]}/${detail[2]}`);if(attempt!==generation)return;
        const signature=JSON.stringify(job);
        if(lastDetailData===signature && get('#jobs-detail-content').childElementCount){timer=setTimeout(refresh,1500);return;}
        lastDetailData=signature;
        const host=get('#jobs-detail-content');host.replaceChildren();
        get('#jobs-detail-status').textContent='';
        const panel=node('section',undefined,'panel jobs-detail-panel');
        panel.append(node('h2',kinds[job.kind]),status(job),node('p',`${words(job.strategy_id) || 'Saved strategy sources'} · ${job.dataset_name}`));
        const text=node('p',progress(job),'jobs-progress-text');text.id='job-progress';panel.append(text);
        const p=job.progress;
        if(p?.total>0 && p.completed!==null && p.completed!==undefined) {
          const bar=node('progress');bar.max=p.total;bar.value=Math.min(p.completed,p.total);bar.setAttribute('aria-label',`Job progress in ${p.unit}`);panel.append(bar);
        }
        const facts=node('dl',undefined,'backtest-run-details');
        for(const [label,value] of [['Job ID',job.id],['Recorded',stamp(job.recorded_at_utc)],['Started',stamp(job.started_at_utc)],['Finished',stamp(job.finished_at_utc)]]) {
          const item=node('div');item.append(node('dt',label),node('dd',value));facts.append(item);
        }
        panel.append(facts);
        if(job.kind==='mechanic_validation' && job.status==='complete') panel.append(node('p',job.review_status==='passed'?'Mechanics review confirmed by the user.':'Run completed. Mechanics review and phase confirmation are separate.'));
        if(job.error)panel.append(node('p',job.error,'mechanic-error'));
        const actions=node('div',undefined,'mechanic-downloads');job.links.forEach(item=>link(actions,item.label,item.href));stopButton(actions,job);panel.append(actions);
        host.append(panel);
      } else {
        const changed=lastList!==location.hash;
        if(changed){lastList=location.hash;offset=Number(query().get('offset') || 0);if(!Number.isSafeInteger(offset)||offset<0)offset=0;}
        const params=query(), filterStatus=params.get('status') || 'all', kind=params.get('kind') || 'all';
        if(changed){get('#jobs-filter-status').value=filterStatus;get('#jobs-filter-kind').value=kind;get('#jobs-search').value=params.get('q') || '';}
        const data=await read('/api/jobs?'+new URLSearchParams({status:filterStatus,kind,q:params.get('q') || '',offset,limit:25}));if(attempt!==generation)return;
        if(offset && !data.items.length && data.total){offset=Math.floor((data.total-1)/25)*25;refresh();return;}
        if(!data.total)offset=0;
        const signature=location.hash+offset+JSON.stringify(data);
        if(lastListData===signature){timer=setTimeout(refresh,1500);return;}
        lastListData=signature;
        const rows=get('#jobs-rows');rows.replaceChildren();
        for(const job of data.items) {
          const row=node('tr');row.dataset.jobId=job.id;row.dataset.jobKind=job.kind;
          const recorded=node('td');link(recorded,stamp(job.recorded_at_utc),job.href);
          const source=node('td');source.append(node('strong',kinds[job.kind]),node('div',words(job.strategy_id) || 'Saved strategy sources'),node('small',job.dataset_name));
          const state=node('td');state.append(status(job));
          const detail=node('td',progress(job));if(job.error)detail.append(node('small',job.error,'mechanic-error'));
          const actions=node('td');link(actions,job.status==='complete'?'View results':'View progress / details',job.href);stopButton(actions,job);
          row.append(recorded,source,state,detail,actions);rows.append(row);
        }
        get('#jobs-list-status').textContent=data.total ? `${data.total} matching ${data.total===1?'job':'jobs'} · updates automatically.` : 'No jobs match these filters. Start a validation or backtest from Campaigns.';
        get('#jobs-page').textContent=data.total?`${offset+1}–${offset+data.items.length} of ${data.total}`:'0 jobs';
        get('#jobs-previous').disabled=!offset;get('#jobs-next').disabled=offset+data.items.length>=data.total;
      }
    } catch(error) {
      if(attempt!==generation)return;
      lastListData=lastDetailData='';
      if(detail){get('#jobs-detail-content').replaceChildren();get('#jobs-detail-status').textContent=error.message;}
      else {get('#jobs-rows').replaceChildren();get('#jobs-list-status').textContent=error.message;get('#jobs-previous').disabled=get('#jobs-next').disabled=true;get('#jobs-page').textContent='';}
    }
    // Refresh even an empty list to discover jobs submitted in another tab.
    if(attempt===generation)timer=setTimeout(refresh,1500);
  }
  get('#jobs-filters').onsubmit=e=>{e.preventDefault();filters();};
  for(const id of ['status','kind'])get('#jobs-filter-'+id).onchange=filters;
  get('#jobs-refresh').onclick=refresh;
  get('#jobs-previous').onclick=()=>{offset=Math.max(0,offset-25);refresh();};
  get('#jobs-next').onclick=()=>{offset+=25;refresh();};
  window.addEventListener('hashchange',()=>{++generation;clearTimeout(timer);refresh();});refresh();
})();
