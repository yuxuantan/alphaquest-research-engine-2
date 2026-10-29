"use strict";

(() => {
  const get = selector => document.querySelector(selector);
  const node = (tag, text) => { const item = document.createElement(tag); if (text !== undefined) item.textContent = text; return item; };
  const number = new Intl.NumberFormat("en-US", {maximumFractionDigits: 2});
  const formatted = (value, suffix = "") => value == null ? "N/A" : `${number.format(value)}${suffix}`;
  const exact = (value, suffix = "") => value == null ? "N/A" : `${value}${suffix}`;
  let controller, data;

  function periods() {
    const body = get("#market-benchmark-periods"); body.replaceChildren();
    for (const item of data[get("#market-benchmark-period").value]) {
      const row = node("tr");
      for (const key of ["period", "strategy_net_pnl", "holding_net_pnl", "excess_net_pnl"]) row.append(node("td", item[key]));
      body.append(row);
    }
  }

  function draw() {
    if (!data) return;
    const svg = get("#market-benchmark-chart"); svg.replaceChildren();
    const excess = get("#market-benchmark-view").value === "excess";
    const fields = excess ? ["excess_net_pnl"] : ["strategy_equity", "holding_equity"];
    svg.setAttribute("aria-label", excess ? "Cumulative excess net profit in account currency" : "Strategy and holding mark-to-market equity in account currency");
    get("#market-benchmark-legend").textContent = excess ? "Strategy minus holding · CU" : "Strategy (blue) · Long holding (orange, dashed) · CU";
    const points = data.chart.items;
    const values = points.flatMap(p => fields.map(field => Number(p[field])));
    let lower = Math.min(...values), upper = Math.max(...values);
    if (!values.every(Number.isFinite) || !Number.isFinite(upper - lower)) {
      get("#market-benchmark-readout").textContent = "Values exceed the chart's numeric range. Exact values are saved in the downloads.";
      return;
    }
    const padding = upper === lower ? Math.max(Math.abs(lower) * .01, 1) : (upper - lower) * .05;
    lower -= padding; upper += padding;
    if (!Number.isFinite(lower) || !Number.isFinite(upper) || upper <= lower || !Number.isFinite(upper - lower)) {
      get("#market-benchmark-readout").textContent = "Values exceed the chart's numeric range. Exact values are saved in the downloads.";
      return;
    }
    const ticks = Array.from({length: 5}, (_, i) => lower + (upper - lower) * i / 4);
    const labels = ticks.map(value => new Intl.NumberFormat("en-US", Math.abs(value) >= 1e9 || (value && Math.abs(value) < .01)
      ? {notation: "scientific", maximumSignificantDigits: 5} : {maximumFractionDigits: 2}).format(value));
    const left = Math.max(75, ...labels.map(text => text.length * 7 + 20)), right = 975;
    const start = Date.parse(data.period_start_utc), end = Date.parse(data.period_end_utc);
    const x = point => left + (point.timestamp_utc ? Date.parse(point.timestamp_utc) - start : 0) / Math.max(1, end - start) * (right - left);
    const y = value => 235 - (Number(value) - lower) / (upper - lower) * 205;
    const add = (tag, attrs, text) => {
      const item = document.createElementNS("http://www.w3.org/2000/svg", tag);
      Object.entries(attrs).forEach(([key, value]) => item.setAttribute(key, value));
      if (text !== undefined) item.textContent = text;
      svg.append(item); return item;
    };
    ticks.forEach((tick, i) => {
      add("line", {x1: left, x2: right, y1: y(tick), y2: y(tick), class: "chart-grid"});
      add("text", {x: left - 10, y: y(tick) + 4, "text-anchor": "end", class: "chart-label"}, labels[i]);
    });
    fields.forEach((field, i) => add("polyline", {points: points.map(point => `${x(point)},${y(point[field])}`).join(" "), class: `chart-line market-series-${i}`}));
    add("text", {x: left, y: 275, class: "chart-label"}, data.period_start_utc.slice(0, 10));
    add("text", {x: right, y: 275, "text-anchor": "end", class: "chart-label"}, `${data.period_end_utc.slice(0, 10)} · UTC`);
    const cursor = add("line", {x1: left, x2: left, y1: 25, y2: 240, class: "market-cursor"});
    const formatter = new Intl.DateTimeFormat("en-GB", {timeZone: data.source.dataset.source_timezone, dateStyle: "medium", timeStyle: "medium"});
    let selected = 0;
    function inspect(index) {
      selected = Math.max(0, Math.min(index, points.length - 1));
      const point = points[selected];
      cursor.setAttribute("x1", x(point)); cursor.setAttribute("x2", x(point));
      get("#market-benchmark-readout").textContent = `${point.timestamp_utc ? formatter.format(new Date(point.timestamp_utc)) + " " + data.source.dataset.source_timezone : "Initial balance"} · Strategy ${point.strategy_equity} CU · Holding ${point.holding_equity} CU · Excess ${point.excess_net_pnl} CU`;
    }
    svg.onpointermove = event => {
      const rect = svg.getBoundingClientRect(), target = (event.clientX - rect.left) / rect.width * 1000;
      let nearest = 0;
      for (let i = 1; i < points.length; i++) if (Math.abs(x(points[i]) - target) < Math.abs(x(points[nearest]) - target)) nearest = i;
      inspect(nearest);
    };
    svg.onkeydown = event => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      inspect(event.key === "Home" ? 0 : event.key === "End" ? points.length - 1 : selected + (event.key === "ArrowRight" ? 1 : -1));
    };
    svg.dataset.points = points.length; svg.dataset.total = data.chart.total;
    const daily = data.chart.granularity === "DAY";
    const frequency = daily ? `DAY granularity: initial balance plus the last selected bar of each calendar date in ${data.storage.timezone}. Holding equity is stored once and shared across matching runs. ` : "Legacy per-bar series. ";
    get("#market-benchmark-chart-note").textContent = `${frequency}${points.length} of ${data.chart.total} observations shown. ${data.chart.sampled ? "Endpoints and bucket extremes for both accounts and their difference; lines omit intermediate observations." : "Full saved series shown."} Horizontal spacing uses elapsed UTC time; gaps remain gaps. Summary metrics still use every selected bar, including bar-close drawdown. Hover or use arrow keys for exact values.`;
    inspect(points.length - 1);
  }

  async function load(record) {
    controller?.abort(); controller = new AbortController();
    const current = controller; data = null;
    get("#market-benchmark-results").hidden = true;
    get("#market-benchmark-context").textContent = "";
    get("#market-benchmark-status").textContent = "Loading saved comparison…";
    try {
      const response = await fetch(`/api/backtests/${record.id}/market-benchmark`, {cache: "no-store", signal: current.signal});
      const result = await response.json();
      if (controller !== current) return;
      if (!response.ok) throw new Error(result.detail || `HTTP ${response.status}`);
      if (result.unavailable) { get("#market-benchmark-status").textContent = result.unavailable; return; }
      data = result;
      get("#market-benchmark-status").textContent = "Price-series comparison · Executable futures performance unverified: contract identity and roll prices/costs are not recorded.";
      get("#market-benchmark-context").textContent = `${record.run_metadata.research?.phase?.toUpperCase() || "Saved"} period only · ${data.settings.contracts} fixed long contract(s) · First Open → final Close · Same starting capital and fill costs · ${data.version}`;
      get("#market-benchmark-checks").textContent = `Source checked during backtest; ${data.observed_bar_count} selected bars align with native equity. Strategy ending equity reconciles. Saved comparison and equity hashes verified.`;
      const warnings = [];
      if (data.accounts.strategy.max_contracts !== data.settings.contracts) warnings.push("Strategy and benchmark quantities differ; this comparison is not risk matched.");
      if (data.accounts.strategy.short_trades) warnings.push("The strategy includes short trades; the benchmark remains long.");
      if (data.source.strategy.session_flattening) warnings.push("Inspect the saved session-flattening assumption; historical lookahead may apply.");
      if (Object.values(data.accounts).some(account => account.nonpositive_equity)) warnings.push("An account reached nonpositive equity. Arithmetic continues without margin liquidation; this path does not establish trading feasibility.");
      get("#market-benchmark-warning").textContent = warnings.join(" ");
      const body = get("#market-benchmark-metrics"); body.replaceChildren();
      const metrics = [
        ["Net profit · CU", "net_pnl"], ["Return on starting equity", "return_pct", "%"],
        ["Mark-to-market max drawdown · CU", "max_drawdown_amount"], ["Mark-to-market max drawdown", "max_drawdown_pct", "%"],
        ["Longest drawdown · seconds", "max_drawdown_duration_seconds"], ["Time in market · fill-bar timestamps", "time_in_market_pct", "%"],
        ["Average contracts while held", "average_contracts_while_held"], ["Maximum contracts", "max_contracts"],
        ["Average bar-close notional · CU", "average_bar_close_notional"], ["Maximum bar-close notional · CU", "maximum_bar_close_notional"],
        ["Maximum bar-close notional / starting capital", "maximum_bar_close_leverage", "×"],
        ["Commission · CU", "total_commissions"], ["Slippage cost · CU", "total_slippage_cost"],
      ];
      for (const [label, key, suffix = ""] of metrics) {
        const row = node("tr"); row.dataset.metric = key; row.append(node("th", label));
        for (const account of [data.accounts.strategy, data.accounts.holding]) {
          const cell = node("td", formatted(account[key], suffix)); cell.title = exact(account[key], suffix); row.append(cell);
        }
        body.append(row);
      }
      get("#market-benchmark-excess").textContent = `Excess net P&L: ${data.excess_net_pnl} CU (strategy minus holding). This is not a risk-adjusted alpha estimate.`;
      const assumptions = get("#market-benchmark-assumptions"); assumptions.replaceChildren(...data.assumptions.map(text => node("li", text)));
      get("#market-benchmark-source").textContent = JSON.stringify({source: data.source, source_checks: data.source_checks, entry: data.entry, holding_trade: data.holding_trade, equity_sha256: data.equity_sha256}, null, 2);
      get("#market-benchmark-json").href = `/api/backtests/${record.id}/exports/market_benchmark`;
      get("#market-benchmark-csv").href = `/api/backtests/${record.id}/exports/market_equity`;
      get("#market-benchmark-csv").textContent = data.storage?.granularity === "DAY" ? "Daily comparison CSV ↓" : "Aligned equity CSV ↓";
      get("#market-benchmark-results").hidden = false;
      periods(); draw();
    } catch (error) {
      if (controller === current && !current.signal.aborted) get("#market-benchmark-status").textContent = `Comparison unavailable: ${error.message}`;
    }
  }
  get("#market-benchmark-view").addEventListener("change", draw);
  get("#market-benchmark-period").addEventListener("change", () => { if (data) periods(); });
  window.addEventListener("report-loaded", event => load(event.detail));
  window.addEventListener("hashchange", () => { controller?.abort(); data = null; });
})();
