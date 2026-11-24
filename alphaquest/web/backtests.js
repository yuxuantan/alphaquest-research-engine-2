"use strict";

(() => {
  const get = (selector) => document.querySelector(selector);
  const form = get("#backtest-form");
  const datasetSelect = get("#backtest-dataset");
  const strategySelect = get("#backtest-strategy");
  const fromDate = get("#backtest-from-date");
  const toDate = get("#backtest-to-date");
  const start = get("#start-backtest");
  const stopBacktest = get("#backtest-stop");
  const refresh = get("#refresh-backtest-choices");
  const resetInstrument = get("#reset-instrument-defaults");
  const tickSize = get("#backtest-tick-size");
  const pointValue = get("#backtest-point-value");
  const count = new Intl.NumberFormat("en-US");
  const barSchema = "Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol";
  const pairedSchema = `${barSchema},ESClose`;
  const state = { datasets: [], strategies: [], busy: false, loading: false, ready: false, strategy: null, instrumentEdited: false };
  let reportRecord, detailedBusy = false;
  const executionLabels = {
    initial_capital: "Initial capital", tick_size: "Tick size", point_value: "Monetary point value",
    slippage_ticks: "Slippage · ticks per fill", commission_per_contract_per_side: "Commission · per contract per side",
  };
  const label = (name) => {
    if (name === "contracts") return "Number of contracts";
    if (name === "overnight_bias_orb") return "Overnight Bias ORB";
    if (name === "noise") return "Noise";
    if (name === "relative_strength") return "Relative Strength";
    return String(name).replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase());
  };

  function element(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined) el.textContent = text;
    return el;
  }

  function selectedDataset() {
    return state.datasets.find((item) => item.id === datasetSelect.value);
  }

  const mechanicSetup = () => new URLSearchParams(location.hash.split("?")[1] || "").get("workflow") === "mechanic";

  function controls() {
    const mechanic = mechanicSetup();
    get("#optimization-settings").hidden = mechanic;
    const calendarUnavailable = renderCalendar();
    for (const fieldset of form.querySelectorAll("fieldset")) fieldset.disabled = state.busy || state.loading;
    for (const input of get("#optimization-settings").querySelectorAll("input, select")) input.disabled = state.busy || state.loading || mechanic;
    get("#optimization-workers").disabled = mechanic || state.busy || state.loading || !window.optimizations.workersReady();
    get("#optimization-workers-retry").disabled = state.busy || state.loading;
    get("#optimization-automatic-prop").disabled = mechanic || state.busy || state.loading;
    refresh.disabled = state.busy || state.loading;
    resetInstrument.disabled = state.busy || state.loading || !selectedDataset()?.instrument_settings;
    start.disabled = state.busy || state.loading || !state.ready || !state.strategy || !selectedDataset()?.instrument_settings || calendarUnavailable || !window.researchSplit.ready() || (!mechanic && !window.optimizations.workersReady());
    start.textContent = state.busy ? "Submitting / running…" : mechanic ? "Open mechanic validation →" : "Start backtests →";
    form.setAttribute("aria-busy", String(state.busy));
  }

  function renderCalendar() {
    const status = get("#backtest-session-calendar");
    const calendar = state.strategy?.session_calendar;
    status.hidden = !calendar;
    if (!calendar) return false;
    const twin = state.strategy?.id === "twin_continuation";
    const includesTrue = name => mechanicSetup()
      ? state.strategy.parameters.find(p => p.name === name)?.default
      : Array.from(document.querySelectorAll(`#optimization-ranges [data-parameter='${name}'] select`)).some(input => input.value === "true");
    const eod = !twin && includesTrue("use_eod_flat");
    const usesCalendar = twin ? includesTrue("use_session_calendar") : eod && includesTrue("use_external_calendar");
    if (!usesCalendar) {
      status.textContent = twin ? "Session calendar: disabled · earlier fixed-clock Twin session model."
        : eod ? "Fixed weekday session · 16:00 Chicago close before applying the buffer and EOD cutoff. Holiday exceptions are off."
        : "Session calendar: disabled · Use EOD Flat is off.";
      return false;
    }
    const symbol = String(selectedDataset()?.symbol || "").trim().toUpperCase();
    const supported = new RegExp(`^(?:${calendar.symbol_pattern})$`).test(symbol);
    const instrument = !twin && symbol.replace(/^@/, "").startsWith("MNQ") ? "MNQ futures"
      : twin ? calendar.instrument : "NQ futures";
    status.textContent = supported
      ? `Session calendar: Auto → ${instrument} · ${calendar.file.split("/").pop()} · saved symbol ${symbol} · ${calendar.timezone}. ${twin ? "Held positions exit at the scheduled closing bar Close, including holiday early closes." : "Set Close buffer minutes below. The default is 5."}`
      : `No reviewed session calendar for saved symbol ${symbol || "(not set)"}. ${twin ? "Twin calendar exits support explicit NQ/MNQ symbols. Choose a supported dataset or turn Use session calendar off." : "Choose an NQ/MNQ dataset or turn Use external calendar off for fixed weekday exits."}`;
    if (!supported && mechanicSetup()) status.textContent = `Default-parameter mechanic validation requires a reviewed calendar for this strategy. Choose a supported NQ/MNQ dataset; calendar defaults cannot be disabled for validation.`;
    return !supported;
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

  function renderStrategy(resetInstrumentValues = false) {
    const strategy = state.strategies.find((item) => item.id === strategySelect.value);
    state.strategy = strategy || null;
    for (const option of datasetSelect.options) {
      if (!option.value) continue;
      const schema = option.dataset.schema;
      option.disabled = schema !== pairedSchema && (strategy?.id === "relative_strength" || schema !== barSchema);
    }
    if (datasetSelect.selectedOptions[0]?.disabled) {
      datasetSelect.value = "";
      resetInstrumentValues = true;
    }
    get("#strategy-description").textContent = strategy?.description || "Select a strategy to see its description.";
    if (strategy?.parameters.some((parameter) => !["int", "integer", "bool", "Decimal"].includes(parameter.type))) {
      state.strategy = null;
      showError({ message: "This strategy uses a parameter type this screen does not support." });
    }
    get("#backtest-fill-assumption").textContent = strategy?.id === "twin_continuation"
      ? "Use full-session one-minute close-labelled bars. Signals calculate at Close; Momentum enters next Open and Breakout uses next-bar OCO stops. Minute execution follows MultiCharts: visit the extreme nearer Open first, Low first on ties. The first entry cancels its sibling. Immediate protection defaults on and follows only the remaining path after fill. Reports include complete High-first and Low-first diagnostic replays; only the fixed primary screens candidates. These are OHLC assumptions, not observed ticks. Turning Immediate protection off restores delayed brackets. Calendar session exits include early closes; missing held closing bars reject. Native phase-controlled replay and entry-decision capture remain unsupported for Twin."
      : strategy?.id === "overnight_bias_orb"
      ? "Use close-labelled one-minute Globex OHLC. Decisions run on 15-minute closes in Eastern time. Market orders fill at the next open, with signal-close stop and target active on the entry bar. Within each minute, the engine uses the nearest-extreme-first path, Low first on ties."
      : strategy?.id === "noise"
      ? "Use close-labelled one-minute NQ or MNQ OHLC. Decisions run on observed 15-minute closes in Central time. Market orders fill at the next observed Open, with the stop and target measured from the fill. The engine models the path inside each minute, visiting the nearer extreme first and Low first on ties. A missing exact flat signal can leave a position open across sessions."
      : strategy?.id === "relative_strength"
      ? "Use synchronized one-minute NQ/MNQ and ES closes. Signals enter at the next observed Open. Stop and target use the entry fill and first become active after the entry bar closes. An open position flattens at the configured Central-time close."
      : strategy?.execution_assumption?.startsWith("next_open_market_next_bar_bracket_")
      ? "Signals use completed closes. Market orders fill at the next observed bar Open. Brackets begin after the entry bar. The modeled OHLC path visits the extreme nearer the Open first, with Low first on ties. With EOD flattening enabled, the cutoff uses the reviewed calendar close or a fixed 16:00 Chicago weekday close, minus the buffer and bounded by EOD Flat Time. No future bars determine the cutoff. Use full-session one-minute data."
      : "Signals and simulated fills use that same close, adjusted by your slippage setting.";
    let defaults = get('#mechanic-default-parameters');
    if (!defaults) { defaults = element('details'); defaults.id = 'mechanic-default-parameters'; get('#strategy-description').after(defaults); }
    defaults.hidden = !mechanicSetup();
    defaults.replaceChildren(element('summary', '', 'Default strategy parameters for mechanic validation'));
    defaults.append(element('pre', '', JSON.stringify(Object.fromEntries(strategy?.parameters.map(p => [p.name,p.default]) || []),null,2)));
    window.optimizations.configure(state.strategy);
    renderDataset(resetInstrumentValues === true);
  }

  function renderDataset(resetValues = true) {
    const dataset = selectedDataset();
    window.researchSplit.configure(datasetSelect.value,strategySelect.value);
    get("#backtest-dataset-info").textContent = dataset
      ? `${count.format(dataset.row_count)} bars · ${dataset.filename} · ${dataset.start.replace("T", " ").replace("Z", " UTC")} to ${dataset.end.replace("T", " ").replace("Z", " UTC")}`
      : state.strategy?.id === "relative_strength"
        ? "Choose a paired NQ/MNQ CSV with ESClose. Upload the paired file in Datasets if needed."
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
    const finishSectionLoading=window.portalLoading.begin(get("#backtest-options-status"));
    try {
    get("#backtest-error").hidden = true;
    controls();
    void window.optimizations.loadSettings();
    try {
      const [datasets, strategies] = await Promise.all([
        window.portalLoading.fetch("/api/datasets", { cache: "no-store" }).then(readResponse),
        window.portalLoading.fetch("/api/strategies", { cache: "no-store" }).then(readResponse),
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
        const schema = dataset.columns?.join(",") || "";
        const compatible = schema === barSchema || schema === pairedSchema;
        const option = new Option(`${dataset.name} · ${count.format(dataset.row_count)} bars${schema === pairedSchema ? " · with ES closes" : compatible ? "" : " · unsupported CSV schema"}`, dataset.id);
        option.dataset.schema = schema;
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
        ? "No supported saved datasets. Upload and save a minute OHLCV CSV in Datasets first."
        : !strategies.length ? "No strategies are available on this server." : "";
      get("#backtest-form-hint").textContent = "Review dataset instrument defaults or override them for this run. Configure account capital and costs separately. Automatic legacy Apex and Lucid prop reports are enabled by default; uncheck the automatic-report option to skip them.";
      if (mechanicSetup()) get("#backtest-form-hint").textContent = "Save the dataset, IS/OOS split and execution costs. The next page runs one backtest using default strategy parameters, then requires your MC parity and execution review.";
      renderStrategy(previousDataset !== datasetSelect.value || !state.instrumentEdited);
    } catch (error) {
      state.ready = false;
      showError(error, "Could not load backtest choices");
      get("#backtest-options-status").textContent = "Use Refresh choices to try again.";
    } finally {
      state.loading = false;
      controls();
    }
    } finally { finishSectionLoading(); }
  }

  function configuration() {
    const parameters = mechanicSetup() ? Object.fromEntries(state.strategy.parameters.map(p => [p.name, p.default])) : window.optimizations.fixedParameters();
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
      strategy_parameters: parameters,
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
    const external = record.run_metadata.source?.kind === 'external_trade_export';
    const compact = record.report_storage?.detail === "compact";
    const compressed = record.report_storage?.compression === "gzip";
    get("#report-storage-note").textContent = compact
      ? "Compact report · All metrics, trades and trade-close equity are saved. " + (record.run_metadata.research?.phase === 'is' ? "Full per-bar account records are available by generating a full-detail replay of this IS parameter set." : "OOS and legacy reports cannot request a full-detail replay; select a new manual OOS run from IS instead.")
      : `Full report · Includes per-bar equity${compressed ? "; JSON is compressed with gzip" : ""}.`;
    if (record.market_benchmark) get("#report-storage-note").textContent += " Aligned strategy/holding bar-close equity is already saved in the Market benchmark CSV; viewing it requires no replay.";
    get("#report-json-download").href = `/api/backtests/${record.id}/exports/report`;
    get("#report-json-download").textContent = compressed ? "Report JSON.gz ↓" : "Report JSON ↓";
    get('#report-source-download').hidden = get('#report-canonical-download').hidden = !external;
    get('#report-source-download').href = `/api/backtests/${record.id}/exports/source`;
    get('#report-canonical-download').href = `/api/backtests/${record.id}/exports/canonical_source`;
    let decisionsDownload = get('#report-decisions-download');
    if (!decisionsDownload) {
      decisionsDownload = element('a', 'button secondary', 'Entry decisions (JSONL) ↓');
      decisionsDownload.id = 'report-decisions-download';
      get('#report-risk-download').after(decisionsDownload);
    }
    decisionsDownload.hidden = external || !record.execution_decisions;
    decisionsDownload.href = `/api/backtests/${record.id}/exports/execution_decisions`;
    if (external) {
      get('#report-storage-note').textContent = 'Imported trade report · Completed fills, exact costs and trade-close equity are saved. Market bars, per-bar equity and native strategy replay are unavailable. Risk coverage remains the exporter’s declared observation basis.';
      for (const id of ['report-generate-detail', 'report-capture-risk', 'report-risk-download']) get('#' + id).hidden = true;
      get('#report-detail-status').hidden = true;
      window.externalTradeImport.renderPreview({source: record.run_metadata.source, manifest: record.run_metadata.external_manifest, summary: record.summary,
        validation: record.run_metadata.source_validation, capabilities: record.capabilities, limitations: record.limitations}, get('#backtest-completion-content'));
      return;
    }
    get("#report-generate-detail").hidden = !compact || record.run_metadata.research?.phase !== 'is';
    get("#report-generate-detail").disabled = detailedBusy;
    get("#report-capture-risk").hidden = !!record.intratrade_risk || record.run_metadata.research?.phase !== 'is';
    get("#report-capture-risk").disabled = detailedBusy;
    get("#report-risk-download").hidden = !record.intratrade_risk;
    get("#report-risk-download").href = `/api/backtests/${record.id}/exports/intratrade_risk`;
    if (record.intratrade_risk) get("#report-storage-note").textContent += ` Intratrade risk: ${record.intratrade_risk.trades} trades captured from held OHLC bars; ${record.intratrade_risk.ambiguous_trades} have ambiguous adverse ordering. Uses conservative bounds, not tick measurements.`;
    else get("#report-storage-note").textContent += " Legacy risk coverage: realized close-only fallback. Capture risk from an IS replay to include held-bar excursions.";
    if (record.execution_decisions) get('#report-storage-note').textContent += ` Entry decisions: ${record.execution_decisions.decisions} captured, ${record.execution_decisions.filled_trades} filled and ${record.execution_decisions.cancelled_decisions} cancelled. Signal-time decisions and actual fills are distinct. A captured decision may have no initial stop; the export preserves that absence. Dynamic native sizing requires a new strategy replay.`;
    get("#report-detail-status").hidden = true;
    const content = get("#backtest-completion-content");
    content.replaceChildren();
    if (record.native_account_control) {
      const note=document.createElement('p');note.textContent='Actual native account-controlled replay. These trades reflect strategy eligibility and quantities chosen from provider account state. Trading equity retains the original backtest capital; withdrawals and modeled trader receipts are recorded separately in the prop analysis.';content.append(note);
      const capture=document.createElement('a');capture.href=`/api/backtests/${record.id}/exports/native_account_control`;capture.textContent='Download native account-control evidence';content.append(capture);
      const analysisId=record.run_metadata.native_account_control?.analysis_id;
      if(analysisId){const analysis=document.createElement('a');analysis.href=`#backtests/prop/job/${analysisId}`;analysis.textContent='Open native account-state analysis';content.append(document.createElement('br'),analysis);}
    }
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
      ...(record.execution_decisions ? [["Entry decision evidence", `${record.execution_decisions.version} · ${record.execution_decisions.events} events · ${record.execution_decisions.bracket_submissions} bracket submissions`], ["Entry decision SHA-256", record.execution_decisions.sha256], ["Entry decision limitations", record.execution_decisions.policy]] : [["Entry decision evidence", "Not captured in this saved report. Historical decision times and initial stops are not inferred from later fills."]]),
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
      const nextOpen = flatten.order_timing === "next_open";
      const cutoff = String(metadata.strategy.parameters.eod_flat_time ?? 1555).padStart(4, "0");
      const fill = nextOpen ? "submit at cutoff; fill next observed bar Open" : "cutoff Close fill (earlier execution model)";
      if (flatten.mode === "overnight_bias_orb_chart_close_v1") {
        const time = value => String(value).padStart(4, "0").replace(/(..)(..)$/, "$1:$2");
        const chartClose = flatten.calendar ? `Scheduled Globex close via ${flatten.calendar.file}. Reviewed coverage ${flatten.calendar.coverage_start} through ${flatten.calendar.coverage_end}.` : `Fixed ${time(flatten.chart_session_close)} ET chart close.`;
        pair.append(element("dt", "", "Overnight Bias ORB exits"), element("dd", "",
          `At the first held 15-minute close at or after ${time(flatten.flat_time)} ET, submit a market exit for the next open. ${chartClose} At the chart close, active bracket orders retain priority before the session-close exit.`));
      } else if (flatten.mode === "noise_exact_chart_time_v1") {
        const time = String(flatten.flat_time).padStart(4, "0");
        pair.append(element("dt", "", "Noise clock exit"), element("dd", "",
          `An observed 15-minute close at exactly ${time.slice(0, 2)}:${time.slice(2)} CT sends a market exit for the next observed Open. If that bar is missing, the stop and target stay active and the position can carry across sessions.`));
      } else if (flatten.mode === "relative_strength_chart_close_v1") {
        const time = value => String(value).padStart(4, "0").replace(/(..)(..)$/, "$1:$2");
        pair.append(element("dt", "", "Relative Strength exits"), element("dd", "",
          `Flatten on the Close of the first held bar at or after ${time(flatten.flat_time)} CT, or at or before ${time(flatten.rth_start)} CT. Active brackets retain priority. ES closes are part of the saved dataset hash. ${flatten.skip_holidays ? "The supplied 2010–2027 NYSE dates were skipped." : "The holiday filter was off."}`));
      } else if (flatten.mode === "twin_csv_session_close_v2") {
        const calendar = flatten.calendar || {};
        pair.append(element("dt", "", "Scheduled session-close exits · no bar lookahead"), element("dd", "",
          `Auto calendar ${flatten.calendar_id} for ${flatten.instrument_symbol} · ${calendar.file}. Held positions fill at the scheduled closing bar Close, including holiday early closes; no next-Open buffer. Existing bracket fills on that bar retain priority. ${flatten.sessions ?? 0} observed sessions; ${flatten.early_close_sessions ?? 0} shortened. Reviewed coverage ${calendar.coverage_start} through ${calendar.coverage_end}. CSV SHA-256: ${calendar.sha256}. Missing held closing bars reject; EOF liquidation remains labelled end_of_data.`));
      } else if (flatten.mode === "fixed_weekday_session_v1") {
        pair.append(element("dt", "", "Fixed weekday session exits"), element("dd", "",
          `16:00 Chicago close minus ${flatten.minutes_before_close} minutes, with the order cutoff at or before ${cutoff.slice(0, 2)}:${cutoff.slice(2)} CT. Submit at or after the cutoff and fill at the next observed bar Open by 16:00. Holiday exceptions are off.`));
      } else if (flatten.mode === "csv_session_calendar_v1") {
        const calendar = flatten.calendar || {};
        pair.append(element("dt", "", "Calendar-based session exits · no bar lookahead"), element("dd", "",
          `${flatten.calendar_selection === "instrument_symbol" ? `Auto calendar ${flatten.calendar_id} for ${flatten.instrument_symbol} · ${calendar.file}. ` : ""}Scheduled close minus ${flatten.minutes_before_close} minutes; ${fill}, order cutoff at/before ${cutoff.slice(0, 2)}:${cutoff.slice(2)} CT. ${flatten.sessions ?? 0} observed sessions; ${flatten.early_close_sessions ?? 0} shortened, ${flatten.closed_sessions ?? 0} closed. Reviewed coverage ${calendar.coverage_start} through ${calendar.coverage_end}. CSV SHA-256: ${calendar.sha256}. Truncation does not change the cutoff.`));
      } else {
        pair.append(element("dt", "", "Backtest lookahead · session exits (earlier model)"), element("dd", "",
          `Last daytime bar minus ${flatten.minutes_before_close} minutes; ${fill}, order cutoff at/before ${cutoff.slice(0, 2)}:${cutoff.slice(2)} CT. ${flatten.sessions ?? 0} inferred sessions; ${flatten.sessions_using_earlier_bar ?? 0} used an earlier available bar; ${flatten.sessions_without_cutoff_bar ?? 0} had no executable cutoff. Truncated sessions count as early closes.`));
      }
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
    if (reportRecord.run_metadata.source?.kind === 'external_trade_export' || reportRecord.capabilities?.native_replay === false) return;
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
        const response = await window.portalLoading.fetch(`/api/progress/${operationId}`, {cache: "no-store"});
        if (response.ok && current() && !finished) {
          const progress = await response.json();
          status.textContent = `Generating ${risk ? "intratrade risk" : "full detail"} · ${progress.stage.replaceAll("_", " ")} · ${count.format(progress.bars_processed)} / ${count.format(progress.total_bars)} bars`;
        }
      } catch { /* The run request remains active when progress is unavailable. */ }
      if (!finished) pollTimer = setTimeout(poll, 1000);
    };
    void poll();
    try {
      const record = await readResponse(await window.portalLoading.fetch(`/api/backtests/${id}/${risk ? "risk" : "detailed"}?progress_id=${operationId}`, {method: "POST"}));
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
    if (mechanicSetup()) {
      state.busy = true;
      controls();
      try {
        const {strategy_parameters, ...declaration} = payload;
        const response = await window.portalLoading.fetch('/api/campaign-workflows', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(declaration)});
        const workflow = await readResponse(response);
        location.hash = `#campaigns/workflows/${workflow.id}/mechanic_validation`;
      } catch (error) { showError(error, 'Could not configure mechanic validation'); }
      finally { state.busy = false; controls(); }
      return;
    }
    if (payload.strategy_parameters === null || !get("#optimization-automatic-prop").checked) {
      get("#backtest-progress").hidden = true;
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
    let stopRequested = false;
    let pollTimer;
    const abortPoll = new AbortController();
    state.busy = true;
    controls();
    get("#backtest-completion").hidden = true;
    get("#backtest-progress-note").textContent = "Preparing to send the run configuration.";
    stopBacktest.hidden = false;
    stopBacktest.disabled = true;
    stopBacktest.textContent = "Stop running backtest";
    stopBacktest.onclick = async () => {
      if (finished || stopRequested || !window.confirm("Stop this running backtest at its next checkpoint? No incomplete report will be saved.")) return;
      stopRequested = true;
      stopBacktest.disabled = true;
      try {
        const response = await window.portalLoading.fetch(`/api/backtests/progress/${operationId}/stop`, {method:"POST"});
        await readResponse(response);
        stopBacktest.textContent = "Stop requested";
        get("#backtest-progress-note").textContent = "Stopping at the next backtest checkpoint…";
      } catch (error) {
        if (!finished) {
          stopRequested = false;
          stopBacktest.disabled = false;
          get("#backtest-progress-note").textContent = error.message;
        }
      }
    };
    paintProgress(current, started);
    const elapsedTimer = setInterval(() => paintProgress(current, started), 250);
    const poll = async () => {
      try {
        const response = await window.portalLoading.fetch(`/api/progress/${operationId}`, { cache: "no-store", signal: abortPoll.signal });
        if (response.ok) {
          const progress = await response.json();
          if (finished) return;
          current = progress;
          if (!stopRequested && progress.stage !== "done") stopBacktest.disabled = false;
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
      payload.reuse_results=get("#optimization-reuse").checked;
      const response = await window.portalLoading.fetch(`/api/backtests?progress_id=${operationId}`, {
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
      current = { ...current, stage: network ? "unconfirmed" : stopRequested ? "stopped" : "failed" };
      showError(network ? { message: "Connection lost. Completion is unconfirmed; check saved runs before submitting again." } : error,
        network ? "Could not confirm completion" : stopRequested ? "Backtest stopped" : "Backtest could not complete");
      get("#backtest-progress-note").textContent = "";
    } finally {
      finished = true;
      clearTimeout(pollTimer);
      clearInterval(elapsedTimer);
      abortPoll.abort();
      stopBacktest.hidden = true;
      stopBacktest.onclick = null;
      paintProgress(current, started);
      state.busy = false;
      controls();
    }
  });

  form.addEventListener("input", (event) => {
    if (!event.target.closest("#optimization-settings")) event.target.setCustomValidity?.("");
    if (event.target.closest("#optimization-settings")) controls();
  });
  form.addEventListener("change", controls);
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

  const main = get('#main-content');
  get('#skip-to-content').addEventListener('click', event => {
    event.preventDefault();
    main.focus({preventScroll: true});
    main.scrollIntoView({block: 'start'});
  });
  let previousPath;
  function navigate() {
    const hash = location.hash;
    const screen = hash === "#research" ? "research"
      : hash.startsWith("#backtests/research") ? "research-workspace"
      : /^#jobs(?:[/?]|$)/.test(hash) ? "jobs"
      : hash.startsWith("#campaigns/workflows/") ? "mechanic"
      : hash.startsWith("#campaigns") ? "campaigns"
      : hash.split('?')[0] === "#prop-sim" ? "prop-sim"
      : hash.split('?')[0] === "#prop-desk" ? "prop-desk"
      : hash.startsWith("#strategies") ? "strategies"
      : hash.startsWith("#optimizations") ? "optimizations"
      : hash.startsWith("#backtests") ? "backtests" : "datasets";
    for (const name of ["datasets", "strategies", "research", "research-workspace", "campaigns", "mechanic", "jobs", "prop-sim", "prop-desk"]) {
      get(`#${name}-screen`).hidden = screen !== name;
    }
    get("#backtests-screen").hidden = !["backtests", "optimizations"].includes(screen) || hash.startsWith("#backtests/prop/");
    get("#prop-screen").hidden = !hash.startsWith("#backtests/prop/");
    const navigation = hash.startsWith("#backtests/prop/") || screen === "research-workspace" ? "prop-sim"
      : ["strategies", "backtests", "optimizations", "mechanic"].includes(screen) ? "campaigns" : screen;
    const path = hash.split('?')[0];
    const setupTitle = mechanicSetup() ? 'Configure mechanic validation' : 'Run a backtest';
    const phaseNames = {mechanic_validation: 'Mechanic validation', is_broad: 'IS Broad', is_narrow: 'IS Narrow', oos: 'OOS'};
    const screenTitles = {datasets: 'Dataset library', research: 'Research', 'research-workspace': 'Saved research',
      campaigns: 'Campaigns', strategies: 'Saved runs', 'prop-sim': 'Prop Sim', 'prop-desk': 'Prop Desk', jobs: 'Job history',
      mechanic: phaseNames[path.split('/')[3]] || 'Campaign workflow', optimizations: 'Backtest batches'};
    let title = screenTitles[screen];
    if (screen === 'backtests') {
      title = path.startsWith('#backtests/report/') ? 'Backtest report'
        : path.startsWith('#backtests/prop/') ? 'Prop analysis'
        : path.startsWith('#backtests/batches') ? 'Backtest batches' : setupTitle;
    }
    get('#current-screen').textContent = title;
    document.title = `${title} · AlphaQuest`;
    get('#backtests-title').textContent = setupTitle;
    controls();
    for (const link of document.querySelectorAll("[data-screen]")) {
      const active = link.dataset.screen === navigation;
      link.classList.toggle("active", active);
      if (active) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    }
    const jobsLink = get('.job-history-link');
    if (screen === 'jobs') jobsLink.setAttribute('aria-current', 'page');
    else jobsLink.removeAttribute('aria-current');
    if (previousPath !== undefined && previousPath !== path) {
      main.focus({preventScroll: true});
      window.scrollTo(0, 0);
    }
    previousPath = path;
    if (["#backtests", "#backtests/new", "#optimizations"].includes(location.hash.split("?")[0])) loadChoices();
  }
  get('#backtest-upload-dataset').onclick = () => {
    try {
      const [path,query] = location.hash.split('?');
      const params = new URLSearchParams(query || ''); params.set('strategy',strategySelect.value);
      sessionStorage.setItem('backtest-upload-return', `${path}?${params}`);
    } catch {}
  };
  window.addEventListener("hashchange", navigate);
  navigate();
})();
