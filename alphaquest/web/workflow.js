"use strict";

// Presentation-only examples for the first workflow revision. No result storage or runs.
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
      stages: ["IS narrow · 2 passes", "Mechanic validation"],
    },
    {
      id: "twin_continuation", name: "Twin continuation",
      hypothesis: "Confirmed swing breakouts and morning momentum offer complementary continuation setups.",
      logic: ["Entry: six-hour confirmed swing breakout or ten-minute morning momentum.", "Stop: setup-owned protection; momentum uses a fixed point distance.", "Take profit: breakout target multiple; momentum uses its scheduled exit."],
      broad: ["Breakout setup · enabled / disabled", "Momentum setup · enabled / disabled", "Immediate protection · enabled / disabled"],
      narrow: ["Breakout target multiple and ATR period", "Momentum trigger and stop distance", "Momentum entry window"],
      stages: ["Mechanic validation", "IS broad · 1 pass"],
    },
  ];
  const list = get("#workflow-campaign-list");
  list.append(node("h2", "Campaigns"), node("p", "2 example campaigns", "muted small"));
  for (const campaign of campaigns) {
    const link = node("a", undefined, "workflow-campaign-link");
    link.href = `#campaigns/${campaign.id}`;
    link.dataset.campaign = campaign.id;
    link.append(node("strong", campaign.name), node("small", campaign.id));
    list.append(link);
  }
  function section(parent, title, values) {
    const host = node("section", undefined, "workflow-detail-section");
    host.append(node("h3", title));
    const bullets = node("ul");
    for (const value of values) bullets.append(node("li", value));
    host.append(bullets);
    parent.append(host);
  }
  function renderCampaign() {
    if (!location.hash.startsWith("#campaigns")) return;
    const id = location.hash === "#campaigns" ? campaigns[0].id : location.hash.slice("#campaigns/".length);
    const campaign = campaigns.find((item) => item.id === id);
    const host = get("#workflow-campaign-detail");
    host.replaceChildren();
    for (const link of list.querySelectorAll("a")) {
      if (link.dataset.campaign === campaign?.id) link.setAttribute("aria-current", "true");
      else link.removeAttribute("aria-current");
    }
    if (!campaign) {
      host.append(node("h2", "Campaign not found"), node("p", "Choose an example campaign from the list."));
      return;
    }
    host.append(node("div", "CAMPAIGN DETAILS", "eyebrow"), node("h2", campaign.name), node("h3", "Hypothesis"), node("p", campaign.hypothesis));
    const research = node("p", "Linked research: ");
    const researchLink = node("a", "No research linked yet", "workflow-inline-link");
    researchLink.href = "#research";
    research.append(researchLink);
    host.append(research);
    section(host, "Shared logic", campaign.logic);
    const params = node("div", undefined, "workflow-parameter-layout");
    section(params, "Broad parameters", campaign.broad);
    section(params, "Narrow parameters", campaign.narrow);
    host.append(params);
    const source = node("details", undefined, "workflow-source");
    source.append(node("summary", "Source code"), node("code", `alphaquest/strategies/${campaign.id}.py`));
    const saved = node("a", "Browse existing saved runs →", "workflow-inline-link");
    saved.href = `#strategies/${campaign.id}`;
    source.append(node("p", "Strategy code in this checkout."), saved);
    host.append(source);
    const datasets = node("section", undefined, "workflow-datasets");
    datasets.append(node("h3", "Datasets"), node("p", "Example periods and latest phases", "muted small"));
    for (const [index, symbol] of ["ES", "NQ"].entries()) {
      const card = node("div", undefined, "workflow-dataset");
      card.append(node("strong", symbol), node("span", "2021-01-01 → 2024-12-31"), node("span", `Latest phase: ${campaign.stages[index]}`, "workflow-stage"));
      datasets.append(card);
    }
    host.append(datasets);
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
