"use strict";
(() => {
  const node=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
  function duration(seconds){
    if(seconds===null||seconds===undefined)return 'Estimating…';
    const minutes=Math.ceil(Math.max(0,seconds)/60);
    return minutes<60?`${minutes} min`:`${Math.floor(minutes/60)} h ${minutes%60} min`;
  }
  window.renderPropProgress=(parent,details,status)=>{
    parent.replaceChildren();if(!details||status!=='running')return;
    parent.className='prop-confidence-progress';
    const d=details,completed=Number(d.completed)||0,total=Number(d.total)||0;
    const native=d.stage==='native_execution',currentETA=!native||d.eta_basis==='completed-worker-paths-v1';
    parent.append(node('p',`${d.stage==='complementary_evidence'?'Complementary evidence':d.stage==='native_execution'?'Native account execution':d.stage==='saved_trade_execution'?'Saved-trade account simulation':d.stage==='native_preparation'?'Preparing native source · '+(d.preparation_stage||'').replaceAll('_',' '):'Historical confidence'} · ${d.sizing_label||d.micros+' MNQ'}${d.candidate_count?` · size ${d.candidate_index} of ${d.candidate_count}`:''}`));
    parent.append(node('p',`${completed.toLocaleString()} / ${total.toLocaleString()} ${d.unit||'resamples'} · ${total?(100*completed/total).toFixed(1):'0.0'}% for this size`));
    if(total){const bar=node('progress');bar.max=total;bar.value=completed;bar.setAttribute('aria-label','Calculation progress for current policy');parent.append(bar);}
    parent.append(node('p',`${d.active_workers} active / ${d.worker_count} workers · elapsed ${duration(d.elapsed_seconds)} · remaining for this size ${duration(currentETA?d.eta_seconds:null)}`));
    const explanation=native&&!currentETA
      ?'This job uses earlier batch progress. ETA is unavailable; individual-path updates apply after the server loads the new worker code.'
      :native&&d.eta_status!=='ready'&&d.eta_status!=='complete'
        ?(d.eta_status==='warming_up'?`Estimating after enough worker paths finish (${d.eta_sample_paths} / ${d.eta_minimum_paths} minimum). Startup and detailed evidence replay are excluded.`:'Preparing detailed evidence and workers. ETA starts after enough worker paths finish.')
        :'ETA is approximate and covers this size only.'+(native?' It uses completed worker paths, excluding startup and detailed evidence replay.':'');
    const note=node('small',explanation+' Every requested account path is retained; progress updates do not trigger calculations.');parent.append(note);
    if(d.reused_resamples)parent.append(node('p',`${Number(d.reused_resamples).toLocaleString()} completed resamples restored from a verified checkpoint.`));
    if(d.updated_at_utc)parent.append(node('p','Last update: '+new Date(d.updated_at_utc).toLocaleTimeString()));
  };
})();
