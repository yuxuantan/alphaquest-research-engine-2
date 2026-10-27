"use strict";

(() => {
  const get = (selector) => document.querySelector(selector);
  const node = (tag, text, cls) => {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (cls) element.className = cls;
    return element;
  };
  const label = (name) => name.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase());
  const drafts = new Map();
  let strategy;
  let jobId = null;
  let sort = "trial", direction = "asc", offset = 0, total = 0;
  let version = 0, timer;
  let workerState = "idle", workerValue = "";
  const workerHelp = get("#optimization-workers-help").textContent;
  const pageSize = () => jobId ? 50 : 25;
  const resultScroll = get("#optimization-results-scroll");
  let headerFrame = null;
  function pinHeaders() {
    if (headerFrame !== null) return;
    headerFrame = requestAnimationFrame(() => {
      headerFrame = null;
      const table = get("#optimization-results");
      const height = table.tHead.getBoundingClientRect().height;
      const widths = Array.from(table.querySelectorAll("thead .optimization-frozen-parameter"),
                                (cell) => cell.getBoundingClientRect().width);
      // Sticky positioning uses the table's scroll box. Offset that position
      // when the page moves the box above the viewport; keep the real, sortable
      // header aligned with its cells for both horizontal and vertical scrolling.
      const offset = Math.min(Math.max(0, -resultScroll.getBoundingClientRect().top),
                              Math.max(0, resultScroll.clientHeight - height));
      resultScroll.style.setProperty("--optimization-header-top", `${offset}px`);
      // Use rendered widths so resized views and different result pages keep
      // every frozen column adjacent, with the same offsets in header and body.
      let left = 0;
      widths.forEach((width, index) => {
        table.style.setProperty(`--optimization-frozen-left-${index}`, `${left}px`);
        left += width;
      });
    });
  }
  window.addEventListener("scroll", pinHeaders, {passive: true});
  window.addEventListener("resize", pinHeaders);
  new ResizeObserver(pinHeaders).observe(resultScroll);
  new ResizeObserver(pinHeaders).observe(get("#optimization-results"));
  function settings(config) {
    if (!Number.isInteger(config?.max_workers) || config.max_workers < 1 || config.max_workers > 8
        || !Number.isInteger(config.default_workers) || config.default_workers < 1 || config.default_workers > config.max_workers) {
      throw new Error("The server returned invalid worker options.");
    }
    const select = get("#optimization-workers");
    const previous = select.value || workerValue;
    select.replaceChildren();
    for (let workers = 1; workers <= config.max_workers; workers++) {
      select.add(new Option(`${workers}${workers === 1 ? " · serial" : " processes"}${workers === config.default_workers ? " · default" : ""}`, String(workers)));
    }
    select.value = previous && Number(previous) <= config.max_workers ? previous : String(config.default_workers);
  }
  async function loadSettings() {
    if (workerState === "loading") return;
    const select = get("#optimization-workers");
    workerValue = select.value || workerValue;
    workerState = "loading";
    select.replaceChildren(new Option("Loading worker options…", ""));
    get("#optimization-workers-help").textContent = "Loading available worker counts…";
    get("#optimization-workers-retry").hidden = true;
    window.dispatchEvent(new Event("optimization-workers-changed"));
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch("/api/optimizations/settings", {cache: "no-store", signal: controller.signal});
      if ([404, 422].includes(response.status)) throw new Error("This server needs to be restarted to load parallel optimization support. Restart the backend, then retry.");
      if (!response.ok) throw new Error(`Could not load worker options (HTTP ${response.status}). Retry worker options.`);
      settings(await response.json());
      workerState = "ready";
      get("#optimization-workers-help").textContent = workerHelp;
    } catch (error) {
      workerState = "error";
      select.replaceChildren(new Option("Worker options unavailable", ""));
      get("#optimization-workers-help").textContent = error.name === "AbortError"
        ? "Loading worker options timed out. Retry worker options."
        : error instanceof SyntaxError ? "The server returned unreadable worker options. Retry worker options."
        : error instanceof TypeError ? "Could not connect to load worker options. Retry worker options." : error.message;
      get("#optimization-workers-retry").hidden = false;
    } finally {
      clearTimeout(timeout);
      window.dispatchEvent(new Event("optimization-workers-changed"));
    }
  }
  async function read(url, options = {}) {
    const response = await fetch(url, { cache: "no-store", ...options });
    const result = await response.json();
    if (!response.ok) throw result;
    return result;
  }
  function errorMessage(error) {
    return typeof error.detail === "string" ? error.detail : Array.isArray(error.detail)
      ? error.detail.map((item) => `${item.loc?.join(" / ")}: ${item.msg}`).join("; ") : error.message || "Request failed. Check the server connection.";
  }
  function remember() {
    if (!strategy) return;
    const values = {};
    for (const row of get("#optimization-ranges").rows) {
      values[row.dataset.parameter] = Object.fromEntries(Array.from(row.querySelectorAll("input,select"), (input) => [input.dataset.range, input.value]));
    }
    drafts.set(strategy.id, values);
  }
  function decimal(value) {
    const text = value.trim();
    const match = text.match(/^([+-]?)(\d+(?:\.\d*)?|\.\d+)(?:[eE]([+-]?\d+))?$/);
    if (!match || text.length > 128) throw new Error("Enter a finite decimal number.");
    const digits = match[2].replace(".", "");
    const exponent = Number(match[3] || 0) - (match[2].split(".")[1]?.length || 0);
    const significant = digits.replace(/^0+/, "");
    const adjusted = significant ? exponent + significant.length - 1 : exponent;
    if (!Number.isSafeInteger(exponent) || exponent < -100 || Math.abs(adjusted) > 100) throw new Error("Use decimals within 100 decimal places/orders of magnitude.");
    return { coefficient: BigInt((match[1] === "-" ? "-" : "") + digits), exponent };
  }
  function scaled(values) {
    const exponent = Math.min(...values.map((value) => value.exponent));
    return values.map((value) => value.coefficient * 10n ** BigInt(value.exponent - exponent));
  }
  function safeInteger(text) {
    const value = decimal(text);
    const divisor = value.exponent < 0 ? 10n ** BigInt(-value.exponent) : 1n;
    if (value.coefficient % divisor !== 0n) return false;
    const integer = value.exponent < 0 ? value.coefficient / divisor : value.coefficient * 10n ** BigInt(value.exponent);
    return integer >= -9007199254740991n && integer <= 9007199254740991n;
  }
  function rowCount(row, parameter, resetStep = false) {
    const input = (part) => row.querySelector(`[data-range="${part}"]`);
    const step = input("step");
    for (const part of ["start", "end", "step"]) input(part).setCustomValidity("");
    try {
      const boolean = parameter.type === "bool";
      const [a, b] = boolean ? [input("start").value, input("end").value]
        : scaled([decimal(input("start").value), decimal(input("end").value)]);
      if (a === b) {
        step.value = "0";
        step.readOnly = true;
      } else {
        step.readOnly = false;
        if (resetStep && (step.value.trim() === "" || /^0(?:\.0*)?$/.test(step.value.trim()))) step.value = "1";
      }
      let count;
      if (boolean) {
        if (step.value !== (a === b ? "0" : "1")) throw new Error("Boolean step must be 0 for a fixed value or 1 for both values.");
        count = a === b ? 1n : 2n;
      } else {
        const [start, end, increment] = scaled([decimal(input("start").value), decimal(input("end").value), decimal(step.value)]);
        if (start > end) throw new Error("Start must be less than or equal to end.");
        if (parameter.type === "int" && [input("start"), input("end"), step].some((field) => !safeInteger(field.value))) throw new Error("Enter whole numbers within the supported integer range.");
        if (start !== end && increment <= 0n) throw new Error("Step must be greater than zero when endpoints differ.");
        count = start === end ? 1n : (end - start) / increment + 1n;
      }
      input("step_count").value = String(count);
      return count;
    } catch (error) {
      input("step_count").value = "";
      (step.readOnly ? input("start") : step).setCustomValidity(error.message);
      return null;
    }
  }
  function count() {
    if (!strategy) return;
    const counts = Array.from(get("#optimization-ranges").rows, (row, index) => rowCount(row, strategy.parameters[index]));
    if (counts.some((value) => value === null)) {
      get("#optimization-count").textContent = "Total combinations: fix invalid ranges or steps to calculate the backtest count.";
      return;
    }
    const combinations = counts.reduce((a, b) => a * b, 1n);
    const factors = counts.filter((value) => value > 1n);
    get("#optimization-count").textContent = `Total combinations: ${(factors.length ? factors : [1n]).join(" × ")} = ${combinations.toLocaleString("en-US")} ${combinations === 1n ? "backtest" : "backtests"}${combinations > 10000n ? " · exceeds the 10,000 limit" : ""}`;
  }
  function configure(next) {
    remember();
    strategy = next;
    get("#optimization-ranges").replaceChildren();
    if (!strategy) return;
    for (const parameter of strategy.parameters) {
      const row = node("tr");
      row.dataset.parameter = parameter.name;
      const title = node("th", label(parameter.name));
      title.scope = "row";
      title.append(node("small", parameter.description, "field-help"));
      row.append(title);
      for (const part of ["start", "end", "step", "step_count"]) {
        const cell = node("td");
        const input = node(parameter.type === "bool" && ["start", "end"].includes(part) ? "select" : "input");
        const saved = drafts.get(strategy.id)?.[parameter.name]?.[part];
        if (input.tagName === "SELECT") {
          input.add(new Option("False", "false"));
          input.add(new Option("True", "true"));
        } else if (part === "step_count") {
          input.type = "text";
          input.readOnly = true;
          input.title = "Calculated automatically from start, end and step.";
        } else {
          // Preserve entered digits: number inputs can round on blur before
          // validation/submission, changing an intended integer increment.
          input.type = "text";
          input.inputMode = parameter.type === "Decimal" ? "decimal" : "numeric";
          input.maxLength = 128;
          if (part === "step") { input.min = "0"; input.step = parameter.type === "Decimal" ? "any" : "1"; }
          else if (parameter.type === "int") {
            input.step = "1";
            input.max = String(parameter.maximum ?? Number.MAX_SAFE_INTEGER);
            if (parameter.minimum !== undefined) input.min = String(parameter.minimum);
          }
          if (parameter.type === "Decimal") { input.inputMode = "decimal"; input.maxLength = 128; }
        }
        input.value = saved ?? String(part === "step" ? 0 : part === "step_count" ? 1 : parameter.default);
        input.required = true;
        input.dataset.range = part;
        input.setAttribute("aria-label", `${label(parameter.name)} ${part === "step_count" ? "step count" : part}`);
        input.addEventListener("input", () => { rowCount(row, parameter, part === "start" || part === "end"); count(); get("#backtest-error").hidden = true; });
        cell.append(input);
        row.append(cell);
      }
      rowCount(row, parameter, true);
      get("#optimization-ranges").append(row);
    }
    count();
  }
  async function start(payload) {
    if (workerState !== "ready") throw new Error("Load worker options successfully before starting optimization. Use Retry worker options.");
    remember();
    const parameter_ranges = {};
    for (const parameter of strategy.parameters) {
      const spec = drafts.get(strategy.id)[parameter.name];
      const convert = (value) => parameter.type === "bool" ? value === "true" : parameter.type === "int" ? Number(value) : value.trim();
      parameter_ranges[parameter.name] = { start: convert(spec.start), end: convert(spec.end), step: parameter.type === "Decimal" ? spec.step.trim() : Number(spec.step) };
    }
    const { strategy_parameters, ...settings } = payload;
    let job;
    try {
      job = await read("/api/optimizations", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...settings, method: "exhaustive", parameter_ranges, workers: Number(get("#optimization-workers").value) }) });
    } catch (error) {
      if (error instanceof TypeError || error instanceof SyntaxError) throw new Error("Completion is unconfirmed. Check optimization history before starting another job; the request was not retried.");
      throw error;
    }
    location.hash = `#optimizations/${job.id}`;
  }
  function pagination() {
    get("#optimization-page").textContent = total ? `${offset + 1}–${Math.min(total, offset + pageSize())} of ${total}` : "No saved results yet";
    get("#optimization-previous").disabled = offset === 0;
    get("#optimization-next").disabled = offset + pageSize() >= total;
  }
  function results(job, page) {
    const table = get("#optimization-results");
    const header = node("tr");
    const varying = new Set(Object.keys(job.axes).filter((name) => job.axes[name].length > 1).map((name) => `param.${name}`));
    const legend = get("#optimization-parameter-legend");
    legend.hidden = false;
    legend.textContent = varying.size
      ? `Highlighted columns vary across trials: ${Array.from(varying, (key) => label(key.slice(6))).join(", ")}. These columns are frozen on the left; headers marked “Varies” identify the optimized parameters.`
      : "All strategy parameters are fixed for this run.";
    const parameters = Object.keys(job.axes).map((name) => [`param.${name}`, label(name)]);
    const columns = [...parameters.filter(([key]) => varying.has(key)), ["trial", "Trial"],
      ...parameters.filter(([key]) => !varying.has(key)),
      ...job.metric_columns.map((name) => [name, label(name)]), ["run_id", "Backtest report"]];
    const freeze = (cell, key) => {
      const index = columns.findIndex(([name]) => name === key);
      cell.classList.add("optimization-varying-parameter", "optimization-frozen-parameter");
      if (index === varying.size - 1) cell.classList.add("optimization-frozen-last");
      cell.style.setProperty("--optimization-frozen-left", `var(--optimization-frozen-left-${index}, 0px)`);
    };
    for (const [key, title] of columns) {
      const th = node("th");
      th.scope = "col";
      th.dataset.column = key;
      th.setAttribute("aria-sort", sort === key ? direction === "asc" ? "ascending" : "descending" : "none");
      const button = node("button", `${title}${sort === key ? direction === "asc" ? " ↑" : " ↓" : " ↕"}`);
      button.type = "button";
      if (varying.has(key)) {
        freeze(th, key);
        th.title = `${job.axes[key.slice(6)].length} values in this optimization grid`;
        button.append(node("span", "Varies", "optimization-varying-badge"));
      }
      button.onclick = () => { direction = sort === key && direction === "asc" ? "desc" : "asc"; sort = key; offset = 0; refresh(); };
      th.append(button);
      header.append(th);
    }
    table.tHead.replaceChildren(header);
    table.tBodies[0].replaceChildren();
    for (const row of page.items) {
      const tr = node("tr");
      for (const [key] of columns) {
        const td = node("td");
        td.dataset.column = key;
        if (varying.has(key)) freeze(td, key);
        if (key === "run_id") {
          const link = node("a", row.run_id);
          link.href = `#backtests/report/${row.run_id}`;
          td.append(link);
        } else {
          const value = key === "trial" ? row.trial : key.startsWith("param.") ? row.parameters[key.slice(6)] : row.metrics[key];
          td.textContent = value == null ? "N/A" : String(value);
        }
        tr.append(td);
      }
      table.tBodies[0].append(tr);
    }
    const download = get("#optimization-download");
    download.href = `/api/optimizations/${job.id}/exports/results?${new URLSearchParams({sort, direction})}`;
    download.hidden = false;
    total = page.total;
    pagination();
    pinHeaders();
  }
  async function refresh() {
    clearTimeout(timer);
    const current = ++version;
    try {
      if (!jobId) {
        get("#optimization-parameter-legend").hidden = true;
        const history = await read(`/api/optimizations?${new URLSearchParams({offset, limit: 25})}`);
        if (current !== version) return;
        get("#optimization-title").textContent = "Saved optimizations";
        get("#optimization-context").textContent = "Reopen running jobs and durable results.";
        get("#optimization-status").textContent = history.total ? "Select a job to inspect its grid and results." : "No optimizations yet. Configure the grid above to start.";
        const table = get("#optimization-results");
        const header = node("tr");
        for (const title of ["Created · UTC", "Strategy", "Status", "Completed trials"]) header.append(node("th", title));
        table.tHead.replaceChildren(header);
        table.tBodies[0].replaceChildren();
        for (const job of history.items) {
          const row = node("tr"), cell = node("td"), link = node("a", job.created_at_utc);
          link.href = `#optimizations/${job.id}`;
          cell.append(link);
          row.append(cell, node("td", label(job.strategy.id)), node("td", job.status), node("td", `${job.completed_trials} / ${job.total_trials}`));
          table.tBodies[0].append(row);
        }
        total = history.total;
        pagination();
        pinHeaders();
        if (history.items.some((job) => ["queued", "running"].includes(job.status))) timer = setTimeout(refresh, 1500);
        return;
      }
      const [job, page] = await Promise.all([
        read(`/api/optimizations/${jobId}`),
        read(`/api/optimizations/${jobId}/results?${new URLSearchParams({sort, direction, offset, limit: 50})}`),
      ]);
      if (current !== version) return;
      get("#optimization-title").textContent = "Optimization results";
      get("#optimization-context").textContent = `${job.dataset.name} · ${label(job.strategy.id)} · ${job.id}`;
      const execution = `${job.worker_count || 1} ${job.worker_count > 1 ? "worker processes" : "worker · serial"}${job.elapsed_seconds == null ? "" : ` · ${job.elapsed_seconds.toFixed(1)}s elapsed`}`;
      const activeTrials = job.active_trials?.length ? ` · active trials ${job.active_trials.map((trial) => `${trial.trial} (${trial.bars_processed}/${trial.total_bars} bars)`).join(", ")}` : "";
      get("#optimization-status").textContent = `${job.status.toUpperCase()} · ${job.completed_trials} / ${job.total_trials} trials saved · ${execution} · ${job.stage.replaceAll("_", " ")}${job.status === "running" ? activeTrials : ""}${job.error ? ` · ${job.error}` : ""}. Click any column heading to sort ascending or descending. Monetary metrics use CU; drawdown duration uses seconds. N/A sorts last. Completed trials remain available if a job fails or is interrupted.`;
      get("#optimization-provenance").hidden = false;
      get("#optimization-settings-used").textContent = JSON.stringify({request: job.request, worker_count: job.worker_count || 1, axes: job.axes, dataset: job.dataset, strategy: job.strategy, execution_settings: job.execution_settings}, null, 2);
      results(job, page);
      if (["queued", "running"].includes(job.status)) timer = setTimeout(refresh, 1000);
    } catch (error) {
      if (current !== version) return;
      get("#optimization-status").textContent = `Could not refresh: ${errorMessage(error)}. Saved results below may be stale. Retrying…`;
      timer = setTimeout(refresh, 3000);
    }
  }
  function navigate() {
    ++version;
    clearTimeout(timer);
    const active = location.hash.startsWith("#optimizations");
    get("#optimization-panel").hidden = !active;
    if (!active) return;
    jobId = location.hash.match(/^#optimizations\/([0-9a-f]{32})$/)?.[1] || null;
    offset = 0; sort = "trial"; direction = "asc";
    get("#optimization-provenance").hidden = true;
    get("#optimization-download").hidden = true;
    get("#optimization-status").textContent = "Loading…";
    get("#optimization-results").tHead.replaceChildren();
    get("#optimization-results").tBodies[0].replaceChildren();
    get("#optimization-parameter-legend").hidden = true;
    refresh();
  }
  get("#optimization-previous").onclick = () => { offset = Math.max(0, offset - pageSize()); refresh(); };
  get("#optimization-next").onclick = () => { offset += pageSize(); refresh(); };
  get("#optimization-workers-retry").onclick = () => { void loadSettings(); };
  window.optimizations = { configure, start, loadSettings, workersReady: () => workerState === "ready" };
  window.addEventListener("hashchange", navigate);
  navigate();
})();
