"use strict";

// Campaign narratives plus real dataset/run navigation. Prop Sim is owned by prop-sim.js.
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
      entryNotes: [
        "VWAP and ADX are only part of entry eligibility. The opening-range break must be latched by a close beyond the range, followed by the selected VWAP retest/reclaim. When enabled, ADX must be at least its elevation threshold and no higher than its configured lookback value. Defaults are threshold 20 and a one-bar decay comparison; a separate chart indicator must use matching settings.",
        "Retest mode 1 remembers a Low touching or falling below VWAP for longs, or a High touching or rising above VWAP for shorts, then requires a close back on the entry side. Mode 2 remembers a close through VWAP and requires a later reclaim. These latches survive delays from ADX or other entry gates until an entry submission or the configured day reset; the eventual entry bar need not touch VWAP again.",
        "Pivots become usable only after the configured number of bars on both sides is complete; equal highs/lows do not qualify. With the default stop swing strength of 20, a fresh low needs 20 completed bars to its right before it can become a confirmed stop pivot. The target has its own strength, default 5. A visible turning point is not yet a confirmed pivot.",
        "Stop mode 1 uses the latest confirmed stop pivot, with the outward buffer. During a sharp decline, the older confirmed low can still be above a long setup’s closing price while the new low awaits confirmation; that makes the long stop invalid and blocks entry. Stop mode 2 instead uses the extreme since the retest latch, with the buffer. Shorts mirror these rules.",
        "On the decision bar, a long needs stop < close < confirmed target; a short needs confirmed target < close < stop. Missing pivots, a stop on the wrong side, or a target already passed block entry. MinRR=0 and MaxStopPoints=0 disable only those optional thresholds: they do not waive the positive stop distance, profitable target direction or required pivot checks. Any enabled reward/risk and maximum-stop limits must also pass.",
        "The strategy must be flat, the direction enabled, the entry/VWAP windows and calendar cutoff eligible, and the submitted quantity positive. Risk sizing can round down to zero. The default daily allowance is one entry submission per configured reset day; exiting or losing that trade does not restore the allowance. Use the saved run’s actual inputs, which may differ from defaults.",
        "A qualifying setup is evaluated on a completed bar and submits a market entry for the next observed bar’s Open. Inspect the decision bar before the fill marker. To explain a skipped setup, compare the retest/ADX gates, candidate stop and target, stop distance, reward/risk, quantity and used daily allowance; a chart image alone cannot establish which gate failed.",
      ],
      interpretationNotes: [
        "The MultiCharts signal’s VWAP overlay shows the value used in that calculation run. If live prices or volume weights differ from later historical backfill, replacing data and recalculating can change VWAP, retest latches and reconstructed entry times. This is a possible explanation for live/backtest differences, not proof of missing data in a particular trade. Later bars alone do not rewrite earlier overlay segments.",
        "Preserve the original live decision values and order source before comparing with refreshed history. Recalculated commentary describes the recalculated run; it cannot recover the original live decision or undo a broker fill.",
      ],
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
      if (campaign.entryNotes?.length) section(host,'Entry requirements and common blockers',campaign.entryNotes);
      if (campaign.interpretationNotes?.length) section(host,'Live and backtest interpretation',campaign.interpretationNotes);
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

  window.addEventListener("hashchange", renderCampaign);
  renderCampaign();
})();
