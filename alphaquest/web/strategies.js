"use strict";

(() => {
  const get = selector => document.querySelector(selector);
  const make = (tag,text,cls) => { const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n; };
  const number=new Intl.NumberFormat('en-US',{maximumFractionDigits:2});
  let groupOffset=0,reportOffset=0,groupId=null,generation=0,controller;
  const read=async (url,signal) => {
    const response=await fetch(url,{cache:'no-store',signal});const result=await response.json();
    if(!response.ok)throw new Error(typeof result.detail==='string'?result.detail:`HTTP ${response.status}`);
    return result;
  };
  const money=value=>value==null?'N/A':number.format(Number(value));
  const groupRoute=()=>location.hash.match(/^#strategies\/([0-9a-f]{64})$/)?.[1]||null;
  async function groups() {
    const current=generation;
    get('#strategies-status').textContent='Loading instruments…';
    get('#strategy-groups-previous').disabled=get('#strategy-groups-next').disabled=true;
    try {
      const page=await read(`/api/strategies/groups?${new URLSearchParams({offset:groupOffset,limit:50})}`,controller.signal);
      if(current!==generation)return;
      if(groupOffset>=page.total&&groupOffset){groupOffset=0;return groups();}
      const list=get('#strategy-groups');list.replaceChildren();
      for(const group of page.items){
        const row=make('tr'),instrument=make('td'),link=make('a',group.instrument,'instrument-link');
        link.href=`#strategies/${group.id}`;link.setAttribute('aria-current',group.id===groupId?'true':'false');
        row.dataset.groupId=group.id;if(group.id===groupId)row.className='selected-instrument';
        instrument.append(link);row.append(instrument,make('td',String(group.backtests)));list.append(row);
      }
      get('#strategies-status').textContent=page.total?'Select an instrument to see its backtests.':'No saved backtests yet. Run your first backtest to create an instrument group.';
      get('#strategy-groups-page').textContent=page.total?`${groupOffset+1}–${groupOffset+page.items.length} of ${page.total}`:'0 instruments';
      get('#strategy-groups-previous').disabled=groupOffset===0;
      get('#strategy-groups-next').disabled=groupOffset+page.items.length>=page.total;
    } catch(error){if(error.name!=='AbortError'&&current===generation)get('#strategies-status').textContent=`Could not load instruments: ${error.message}. Use Refresh.`;}
  }
  async function reports(){
    if(!groupId)return;
    const current=generation;get('#strategy-results-status').textContent='Loading backtests…';
    get('#strategy-results').replaceChildren();get('#strategy-results-wrap').hidden=true;
    get('#strategy-reports-previous').disabled=get('#strategy-reports-next').disabled=true;
    try {
      const page=await read(`/api/strategies/groups/${groupId}/backtests?${new URLSearchParams({offset:reportOffset,limit:25})}`,controller.signal);
      if(current!==generation)return;
      if(reportOffset>=page.total&&reportOffset){reportOffset=0;return reports();}
      get('#strategy-results-heading').textContent=`${page.group.instrument} · Backtests`;
      for(const record of page.items){
        const row=make('tr');row.dataset.runId=record.id;
        const strategy=make('td',record.strategy_id.replaceAll('_',' '));
        strategy.append(make('small',record.dataset_name,'field-help'));
        strategy.title=`Created ${record.created_at_utc} · ${record.id}`;
        const period=record.selection;const dates=make('td',`${(period.from_date||period.start_utc||'').slice(0,10)} → ${(period.to_date||period.end_utc||'').slice(0,10)}`);
        strategy.append(make('small',dates.textContent,'field-help'));
        strategy.append(make('small',period.source_timezone||'','field-help'));
        const net=make('td',money(record.metrics.total_net_pnl));net.title=record.metrics.total_net_pnl;
        net.className=Number(record.metrics.total_net_pnl)<0?'negative':'positive';
        net.append(make('small',`${record.metrics.trades_taken} trades`,'field-help'),make('small',`DD ${money(record.metrics.max_drawdown_amount)}`,'field-help'));
        const action=make('td'),open=make('a','↗','button secondary report-open-icon');
        open.href=`#backtests/report/${record.id}`;open.setAttribute('aria-label',`Open backtest report ${record.id}`);open.title='Open full backtest report';action.append(open);
        if(record.batch_id){const batch=make('a','Sweep','small');batch.href=`#optimizations/${record.batch_id}`;batch.title='Open this parameter sweep';action.append(batch);}
        row.append(strategy,net,make('td',money(record.historical_net)),action);
        get('#strategy-results').append(row);
      }
      get('#strategy-results-wrap').hidden=false;
      get('#strategy-results-status').textContent=`${page.total} saved backtests · P&L/drawdown in CU; Historical net in USD after prop acquisition fees. N/A means unavailable.`;
      get('#strategy-reports-page').textContent=page.total?`${reportOffset+1}–${reportOffset+page.items.length} of ${page.total}`:'0 backtests';
      get('#strategy-reports-previous').disabled=reportOffset===0;get('#strategy-reports-next').disabled=reportOffset+page.items.length>=page.total;
    } catch(error){if(error.name!=='AbortError'&&current===generation)get('#strategy-results-status').textContent=`Could not load backtests: ${error.message}. Use Refresh.`;}
  }
  function navigate(){
    ++generation;controller?.abort();controller=new AbortController();
    if(!location.hash.startsWith('#strategies'))return;
    groupId=groupRoute();reportOffset=0;
    get('#strategy-results').replaceChildren();get('#strategy-results-wrap').hidden=true;
    get('#strategy-results-heading').textContent='Backtests';
    get('#strategy-results-status').textContent='Select an instrument on the left to view saved backtests.';
    get('#strategy-reports-page').textContent='';get('#strategy-reports-previous').disabled=get('#strategy-reports-next').disabled=true;
    void groups();if(groupId)void reports();
  }
  get('#refresh-strategies').onclick=()=>{void groups();if(groupId)void reports();};
  get('#strategy-groups-previous').onclick=()=>{groupOffset=Math.max(0,groupOffset-50);void groups();};
  get('#strategy-groups-next').onclick=()=>{groupOffset+=50;void groups();};
  get('#strategy-reports-previous').onclick=()=>{reportOffset=Math.max(0,reportOffset-25);void reports();};
  get('#strategy-reports-next').onclick=()=>{reportOffset+=25;void reports();};
  window.addEventListener('hashchange',navigate);navigate();
})();
