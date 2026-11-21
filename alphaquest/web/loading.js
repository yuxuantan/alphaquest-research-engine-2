"use strict";
(() => {
  // Presentation only. Callers retain ownership of requests, errors and results.
  const states=new WeakMap(),regions=new WeakMap(),requests=new Set(),nativeFetch=window.fetch.bind(window);
  let timer;
  function updateNetwork(){
    clearTimeout(timer);
    const indicator=document.getElementById('portal-network-loading');if(!indicator)return;
    const pending=[...requests].some(r=>r.route===location.hash);
    if(!pending){indicator.hidden=true;return;}
    timer=setTimeout(()=>{
      const local=[...document.querySelectorAll('.portal-loading')].some(el=>el.getClientRects().length>0);
      indicator.hidden=local||![...requests].some(r=>r.route===location.hash);
    },200);
  }
  function begin(target,{label}={}){
    if(typeof target==='string')target=document.querySelector(target);
    if(!target)return ()=>{};
    const previous=states.get(target),original=previous?previous.original:target.getAttribute('aria-busy');
    const originalText=previous?previous.originalText:target.textContent;
    if(label!==undefined)target.textContent=label;
    const state={original,originalText};states.set(target,state);
    target.classList.add('portal-loading');target.setAttribute('aria-busy','true');
    const stop=()=>{
      if(states.get(target)!==state)return;
      states.delete(target);target.classList.remove('portal-loading');
      if(label!==undefined&&target.textContent===label)target.textContent=originalText;
      if(original===null)target.removeAttribute('aria-busy');else target.setAttribute('aria-busy',original);
      updateNetwork();
    };
    state.stop=stop;updateNetwork();return stop;
  }
  function clear(target){if(typeof target==='string')target=document.querySelector(target);if(target)states.get(target)?.stop();}
  function message(label='Loading…'){
    const p=document.createElement('p');p.textContent=label;p.setAttribute('role','status');p.setAttribute('aria-live','polite');begin(p);return p;
  }
  function region(host,label='Loading…'){
    const prior=regions.get(host),original=prior?prior.original:host.getAttribute('aria-busy'),p=message(label),state={original};
    regions.set(host,state);host.replaceChildren(p);host.setAttribute('aria-busy','true');
    return ()=>{clear(p);if(regions.get(host)!==state)return;regions.delete(host);if(original===null)host.removeAttribute('aria-busy');else host.setAttribute('aria-busy',original);};
  }

  async function fetch(...args){
    const request={route:location.hash};requests.add(request);updateNetwork();
    try{return await nativeFetch(...args);}finally{requests.delete(request);updateNetwork();}
  }
  window.addEventListener('hashchange',updateNetwork);
  window.portalLoading={begin,clear,message,region,fetch};
})();
