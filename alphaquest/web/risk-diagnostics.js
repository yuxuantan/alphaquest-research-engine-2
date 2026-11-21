"use strict";
(() => {
  const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
  const value=v=>v===null||v===undefined?'Unavailable':new Intl.NumberFormat(undefined,{minimumFractionDigits:2,maximumFractionDigits:2}).format(Number(v));
  window.attachRiskDiagnostics=(parent,id,options={})=>{
    const box=node('details',undefined,'panel research-risk-diagnostics');box.append(node('summary','Risk-normalized research · diagnostics'));
    const content=node('div');box.append(content);parent.append(box);let loaded=false;
    box.addEventListener('toggle',async()=>{
      if(!box.open||loaded)return;loaded=true;content.replaceChildren(window.portalLoading.message('Checking saved initial-risk evidence…'));
      try{
        const response=await window.portalLoading.fetch(`/api/backtests/${id}/risk-diagnostics`);const data=await response.json();if(!response.ok)throw Error(data.detail||'Saved risk evidence is unavailable.');
        content.replaceChildren();const c=data.coverage,s=data.summary;
        content.append(node('p',`${c.valid_trades} / ${c.total_trades} trades have valid causal risk evidence · ${data.status}.`));
        content.append(node('p','Planned net R = actual net trade profit ÷ initial planned risk including declared trade costs. These diagnostics do not change campaign passing criteria.','field-help'));
        const settings=data.source.native_manifest.execution_settings,parameters=data.source.native_manifest.run_metadata.strategy?.parameters||{};
        content.append(node('p',`Commission per contract per side: ${settings.commission_per_contract_per_side}; entry and planned stop-exit slippage: ${settings.slippage_ticks} tick(s) each.`,'field-help'));
        content.append(node('p',`Point value: ${settings.point_value}; tick size: ${settings.tick_size}. Research baseline: ${parameters.use_vol_sizing?'strategy-local risk sizing':(parameters.position_size??parameters.contracts)!==undefined?(parameters.position_size??parameters.contracts)+' fixed contract(s)':'saved report quantity'}. Strategy-local sizing: ${parameters.use_vol_sizing?'enabled':'disabled'}.`,'field-help'));
        const metrics=node('p',`Mean ${value(s.mean_planned_net_r)}R · Median ${value(s.median_planned_net_r)}R · Total ${value(s.total_planned_net_r)}R · Worst ${value(s.worst_planned_net_r)}R`);content.append(metrics);
        if(!c.complete)content.append(node('p','Full-history R summaries are unavailable until every trade has valid evidence. Missing initial stops are never inferred. '+Object.entries(c.missing_reasons).map(([k,v])=>`${k.replaceAll('_',' ')}: ${v}`).join(' · '),'workflow-notice'));
        const net=data.source.native_manifest.summary?.total_net_pnl;
        if(c.complete&&net!==undefined&&Number(net)*Number(s.mean_planned_net_r)<0)content.append(node('p','Dollar profit and average planned net R have opposite signs. Review changes in initial risk across trades before choosing a sizing policy. This does not add a passing criterion.','workflow-notice'));
        if(data.complete_months.length){const months=node('details');months.append(node('summary','Complete-month risk diagnostics'));const monthly=node('table',undefined,'library-table');monthly.innerHTML='<thead><tr><th>Month</th><th>Trades</th><th>Valid risk</th><th>Mean net R</th><th>Total net R</th></tr></thead><tbody></tbody>';for(const m of data.complete_months){const r=node('tr');for(const v of [m.month,m.trades,m.valid_r_trades,value(m.mean_planned_net_r),value(m.total_planned_net_r)])r.append(node('td',String(v)));monthly.tBodies[0].append(r);}const scroll=node('div',undefined,'optimization-scroll');scroll.append(monthly);months.append(scroll);content.append(months);}
        const selected=options.tradeIds?data.trades.filter(t=>options.tradeIds.includes(String(t.trade_id))):data.trades;
        const scroll=node('div',undefined,'optimization-scroll'),table=node('table',undefined,'library-table');table.innerHTML='<thead><tr><th>Trade</th><th>Decision reference</th><th>Decision time (UTC)</th><th>Initial stop</th><th>Stop known at (UTC)</th><th>Filled quantity</th><th>Point value</th><th>Planned risk / contract</th><th>Total planned risk</th><th>Planned net R</th><th>Evidence</th></tr></thead><tbody></tbody>';
        for(const r of selected.slice(0,100)){const row=node('tr');for(const v of [r.trade_id,r.decision_reference_price??'Unavailable',r.sizing_decision_time_utc??'Unavailable',r.initial_stop_price??'Unavailable',r.initial_stop_known_at_utc??'Unavailable',r.quantity??'Unavailable',r.point_value??'Unavailable',value(r.planned_risk_per_contract),value(r.planned_total_risk),value(r.planned_net_r),r.available?(r.initial_stop_adverse_to_actual_fill?'Causal initial stop':'Fill beyond initial stop · inspect execution'):r.reason.replaceAll('_',' ')])row.append(node('td',String(v)));table.tBodies[0].append(row);}scroll.append(table);content.append(scroll);
        if(selected.length>100)content.append(node('p',`Showing 100 of ${selected.length} trades. Download retains all rows.`,'field-help'));
        const link=node('a','Risk diagnostics JSON ↓');link.href=`/api/backtests/${id}/exports/risk_metrics`;content.append(link);
      }catch(e){content.replaceChildren(node('p',e.message));loaded=false;}
    });return box;
  };
})();
