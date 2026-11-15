/* Explicit contract rolls are a dataset operation, before campaign selection. */
(() => {
  const form=document.querySelector('#upload-form');
  const details=document.createElement('details');details.className='panel tick-roll-box';
  details.innerHTML='<summary>Build a continuous tick dataset from contract files</summary><p class="small muted">Import each contract first using the same root instrument (e.g. NQ). Declare an ordered CME session roll schedule before inspecting results. Prices remain unadjusted; contracts are never mixed within a session.</p><label>Dataset name<input id="tick-roll-name" maxlength="120" placeholder="NQ · declared quarterly roll"></label><label>Root instrument<input id="tick-roll-symbol" value="NQ"></label><div id="tick-roll-rows"></div><button type="button" class="button secondary" id="tick-roll-add">Add contract range</button> <button type="button" class="button primary" id="tick-roll-save">Build tick dataset</button><p role="status" id="tick-roll-status"></p>';
  form.parentElement.append(details);
  const rows=details.querySelector('#tick-roll-rows'),status=details.querySelector('#tick-roll-status');
  let inventory=[];
  async function add(){
    try{
      inventory=(await (await fetch('/api/datasets')).json()).filter(x=>x.tick_data);
      if(!inventory.length){status.textContent='Import a trade tick contract file first.';return;}
      const row=document.createElement('div');row.className='fields';
      for(const [label,type] of [['Contract source','select'],['First CME session','date'],['Last CME session','date']]){
        const wrap=document.createElement('label');wrap.textContent=label;
        const input=document.createElement(type==='select'?'select':'input');if(type!=='select')input.type=type;
        if(type==='select')for(const ds of inventory){const option=document.createElement('option');option.value=ds.id;option.textContent=ds.name;input.append(option);}
        wrap.append(input);row.append(wrap);
      }
      const remove=document.createElement('button');remove.type='button';remove.className='button secondary';remove.textContent='Remove range';remove.onclick=()=>row.remove();row.append(remove);rows.append(row);
    }catch(e){status.textContent=e.message;}
  }
  details.querySelector('#tick-roll-add').onclick=add;
  details.querySelector('#tick-roll-save').onclick=async e=>{
    const button=e.currentTarget;button.disabled=true;status.textContent='Checking sources and building observed minutes…';
    try{
      const segments=[...rows.children].map(row=>({dataset_id:row.querySelector('select').value,first_session:row.querySelectorAll('input')[0].value,last_session:row.querySelectorAll('input')[1].value}));
      const response=await fetch('/api/datasets/ticks/compose',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:details.querySelector('#tick-roll-name').value,symbol:details.querySelector('#tick-roll-symbol').value.trim(),segments})});
      const result=await response.json();if(!response.ok)throw Error(typeof result.detail==='string'?result.detail:JSON.stringify(result.detail));
      status.textContent=`Saved ${result.name}: ${result.tick_data.records.toLocaleString()} trades. Available in campaign dataset selection.`;
      window.dispatchEvent(new Event('datasets-changed'));location.reload();
    }catch(error){status.textContent=error.message;}finally{button.disabled=false;}
  };
})();
