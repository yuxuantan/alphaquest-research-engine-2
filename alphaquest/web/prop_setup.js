/* Guided presentation over the existing prop/research forms and their owners. */
(() => {
  'use strict';
  const $ = selector => document.querySelector(selector);
  const node = (tag, text, cls) => { const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n; };
  const titles={research:'Find a robust strategy, size and account',compare:'Compare qualified candidates',inspect:'Inspect one strategy/account policy',legacy:'Legacy joint sizing',budget:'Budgeted cash ledger',pair:'Compare frozen phase pairs'};
  const hosts={research:'#prop-robust-research',compare:'#prop-campaigns',inspect:'#prop-native-replay',legacy:'#prop-form',budget:'#prop-form',pair:'#prop-pair-comparison'};
  const forms={research:'#robust-form',compare:'#campaign-form',inspect:'#native-form',legacy:'#prop-form',budget:'#prop-form',pair:'#pair-form'};
  const outer={research:'#robust-configure',compare:'#campaign-configure',inspect:'#native-configure',pair:'#pair-configure'};
  const buttons={research:['#robust-preview','#robust-run'],compare:['#campaign-check','#campaign-run'],inspect:['#native-check','#native-run'],legacy:['#prop-check','#prop-run'],budget:['#prop-check','#prop-run'],pair:['#pair-check','#pair-run']};
  let dispose=()=>{};
  function mark(element,step){if(element)element.dataset.setupStep=step;}
  function near(id){return $(id)?.closest('label');}
  function advanced(parent,title,items){
    const present=items.filter(Boolean);if(!present.length||present[0].closest('.setup-context-details'))return;
    const detail=node('details',undefined,'setup-context-details');mark(detail,present[0].dataset.setupStep||parent.dataset.setupStep||'accounts');detail.append(node('summary',title));parent.insertBefore(detail,present[0]);for(const item of present)detail.append(item);
  }
  function partition(goal){
    const form=$(forms[goal]);if(!form)return;
    if(goal==='research'){
      let step='sources';for(const child of form.children){
        if(child.tagName==='H3'&&child.textContent.startsWith('2.'))step='design';
        mark(child,step);
        if(child.id==='robust-economic-configure')mark(child,'accounts');
        if(child.classList.contains('robust-actions')||['robust-status','robust-plan'].includes(child.id))mark(child,'review');
        if(child.id==='robust-workspace-controls')mark(child,'sources design accounts review');
      }
      mark($('#robust-result'),'review');
      const h=$(hosts[goal]).querySelector('h2');if(h&&h.textContent!=='Test robustness across historical windows')h.textContent='Test robustness across historical windows';
      const economic=$('#robust-economic-configure');if(economic){if(economic.querySelector('summary').textContent!=='Evaluate prop-account outcomes')economic.querySelector('summary').textContent='Evaluate prop-account outcomes';}
      advanced($('#robust-mode')?.parentElement.parentElement,'Window buffers and minimum fold counts',['purge_sessions','embargo_sessions','minimum_inner_folds','minimum_outer_folds'].map(key=>near('#robust-'+key)));
      for(const input of form.querySelectorAll('select[id$="-execution"]'))label(input,'How should account behavior be simulated?');
    }else if(goal==='compare'){
      for(const child of form.children)mark(child,'accounts');
      const sourceBox=$('#campaign-sources');mark(sourceBox,'sources accounts');
      for(const row of sourceBox?.children||[]){
        for(const child of row.children)mark(child,'accounts');
        for(const selector of ['.campaign-kind','.campaign-source-search','.campaign-reference','.campaign-trials'])mark(row.querySelector(selector)?.closest('label'),'sources');
        for(const selector of ['.campaign-source-info','.campaign-source-more','.campaign-source-status'])mark(row.querySelector(selector),'sources');
        for(const b of row.querySelectorAll('button'))if(b.textContent==='Remove source')mark(b,'sources');
      }
      mark($('#campaign-add-source'),'sources');mark($('#campaign-new-evaluation')?.parentElement,'accounts');
      for(const id of ['#campaign-is-start','#campaign-is-end']){mark($(id)?.parentElement.parentElement,'sources accounts');mark(near(id),'sources');}
      for(const id of ['#campaign-window-status','#campaign-window-reset'])mark($(id),'sources');
      for(const id of ['#campaign-check','#campaign-run','#campaign-status','#campaign-count'])mark($(id),'review');for(const output of form.querySelectorAll('.campaign-checks'))mark(output,'review');
      // The shared grid contains dates and sampling: separate the controls without changing their form owner.
      const grid=near('#campaign-paths')?.parentElement;
      if(grid){for(const child of grid.children)if(!child.dataset.setupStep)mark(child,'accounts');
        advanced(grid,'Historical sampling and reproducible seeds',['#campaign-paths','#campaign-seed','#campaign-block','#campaign-start'].map(near));}
      const h=$(hosts[goal]).querySelector('h2');if(h&&h.textContent!=='Compare saved candidates for one prop phase')h.textContent='Compare saved candidates for one prop phase';
      label($('#campaign-phase'),'Which phase are you comparing?');label($('#campaign-execution'),'How should account behavior be simulated?');
    }else if(goal==='inspect'){
      for(const child of form.children)mark(child,child.tagName==='FIELDSET'?'sources accounts':'review');
      const fields=form.querySelector('fieldset');for(const child of fields?.children||[])mark(child,'accounts');
      for(const id of ['#native-first','#native-last'])mark(near(id),'sources');
      const h=$(hosts[goal]).querySelector('h2');if(h&&h.textContent!=='Inspect one strategy under account rules')h.textContent='Inspect one strategy under account rules';
      label($('#native-phase'),'Which phase are you inspecting?');
    }else if(goal==='pair'){
      for(const child of form.children)mark(child,'accounts');
      for(const id of ['#pair-check','#pair-run'])mark($(id)?.parentElement,'review');
      for(const child of form.children)if(child.getAttribute('role')==='status'||child.id==='pair-check-evidence')mark(child,'review');
    }else{
      for(const child of form.children)mark(child,'accounts');
      mark(form.querySelector('.prop-actions'),'review');mark($('#prop-check-output'),'review');
      const json=near('#prop-overrides');if(json&&!json.closest('.setup-expert-json')){const detail=node('details',undefined,'setup-expert-json');detail.append(node('summary','Expert model overrides · JSON'));json.before(detail);detail.append(json);}
    }
    for(const mode of form.querySelectorAll('select[class*="sizing-mode"]'))label(mode,'How should position size be determined?');
  }
  function label(input,text){if(input?.closest('label')?.firstChild?.nodeType===Node.TEXT_NODE&&input.closest('label').firstChild.textContent!==text)input.closest('label').firstChild.textContent=text;}
  function applicable(input){
    if(input.matches(':disabled')||input.type==='hidden')return false;
    for(let p=input;p&&p.id!=='prop-config';p=p.parentElement)if(p.hidden)return false;
    return true;
  }
  function value(input){return input.type==='checkbox'?(input.checked?'Yes':'No'):input.tagName==='SELECT'?(input.selectedOptions[0]?.textContent||'Not selected'):(input.value||'Not set');}
  function controlLabel(input){const wrapper=input.closest('label');if(!wrapper)return input.id||input.name||'Setting';return [...wrapper.childNodes].filter(n=>n!==input).map(n=>n.textContent).join(' ').trim()||input.id||'Setting';}
  async function mount({source,initializers,initialGoal=null,isCurrent=()=>true}){
    dispose();for(const history of document.querySelectorAll('[data-setup-task-history]'))history.remove();const abort=new AbortController();let observer=null;dispose=()=>{abort.abort();observer?.disconnect();};
    const signal=abort.signal,current=()=>!signal.aborted&&isCurrent();
    const root=$('#prop-config');for(const selector of new Set(Object.values(hosts)))if($(selector))root.append($(selector));if($('#prop-source-card'))root.append($('#prop-source-card'));$('#prop-setup')?.remove();root.classList.remove('setup-all-settings');root.classList.add('setup-guided');
    const shell=node('section',undefined,'prop-setup');shell.id='prop-setup';root.prepend(shell);
    const goalPicker=node('details');goalPicker.id='setup-goal-picker';goalPicker.open=true;const goalSummary=node('summary','Choose your research goal');goalPicker.append(goalSummary);shell.append(goalPicker);
    const intro=node('div');intro.append(node('h2','What do you want to find out?'),node('p','Choose a goal. We will show the sources, assumptions and checks needed for that task. Opening configuration does not start a calculation.'));goalPicker.append(intro);
    const goals=node('div',undefined,'setup-goals');goals.id='setup-goals';intro.append(goals);
    const external=source.run_metadata.source?.kind==='external_trade_export',isIS=source.run_metadata.research?.phase==='is';
    const symbol=source.run_metadata.instrument?.symbol||source.run_metadata.full_dataset?.symbol||source.run_metadata.dataset.symbol||'';
    const isMNQ=/^@?MNQ(?:[!#12]*|[FGHJKMNQUVXZ][0-9]{1,4})?(?:[. ]CME)?$/i.test(symbol);
    const nativeCandidate=!external&&isIS&&isMNQ&&source.run_metadata.strategy.id==='vwap_pullback_risk_sizing';
    const availability={research:!external&&isIS&&source.capabilities?.nested_research!==false,compare:isIS&&(!external||source.capabilities?.phase_selection===true),inspect:nativeCandidate};
    const explanations={research:'Test strategy robustness across historical windows, then evaluate eligible sizing and account policies.',compare:'Compare saved IS candidates for Evaluation cost/time or Funded trader receipts. This does not replace strategy qualification.',inspect:'Rerun one supported strategy with account-controlled sizing. This is one policy inspection, not a complete selection study.'};
    const reasons={research:external?'Imported trades cannot rerun a native strategy. Use an eligible phase comparison, or return to a native IS report.':'This task needs a declared native IS report.',compare:'This task needs an eligible declared IS source. Review source capabilities or return to an IS report.',inspect:'Account-controlled replay currently needs an IS MNQ VWAP strategy source. Complete one-minute coverage and strategy settings must still pass Check. Use an eligible source or explicitly choose another tool.'};
    const goalButtons=[];
    for(const key of ['research','compare','inspect']){
      const card=node('article',undefined,'setup-goal-card'),b=node('button',titles[key],'button secondary');b.type='button';b.id='setup-goal-'+key;b.setAttribute('aria-pressed','false');card.append(b,node('p',explanations[key]));
      if(key==='research')card.prepend(node('span','Recommended for full research','setup-recommended'));
      if(!availability[key]){b.disabled=true;card.append(node('p',reasons[key],'setup-limitation'));}
      b.onclick=()=>choose(key);goals.append(card);goalButtons.push(b);
    }
    const other=node('details');other.id='setup-other-tools';other.append(node('summary','Other analysis tools'));intro.append(other);
    other.append(node('p','Explicit alternatives with different meanings. Legacy joint reports keep their original calculations; they do not select independent phases.'));
    for(const key of ['legacy','budget','pair']){const b=node('button',titles[key],'button secondary');b.id='setup-goal-'+key;b.type='button';b.onclick=()=>choose(key);other.append(b);goalButtons.push(b);if(external&&key==='budget'){b.disabled=true;b.title='Budgeted lifecycle requires native phase sources.';}}
    const compatibilityDetails=node('details');compatibilityDetails.id='setup-compatibility-details';compatibilityDetails.open=true;compatibilityDetails.append(node('summary','Source compatibility and identity'));shell.append(compatibilityDetails);
    const compatibility=node('div',undefined,'setup-compatibility');compatibility.id='setup-source-compatibility';compatibilityDetails.append(compatibility);
    compatibility.append(node('h3','Source compatibility · preliminary'),node('p',`${source.run_metadata.strategy.id.replaceAll('_',' ')} · ${source.run_metadata.dataset.name} · ${source.run_metadata.research?.phase?.toUpperCase()||'Undeclared research phase'}`));
    compatibility.append(node('p',nativeCandidate?'Potential native account-controlled replay source. Complete sessions, causal risk, settings and costs are verified by the task check before running.':external?'Imported trade path: source declarations and risk coverage must be checked. Native strategy reruns are unavailable.':'Saved native backtest. Robustness/phase eligibility and scaling still require task checks; native account-controlled resizing is not established by this source alone.'));
    compatibility.append(node('p','Existing net P&L already includes saved costs. Planning costs affect quantity decisions; do not deduct the same trading costs twice.'));
    const workspace=node('div',undefined,'setup-workspace');workspace.hidden=true;shell.append(workspace);
    const main=node('div',undefined,'setup-main'),summaryPanel=node('details',undefined,'setup-summary'),aside=node('div');summaryPanel.id='setup-summary';summaryPanel.append(node('summary','Your study'),aside);summaryPanel.open=innerWidth>1100;const media=matchMedia('(max-width:1100px)');media.addEventListener('change',()=>{summaryPanel.open=!media.matches;},{signal});summaryPanel.setAttribute('aria-label','Your study summary');workspace.append(main,summaryPanel);
    const heading=node('h2');heading.id='setup-task-title';main.append(heading);
    const nav=node('nav',undefined,'setup-steps');nav.setAttribute('aria-label','Configuration steps');main.append(nav);
    const allLabel=node('label',undefined,'setup-show-all'),all=node('input');all.type='checkbox';all.id='setup-show-all';allLabel.append(all,node('span','Show all settings for this task'));main.append(allLabel);
    const message=node('p');message.id='setup-message';message.setAttribute('role','status');main.append(message);
    const stageHeading=node('h3');stageHeading.id='setup-stage-title';stageHeading.tabIndex=-1;main.append(stageHeading);
    const help=node('p');help.id='setup-stage-help';main.append(help);
    const content=node('div');content.id='setup-task-content';main.append(content);
    const qualification=node('label');qualification.id='setup-qualification-choice';const only=node('input');only.type='checkbox';only.id='setup-qualification-only';qualification.append(only,document.createTextNode(' Explicitly run strategy qualification only, without prop-account selection'));content.append(qualification);
    const review=node('section');review.id='setup-review';content.append(review);
    const footer=node('div',undefined,'setup-footer'),back=node('button','Back','button secondary'),next=node('button','Continue','button primary');back.type=next.type='button';back.id='setup-back';next.id='setup-next';footer.append(back,next);main.append(footer);
    const initialized=new Map(),listenerForms=new WeakSet();let goal=null,step='sources',loading=false,revision=0;
    const descriptions={sources:'Confirm the selected IS sources and their coverage. Add saved reports or grids only when needed.',design:'Declare historical windows, qualification requirements, execution stresses and references before looking at study outcomes.',accounts:'Choose Evaluation, Funded or both where supported. Review account rules, sizing, costs and risk limits. Each phase keeps its own objective.',review:'Review all assumptions, check sources and work, then explicitly run. A passed check is not a trading or provider certification.'};
    function steps(){return goal==='research'?['sources','design','accounts','review']:['sources','accounts','review'];}
    function fieldRows(){const form=$(forms[goal]);return form?[...form.querySelectorAll('input,select,textarea')].filter(applicable).filter(i=>!['search','button','submit'].includes(i.type)):[];}
    function update(){
      if(!current()||!goal||loading)return;
      partition(goal);const form=$(forms[goal]),host=$(hosts[goal]);
      if(!form){next.disabled=true;back.disabled=true;qualification.hidden=true;review.hidden=true;aside.replaceChildren(node('h3','Task unavailable'),node('p','The settings did not load. Choose this task again to retry, or select an available alternative.'));return;}
      if(goal==='research'&&!all.checked&&step==='accounts'&&$('#robust-economic-configure'))$('#robust-economic-configure').open=true;
      if(all.checked)for(const detail of host.querySelectorAll('.setup-context-details,.setup-expert-json'))detail.open=true;
      const nativeSelectors=goal==='compare'?[$('#campaign-execution')]:goal==='research'?[...form.querySelectorAll('select[id$="-execution"]')]:[];
      const selectedNative=goal==='compare'?[...form.querySelectorAll('.campaign-reference')].filter(i=>i.value===source.id).map(()=>source.run_metadata.strategy.id):[...form.querySelectorAll('#robust-source-choices input:checked')].map(i=>i.dataset.strategyId);
      const incompatible=!isMNQ||selectedNative.some(id=>id&&id!=='vwap_pullback_risk_sizing');
      for(const selector of nativeSelectors.filter(Boolean)){const option=selector.querySelector('option[value="native"]');if(!option)continue;if(!option.dataset.setupOriginalDisabled)option.dataset.setupOriginalDisabled=String(option.disabled);const disabled=option.dataset.setupOriginalDisabled==='true'||incompatible;if(option.disabled!==disabled)option.disabled=disabled;const reason=selector.value==='native'&&disabled?'Native reruns are unavailable for a selected source. Keep the declaration and choose a compatible source or explicitly change execution.':'';const previous=selector.dataset.setupValidity||'';if(reason){if(!selector.validity.customError||selector.validationMessage===previous){selector.setCustomValidity(reason);selector.dataset.setupValidity=reason;}}else{if(previous&&selector.validationMessage===previous)selector.setCustomValidity('');delete selector.dataset.setupValidity;}}
      let warning=host.querySelector('.setup-execution-compatibility');if(nativeSelectors.length&&!warning){warning=node('p',undefined,'setup-execution-compatibility setup-limitation');form.prepend(warning);mark(warning,'accounts');}if(warning){const text=incompatible?'Native account-controlled execution is unavailable for the selected instrument or strategy. Saved-trade scenarios keep their explicit assumptions; choose compatible MNQ VWAP sources for native risk-based sizing.':'Native execution still needs complete-session, causal-risk, cost and strategy-setting checks. No execution method is selected or substituted automatically.';if(warning.textContent!==text)warning.textContent=text;}
      for(const child of host.querySelectorAll('[data-setup-step]'))child.dataset.setupVisible=String(all.checked||child.dataset.setupStep.split(' ').includes(step));
      root.classList.toggle('setup-all-settings',all.checked);
      const d=outer[goal]?$(outer[goal]):null;if(d&&!all.checked)d.open=true;
      for(const b of nav.children){const active=b.dataset.step===step;b.setAttribute('aria-current',active?'step':'false');}
      stageHeading.textContent=all.checked?'All settings for this task':({sources:'Confirm sources',design:'Design the research',accounts:'Choose accounts and sizing',review:'Review, check and run'}[step]);help.textContent=descriptions[step];
      qualification.hidden=goal!=='research'||(!all.checked&&step!=='accounts');review.hidden=!all.checked&&step!=='review';
      const run=$(buttons[goal][1]),checked=!!run&&!run.disabled;
      aside.replaceChildren(node('h3','Your study'),node('p',titles[goal]),node('p','Source: '+source.run_metadata.dataset.name),node('p','Strategy: '+source.run_metadata.strategy.id.replaceAll('_',' ')));
      const plan=source.run_metadata.research?.plan;if(plan)aside.append(node('p',`Saved IS: ${plan.is_start} → ${plan.is_end}`));
      const phase=goal==='research'?['evaluation','funded'].filter(p=>$('#robust-economic-'+p)?.checked).join(' + '):$(goal==='compare'?'#campaign-phase':'#native-phase')?.selectedOptions[0]?.textContent;
      if(phase)aside.append(node('p','Phase objective: '+phase));else if(goal==='research')aside.append(node('p','No prop phase enabled · qualification only'));
      if(goal==='research')for(const phaseName of ['evaluation','funded'])if($('#robust-economic-'+phaseName)?.checked){const profiles=[['apex-50k-eod','Apex 50K EOD'],['lucidflex-50k','LucidFlex 50K']].filter(([id])=>$('#robust-economic-'+phaseName+'-'+id)?.checked).map(([,name])=>name);aside.append(node('p',(phaseName==='evaluation'?'Evaluation':'Funded')+' accounts: '+(profiles.join(' · ')||'None selected')));}
      if(goal==='compare'&&$('#campaign-count'))aside.append(node('p',$('#campaign-count').textContent));
      const important=fieldRows().filter(i=>!i.matches('.campaign-reference,.campaign-kind,.campaign-trials')).filter(i=>/profile|model|quantities|micros|sizes|risk|cap|budget|sizing-mode|reference|breach|horizon|delay|price|activation|commission|slippage|execution$/.test(i.id+' '+i.className));
      const list=node('ul');for(const input of important.slice(0,12))list.append(node('li',`${controlLabel(input)}: ${value(input)}`));aside.append(list);
      aside.append(node('p',checked?'Task checks passed for the current settings. Review the returned plan before running.':'Source checks required before running. Changes invalidate previous checks.','setup-check-state'));
      const output=$(goal==='research'?'#robust-status':goal==='compare'?'#campaign-status':goal==='inspect'?'#native-status':goal==='pair'?'#pair-status':'#prop-status');if(output?.textContent)aside.append(node('p',output.textContent));
      aside.append(node('p','Final access, provider rules, fill assumptions and settlement limitations remain explicit. No calculation runs when changing steps.'));
      if(!review.hidden){review.replaceChildren(node('h3','Review your declaration'),node('p','These are the enabled form settings, including advanced assumptions. The task check below resolves authoritative membership, dates, costs and work. Defaults are not recommendations.'));
        const detail=node('details');detail.append(node('summary','Inspect every enabled setting'));const dl=node('dl');for(const input of fieldRows()){dl.append(node('dt',controlLabel(input)),node('dd',value(input)));}detail.append(dl);review.append(detail);
        if(goal==='research'&&!phase)review.append(node('p','This run stops at strategy qualification. It will not select a position size or prop account.','setup-limitation'));
      }
      const position=steps().indexOf(step);back.disabled=position===0;next.hidden=step==='review'||all.checked;next.disabled=!form||loading;next.textContent=steps()[position+1]==='review'?'Review configuration':'Continue';
    }
    function go(target,focus=true){step=target;compatibilityDetails.open=target==='sources';message.textContent='';update();if(focus)stageHeading.focus({preventScroll:true});}
    function researchIntentValid(){const phases=['evaluation','funded'].some(p=>$('#robust-economic-'+p)?.checked);return goal!=='research'||all.checked||(phases&&!only.checked)||(!phases&&only.checked);}
    function validateStep(){
      if(goal==='research'&&step==='accounts'&&!researchIntentValid()){message.textContent=only.checked?'Disable the prop phases for qualification only, or uncheck qualification only to compare accounts.':'Enable Evaluation or Funded, or explicitly choose qualification only.';return false;}
      if(goal==='research'&&step==='accounts'&&!only.checked&&!['evaluation','funded'].some(p=>$('#robust-economic-'+p)?.checked)){message.textContent='Enable Evaluation or Funded, or explicitly choose qualification only.';return false;}
      const form=$(forms[goal]);for(const input of fieldRows()){const owner=input.closest('[data-setup-step]');if(owner?.dataset.setupStep.split(' ').includes(step)&&!input.checkValidity()){input.reportValidity();return false;}}return !!form;
    }
    async function choose(key){
      if(!current()||(key in availability&&!availability[key]))return;
      const attempt=++revision;goal=key;step='sources';all.checked=false;loading=true;workspace.hidden=false;goalPicker.open=false;goalSummary.textContent='Change goal · '+titles[key];compatibilityDetails.open=true;message.textContent='Loading this task…';heading.textContent=titles[key];
      for(const selector of new Set(Object.values(hosts)))$(selector).hidden=true;
      const host=$(hosts[key]);host.hidden=false;content.append(host); // Existing forms, listeners and form ownership are retained.
      for(const b of goalButtons)b.setAttribute('aria-pressed',String(b.id==='setup-goal-'+key));
      nav.replaceChildren();for(const name of steps()){const b=node('button',({sources:'Sources',design:'Research design',accounts:'Accounts and sizing',review:'Review and run'}[name]),'button secondary');b.type='button';b.id='setup-step-'+name;b.dataset.step=name;b.onclick=()=>go(name);nav.append(b);}
      try{
        if(!initialized.has(key))initialized.set(key,Promise.resolve().then(()=>initializers[key]()));
        await initialized.get(key);if(!current()||attempt!==revision)return;
        if((key==='legacy'||key==='budget')){const method=$('#prop-method'),expected=key==='budget'?'budgeted_lifecycle':'annualized';if(method.value!==expected){method.value=expected;method.dispatchEvent(new Event('change',{bubbles:true}));}}
        const d=outer[key]?$(outer[key]):null;if(d)d.open=true;
        for(const history of host.querySelectorAll('[data-setup-history]')){const wrap=node('details');wrap.dataset.setupTaskHistory=key;wrap.append(node('summary',key==='research'?'Previous strategy studies':'Previous phase campaigns'),history);$('#prop-previous').append(wrap);}
        const form=$(forms[key]);if(!form)throw Error(host.textContent||'This task is unavailable for the source.');
        if(!listenerForms.has(form)){listenerForms.add(form);form.addEventListener('click',event=>{if(['robust-preview','robust-run'].includes(event.target.closest('button')?.id)&&!researchIntentValid()){event.preventDefault();event.stopImmediatePropagation();go('accounts');message.textContent='Enable Evaluation or Funded, or explicitly choose qualification only.';}},{capture:true,signal});for(const event of ['input','change'])form.addEventListener(event,()=>queueMicrotask(update),{signal});
          form.addEventListener('invalid',event=>{const target=event.target,part=target.closest('[data-setup-step]');if(part)step=part.dataset.setupStep.split(' ')[0];for(let p=target.parentElement;p&&p!==host;p=p.parentElement)if(p.tagName==='DETAILS')p.open=true;update();message.textContent='Review the highlighted setting: '+controlLabel(target);},{capture:true,signal});}
        observer?.disconnect();observer=new MutationObserver(()=>{if(!loading)queueMicrotask(update);});observer.observe(host,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['disabled','hidden']});
        message.textContent='Settings are preserved when you change steps or revisit this task. Check again after editing.';
      }catch(error){initialized.delete(key);goalPicker.open=true;message.textContent='Could not open task: '+error.message+' Choose the task again to retry.';}
      finally{if(current()&&attempt===revision){loading=false;update();if($(forms[key]))stageHeading.focus({preventScroll:true});}}
    }
    next.onclick=()=>{if(validateStep())go(steps()[steps().indexOf(step)+1]);};back.onclick=()=>go(steps()[steps().indexOf(step)-1]);all.onchange=update;only.onchange=update;
    for(const selector of new Set(Object.values(hosts)))$(selector).hidden=true;
    // Source evidence and saved history stay separate from editable task forms.
    const sourceCard=$('#prop-source-card');if(sourceCard){sourceCard.classList.add('setup-source-evidence');compatibility.append(sourceCard);sourceCard.hidden=true;}
    const sourceDetails=node('details');sourceDetails.append(node('summary','Inspect saved source identity'));if(sourceCard){sourceDetails.append(sourceCard);sourceCard.hidden=false;}compatibility.append(sourceDetails);
    if(initialGoal){await choose(initialGoal);if(current()&&initialGoal==='research'&&new URLSearchParams(location.hash.split('?')[1]||'').get('research'))go('review',false);}
    return {choose,go,update};
  }
  window.propSetup={mount};
})();
