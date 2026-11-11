"use strict";

// Campaign narratives plus real dataset/run navigation. Prop Sim remains a preview.
(() => {
  const get = (selector) => document.querySelector(selector);
  const node = (tag, text, className) => {
    const item = document.createElement(tag);
    if (text !== undefined) item.textContent = text;
    if (className) item.className = className;
    return item;
  };
  const campaigns = [
    {
      id: "vwap_pullback_risk_sizing", name: "ORB + VWAP pullback",
      hypothesis: "A breakout of the day’s opening range followed by a pullback into VWAP signals continuation.",
      logic: ["Entry: opening-range break, then VWAP retest and reclaim.", "Stop: confirmed pivot or pullback extreme, with a configurable buffer.", "Take profit: confirmed pivot target, subject to reward/risk criteria."],
      broad: ["Stop mode · 1: confirmed pivot; 2: pullback extreme.", "Retest mode · 1: touch VWAP; 2: close through VWAP, then reclaim."],
      narrow: ["ADX length and elevation threshold", "Stop / target swing strength", "Entry window and minimum reward/risk"],
    },
    {
      id: "twin_continuation", name: "Twin continuation",
      hypothesis: "Confirmed swing breakouts and morning momentum offer complementary continuation setups.",
      logic: ["Entry: six-hour confirmed swing breakout or ten-minute morning momentum.", "Stop: setup-owned protection; momentum uses a fixed point distance.", "Take profit: breakout target multiple; momentum uses its scheduled exit."],
      broad: ["Breakout setup · enabled / disabled", "Momentum setup · enabled / disabled", "Immediate protection · enabled / disabled"],
      narrow: ["Breakout target multiple and ATR period", "Momentum trigger and stop distance", "Momentum entry window"],
    },
  ];
  const list = get("#workflow-campaign-list");
  let catalogue, definitions, generation = 0;
  const read = async (url) => {
    const response = await fetch(url, {cache:'no-store'});
    const body = await response.json();
    if (!response.ok) throw Error(typeof body.detail === 'string' ? body.detail : 'Could not load campaign datasets.');
    return body;
  };
  function section(parent, title, values) {
    const host = node("section", undefined, "workflow-detail-section");
    host.append(node("h3", title));
    const bullets = node("ul");
    for (const value of values) bullets.append(node("li", value));
    host.append(bullets);
    parent.append(host);
  }
  const action = (parent, title, href) => {
    const link = node('a', title, 'workflow-inline-link'); link.href = href; parent.append(link); return link;
  };
  async function renderCampaign() {
    const current = ++generation;
    if (!/^#campaigns(?:\/[^/]+)?$/.test(location.hash)) return;
    const host = get("#workflow-campaign-detail");
    host.replaceChildren(node('p', 'Loading campaigns and datasets…'));
    try {
      [catalogue, definitions] = await Promise.all([read('/api/strategies/library'), read('/api/strategies')]);
      if (current !== generation) return;
      const id = location.hash === '#campaigns' ? catalogue.items.find(item => item.id === 'vwap_pullback_risk_sizing')?.id || catalogue.items[0]?.id : location.hash.slice('#campaigns/'.length);
      list.replaceChildren(node('h2', 'Campaigns'), node('p', `${catalogue.items.length} strategy codes`, 'muted small'));
      for (const item of catalogue.items) {
        const name = campaigns.find(c => c.id === item.id)?.name || item.name;
        const link = node('a', undefined, 'workflow-campaign-link');
        link.href = `#campaigns/${encodeURIComponent(item.id)}`;
        if (item.id === id) link.setAttribute('aria-current','true');
        link.append(node('strong',name),node('small',item.id)); list.append(link);
      }
      host.replaceChildren();
      const item = catalogue.items.find(c => c.id === id);
      if (!item) { host.append(node('h2','Campaign not found'),node('p','Choose a campaign from the list.')); return; }
      const definition = definitions.find(c => c.id === id);
      const campaign = campaigns.find(c => c.id === id) || {id, name:item.name, hypothesis:definition?.description || 'Archived strategy code.', logic:[], broad:[], narrow:[]};
      get('#campaign-new-backtest').href = `#backtests/new?${new URLSearchParams({workflow:'mechanic', strategy:id})}`;
      get('#campaign-new-backtest').hidden = !definition;
      host.append(node('div','CAMPAIGN DETAILS','eyebrow'),node('h2',campaign.name),node('h3','Hypothesis'),node('p',campaign.hypothesis));
      const research = node('p','Linked research: '); action(research,'No research linked yet','#research'); host.append(research);
      section(host,'Shared logic',campaign.logic.length ? campaign.logic : [definition?.description || 'Open a saved report to inspect its recorded logic.']);
      const params = node('div',undefined,'workflow-parameter-layout');
      section(params,'Broad parameters',campaign.broad.length ? campaign.broad : ['Not classified yet']);
      section(params,'Narrow parameters',campaign.narrow.length ? campaign.narrow : ['Not classified yet']); host.append(params);
      const source = node('details',undefined,'workflow-source');
      source.append(node('summary','Source code'),node('code',definition ? `alphaquest/strategies/${id}.py` : 'No current local strategy code. Inspect the saved report for recorded provenance.'));
      action(source,'Browse existing saved runs →',`#strategies/${encodeURIComponent(id)}`); host.append(source);
      const datasets = node('section',undefined,'workflow-datasets');
      datasets.append(node('h3','Datasets'),node('p','Saved sources and their current validation phase','muted small')); host.append(datasets);
      const [workflows, groups] = await Promise.all([read(`/api/campaign-workflows?${new URLSearchParams({strategy_id:id})}`), read(`/api/strategies/${encodeURIComponent(id)}/datasets?limit=100`)]);
      if (current !== generation) return;
      const seen = new Set();
      for (const workflow of workflows.items) {
        const saved = workflow.declaration, dataset = saved.dataset;
        seen.add(dataset.id);
        const card = node('div',undefined,'workflow-dataset workflow-real-dataset');
        const latest=workflow.phases.find(phase=>phase.id===workflow.latest_phase);
        const pendingNarrow=latest.id==='is_narrow' ? workflow.narrow.find(branch=>!branch.confirmed_at_utc) : null;
        const destination=`#campaigns/workflows/${workflow.id}/${latest.id}${pendingNarrow?`?broad_trial=${pendingNarrow.broad_trial}`:''}`;
        const heading = node('a',dataset.name,'workflow-inline-link');
        heading.href = destination;
        card.append(heading,node('span',`${dataset.symbol || 'Unspecified'} · ${saved.plan.is_start} → ${saved.plan.is_end} IS`));
        card.append(node('span',`${latest.label} · ${latest.status.replaceAll('_',' ')}`,'workflow-stage'));
        if (!workflow.review) action(card,'Resume backtest →',destination);
        datasets.append(card);
      }
      for (const group of groups.items) {
        if (seen.has(group.available_dataset_id)) continue;
        const d = group.dataset, card = node('div',undefined,'workflow-dataset workflow-real-dataset');
        const start = group.available_dataset_id && definition ? `#backtests/new?${new URLSearchParams({workflow:'mechanic',strategy:id,dataset:group.available_dataset_id})}` : `#strategies/${id}/datasets/${group.id}`;
        action(card, d.name, start);
        card.append(node('span',`${group.instrument} · ${d.start_date || 'Unknown start'} → ${d.end_date || 'Unknown end'}`),node('span','Mechanic validation · not started','workflow-stage'));
        action(card,'Inspect saved results →',`#strategies/${id}/datasets/${group.id}`);
        datasets.append(card);
      }
      if (!workflows.items.length && !groups.items.length) datasets.append(node('p','No saved datasets for this campaign. Choose New backtest to select or upload a dataset.'));
      if (groups.total > groups.items.length) action(datasets,'Browse all saved datasets →',`#strategies/${id}`);
    } catch (error) {
      if (current === generation) {
        host.replaceChildren(node('p',error.message));
        const retry = node('button','Retry','button secondary'); retry.onclick = renderCampaign; host.append(retry);
      }
    }
  }

  const examples = [
    {id: "orb-1", name: "ORB + VWAP pullback", params: "stop_mode=1, retest_mode=1", risk: 0},
    {id: "orb-2", name: "ORB + VWAP pullback", params: "stop_mode=2, retest_mode=2", risk: 200},
    {id: "twin-1", name: "Twin continuation", params: "use_breakout=true, use_momentum=true", risk: 300},
    {id: "twin-2", name: "Twin continuation", params: "use_breakout=false, mo_trigger=100", risk: 50},
  ];
  const selected = new Set(examples.map((item) => item.id));
  let evaluation = null;
  function updateProfile() {
    const choice = examples.find((item) => item.id === evaluation);
    get("#prop-preview-profile").textContent = choice
      ? `Example evaluation profile: ${choice.name} · ${choice.params} · $${choice.risk} risk per trade.`
      : "Select an example evaluation profile above.";
  }
  function renderInputs() {
    const choices = examples.filter((item) => selected.has(item.id));
    if (!selected.has(evaluation)) evaluation = null;
    get("#prop-preview-count").textContent = `(${choices.length} selected)`;
    for (const id of ["selected", "evaluation", "funded"]) get(`#prop-preview-${id}`).replaceChildren();
    for (const choice of choices) {
      const card = node("div", undefined, "workflow-input-card");
      card.append(node("strong", choice.name), node("code", choice.params));
      get("#prop-preview-selected").append(card);
      const label = node("label", undefined, "workflow-sizing-row");
      const radio = node("input");
      radio.type = "radio";
      radio.name = "preview-evaluation";
      radio.value = choice.id;
      radio.checked = evaluation === choice.id;
      radio.onchange = () => { evaluation = choice.id; updateProfile(); };
      const text = node("span", `${choice.name} · ${choice.params}`);
      text.append(node("strong", `Example risk: $${choice.risk} per trade`));
      label.append(radio, text);
      get("#prop-preview-evaluation").append(label);
      const funded = node("div", undefined, "workflow-sizing-row");
      const fundedText = node("span", `${choice.name} · ${choice.params}`);
      fundedText.append(node("strong", `Example risk: $${choice.risk} per trade`));
      funded.append(fundedText);
      get("#prop-preview-funded").append(funded);
    }
    if (!choices.length) {
      for (const id of ["selected", "evaluation", "funded"]) get(`#prop-preview-${id}`).append(node("p", "No example inputs selected. Choose strategy inputs above.", "muted"));
    }
    updateProfile();
  }
  for (const choice of examples) {
    const label = node("label", undefined, "workflow-input-option");
    const input = node("input");
    input.type = "checkbox";
    input.value = choice.id;
    input.checked = true;
    input.onchange = () => { input.checked ? selected.add(choice.id) : selected.delete(choice.id); renderInputs(); };
    label.append(input, node("span", `${choice.name} · ${choice.params}`));
    get("#prop-preview-options").append(label);
  }
  get("#prop-preview-add").onclick = () => {
    get("#prop-preview-picker").open = true;
    get("#prop-preview-options input").focus();
  };
  window.addEventListener("hashchange", renderCampaign);
  renderCampaign();
  renderInputs();
})();
