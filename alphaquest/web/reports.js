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
  const deleting = new Set();
  let tradeTimeZone = "UTC";
  let tradeTimeFormatter;
  const node = (tag, text, cls) => {
    const item = document.createElement(tag);
    if (text !== undefined) item.textContent = text;
    if (cls) item.className = cls;
    return item;
  };
  const stamp = (value) => value ? value.replace("T", " ").replace("Z", "") : "Initial balance";
  function deleteButton(record) {
    const button = node("button", "Delete", "button danger");
    button.type = "button";
    button.dataset.deleteRun = record.id;
    button.setAttribute("aria-label", `Delete backtest ${record.id}`);
    button.disabled = deleting.has(record.id);
    button.onclick = () => deleteBacktest(record);
    return button;
  }
  async function deleteBacktest(record) {
    if (deleting.has(record.id)) return;
    if (!window.confirm(`Delete backtest “${record.run_metadata.dataset.name}”?\n\nRun ${record.id}\n\nThis permanently removes this backtest and its report files. The source dataset, saved prop analyses and optimization metrics are kept. This cannot be undone.`)) return;
    deleting.add(record.id);
    document.querySelectorAll('[data-delete-run]').forEach(button => { if (button.dataset.deleteRun === record.id) button.disabled = true; });
    const status = get("#backtest-delete-status"); status.hidden = false; status.textContent = "Deleting backtest…";
    try {
      const response = await fetch(`/api/backtests/${record.id}`, {method: "DELETE"});
      if (!response.ok && response.status !== 404) {
        const result = await response.json();
        throw new Error(typeof result.detail === "string" ? result.detail : `HTTP ${response.status}`);
      }
      status.textContent = "Backtest deleted. Source dataset, saved prop analyses and optimization metrics kept.";
      if (location.hash === `#backtests/report/${record.id}`) location.hash = "#strategies";
      else if (location.hash === "#backtests") await history(historyOffset);
    } catch (exc) {
      status.textContent = `Could not delete backtest: ${exc.message}`;
    } finally {
      deleting.delete(record.id);
      document.querySelectorAll('[data-delete-run]').forEach(button => { if (button.dataset.deleteRun === record.id) button.disabled = false; });
    }
  }
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
    if (record.run_metadata.automatic_prop_analysis) {
      const automatic = record.run_metadata.automatic_prop_analysis;
      const card = node("div", undefined, "panel report-metric");
      card.append(node("span", "Historical net · USD", "stat-label"));
      const amount = node("strong", "Loading…"); amount.id = "report-historical-net";
      const note = node("p", "", "small muted"); note.id = "report-prop-result-note";
      const link = node("a", "Open default prop analysis →"); link.href = `#backtests/prop/job/${automatic.id}`;
      card.append(amount, note, node("p", `Apex 50K EOD · ${automatic.settings.SLOTS} slots · $${automatic.settings.EVAL_PRICE} evaluation + $${automatic.settings.ACTIVATION_FEE} activation · full history`, "small muted"), link);
      holder.append(card);
      for(const item of automatic.companions||[]){
        const extra=node('div',undefined,'panel report-metric');
        const value=node('strong','Loading…');value.id='report-lucid-historical-net';
        const note=node('p','', 'small muted');note.id='report-lucid-result-note';
        const open=node('a','Open LucidFlex analysis →');open.href=`#backtests/prop/job/${item.id}`;
        extra.append(node('span','LucidFlex historical net · USD','stat-label'),value,
          node('p',`${item.label} · ${item.settings.SLOTS} slots · $${item.settings.EVAL_PRICE} evaluation · no activation fee`,'small muted'),note,open);
        holder.append(extra);
      }
    }
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
  const usd = (value, digits = 0) => value == null ? "N/A" : new Intl.NumberFormat("en-US", {style: "currency", currency: "USD", minimumFractionDigits: digits, maximumFractionDigits: digits}).format(value);
  const probability = (value) => value == null ? "N/A" : `${number.format(Number((value * 100).toFixed(1)))}%`;
  function propMetric(parent, key, label, value, note, exact) {
    const card = node("div", undefined, "prop-metric");
    const amount = node("strong", value, key === "historical-net" ? moneyClass(exact) : "");
    amount.id = `report-prop-${key}`;
    if (exact != null) amount.title = `Saved value: ${exact}`;
    card.append(node("span", label, "prop-metric-label"), amount, node("p", note));
    parent.append(card);
  }
  async function propSummary(record, controller) {
    void companionSummaries(record,controller);
    const automatic = record.run_metadata.automatic_prop_analysis;
    try {
      let id = automatic?.id;
      if (!id) {
        const source = record.run_metadata.detailed_from_run_id || record.id;
        const saved = await read(`/api/prop-analyses/sources/${source}?discover_exports=false`, controller.signal);
        if (active !== controller) return;
        id = (saved.analyses.find((item) => item.status === "complete") || saved.analyses[0])?.id;
      }
      if (active !== controller) return;
      if (!id) {
        get("#report-prop-status").textContent = "No saved prop analysis yet. Use Configure prop analysis to check the source and run one.";
        return;
      }
      const result = await read(`/api/prop-analyses/${id}`, controller.signal);
      if (active !== controller) return;
      const context = get("#report-prop-context");
      context.textContent = `${automatic ? "Default automatic analysis" : result.status === "complete" ? "Latest completed saved analysis" : "Latest saved analysis"} · ${id}`;
      const actions = get("#report-prop-actions"); actions.replaceChildren();
      const link = node("a", "Open full analysis →", "button secondary"); link.href = `#backtests/prop/job/${id}`; actions.append(link);
      const amount = get("#report-historical-net");
      if (amount) {
        amount.textContent = usd(result.historical_net);
        amount.className = result.historical_net == null ? "" : moneyClass(result.historical_net);
        get("#report-prop-result-note").textContent = result.reason || "Payouts minus acquisition costs, including activation fees. Native close-only excursion fallback.";
      }
      const status = get("#report-prop-status");
      if (result.status !== "complete") {
        status.textContent = `${result.status} · ${result.reason || result.progress}`;
        if (["queued", "running"].includes(result.status)) setTimeout(() => { if (active === controller) propSummary(record, controller); }, 1500);
        return;
      }
      const report = await read(`/api/prop-analyses/${id}/downloads/report.json`, controller.signal);
      if (active !== controller) return;
      if (report.format_version !== 3 || !report.calculations) {
        status.textContent = "Historical engine report. Open the full analysis to inspect its original results and model.";
        return;
      }
      const c = report.calculations, e = c.evaluation, funded = c.funded?.selected, totals = c.history?.totals;
      const settings = report.settings;
      context.textContent += ` · Apex 50K EOD · ${settings.SLOTS} slots · full history ${c.samples.data.join(" – ")} · $${settings.EVAL_PRICE} evaluation + $${settings.ACTIVATION_FEE} activation`;
      const holder = get("#report-prop-metrics"); holder.replaceChildren();
      const cash = node("div", undefined, "prop-metric-grid prop-three-metrics"); holder.append(cash);
      propMetric(cash, "historical-net", "Historical net · USD", usd(totals?.net), "Payouts minus acquisition costs across all slots over the observed history.", totals?.net);
      propMetric(cash, "payouts", "Historical payouts · USD", usd(totals?.payouts), "Total payouts across the historical slots.", totals?.payouts);
      propMetric(cash, "costs", "Acquisition costs · USD", usd(totals?.costs), "Evaluation and activation fees for historical funded starts.", totals?.costs);
      const evaluation = node("p", `Evaluation pass rate: ${probability(e.pass_rate)} · Evaluation size: ${e.selected_micros} MNQ · Average acquisition cost: ${usd(e.cost_per_funded, 2)}${funded ? ` · Funded size: ${funded.micros} MNQ` : ""}`, "small");
      evaluation.id = "report-prop-evaluation"; holder.append(evaluation);
      if (funded) {
        holder.append(node("h3", "One funded account · holdout simulation"));
        const accounts = node("div", undefined, "prop-metric-grid"); holder.append(accounts);
        propMetric(accounts, "average-payout", "Average lifetime payout", usd(funded["E[payout]"], 2), "Includes accounts paid $0; before evaluation and activation fees.", funded["E[payout]"]);
        propMetric(accounts, "median-payout", "Median lifetime payout", usd(funded["median life"], 2), "The middle simulated funded account.", funded["median life"]);
        propMetric(accounts, "payout-chance", "Receives a payout", probability(funded["P(>=1 payout)"]), "At least one payout during the account lifetime.", funded["P(>=1 payout)"]);
        propMetric(accounts, "drawdown-failure", "Fails the drawdown limit", probability(funded.blown), "An account can receive payouts before failing.", funded.blown);
      }
      status.textContent = c.unavailable || "Historical cash follows the observed sequence, including training days. Slots share one trade path. Simulated account payouts are separate from historical net.";
      holder.append(node("p", report.source.excursion_provenance, "small muted"));
      const download = node("a", "Report data (JSON) ↓", "button secondary"); download.href = `/api/prop-analyses/${id}/downloads/report.json`; actions.append(download);
    } catch (exc) {
      if (active !== controller || controller.signal.aborted) return;
      if (get("#report-historical-net")) get("#report-historical-net").textContent = "N/A";
      get("#report-prop-status").textContent = `Could not load saved prop analysis: ${exc.message}`;
    }
  }
  async function companionSummaries(record,controller){
    const holder=get('#report-prop-companions');holder.replaceChildren();
    const companions=record.run_metadata.automatic_prop_analysis?.companions||[];holder.hidden=!companions.length;
    for(const item of companions){
      try{
        const result=await read(`/api/prop-analyses/${item.id}`,controller.signal);if(active!==controller)return;
        const value=get('#report-lucid-historical-net');if(value)value.textContent=usd(result.historical_net);
        const note=get('#report-lucid-result-note');if(note)note.textContent=result.reason||'Trader payouts after 90/10 split, minus evaluation costs; full observed history.';
        const block=node('section',undefined,'report-panel');block.append(node('h3',item.label||'LucidFlex 50K'));
        const open=node('a','Open LucidFlex full analysis →','button secondary');open.href=`#backtests/prop/job/${item.id}`;
        block.append(open,node('p',`${result.status} · $${item.settings.EVAL_PRICE} evaluation · ${item.settings.SLOTS} slots · no activation fee`,'small muted'));
        if(result.status==='complete'){
          const report=await read(`/api/prop-analyses/${item.id}/downloads/report.json`,controller.signal);if(active!==controller)return;
          const c=report.calculations,f=c.funded?.selected;
          block.append(node('p',`Historical net ${usd(result.historical_net)} · Evaluation pass ${probability(c.evaluation.pass_rate)} · Selected evaluation ${c.evaluation.selected_micros} MNQ${f?` · Funded ${f.micros} MNQ · Mean trader payout ${usd(f['E[payout]'])}`:''}`));
          block.append(node('p',c.unavailable||'Sim-funded payouts stop at five; live trading and discretionary early live transitions are outside this model.','small muted'));
          const download=node('a','LucidFlex report data (JSON) ↓','button secondary');download.href=`/api/prop-analyses/${item.id}/downloads/report.json`;block.append(download);
        }else block.append(node('p',result.reason||result.progress));
        holder.append(block);
      }catch(error){if(active!==controller||controller.signal.aborted)return;holder.append(node('p','Could not load saved LucidFlex analysis: '+error.message));const amount=get('#report-lucid-historical-net');if(amount)amount.textContent='N/A';}
    }
  }
  async function performance(record, controller) {
    get('#report-performance-body').replaceChildren();
    get('#report-performance-status').textContent='Loading timing diagnostics…';
    get('#report-performance-download').hidden=true;
    try {
      const data=await read(`/api/backtests/${record.id}/performance`,controller.signal);
      if(active!==controller)return;
      get('#report-performance-status').textContent=data.unavailable || `Total elapsed: ${data.elapsed_seconds.toFixed(3)} seconds. Phase times exclude time attributed to nested phases.`;
      if(data.details?.prop_backend)get('#report-performance-status').textContent+=` Prop engine: ${data.details.prop_backend}.`;
      if(data.details?.prop_calculation_reused_from)get('#report-performance-status').textContent+=' Verified prop calculations reused.';
      if(data.details?.source_cache_hit)get('#report-performance-status').textContent+=' Parsed source reused.';
      if(data.details?.prepared_feature_series)get('#report-performance-status').textContent+=` Prepared indicator series: ${data.details.prepared_feature_series}.`;
      if(data.details?.prop_execution?.workers_used)get('#report-performance-status').textContent+=` Prop workers: ${data.details.prop_execution.workers_used}.`;
      for(const [key,value] of Object.entries(data.phases_seconds || {})) {
        const row=node('tr');row.append(node('td',key.replaceAll('_',' ')),node('td',value.toFixed(3)));get('#report-performance-body').append(row);
      }
      const link=get('#report-performance-download');link.hidden=Boolean(data.unavailable);link.href=`/api/backtests/${record.id}/exports/performance`;
    } catch(exc) {if(active===controller&&!controller.signal.aborted)get('#report-performance-status').textContent=`Timing diagnostics unavailable: ${exc.message}`;}
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
    get("#report-prop-context").textContent = "";
    get("#report-prop-actions").replaceChildren();
    get("#report-prop-metrics").replaceChildren();
    get("#report-prop-status").textContent = "Loading saved prop analysis…";
    error("Loading saved report…");
    try {
      const record = await read(`/api/backtests/${id}`, controller.signal);
      if (active !== controller) return;
      let back="#strategies";
      try{const context=JSON.parse(sessionStorage.getItem('strategy-report-return'));if(context?.id===record.id&&/^#strategies\/[^/]+\/datasets\/[0-9a-f]{64}$/.test(context.route))back=context.route;}catch{}
      get("#report-back-strategies").href=back;
      tradeTimezone(record);
      metrics(record);
      const remove = get("#report-delete");
      remove.dataset.deleteRun = record.id;
      remove.disabled = deleting.has(record.id);
      remove.onclick = () => deleteBacktest(record);
      propSummary(record, controller);
      performance(record, controller);
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
      if (offset && offset >= page.total) return history(page.total ? Math.floor((page.total - 1) / 25) * 25 : 0);
      historyOffset = offset;
      const list = get("#completed-runs-list");
      list.replaceChildren();
      for (const record of page.items) {
        const link = node("a", undefined, "completed-run");
        link.href = `#backtests/report/${record.id}`;
        link.append(node("strong", record.run_metadata.dataset.name), node("span", `${record.run_metadata.strategy.id} · ${stamp(record.created_at_utc)} UTC`, "small muted"), node("span", `${record.summary.total_net_pnl} CU · ${record.summary.trades_taken} trades`, moneyClass(record.summary.total_net_pnl)), node("code", record.id, "run-identifier small"));
        const row = node("div", undefined, "completed-run-row"); row.dataset.runId = record.id;
        row.append(link, deleteButton(record)); list.append(row);
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
    get("#backtest-setup").hidden = report || location.hash.startsWith("#optimizations/") || location.hash.startsWith("#backtests/batches");
    get("#completed-runs").hidden = report || location.hash.startsWith("#optimizations") || location.hash !== "#backtests";
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
