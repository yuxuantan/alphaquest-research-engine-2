/* Final-session reservations in the existing dataset details workflow. */
(() => {
  const node=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
  const uuid=()=>crypto.randomUUID().replaceAll('-','');
  async function api(path,body){const response=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),result=await response.json();if(!response.ok)throw Error(typeof result.detail==='string'?result.detail:JSON.stringify(result.detail));return result;}
  function field(parent,title,id,type='text'){const label=node('label',title),input=node('input');input.id=id;input.type=type;input.required=true;label.append(input);parent.append(label);return input;}
  function button(parent,title,id){const b=node('button',title);b.type='button';b.className='button secondary';b.id=id;parent.append(b);return b;}
  function accessEvidence(parent,access){
    parent.append(node('p',`Access evidence: ${access.status}. External declaration independently verified: no. Untouched-data certificate: no.`));
    const rows=[...(access.conflicts||[]).map(row=>({kind:'Prior access',...row})),...(access.unknowns||[]).map(row=>({kind:'Unknown lineage',...row}))];
    if(rows.length){const list=node('ul');for(const row of rows)list.append(node('li',`${row.kind} · ${row.origin||row.event_kind||row.kind} · ${row.sessions?.join(', ')||row.window?.first_session||'Saved access evidence'} · ${row.id||row.sequence||''}`));parent.append(list);}
    if(access.status!=='ELIGIBLE_UNDER_DECLARED_LOCAL_SCOPE')parent.append(node('p','A protected reservation does not repair missing or conflicting access history. Final untouched verification remains blocked until the server can establish eligible evidence.'));
  }
  async function configure(parent,dataset){
    const section=node('details');section.id='dataset-research-reservations';section.append(node('summary','Final research holdout reservations'));parent.append(section);
    section.append(node('p','Reserve a contiguous range of observed CME session dates before strategy execution or price inspection. Dates follow the 17:00 America/Chicago session boundary. Reservation protects data from ordinary access; it does not prove an edge or certify external access history.'));
    const history=node('div');history.id='dataset-reservation-history';section.append(history);
    const form=node('form');form.id='dataset-reservation-form';section.append(form);form.onsubmit=event=>event.preventDefault();
    const fields=node('div');fields.className='prop-fields';form.append(fields);
    const first=field(fields,'First final session · inclusive','dataset-reservation-first','date'),last=field(fields,'Last final session · inclusive','dataset-reservation-last','date');
    const market=field(fields,'Market domain','dataset-reservation-domain');market.value='CME:NASDAQ100';market.readOnly=true;
    const label=node('label','Access outside this AlphaQuest library'),external=node('select');external.id='dataset-reservation-external';
    for(const [value,title]of [['unknown','Unknown / cannot attest'],['declared_not_inspected','I declare these final sessions were not inspected'],['inspected','These final sessions were already inspected']]){const option=node('option',title);option.value=value;external.append(option);}label.append(external);fields.append(label);
    const preview=button(form,'Check reservation range','dataset-reservation-preview'),reserve=button(form,'Reserve checked session range','dataset-reservation-save');reserve.disabled=true;
    const status=node('p');status.id='dataset-reservation-status';status.setAttribute('role','status');form.append(status);
    const evidence=node('div');evidence.id='dataset-reservation-evidence';form.append(evidence);
    let checked=null,revision=0,busy=false;
    const invalidate=()=>{revision++;checked=null;reserve.disabled=true;status.textContent='Dates or access declaration changed. Check the range again.';};form.addEventListener('input',invalidate);form.addEventListener('change',invalidate);
    async function refresh(){
      const saved=await api(`/api/datasets/${dataset.id}/research-reservations`);if(!section.isConnected)return;history.replaceChildren();
      if(!saved.items.length)history.append(node('p','No final sessions are reserved for this dataset.'));
      for(const row of saved.items){const item=node('details');item.append(node('summary',`${row.status} · ${row.sessions[0]} → ${row.sessions.at(-1)} · ${row.sessions.length} sessions`));item.append(node('p',`Reservation ${row.id}`));accessEvidence(item,row.access_at_reservation);
        if(['RESERVED','BOUND'].includes(row.status)){const releaseForm=node('form');releaseForm.onsubmit=event=>event.preventDefault();item.append(releaseForm);releaseForm.append(node('p','Releasing permits ordinary price access. Prior accesses remain recorded and cannot later be relabeled untouched. A bound procedure keeps its original evidence.'));
          const reason=field(releaseForm,'Reason for releasing this reservation','dataset-reservation-release-reason-'+row.id);reason.maxLength=1000;
          const release=button(releaseForm,'Release protected session range','dataset-reservation-release-'+row.id),result=node('p');result.setAttribute('role','status');releaseForm.append(result);
          release.onclick=async()=>{if(!releaseForm.reportValidity())return;release.disabled=true;try{await api(`/api/datasets/${dataset.id}/research-reservations/${row.id}/release`,{request_id:uuid(),reason:reason.value.trim()});await refresh();}catch(error){result.textContent=error.message;release.disabled=false;}};
        }history.append(item);
      }
    }
    preview.onclick=async()=>{if(busy||!form.reportValidity())return;const version=revision;busy=true;preview.disabled=true;reserve.disabled=true;status.textContent='Checking observed session labels and recorded access…';
      try{const body={request_id:uuid(),first_session:first.value,last_session:last.value,market_domain:market.value,external_access:external.value},result=await api(`/api/datasets/${dataset.id}/research-reservations/preview`,body);if(version!==revision||!section.isConnected)return;checked=body;evidence.replaceChildren(node('p',`${result.proposed_sessions.length} complete observed session labels: ${result.proposed_sessions[0]} → ${result.proposed_sessions.at(-1)}.`));accessEvidence(evidence,result.access);reserve.disabled=false;status.textContent='Range checked. Reserving protects these sessions; eligibility remains exactly as reported.';}
      catch(error){status.textContent=error.message;checked=null;}finally{busy=false;preview.disabled=false;}};
    reserve.onclick=async()=>{if(busy||!checked)return;busy=true;reserve.disabled=true;try{const result=await api(`/api/datasets/${dataset.id}/research-reservations`,checked);status.textContent=`${result.status} · ${result.id}. Use this reservation when freezing the complete evaluated research procedure.`;checked=null;await refresh();}catch(error){status.textContent=error.message;}finally{busy=false;}};
    try{await refresh();}catch(error){history.textContent='Reservation history unavailable: '+error.message;}
  }
  window.researchReservations={configure,accessEvidence};
})();
