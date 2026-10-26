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
  let instrumentTemplates = [], instrumentsAvailable = true;
  let coverageData = null, coverageDirty = false;
  let setupOffset = 0, resultOffset = 0;
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

  const noActivation = id => id?.endsWith("_no_activation");
  const pricingName = id => noActivation(id) ? "No activation fee" : "Standard";
  function profileLabel(view) {
    const p = view.display, fees = p.fee_defaults;
    const price = noActivation(p.id) ? `${fees?.attempt_fee ?? "unknown"} evaluation · no activation fee` :
      `${fees?.attempt_fee ?? "unknown"} evaluation + ${fees?.activation_fee ?? "unknown"} activation`;
    return `Apex 50K EOD · ${p.platform} · ${price} ${p.currency}`;
  }

  function showRules(view) {
    const target = get("#prop-rules"); target.replaceChildren();
    const p = view.display, phase = get("#prop-phase").value;
    const rules = p[phase];
    showFee(view);
    target.append(node("h3", `${p.platform} · ${pricingName(p.id)} · ${phase} · profile ${p.version}`));
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

  function selectedProfile() {
    return templates.find(t => t.snapshot.profile.id === get("#prop-profile").value);
  }

  function fillProfileFees() {
    const fees = selectedProfile()?.display.fee_defaults;
    get("#prop-profile-attempt-fee").value = fees?.attempt_fee ?? "";
    get("#prop-profile-activation-fee").value = fees?.activation_fee ?? "";
    get("#prop-profile-activation-fee").readOnly = noActivation(get("#prop-profile").value);
  }

  function showFee(view) {
    const phase = get("#prop-phase").value, fees = view.display.fee_defaults;
    const label = phase === "evaluation" ? "Evaluation attempt" : "Funded activation";
    const amount = fees?.[phase === "evaluation" ? "attempt_fee" : "activation_fee"];
    const override = get("#prop-fee-override").checked;
    get("#prop-fee-field").hidden = !override;
    get("#prop-fee").required = override;
    get("#prop-fee-label").textContent = `${label} fee override · USD`;
    const defaultText = amount == null ?
      `${label} fee: no profile default yet. Set it once under “Edit reusable account profile fees”, or use a simulation override.` :
      `${label} fee: ${amount} ${view.display.currency} from ${saved && !dirty ? "the saved" : "the selected"} profile · user supplied ${fees.configured_on}.${override ? " Simulation override enabled below." : " Applied automatically; no fee entry needed."}`;
    get("#prop-fee-summary").textContent = override ?
      `${label} fee: ${get("#prop-fee").value || "enter an amount"} ${view.display.currency} · user-supplied simulation override. ${defaultText}` : defaultText;
  }

  function calendarFields() {
    const advanced = get("#prop-coverage-mode").value === "advanced";
    get("#prop-advanced-coverage").hidden = !advanced;
    get("#prop-auto-coverage").hidden = advanced;
    const mode = get("#prop-calendar-mode").value;
    get("#prop-recurring-window").hidden = mode !== "weekday_approximation";
    get("#prop-explicit-calendar").hidden = mode !== "explicit";
    ["#prop-window-start", "#prop-window-end", "#prop-cadence"].forEach(s => get(s).required = advanced && mode === "weekday_approximation");
    get("#prop-calendar-mode").required = advanced;
    get("#prop-coverage").required = advanced;
    get("#prop-days").required = advanced && mode === "explicit";
    get("#prop-export-editor").hidden = get("#prop-export-profile").value !== "custom";
  }

  function renderCoverage(data, fillChoices = true) {
    coverageData = data;
    const target = get("#prop-coverage-summary"); target.replaceChildren();
    if (fillChoices) {
      const select = get("#prop-export-profile"); select.replaceChildren();
      const prompt = node("option", "Choose the exporter’s intended session and interval"); prompt.value = ""; select.append(prompt);
      (data?.presets ?? []).forEach(p => { const o = node("option", p.name); o.value = p.id; select.append(o); });
      const custom = node("option", "Custom export-session profile…"); custom.value = "custom"; select.append(custom);
      const p = data?.profile;
      select.value = p ? ((data.presets ?? []).some(item => item.id === p.id) ? p.id : "custom") : "";
      get("#prop-export-name").value = p?.name ?? "";
      get("#prop-export-first").value = p?.first_bar_time ?? "";
      get("#prop-export-last").value = p?.last_bar_time ?? "";
      get("#prop-export-interval").value = p?.bar_interval_seconds ?? data?.source?.suggested_interval_seconds ?? "";
      get("#prop-export-calendar").value = p?.calendar ?? "cme_equity_model";
    }
    const report = data?.coverage;
    get("#prop-coverage-status").textContent = !data ? "Advanced calendar loaded. Switch to automatic coverage to inspect the source and select a reusable profile." :
      data.status === "inspection_error" ? `Coverage inspection unavailable: ${data.error} Retry with Refresh coverage or use an advanced explicit calendar; no automatic coverage is authorized.` :
      data.status === "profile_required" ? `Source inspected: ${data.source.bar_count} bars. Observed interval suggestion: ${data.source.suggested_interval_seconds ?? "unknown"} seconds. Choose the intended export profile once.` :
      report?.status === "compatible" ? "Coverage matches the chosen export profile. Save and check source data for full financial reconciliation." :
      "Coverage is incomplete or incompatible. Missing bars and partial boundaries block saving and execution; no dates or bars were filled or dropped.";
    if (data?.calendar_model) target.append(node("p", `${data.calendar_model.version}. ${data.calendar_model.assumption}`));
    if (data?.profile?.calendar === "weekday_approximation") target.append(node("p", "Selected approximation: weekdays only, without holiday exceptions.", "prop-notice"));
    if (report) {
      const s = report.summary;
      target.append(table(["Covered sessions", "Zero-trade sessions", "Closed dates", "Holiday dates", "Early closes", "Missing bars", "Unexpected bars", "Partial sessions"],
        [[s.covered_sessions, s.zero_trade_sessions, s.closed_dates, s.holiday_dates, s.early_closes, s.missing_bars, s.unexpected_bars, s.partial_sessions]]));
      target.append(table(["Prop session date", "Coverage", "Expected bars", "Observed bars", "Missing", "Unexpected", "Trades", "Early close"],
        report.sessions.map(r => [r.trading_date, r.status, r.expected_bars, r.observed_bars, r.missing_bars, r.unexpected_bars, r.trade_count, r.early_close])));
      target.append(details("Captured source, export profile, and coverage identity", {source: data.source, profile: data.profile,
        profile_sha256: data.profile_sha256, calendar_sha256: report.calendar_sha256, calendar_model: data.calendar_model}));
    }
    get("#prop-coverage-count").textContent = report ? `${report.offset ?? 0}–${(report.offset ?? 0) + report.sessions.length} of ${report.total ?? report.sessions.length} session dates` : "";
    get("#prop-coverage-prev").disabled = !report || !(report.offset > 0);
    get("#prop-coverage-next").disabled = !report || (report.offset ?? 0) + report.sessions.length >= (report.total ?? report.sessions.length);
    calendarFields();
  }

  async function refreshCoverage(offset = 0, captured = false) {
    const local = controller;
    const endpoint = captured && saved?.coverage ? `${api}/setups/${saved.id}/coverage` : `${api}/sources/${source.source.id}/coverage`;
    const data = await read(`${endpoint}?offset=${offset}&limit=50`);
    if (local !== controller) return;
    coverageDirty = false;
    renderCoverage(data);
    if (!saved && data.account_start_utc) {
      get("#prop-start").value = data.account_start_utc;
      get("#prop-end").value = data.end_utc;
    }
    setBusy(false);
  }

  function instrumentFields() {
    const id = get("#prop-instrument-profile").value, custom = id === "custom";
    get("#prop-instrument-custom").hidden = !custom;
    ["#prop-symbol", "#prop-currency", "#prop-weight", "#prop-unit-url", "#prop-basis"].forEach(s => get(s).required = custom);
    const target = get("#prop-instrument-summary"); target.replaceChildren();
    if (custom) return true;
    if (!id) { target.append(node("p", "Choose an instrument profile to fill its units automatically.")); return false; }
    const candidate = saved && !dirty ? saved.instrument.profile : null;
    const captured = candidate?.profile.id === id ? candidate : null;
    const view = captured ? saved.instrument_profile_view : instrumentTemplates.find(t => t.snapshot.profile.id === id);
    const snapshot = view?.snapshot;
    if (!snapshot) { target.append(node("p", "Selected instrument template unavailable. Reload or choose a custom declaration.")); return false; }
    const p = view.display;
    target.append(table(["Instrument", "Currency", "Tick size", "Point value per contract", "Apex units per contract"],
      [[p.symbol, p.currency, p.tick_size, p.point_value, p.contract_limit_weight]]));
    const compatible = captured ? true : view.compatibility?.compatible !== false;
    target.append(node("p", captured ? "Saved instrument snapshot loaded; earlier settings are preserved." : compatible ?
      "Contract specifications match the saved backtest. Your selection declares its contract identity and currency wherever the source metadata is missing." :
      `Cannot use this profile: ${view.compatibility.issues.join(" ")} Correct the source backtest or select its actual instrument; the simulator will not convert it.`, compatible ? "" : "prop-notice"));
    const evidence = node("details"); evidence.append(node("summary", `${p.name} · version ${p.version} · sources and captured settings`));
    const list = node("ul");
    p.sources.forEach(s => {
      const li = node("li"), a = node("a", s.id); a.href = s.url;
      li.append(a, document.createTextNode(` · retrieved ${s.retrieved_on} · effective ${s.effective_on ?? "unknown"}`)); list.append(li);
    });
    evidence.append(list, node("p", `Instrument profile SHA-256: ${snapshot.profile_sha256}`, "prop-hash"));
    target.append(evidence);
    return compatible;
  }

  function setBusy(value) {
    busy = value;
    get("#prop-save-profile-fees").disabled = value || !templatesAvailable;
    const instrumentReady = instrumentFields();
    const preset = !["", "custom"].includes(get("#prop-instrument-profile").value);
    const coverageReady = get("#prop-coverage-mode").value === "advanced" || (!coverageDirty && coverageData?.status === "compatible");
    if (preset && !instrumentsAvailable) get("#prop-save-note").textContent = "Current instrument templates unavailable. The saved snapshot remains available for source checking and execution; reload before saving edits.";
    get("#prop-save").disabled = value || !templatesAvailable || (preset && !instrumentsAvailable) || !instrumentReady || !coverageReady || (Boolean(saved) && !dirty);
    get("#prop-remember-session").disabled = value || !get("#prop-export-profile").value;
    get("#prop-refresh-coverage").disabled = value;
    const report = coverageData?.coverage;
    get("#prop-coverage-prev").disabled = value || coverageDirty || !report || !(report.offset > 0);
    get("#prop-coverage-next").disabled = value || coverageDirty || !report || (report.offset ?? 0) + report.sessions.length >= (report.total ?? report.sessions.length);
    get("#prop-check").disabled = value || dirty || !saved;
    const evaluation = saved?.resolved.config.phase === "evaluation";
    get("#prop-run").disabled = value || dirty || !evaluation || saved?.latest_check?.status !== "compatible";
    get("#prop-run-note").textContent = saved && !evaluation ? "Funded execution is not implemented yet; funded setups and input checks remain available." :
      dirty ? "Save changed settings and check source data before running." : !saved || saved.latest_check?.status !== "compatible" ?
        "Save an evaluation setup and check source compatibility before running." : "Run historical evaluation using these captured settings. Source identity is revalidated; a compatibility check does not authorize changed inputs.";
    for (const input of get("#prop-form").querySelectorAll("input,select,textarea")) input.disabled = value;
  }

  function changed() {
    dirty = true;
    get("#prop-input-check").hidden = true;
    get("#prop-save-note").textContent = templatesAvailable ? "Unsaved settings. Save a new setup before checking inputs." : "Current templates unavailable. Reload to restore the saved setup or retry loading templates.";
    const template = templates.find(t => t.snapshot.profile.id === get("#prop-profile").value);
    if (template) showRules(template);
    setBusy(busy);
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
      "#prop-calendar-mode": data?.calendar?.mode ?? "", "#prop-coverage": data?.calendar?.coverage_assumption ?? "",
      "#prop-window-start": data?.calendar?.start_time ?? "", "#prop-window-end": data?.calendar?.end_time ?? "",
      "#prop-cadence": data?.calendar?.bar_interval_seconds ?? "", "#prop-days": data?.calendar?.days ? JSON.stringify(data.calendar.days, null, 2) : ""};
    Object.entries(values).forEach(([selector, value]) => get(selector).value = value);
    get("#prop-fee-override").checked = data?.fee != null;
    fillProfileFees();
    get("#prop-profile-fees").open = !selectedProfile()?.display.fee_defaults;
    const dataset = source.source.run_metadata.dataset;
    const match = instrumentTemplates.find(t => t.display.symbol === dataset.symbol && t.display.currency === dataset.currency && t.compatibility?.compatible);
    const instrumentId = data ? (data.instrument_profile_id ?? "custom") : match?.display.id ?? "";
    get("#prop-instrument-profile").value = instrumentId;
    get("#prop-coverage-mode").value = data?.calendar ? "advanced" : "automatic";
    calendarFields();
  }

  async function setupList(offset = 0) {
    const local = controller;
    const data = await read(`${api}/setups?source_backtest_id=${source.source.id}&offset=${offset}&limit=25`);
    if (local !== controller) return;
    setupOffset = offset;
    const target = get("#prop-setup-list"); target.replaceChildren();
    data.items.forEach(item => {
      const link = node("a", `${item.platform} · ${pricingName(item.profile_id)} · ${item.phase} · quantity ${item.quantity} · ${item.created_at_utc}`, "completed-run");
      link.href = `#backtests/prop/${item.id}`; target.append(link);
    });
    if (!data.total) target.append(node("p", "No saved setups for this backtest yet."));
    get("#prop-setups-prev").disabled = offset === 0;
    get("#prop-setups-next").disabled = offset + data.items.length >= data.total;
    get("#prop-setups-count").textContent = `${data.total} saved setups`;
  }

  async function resultList(offset = 0) {
    const local = controller;
    const target = get("#prop-results-list"); target.replaceChildren();
    get("#prop-results-prev").disabled = get("#prop-results-next").disabled = true;
    if (!saved) { target.textContent = "Save a setup first."; get("#prop-results-count").textContent = ""; return; }
    const data = await read(`${api}/results?setup_id=${saved.id}&offset=${offset}&limit=25`);
    if (local !== controller) return;
    resultOffset = offset;
    data.items.forEach(item => {
      const link = node("a", `${item.summary.outcome} · balance ${item.summary.balance} · ${item.created_at_utc}`, "completed-run");
      link.href = `#backtests/prop/result/${item.id}`; target.append(link);
    });
    if (!data.total) target.textContent = "No completed simulations for this setup yet.";
    get("#prop-results-count").textContent = `${data.total} saved results`;
    get("#prop-results-prev").disabled = offset === 0;
    get("#prop-results-next").disabled = offset + data.items.length >= data.total;
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
    get("#prop-title-text").textContent = "Prop simulation";
    get("#prop-intro").textContent = "Configure account rules and check your saved backtest’s source data.";
    get("#prop-workflow").hidden = true;
    get("#prop-saved").hidden = get("#prop-input-check").hidden = true;
    status("Loading prop setup…");
    saved = null; dirty = false; busy = false;
    try {
      let setup = null;
      if (!match[1]) setup = await read(`${api}/setups/${match[2]}`);
      let catalogAvailable = true;
      let instrumentCatalogAvailable = true;
      status("Loading setup and inspecting saved source timestamps. Large reports can take time…");
      const [context, profiles, instruments, coverage] = await Promise.all([
        setup ? Promise.resolve(setup.source_context) : read(`${api}/sources/${match[2]}`),
        read(`${api}/profiles`).catch(error => {
          if (!setup || error.name === "AbortError") throw error;
          catalogAvailable = false; return [setup.profile_view];
        }),
        read(`${api}/instrument-profiles?source_backtest_id=${setup?.source_backtest_id ?? match[2]}`).catch(error => {
          if (!setup || error.name === "AbortError") throw error;
          instrumentCatalogAvailable = false;
          return setup.instrument_profile_view ? [setup.instrument_profile_view] : [];
        }),
        setup ? Promise.resolve(setup.coverage ?? null) : read(`${api}/sources/${match[2]}/coverage`).catch(error => {
          if (error.name === "AbortError") throw error;
          return {status: "inspection_error", error: error.message};
        })
      ]);
      if (local !== controller) return;
      source = context; templates = profiles; saved = setup; templatesAvailable = catalogAvailable;
      instrumentTemplates = instruments; instrumentsAvailable = instrumentCatalogAvailable;
      const instrumentSelect = get("#prop-instrument-profile"); instrumentSelect.replaceChildren();
      const prompt = node("option", "Choose the contract traded by this backtest"); prompt.value = ""; instrumentSelect.append(prompt);
      instruments.forEach(view => { const p = view.display, option = node("option", `${p.symbol} · ${p.name}`); option.value = p.id; instrumentSelect.append(option); });
      const custom = node("option", "Custom / legacy declaration"); custom.value = "custom"; instrumentSelect.append(custom);
      get("#prop-profile").replaceChildren();
      profiles.forEach(view => { const option = node("option", profileLabel(view)); option.value = view.snapshot.profile.id; get("#prop-profile").append(option); });
      get("#prop-back").href = `#backtests/report/${context.source.id}`;
      get("#prop-back").textContent = "← Back to backtest report";
      const record = context.source;
      get("#prop-source").replaceChildren(node("p", `${record.run_metadata.dataset.name} · ${record.run_metadata.strategy.id} · ${record.summary.trades_taken} trades · net P&L ${record.summary.total_net_pnl} source currency units`),
        node("p", `Backtest ${record.id}`, "prop-hash"), details("Preserved strategy, dataset, execution, and selected dates", {metadata: record.run_metadata, execution_settings: record.execution_settings, execution_assumption: record.execution_assumption}));
      get("#prop-execution-units").textContent = `Saved tick size ${record.execution_settings.tick_size}; monetary point value ${record.execution_settings.point_value} per point per contract. These captured values are preserved.`;
      get("#prop-calendar-range").textContent = `Declare all session dates from ${context.first_session_date} through ${context.last_session_date}.`;
      fillForm(setup?.declaration);
      coverageDirty = false; renderCoverage(coverage);
      if (!setup && coverage?.account_start_utc) {
        get("#prop-start").value = coverage.account_start_utc;
        get("#prop-end").value = coverage.end_utc;
      }
      showRules(setup?.profile_view ?? profiles[0]);
      get("#prop-saved").hidden = !setup;
      get("#prop-save").textContent = setup ? "Save new setup" : "Save setup";
      get("#prop-save-note").textContent = !catalogAvailable ? "Current templates unavailable; saved rules remain available for source checking." : setup ? "Saved snapshot loaded. Edits will use the selected current template when saved as a new setup." : "Save these settings before checking source data.";
      if (setup) {
        get("#prop-saved-id").textContent = `Setup ${setup.id} · ${setup.created_at_utc} · draft`;
        get("#prop-setup-downloads").replaceChildren();
        downloads(get("#prop-setup-downloads"), `${api}/setups/${setup.id}`, ["setup.json", "profile.json", "simulation.json", "calendar.json", ...(setup.instrument.profile ? ["instrument.json"] : []), ...(setup.coverage ? ["coverage.json"] : [])]);
      }
      get("#prop-workflow").hidden = false;
      setBusy(false); status(setup ? "Saved setup loaded." : "Configure this backtest’s prop setup.");
      await Promise.all([setupList(0), resultList(0), setup?.latest_check ? renderCheck(setup.latest_check, local) : Promise.resolve()]);
    } catch (error) { if (error.name !== "AbortError" && local === controller) status(error.message); }
  }

  get("#prop-form").addEventListener("input", event => {
    if (event.target.closest("#prop-export-editor") || event.target.id === "prop-export-profile") coverageDirty = true;
    changed();
  });
  get("#prop-form").addEventListener("change", () => { calendarFields(); changed(); });
  function resetFeeOverride() {
    get("#prop-fee-override").checked = false;
    get("#prop-fee").value = "";
    fillProfileFees();
  }
  get("#prop-phase").addEventListener("change", resetFeeOverride);
  get("#prop-profile").addEventListener("change", resetFeeOverride);
  get("#prop-remember-session").onclick = async () => {
    if (busy) return;
    const local = controller;
    try {
      const id = get("#prop-export-profile").value;
      const clock = selector => get(selector).value.length === 5 ? get(selector).value + ":00" : get(selector).value;
      const body = id !== "custom" ? {preset_id: id} : {custom: {id: "custom_export", version: "1.0.0", name: get("#prop-export-name").value,
        calendar: get("#prop-export-calendar").value, window: "custom", bar_interval_seconds: Number(get("#prop-export-interval").value),
        first_bar_time: clock("#prop-export-first"), last_bar_time: clock("#prop-export-last"), timezone: "America/New_York"}};
      setBusy(true); status("Saving the dataset export profile and checking expected coverage…");
      await read(`${api}/sources/${source.source.id}/session-profile`, {method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
      if (local !== controller) return;
      await refreshCoverage();
      if (local !== controller) return;
      changed();
      status("Dataset session profile saved. Review the coverage summary before saving the simulation setup.");
    } catch (error) { if (error.name !== "AbortError" && local === controller) status(`Session profile or coverage could not be applied: ${error.message}`); }
    finally { if (local === controller) setBusy(false); }
  };
  get("#prop-refresh-coverage").onclick = async () => {
    if (busy) return;
    const local = controller;
    try {
      setBusy(true); await refreshCoverage();
      if (local !== controller) return;
      changed(); status("Coverage refreshed from the saved source and dataset profile.");
    }
    catch (error) { if (error.name !== "AbortError" && local === controller) { coverageDirty = true; status(`Coverage refresh failed: ${error.message}`); } }
    finally { if (local === controller) setBusy(false); }
  };
  get("#prop-coverage-prev").onclick = () => refreshCoverage(Math.max(0, (coverageData?.coverage?.offset ?? 0) - 50), Boolean(saved && !dirty)).catch(e => status(e.message));
  get("#prop-coverage-next").onclick = () => refreshCoverage((coverageData?.coverage?.offset ?? 0) + 50, Boolean(saved && !dirty)).catch(e => status(e.message));
  get("#prop-save-profile-fees").onclick = async () => {
    if (busy || !templatesAvailable) return;
    const local = controller;
    try {
      setBusy(true);
      const body = {attempt_fee: get("#prop-profile-attempt-fee").value || null,
        activation_fee: get("#prop-profile-activation-fee").value || null};
      const view = await read(`${api}/profiles/${get("#prop-profile").value}/fees`, {
        method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
      if (local !== controller) return;
      templates = templates.map(t => t.snapshot.profile.id === view.snapshot.profile.id ? view : t);
      Array.from(get("#prop-profile").options).find(option => option.value === view.snapshot.profile.id).textContent = profileLabel(view);
      changed();
      status("Profile fees saved. Save a new setup to capture these defaults; earlier setups and results are unchanged.");
    } catch (error) { if (error.name !== "AbortError" && local === controller) status(`Profile fees not saved: ${error.message}`); }
    finally { if (local === controller) setBusy(false); }
  };
  get("#prop-form").addEventListener("submit", async event => {
    event.preventDefault(); if (busy) return;
    const local = controller;
    try {
      const value = selector => get(selector).value;
      const body = {source_backtest_id: source.source.id, profile_id: value("#prop-profile"), phase: value("#prop-phase"),
        observation_mode: value("#prop-mode"), quantity: Number(value("#prop-quantity")), fee: get("#prop-fee-override").checked ? value("#prop-fee") : null,
        account_start_utc: value("#prop-start"), end_utc: value("#prop-end")};
      if (value("#prop-coverage-mode") === "advanced") {
        const calendar = {mode: value("#prop-calendar-mode"), coverage_assumption: value("#prop-coverage")};
        if (calendar.mode === "explicit") calendar.days = JSON.parse(value("#prop-days"));
        else Object.assign(calendar, {start_time: value("#prop-window-start"), end_time: value("#prop-window-end"), bar_interval_seconds: Number(value("#prop-cadence"))});
        body.calendar = calendar;
      }
      else body.source_session_profile_sha256 = coverageData.profile_sha256;
      if (value("#prop-instrument-profile") === "custom") Object.assign(body, {instrument_symbol: value("#prop-symbol"),
        currency: value("#prop-currency"), contract_limit_weight: value("#prop-weight"), contract_limit_source_url: value("#prop-unit-url"),
        instrument_basis: value("#prop-basis")});
      else body.instrument_profile_id = value("#prop-instrument-profile");
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
      status(result.status === "compatible" ? "Source check complete. Historical evaluation is ready; funded execution remains unavailable." : "Source check rejected. Review the reason and save corrected settings.");
    } catch (error) { if (error.name !== "AbortError" && local === controller) status(`Source check unavailable: ${error.message}`); }
    finally { if (local === controller) setBusy(false); }
  };
  get("#prop-run").onclick = async () => {
    if (!saved || dirty || busy || get("#prop-run").disabled) return;
    const local = controller;
    setBusy(true); status("Revalidating source and running historical evaluation…");
    try {
      const result = await read(`${api}/setups/${saved.id}/run`, {method: "POST"});
      if (local === controller) location.hash = `#backtests/prop/result/${result.id}`;
    } catch (error) {
      if (error.name !== "AbortError" && local === controller) status(`Simulation operation failed: ${error.message} No financial outcome is reported for a failed operation. Reload to check saved results before retrying an interrupted request.`);
    } finally { if (local === controller) setBusy(false); }
  };
  get("#prop-results-prev").onclick = () => resultList(Math.max(0, resultOffset - 25)).catch(e => status(e.message));
  get("#prop-results-next").onclick = () => resultList(resultOffset + 25).catch(e => status(e.message));
  get("#prop-setups-prev").onclick = () => setupList(Math.max(0, setupOffset - 25)).catch(e => status(e.message));
  get("#prop-setups-next").onclick = () => setupList(setupOffset + 25).catch(e => status(e.message));
  window.addEventListener("hashchange", navigate); navigate();
})();
