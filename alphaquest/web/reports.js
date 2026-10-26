"use strict";

(() => {
  const get = (selector) => document.querySelector(selector);
  const number = new Intl.NumberFormat("en-US");
  const percentage = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2, useGrouping: false });
  const formatPercentage = (value) => value == null ? "N/A" : `${percentage.format(value)}%`;
  const pageSize = 50;
  let active;
  let runId;
  let tradeOffset = 0;
  let historyOffset = 0;
  let historyVersion = 0;
  let chartData;
  let tradeTimeZone = "UTC";
  let tradeTimeFormatter;
  const node = (tag, text, cls) => {
    const item = document.createElement(tag);
    if (text !== undefined) item.textContent = text;
    if (cls) item.className = cls;
    return item;
  };
  const stamp = (value) => value ? value.replace("T", " ").replace("Z", "") : "Initial balance";
  function tradeStamp(value) {
    const parts = Object.fromEntries(tradeTimeFormatter.formatToParts(new Date(value)).map((part) => [part.type, part.value]));
    return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}:${parts.second}`;
  }
  function tradeTimezone(record) {
    tradeTimeZone = record.run_metadata.dataset.source_timezone || "UTC";
    tradeTimeFormatter = new Intl.DateTimeFormat("en-GB", {
      timeZone: tradeTimeZone, calendar: "iso8601", numberingSystem: "latn", hourCycle: "h23",
      year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
    get("#report-entry-time-header").textContent = `Entry · ${tradeTimeZone}`;
    get("#report-exit-time-header").textContent = `Exit · ${tradeTimeZone}`;
    get("#report-trade-timezone-note").textContent = `${tradeTimeZone} timestamps · P&L in CU`;
    get("#report-trade-timezone-hint").textContent = `Entry and exit times use ${tradeTimeZone} (dataset timezone). CSV exports use UTC. Scroll horizontally for all trade fields.`;
  }
  const moneyClass = (value) => Number(value) < 0 ? "negative" : Number(value) > 0 ? "positive" : "";
  async function read(url, signal) {
    const response = await fetch(url, { cache: "no-store", signal });
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : `Report request failed (HTTP ${response.status}).`);
    return result;
  }
  function error(message) {
    get("#report-status").hidden = false;
    get("#report-status").textContent = message;
  }
  function duration(value) {
    if (value === undefined) return "N/A";
    let seconds = Number(value);
    if (!seconds) return "0s";
    const parts = [];
    for (const [unit, size] of [["d", 86400], ["h", 3600], ["m", 60]]) {
      const count = Math.floor(seconds / size);
      if (count) parts.push(`${count}${unit}`);
      seconds %= size;
    }
    if (seconds) parts.push(`${Number(seconds.toFixed(6))}s`);
    return parts.join(" ");
  }
  function metrics(record) {
    const summary = record.summary;
    const holder = get("#report-summary");
    holder.replaceChildren();
    for (const [title, value, key] of [
      ["Total net P&L · CU", summary.total_net_pnl, "net"],
      ["Trades taken", number.format(summary.trades_taken), "trades"],
      ["Win rate", formatPercentage(summary.win_rate_pct), "win-rate"],
      ["Max drawdown · CU", summary.max_drawdown_amount ?? "N/A", "drawdown-amount"],
      ["Max drawdown · %", formatPercentage(summary.max_drawdown_pct), "drawdown-pct"],
      ["Max drawdown duration", duration(summary.max_drawdown_duration_seconds), "drawdown-duration"],
    ]) {
      const card = node("div", undefined, "panel report-metric");
      card.append(node("span", title, "stat-label"));
      const amount = node("strong", value, key === "net" ? moneyClass(value) : "");
      amount.id = `report-${key}`;
      card.append(amount);
      if (key === "net") card.append(node("p", `Gross ${summary.total_gross_pnl} · Commissions ${summary.total_commissions}`, "small muted"));
      if (key === "trades") card.append(node("p", `${summary.winning_trades} winning · ${summary.losing_trades} losing · ${summary.breakeven_trades} breakeven`, "small muted"));
      if (key === "win-rate") card.append(node("p", "Winners / all completed trades; breakevens included.", "small muted"));
      if (key === "drawdown-amount") card.append(node("p", "Largest peak-to-trough fall in trade-close equity, after all costs.", "small muted"));
      if (key === "drawdown-pct") card.append(node("p", "Largest percentage fall relative to its prior equity peak.", "small muted"));
      if (key === "drawdown-duration") card.append(node("p", "Longest elapsed UTC time from a peak to recovery, or dataset end if unrecovered. Initial balance uses the first bar's time.", "small muted"));
      holder.append(card);
    }
    const balances = node("p", `Initial equity ${summary.initial_capital} CU → Final equity ${summary.final_equity} CU. Account currency unspecified.`, "report-balances small");
    balances.id = "report-balances";
    holder.append(balances);
  }
  function equityScale(min, max) {
    // Aim for about five labels, extending the domain to clean step multiples.
    // Do not force zero: a large starting balance can have a small trading range.
    if (min === max) {
      const padding = Math.abs(min) * .01 || 1;
      min -= padding;
      max += padding;
    }
    const roughStep = (max - min) / 4;
    const exponent = Math.floor(Math.log10(roughStep));
    const magnitude = 10 ** exponent;
    const multiple = [1, 2, 2.5, 5, 10].find((value) => value * magnitude >= roughStep) || 10;
    const step = multiple * magnitude || Number.MIN_VALUE;
    // Parse decimal multiples once, avoiding artifacts such as 0.30000000000000004.
    const tickAt = (index) => magnitude ? Number(`${index * multiple}e${exponent}`) : index * step;
    let first = Math.floor(min / step), last = Math.ceil(max / step);
    if (tickAt(first) > min) first--;
    if (tickAt(last) < max) last++;
    const lower = tickAt(first), upper = tickAt(last);
    if (![lower, upper, step, upper - lower].every(Number.isFinite) || upper <= lower || last - first > 10) return null;
    const ticks = Array.from({ length: last - first + 1 }, (_, i) => tickAt(first + i));
    if (ticks.some((value, i) => i && value <= ticks[i - 1])) return null;
    const decimals = Math.min(100, Math.max(0, -exponent + (multiple === 2.5 ? 1 : 0)));
    const significant = Math.min(17, Math.max(3, Math.ceil(Math.log10(Math.max(1, Math.max(Math.abs(lower), Math.abs(upper)) / step))) + 2));
    const labels = ticks.map((value) => new Intl.NumberFormat("en-US", Math.abs(value) >= 1e9 || (value !== 0 && Math.abs(value) < .0001)
      ? { notation: "scientific", maximumSignificantDigits: significant }
      : { maximumFractionDigits: decimals }).format(Object.is(value, -0) ? 0 : value));
    return { lower, upper, step, ticks, labels };
  }

  function chart(data) {
    chartData = data;
    const svg = get("#equity-chart");
    const width = Math.max(320, svg.clientWidth);
    const right = width - 20;
    svg.setAttribute("viewBox", `0 0 ${width} 300`);
    const ns = "http://www.w3.org/2000/svg";
    const draw = (tag, attrs, text) => {
      const item = document.createElementNS(ns, tag);
      for (const [key, value] of Object.entries(attrs)) item.setAttribute(key, value);
      if (text !== undefined) item.textContent = text;
      svg.append(item);
      return item;
    };
    svg.replaceChildren();
    const points = data.items;
    const peak = data.peak;
    const final = points[points.length - 1];
    get("#chart-equity-summary").textContent = `${peak ? `Peak equity ${peak.equity} CU · ${peak.trade_number ? "after trade " + peak.trade_number : "initial balance"} · ` : ""}Final equity ${final.equity} CU. Values belong to this saved run.`;
    const values = points.map((point) => Number(point.equity));
    const min = Math.min(...values), max = Math.max(...values);
    // Geometry alone uses Number. Labels, tooltips, exports and metrics retain
    // server Decimal strings. Avoid drawing misleading non-finite geometry.
    if (!values.every(Number.isFinite) || !Number.isFinite(max - min)) {
      get("#chart-readout").textContent = "Equity exceeds the chart's numeric range. Exact values are available in the CSV and saved report.";
      return;
    }
    const scale = equityScale(min, max);
    if (!scale) {
      get("#chart-readout").textContent = "Equity exceeds the chart's numeric range. Exact values are available in the CSV and saved report.";
      return;
    }
    const left = Math.max(65, ...scale.labels.map((text) => text.length * 7 + 20));
    const spread = scale.upper - scale.lower;
    svg.dataset.yMin = scale.lower;
    svg.dataset.yMax = scale.upper;
    svg.dataset.yStep = scale.step;
    const x = (point) => left + point.trade_number / Math.max(1, data.total - 1) * (right - left);
    const y = (value) => 235 - (value - scale.lower) / spread * 205;
    for (const [tick, value] of scale.ticks.entries()) {
      const position = y(value);
      draw("line", { x1: left, x2: right, y1: position, y2: position, class: "chart-grid" });
      draw("text", { x: left - 10, y: position + 4, "text-anchor": "end", class: "chart-label chart-y-label" }, scale.labels[tick]);
    }
    draw("polyline", { points: points.map((point, i) => `${x(point)},${y(values[i])}`).join(" "), class: "chart-line" });
    draw("text", { x: left, y: 270, class: "chart-label" }, "Initial");
    draw("text", { x: right, y: 290, "text-anchor": "end", class: "chart-label" }, `${number.format(data.total - 1)} completed trades →`);
    const cursor = draw("circle", { cx: x(points[0]), cy: y(values[0]), r: 5, class: "chart-cursor" });
    let selected = 0;
    function inspect(index) {
      selected = Math.max(0, Math.min(index, points.length - 1));
      const point = points[selected];
      cursor.setAttribute("cx", x(point));
      cursor.setAttribute("cy", y(values[selected]));
      get("#chart-readout").textContent = `${point.trade_number ? tradeStamp(point.exit_time_utc) + " " + tradeTimeZone + " · Trade " + point.trade_number : "Initial balance"} · Equity ${point.equity} CU${point.trade_number ? " · Trade net P&L " + point.net_pnl + " CU" : ""}`;
    }
    svg.onpointermove = (event) => {
      const rect = svg.getBoundingClientRect();
      const target = (event.clientX - rect.left) / rect.width * width;
      let nearest = 0;
      for (let i = 1; i < points.length; i++) if (Math.abs(x(points[i]) - target) < Math.abs(x(points[nearest]) - target)) nearest = i;
      inspect(nearest);
    };
    svg.onkeydown = (event) => {
      if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
        event.preventDefault();
        inspect(event.key === "Home" ? 0 : event.key === "End" ? points.length - 1 : selected + (event.key === "ArrowRight" ? 1 : -1));
      }
    };
    inspect(points.length - 1);
    get("#chart-note").textContent = `${number.format(points.length)} of ${number.format(data.total)} trade-close equity points shown (including initial balance). ${data.sampled ? "Min/max per trade-count bucket, plus endpoints; connecting lines omit intermediate trades." : "Full series shown."} Horizontal spacing follows completed trade count. Hover or use arrow keys for exact values. Metrics use the complete run.`;
    svg.dataset.points = points.length;
    svg.dataset.total = data.total;
  }
  async function trades(offset, controller) {
    get("#trades-previous").disabled = get("#trades-next").disabled = true;
    get("#report-trades-count").textContent = "Loading trades…";
    try {
      const page = await read(`/api/backtests/${runId}/trades?offset=${offset}&limit=${pageSize}`, controller.signal);
      if (controller !== active) return;
      tradeOffset = offset;
      const body = get("#report-trades-body");
      body.replaceChildren();
      for (const trade of page.items) {
        const row = node("tr");
        row.dataset.trade = trade.trade_number;
        for (const key of ["trade_number", "entry_time_utc", "exit_time_utc", "entry_fill_price", "exit_fill_price", "contracts", "gross_pnl", "total_commissions", "net_pnl", "actual_holding_minutes", "exit_reason"]) {
          const cell = node("td", key.endsWith("time_utc") ? tradeStamp(trade[key]) : String(trade[key]));
          cell.dataset.field = key;
          if (key.endsWith("time_utc")) cell.title = `Stored UTC: ${trade[key]}`;
          if (key === "net_pnl") cell.className = moneyClass(trade[key]);
          row.append(cell);
        }
        body.append(row);
      }
      if (!page.total) {
        const cell = node("td", "No trades were taken. Equity remains at initial capital.");
        cell.colSpan = 11;
        const row = node("tr"); row.append(cell); body.append(row);
      }
      get("#report-trades-count").textContent = page.total ? `${number.format(offset + 1)}–${number.format(offset + page.items.length)} of ${number.format(page.total)} trades` : "0 trades";
      get("#trades-previous").disabled = offset === 0;
      get("#trades-next").disabled = offset + page.items.length >= page.total;
    } catch (exc) {
      if (controller.signal.aborted) return;
      get("#report-trades-body").replaceChildren();
      get("#report-trades-count").textContent = "Trades unavailable. Reopen the report to retry.";
      throw exc;
    }
  }
  async function openReport(id) {
    const controller = new AbortController();
    active = controller;
    runId = id;
    get("#backtest-completion").hidden = true;
    error("Loading saved report…");
    try {
      const record = await read(`/api/backtests/${id}`, controller.signal);
      if (active !== controller) return;
      tradeTimezone(record);
      metrics(record);
      window.dispatchEvent(new CustomEvent("report-loaded", { detail: record }));
      get("#report-prop-setup").href = `#backtests/prop/new/${record.id}`;
      get("#report-run-id").textContent = `Run ${record.id} · ${stamp(record.created_at_utc)} UTC`;
      for (const kind of ["trades", "equity"]) get(`#report-${kind}-download`).href = `/api/backtests/${id}/exports/${kind}`;
      const [preview] = await Promise.all([
        read(`/api/backtests/${id}/chart?max_points=1000`, controller.signal), trades(0, controller),
      ]);
      if (active !== controller) return;
      get("#backtest-completion").hidden = false;
      chart(preview);
      get("#report-status").hidden = true;
      get("#backtest-completion").scrollIntoView({ block: "start" });
    } catch (exc) {
      if (!controller.signal.aborted) error(`${exc.message} Use Backtests or Refresh reports to choose a saved report.`);
    }
  }
  async function history(offset = 0) {
    const version = ++historyVersion;
    get("#refresh-reports").disabled = true;
    get("#runs-previous").disabled = get("#runs-next").disabled = true;
    get("#completed-runs-status").textContent = "Loading completed reports…";
    try {
      const page = await read(`/api/backtests?offset=${offset}&limit=25`);
      if (version !== historyVersion) return;
      historyOffset = offset;
      const list = get("#completed-runs-list");
      list.replaceChildren();
      for (const record of page.items) {
        const link = node("a", undefined, "completed-run");
        link.href = `#backtests/report/${record.id}`;
        link.append(node("strong", record.run_metadata.dataset.name), node("span", `${record.run_metadata.strategy.id} · ${stamp(record.created_at_utc)} UTC`, "small muted"), node("span", `${record.summary.total_net_pnl} CU · ${record.summary.trades_taken} trades`, moneyClass(record.summary.total_net_pnl)), node("code", record.id, "run-identifier small"));
        list.append(link);
      }
      get("#completed-runs-status").textContent = page.total ? "Saved reports remain available after refresh and dataset deletion." : "No completed reports yet.";
      get("#completed-runs-count").textContent = page.total ? `${offset + 1}–${offset + page.items.length} of ${number.format(page.total)} reports` : "0 reports";
      get("#runs-previous").disabled = offset === 0;
      get("#runs-next").disabled = offset + page.items.length >= page.total;
    } catch (exc) {
      if (version === historyVersion) get("#completed-runs-status").textContent = `Could not load reports: ${exc.message}`;
    } finally {
      if (version === historyVersion) get("#refresh-reports").disabled = false;
    }
  }
  function navigate() {
    active?.abort();
    chartData = null;
    const match = location.hash.match(/^#backtests\/report\/([0-9a-f]{32})$/);
    const report = Boolean(match);
    get("#backtest-setup").hidden = report;
    get("#completed-runs").hidden = report;
    get("#backtest-completion").hidden = true;
    get("#report-status").hidden = true;
    if (report) openReport(match[1]);
    else if (location.hash === "#backtests") history();
  }
  get("#trades-previous").onclick = () => trades(Math.max(0, tradeOffset - pageSize), active).catch((exc) => error(exc.message));
  get("#trades-next").onclick = () => trades(tradeOffset + pageSize, active).catch((exc) => error(exc.message));
  get("#refresh-reports").onclick = () => history(0);
  get("#runs-previous").onclick = () => history(Math.max(0, historyOffset - 25));
  get("#runs-next").onclick = () => history(historyOffset + 25);
  window.addEventListener("hashchange", navigate);
  window.addEventListener("resize", () => { if (chartData) chart(chartData); });
  navigate();
})();
