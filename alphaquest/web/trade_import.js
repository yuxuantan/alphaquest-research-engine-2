"use strict";

/* Imported trades enter the ordinary saved-backtest catalogue and report. */
(() => {
  const panel = document.querySelector('#external-trade-import');
  if (!panel) return;
  const node = (tag, text, className) => {
    const item = document.createElement(tag);
    if (text !== undefined) item.textContent = text;
    if (className) item.className = className;
    return item;
  };
  const words = value => String(value).replaceAll('_', ' ');
  const display = value => value === null || value === undefined || value === '' ? 'Not supplied' : String(value);
  const disclosure = node('details');
  disclosure.append(node('summary', 'Import external trades'));
  panel.append(disclosure);
  const content = node('div', undefined, 'backtest-fields');
  disclosure.append(content);
  content.append(node('p', 'Import a canonical external-trade JSON export. Review its identity, costs and risk coverage, then save an ordinary report for prop source checking.'));
  const fileLabel = node('label', 'Canonical trade export · JSON');
  const file = node('input'); file.type = 'file'; file.id = 'trade-import-file'; file.accept = '.json,application/json';
  fileLabel.append(file); content.append(fileLabel);
  const selected = node('p', 'Choose an exported file.', 'small muted'); selected.id = 'trade-import-file-note'; content.append(selected);
  const actions = node('div', undefined, 'report-downloads');
  const check = node('button', 'Check import', 'button secondary'); check.type = 'button'; check.id = 'trade-import-check';
  const save = node('button', 'Save imported report', 'button primary'); save.type = 'button'; save.id = 'trade-import-save';
  actions.append(check, save); content.append(actions);
  const status = node('p', '', 'small'); status.id = 'trade-import-status'; status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
  const preview = node('div'); preview.id = 'trade-import-preview'; content.append(status, preview);
  let revision = 0, busy = false, checkedBytes = null, checkedName = null, controller = null;

  function controls() {
    file.disabled = busy;
    check.disabled = busy || !file.files?.length;
    save.disabled = busy || !checkedBytes;
  }
  function invalidate() {
    revision++; controller?.abort(); checkedBytes = null; checkedName = null;
    preview.replaceChildren(); status.textContent = ''; controls();
  }
  file.addEventListener('change', () => {
    invalidate(); const chosen = file.files?.[0];
    selected.textContent = chosen ? `${chosen.name} · ${chosen.size.toLocaleString()} bytes` : 'Choose an exported file.';
  });
  function facts(parent, title, rows) {
    const section = node('section'); section.append(node('h3', title));
    const list = node('dl', undefined, 'backtest-run-details');
    for (const [key, value] of rows) {
      const pair = node('div'); pair.append(node('dt', key), node('dd', display(value))); list.append(pair);
    }
    section.append(list); parent.append(section);
  }
  function render(data, target) {
    const output = target || preview;
    output.replaceChildren();
    const source = data.source || {}, summary = data.summary || {}, manifest = data.manifest || {}, validation = data.validation || {};
    const instrument = manifest.instrument || {}, time = manifest.time || {}, coverage = manifest.coverage || {}, research = manifest.research || {}, risk = manifest.risk || {};
    const totals = validation.totals || {}, currency = instrument.currency || 'unspecified currency';
    facts(output, 'Trade source', [
      ['Origin', words(manifest.origin || source.kind)], ['Strategy', manifest.strategy?.id],
      ['Instrument', instrument.symbol], ['Currency', currency],
      [`Initial capital · ${currency}`, manifest.initial_capital], [`Final trade-close equity · ${currency}`, summary.final_equity],
      ['Completed trades', validation.trade_count ?? summary.trades_taken], ['Recorded risk events', validation.event_count],
      [`Net P&L · ${currency}`, totals.net_pnl ?? summary.total_net_pnl],
      [`Commission included · ${currency}`, totals.total_commissions ?? summary.total_commissions],
      [`Slippage included · ${currency}`, totals.slippage_cost ?? summary.total_slippage_cost],
      ['Declared observation start · UTC', coverage.start_utc], ['Declared observation end · UTC', coverage.end_utc],
      ['Declared sessions', coverage.sessions?.length], ['Source timezone', time.source_timezone],
      ['Research phase · exporter declaration', words(research.phase || 'unspecified')], ['Prior access · exporter declaration', words(research.prior_access || 'unknown')],
      ['Risk basis · exporter declaration', words(risk.basis || 'unknown')], ['Risk coverage · exporter declaration', words(risk.coverage || 'unknown')],
    ]);
    output.append(node('p', validation.exact_arithmetic ? 'Trade counts, completion hash and cost arithmetic reconcile. Exporter coverage declarations are preserved; import does not independently verify complete market observations or untouched history.' : 'Inspect the saved validation and exporter declarations before using this source.'));
    if (validation.costs) output.append(node('p', validation.costs));
    const provenance = node('details'); provenance.append(node('summary', 'Inspect exporter identity and source assumptions')); output.append(provenance);
    facts(provenance, 'Immutable source identity', [
      ['Export ID', source.export_id], ['Schema', source.schema_version], ['File SHA-256', source.raw_sha256], ['File bytes', source.raw_bytes], ['Payload SHA-256', source.payload_sha256],
      ['Exporter build', manifest.exporter_build], ['Platform edition', manifest.platform?.edition], ['Platform build', manifest.platform?.build], ['Platform bitness', manifest.platform?.bitness],
      ['Strategy implementation SHA-256', manifest.strategy?.implementation_sha256], ['Declared dataset', manifest.dataset?.name], ['Declared dataset SHA-256', manifest.dataset?.sha256],
      ['Contract identity', manifest.dataset?.contract], ['Price adjustment', manifest.dataset?.adjustment], ['Tick size', instrument.tick_size], ['Monetary point value', instrument.point_value],
      ['Timestamp basis', words(time.timestamp_basis || 'unknown')], ['Source bar interval · seconds', time.bar_interval_seconds], ['Session convention', time.session_convention],
      ['Calendar ID · exporter declaration', coverage.calendar_id], ['Calendar SHA-256 · exporter declaration', coverage.calendar_sha256],
      ['Coverage completion · exporter declaration', words(coverage.completion || 'unknown')], ['Research declaration', research.declaration],
      ['Risk units', words(risk.units || 'unknown')], ['Risk equity basis', words(risk.equity_basis || 'unknown')], ['Risk observation claim', words(risk.observation_claim || 'unknown')],
      ['Execution assumption', manifest.execution?.fill_assumption], ['Sizing path invariance · exporter declaration', words(manifest.execution?.sizing_path_invariance || 'unverified')],
    ]);
    if (Object.keys(manifest.strategy?.parameters || {}).length) facts(provenance, 'Saved strategy parameters', Object.entries(manifest.strategy.parameters).map(([key, value]) => [key, typeof value === 'object' && value !== null ? JSON.stringify(value) : value]));
    if (manifest.execution?.assumptions?.length) { const assumptions = node('ul'); for (const item of manifest.execution.assumptions) assumptions.append(node('li', item)); provenance.append(assumptions); }
    const capabilities = node('section'); capabilities.append(node('h3', 'Available operations'));
    const list = node('ul');
    const names = {prop_analysis: 'Prop source analysis', native_replay: 'Native strategy replay', bar_equity: 'Per-bar equity', market_benchmark: 'Market benchmark', controlled_oos: 'Native OOS execution', nested_research: 'Nested strategy reruns'};
    for (const [key, title] of Object.entries(names)) list.append(node('li', `${title}: ${data.capabilities?.[key] === true ? 'available' : 'unavailable'}`));
    capabilities.append(list); output.append(capabilities);
    if (data.capabilities?.prop_analysis_reason) capabilities.append(node('p', data.capabilities.prop_analysis_reason));
    if (data.limitations?.length) {
      const section = node('section'); section.append(node('h3', 'Source limitations')); const items = node('ul');
      for (const item of data.limitations) items.append(node('li', item)); section.append(items); output.append(section);
    }
  }
  async function request(path, bytes, filename, signal) {
    const response = await fetch(`${path}?${new URLSearchParams({filename})}`, {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: bytes, signal,
    });
    let data;
    try { data = await response.json(); } catch { throw Error(`Import request failed (HTTP ${response.status}).`); }
    if (!response.ok) {
      const detail = data.detail;
      throw Error(typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map(item => item.msg || display(item)).join('; ') : `Import request failed (HTTP ${response.status}).`);
    }
    return {data, status: response.status};
  }
  check.onclick = async () => {
    const chosen = file.files?.[0]; if (busy || !chosen) return;
    invalidate(); const token = revision; busy = true; controls();
    controller = new AbortController(); status.textContent = 'Checking source identity, trade costs and risk coverage…';
    try {
      if (!chosen.size || chosen.size > 32 * 1024 * 1024) throw Error('Choose a nonempty canonical JSON export no larger than 32 MiB.');
      const bytes = await chosen.arrayBuffer();
      if (token !== revision) return;
      const {data} = await request('/api/backtests/imports/check', bytes, chosen.name, controller.signal);
      if (token !== revision) return;
      if (data.status !== 'compatible') throw Error('This import did not pass source validation.');
      checkedBytes = bytes; checkedName = chosen.name; render(data);
      status.textContent = 'Source checks passed. Review the source and limitations, then save the imported report.';
    } catch (error) {
      if (token === revision && error.name !== 'AbortError') status.textContent = `Import needs attention: ${error.message}`;
    } finally { if (token === revision) { busy = false; controls(); } }
  };
  save.onclick = async () => {
    if (busy || !checkedBytes) return;
    const token = revision, bytes = checkedBytes, filename = checkedName; busy = true; controls();
    controller = new AbortController(); status.textContent = 'Saving the reviewed trade source and report…';
    try {
      const {data, status: code} = await request('/api/backtests/imports', bytes, filename, controller.signal);
      if (token !== revision) return;
      if (!/^[0-9a-f]{32}$/.test(data.id || '')) throw Error('The server did not return a saved report ID.');
      status.textContent = code === 200 ? 'This exact source is already saved. Opening its report…' : 'Imported report saved. Opening the report…';
      location.hash = `#backtests/report/${data.id}`;
    } catch (error) {
      if (token === revision && error.name !== 'AbortError') status.textContent = `Could not save the import: ${error.message} Retry saves the same reviewed file.`;
    } finally { if (token === revision) { busy = false; controls(); } }
  };
  function navigate() {
    if (location.hash === '#backtests/new?import=external') { disclosure.open = true; requestAnimationFrame(() => { if (location.hash === '#backtests/new?import=external') panel.scrollIntoView({block: 'start'}); }); }
  }
  window.addEventListener('hashchange', navigate); navigate();
  window.externalTradeImport = {renderPreview: render};
  controls();
})();
