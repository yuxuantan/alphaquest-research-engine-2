"use strict";
(() => {
  const get=s=>document.querySelector(s);
  const mode=get('#sample-split-mode'), percent=get('#sample-is-percent');
  const inputs=[get('#backtest-from-date'),get('#backtest-to-date'),get('#sample-oos-start'),get('#sample-oos-end')];
  const status=get('#sample-status'),review=get('#sample-review');
  let pair='',dataset='',strategy='',version=0,ready=false,loading=false;
  const notify=()=>window.dispatchEvent(new Event('research-split-changed'));
  async function read(response){const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail||data));return data;}
  const bounds=plan=>`IS ${plan.is_start} → ${plan.is_end} (${plan.is_bars.toLocaleString()} bars); OOS ${plan.oos_start} → ${plan.oos_end} (${plan.oos_bars.toLocaleString()} bars). ${plan.source_timezone}.`;
  function showHistory(element,data){element.textContent=`OOS runs require manual selection from a completed IS report. No attempt limit.${data.legacy_reports?` This strategy/source has ${data.legacy_reports} legacy reports without a holdout declaration. Previously viewed data is not an untouched holdout.`:''}`;element.classList.remove('warning');element.setAttribute('role','status');}
  function payload(){return mode.value==='percentage'?{mode:'percentage',is_percent:Number(percent.value)}:{mode:'dates',...Object.fromEntries(['is_start','is_end','oos_start','oos_end'].map((key,i)=>[key,inputs[i].value]))};}
  function fields(){
    get('#sample-percent-fields').hidden=mode.value!=='percentage';get('#sample-date-fields').hidden=mode.value!=='dates';
    percent.required=mode.value==='percentage';percent.disabled=mode.value!=='percentage'||loading;
    for(const input of inputs){input.required=mode.value==='dates';input.disabled=mode.value!=='dates'||loading;}
    mode.disabled=loading;review.disabled=loading||!dataset||!strategy||!mode.value;
    get('#sample-oos-percent').value=percent.value===''?'':String(Number((100-Number(percent.value)).toFixed(2)));
  }
  function changed(){version++;ready=false;status.textContent='Review the IS/OOS split before running.';fields();notify();}
  mode.addEventListener('change',changed);percent.addEventListener('input',changed);for(const input of inputs)input.addEventListener('input',changed);
  async function configure(d,s,force=false){
    if(!force&&pair===d+'|'+s)return;
    pair=d+'|'+s;dataset=d;strategy=s;const token=++version;ready=false;loading=!!(d&&s);mode.value='';for(const input of inputs)input.value='';
    status.textContent=loading?'Loading saved declaration…':'Choose a dataset and strategy.';get('#sample-budget').textContent='';get('#sample-budget').classList.remove('warning');fields();notify();
    if(!loading)return;
    try{
      const data=await fetch(`/api/backtests/research-plan?${new URLSearchParams({dataset_id:d,strategy_id:s})}`,{cache:'no-store'}).then(read);
      if(token!==version)return;
      showHistory(get('#sample-budget'),data);
      if(data.plan){mode.value='dates';['is_start','is_end','oos_start','oos_end'].forEach((k,i)=>inputs[i].value=data.plan[k]);ready=true;status.textContent='Saved split; editable for a new IS run. '+bounds(data.plan);}
      else status.textContent='Choose a split method and review the declaration before running.';
    }catch(error){if(token===version)status.textContent='Could not load declaration: '+error.message;}
    finally{if(token===version){loading=false;fields();notify();}}
  }
  review.onclick=async()=>{
    const token=++version;ready=false;loading=true;status.textContent='Checking source dates and split…';fields();notify();
    try{
      const data=await fetch('/api/backtests/research-plan/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({dataset_id:dataset,strategy_id:strategy,sample_split:payload()})}).then(read);
      if(token!==version)return;
      ready=true;status.textContent=bounds(data.proposed_plan)+' Initial backtests and prop simulations use IS only.';showHistory(get('#sample-budget'),data);
    }catch(error){if(token===version)status.textContent='Split needs attention: '+error.message;}
    finally{if(token===version){loading=false;fields();notify();}}
  };
  window.researchSplit={configure,payload,ready:()=>ready&&!loading};
  fields();

  let selected=null,reportVersion=0,oosBusy=false,requestId=null;
  const run=get('#report-run-oos'),resultLink=get('#report-oos-result'),message=get('#report-oos-status');
  async function report(record){
    const token=++reportVersion;selected=record;requestId=null;run.hidden=true;resultLink.hidden=true;message.textContent='';
    const research=record.run_metadata.research;
    get('#report-oos-budget').textContent='';get('#report-oos-budget').classList.remove('warning');get('#report-oos-parameters').textContent='';
    get('#report-research-title').textContent=research?research.phase==='is'?'In-sample backtest':'Out-of-sample backtest':'Legacy backtest';
    get('#report-research-period').textContent=research?bounds(research.plan):'This report predates required IS/OOS declarations. Its data may already have been inspected; it does not establish an untouched holdout. Declare a split in a new IS backtest to use the controlled workflow.';
    if(!research)return;
    get('#report-oos-parameters').textContent='Selected parameters: '+Object.entries(record.run_metadata.strategy.parameters).map(([k,v])=>`${k}=${v}`).join(', ');
    const source=research.phase==='is'?record.id:research.parent_run_id;
    try{
      const data=await fetch(`/api/backtests/${record.id}/oos`,{cache:'no-store'}).then(read);if(token!==reportVersion)return;
      showHistory(get('#report-oos-budget'),data);
      run.hidden=research.phase!=='is';run.disabled=oosBusy;
      const saved=data.attempts.filter(a=>a.parent_run_id===source&&a.status==='complete'&&a.report_available).at(-1);
      if(saved){resultLink.href=`#backtests/report/${saved.run_id}`;resultLink.hidden=false;}
    }catch(error){if(token===reportVersion)message.textContent='Could not load OOS history: '+error.message;}
  }
  window.addEventListener('report-loaded',event=>{void report(event.detail);if(event.detail.run_metadata.research&&dataset===event.detail.run_metadata.dataset.id&&strategy===event.detail.run_metadata.strategy.id)void configure(dataset,strategy,true);});
  run.onclick=async()=>{
    if(oosBusy||!selected)return;
    const record=selected,token=reportVersion;
    if(!requestId){
      if(!confirm('Run OOS backtest and automatic Apex 50K EOD + LucidFlex 50K prop analyses with this completed IS report’s saved split, parameters and execution costs? To use a different split or settings, run a new IS backtest first.'))return;
      requestId=crypto.randomUUID();
    }
    oosBusy=true;run.disabled=true;message.textContent='Running the manually selected OOS backtest and prop simulation.';
    const operation=crypto.randomUUID(),began=performance.now();let stopped=false,timer;
    async function poll(){
      try{const response=await fetch(`/api/progress/${operation}`,{cache:'no-store'});if(response.ok){const p=await response.json();if(token===reportVersion&&!stopped)message.textContent=`OOS · ${p.stage} · ${p.bars_processed.toLocaleString()} / ${p.total_bars.toLocaleString()} bars · ${Math.round((performance.now()-began)/1000)}s elapsed`;}}catch{}
      if(!stopped)timer=setTimeout(poll,700);
    }
    void poll();
    try{
      const response=await fetch(`/api/backtests/${record.id}/oos?progress_id=${operation}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({request_id:requestId})});
      const data=await read(response);
      if(token!==reportVersion)return;
      if(response.status===202){message.textContent='This OOS request is already running. Reload this IS report later to open its saved result.';return;}
      location.hash=`backtests/report/${data.id}`;
    }catch(error){if(token===reportVersion){message.textContent='OOS request: '+error.message+'. Reload the report to check saved attempts. A network retry of this button reuses the same request ID.';}}
    finally{stopped=true;clearTimeout(timer);oosBusy=false;if(token===reportVersion){run.disabled=false;const currentMessage=message.textContent,retryId=requestId;await report(record);requestId=retryId;message.textContent=currentMessage;}else if(selected)await report(selected);}
  };
})();
