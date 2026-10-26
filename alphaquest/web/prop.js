"use strict";

(() => {
  const get = selector => document.querySelector(selector);
  const api = "/api/prop-simulations";
  const node = (tag, text, className) => {
    const item = document.createElement(tag);
    if (text !== undefined) item.textContent = text;
    if (className) item.className = className;
    return item;
  };
  let controller, source, templates, saved, dirty, templatesAvailable = true, busy = false;
  let setupOffset = 0;
  const status = message => { get("#prop-status").textContent = message; };

  async function read(url, options = {}, signal = controller?.signal) {
    const response = await fetch(url, {...options, signal, cache: "no-store"});
    let result;
    try { result = await response.json(); } catch (_) { throw new Error(`Request failed (HTTP ${response.status}).`); }
    if (!response.ok) {
      const detail = Array.isArray(result.detail) ? result.detail.map(e => `${e.loc.join(".")}: ${e.msg}`).join("; ") : result.detail;
      throw new Error(detail || `Request failed (HTTP ${response.status}).`);
    }
    return result;
  }

  function table(headers, rows) {
    const wrapper = node("div", undefined, "report-table-scroll");
    const table = node("table", undefined, "prop-table");
    const head = node("thead"), tr = node("tr"), body = node("tbody");
    headers.forEach(label => tr.append(node("th", label)));
    head.append(tr);
    rows.forEach(row => {
      const tr = node("tr");
      row.forEach(value => tr.append(node("td", value == null ? "—" : String(value))));
      body.append(tr);
    });
    table.append(head, body); wrapper.append(table);
    return wrapper;
  }

  function details(title, value) {
    const item = node("details");
    item.append(node("summary", title), node("pre", JSON.stringify(value, null, 2)));
    return item;
  }

  function downloads(parent, base, files) {
    files.forEach(name => {
      const link = node("a", name, "button secondary");
      link.href = `${base}/exports/${name}`; link.download = ""; parent.append(link);
    });
  }

  function showRules(view) {
    const target = get("#prop-rules"); target.replaceChildren();
    const p = view.display, phase = get("#prop-phase").value;
    const rules = p[phase];
    target.append(node("h3", `${p.platform} · ${phase} · profile ${p.version}`));
    const rows = [["Initial balance", rules.initial_balance], ["Trailing drawdown", rules.drawdown.amount],
      ["Lock profit", rules.drawdown.lock_profit ?? "No lock"], ["Session timezone", p.session.timezone]];
    if (phase === "evaluation") rows.push(["Profit target", rules.profit_target], ["Daily loss limit", rules.limits.daily_loss_limit],
      ["Maximum contracts", rules.limits.max_contracts], ["Access deadline", `${rules.access_calendar_days} calendar days`]);
    target.append(table(["Rule", "Value"], rows));
    if (phase === "funded") {
      target.append(node("h3", "Limits by prior-session profit"), table(["Inclusive minimum profit", "Maximum contracts", "Daily loss limit"],
        rules.tiers.map(t => [t.minimum_profit, t.limits.max_contracts, t.limits.daily_loss_limit])));
      target.append(node("p", "Negative prior-session profits use the first tier. Each following minimum starts a new tier."));
      target.append(details("Payout eligibility, withdrawals, and inactivity", {payouts: rules.payouts, inactivity: rules.inactivity}));
    }
    p.evidence.filter(e => e.status === "source_conflict").forEach(e => target.append(node("p", e.note, "prop-notice")));
    const evidence = node("details"); evidence.append(node("summary", "Sources, assumptions, and captured profile identity"));
    evidence.append(node("p", `Profile SHA-256: ${view.snapshot.profile_sha256}`, "prop-hash"));
    evidence.append(node("p", "Retrieval dates describe the saved rules review. Unknown effective dates remain unspecified; sources are not rechecked when this setup is opened."));
    const list = node("ul");
    p.sources.forEach(s => {
      const li = node("li"), link = node("a", s.id); link.href = s.url;
      li.append(link, document.createTextNode(` · retrieved ${s.retrieved_on} · effective ${s.effective_on ?? "unknown"}`)); list.append(li);
    });
    evidence.append(list, details("Verified rules and modeling assumptions", {evidence: p.evidence, assumptions: p.assumptions}));
    target.append(evidence);
  }

  function calendarFields() {
    const mode = get("#prop-calendar-mode").value;
    get("#prop-recurring-window").hidden = mode !== "weekday_approximation";
    get("#prop-explicit-calendar").hidden = mode !== "explicit";
    ["#prop-window-start", "#prop-window-end", "#prop-cadence"].forEach(s => get(s).required = mode === "weekday_approximation");
    get("#prop-days").required = mode === "explicit";
  }

  function setBusy(value) {
    busy = value;
    get("#prop-save").disabled = value || !templatesAvailable || (Boolean(saved) && !dirty);
    get("#prop-check").disabled = value || dirty || !saved;
    for (const input of get("#prop-form").querySelectorAll("input,select,textarea")) input.disabled = value;
  }

  function changed() {
    dirty = true;
    get("#prop-input-check").hidden = true;
    get("#prop-save-note").textContent = templatesAvailable ? "Unsaved settings. Save a new setup before checking inputs." : "Current templates unavailable. Reload to restore the saved setup or retry loading templates.";
    const template = templates.find(t => t.snapshot.profile.id === get("#prop-profile").value);
    if (template) showRules(template);
    setBusy(false);
  }

  function fillForm(data) {
    get("#prop-form").reset();
    const values = {"#prop-profile": data?.profile_id ?? templates[0].snapshot.profile.id,
      "#prop-phase": data?.phase ?? "evaluation", "#prop-mode": data?.observation_mode ?? "bar_close",
      "#prop-quantity": data?.quantity ?? source.source.run_metadata.strategy.parameters.contracts ?? "",
      "#prop-fee": data?.fee ?? "", "#prop-start": data?.account_start_utc ?? source.account_start_utc,
      "#prop-end": data?.end_utc ?? source.end_utc, "#prop-symbol": data?.instrument_symbol ?? source.source.run_metadata.dataset.symbol ?? "",
      "#prop-currency": data?.currency ?? "", "#prop-weight": data?.contract_limit_weight ?? "",
      "#prop-unit-url": data?.contract_limit_source_url ?? "", "#prop-basis": data?.instrument_basis ?? "",
      "#prop-calendar-mode": data?.calendar.mode ?? "", "#prop-coverage": data?.calendar.coverage_assumption ?? "",
      "#prop-window-start": data?.calendar.start_time ?? "", "#prop-window-end": data?.calendar.end_time ?? "",
      "#prop-cadence": data?.calendar.bar_interval_seconds ?? "", "#prop-days": data?.calendar.days ? JSON.stringify(data.calendar.days, null, 2) : ""};
    Object.entries(values).forEach(([selector, value]) => get(selector).value = value);
    get("#prop-fee-label").textContent = `${get("#prop-phase").value === "evaluation" ? "Evaluation attempt" : "Funded activation"} fee · USD`;
    calendarFields();
  }

  async function setupList(offset = 0) {
    const local = controller;
    const data = await read(`${api}/setups?source_backtest_id=${source.source.id}&offset=${offset}&limit=25`);
    if (local !== controller) return;
    setupOffset = offset;
    const target = get("#prop-setup-list"); target.replaceChildren();
    data.items.forEach(item => {
      const link = node("a", `${item.platform} · ${item.phase} · quantity ${item.quantity} · ${item.created_at_utc}`, "completed-run");
      link.href = `#backtests/prop/${item.id}`; target.append(link);
    });
    if (!data.total) target.append(node("p", "No saved setups for this backtest yet."));
    get("#prop-setups-prev").disabled = offset === 0;
    get("#prop-setups-next").disabled = offset + data.items.length >= data.total;
    get("#prop-setups-count").textContent = `${data.total} saved setups`;
  }

  async function renderCheck(check, local = controller) {
    if (local !== controller) return;
    const target = get("#prop-check-result"); target.replaceChildren();
    get("#prop-input-check").hidden = false;
    target.append(node("p", check.status === "compatible" ? "Source inputs are compatible with this setup." : `Source inputs rejected: ${check.error}`,
      check.status === "compatible" ? "prop-pass" : "prop-fail"));
    target.append(node("p", `Checked ${check.created_at_utc}. This is an input compatibility check; account rules have not been simulated.`));
    const links = node("div", undefined, "report-downloads");
    downloads(links, `${api}/checks/${check.id}`, check.status === "compatible" ? ["check.json", "source.json", "sessions.csv", "observations.csv"] : ["check.json"]);
    target.append(links);
    if (check.status !== "compatible") return;
    const s = check.summary;
    target.append(table(["Source quantity", "Comparison quantity", "Source net P&L", "Comparison net P&L", "Covered zero-trade sessions"],
      [[s.source_contracts ?? "No trades", s.quantity, s.source_net_pnl, s.net_pnl, s.zero_trade_sessions]]));
    target.append(table(["Gross P&L", "Commissions · included", "Slippage · included, informational", "Source bars", "Source trades"],
      [[s.gross_pnl, s.total_commissions, s.slippage_cost, s.source_bar_count, s.source_trade_count]]));
    target.append(node("p", "Existing costs are counted once. Observation P&L is cumulative relative to each trade’s pre-entry equity; do not sum bar marks. Flat observations have zero trade-relative change."));
    const sessionPreview = node("div"), observationPreview = node("div");
    const sessionControls = node("div", undefined, "prop-actions");
    const sessionPrev = node("button", "Previous sessions", "button secondary"), sessionNext = node("button", "Next sessions", "button secondary"), sessionCount = node("span");
    sessionPrev.type = sessionNext.type = "button";
    sessionControls.append(sessionPrev, sessionNext, sessionCount);
    const mode = node("select"), filter = node("input"); mode.id = "prop-preview-mode"; filter.id = "prop-preview-date"; filter.type = "date";
    ["bar_close", "trade_close"].forEach(value => { const option = node("option", value === "bar_close" ? "Bar close" : "Trade close"); option.value = value; mode.append(option); });
    mode.value = saved.resolved.config.observation_mode;
    const filterRow = node("div", undefined, "prop-fields");
    const modeLabel = node("label", "Preview observation mode"), dateLabel = node("label", "Session date · optional");
    modeLabel.append(mode); dateLabel.append(filter); filterRow.append(modeLabel, dateLabel);
    const observationControls = node("div", undefined, "prop-actions");
    const obsPrev = node("button", "Previous observations", "button secondary"), obsNext = node("button", "Next observations", "button secondary"), obsCount = node("span");
    obsPrev.type = obsNext.type = "button"; observationControls.append(obsPrev, obsNext, obsCount);
    target.append(node("h3", "Sessions"), sessionPreview, sessionControls, node("h3", "Observation preview"), filterRow, observationPreview, observationControls);
    let sessionOffset = 0, observationOffset = 0, observationVersion = 0;
    async function sessions(offset) {
      sessionPrev.disabled = sessionNext.disabled = true;
      try {
        const data = await read(`${api}/checks/${check.id}/sessions?offset=${offset}&limit=50`, {}, local.signal);
        if (local !== controller || !target.contains(sessionPreview)) return;
        sessionOffset = offset;
        sessionPreview.replaceChildren(table(["Session date", "Coverage", "Open UTC", "Bars", "Trades", "Net P&L"],
          data.items.map(s => [s.trading_date, s.status, s.open_utc, s.bar_count, s.trade_count, s.net_pnl])));
        sessionCount.textContent = `${offset + data.items.length} of ${data.total} sessions`;
        sessionPrev.disabled = offset === 0; sessionNext.disabled = offset + data.items.length >= data.total;
      } catch (error) { if (error.name !== "AbortError") sessionPreview.textContent = error.message; }
    }
    async function observations(offset) {
      const version = ++observationVersion;
      obsPrev.disabled = obsNext.disabled = true;
      observationPreview.textContent = "Loading observations…";
      try {
        const query = new URLSearchParams({offset, limit: 50, mode: mode.value});
        if (filter.value) query.set("trading_date", filter.value);
        const data = await read(`${api}/checks/${check.id}/observations?${query}`, {}, local.signal);
        if (version !== observationVersion || local !== controller || !target.contains(observationPreview)) return;
        observationOffset = offset;
        observationPreview.replaceChildren(table(["Session", "Timestamp UTC", "Trade", "Source quantity", "Position quantity", "Source equity", "Trade-relative P&L"],
          data.items.map(o => [o.trading_date, o.timestamp_utc, o.trade_number, o.source_contracts, o.position_contracts, o.source_equity, o.equity_change])));
        obsCount.textContent = `${offset + data.items.length} of ${data.total} observations`;
        obsPrev.disabled = offset === 0; obsNext.disabled = offset + data.items.length >= data.total;
      } catch (error) { if (error.name !== "AbortError" && version === observationVersion) observationPreview.textContent = error.message; }
    }
    sessionPrev.onclick = () => sessions(Math.max(0, sessionOffset - 50)); sessionNext.onclick = () => sessions(sessionOffset + 50);
    obsPrev.onclick = () => observations(Math.max(0, observationOffset - 50)); obsNext.onclick = () => observations(observationOffset + 50);
    mode.onchange = filter.onchange = () => observations(0);
    await Promise.all([sessions(0), observations(0)]);
  }

  async function navigate() {
    controller?.abort(); controller = new AbortController();
    const local = controller;
    const match = location.hash.match(/^#backtests\/prop\/(?:(new)\/)?([0-9a-f]{32})$/);
    if (!match) return;
    get("#prop-workflow").hidden = true;
    get("#prop-saved").hidden = get("#prop-input-check").hidden = true;
    status("Loading prop setup…");
    saved = null; dirty = false; busy = false;
    try {
      let setup = null;
      if (!match[1]) setup = await read(`${api}/setups/${match[2]}`);
      let catalogAvailable = true;
      const [context, profiles] = await Promise.all([
        setup ? Promise.resolve(setup.source_context) : read(`${api}/sources/${match[2]}`),
        read(`${api}/profiles`).catch(error => {
          if (!setup || error.name === "AbortError") throw error;
          catalogAvailable = false; return [setup.profile_view];
        })
      ]);
      if (local !== controller) return;
      source = context; templates = profiles; saved = setup; templatesAvailable = catalogAvailable;
      get("#prop-profile").replaceChildren();
      profiles.forEach(view => { const option = node("option", `Apex 50K EOD · ${view.display.platform}`); option.value = view.snapshot.profile.id; get("#prop-profile").append(option); });
      get("#prop-back").href = `#backtests/report/${context.source.id}`;
      const record = context.source;
      get("#prop-source").replaceChildren(node("p", `${record.run_metadata.dataset.name} · ${record.run_metadata.strategy.id} · ${record.summary.trades_taken} trades · net P&L ${record.summary.total_net_pnl} source currency units`),
        node("p", `Backtest ${record.id}`, "prop-hash"), details("Preserved strategy, dataset, execution, and selected dates", {metadata: record.run_metadata, execution_settings: record.execution_settings, execution_assumption: record.execution_assumption}));
      get("#prop-execution-units").textContent = `Saved tick size ${record.execution_settings.tick_size}; monetary point value ${record.execution_settings.point_value} per point per contract. These captured values are preserved.`;
      get("#prop-calendar-range").textContent = `Declare all session dates from ${context.first_session_date} through ${context.last_session_date}.`;
      fillForm(setup?.declaration);
      showRules(setup?.profile_view ?? profiles[0]);
      get("#prop-saved").hidden = !setup;
      get("#prop-save").textContent = setup ? "Save new setup" : "Save setup";
      get("#prop-save-note").textContent = !catalogAvailable ? "Current templates unavailable; saved rules remain available for source checking." : setup ? "Saved snapshot loaded. Edits will use the selected current template when saved as a new setup." : "Save these settings before checking source data.";
      if (setup) {
        get("#prop-saved-id").textContent = `Setup ${setup.id} · ${setup.created_at_utc} · draft`;
        get("#prop-setup-downloads").replaceChildren();
        downloads(get("#prop-setup-downloads"), `${api}/setups/${setup.id}`, ["setup.json", "profile.json", "simulation.json", "calendar.json"]);
      }
      get("#prop-workflow").hidden = false;
      setBusy(false); status(setup ? "Saved setup loaded." : "Configure this backtest’s prop setup.");
      await Promise.all([setupList(0), setup?.latest_check ? renderCheck(setup.latest_check, local) : Promise.resolve()]);
    } catch (error) { if (error.name !== "AbortError" && local === controller) status(error.message); }
  }

  get("#prop-form").addEventListener("input", changed);
  get("#prop-form").addEventListener("change", () => { calendarFields(); changed(); });
  get("#prop-phase").addEventListener("change", () => {
    get("#prop-fee").value = "";
    get("#prop-fee-label").textContent = `${get("#prop-phase").value === "evaluation" ? "Evaluation attempt" : "Funded activation"} fee · USD`;
  });
  get("#prop-form").addEventListener("submit", async event => {
    event.preventDefault(); if (busy) return;
    const local = controller;
    try {
      const value = selector => get(selector).value;
      const calendar = {mode: value("#prop-calendar-mode"), coverage_assumption: value("#prop-coverage")};
      if (calendar.mode === "explicit") calendar.days = JSON.parse(value("#prop-days"));
      else Object.assign(calendar, {start_time: value("#prop-window-start"), end_time: value("#prop-window-end"), bar_interval_seconds: Number(value("#prop-cadence"))});
      const body = {source_backtest_id: source.source.id, profile_id: value("#prop-profile"), phase: value("#prop-phase"),
        observation_mode: value("#prop-mode"), quantity: Number(value("#prop-quantity")), fee: value("#prop-fee"),
        account_start_utc: value("#prop-start"), end_utc: value("#prop-end"), instrument_symbol: value("#prop-symbol"),
        currency: value("#prop-currency"), contract_limit_weight: value("#prop-weight"), contract_limit_source_url: value("#prop-unit-url"),
        instrument_basis: value("#prop-basis"), calendar};
      setBusy(true); status("Saving setup…");
      const result = await read(`${api}/setups`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
      if (local === controller) location.hash = `#backtests/prop/${result.id}`;
    } catch (error) { if (error.name !== "AbortError" && local === controller) status(`Setup not saved: ${error.message}`); }
    finally { if (local === controller) setBusy(false); }
  });
  get("#prop-check").onclick = async () => {
    if (!saved || dirty || busy) return;
    const local = controller;
    setBusy(true); get("#prop-input-check").hidden = true; status("Checking the complete saved source. Large backtests may take some time…");
    try {
      const result = await read(`${api}/setups/${saved.id}/check`, {method: "POST"});
      if (local !== controller) return;
      saved.latest_check = result;
      await renderCheck(result, local);
      status(result.status === "compatible" ? "Source check complete. Account simulation is not yet available." : "Source check rejected. Review the reason and save corrected settings.");
    } catch (error) { if (error.name !== "AbortError" && local === controller) status(`Source check unavailable: ${error.message}`); }
    finally { if (local === controller) setBusy(false); }
  };
  get("#prop-setups-prev").onclick = () => setupList(Math.max(0, setupOffset - 25)).catch(e => status(e.message));
  get("#prop-setups-next").onclick = () => setupList(setupOffset + 25).catch(e => status(e.message));
  window.addEventListener("hashchange", navigate); navigate();
})();
