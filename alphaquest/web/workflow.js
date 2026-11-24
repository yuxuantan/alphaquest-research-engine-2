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
    {
      id: "overnight_bias_orb", name: "Overnight Bias ORB",
      hypothesis: "This strategy tests whether a breakout in the direction suggested by the regular-session open will continue intraday.",
      overview: {
        steps: [
          "Choose a side for the day. Measure the overnight high and low from midnight through 09:30 ET. If the regular-session open is at least 67% of the way from the overnight low to the high, only longs are allowed. At 33% or lower, only shorts are allowed. In between, the strategy sits out.",
          "Wait for a breakout. Mark the high and low from 09:30 to 09:45 ET. From the 10:00 through the 13:00 ET close, look for a 15-minute close strictly above that high for a long or strictly below that low for a short. The signal must pass the trend-strength and range filters. The default is one contract, one position at a time and up to four entry submissions per day.",
          "Enter at the next open. The initial stop is 30% of the 15-day regular-session average true range (ATR). The target is three times that distance. Both levels are measured from the breakout close and are active on the entry bar. They stay at those prices if the market gaps at entry.",
          "Exit on the stop or target. If a position is still open at the first 15-minute close at or after 15:30 ET, send a market exit for the next open. The scheduled Globex close is the backup exit, including on early-close days.",
        ],
        example: "If the overnight range is 20,000–20,100 and the regular session opens at 20,080, the day is long-only. If the opening-range high is 20,095 and a qualifying bar closes at 20,100, a 100-point ATR puts the stop at 20,070 and the target at 20,190. A next-open fill at 20,105 leaves 35 points to the stop and 85 to the target, before costs.",
      },
      entryNotes: [
        "Trend strength uses Wilder ADX on 15-minute candles, with length 16 and a minimum reading of 20 by default. ADX measures trend strength. The overnight range determines the trade direction.",
        "The breakout candle’s high-low range can be at most 2.5 times the average range of the preceding 20 candles. A skipped breakout leaves the daily bias in effect for later qualifying closes.",
        "The opening range can be at most twice its 20-period exponential moving average through the previous session. This filter starts at opening range 20 once the reference is positive. The ATR gate requires 15 completed regular sessions and a positive stop distance.",
      ],
      dataNotes: [
        "Use full-session, close-labelled one-minute NQ or MNQ Globex OHLC in AlphaQuest. The strategy groups those minutes into 15-minute candles for decisions. The overnight high and low come from the post-midnight portion of the session.",
        "Allow about two months of data inside each calculation window. The first 250 completed 15-minute candles supply MaxBarsBack, then the strategy builds its daily ATR and opening-range history.",
      ],
      interpretationNotes: [
        "For MultiCharts comparison, use a single 15-minute Globex series, one-minute Bar Magnifier and the same dates, time settings and costs. With showValidation enabled, check the breakout bar’s gates and submitted stop and target against the fills in the trade export.",
      ],
      broad: ["Examples of searchable inputs include the overnight bias thresholds, ADX, breakout-candle and opening-range filters, ATR stop multiplier and target multiple."],
      narrow: ["Narrow locks the selected Broad values by default. Eligible numeric axes can be explicitly refined on a finer grid."],
    },
    {
      id: "noise", name: "Noise",
      hypothesis: "Noise looks for directional moves that are unusually large for that time of day.",
      overview: {
        steps: [
          "Build a separate noise band for each 15-minute slot from 09:00 through 14:15 CT. Average the prior 20 observations of the absolute percentage move from the day’s opening price at that slot. Expand the higher of the date open and previous close upward by that percentage, and the lower anchor downward.",
          "From 09:00 through 14:00 CT, buy when the close is strictly above both the upper band and the candle’s open. Sell short when the close is strictly below both the lower band and the candle’s open. Market entries fill at the next open. The default size is two contracts.",
          "A 50-point stop and 25-point target are active from the actual entry fill. At a warmed-up slot, a long sends a next-open exit if the close is below the higher of the upper band and EMA 20. A short exits above the lower of the lower band and EMA 20. The exact 14:30 CT close also sends a next-open exit. An early close that omits that bar can leave a position open into the next session.",
          "An opposite breakout through 14:00 CT sends a next-open exit and can reverse. The exit still goes through if the new entry is blocked. Each chart date allows up to 10 entry submissions, including reversals, and bars new entries after three closed losses at least as large as the full position’s stop.",
        ],
        example: "With a date open of 20,000, a previous close of 19,980 and a prior average move of 0.25%, the upper band is 20,050 and the lower band is 19,930.05. A bullish close at 20,060 qualifies for a long if the entry gates pass. If the next open fills at 20,065, the stop is 20,015 and the target is 20,090.",
      },
      dataNotes: [
        "Select close-labelled one-minute NQ or MNQ OHLC data. AlphaQuest evaluates 15-minute closes in Central time. Supply enough history for 20 prior observations of each slot inside the selected window.",
        "The anchors come from the first candle of each Central chart date and the immediately preceding close. On a regular-session dataset they are the session open and previous session close. With Globex coverage they come from around midnight. Match the chart session template and history for comparison.",
      ],
      interpretationNotes: [
        "In MultiCharts .NET, use one close-stamped 15-minute series on the Exchange clock, with IOG off and one-minute Bar Magnifier. Turn on showValidation to inspect the anchors, bands, EMA, daily limits and order submissions. Use native trade markers and the export to check fills.",
        "AlphaQuest follows a modeled path inside each minute. Start the comparison with matching data and zero costs, then repeat with your commission and slippage settings.",
      ],
      broad: ["Examples of searchable inputs include band lookback and multiplier, EMA length, stop distance, target multiple and direction switches."],
      narrow: ["Narrow locks the selected Broad values by default. Eligible numeric axes can be explicitly refined on a finer grid."],
    },
  ];
  const list = get("#workflow-campaign-list");
  let catalogue, definitions, generation = 0, deletionNotice = null;
  const read = async (url, method='GET', payload) => {
    const response = await window.portalLoading.fetch(url, {cache:'no-store',method,headers:payload?{'Content-Type':'application/json'}:undefined,body:payload?JSON.stringify(payload):undefined});
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
    return host;
  }
  const action = (parent, title, href) => {
    const link = node('a', title, 'workflow-inline-link'); link.href = href; parent.append(link); return link;
  };
  async function renderCampaign() {
    const current = ++generation;
    if (!/^#campaigns(?:\/[^/]+)?$/.test(location.hash)) return;
    const host = get("#workflow-campaign-detail");
    const finishSectionLoading=window.portalLoading.region(host,'Loading campaigns and datasets…');
    try {
    try {
      [catalogue, definitions] = await Promise.all([read('/api/strategies/library'), read('/api/strategies')]);
      if (current !== generation) return;
      const id = location.hash === '#campaigns' ? catalogue.items.find(item => item.id === 'vwap_pullback_risk_sizing')?.id || catalogue.items[0]?.id : location.hash.slice('#campaigns/'.length);
      list.replaceChildren(node('h2', 'Choose a campaign'));
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
      host.append(node('h2',campaign.name),node('p',campaign.hypothesis,'campaign-hypothesis'));
      if (campaign.overview) {
        const overview = section(host, 'How it trades', campaign.overview.steps);
        overview.classList.add('campaign-overview');
        const example = node('p',undefined,'campaign-example');
        example.append(node('strong','Example. '), campaign.overview.example);
        overview.append(example);
      }
      const datasets = node('section',undefined,'workflow-datasets');
      const datasetsStatus = window.portalLoading.message('Loading campaign datasets…');
      datasets.append(node('h3','Datasets'),datasetsStatus);
      const notes = node('details',undefined,'campaign-strategy-notes');
      notes.append(node('summary','Strategy notes and source'));
      if (!campaign.overview) {
        host.append(datasets);
        notes.append(node('p','No research linked yet.','field-help'));
        section(notes,'Shared logic',campaign.logic.length ? campaign.logic : [definition?.description || 'Open a saved report to inspect its recorded logic.']);
      }
      if (campaign.entryNotes?.length) section(notes,'Entry requirements and common blockers',campaign.entryNotes);
      if (campaign.dataNotes?.length) section(notes,'Data and warm-up',campaign.dataNotes);
      if (campaign.interpretationNotes?.length) section(notes,'Live and backtest interpretation',campaign.interpretationNotes);
      const params = node('div',undefined,'workflow-parameter-layout');
      section(params,'Broad parameters',campaign.broad?.length ? campaign.broad : ['Not classified yet']);
      section(params,'Narrow parameters',campaign.narrow?.length ? campaign.narrow : ['Not classified yet']); notes.append(params);
      const source = node('details',undefined,'workflow-source');
      source.append(node('summary','Source code'),node('code',definition ? `alphaquest/strategies/${id}.py` : 'No current local strategy code. Inspect the saved report for recorded provenance.'));
      action(source,'Browse existing saved runs →',`#strategies/${encodeURIComponent(id)}`); notes.append(source);
      host.append(notes);
      if (campaign.overview) host.append(datasets);
      const [workflows, groups] = await Promise.all([read(`/api/campaign-workflows?${new URLSearchParams({strategy_id:id})}`), read(`/api/strategies/${encodeURIComponent(id)}/datasets?limit=100`)]);
      window.portalLoading.clear(datasetsStatus);
      datasetsStatus.remove();
      if (current !== generation) return;
      const sourceOf = dataset => ({sha256:dataset.sha256,source_timezone:dataset.source_timezone,source_kind:dataset.source_kind||'native'});
      const currentPage = () => current===generation && /^#campaigns(?:\/[^/]+)?$/.test(location.hash);
      if(deletionNotice?.strategy_id===id){
        const notice=node('div',undefined,'workflow-link-notice');notice.setAttribute('role','status');
        notice.append(node('span',deletionNotice.text));datasets.append(notice);
      }
      const deleteButton = (card,dataset,target) => {
        const controls=node('div',undefined,'workflow-link-actions'),button=node('button',target.workflow_id?'Delete workflow and results…':'Delete saved results…','button secondary danger'),notice=node('p',undefined,'small');
        button.type='button';button.setAttribute('aria-label',target.workflow_id?`Delete workflow ${target.workflow_id.slice(0,8)} for ${dataset.name}`:`Delete saved results for ${dataset.name}`);notice.setAttribute('role','status');controls.append(button);card.append(controls,notice);
        button.onclick=async()=>{
          button.disabled=true;
          try {
            const body={strategy_id:id,source:sourceOf(dataset),...target},preview=await read('/api/campaign-dataset-links/preview','POST',body);
            if(!currentPage())return;
            const dialog=node('dialog',undefined,'workflow-delete-dialog');dialog.setAttribute('aria-labelledby','workflow-delete-title');
            const title=node('h2','Permanently delete workflow and results');title.id='workflow-delete-title';
            dialog.append(title,node('p',`${campaign.name} · ${preview.dataset_name}`),node('p',preview.workflow_id?`Selected workflow: ${preview.workflow_id}`:'Selected saved-results group'),node('p',preview.interpretation));
            const summary=node('ul');
            for(const text of [`${preview.workflow_ids.length} workflow(s), including their reviews and frozen selections`,`${preview.job_ids.length} backtest batch(es) and ${preview.run_ids.length} backtest report(s)`,`${preview.simulation_ids.length} downstream Prop Sim / portfolio simulation(s) and ${preview.phase_campaign_ids.length} phase package(s)`,`${(preview.research_studies||[]).length} dependent research ${(preview.research_studies||[]).length===1?'study':'studies'}`,`${preview.analysis_ids.length} Monte Carlo / prop / research report(s)`,`${preview.file_count} files · ${(preview.bytes/1024/1024).toFixed(2)} MB`])summary.append(node('li',text));
            dialog.append(summary);
            const detail=(label,items,href)=>{
              if(!items.length)return;
              const box=node('details');box.append(node('summary',label));const values=node('ul');
              for(const value of items){const row=node('li');if(href)action(row,value,href(value));else row.textContent=value;values.append(row);}box.append(values);dialog.append(box);
            };
            detail('Affected workflows',preview.workflow_ids,value=>`#campaigns/workflows/${value}/mechanic_validation`);
            detail('Downstream simulations that will also be deleted',preview.simulation_ids,value=>`#prop-sim?analysis=${value}`);
            if(preview.research_studies?.length){
              const box=node('details');box.append(node('summary','Dependent research studies that will also be deleted'));const list=node('ul');
              for(const study of preview.research_studies){
                const row=node('li'),text=`${study.name} · ${study.status} · ${study.saved_steps} saved steps · created ${study.created_at_utc.slice(0,10)} · ${study.id}`;
                if(study.analysis_id)action(row,text,`#backtests/prop/job/${study.analysis_id}`);else row.textContent=text;
                list.append(row);
              }box.append(list,node('p','These saved study plans, checkpoints and unshared results will be removed. Shared reports and research-access history are retained.','muted small'));dialog.append(box);
            }
            detail('Backtest batches',preview.job_ids,value=>`#jobs/backtest_batch/${value}`);
            detail('Backtest reports',preview.run_ids,value=>`#backtests/report/${value}`);
            detail('Monte Carlo / prop reports',preview.analysis_ids,value=>`#jobs/prop_analysis/${value}`);
            detail('Files to delete',preview.files.map(f=>`${f.kind}: ${f.path} (${f.bytes.toLocaleString()} bytes)`));
            const retained=[...preview.retained_jobs.map(r=>`Batch ${r.id}: ${r.reasons.join('; ')}`),...preview.retained_runs.map(r=>`Backtest ${r.id}: ${r.reasons.join('; ')}`),...preview.retained_analyses.map(r=>`Analysis ${r.id}: ${r.reasons.join('; ')}`)];
            detail(`Shared evidence kept · ${retained.length}`,retained);
            if(retained.length)dialog.append(node('p','Shared reports stay under Saved results and may still have a saved-results card. Other workflows using this dataset remain linked.','muted small'));
            if(preview.blockers.length){
              const blocked=node('div',undefined,'workflow-delete-blockers');blocked.setAttribute('role','alert');blocked.append(node('h3','Deletion is blocked'));
              for(const item of preview.blockers){const line=node('p',item.message);if(item.href)action(line,' Open dependency →',item.href);blocked.append(line);}dialog.append(blocked);
            }
            const consent=node('label',undefined,'workflow-delete-consent'),check=node('input');check.type='checkbox';
            consent.append(check,node('span','I understand that the selected workflow or saved-results group, listed downstream research studies, simulations and unshared results will be permanently deleted. There is no Undo.'));dialog.append(consent);
            const status=node('p',undefined,'small');status.setAttribute('role','status');dialog.append(status);
            const buttons=node('div',undefined,'workflow-link-actions'),cancel=node('button','Cancel','button secondary'),confirm=node('button','Permanently delete','button danger');
            cancel.type=confirm.type='button';confirm.disabled=true;check.onchange=()=>{confirm.disabled=!check.checked||!preview.deletable;};cancel.onclick=()=>dialog.close();
            buttons.append(cancel,confirm);dialog.append(buttons);document.body.append(dialog);
            const navigation=()=>dialog.close();window.addEventListener('hashchange',navigation);
            dialog.addEventListener('close',()=>{window.removeEventListener('hashchange',navigation);dialog.remove();if(button.isConnected)button.disabled=false;},{once:true});
            confirm.onclick=async()=>{
              confirm.disabled=cancel.disabled=check.disabled=true;status.textContent='Deleting the listed records and files…';
              // Escape must not dismiss an in-flight deletion and hide its receipt.
              const prevent=event=>event.preventDefault();dialog.addEventListener('cancel',prevent);
              try {
                const receipt=await read('/api/campaign-dataset-links','DELETE',{...body,confirmation_sha256:preview.confirmation_sha256});
                if(receipt.cleanup_pending.length){
                  status.textContent='Catalogue deletion is complete, but some files still need cleanup. Click Retry file cleanup.';confirm.textContent='Retry file cleanup';confirm.disabled=false;cancel.disabled=false;return;
                }
                deletionNotice={strategy_id:id,text:`${preview.dataset_name}: selected ${preview.workflow_id?'workflow':'saved results'} and unshared results permanently deleted. Original dataset and campaign kept.${retained.length?' Shared evidence retained.':''}`};
                dialog.close();if(currentPage())await renderCampaign();
              }catch(error){status.textContent=error.message+' Close this preview and review again before retrying.';cancel.disabled=false;}
              finally{dialog.removeEventListener('cancel',prevent);}
            };
            dialog.showModal();cancel.focus();
          } catch(error) { if(card.isConnected)notice.textContent=error.message; }
          finally { if(button.isConnected&&!document.querySelector('.workflow-delete-dialog'))button.disabled=false; }
        };
      };
      const seen = new Set();
      for (const workflow of workflows.items) {
        const saved = workflow.declaration, dataset = saved.dataset;
        seen.add(dataset.id);
        const card = node('div',undefined,'workflow-dataset workflow-real-dataset');
        card.dataset.workflowId=workflow.id;
        const latest=workflow.phases.find(phase=>phase.id===workflow.latest_phase);
        const pendingNarrow=latest.id==='is_narrow' ? workflow.narrow.find(branch=>!branch.confirmed_at_utc) : null;
        const destination=`#campaigns/workflows/${workflow.id}/${latest.id}${pendingNarrow?`?broad_trial=${pendingNarrow.broad_trial}`:''}`;
        const heading = node('a',dataset.name,'workflow-inline-link');
        heading.href = destination;
        card.append(heading,node('span',`${dataset.symbol || 'Unspecified'} · ${saved.plan.is_start} → ${saved.plan.is_end} IS`));
        card.append(node('span',`Created ${new Date(workflow.created_at_utc).toLocaleString()} · Workflow ${workflow.id.slice(0,8)}`,'muted small'));
        const version=node('details');version.append(node('summary','Workflow details'),node('code',`Strategy ${String(saved.strategy_source_sha256||'unknown').slice(0,12)} · Engine ${String(saved.engine_identity||'unknown').slice(0,12)}`));card.append(version);
        card.append(node('span',`${latest.label} · ${latest.status.replaceAll('_',' ')}`,'workflow-stage'));
        deleteButton(version,dataset,{workflow_id:workflow.id});datasets.append(card);
      }
      for (const group of groups.items) {
        if (seen.has(group.available_dataset_id)) continue;
        const d = group.dataset, card = node('div',undefined,'workflow-dataset workflow-real-dataset');
        const start = group.available_dataset_id && definition ? `#backtests/new?${new URLSearchParams({workflow:'mechanic',strategy:id,dataset:group.available_dataset_id})}` : `#strategies/${id}/datasets/${group.id}`;
        action(card, d.name, start);
        card.append(node('span',`${group.instrument} · ${d.start_date || 'Unknown start'} → ${d.end_date || 'Unknown end'}`),node('span',`Saved results · ${group.reports} report(s) · no active workflow`,'workflow-stage'));
        action(card,'Inspect saved results →',`#strategies/${id}/datasets/${group.id}`);
        const savedResults=node('details');savedResults.append(node('summary','Manage saved results'));card.append(savedResults);
        deleteButton(savedResults,d,{group_id:group.id});datasets.append(card);
      }
      if (!datasets.querySelector('.workflow-real-dataset')) datasets.append(node('p','No saved datasets for this campaign. Choose New backtest to select or upload a dataset.'));
      if (groups.total > groups.items.length) action(datasets,'Browse all saved datasets →',`#strategies/${id}`);
    } catch (error) {
      if (current === generation) {
        host.replaceChildren(node('p',error.message));
        const retry = node('button','Retry','button secondary'); retry.onclick = renderCampaign; host.append(retry);
      }
    }
    } finally { finishSectionLoading(); }
  }

  window.addEventListener("hashchange", renderCampaign);
  renderCampaign();
})();
