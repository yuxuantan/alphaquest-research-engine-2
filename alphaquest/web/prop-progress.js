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
    parent.append(node('p',`Historical confidence · ${d.micros} MNQ${d.candidate_count?` · size ${d.candidate_index} of ${d.candidate_count}`:''}`));
    parent.append(node('p',`${completed.toLocaleString()} / ${total.toLocaleString()} resamples · ${total?(100*completed/total).toFixed(1):'0.0'}% for this size`));
    if(total){const bar=node('progress');bar.max=total;bar.value=completed;bar.setAttribute('aria-label','Historical confidence resamples for current size');parent.append(bar);}
    parent.append(node('p',`${d.active_workers} active / ${d.worker_count} workers · elapsed ${duration(d.elapsed_seconds)} · remaining for this size ${duration(d.eta_seconds)}`));
    const note=node('small','ETA is approximate and covers this size only. Confidence checks retain every requested account path.');parent.append(note);
    if(d.reused_resamples)parent.append(node('p',`${Number(d.reused_resamples).toLocaleString()} completed resamples restored from a verified checkpoint.`));
    if(d.updated_at_utc)parent.append(node('p','Last update: '+new Date(d.updated_at_utc).toLocaleTimeString()));
  };
})();
