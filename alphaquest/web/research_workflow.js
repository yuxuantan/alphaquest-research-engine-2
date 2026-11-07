/* Nested research stays in the saved backtest -> prop configuration workflow. */
(() => {
  'use strict';
  const base = '/api/research-campaigns/robust';
  const panel = document.querySelector('#prop-robust-research');
  const node = (tag, text, className) => {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (className) element.className = className;
    return element;
  };
  const link = (text, href) => { const element = node('a', text); element.href = href; return element; };
  let generation = 0;
  async function api(path, body) {
    const response = await fetch(path, body === undefined ? {cache: 'no-store'} : {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
    });
    const result = await response.json();
    if (!response.ok) {
      const detail = result.detail;
      throw Error(typeof detail === 'string' ? detail : Array.isArray(detail)
        ? detail.map(item => `${item.loc?.slice(1).join(' → ') || 'Settings'}: ${item.msg}`).join('; ')
        : JSON.stringify(detail || result));
    }
    return result;
  }
  function button(parent, text, id) {
    const element = node('button', text, 'button secondary'); element.type = 'button';
    if (id) element.id = id;
    parent.append(element); return element;
  }
  function field(parent, label, id, value, type = 'number') {
    const wrapper = node('label', label), input = node('input');
    input.type = type; input.id = id; input.value = value; input.required = true;
    wrapper.append(input); parent.append(wrapper); return input;
  }
  function select(parent, label, id, options) {
    const wrapper = node('label', label), input = node('select'); input.id = id;
    for (const [value, text] of options) { const option = node('option', text); option.value = value; input.append(option); }
    wrapper.append(input); parent.append(wrapper); return input;
  }
  function list(parent, values) {
    if (!values?.length) return;
    const items = node('ul'); for (const value of values) items.append(node('li', value)); parent.append(items);
  }
  function table(parent, labels, rows, id) {
    const wrap = node('div', undefined, 'robust-table-scroll'); wrap.tabIndex = 0;
    wrap.setAttribute('role', 'region'); wrap.setAttribute('aria-label', labels.join(', '));
    const result = node('table', undefined, 'prop-table'), head = node('thead'), title = node('tr'), body = node('tbody');
    if (id) result.id = id;
    for (const label of labels) { const cell = node('th', label); cell.scope = 'col'; title.append(cell); }
    for (const row of rows) { const tr = node('tr'); row.forEach((value, index) => { const td = node('td'); td.dataset.label = labels[index]; td.append(value instanceof Node ? value : document.createTextNode(String(value ?? 'Unavailable'))); tr.append(td); }); body.append(tr); }
    head.append(title); result.append(head, body); wrap.append(result); parent.append(wrap); return result;
  }
  const words = value => value.replaceAll('_', ' ').replace(/^./, first => first.toUpperCase());
  const regimeLabel = name => ({trend: 'Trending prior prices', range: 'Ranging prior prices',
    high_volatility: 'High prior volatility', low_volatility: 'Low prior volatility',
    high_liquidity: 'High prior volume (liquidity proxy)', low_liquidity: 'Low prior volume (liquidity proxy)',
    asia_session: 'Asia clock window', europe_session: 'Europe clock window', us_session: 'US clock window'}[name] || words(name));
  const parameters = item => Object.entries(item.parameters || {}).map(([key, value]) => `${key}=${typeof value === 'object' ? `${value.start}…${value.end}` : value}`).join(', ');
  const candidateLabel = item => `${(item.strategy_id || 'Strategy').replaceAll('_', ' ')} · ${parameters(item)}`;
  const period = item => item ? `${item.first_session} → ${item.last_session} (${Array.isArray(item.sessions) ? item.sessions.length : item.sessions} sessions)` : 'Unavailable';
  const reason = value => {
    const [code, detail] = value.split(':');
    const labels = {all_predeclared_criteria_met: 'All declared qualification criteria passed',
      uncertainty_lower_bound_below_threshold: 'Historical uncertainty interval reaches below the required mean',
      too_few_parameter_neighbors: 'Too few neighboring parameter configurations were tested',
      neighbor_evidence_incomplete: 'Neighboring configurations need more evidence',
      unstable_parameter_region: 'Too few neighboring configurations met the criteria',
      bootstrap_tail_resolution: 'Too few bootstrap repetitions to resolve the declared confidence interval',
      too_few_sessions_for_blocks: 'Too few validation sessions for the declared sampling blocks'};
    return (labels[code] || words(code)) + (detail ? `: ${detail}` : '');
  };
  function showPlan(parent, plan) {
    parent.replaceChildren(node('h3', 'Review the chronological plan'));
    parent.append(node('p', `${plan.candidates.length} configurations · ${plan.folds.length} outer folds · ${plan.estimated_backtests} new backtest tasks before reuse.`));
    if (plan.execution_scenarios?.length) {
      parent.append(node('p', `${plan.execution_scenarios.length} execution scenarios are included in this work count. Every declared scenario gates qualification.`));
      table(parent, ['Execution scenario', 'Added commission · USD / contract / side', 'Added market / stop-only slippage · ticks', 'Limit fill assumption'],
        plan.execution_scenarios.map(item => [item.name, item.additional_commission_per_contract_per_side,
          `${item.additional_slippage_ticks} / ${item.stop_extra_slippage_ticks}`,
          `${item.limit_penetration_ticks}-tick penetration; opening improvement ${item.limit_price_improvement ? 'allowed' : 'disabled'}`]), 'robust-scenario-plan');
    }
    if (plan.regimes?.enabled_names?.length) parent.append(node('p', `Market conditions assessed: ${plan.regimes.enabled_names.map(regimeLabel).join(', ')}. Required for qualification: ${(plan.qualification.required_regimes || []).map(regimeLabel).join(', ') || 'none'}.`));
    table(parent, ['Outer fold', 'Research period', 'Reserved outer period', 'Inner validation folds'],
      plan.folds.map(fold => [fold.index, period(fold.train), period(fold.test), fold.inner.length]), 'robust-fold-plan');
    const inner = node('details'); inner.append(node('summary', 'Inspect every inner training and validation boundary'));
    table(inner, ['Outer fold', 'Inner fold', 'Training', 'Validation', 'Excluded sessions'], plan.folds.flatMap(fold => fold.inner.map(part => [fold.index, part.index, period(part.train), period(part.validation),
      `Purge: ${(part.excluded?.purge_sessions || []).join(', ') || 'none'}; embargo: ${(part.excluded?.embargo_sessions || []).join(', ') || 'none'}`])));
    parent.append(inner);
    parent.append(node('p', 'Each period starts without prior strategy state. Counts use observed sessions; saved source history has already been accessed.'));
    const assumptions = node('details'); assumptions.append(node('summary', 'Research assumptions and prior access')); list(assumptions, plan.limitations); parent.append(assumptions);
    parent.append(node('p', 'This increment runs inner qualification only. The outer periods remain reserved; economic selection, outer replay and deployment recommendation are pending.', 'robust-notice'));
  }
  function showResult(parent, record, includeDownloads = true) {
    const result = record.result;
    parent.replaceChildren(node('h3', `${record.declaration.name} · inner qualification evidence`));
    parent.append(node('p', 'These are chronological inner-validation results within each outer training period. They are not unseen outer outcomes or a deployment recommendation.', 'robust-notice'));
    if (!result) { parent.append(node('p', 'The saved result is not yet available.')); return; }
    const requirements = node('details'); requirements.append(node('summary', 'Saved qualification requirements'));
    table(requirements, ['Requirement', 'Saved value'], Object.entries(record.declaration.qualification).map(([key, value]) => [words(key), Array.isArray(value) ? value.join(', ') || 'None declared' : value === null ? 'Not imposed' : value]));
    parent.append(requirements);
    const candidates = new Map(record.plan.candidates.map(item => [item.id, item]));
    for (const fold of result.folds) {
      const section = node('details'); section.open = true; section.append(node('summary', `Outer fold ${fold.index} · ${fold.qualification.approved_ids.length} approved configurations`));
      table(section, ['Configuration', 'Qualification', 'Reasons'], fold.qualification.candidates.map(candidate => [
        candidateLabel(candidates.get(candidate.candidate_id) || {}),
        node('strong', candidate.status, `robust-outcome robust-${candidate.status.toLowerCase()}`),
        candidate.reasons.map(reason).join('; ') || 'All declared qualification requirements passed.',
      ]), `robust-qualification-${fold.index}`);
      for (const candidate of fold.qualification.candidates) {
        const detail = node('details'); detail.append(node('summary', `Evidence: ${candidateLabel(candidates.get(candidate.candidate_id) || {})}`));
        const metrics = Object.entries(candidate.metrics || {}).filter(([, value]) => value === null || typeof value !== 'object');
        table(detail, ['Measure', 'Value'], metrics.map(([key, value]) => [words(key), value]));
        if (candidate.uncertainty) {
          const interval = candidate.uncertainty;
          detail.append(node('p', `Historical uncertainty interval: ${interval.lower} to ${interval.upper} ${interval.unit}. Declared-family confidence level: ${interval.family_confidence_level * 100}%.`));
          detail.append(node('p', interval.limitations));
        }
        if (candidate.parameter_stability) {
          const region = candidate.parameter_stability;
          detail.append(node('p', `Parameter neighborhood: ${region.individually_qualified_neighbors?.length || 0} of ${region.neighbor_ids?.length || 0} neighbors met the individual criteria; ${region.required_passing_neighbors ?? 'unavailable'} required.`));
        }
        if (candidate.execution_stress) {
          const stress = candidate.execution_stress;
          detail.append(node('p', `Additional cost stress: $${stress.additional_round_trip_cost} per completed trade; stressed mean $${stress.stressed_mean_session_net ?? 'unavailable'} per validation session. Break-even additional cost: $${stress.break_even_additional_round_trip_cost ?? 'unavailable'} per trade.`));
          if (stress.scenarios?.length) {
            detail.append(node('h4', 'Execution scenario reruns'));
            const scenarios = table(detail, ['Scenario', 'Qualification', 'Coverage', 'Mean net · USD / validation session'], stress.scenarios.map(item => [
              item.name, item.status || (item.complete ? 'ASSESSED' : 'INSUFFICIENT_EVIDENCE'), item.complete ? 'All inner folds' : 'Incomplete', item.mean_session_net]));
            scenarios.classList.add('robust-scenario-results');
          }
        }
        if (candidate.market_conditions?.length) {
          detail.append(node('h4', 'Market-condition evidence'));
          detail.append(node('p', 'Only marked required conditions gate admission. Mean contributions include validation sessions with no trades in that condition. Conditions may overlap; their net amounts must not be added together.'));
          const conditions = table(detail, ['Condition', 'Required', 'Evidence', 'Validation sessions / assigned trades', 'Mean contribution · USD / validation session', 'Availability'], candidate.market_conditions.map(item => [
            regimeLabel(item.name), item.required ? 'Yes' : 'No', item.status,
            `${item.sessions} / ${item.trades}`, item.mean_session_net,
            item.reason ? reason(item.reason) : item.classification_complete ? 'Complete observable classification' : 'Classification incomplete']));
          conditions.classList.add('robust-regime-results');
        }
        const fitEvidence = (fold.regime_evidence || []).filter(item => item.candidate_id === candidate.candidate_id);
        if (fitEvidence.length) {
          const fit = node('details'); fit.append(node('summary', 'Training calibration and unknown validation observations'));
          const fitTable = table(fit, ['Inner fold', 'Training cutoff · UTC', 'Training feature samples', 'Calibration', 'Validation trades with unknown features'], fitEvidence.map(item => [
            item.inner_fold_index, item.fit.cutoff, item.fit.samples, words(item.fit.status), item.unclassified.trade_count]));
          fitTable.classList.add('robust-regime-fits');
          for (const item of fitEvidence) {
            fit.append(node('p', `Inner fold ${item.inner_fold_index}: trend efficiency ${item.fit.thresholds.trend_efficiency}; volatility threshold ${item.fit.thresholds.volatility_points ?? 'unavailable'} price points; liquidity threshold ${item.fit.thresholds.liquidity_volume ?? 'unavailable'} source-volume units.`));
            if (Object.keys(item.unclassified.reasons || {}).length) list(fit, Object.entries(item.unclassified.reasons).map(([key, count]) => `${reason(key)}: ${count} trades`));
          }
          fit.append(node('p', 'Trade-level label assignments and calibration provenance are saved in the report download. Missing warm-up observations are not filled with future information. Volume is a liquidity proxy, not evidence of executable depth or fill quality.')); detail.append(fit);
        }
        if (candidate.complexity) {
          const complexity = candidate.complexity;
          detail.append(node('h4', 'Strategy complexity'));
          detail.append(node('p', `Parameter classification: ${complexity.status || 'unreviewed'}. Searched signal dimensions: ${complexity.signal_search_dimensions ?? 'unavailable'}. Enabled optional filters: ${(complexity.enabled_optional_filters || []).join(', ') || 'none'}.`));
          if (complexity.inactive_parameters?.length) detail.append(node('p', `Inactive parameters: ${complexity.inactive_parameters.join(', ')}. Their enabling controls are off, so these settings do not define distinct candidates or parameter neighbors.`));
          if (complexity.definition) detail.append(node('p', complexity.definition));
          if (complexity.simpler_configurations?.length) table(detail, ['Simpler configuration', 'Enabled optional filters', 'Mean net · USD / session', 'Individual qualification'], complexity.simpler_configurations.map(item => [
            candidateLabel(candidates.get(item.candidate_id) || {}), item.enabled_optional_filters.join(', ') || 'none', item.mean_session_net, item.individual_status]));
          if (complexity.interpretation) detail.append(node('p', complexity.interpretation));
        }
        list(detail, candidate.limitations);
        const runs = (fold.backtests || []).filter(run => run.candidate_id === candidate.candidate_id);
        if (runs.length) {
          const links = node('ul');
          for (const run of runs) { const item = node('li'); item.append(link(`Inner fold ${run.inner_fold_index} · ${run.scenario_name ? `Execution scenario ${run.scenario_name}` : words(run.role)} backtest`, `#backtests/report/${run.run_id}`)); links.append(item); }
          detail.append(links);
        }
        section.append(detail);
      }
      parent.append(section);
    }
    parent.append(node('h3', 'Next decision'));
    list(parent, result.readiness?.reasons || ['Outer economic replay and deployment validation are pending.']);
    parent.append(node('p', `Readiness: ${result.readiness?.status || 'INCOMPLETE'}. No deployment policy is recommended by this increment.`));
    if (includeDownloads) {
      const downloads = node('div', undefined, 'robust-actions');
      for (const file of ['report.json', 'analysis.zip', 'qualification.csv']) downloads.append(link(`Download ${file}`, `${base}/${record.campaign_id}/exports/${file}`));
      parent.append(downloads);
    }
    if (record.analysis_id) parent.append(link('Open the saved analysis report', `#backtests/prop/job/${record.analysis_id}`));
  }
  function renderAnalysis(report) {
    const record = {campaign_id: report.request.campaign_id, declaration: report.request, plan: report.plan, result: report.calculations};
    document.querySelector('#prop-config').hidden = true;
    document.querySelector('#prop-report').hidden = false;
    document.querySelector('#prop-heading-title').textContent = 'Nested research · inner qualification';
    document.querySelector('#prop-heading-note').textContent = 'Saved chronological inner evidence · outer economic validation pending';
    document.querySelector('#prop-back').href = `#backtests/prop/new/${report.request.source_backtest_id}`;
    document.querySelector('#prop-back').textContent = '← Back to research configuration';
    const content = document.querySelector('#prop-report-content'); content.replaceChildren();
    const plan = node('section', undefined, 'panel prop-panel'), results = node('section', undefined, 'panel prop-panel');
    content.append(plan, results); showPlan(plan, report.plan); showResult(results, record, false);
    const downloads = node('div', undefined, 'robust-actions');
    for (const [name, path] of [['Report JSON', 'downloads/report.json'], ['Analysis ZIP', 'downloads/analysis.zip'], ['Qualification CSV', 'files/qualification.csv']]) downloads.append(link(name, `/api/prop-analyses/${report.id}/${path}`));
    results.append(downloads);
  }
  async function configure(source) {
    const version = ++generation, route = location.hash;
    const current = () => version === generation && route === location.hash;
    panel.replaceChildren(node('h2', 'Nested research'));
    if (source.run_metadata.source?.kind === 'external_trade_export' || source.capabilities?.nested_research === false) {
      panel.append(node('p', 'Nested strategy reruns require native strategy code and market bars. Imported trades retain their declared research history; eligible sources can use independent phase campaigns above, while nested strategy reruns remain unavailable.')); return;
    }
    if (source.run_metadata.research?.phase !== 'is') {
      panel.append(node('p', 'Open a declared in-sample backtest to configure chronological research.')); return;
    }
    panel.append(node('p', 'Check whether strategy configurations remain credible across earlier training and later validation periods. Research settings and thresholds are saved before any work starts.'));
    const history = node('div'), disclosure = node('details'); disclosure.id = 'robust-configure';
    disclosure.append(node('summary', 'Configure nested research'));
    panel.append(history, disclosure);
    const loading = node('p', 'Loading research settings…'); disclosure.append(loading);
    let defaults;
    try { defaults = await api(`${base}/defaults`); } catch (error) { loading.textContent = `Research settings unavailable: ${error.message}`; return; }
    if (!current()) return;
    loading.remove();
    const form = node('form'); form.id = 'robust-form'; disclosure.append(form);
    form.addEventListener('submit', event => event.preventDefault());
    const name = field(form, 'Research name', 'robust-name', `${source.run_metadata.strategy.id.replaceAll('_', ' ')} · nested qualification`, 'text'); name.maxLength = 120;
    form.append(node('h3', '1. Choose saved strategy configurations'));
    form.append(node('p', 'Saved IS reports define candidate parameters and execution settings. Each configuration is rerun on the declared inner periods. Saved full-period performance is not used to qualify it.'));
    const picker = node('div', undefined, 'prop-fields'); form.append(picker);
    const kind = select(picker, 'Source type', 'robust-source-kind', [['backtest_id', 'Backtests'], ['optimization_id', 'Optimization jobs']]);
    const query = field(picker, 'Find saved sources', 'robust-source-search', '', 'search'); query.required = false;
    const choices = node('div', undefined, 'robust-source-choices'); choices.id = 'robust-source-choices'; form.append(choices);
    const sourceStatus = node('p'); sourceStatus.id = 'robust-source-status'; sourceStatus.setAttribute('role', 'status');
    const more = button(form, 'Load more sources', 'robust-source-more'); form.append(sourceStatus);
    const selected = new Map([[`backtest_id:${source.id}`, {kind: 'backtest_id', id: source.id, item: {
      strategy_id: source.run_metadata.strategy.id, parameters: source.run_metadata.strategy.parameters,
      dataset_name: source.run_metadata.dataset.name, selectable: true,
    }}]]);
    let matches = [], offset = 0, total = 0, searchVersion = 0, searchTimer;
    function drawSources() {
      choices.replaceChildren();
      const entries = new Map([...selected, ...matches.map(item => [`${kind.value}:${item.id}`, {kind: kind.value, id: item.id, item}])]);
      for (const [key, entry] of entries) {
        const label = node('label', undefined, 'robust-source-choice'), check = node('input');
        check.type = 'checkbox'; check.checked = selected.has(key); check.disabled = !entry.item.selectable;
        check.setAttribute('aria-label', `${candidateLabel(entry.item)} ${entry.id.slice(0, 8)}`);
        const text = node('span', `${candidateLabel(entry.item)} · ${entry.item.dataset_name || ''}${entry.kind === 'optimization_id' ? ` · ${entry.item.total_trials} trials` : ''} · ${entry.id.slice(0, 8)}`);
        check.onchange = () => { if (check.checked) selected.set(key, entry); else selected.delete(key); invalidate(); };
        label.append(check, text); choices.append(label);
      }
    }
    async function loadSources(reset = false) {
      const attempt = ++searchVersion, type = kind.value;
      more.disabled = true; sourceStatus.textContent = 'Loading saved IS sources…';
      try {
        const page = await api(`/api/research-campaigns/sources?${new URLSearchParams({kind: type, q: query.value.trim(), offset: reset ? 0 : offset, limit: 50})}`);
        if (!current() || attempt !== searchVersion) return;
        matches = reset ? page.items : matches.concat(page.items); offset = page.offset + page.items.length; total = page.total;
        drawSources(); more.hidden = offset >= total;
        sourceStatus.textContent = total ? `${matches.length} of ${total} matching sources. Selected sources remain visible when searching.` : 'No matching sources. Selected configurations remain available.';
      } catch (error) { if (current()) sourceStatus.textContent = `Could not load sources: ${error.message}`; }
      finally { if (current() && attempt === searchVersion) more.disabled = false; }
    }
    more.onclick = () => loadSources();
    kind.onchange = () => { matches = []; drawSources(); loadSources(true); };
    query.oninput = () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => loadSources(true), 250); };
    form.append(node('h3', '2. Declare the chronological validation plan'));
    const folds = node('div', undefined, 'prop-fields'); form.append(folds);
    const mode = select(folds, 'Training window', 'robust-mode', [['rolling', 'Rolling · fixed training length'], ['expanding', 'Expanding · retain earlier history']]); mode.value = defaults.folds.mode;
    const foldLabels = {
      outer_train_sessions: 'Outer training · sessions', outer_test_sessions: 'Reserved outer test · sessions',
      inner_train_sessions: 'Inner training · sessions', inner_validation_sessions: 'Inner validation · sessions',
      purge_sessions: 'Purge between training and validation · sessions', embargo_sessions: 'Embargo · sessions',
      minimum_inner_folds: 'Minimum inner folds', minimum_outer_folds: 'Minimum outer folds',
    };
    const foldInputs = {};
    for (const [key, label] of Object.entries(foldLabels)) {
      const input = field(folds, label, `robust-${key}`, defaults.folds[key]); input.min = key.includes('purge') || key.includes('embargo') ? 0 : 1; input.step = 1; foldInputs[key] = input;
    }
    form.append(node('p', 'Session counts use observed CME session dates with a 17:00 Chicago boundary. The preview shows exact dates, gaps and work count. A source that cannot support the declared plan is rejected.'));
    const thresholds = node('details'); thresholds.id = 'robust-qualification-configure'; thresholds.append(node('summary', '3. Qualification requirements · review before running'));
    thresholds.append(node('p', 'These are saved research requirements, not universal evidence standards. Changing them after inspecting results is another research decision and does not create untouched evidence.'));
    const qualificationFields = node('div', undefined, 'prop-fields'); thresholds.append(qualificationFields); form.append(thresholds);
    const qualificationInputs = {}, optionalLimits = {};
    const complexityLabels = {maximum_signal_search_dimensions: 'Maximum searched signal dimensions', maximum_enabled_optional_filters: 'Maximum enabled optional strategy filters'};
    const moneyFields = new Set(['minimum_mean_session_net', 'additional_round_trip_cost', 'minimum_stressed_mean_session_net', 'minimum_scenario_mean_session_net', 'minimum_regime_mean_session_net']);
    const qualificationLabels = {
      minimum_folds: 'Required inner validation folds', minimum_sessions: 'Required validation sessions', minimum_trades: 'Required completed validation trades',
      minimum_trades_per_fold: 'Required trades in each inner fold', minimum_mean_session_net: 'Minimum mean net · USD per session',
      minimum_positive_fold_fraction: 'Minimum profitable fold fraction · 0–1', maximum_profit_concentration: 'Maximum share of positive profits in one fold · 0–1',
      additional_round_trip_cost: 'Additional stress cost · USD per completed trade', minimum_stressed_mean_session_net: 'Minimum stressed mean net · USD per session',
      minimum_neighbors: 'Required adjacent parameter neighbors', minimum_neighbor_pass_fraction: 'Minimum qualifying neighbor fraction · 0–1',
      bootstrap_replicates: 'Historical bootstrap repetitions', bootstrap_block_sessions: 'Historical sampling block · sessions', bootstrap_seed: 'Reproducible sampling seed',
      confidence_level: 'Historical interval confidence · 0.5–1', minimum_bootstrap_tail_samples: 'Minimum repetitions in each interval tail',
      required_scenarios: 'Required execution scenarios · comma-separated names', required_regimes: 'Required market regimes · comma-separated names',
      minimum_regime_sessions: 'Required sessions in each named regime', minimum_regime_trades: 'Required trades in each named regime',
      minimum_scenario_mean_session_net: 'Minimum scenario mean net · USD per session', minimum_regime_mean_session_net: 'Minimum regime mean net · USD per session',
    };
    for (const [key, value] of Object.entries(defaults.qualification)) {
      if (key === 'required_scenarios' || key === 'required_regimes') continue;
      if (key in complexityLabels) {
        const group = node('div'), label = node('label', undefined, 'robust-source-choice'), enabled = node('input'); enabled.type = 'checkbox'; enabled.id = `robust-enable-${key}`; enabled.checked = value !== null;
        label.append(enabled, node('span', `Impose a limit: ${complexityLabels[key].toLowerCase()}`)); group.append(label);
        const input = field(group, complexityLabels[key], `robust-qualification-${key}`, value ?? ''); input.min = 0; input.step = 1; input.disabled = !enabled.checked;
        enabled.onchange = () => { input.disabled = !enabled.checked; invalidate(); if (enabled.checked) input.focus(); };
        optionalLimits[key] = {enabled, input}; qualificationFields.append(group); continue;
      }
      if (typeof value === 'number' || moneyFields.has(key)) { const input = field(qualificationFields, qualificationLabels[key] || words(key), `robust-qualification-${key}`, value); input.step = 'any'; qualificationInputs[key] = input; }
      else if (typeof value === 'boolean') { const input = select(qualificationFields, words(key), `robust-qualification-${key}`, [['true', 'Required'], ['false', 'Not required']]); input.value = String(value); qualificationInputs[key] = input; }
      else if (Array.isArray(value)) { const input = field(qualificationFields, qualificationLabels[key] || words(key), `robust-qualification-${key}`, value.join(', '), 'text'); input.required = false; qualificationInputs[key] = input; }
    }
    thresholds.append(node('p', 'Net amounts use each saved source’s trade quantities and baseline costs. The additional round-trip cost check adjusts cash only. Execution assumptions are rerun separately below. Historical sampling repetitions do not add independent observations.'));
    const scenarioSection = node('details'); scenarioSection.id = 'robust-execution-configure'; scenarioSection.append(node('summary', '4. Execution stress · rerun the strategy'));
    scenarioSection.append(node('p', 'Add named execution scenarios to rerun each inner validation period. Each scenario must meet the declared scenario threshold for a configuration to qualify. Changes apply in addition to the source’s baseline costs and execution settings.'));
    const scenarioRows = node('div'); scenarioRows.id = 'robust-execution-scenarios'; scenarioSection.append(scenarioRows); form.append(scenarioSection);
    let scenarioSequence = 0;
    const scenarioInputs = new Map();
    const scenarioLabels = {
      additional_commission_per_contract_per_side: 'Additional commission · USD per contract per side',
      additional_slippage_ticks: 'Additional market slippage · ticks', stop_extra_slippage_ticks: 'Additional stop-only slippage · ticks',
      limit_penetration_ticks: 'Required limit-price penetration · ticks',
    };
    function addScenario() {
      const index = ++scenarioSequence, row = node('fieldset'), legend = node('legend', `Execution scenario ${index}`);
      row.className = 'prop-fields'; row.dataset.scenarioIndex = String(index); row.append(legend);
      const inputs = {name: field(row, 'Scenario name', `robust-scenario-${index}-name`, `stress-${index}`, 'text')}; inputs.name.maxLength = 100;
      for (const [key, label] of Object.entries(scenarioLabels)) {
        const input = field(row, label, `robust-scenario-${index}-${key}`, defaults.execution_scenario[key]);
        input.min = 0; input.step = key === 'additional_commission_per_contract_per_side' ? 'any' : 1; inputs[key] = input;
      }
      inputs.limit_price_improvement = select(row, 'Limit order price improvement', `robust-scenario-${index}-limit_price_improvement`, [['true', 'Allow the existing opening-price improvement'], ['false', 'Fill at the limit price when eligible']]);
      inputs.limit_price_improvement.value = String(defaults.execution_scenario.limit_price_improvement);
      const remove = button(row, 'Remove scenario', `robust-scenario-${index}-remove`);
      remove.onclick = () => { scenarioInputs.delete(index); row.remove(); invalidate(); };
      scenarioInputs.set(index, inputs); scenarioRows.append(row); invalidate(); inputs.name.focus();
    }
    if (defaults.execution_scenario) button(scenarioSection, 'Add execution scenario', 'robust-add-scenario').onclick = addScenario;
    else scenarioSection.append(node('p', 'Execution scenario settings are unavailable from this server.'));
    const regimesSection = node('details'); regimesSection.id = 'robust-regimes-configure'; regimesSection.append(node('summary', '5. Market conditions · choose relevant evidence'));
    regimesSection.append(node('p', 'Assess the market conditions relevant to this hypothesis. Require only those conditions in which the strategy is intended to work. A strategy does not need to profit in every assessed condition. Calibration uses each inner training period; validation labels use information available by the decision time.'));
    const regimeChoices = node('div', undefined, 'robust-source-choices'); regimeChoices.id = 'robust-regime-choices'; regimesSection.append(regimeChoices); form.append(regimesSection);
    const regimeInputs = new Map();
    const regimeNames = Array.isArray(defaults.regime_names) ? defaults.regime_names.map(name => [name, words(name)]) : Object.entries(defaults.regime_names || {});
    for (const [key, label] of regimeNames) {
      const row = node('fieldset', undefined, 'prop-fields'); row.append(node('legend', label));
      const enabledLabel = node('label', undefined, 'robust-source-choice'), enabled = node('input'); enabled.type = 'checkbox'; enabled.id = `robust-regime-${key}`;
      enabled.checked = defaults.regimes.enabled_names.includes(key); enabledLabel.append(enabled, node('span', `Assess ${label.toLowerCase()}`));
      const requiredLabel = node('label', undefined, 'robust-source-choice'), required = node('input'); required.type = 'checkbox'; required.id = `robust-require-${key}`;
      required.checked = defaults.qualification.required_regimes.includes(key); required.disabled = !enabled.checked;
      requiredLabel.append(required, node('span', `Require ${label.toLowerCase()} for qualification`));
      enabled.onchange = () => { required.disabled = !enabled.checked; if (!enabled.checked) required.checked = false; invalidate(); };
      required.onchange = invalidate; row.append(enabledLabel, requiredLabel); regimeChoices.append(row); regimeInputs.set(key, {enabled, required});
    }
    const calibration = node('details'); calibration.id = 'robust-regime-calibration'; calibration.append(node('summary', 'Advanced market-condition calibration'));
    const calibrationFields = node('div', undefined, 'prop-fields'); calibration.append(calibrationFields); regimesSection.append(calibration);
    const calibrationLabels = {
      lookback_bars: 'Feature lookback · completed bars', minimum_training_features: 'Minimum training observations for calibration',
      trend_efficiency_threshold: 'Trend efficiency threshold · 0–1', volatility_quantile: 'Training volatility split · quantile 0–1',
      liquidity_quantile: 'Training liquidity split · quantile 0–1', timezone: 'Session-label timezone · IANA name',
      asia_start_hour: 'Asia label starts · local hour 0–23', europe_start_hour: 'Europe label starts · local hour 0–23', us_start_hour: 'US label starts · local hour 0–23',
    };
    const calibrationInputs = {};
    for (const [key, label] of Object.entries(calibrationLabels)) {
      if (defaults.regimes?.[key] === undefined) continue;
      const input = field(calibrationFields, label, `robust-regime-${key}`, defaults.regimes[key], key === 'timezone' ? 'text' : 'number');
      if (key !== 'timezone') input.step = ['trend_efficiency_threshold', 'volatility_quantile', 'liquidity_quantile'].includes(key) ? 'any' : 1;
      calibrationInputs[key] = input;
    }
    regimesSection.append(node('p', 'Missing calibration observations and unavailable warm-up features stay visible as unknown evidence. Required conditions with insufficient evidence block qualification.'));
    const actions = node('div', undefined, 'robust-actions'); form.append(actions);
    const preview = button(actions, 'Preview dates and source checks', 'robust-preview');
    const run = button(actions, 'Save and run inner qualification', 'robust-run'); run.disabled = true;
    const status = node('p'); status.id = 'robust-status'; status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite'); form.append(status);
    const planView = node('div'); planView.id = 'robust-plan'; form.append(planView);
    const resultView = node('div'); resultView.id = 'robust-result'; disclosure.append(resultView);
    let checked = null, revision = 0, busy = false, watchVersion = 0;
    function invalidate() { revision++; checked = null; run.disabled = true; status.textContent = 'Settings changed. Preview the plan before running.'; planView.replaceChildren(); }
    form.addEventListener('input', event => { if (event.target !== query) invalidate(); });
    form.addEventListener('change', event => { if (event.target !== kind && event.target.type !== 'checkbox') invalidate(); });
    function body() {
      if (!selected.size) throw Error('Choose at least one saved source.');
      const qualification = {...defaults.qualification};
      for (const [key, input] of Object.entries(qualificationInputs)) qualification[key] = moneyFields.has(key) ? input.value : Array.isArray(defaults.qualification[key])
        ? input.value.split(',').map(value => value.trim()).filter(Boolean) : typeof defaults.qualification[key] === 'boolean' ? input.value === 'true' : Number(input.value);
      for (const [key, fields] of Object.entries(optionalLimits)) qualification[key] = fields.enabled.checked ? Number(fields.input.value) : null;
      const execution_scenarios = [...scenarioInputs.values()].map(inputs => ({name: inputs.name.value.trim(),
        ...Object.fromEntries(Object.keys(scenarioLabels).map(key => [key, key === 'additional_commission_per_contract_per_side' ? inputs[key].value : Number(inputs[key].value)])),
        limit_price_improvement: inputs.limit_price_improvement.value === 'true'}));
      qualification.required_scenarios = execution_scenarios.map(scenario => scenario.name);
      qualification.required_regimes = [...regimeInputs].filter(([, inputs]) => inputs.required.checked).map(([key]) => key);
      const regimes = {...defaults.regimes, enabled_names: [...regimeInputs].filter(([, inputs]) => inputs.enabled.checked).map(([key]) => key)};
      for (const [key, input] of Object.entries(calibrationInputs)) regimes[key] = typeof defaults.regimes[key] === 'number' ? Number(input.value) : input.value;
      return {campaign_id: crypto.randomUUID().replaceAll('-', ''), name: name.value.trim(), source_backtest_id: source.id,
        sources: [...selected.values()].map(entry => ({[entry.kind]: entry.id, sizes: [1]})),
        folds: {...Object.fromEntries(Object.entries(foldInputs).map(([key, input]) => [key, Number(input.value)])), mode: mode.value}, qualification,
        execution_scenarios, regimes};
    }
    async function refreshHistory() {
      try {
        const saved = await api(`${base}?source_id=${source.id}`); if (!current()) return;
        history.replaceChildren();
        if (saved.items.length) history.append(node('h3', 'Saved research'));
        for (const record of saved.items) button(history, `${record.name || record.declaration?.name || 'Research'} · ${record.status}`, '').onclick = () => watch(record.campaign_id);
      } catch (error) { if (current()) history.textContent = `Saved research could not load: ${error.message}`; }
    }
    async function watch(id) {
      const attempt = ++watchVersion; disclosure.open = true;
      status.textContent = 'Opening saved research…';
      while (current() && attempt === watchVersion) {
        let record;
        try { record = await api(`${base}/${id}`); } catch (error) { status.textContent = error.message; return; }
        if (!current() || attempt !== watchVersion) return;
        status.textContent = `${record.declaration.name} · ${record.status} · ${record.progress || ''}`;
        if (record.status === 'complete') { showPlan(planView, record.plan); showResult(resultView, record); await refreshHistory(); return; }
        if (['error', 'failed', 'interrupted', 'draft', 'ready', 'validated'].includes(record.status)) {
          showPlan(planView, record.plan);
          resultView.replaceChildren(node('p', record.error || 'The checked research plan is saved and ready to run.'));
          const retry = button(resultView, record.error ? 'Retry saved research' : 'Run saved research', 'robust-resume');
          retry.onclick = async () => { retry.disabled = true; try { await api(`${base}/${id}/run`, {}); watch(id); } catch (error) { status.textContent = error.message; retry.disabled = false; } };
          return;
        }
        resultView.replaceChildren(node('p', record.cancel_requested ? 'Stop requested at the next available checkpoint. Completed backtests are retained. A finishing run may complete before the stop takes effect.' : 'Research continues when you navigate away. Completed backtests are retained for recovery.'));
        const cancel = button(resultView, 'Request stop at next checkpoint', 'robust-cancel'); cancel.disabled = record.cancel_requested;
        cancel.onclick = async () => { cancel.disabled = true; try { await api(`${base}/${id}/cancel`, {}); } catch (error) { status.textContent = error.message; cancel.disabled = false; } };
        await new Promise(resolve => setTimeout(resolve, 750));
      }
    }
    preview.onclick = async () => {
      if (busy || !form.reportValidity()) return;
      busy = true; preview.disabled = true; run.disabled = true; const versionAtCheck = revision;
      status.textContent = 'Checking sources and deriving session boundaries…';
      try {
        const request = body(), plan = await api(`${base}/preview`, request);
        if (!current() || revision !== versionAtCheck) return;
        checked = {...request, confirmed_backtest_count: plan.estimated_backtests}; showPlan(planView, plan); run.disabled = false;
        run.textContent = `Save and run ${plan.estimated_backtests} inner backtests`;
        status.textContent = 'Source checks passed. Review the dates and qualification requirements, then run.';
      } catch (error) { if (current()) status.textContent = `Plan needs attention: ${error.message}`; }
      finally { busy = false; if (current()) preview.disabled = false; }
    };
    run.onclick = async () => {
      if (busy || !checked) return;
      busy = true; run.disabled = true; preview.disabled = true; status.textContent = 'Saving the declared research procedure…';
      try {
        const record = await api(base, checked); await api(`${base}/${record.campaign_id}/run`, {});
        await refreshHistory(); await watch(record.campaign_id);
      } catch (error) { if (current()) status.textContent = `Research could not start: ${error.message}`; }
      finally { busy = false; if (current()) { preview.disabled = false; run.disabled = !checked; } }
    };
    drawSources(); await Promise.all([loadSources(true), refreshHistory()]);
  }
  window.robustResearch = {configure, renderAnalysis};
})();
