"use strict";

(() => {
  const get = selector => document.querySelector(selector);
  const node = (tag, text) => { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; return e; };
  let active, resultId, offset = 0;
  async function read(url, local) {
    const response = await fetch(url, {signal: local.signal, cache: "no-store"});
    const value = await response.json();
    if (!response.ok) throw new Error(typeof value.detail === "string" ? value.detail : `Result request failed (${response.status}).`);
    return value;
  }
  function table(headers, rows) {
    const wrapper = node("div"), table = node("table"), head = node("thead"), body = node("tbody"), tr = node("tr");
    wrapper.className = "report-table-scroll"; table.className = "prop-table";
    headers.forEach(v => tr.append(node("th", v))); head.append(tr);
    rows.forEach(row => { const tr = node("tr"); row.forEach(v => tr.append(node("td", v == null ? "—" : String(v)))); body.append(tr); });
    table.append(head, body); wrapper.append(table); return wrapper;
  }
  async function events(start, local) {
    get("#prop-events-prev").disabled = get("#prop-events-next").disabled = true;
    try {
      const data = await read(`/api/prop-simulations/results/${resultId}/events?offset=${start}&limit=50`, local);
      if (local !== active) return;
      offset = start;
      get("#prop-result-events").replaceChildren(table(["#", "UTC", "Event", "Trade", "Balance", "Equity", "Floor", "Trading delta", "External cost", "Detail"],
        data.items.map(e => [e.sequence, e.timestamp_utc, e.kind, e.trade_number, e.balance, e.equity, e.trailing_floor, e.realized_delta, e.external_cost, e.detail])));
      get("#prop-events-count").textContent = `${start + data.items.length} of ${data.total} events`;
      get("#prop-events-prev").disabled = start === 0; get("#prop-events-next").disabled = start + data.items.length >= data.total;
    } catch (error) { if (error.name !== "AbortError" && local === active) get("#prop-result-events").textContent = error.message; }
  }
  function chart(data) {
    const svg = get("#prop-account-chart"); svg.replaceChildren();
    const points = data.items;
    const input = get("#prop-trace-point"); input.max = points.length - 1; input.value = points.length - 1;
    const exact = () => {
      const point = points[Number(input.value)];
      get("#prop-chart-readout").textContent = `${point.timestamp_utc} · event ${point.sequence} · equity ${point.equity} · balance ${point.balance} · floor ${point.trailing_floor}`;
    };
    input.oninput = exact; exact();
    get("#prop-chart-note").textContent = `${points.length} of ${data.total} saved equity observations shown. ${data.sampled ? "Bucket equity extrema and last point, plus endpoints; intermediate events are omitted." : "Full observed trace."} Horizontal spacing follows account-event sequence. Exact values are available in the events table and CSV.`;
    const values = points.flatMap(p => [Number(p.equity), Number(p.trailing_floor)]);
    const lower = Math.min(...values), upper = Math.max(...values), range = upper - lower || 1;
    if (!values.every(Number.isFinite) || !Number.isFinite(range)) {
      get("#prop-chart-note").textContent = "Values exceed chart geometry limits. Inspect exact values in the event table and exports."; return;
    }
    const draw = (tag, attrs, text) => {
      const e = document.createElementNS("http://www.w3.org/2000/svg", tag);
      Object.entries(attrs).forEach(([key, value]) => e.setAttribute(key, value));
      if (text !== undefined) e.textContent = text;
      svg.append(e); return e;
    };
    const x = p => 90 + (p.sequence - points[0].sequence) / Math.max(1, points.at(-1).sequence - points[0].sequence) * 890;
    const y = value => 245 - (Number(value) - lower) / range * 210;
    draw("polyline", {points: points.map(p => `${x(p)},${y(p.equity)}`).join(" "), class: "prop-equity-line"});
    draw("polyline", {points: points.map(p => `${x(p)},${y(p.trailing_floor)}`).join(" "), class: "prop-floor-line"});
    draw("text", {x: 4, y: 30, class: "chart-label"}, "Equity / floor");
    draw("text", {x: 90, y: 280, class: "chart-label"}, points[0].timestamp_utc);
    draw("text", {x: 980, y: 280, "text-anchor": "end", class: "chart-label"}, points.at(-1).timestamp_utc);
    const cursor = draw("circle", {cx: x(points.at(-1)), cy: y(points.at(-1).equity), r: 4, fill: "#0b806f"});
    input.oninput = () => { exact(); const p = points[Number(input.value)]; cursor.setAttribute("cx", x(p)); cursor.setAttribute("cy", y(p.equity)); };
  }
  async function navigate() {
    active?.abort(); active = new AbortController(); const local = active;
    const match = location.hash.match(/^#backtests\/prop\/result\/([0-9a-f]{32})$/);
    get("#prop-result-view").hidden = true;
    if (!match) return;
    get("#prop-workflow").hidden = true;
    get("#prop-title-text").textContent = "Evaluation result";
    get("#prop-intro").textContent = "Historical account replay from a completed backtest.";
    get("#prop-status").textContent = "Loading saved simulation…";
    resultId = match[1];
    try {
      const result = await read(`/api/prop-simulations/results/${resultId}`, local);
      if (local !== active) return;
      const s = result.summary;
      get("#prop-back").href = `#backtests/prop/${result.setup_id}`;
      get("#prop-back").textContent = "← Back to saved setup";
      const summary = get("#prop-result-summary"); summary.replaceChildren();
      summary.append(node("p", `Result ${result.id} · ${result.created_at_utc} · ${result.currency} · ${result.observation_mode}`));
      const profile = result.resolved.rules.profile;
      summary.append(node("p", `Account profile: ${profile.id} · ${profile.id.endsWith("_no_activation") ? "No activation fee" : "Standard"}.`));
      const instrument = result.instrument;
      summary.append(node("p", `Instrument: ${instrument.symbol} · ${instrument.currency}${instrument.profile ? ` · profile ${instrument.profile.profile.id} version ${instrument.profile.profile.version}` : " · custom declaration"}.`));
      const sourceLink = node("a", `Source backtest ${result.source_backtest_id}`);
      sourceLink.href = `#backtests/report/${result.source_backtest_id}`;
      summary.append(sourceLink);
      summary.append(node("p", `Outcome: ${s.outcome} at ${s.outcome_at_utc}.`));
      summary.append(node("p", s.reason));
      summary.append(table(["Account balance", "Sampled equity", "Trailing floor", "EOD high-water", "Accepted trading P&L"],
        [[s.balance, s.equity, s.trailing_floor, s.high_water, s.realized_net_trading_pnl]]));
      summary.append(table(["Processed entries", "Source closes completed", "Skipped trades", "Not reached", "Forced exits", "Suspensions", "Covered sessions", "Zero-trade sessions"],
        [[s.processed_trades, s.completed_source_trades, s.skipped_trades, s.unprocessed_trades, s.forced_exits, s.suspensions, s.processed_sessions, s.zero_trade_sessions]]));
      summary.append(node("p", "Skipped trades were suppressed by a suspension or pending target. Not-reached trades lie after account termination or the configured historical end."));
      summary.append(table(["External fees", "Modeled receipts", "Modeled net cash", "Calendar expiry UTC", "Target UTC", "Review UTC", "Recognition UTC"],
        [[s.external_costs, s.modeled_receipts, s.modeled_net_cash, s.expiry_at_utc, s.target_reached_at_utc, s.reviewed_at_utc, s.recognized_at_utc]]));
      const links = get("#prop-result-downloads"); links.replaceChildren();
      ["report.json", "events.csv", "source.json", "simulation.json", "profile.json", "calendar.json", ...(result.artifacts["instrument.json"] ? ["instrument.json"] : []), ...(result.artifacts["coverage.json"] ? ["coverage.json"] : [])].forEach(filename => {
        const link = node("a", filename); link.className = "button secondary";
        link.href = `/api/prop-simulations/results/${result.id}/exports/${filename}`; link.download = ""; links.append(link);
      });
      const settings = get("#prop-result-settings"); settings.replaceChildren();
      if (result.coverage) settings.append(node("p", `Source-session profile: ${result.coverage.profile.name} · ${result.coverage.profile_sha256}`));
      result.limitations.forEach(text => settings.append(node("p", text)));
      settings.append(node("p", `Engine ${result.engine_version} · source snapshot ${result.source_sha256}`));
      const detail = node("details"); detail.append(node("summary", "Resolved settings, evidence and reconciliation"),
        node("pre", JSON.stringify({resolved: result.resolved, source_snapshot: result.source_snapshot, calendar: result.calendar, instrument: result.instrument, assumptions: result.assumptions, reconciliation: result.reconciliation}, null, 2)));
      settings.append(detail);
      get("#prop-result-view").hidden = false;
      const [data] = await Promise.all([read(`/api/prop-simulations/results/${resultId}/chart?max_points=500`, local), events(0, local)]);
      if (local !== active) return;
      chart(data);
      get("#prop-status").textContent = "Saved historical evaluation result. Financial outcome and operation status are separate.";
    } catch (error) { if (error.name !== "AbortError" && local === active) get("#prop-status").textContent = `Result unavailable: ${error.message}`; }
  }
  get("#prop-events-prev").onclick = () => events(Math.max(0, offset - 50), active);
  get("#prop-events-next").onclick = () => events(offset + 50, active);
  window.addEventListener("hashchange", navigate); navigate();
})();
