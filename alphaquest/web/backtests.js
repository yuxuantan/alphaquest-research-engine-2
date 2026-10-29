"use strict";

(() => {
  const get = (selector) => document.querySelector(selector);
  const form = get("#backtest-form");
  const datasetSelect = get("#backtest-dataset");
  const strategySelect = get("#backtest-strategy");
  const fromDate = get("#backtest-from-date");
  const toDate = get("#backtest-to-date");
  const start = get("#start-backtest");
  const refresh = get("#refresh-backtest-choices");
  const resetInstrument = get("#reset-instrument-defaults");
  const tickSize = get("#backtest-tick-size");
  const pointValue = get("#backtest-point-value");
  const count = new Intl.NumberFormat("en-US");
  const state = { datasets: [], strategies: [], busy: false, loading: false, ready: false, strategy: null, instrumentEdited: false };
  const drafts = new Map();
  let reportRecord, detailedBusy = false;
  const mode = get("#backtest-mode");
  const optimizing = () => mode.value === "exhaustive";
  const executionLabels = {
    initial_capital: "Initial capital", tick_size: "Tick size", point_value: "Monetary point value",
    slippage_ticks: "Slippage · ticks per fill", commission_per_contract_per_side: "Commission · per contract per side",
  };
  const label = (name) => name === "contracts" ? "Number of contracts" : String(name).replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase());

  function element(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined) el.textContent = text;
    return el;
  }

  function selectedDataset() {
    return state.datasets.find((item) => item.id === datasetSelect.value);
  }

  function controls() {
    mode.disabled=state.busy || state.loading;
    for (const fieldset of form.querySelectorAll("fieldset")) fieldset.disabled = state.busy || state.loading;
    for (const input of get("#strategy-parameters").querySelectorAll("input")) input.disabled = optimizing() || state.busy || state.loading;
    for (const input of get("#optimization-settings").querySelectorAll("input, select")) input.disabled = !optimizing() || state.busy || state.loading;
    get("#backtest-reuse").disabled=optimizing() || state.busy || state.loading;
    get("#optimization-workers").disabled = !optimizing() || state.busy || state.loading || !window.optimizations.workersReady();
    get("#optimization-workers-retry").disabled = state.busy || state.loading;
    refresh.disabled = state.busy || state.loading;
    resetInstrument.disabled = state.busy || state.loading || !selectedDataset()?.instrument_settings;
    start.disabled = state.busy || state.loading || !state.ready || !state.strategy || !selectedDataset()?.instrument_settings || !window.researchSplit.ready() || (optimizing() && !window.optimizations.workersReady());
    start.textContent = state.busy ? "Submitting / running…" : optimizing() ? "Start backtests →" : "Start backtest →";
    form.setAttribute("aria-busy", String(state.busy));
  }

  function showError(error, title = "Backtest needs attention") {
    const box = get("#backtest-error");
    box.replaceChildren(element("strong", "validation-title", title));
    const message = typeof error.detail === "string" ? error.detail : error.message || "The request failed. Check the server connection.";
    box.append(element("p", "", message));
    if (Array.isArray(error.detail)) {
      const list = element("ul");
      for (const item of error.detail) {
        const location = (item.loc || []).filter((key) => key !== "body").map(label).join(" › ");
        list.append(element("li", "", `${location ? location + ": " : ""}${item.msg}`));
      }
      box.append(list);
    }
    box.hidden = false;
    if (!get("#backtests-screen").hidden) {
      box.focus({ preventScroll: true });
      box.scrollIntoView({ block: "nearest" });
    }
  }

  async function readResponse(response) {
    let result;
    try { result = await response.json(); }
    catch { throw new Error(`The server returned an unreadable response (HTTP ${response.status}).`); }
    if (!response.ok) throw { ...result, status: response.status };
    return result;
  }

  function rememberParameters() {
    if (!state.strategy) return;
    drafts.set(state.strategy.id, Object.fromEntries(Array.from(get("#strategy-parameters").querySelectorAll("input"), (input) => [input.dataset.parameter, input.type === "checkbox" ? input.checked : input.value])));
  }

  function renderStrategy() {
    rememberParameters();
    const strategy = state.strategies.find((item) => item.id === strategySelect.value);
    state.strategy = strategy || null;
    const fields = get("#strategy-parameters");
    fields.replaceChildren();
    get("#strategy-description").textContent = strategy?.description || "Select a strategy to see its description.";
    if (strategy) {
      for (const parameter of strategy.parameters) {
        if (!["int", "integer", "bool", "Decimal"].includes(parameter.type)) {
          state.strategy = null;
          showError({ message: "This strategy uses a parameter type this screen does not support." });
          break;
        }
        const wrapper = element("label", "", label(parameter.name));
        const input = element("input");
        input.id = `strategy-${parameter.name}`;
        input.name = parameter.name;
        input.dataset.parameter = parameter.name;
        input.dataset.type = parameter.type;
        const saved = drafts.get(strategy.id)?.[parameter.name] ?? parameter.default;
        if (parameter.type === "bool") {
          input.type = "checkbox";
          input.checked = saved === true;
        } else if (parameter.type === "Decimal") {
          input.type = "text";
          input.inputMode = "decimal";
          input.dataset.decimal = "nonnegative";
          input.required = true;
          input.value = String(saved ?? "");
        } else {
          input.dataset.integer = "";
          input.type = "number";
          input.step = "1";
          input.max = String(parameter.maximum ?? Number.MAX_SAFE_INTEGER);
          if (parameter.minimum !== undefined) input.min = String(parameter.minimum);
          input.required = true;
          input.value = String(saved ?? "");
        }
        const help = element("span", "field-help", parameter.description);
        help.id = `${input.id}-help`;
        input.setAttribute("aria-describedby", help.id);
        input.setAttribute("aria-label", label(parameter.name));
        wrapper.append(input, help);
        fields.append(wrapper);
      }
    }
    get("#backtest-fill-assumption").textContent = strategy?.execution_assumption?.startsWith("next_open_market_next_bar_bracket_stop_first")
      ? "Signals use completed closes. Market orders fill at the next observed bar Open. Brackets begin after the entry bar; ambiguous bars use stop first. With EOD flatten enabled, BACKTEST LOOKAHEAD uses the last daytime bar to infer each session close, then closes five minutes earlier (at/before 15:55 CT) and blocks later entries. A missing cutoff minute uses the preceding available bar. Truncated data is treated as an early close. Use full-session one-minute data."
      : "Signals and simulated fills use that same close, adjusted by your slippage setting.";
    window.optimizations.configure(strategy);
    window.researchSplit.configure(datasetSelect.value,strategySelect.value);
    controls();
  }

  function renderDataset(resetValues = true) {
    const dataset = selectedDataset();
    window.researchSplit.configure(datasetSelect.value,strategySelect.value);
    get("#backtest-dataset-info").textContent = dataset
      ? `${count.format(dataset.row_count)} bars · ${dataset.filename} · ${dataset.start.replace("T", " ").replace("Z", " UTC")} to ${dataset.end.replace("T", " ").replace("Z", " UTC")}`
      : "Choose a saved dataset. New datasets can be uploaded and saved in Datasets.";
    get("#backtest-timezone").textContent = dataset?.source_timezone || "Choose a dataset";
    const settings = dataset?.instrument_settings;
    const grid = get("#backtest-instrument-settings");
    grid.replaceChildren();
    for (const [key, title] of [["tick_size", "Tick size"], ["point_value", "Monetary point value"]]) {
      const pair = element("div");
      pair.dataset.instrument = key;
      pair.append(element("dt", "", `Dataset default · ${title}`), element("dd", "", settings?.[key] || "Not set"));
      grid.append(pair);
    }
    if (resetValues) {
      tickSize.value = settings?.tick_size || "";
      pointValue.value = settings?.point_value || "";
      tickSize.setCustomValidity("");
      pointValue.setCustomValidity("");
      state.instrumentEdited = false;
    }
    get("#backtest-instrument-status").textContent = !dataset ? "Choose a dataset to see its instrument settings."
      : settings ? state.instrumentEdited ? "Instrument values edited for this run. Dataset defaults stay unchanged."
        : "Using dataset defaults. Edit the values above to override them for this run only."
      : "Set tick size and monetary point value in Datasets before running a backtest.";
    get("#backtest-date-range-help").textContent = `All dates are inclusive${dataset ? " in " + dataset.source_timezone : " in the dataset's saved source timezone"}. Percentages split chronological whole trading dates, rounding the IS date count down. IS must precede OOS; initial backtests and prop simulations use IS only.`;
    controls();
  }

  async function loadChoices() {
    if (state.busy || state.loading) return;
    state.loading = true;
    get("#backtest-options-status").textContent = "Loading datasets and strategies…";
    get("#backtest-error").hidden = true;
    controls();
    void window.optimizations.loadSettings();
    try {
      const [datasets, strategies] = await Promise.all([
        fetch("/api/datasets", { cache: "no-store" }).then(readResponse),
        fetch("/api/strategies", { cache: "no-store" }).then(readResponse),
      ]);
      const preset = new URLSearchParams(location.hash.split("?")[1] || "");
      const previousDataset = datasetSelect.value;
      const desiredDataset = preset.get("dataset") || previousDataset;
      const previousStrategy = preset.get("strategy") || strategySelect.value;
      state.datasets = datasets;
      state.strategies = strategies;
      datasetSelect.replaceChildren(new Option("Choose a saved dataset", ""));
      let supported = 0;
      for (const dataset of datasets) {
        const compatible = dataset.columns?.join(",") === "Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol";
        const option = new Option(`${dataset.name} · ${count.format(dataset.row_count)} bars${compatible ? "" : " · unsupported CSV schema"}`, dataset.id);
        option.disabled = !compatible;
        datasetSelect.add(option);
        if (compatible) supported++;
      }
      datasetSelect.value = Array.from(datasetSelect.options).some((option) => option.value === desiredDataset && !option.disabled) ? desiredDataset : "";
      strategySelect.replaceChildren(new Option("Choose a strategy", ""));
      for (const strategy of strategies) strategySelect.add(new Option(label(strategy.id), strategy.id));
      strategySelect.value = strategies.some((strategy) => strategy.id === previousStrategy)
        ? previousStrategy : strategies.length ? strategies[0].id : "";
      state.ready = supported > 0 && strategies.length > 0;
      get("#backtest-options-status").textContent = !supported
        ? "No supported saved datasets. Upload and save a nine-column CSV in Datasets first."
        : !strategies.length ? "No strategies are available on this server." : "";
      get("#backtest-form-hint").textContent = "Review dataset instrument defaults or override them for this run. Configure account capital and costs separately. Each backtest also runs the standard Apex 50K EOD analysis with activation fees.";
      renderStrategy();
      renderDataset(previousDataset !== datasetSelect.value || !state.instrumentEdited);
    } catch (error) {
      state.ready = false;
      showError(error, "Could not load backtest choices");
      get("#backtest-options-status").textContent = "Use Refresh choices to try again.";
    } finally {
      state.loading = false;
      controls();
    }
  }

  function configuration() {
    for (const input of form.querySelectorAll("input")) {
      if (input.disabled || input.closest("#optimization-settings")) continue;
      input.setCustomValidity("");
      const value = input.value.trim();
      if (input.hasAttribute("data-integer") && value !== "" && !Number.isSafeInteger(Number(value))) {
        input.setCustomValidity("Enter a whole number within the supported integer range.");
      }
      if (input.dataset.decimal) {
        const valid = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(value);
        const mantissa = value.split(/[eE]/)[0];
        const zero = !/[1-9]/.test(mantissa);
        const negative = mantissa.startsWith("-") && !zero;
        if (!valid || negative || (input.dataset.decimal === "positive" && zero)) {
          input.setCustomValidity(input.dataset.decimal === "positive" ? "Enter a decimal number greater than zero." : "Enter a non-negative decimal number.");
        }
      }
    }
    if (fromDate.value && toDate.value && fromDate.value > toDate.value) {
      toDate.setCustomValidity("To date must be on or after From date.");
    }
    if (!form.checkValidity()) {
      const invalid = form.querySelector("input:invalid, select:invalid");
      showError({ message: `${invalid?.closest("label")?.firstChild?.textContent?.trim() || "Configuration"}: ${invalid?.validationMessage || "Complete the required fields."}` });
      form.reportValidity();
      return null;
    }
    const execution = {};
    for (const input of form.querySelectorAll("[data-decimal], #backtest-slippage-ticks")) {
      if (input.dataset.parameter) continue;
      execution[input.name] = input.hasAttribute("data-integer") ? Number(input.value) : input.value.trim();
    }
    return {
      dataset_id: datasetSelect.value, strategy_id: strategySelect.value,
      strategy_parameters: Object.fromEntries(Array.from(get("#strategy-parameters").querySelectorAll("input"), (input) => [input.dataset.parameter, input.dataset.type === "bool" ? input.checked : input.dataset.type === "Decimal" ? input.value.trim() : Number(input.value)])),
      execution_settings: execution,
      market_benchmark: {contracts: Number(get("#backtest-benchmark-contracts").value)},
      sample_split: window.researchSplit.payload(),
    };
  }

  function paintProgress(progress, started) {
    const titles = { waiting: "Waiting for server", preparing: "Preparing saved dataset",
      preparing_data: "Preparing backtest · checking source bars", preparing_features: "Preparing backtest · calculating indicators", replaying: "Running backtest",
      saving_report: "Saving report", saving_results: "Saving run results", done: "Backtest saved", failed: "Backtest failed", unconfirmed: "Result unconfirmed" };
    get("#backtest-progress").hidden = false;
    get("#backtest-progress").classList.toggle("failed", ["failed", "unconfirmed"].includes(progress.stage));
    get("#backtest-progress-title").textContent = progress.stage.startsWith("prop_simulation:")
      ? `Apex 50K EOD · ${progress.stage.slice("prop_simulation: ".length)}` : titles[progress.stage] || "Processing backtest";
    // Preparation counters scan the source independently; their percentages
    // cannot represent strategy replay or overall job completion.
    const preparing = ["waiting", "preparing", "preparing_data", "preparing_features"].includes(progress.stage);
    const determinate = !preparing && !["failed", "unconfirmed"].includes(progress.stage) && progress.total_bars > 0;
    const percent = determinate ? Math.min(100, progress.bars_processed / progress.total_bars * 100) : null;
    get("#backtest-progress-percent").textContent = percent === null ? "" : `${Math.floor(percent)}% of bars`;
    const bar = get("#backtest-progress-bar");
    if (percent === null) bar.removeAttribute("value");
    else bar.value = percent;
    const counts = `${count.format(progress.bars_processed || 0)} / ${count.format(progress.total_bars || 0)}`;
    get("#backtest-progress-detail").textContent = progress.stage === "preparing_data"
      ? `${counts} source bars checked`
      : progress.stage === "preparing_features" ? `${counts} indicator bars prepared`
      : preparing ? "Strategy replay has not started yet."
      : `${counts} bars processed`;
    const seconds = Math.floor((performance.now() - started) / 1000);
    get("#backtest-elapsed").textContent = seconds < 60 ? `${seconds}s elapsed` : `${Math.floor(seconds / 60)}m ${seconds % 60}s elapsed`;
  }

  function completion(record) {
    reportRecord = record;
    const compact = record.report_storage?.detail === "compact";
    const compressed = record.report_storage?.compression === "gzip";
    get("#report-storage-note").textContent = compact
      ? "Compact report · All metrics, trades and trade-close equity are saved. " + (record.run_metadata.research?.phase === 'is' ? "Full per-bar account records are available by generating a full-detail replay of this IS parameter set." : "OOS and legacy reports cannot request a full-detail replay; select a new manual OOS run from IS instead.")
      : `Full report · Includes per-bar equity${compressed ? "; JSON is compressed with gzip" : ""}.`;
    if (record.market_benchmark) get("#report-storage-note").textContent += " Aligned strategy/holding bar-close equity is already saved in the Market benchmark CSV; viewing it requires no replay.";
    get("#report-json-download").href = `/api/backtests/${record.id}/exports/report`;
    get("#report-json-download").textContent = compressed ? "Report JSON.gz ↓" : "Report JSON ↓";
    get("#report-generate-detail").hidden = !compact || record.run_metadata.research?.phase !== 'is';
    get("#report-generate-detail").disabled = detailedBusy;
    get("#report-capture-risk").hidden = !!record.intratrade_risk || record.run_metadata.research?.phase !== 'is';
    get("#report-capture-risk").disabled = detailedBusy;
    get("#report-risk-download").hidden = !record.intratrade_risk;
    get("#report-risk-download").href = `/api/backtests/${record.id}/exports/intratrade_risk`;
    if (record.intratrade_risk) get("#report-storage-note").textContent += ` Intratrade risk: ${record.intratrade_risk.trades} trades captured from held OHLC bars; ${record.intratrade_risk.ambiguous_trades} have ambiguous adverse ordering. Uses conservative bounds, not tick measurements.`;
    else get("#report-storage-note").textContent += " Legacy risk coverage: realized close-only fallback. Capture risk from an IS replay to include held-bar excursions.";
    get("#report-detail-status").hidden = true;
    const content = get("#backtest-completion-content");
    content.replaceChildren();
    const metadata = record.run_metadata;
    const defaults = metadata.dataset.instrument_settings;
    const overrides = metadata.instrument_overrides;
    const selection = metadata.selection;
    const grid = element("dl", "backtest-run-details");
    const pairs = [
      ["Run ID", record.id], ["Dataset", metadata.dataset.name], ["Dataset ID", metadata.dataset.id],
      ["Bars used", count.format(selection?.row_count ?? metadata.dataset.row_count)], ["Source dataset bars", count.format(metadata.dataset.row_count)],
      ["From date (inclusive)", selection?.from_date || "First available date"], ["To date (inclusive)", selection?.to_date || "Last available date"],
      ["Source timezone", metadata.dataset.source_timezone],
      ["Replay start · UTC", record.period_start_utc], ["Replay end · UTC", record.period_end_utc],
      ...(selection ? [["Source rows used", `${selection.first_source_bar_number}–${selection.last_source_bar_number}`]] : []),
      ["Strategy", label(metadata.strategy.id)], ["Timestamp convention", record.timestamp_convention === "bar_close" ? "Bar close" : record.timestamp_convention],
      ["Dataset SHA-256", metadata.dataset.sha256], ["Strategy source SHA-256", metadata.strategy.source_sha256],
      ["Execution assumption", record.execution_assumption], ["Currency", "CU · account currency unspecified"],
      ["Dataset default tick size", defaults?.tick_size || "Not recorded"],
      ["Dataset default monetary point value", defaults?.point_value || "Not recorded"],
      ["Instrument overrides", overrides ? Object.entries(overrides).map(([key, value]) => `${executionLabels[key]}: ${value}`).join(" · ") || "None (dataset defaults)"
        : "Not recorded (older run)"],
    ];
    for (const [name, value] of pairs) {
      const pair = element("div");
      if (name === "Instrument overrides") pair.dataset.instrumentOverrides = "";
      pair.append(element("dt", "", name), element("dd", name.endsWith("ID") ? "run-identifier" : "", value));
      grid.append(pair);
    }
    const flatten = metadata.strategy.session_flattening;
    if (flatten?.enabled) {
      const pair = element("div");
      pair.dataset.setting = "session_flattening";
      pair.append(element("dt", "", "Backtest lookahead · session exits"), element("dd", "",
        `Last daytime bar minus ${flatten.minutes_before_close} minutes; cutoff Close fill, at/before 15:55 CT. ${flatten.sessions ?? 0} inferred sessions; ${flatten.sessions_using_earlier_bar ?? 0} used an earlier available bar; ${flatten.sessions_without_cutoff_bar ?? 0} had no executable cutoff. Truncated sessions count as early closes.`));
      grid.append(pair);
    }
    content.append(grid);
    for (const [title, settings, labels] of [
      ["Strategy parameters used", metadata.strategy.parameters, null],
      ["Execution settings used", record.execution_settings, executionLabels],
    ]) {
      content.append(element("h3", "parameter-heading", title));
      const details = element("dl", "backtest-run-details settings-used");
      for (const [name, value] of Object.entries(settings)) {
        const pair = element("div");
        pair.dataset.setting = name;
        pair.append(element("dt", "", labels?.[name] || label(name)), element("dd", "", String(value)));
        details.append(pair);
      }
      content.append(details);
    }
  }
  window.addEventListener("report-loaded", (event) => completion(event.detail));
  get("#report-generate-detail").onclick = () => replayReport(false);
  get("#report-capture-risk").onclick = () => replayReport(true);
  async function replayReport(risk) {
    if (detailedBusy || !reportRecord) return;
    const id = reportRecord.id, operationId = crypto.randomUUID();
    const hash = location.hash;
    const status = get("#report-detail-status");
    const current = () => location.hash === hash;
    detailedBusy = true;
    get("#report-generate-detail").disabled = true;
    get("#report-capture-risk").disabled = true;
    status.hidden = false;
    status.textContent = risk ? "Replaying IS to capture held-bar risk and run a new Apex analysis…" : "Replaying this parameter set to save compressed full detail…";
    let pollTimer, finished = false;
    const poll = async () => {
      try {
        const response = await fetch(`/api/progress/${operationId}`, {cache: "no-store"});
        if (response.ok && current() && !finished) {
          const progress = await response.json();
          status.textContent = `Generating ${risk ? "intratrade risk" : "full detail"} · ${progress.stage.replaceAll("_", " ")} · ${count.format(progress.bars_processed)} / ${count.format(progress.total_bars)} bars`;
        }
      } catch { /* The run request remains active when progress is unavailable. */ }
      if (!finished) pollTimer = setTimeout(poll, 1000);
    };
    void poll();
    try {
      const record = await readResponse(await fetch(`/api/backtests/${id}/${risk ? "risk" : "detailed"}?progress_id=${operationId}`, {method: "POST"}));
      if (current()) location.hash = `#backtests/report/${record.id}`;
    } catch (error) {
      if (current()) status.textContent = error instanceof TypeError
        ? "Connection lost. Check saved backtests before generating detail again; completion is unconfirmed."
        : `Could not generate ${risk ? "intratrade risk" : "full detail"}: ${error.message || JSON.stringify(error.detail || error)}`;
    } finally {
      finished = true;
      clearTimeout(pollTimer);
      detailedBusy = false;
      get("#report-generate-detail").disabled = false;
      get("#report-capture-risk").disabled = false;
    }
  };

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (state.busy || state.loading || !state.ready || !state.strategy) return;
    get("#backtest-error").hidden = true;
    const payload = configuration();
    if (!payload) return;
    if (optimizing()) {
      state.busy = true;
      controls();
      try { await window.optimizations.start(payload); }
      catch (error) { showError(error, "Optimization needs attention"); }
      finally { state.busy = false; controls(); }
      return;
    }
    const operationId = crypto.randomUUID();
    const started = performance.now();
    let current = { stage: "waiting", bars_processed: 0, total_bars: payload.from_date || payload.to_date ? 0 : selectedDataset()?.row_count || 0 };
    let finished = false;
    let pollTimer;
    const abortPoll = new AbortController();
    state.busy = true;
    controls();
    get("#backtest-completion").hidden = true;
    get("#backtest-progress-note").textContent = "Preparing to send the run configuration.";
    paintProgress(current, started);
    const elapsedTimer = setInterval(() => paintProgress(current, started), 250);
    const poll = async () => {
      try {
        const response = await fetch(`/api/progress/${operationId}`, { cache: "no-store", signal: abortPoll.signal });
        if (response.ok) {
          const progress = await response.json();
          if (finished) return;
          current = progress;
          get("#backtest-progress-note").textContent = ["preparing", "preparing_data", "preparing_features"].includes(progress.stage)
            ? "Checking the source and preparing indicators before strategy replay. The percentage bar tracks strategy replay only."
            : progress.stage.startsWith("prop_simulation:") ? "Strategy replay finished. Running Apex 50K EOD analysis before saving the result."
            : progress.stage.startsWith("saving") ? "Replay finished. Waiting for results to be saved."
            : progress.stage === "done" ? "Results saved. Waiting for the completed run response." : "";
          paintProgress(current, started);
        } else if (!finished) {
          get("#backtest-progress-note").textContent = response.status === 404
            ? "Waiting for a progress snapshot. The run request is still active."
            : "Progress is temporarily unavailable. The run request is still active.";
        }
      } catch {
        if (!finished) get("#backtest-progress-note").textContent = "Progress is temporarily unavailable. The run request is still active.";
      }
      if (!finished) pollTimer = setTimeout(poll, 500);
    };
    poll();
    try {
      payload.reuse_results=get("#backtest-reuse").checked;
      const response = await fetch(`/api/backtests?progress_id=${operationId}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
      });
      const record = await readResponse(response);
      if (record.status !== "complete" || !record.id) throw new Error("The server did not confirm a completed run.");
      finished = true;
      const total = record.run_metadata.selection?.row_count ?? record.run_metadata.dataset.row_count;
      current = { stage: "done", bars_processed: total, total_bars: total };
      location.hash = `backtests/report/${record.id}`;
      get("#backtest-progress-note").textContent = response.headers.get("X-AlphaQuest-Reused") === "true" ? `Reopened verified run ${record.id}.` : `Run ${record.id} saved successfully.`;
    } catch (error) {
      finished = true;
      const network = error instanceof TypeError;
      current = { ...current, stage: network ? "unconfirmed" : "failed" };
      showError(network ? { message: "Connection lost. Completion is unconfirmed; check saved runs before submitting again." } : error,
        network ? "Could not confirm completion" : "Backtest could not complete");
      get("#backtest-progress-note").textContent = "";
    } finally {
      finished = true;
      clearTimeout(pollTimer);
      clearInterval(elapsedTimer);
      abortPoll.abort();
      paintProgress(current, started);
      state.busy = false;
      controls();
    }
  });

  form.addEventListener("input", (event) => {
    if (!event.target.closest("#optimization-settings")) event.target.setCustomValidity?.("");
  });
  datasetSelect.addEventListener("change", () => renderDataset());
  resetInstrument.addEventListener("click", () => renderDataset());
  for (const input of [tickSize, pointValue]) input.addEventListener("input", () => {
    state.instrumentEdited = true;
    renderDataset(false);
  });
  strategySelect.addEventListener("change", renderStrategy);
  refresh.addEventListener("click", loadChoices);
  window.addEventListener("optimization-workers-changed", controls);
  window.addEventListener("research-split-changed", controls);

  function modeChanged(loadWorkers=true) {
    get("#strategy-parameters").hidden = optimizing();
    get("#strategy-parameters-heading").hidden = optimizing();
    get("#optimization-settings").hidden = !optimizing();
    get("#backtest-reuse-settings").hidden=optimizing();
    get("#backtest-progress").hidden = optimizing() || get("#backtest-progress").hidden;
    if(loadWorkers && optimizing() && !window.optimizations.workersReady())void window.optimizations.loadSettings();
    controls();
  }
  mode.addEventListener("change",()=>modeChanged());

  function navigate() {
    if(location.hash==="#optimizations")mode.value="exhaustive";
    const screen = location.hash.startsWith("#strategies") ? "strategies" : location.hash.startsWith("#optimizations") ? "optimizations" : location.hash.startsWith("#backtests") ? "backtests" : "datasets";
    get("#strategies-screen").hidden=screen!=="strategies";
    get("#datasets-screen").hidden = screen !== "datasets";
    get("#backtests-screen").hidden = !["backtests", "optimizations"].includes(screen) || location.hash.startsWith("#backtests/prop/");
    get("#prop-screen").hidden = !location.hash.startsWith("#backtests/prop/");
    const title = screen === "datasets" ? "Datasets" : "Strategies";
    get("#current-screen").textContent = title;
    document.title = `${title} · AlphaQuest`;
    get("#backtests-title").textContent = "Run backtests.";
    modeChanged(false);
    controls();
    for (const link of document.querySelectorAll("[data-screen]")) {
      const active = link.dataset.screen === (screen === "datasets" ? "datasets" : "strategies");
      link.classList.toggle("active", active);
      if (active) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    }
    get("#footer-context").textContent = screen === "strategies" ? "Strategies · Datasets and IS/OOS runs" : optimizing() ? "Optimizations · Exhaustive parameter research" : screen === "backtests" ? "Backtests · Configure and run" : "Dataset management · Component 1 of your research workflow";
    if (["#backtests", "#backtests/new", "#optimizations"].includes(location.hash.split("?")[0])) loadChoices();
  }
  window.addEventListener("hashchange", navigate);
  navigate();
})();
