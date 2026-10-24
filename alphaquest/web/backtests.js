"use strict";

(() => {
  const get = (selector) => document.querySelector(selector);
  const form = get("#backtest-form");
  const datasetSelect = get("#backtest-dataset");
  const strategySelect = get("#backtest-strategy");
  const start = get("#start-backtest");
  const refresh = get("#refresh-backtest-choices");
  const count = new Intl.NumberFormat("en-US");
  const state = { datasets: [], strategies: [], busy: false, loading: false, ready: false, strategy: null };
  const drafts = new Map();
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
    for (const fieldset of form.querySelectorAll("fieldset")) fieldset.disabled = state.busy || state.loading;
    refresh.disabled = state.busy || state.loading;
    start.disabled = state.busy || state.loading || !state.ready || !state.strategy;
    start.textContent = state.busy ? "Backtest running…" : "Start backtest →";
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
    drafts.set(state.strategy.id, Object.fromEntries(Array.from(get("#strategy-parameters").querySelectorAll("input"), (input) => [input.dataset.parameter, input.value])));
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
        if (!["int", "integer"].includes(parameter.type)) {
          state.strategy = null;
          showError({ message: "This strategy uses a parameter type this screen does not support." });
          break;
        }
        const wrapper = element("label", "", label(parameter.name));
        const input = element("input");
        input.id = `strategy-${parameter.name}`;
        input.name = parameter.name;
        input.dataset.parameter = parameter.name;
        input.dataset.integer = "";
        input.type = "number";
        input.step = "1";
        input.max = String(parameter.maximum ?? Number.MAX_SAFE_INTEGER);
        if (parameter.minimum !== undefined) input.min = String(parameter.minimum);
        input.required = true;
        input.value = drafts.get(strategy.id)?.[parameter.name] ?? String(parameter.default ?? "");
        const help = element("span", "field-help", parameter.description);
        help.id = `${input.id}-help`;
        input.setAttribute("aria-describedby", help.id);
        input.setAttribute("aria-label", label(parameter.name));
        wrapper.append(input, help);
        fields.append(wrapper);
      }
    }
    controls();
  }

  function renderDataset() {
    const dataset = selectedDataset();
    get("#backtest-dataset-info").textContent = dataset
      ? `${count.format(dataset.row_count)} bars · ${dataset.filename} · ${dataset.start.replace("T", " ").replace("Z", " UTC")} to ${dataset.end.replace("T", " ").replace("Z", " UTC")}`
      : "Choose a saved dataset. New datasets can be uploaded and saved in Datasets.";
    get("#backtest-timezone").textContent = dataset?.source_timezone || "Choose a dataset";
  }

  async function loadChoices() {
    if (state.busy || state.loading) return;
    state.loading = true;
    get("#backtest-options-status").textContent = "Loading datasets and strategies…";
    get("#backtest-error").hidden = true;
    controls();
    try {
      const [datasets, strategies] = await Promise.all([
        fetch("/api/datasets", { cache: "no-store" }).then(readResponse),
        fetch("/api/strategies", { cache: "no-store" }).then(readResponse),
      ]);
      const previousDataset = datasetSelect.value;
      const previousStrategy = strategySelect.value;
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
      datasetSelect.value = Array.from(datasetSelect.options).some((option) => option.value === previousDataset && !option.disabled) ? previousDataset : "";
      strategySelect.replaceChildren(new Option("Choose a strategy", ""));
      for (const strategy of strategies) strategySelect.add(new Option(label(strategy.id), strategy.id));
      strategySelect.value = strategies.some((strategy) => strategy.id === previousStrategy)
        ? previousStrategy : strategies.length === 1 ? strategies[0].id : "";
      state.ready = supported > 0 && strategies.length > 0;
      get("#backtest-options-status").textContent = !supported
        ? "No supported saved datasets. Upload and save a nine-column CSV in Datasets first."
        : !strategies.length ? "No strategies are available on this server." : "";
      get("#backtest-form-hint").textContent = "Instrument settings and costs are supplied explicitly for this run.";
      renderStrategy();
      renderDataset();
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
    if (!form.checkValidity()) {
      const invalid = form.querySelector("input:invalid, select:invalid");
      showError({ message: `${invalid?.closest("label")?.firstChild?.textContent?.trim() || "Configuration"}: ${invalid?.validationMessage || "Complete the required fields."}` });
      form.reportValidity();
      return null;
    }
    const execution = {};
    for (const input of form.querySelectorAll("[data-decimal], #backtest-slippage-ticks")) {
      execution[input.name] = input.hasAttribute("data-integer") ? Number(input.value) : input.value.trim();
    }
    return {
      dataset_id: datasetSelect.value, strategy_id: strategySelect.value,
      strategy_parameters: Object.fromEntries(Array.from(get("#strategy-parameters").querySelectorAll("input"), (input) => [input.dataset.parameter, Number(input.value)])),
      execution_settings: execution,
    };
  }

  function paintProgress(progress, started) {
    const titles = { waiting: "Waiting for server", preparing: "Preparing saved dataset", replaying: "Running backtest",
      saving_report: "Saving report", saving_results: "Saving run results", done: "Backtest saved", failed: "Backtest failed", unconfirmed: "Result unconfirmed" };
    get("#backtest-progress").hidden = false;
    get("#backtest-progress").classList.toggle("failed", ["failed", "unconfirmed"].includes(progress.stage));
    get("#backtest-progress-title").textContent = titles[progress.stage] || "Processing backtest";
    const determinate = !["waiting", "preparing", "failed", "unconfirmed"].includes(progress.stage) && progress.total_bars > 0;
    const percent = determinate ? Math.min(100, progress.bars_processed / progress.total_bars * 100) : null;
    get("#backtest-progress-percent").textContent = percent === null ? "" : `${Math.floor(percent)}% of bars`;
    const bar = get("#backtest-progress-bar");
    if (percent === null) bar.removeAttribute("value");
    else bar.value = percent;
    get("#backtest-progress-detail").textContent = `${count.format(progress.bars_processed || 0)} / ${count.format(progress.total_bars || 0)} bars processed`;
    const seconds = Math.floor((performance.now() - started) / 1000);
    get("#backtest-elapsed").textContent = seconds < 60 ? `${seconds}s elapsed` : `${Math.floor(seconds / 60)}m ${seconds % 60}s elapsed`;
  }

  function completion(record) {
    const content = get("#backtest-completion-content");
    content.replaceChildren();
    const metadata = record.run_metadata;
    const grid = element("dl", "backtest-run-details");
    const pairs = [
      ["Run ID", record.id], ["Dataset", metadata.dataset.name], ["Dataset ID", metadata.dataset.id],
      ["Bars", count.format(metadata.dataset.row_count)], ["Source timezone", metadata.dataset.source_timezone],
      ["Strategy", label(metadata.strategy.id)], ["Timestamp convention", record.timestamp_convention === "bar_close" ? "Bar close" : record.timestamp_convention],
    ];
    for (const [name, value] of pairs) {
      const pair = element("div");
      pair.append(element("dt", "", name), element("dd", name.endsWith("ID") ? "run-identifier" : "", value));
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
    get("#backtest-completion").hidden = false;
    if (!get("#backtests-screen").hidden) get("#backtest-completion").scrollIntoView({ block: "start" });
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (state.busy || state.loading || !state.ready || !state.strategy) return;
    get("#backtest-error").hidden = true;
    const payload = configuration();
    if (!payload) return;
    const operationId = crypto.randomUUID();
    const started = performance.now();
    let current = { stage: "waiting", bars_processed: 0, total_bars: selectedDataset()?.row_count || 0 };
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
          get("#backtest-progress-note").textContent = progress.stage.startsWith("saving")
            ? "Replay finished. Waiting for results to be saved."
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
      const response = await fetch(`/api/backtests?progress_id=${operationId}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
      });
      const record = await readResponse(response);
      if (record.status !== "complete" || !record.id) throw new Error("The server did not confirm a completed run.");
      finished = true;
      current = { stage: "done", bars_processed: record.run_metadata.dataset.row_count, total_bars: record.run_metadata.dataset.row_count };
      completion(record);
      get("#backtest-progress-note").textContent = `Run ${record.id} saved successfully.`;
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

  form.addEventListener("input", (event) => event.target.setCustomValidity?.(""));
  datasetSelect.addEventListener("change", renderDataset);
  strategySelect.addEventListener("change", renderStrategy);
  refresh.addEventListener("click", loadChoices);

  function navigate() {
    const screen = location.hash === "#backtests" ? "backtests" : "datasets";
    get("#datasets-screen").hidden = screen !== "datasets";
    get("#backtests-screen").hidden = screen !== "backtests";
    get("#current-screen").textContent = screen === "backtests" ? "Backtests" : "Datasets";
    document.title = `${screen === "backtests" ? "Backtests" : "Datasets"} · AlphaQuest`;
    for (const link of document.querySelectorAll("[data-screen]")) {
      const active = link.dataset.screen === screen;
      link.classList.toggle("active", active);
      if (active) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    }
    get("#footer-context").textContent = screen === "backtests" ? "Backtests · Configure and run" : "Dataset management · Component 1 of your research workflow";
    if (screen === "backtests") loadChoices();
  }
  window.addEventListener("hashchange", navigate);
  navigate();
})();
