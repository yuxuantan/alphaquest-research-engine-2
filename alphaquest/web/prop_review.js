(() => {
  const get = (selector) => document.querySelector(selector);
  const element = (tag, text, className) => {
    const item = document.createElement(tag);
    if (text !== undefined) item.textContent = text;
    if (className) item.className = className;
    return item;
  };
  const status = get("#prop-review-status");
  const result = get("#prop-review-result");
  let loaded = false;
  let busy = false;

  function table(headers, rows) {
    const wrapper = element("div", undefined, "report-table-scroll");
    const table = element("table", undefined, "prop-table");
    const head = element("thead");
    const tr = element("tr");
    headers.forEach(label => tr.append(element("th", label)));
    head.append(tr);
    const body = element("tbody");
    rows.forEach(row => {
      const tr = element("tr");
      row.forEach(value => {
        const cell = element("td");
        const text = typeof value === "string" ? value : JSON.stringify(value);
        if (text.length > 180) {
          const details = element("details");
          details.append(element("summary", "Inspect value"), element("pre", text));
          cell.append(details);
        } else cell.textContent = text;
        tr.append(cell);
      });
      body.append(tr);
    });
    table.append(head, body);
    wrapper.append(table);
    return wrapper;
  }

  function panel(number, title, deliverable) {
    const section = element("section", undefined, "panel prop-panel");
    section.id = `prop-subtask-${number}`;
    section.append(element("h2", `${number}. ${title}`), element("p", `Deliverable: ${deliverable}`));
    result.append(section);
    return section;
  }

  function details(parent, title, value) {
    const item = element("details");
    item.append(element("summary", title), element("pre", JSON.stringify(value, null, 2)));
    parent.append(item);
  }

  function render(review) {
    result.replaceChildren();
    result.hidden = false;
    get("#prop-platform").value = review.platform;
    get("#prop-quantity").value = String(review.quantity);
    const exportUrl = (name) => `/api/prop-review/${review.id}/exports/${name}`;
    const overview = element("div", undefined, "panel prop-panel");
    const passed = review.checks.filter(c => c.passed).length;
    overview.append(element("h2", `${passed}/${review.checks.length} checks passed`, review.all_passed ? "prop-pass" : "prop-fail"));
    overview.append(element("p", `Saved review ${review.id} · ${review.created_at_utc} · ${review.platform} · quantity ${review.quantity}`));
    overview.append(element("p", "Green checks compare executed output with fixture expectations. Synthetic inputs do not establish strategy performance or provider approval."));
    const downloads = element("div", undefined, "report-downloads");
    review.exports.forEach(name => {
      const link = element("a", name, "button secondary");
      link.href = exportUrl(name);
      link.download = "";
      downloads.append(link);
    });
    overview.append(downloads);
    result.append(overview);

    const spec = panel(1, "Specification", "the saved implementation specification, its SHA-256, and design checks.");
    spec.append(element("p", review.specification.design.join(" → "), "prop-design"));
    spec.append(element("p", `Specification SHA-256: ${review.specification.sha256}`, "prop-hash"));
    spec.append(element("p", `Notebook reviewed ${review.specification.notebook_reviewed_on}. ${review.specification.notebook_check}`));
    spec.append(element("p", `Pinned notebook SHA-256: ${review.specification.notebook_sha256}`, "prop-hash"));
    const specDetails = element("details");
    const specText = element("pre", "Loading specification…");
    specDetails.append(element("summary", "Read the saved specification"), specText);
    let specLoaded = false;
    specDetails.addEventListener("toggle", async () => {
      if (!specDetails.open || specLoaded) return;
      specLoaded = true;
      try {
        const response = await fetch(exportUrl("specification.md"));
        if (!response.ok) throw new Error("Unable to load specification.");
        specText.textContent = await response.text();
      } catch (error) { specText.textContent = error.message; specLoaded = false; }
    });
    spec.append(specDetails);

    const rules = panel(2, "Rules and configuration", "immutable resolved profiles, phase settings, tier probes, and strict validation results.");
    const profile = review.rules.snapshot.profile;
    rules.append(element("p", `${profile.id} · version ${profile.version} · ${profile.currency}`));
    rules.append(element("p", `Profile SHA-256: ${review.rules.snapshot.profile_sha256}`, "prop-hash"));
    rules.append(table(["Phase", "Target", "Trailing drawdown", "Lock profit", "Calendar deadline"], [
      ["Evaluation", review.rules.evaluation.profit_target, review.rules.evaluation.drawdown.amount,
        review.rules.evaluation.drawdown.lock_profit ?? "No lock", `${review.rules.evaluation.access_calendar_days} days`],
      ["Funded", "Payout eligibility", review.rules.funded.drawdown.amount, review.rules.funded.drawdown.lock_profit, "None"]
    ]));
    rules.append(element("h3", "Funded tier boundary probes"));
    rules.append(table(["Prior-session profit", "Maximum contracts", "Daily loss limit"], review.rules.tiers.map(t => [t.profit, t.max_contracts, t.daily_loss_limit])));
    review.rules.evidence.filter(e => e.status === "source_conflict").forEach(e => rules.append(element("p", `Recorded source conflict: ${e.note}`, "prop-notice")));
    rules.append(element("p", "Source retrieval dates below describe the saved rules review. Effective dates are unknown where null; this screen makes no fresh provider verification."));
    const sources = element("ul");
    review.rules.sources.forEach(source => {
      const li = element("li");
      const link = element("a", source.id);
      link.href = source.url;
      li.append(link, document.createTextNode(` · retrieved ${source.retrieved_on} · effective date ${source.effective_on ?? "unknown"}`));
      sources.append(li);
    });
    rules.append(sources);
    details(rules, "Full phase settings and platform differences", {evaluation: review.rules.evaluation, funded: review.rules.funded, platforms: review.rules.platforms});
    details(rules, "Verified evidence and modeling assumptions", {evidence: review.rules.evidence, assumptions: review.rules.assumptions});

    const adapter = panel(3, "Saved-backtest adapter", "source provenance, explicit calendar, sessions, both observation streams, and rejection examples.");
    const trade = review.adapter.trade;
    adapter.append(element("p", `Source quantity ${trade.source.contracts} → comparison quantity ${trade.contracts}. Net P&L ${trade.net_pnl} USD.`));
    adapter.append(table(["Gross P&L", "Commissions (already included)", "Informational slippage (already included)", "Net P&L"],
      [[trade.gross_pnl, trade.total_commissions, trade.slippage_cost, trade.net_pnl]]));
    adapter.append(element("p", "Explicit synthetic windows: January 5–7, 2026, 14:00–14:02 UTC each day. All nine bars are present; only January 6 trades. These are complete fixture windows, not full exchange sessions."));
    adapter.append(table(["Session date", "Coverage", "Bars", "Trades", "Net P&L"], review.adapter.sessions.map(s => [s.trading_date, s.status, s.bar_count, s.trade_count, s.net_pnl])));
    adapter.append(element("h3", "Actual observation streams"));
    adapter.append(element("p", "Trade-close samples come from equity.csv; bar-close samples come from report.json. P&L below is cumulative relative to each trade’s pre-entry equity. Flat observations show zero; do not sum bar marks."));
    adapter.append(table(["Mode", "Timestamp UTC", "Source quantity", "Position quantity", "Source equity", "Trade-relative P&L"],
      review.adapter.observations.map(o => [o.mode, o.timestamp_utc, o.source_contracts ?? "No trade", o.position_contracts, o.source_equity, o.equity_change])));
    adapter.append(element("h3", "Sunday timestamps and daylight saving"));
    adapter.append(element("p", "The March 8 Sunday 20:00 New York observation belongs to Monday March 9. Closed weekend dates remain explicit. The open moves from 23:00 to 22:00 UTC after DST."));
    adapter.append(table(["Session date", "Coverage", "Open UTC", "Bars"], review.adapter.dst_sessions.map(s => [s.trading_date, s.status, s.open_utc, s.bar_count])));
    details(adapter, "Preserved source identity, parameters, execution, and artifact hashes", review.adapter.source_snapshot);
    adapter.append(element("p", `Source snapshot SHA-256: ${review.adapter.source_sha256}`, "prop-hash"));
    adapter.append(element("p", `Resolved settings SHA-256: ${review.adapter.settings_sha256}`, "prop-hash"));

    [spec, rules, adapter].forEach((section, index) => {
      section.append(element("h3", "Validation: expected versus actual"));
      const checks = review.checks.filter(c => c.subtask === index + 1);
      section.append(table(["Check", "Expected", "Actual", "Result"], checks.map(c => [c.name, c.expected, c.actual, c.passed ? "PASS" : "FAIL"])));
    });
    const limits = element("div", undefined, "panel prop-panel");
    limits.append(element("h2", "Scope of this demonstration"));
    review.limitations.forEach(limit => limits.append(element("p", limit)));
    result.append(limits);
    status.textContent = `${review.all_passed ? "Review passed" : "Review has failed checks"}. Saved evidence remains available after reload.`;
  }

  async function requestReview(generate) {
    if (busy) return;
    busy = true;
    get("#prop-generate").disabled = true;
    get("#prop-platform").disabled = true;
    get("#prop-quantity").disabled = true;
    status.textContent = generate ? "Generating synthetic saved runs and checking actual outputs…" : "Loading saved review…";
    result.hidden = true;
    try {
      const response = await fetch(generate ? "/api/prop-review" : "/api/prop-review/latest", generate ? {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({platform: get("#prop-platform").value, quantity: Number(get("#prop-quantity").value)})
      } : {});
      if (!generate && response.status === 404) {
        status.textContent = "No review saved yet. Choose a platform and quantity, then generate a review.";
        return;
      }
      if (!response.ok) {
        let message = "Unable to complete the review. Try again.";
        try { const error = await response.json(); if (typeof error.detail === "string") message = error.detail; } catch (_) { /* HTTP error may be plain text. */ }
        throw new Error(message);
      }
      render(await response.json());
      loaded = true;
    } catch (error) { status.textContent = `Review unavailable: ${error.message}`; }
    finally {
      busy = false;
      get("#prop-generate").disabled = false;
      get("#prop-platform").disabled = false;
      get("#prop-quantity").disabled = false;
    }
  }
  get("#prop-review-form").addEventListener("submit", event => { event.preventDefault(); requestReview(true); });
  ["#prop-platform", "#prop-quantity"].forEach(selector => get(selector).addEventListener("change", () => {
    status.textContent = "Options changed. Generate a new review to apply them; any visible results belong to the saved review labeled below.";
  }));
  function navigate() {
    if (location.hash.startsWith("#prop-review") && !loaded) requestReview(false);
  }
  window.addEventListener("hashchange", navigate);
  navigate();
})();
