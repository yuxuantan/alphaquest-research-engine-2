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
  const valueText = value => value === null || value === undefined ? 'Unavailable'
    : typeof value === 'boolean' ? value ? 'Yes' : 'No'
    : Array.isArray(value) ? value.map(valueText).join(', ') || 'None' : String(value);
  const phaseLabel = phase => phase === 'evaluation' ? 'Evaluation · acquisition cost and time' : 'Funded · trader cash received';
  const selectionLabel = selector => ({pareto_family: 'Keep the complete cost / time Pareto family',
    min_cost_under_time_cap: 'Lowest expected cost within the declared time limit',
    min_time_under_cost_cap: 'Shortest expected time within the declared cost limit',
    maximum_expected_received_cash: 'Highest expected trader cash received',
    conservative_expected_received_cash: 'Highest historical lower bound on expected trader cash'}[selector?.mode] || 'Selection rule unavailable');
  function retainedTable(parent, title, rows, columns, className) {
    if (!rows?.length) return;
    const detail = node('details'); detail.append(node('summary', `${title} · ${rows.length} retained rows`));
    if (className) detail.className = className;
    const content = node('div'), controls = node('div', undefined, 'robust-actions');
    const previous = button(controls, 'Previous 25'), position = node('span'), next = button(controls, 'Next 25');
    controls.insertBefore(position, next); detail.append(content, controls); parent.append(detail);
    let offset = 0;
    const draw = () => {
      content.replaceChildren();
      table(content, columns.map(([label]) => label), rows.slice(offset, offset + 25).map(row => columns.map(([, read]) => valueText(read(row)))));
      position.textContent = `${offset + 1}–${Math.min(offset + 25, rows.length)} of ${rows.length}`;
      previous.disabled = offset === 0; next.disabled = offset + 25 >= rows.length;
    };
    previous.onclick = () => { offset = Math.max(0, offset - 25); draw(); };
    next.onclick = () => { offset += 25; draw(); }; draw();
  }
  function showStudy(parent, study) {
    const section = node('details'); section.append(node('summary', phaseLabel(study.phase)));
    section.append(node('p', selectionLabel(study.selector)));
    table(section, ['Account profile', 'Saved rule version', 'Fixed MNQ policies', ...(study.phase === 'evaluation' ? ['Evaluation fee · USD', 'Activation fee · USD'] : [])],
      study.profiles.map(profile => [profile.profile_id, profile.rule_version, study.policies.map(policy => policy.micros).join(', '),
        ...(study.phase === 'evaluation' ? [profile.evaluation_price, profile.activation_fee] : [])]));
    const labels = {maximum_cost_per_funded: 'Maximum expected acquisition cost · USD',
      maximum_expected_calendar_days: 'Maximum expected acquisition time · calendar days',
      minimum_pass_probability: 'Minimum pass probability · 0–1', minimum_expected_cash: 'Minimum selected expected-cash objective · USD',
      maximum_account_breach_probability: 'Maximum account breach probability · 0–1',
      minimum_probability_first_payout: 'Minimum first payout probability · 0–1', minimum_p10_payouts: 'Minimum P10 received cash · USD',
      maximum_position_size: 'Maximum position size · MNQ'};
    const constraints = {...study.selector, ...study.search_settings?.constraints};
    table(section, ['Declared constraint', 'Value'], Object.entries(labels).filter(([key]) => constraints[key] !== undefined).map(([key, label]) => [label, constraints[key] ?? 'Not imposed']));
    section.append(node('p', `Exact objective ties: ${study.selector?.tie_policy === 'configuration_id' ? 'choose the first by stable configuration ID' : 'retain the complete tied family'}.`));
    const settings = [['Forecast paths per candidate', study.simulation?.simulations], ['Simulation seed', study.simulation?.seed],
      ['Account size ceiling · MNQ', study.simulation?.max_micros], ['Resampling block · weekdays', study.sampling?.block_weekdays], ['Costs', study.costs?.mode === 'source' ? 'Saved source costs; no second deduction' : study.costs?.mode],
      ['Declared calendar version', study.search_settings?.calendar?.version], ['Calendar timezone', study.search_settings?.calendar?.timezone],
      ['Declared closed dates', valueText(study.search_settings?.calendar?.closures || [])]];
    if (study.phase === 'evaluation') settings.push(['Acquisition forecast chains', study.sampling?.chain_simulations], ['Acquisition seed', study.sampling?.chain_seed],
      ['Retry delay · calendar days', study.retry?.retry_delay_calendar_days], ['Activation delay · eligible sessions', study.retry?.activation_delay_sessions],
      ['Attempt guard', study.retry?.max_attempts], ['Calendar-day guard', study.retry?.max_calendar_days]);
    else settings.push(['Forecast horizon · calendar days', study.search_settings?.horizon_calendar_days ?? 'Derived from each outer interval; see the chronological plan'],
      ['Receipt delay · calendar days', study.search_settings?.receipt_delay_calendar_days]);
    table(section, ['Saved forecast assumption', 'Value'], settings.map(([label, value]) => [label, valueText(value)]));
    if (study.search_settings?.conservative_objective) {
      section.append(node('p', 'The conservative objective resamples historical session blocks and re-estimates expected cash. Its lower empirical percentile concerns the mean estimate, not the payout of one account. It is neither a Monte Carlo-only confidence interval nor a future guarantee.'));
      table(section, ['Historical mean requirement', 'Saved value'], Object.entries(study.search_settings.conservative_objective).map(([key, value]) => [words(key), value]));
    }
    if (study.phase === 'funded') section.append(node('p', 'Forecast and chronological replay both use unrounded modeled trader entitlement. This fixed receipt amount convention preserves comparability; it is not a statement of bank settlement or cent rounding.'));
    parent.append(section);
  }
  function showChronologicalReplay(parent, replay) {
    const section = node('section', undefined, 'robust-chronological-result'); parent.append(section);
    section.append(node('h4', 'Historical chronological replay · one observed path'));
    section.append(node('p', 'This is one local replay of the dated outer observations under the previously frozen policy. It is separate from the earlier Monte Carlo forecast; it does not establish future or provider performance.'));
    const evaluation = replay.phase === 'evaluation';
    const measures = evaluation ? [
      ['Evaluation passed', replay.evaluation_passed], ['Acquisition completed before cutoff', replay.acquisition_completed],
      ['Pass date', replay.pass_date], ['Activation eligibility date', replay.eligibility_date], ['First funded-ready date', replay.ready_date], ['Attempts', replay.attempts?.length],
      ['Paid evaluation fees · USD', replay.paid_evaluation_fees], ['Paid activation fees · USD', replay.paid_activation_fees],
      ['Paid evaluation and activation fees · USD', replay.paid_fees], ['Activation paid', replay.activation_paid],
      ['Pending activation obligation · USD', replay.pending_activation], ['Calendar days to funded readiness', replay.calendar_days_to_funded],
      ['Net trader cash · USD', replay.net_cash], ['Censored at cutoff or guard', replay.censored],
      ['Effective observation cutoff · exclusive', replay.effective_observation_cutoff_exclusive], ['Calendar guard shortens the outer observation window', replay.calendar_guard_truncates_window]] : [
      ['Account outcome', replay.outcome], ['Terminal date', replay.terminal_date], ['Cash received · USD', replay.cash_received],
      ['Pending modeled receipts · USD', replay.pending_cash], ['Gross account deductions · USD', replay.gross_account_deductions],
      ['Raw trader entitlement · USD', replay.raw_trader_entitlement], ['Receipt amount convention', replay.receipt_amount_convention],
      ['Ending trading equity · USD', replay.equity], ['Modeled trading profit · USD', replay.trading_profit],
      ['Lifetime censored', replay.lifetime_censored], ['Horizon observations complete', replay.horizon_observations_complete], ['Account sessions processed', replay.observed_sessions]];
    const metrics = table(section, ['Historical observation', 'Value'], measures.map(([label, value]) => [label, valueText(value)])); metrics.classList.add('robust-chronological-metrics');
    section.append(node('p', evaluation
      ? 'Evaluation uses actual subsequent dates for each frozen retry. Evaluation profit is not trader cash, and this phase does not trade a funded account.'
      : 'One fresh funded account; no acquisition fees or replacement account. Equity and payout requests are not trader cash. Receipts due at the exclusive cutoff remain pending.'));
    retainedTable(section, 'Evaluation attempts', replay.attempts, [
      ['Attempt', row => row.index], ['Purchase date', row => row.purchase_date], ['First session', row => row.first_session],
      ['Terminal date', row => row.terminal_date], ['Outcome', row => row.outcome], ['Ending equity · USD', row => row.equity]], 'robust-attempts');
    retainedTable(section, 'Payout requests and settlement', replay.payout_events, [
      ['Request date', row => row.request_date], ['Account deduction · USD', row => row.gross_account_deduction],
      ['Raw trader entitlement · USD', row => row.raw_trader_entitlement], ['Modeled receipt · USD', row => row.trader_amount],
      ['Receipt date', row => row.receipt_date], ['Received before cutoff', row => row.received_within_horizon],
      ['Amount convention', row => row.amount_convention], ['Settlement assumption', row => row.timing]], 'robust-payouts');
    retainedTable(section, 'Dated cash ledger', replay.cash_ledger, [
      ['Date', row => row.date], ['Event', row => words(row.event || 'unknown')], ['Cash change · USD', row => row.cash_delta],
      ['Account equity change · USD', row => row.account_equity_delta], ['Attempt / payout', row => row.attempt ?? row.payout_id]], 'robust-cash-ledger');
    retainedTable(section, 'Chronological account transitions', replay.trace, [
      ['Session date', row => row.date], ['Equity before · USD', row => row.equity_before], ['Equity after · USD', row => row.equity_after],
      ['Outcome / event', row => row.outcome || words(row.event || 'unknown')], ['Visited source trades', row => row.visited_source_trade_ids],
      ['Executed opportunities', row => row.executed], ['Unvisited source trades', row => row.unvisited_source_trade_ids]], 'robust-outer-trace');
    if (replay.observations) section.append(node('p', `${replay.observations.source_opportunities} observed source opportunities · ${replay.observations.visited} visited · ${replay.observations.unvisited} unvisited after account timing or termination.`));
    if (replay.assumptions?.length) { const assumptions = node('details'); assumptions.append(node('summary', 'Chronological model assumptions')); list(assumptions, replay.assumptions); section.append(assumptions); }
    if (replay.readiness) section.append(node('p', `Replay interpretation: ${replay.readiness}.`));
  }
  function economicControls(parent, defaults, changed) {
    const section = node('details'); section.id = 'robust-economic-configure';
    section.append(node('summary', '6. Economic validation · optional independent phase studies'));
    section.append(node('p', 'Every qualified strategy configuration enters each enabled study at every declared profile and fixed MNQ quantity. The saved selection rule freezes its choices before outer strategy execution. No second strategy grid or combined Evaluation / Funded score is used.'));
    section.append(node('p', 'Native studies currently support fixed quantities without account-cushion sizing guards. Dollar or percentage risk sizing requires account-state strategy reruns. Imported trade sources do not acquire native nested-replay capability.'));
    parent.append(section);
    const studies = [];
    for (const phase of ['evaluation', 'funded']) {
      const template = defaults.economic_studies?.[phase];
      if (!template) continue;
      const entry = node('section'), label = node('label', undefined, 'robust-source-choice'), enabled = node('input');
      enabled.type = 'checkbox'; enabled.id = `robust-economic-${phase}`;
      label.append(enabled, node('span', `Include ${phaseLabel(phase)}`)); entry.append(label); section.append(entry);
      const fields = node('fieldset'); fields.id = `robust-economic-${phase}-fields`; fields.disabled = true; fields.hidden = true; fields.append(node('legend', phaseLabel(phase))); entry.append(fields);
      const prefix = `robust-economic-${phase}-`, inputs = [], profileInputs = [];
      const profiles = node('div', undefined, 'prop-fields'); fields.append(profiles);
      for (const profile of defaults.economic_profiles?.[phase] || template.profiles) {
        const wrapper = node('fieldset'), legend = node('legend'), chosen = node('input'); chosen.type = 'checkbox';
        chosen.id = prefix + profile.profile_id; chosen.checked = template.profiles.some(item => item.profile_id === profile.profile_id);
        const title = node('label', undefined, 'robust-source-choice'); title.append(chosen, node('span', profile.profile_id)); legend.append(title); wrapper.append(legend);
        wrapper.append(node('p', `Local rule version: ${profile.rule_version}. These are saved model rules, not newly verified provider terms.`));
        const fees = {};
        if (phase === 'evaluation') for (const [key, text] of [['evaluation_price', 'Evaluation fee · USD'], ['activation_fee', 'Activation fee · USD']]) {
          const input = field(wrapper, text, prefix + profile.profile_id + '-' + key, profile[key]); input.min = 0; input.step = '0.01'; fees[key] = input;
        }
        const sync = () => { Object.values(fees).forEach(input => { input.disabled = !chosen.checked; }); };
        chosen.onchange = () => { sync(); changed(); }; sync(); profiles.append(wrapper); profileInputs.push({profile, chosen, fees});
      }
      const quantities = field(fields, 'Fixed MNQ quantities to compare · comma-separated whole numbers', prefix + 'quantities', template.policies.map(policy => policy.micros).join(', '), 'text');
      fields.append(node('p', 'Requested quantities remain subject to the saved account size ceiling, phase size tiers and daily account rules.'));
      const selector = node('div', undefined, 'prop-fields'); fields.append(selector);
      let historical = null; const historicalInputs = {};
      const mode = select(selector, 'Predeclared selection rule', prefix + 'selector', phase === 'evaluation' ? [
        ['pareto_family', 'Keep the complete cost / time Pareto family'], ['min_cost_under_time_cap', 'Lowest expected cost within a time limit'],
        ['min_time_under_cost_cap', 'Shortest expected time within a cost limit']] : [
        ['maximum_expected_received_cash', 'Highest expected trader cash received'],
        ['conservative_expected_received_cash', 'Highest historical lower bound on expected trader cash']]);
      mode.value = template.selector.mode;
      const constraints = node('details'); constraints.append(node('summary', 'Selection limits and exact ties')); fields.append(constraints);
      const limits = node('div', undefined, 'prop-fields'); constraints.append(limits);
      const optional = new Map();
      const addLimit = (group, key, title, maximum) => {
        const box = node('div'), label = node('label', undefined, 'robust-source-choice'), toggle = node('input'); toggle.type = 'checkbox';
        toggle.id = prefix + 'enable-' + key; toggle.checked = template[group]?.[key] !== null && template[group]?.[key] !== undefined;
        const actual = group === 'constraints' ? template.search_settings?.constraints?.[key] : template[group]?.[key]; toggle.checked = actual !== null && actual !== undefined;
        label.append(toggle, node('span', title)); box.append(label);
        const input = field(box, title, prefix + key, actual ?? ''); input.step = key === 'maximum_position_size' ? '1' : 'any';
        if (key !== 'minimum_expected_cash') input.min = 0; if (maximum !== undefined) input.max = maximum;
        const sync = () => { input.disabled = !toggle.checked; input.required = toggle.checked; };
        toggle.onchange = () => { sync(); changed(); }; sync(); limits.append(box); optional.set(key, {group, toggle, input});
      };
      if (phase === 'evaluation') {
        addLimit('selector', 'maximum_cost_per_funded', 'Maximum expected acquisition cost · USD');
        addLimit('selector', 'maximum_expected_calendar_days', 'Maximum expected acquisition time · calendar days');
        addLimit('selector', 'minimum_pass_probability', 'Minimum pass probability · 0–1', 1);
      } else {
        addLimit('selector', 'minimum_expected_cash', 'Minimum selected expected-cash objective · USD');
        for (const [key, title, maximum] of [
          ['maximum_account_breach_probability', 'Maximum account breach probability · 0–1', 1],
          ['minimum_probability_first_payout', 'Minimum first payout probability · 0–1', 1],
          ['minimum_p10_payouts', 'Minimum P10 received cash · USD'], ['maximum_position_size', 'Maximum position size · MNQ', 40]]) addLimit('constraints', key, title, maximum);
      }
      const ties = select(constraints, 'Exact objective ties', prefix + 'ties', [['keep_all_exact_ties', 'Retain the complete tied family'], ['configuration_id', 'Choose the first by stable configuration ID']]);
      ties.value = template.selector.tie_policy;
      const syncSelector = () => {
        const pareto = mode.value === 'pareto_family'; ties.disabled = pareto; if (pareto) ties.value = 'keep_all_exact_ties';
        if (historical) { historical.disabled = mode.value !== 'conservative_expected_received_cash'; historical.hidden = historical.disabled; }
        const required = {min_cost_under_time_cap: 'maximum_expected_calendar_days', min_time_under_cost_cap: 'maximum_cost_per_funded'}[mode.value];
        for (const [key, setting] of optional) {
          setting.toggle.disabled = key === required;
          if (key === required) { setting.toggle.checked = true; setting.input.disabled = false; setting.input.required = true; constraints.open = true; }
        }
      };
      mode.onchange = () => { syncSelector(); changed(); }; syncSelector();
      const timing = node('div', undefined, 'prop-fields'); fields.append(timing);
      const advanced = node('details'); advanced.append(node('summary', 'Forecast sampling, seeds and model guards'));
      const sampling = node('div', undefined, 'prop-fields'); advanced.append(sampling); fields.append(advanced);
      const addInput = (container, group, key, title, minimum = 0) => {
        if (template[group]?.[key] === undefined || template[group][key] === null) return;
        const input = field(container, title, prefix + key, template[group][key]); input.min = minimum; input.step = '1'; inputs.push({group, key, input});
      };
      addInput(sampling, 'simulation', 'simulations', 'Forecast paths per candidate', 2);
      addInput(sampling, 'simulation', 'seed', 'Simulation seed');
      addInput(sampling, 'simulation', 'max_micros', 'Account size ceiling · MNQ', 1);
      addInput(sampling, 'sampling', 'block_weekdays', 'Resampling block · weekdays', 1);
      if (phase === 'evaluation') {
        addInput(timing, 'retry', 'retry_delay_calendar_days', 'Retry delay after failure · calendar days');
        addInput(timing, 'retry', 'activation_delay_sessions', 'Activation delay after pass · eligible sessions');
        addInput(sampling, 'sampling', 'chain_simulations', 'Acquisition forecast chains', 2);
        addInput(sampling, 'sampling', 'chain_seed', 'Acquisition seed');
        addInput(sampling, 'retry', 'max_attempts', 'Attempt guard · unresolved chains remain censored', 1);
        addInput(sampling, 'retry', 'max_calendar_days', 'Calendar-day guard · unresolved chains remain censored', 1);
      } else {
        addInput(timing, 'search_settings', 'horizon_calendar_days', 'Forecast receipt horizon · calendar days', 1);
        addInput(timing, 'search_settings', 'receipt_delay_calendar_days', 'Modeled receipt delay · calendar days');
        addInput(sampling, 'search_settings', 'bootstrap_replicates', 'Forecast uncertainty bootstrap repetitions', 100);
        addInput(sampling, 'search_settings', 'bootstrap_seed', 'Forecast uncertainty seed');
        fields.append(node('p', 'Receipt timing is a declared settlement assumption. Both the forecast and replay use unrounded modeled trader entitlement; no bank cent-rounding convention is inferred. Payout requests, account deductions, pending receipts and received cash remain separate.'));
        historical = node('fieldset'); historical.id = prefix + 'historical-mean'; historical.append(node('legend', 'Historical uncertainty of the expected cash mean'));
        historical.append(node('p', 'Resample historical session blocks, then estimate expected cash again. The lower empirical percentile is family-adjusted across the declared candidates. This is different from one-account payout P10 and from Monte Carlo standard error. Insufficient history, tail resolution or excessive simulation noise leaves the candidate unresolved.'));
        const historyFields = node('div', undefined, 'prop-fields'); historical.append(historyFields); fields.append(historical);
        const historicalLabels = {confidence_level: 'Nominal historical family confidence · 0.5–1', replicates: 'Historical resampling repetitions', block_sessions: 'Historical block · observed sessions',
          minimum_history_sessions: 'Minimum observed history sessions', minimum_history_blocks: 'Minimum historical blocks', simulations_per_replicate: 'Account paths per historical repetition',
          history_seed: 'Historical resampling seed', simulation_seed: 'Account simulation seed', maximum_mc_standard_error: 'Maximum Monte Carlo standard error · USD'};
        for (const [key, title] of Object.entries(historicalLabels)) {
          if (defaults.conservative_objective?.[key] === undefined) continue;
          const input = field(historyFields, title, prefix + 'historical-' + key, defaults.conservative_objective[key]);
          input.step = ['confidence_level', 'maximum_mc_standard_error'].includes(key) ? 'any' : '1'; input.min = 0;
          historicalInputs[key] = input;
        }
        syncSelector();
      }
      const calendar = node('details'); calendar.append(node('summary', 'Declared calendar and coverage'));
      const calendarFields = node('div', undefined, 'prop-fields'); calendar.append(calendarFields); fields.append(calendar);
      const calendarTemplate = template.search_settings?.calendar || {};
      const calendarVersion = field(calendarFields, 'Declared calendar version', prefix + 'calendar-version', calendarTemplate.version || '', 'text');
      const calendarTimezone = field(calendarFields, 'Calendar timezone · IANA name', prefix + 'calendar-timezone', calendarTemplate.timezone || '', 'text');
      const closures = field(calendarFields, 'Known closed session dates · YYYY-MM-DD, separated by commas', prefix + 'calendar-closures', (calendarTemplate.closures || []).join(', '), 'text'); closures.required = false;
      calendar.append(node('p', 'This is a saved calendar declaration. The weekday default has no official holiday verification. Missing expected open sessions block chronological replay; they are not filled with zero trades. Enter known closures before running.'));
      fields.append(node('p', 'Forecast scenario dates and chronological outer intervals are derived from each fold and saved in the preview. Source costs are retained without a second deduction.'));
      enabled.onchange = () => { fields.disabled = !enabled.checked; fields.hidden = !enabled.checked; changed(); };
      studies.push(() => {
        if (!enabled.checked) return null;
        const study = structuredClone(template);
        study.profiles = profileInputs.filter(item => item.chosen.checked).map(({profile, fees}) => ({...profile, ...Object.fromEntries(Object.entries(fees).map(([key, input]) => [key, input.value]))}));
        if (!study.profiles.length) throw Error(`Choose at least one ${phase} account profile.`);
        const values = quantities.value.split(',').map(value => value.trim());
        const maximum = phase === 'evaluation' ? 60 : 40;
        if (values.some(value => !/^\d+$/.test(value) || Number(value) < 1 || Number(value) > maximum)) throw Error(`${words(phase)} fixed quantities must be whole MNQ from 1 to ${maximum}.`);
        if (new Set(values.map(Number)).size !== values.length) throw Error(`${words(phase)} fixed quantities must be unique.`);
        study.policies = values.map(value => ({micros: Number(value)}));
        study.selector = {...study.selector, mode: mode.value, tie_policy: ties.value};
        for (const [key, setting] of optional) {
          const target = setting.group === 'constraints' ? (study.search_settings.constraints ||= {}) : study[setting.group];
          target[key] = setting.toggle.checked ? setting.group === 'selector' ? setting.input.value : Number(setting.input.value) : null;
        }
        for (const {group, key, input} of inputs) study[group][key] = Number(input.value);
        if (phase === 'funded') study.search_settings.conservative_objective = mode.value === 'conservative_expected_received_cash'
          ? {...defaults.conservative_objective, ...Object.fromEntries(Object.entries(historicalInputs).map(([key, input]) => [key, Number(input.value)]))} : null;
        const closedDates = closures.value.split(',').map(value => value.trim()).filter(Boolean);
        if (closedDates.some(value => !/^\d{4}-\d{2}-\d{2}$/.test(value))) throw Error('Use YYYY-MM-DD for each declared closed session date.');
        study.search_settings.calendar = {...calendarTemplate, version: calendarVersion.value.trim(), timezone: calendarTimezone.value.trim(), closures: closedDates};
        return study;
      });
    }
    return () => studies.map(read => read()).filter(Boolean);
  }
  function showEconomicSelection(parent, fold) {
    const selection = fold.economic_selection;
    if (!selection) return;
    const section = node('section', undefined, 'robust-economic-result'); section.id = `robust-economics-${fold.index}`;
    section.append(node('h3', 'Earlier economic forecasts and frozen choices'));
    section.append(node('p', `Selection status: ${selection.status || selection.membership?.status || 'Unavailable'}. ${selection.membership?.configuration_ids?.length ?? 0} qualified signal configurations enter each declared phase independently.`));
    if (!selection.phases?.length) {
      section.append(node('p', 'The procedure abstained before an economic policy was selected. No outer account outcome is fabricated.'));
      list(section, selection.reasons); parent.append(section); return;
    }
    for (const phase of selection.phases) {
      const study = node('section', undefined, 'robust-phase-evidence'); study.dataset.phase = phase.phase;
      const decision = phase.decision || {};
      study.append(node('h4', phaseLabel(phase.phase)), node('p', `Decision: ${decision.status || 'Unavailable'}. ${decision.selected_ids?.length || 0} frozen alternatives from ${phase.complete_search_candidate_count ?? 'unavailable'} complete declared economic candidates.`));
      if (decision.selector) study.append(node('p', selectionLabel(decision.selector)));
      if (decision.reason) study.append(node('p', reason(decision.reason)));
      if (decision.unresolved_ids?.length) study.append(node('p', `Unresolved candidates: ${decision.unresolved_ids.join(', ')}. The complete candidate family must resolve before selection.`));
      if (decision.excluded?.length) table(study, ['Candidate', 'Failed economic limits'], decision.excluded.map(item => [item.candidate_id, (item.constraints || []).map(words).join(', ')]));
      const forecasts = phase.training_forecasts || [], evaluation = phase.phase === 'evaluation';
      if (forecasts.length) {
        const forecastTable = table(study, ['Frozen candidate', 'Strategy and parameters', 'Profile / fixed MNQ',
          ...(evaluation ? ['Expected acquisition cost · USD', 'Expected acquisition time · calendar days', 'Pass probability · 0–1', 'MC standard error · cost / days']
            : ['Expected received cash · USD', 'P10 received cash · USD', 'Breach probability · 0–1', 'MC mean standard error · USD'])], forecasts.map(item => {
          const config = item.manifest.configuration, metrics = item.metrics || {}, uncertainty = item.uncertainty || {};
          const source = node('div', candidateLabel({strategy_id: item.manifest.strategy.id, parameters: item.manifest.strategy.parameters}));
          source.append(node('br'), link('Open training backtest', `#backtests/report/${config.source.source_backtest_id}`));
          return [item.candidate_id.slice(0, 12), source, `${config.profile.profile_id} / ${config.micros}`,
            ...(evaluation ? [metrics.cost_per_funded, metrics.expected_calendar_days_to_funded, metrics.pass_probability, `${valueText(uncertainty.cost_se)} / ${valueText(uncertainty.calendar_mean_se)}`]
              : [metrics.expected_payouts, metrics.p10_payouts, metrics.account_breach_probability, uncertainty.mean_monte_carlo_se])];
        })); forecastTable.classList.add('robust-training-forecasts');
        study.append(node('p', 'These are training forecasts. Monte Carlo standard error measures simulation precision conditional on the saved observations and model; it does not measure future uncertainty.'));
        const historical = forecasts.filter(item => item.uncertainty?.historical_mean);
        if (historical.length) {
          study.append(node('h4', 'Historical uncertainty of expected cash'));
          table(study, ['Frozen candidate', 'Historical evidence', 'Lower mean cash · USD', 'Observed history sessions / blocks', 'Declared family / lower tail rank', 'Maximum inner MC standard error · USD', 'Evidence limits'], historical.map(item => {
            const evidence = item.uncertainty.historical_mean;
            return [item.candidate_id.slice(0, 12), evidence.status, evidence.lower_mean_cash,
              `${valueText(evidence.history_session_count)} / ${valueText(evidence.history_block_count)}`, `${valueText(evidence.family_size)} / ${valueText(evidence.tail_rank)}`,
              evidence.mc_noise?.maximum_observed_standard_error, (evidence.reasons || []).map(reason).join('; ') || 'Saved evidence gates resolved'];
          }));
          study.append(node('p', 'The lower empirical percentile concerns the re-estimated expected-cash mean after historical block resampling. It is separate from account P10, conditional Monte Carlo error and future/model uncertainty. The declared family tail and evidence gates are retained in the complete phase report.'));
          if (phase.analysis_id) study.append(link('Download historical mean re-estimations', `/api/prop-analyses/${phase.analysis_id}/files/historical_mean_cash.json`), node('br'));
        }
      }
      if (phase.analysis_id) study.append(link('Open complete earlier phase forecast and candidate family', `#backtests/prop/job/${phase.analysis_id}`));
      if (phase.provider_rules) window.phaseCampaigns?.renderRuleReview(study, phase.provider_rules, phase.deployment_readiness, phase.analysis_id);
      for (const frozen of phase.frozen_packages || []) {
        const detail = node('details'); detail.className = 'robust-frozen-policy';
        detail.append(node('summary', `Frozen ${frozen.candidate_id.slice(0, 12)} · ${frozen.configuration.profile.profile_id} · ${frozen.configuration.micros} MNQ`));
        table(detail, ['Immutable selection evidence', 'Saved value'], [
          ['Strategy and parameters', candidateLabel({strategy_id: frozen.strategy.id, parameters: frozen.strategy.parameters})],
          ['Last training session', frozen.configuration.period?.last_session], ['Outer first session', frozen.outer_window.first_session],
          ['Outer cutoff · exclusive calendar date', frozen.outer_window.cutoff_date_exclusive], ['Frozen policy SHA-256', frozen.package_sha256],
          ...(phase.phase === 'funded' ? [['Receipt amount convention', frozen.receipt_amount_convention], ['Receipt delay · calendar days', frozen.receipt_delay_calendar_days]] : []),
          ['Training context SHA-256', frozen.training_context_sha256], ['Training report SHA-256', frozen.training_report_sha256],
          ['Selection seal SHA-256', selection.selection_seal_sha256]]);
        study.append(detail);
      }
      if (!decision.selected_ids?.length) study.append(node('p', 'This independent phase abstained. Another phase’s selection does not supply a replacement policy.'));
      if (decision.certification) study.append(node('p', decision.certification));
      section.append(study);
    }
    list(section, selection.limitations); parent.append(section);
  }
  function showBaselines(parent, fold) {
    if (!fold.baseline_results?.length) return;
    const section = node('section', undefined, 'robust-baseline-results');
    section.append(node('h3', 'Predeclared reference observations'));
    section.append(node('p', 'These simple references were declared before execution. Their original edge qualification is retained; a measured reference is not an admitted or recommended strategy.'));
    for (const reference of fold.baseline_results) {
      const detail = node('details'); detail.append(node('summary', `${reference.baseline_id} · ${words(reference.phase)} · ${reference.status}`));
      const package_ = reference.frozen_package, forecast = reference.training_forecast, metrics = forecast?.metrics || {};
      table(detail, ['Reference declaration', 'Saved value'], [
        ['Required reference', valueText(reference.required)], ['Original edge qualification', reference.edge_qualification?.status],
        ['Signal configuration', package_ ? candidateLabel({strategy_id: package_.strategy.id, parameters: package_.strategy.parameters}) : 'Unavailable'],
        ['Account profile / fixed MNQ', package_ ? `${package_.configuration.profile.profile_id} / ${package_.configuration.micros}` : 'Unavailable'],
        ['Recommendation eligible', 'No'], ['Reference seal SHA-256', reference.reference_seal_sha256], ['Frozen reference SHA-256', package_?.package_sha256]]);
      list(detail, (reference.edge_qualification?.reasons || []).map(reason));
      if (forecast) table(detail, ['Earlier reference forecast', 'Value'], reference.phase === 'funded'
        ? [['Expected received cash · USD', metrics.expected_payouts], ['P10 received cash · USD', metrics.p10_payouts], ['MC mean standard error · USD', forecast.uncertainty?.mean_monte_carlo_se]]
        : [['Expected acquisition cost · USD', metrics.cost_per_funded], ['Expected acquisition time · calendar days', metrics.expected_calendar_days_to_funded], ['Pass probability · 0–1', metrics.pass_probability]]);
      if (reference.analysis_id) detail.append(link('Open complete earlier reference forecast', `#backtests/prop/job/${reference.analysis_id}`), node('br'));
      if (reference.outer_run_id) detail.append(link('Open ordinary reference outer backtest', `#backtests/report/${reference.outer_run_id}`));
      if (reference.chronological_replay) showChronologicalReplay(detail, reference.chronological_replay);
      section.append(detail);
    }
    parent.append(section);
  }
  function showReliability(parent, reliability) {
    if (!reliability) return;
    const section = node('section', undefined, 'robust-reliability-result'); section.id = 'robust-reliability-result';
    section.append(node('h3', 'Consolidated outer evidence'), node('p', `Historical evidence status: ${reliability.status}. Production qualified: no.`));
    section.append(node('p', 'The changing selection procedure is evaluated across the declared outer folds. Each fold counts once. Complete selected families remain alternative policies; no implicit allocation or best outer winner is created.'));
    const declared = node('details'); declared.append(node('summary', 'Saved reliability requirements'));
    table(declared, ['Declared requirement', 'Saved value'], Object.entries(reliability.settings || {}).map(([key, value]) => [words(key), valueText(value)])); section.append(declared);
    for (const [phaseName, phase] of Object.entries(reliability.phases || {})) {
      const study = node('section', undefined, 'robust-reliability-phase'); study.dataset.phase = phaseName;
      const funded = phaseName === 'funded', coverage = phase.coverage || {}, scalar = phase.scalar_metrics || {};
      study.append(node('h4', phaseLabel(phaseName)), node('p', `Evidence: ${phase.status}. ${coverage.declared_outer_folds} declared outer folds; ${reliability.settings.minimum_outer_blocks} required by the saved evidence threshold.`));
      list(study, (phase.reasons || []).map(reason));
      table(study, ['Coverage', 'Observed'], [
        ['Completed folds / declared folds', `${coverage.completed_outer_folds} / ${coverage.declared_outer_folds}`],
        ['Folds with a unique measurable action', coverage.scalar_eligible_folds], ['Folds retaining policy families', coverage.selected_family_folds],
        ['Abstained folds', coverage.abstained_folds], ['Folds without a unique measured procedure action', coverage.unmeasured_folds],
        ['Complete-action fraction', coverage.complete_fold_fraction], ['Historical outer blocks with selected replay', coverage.historical_outer_blocks],
        ['Unique outer sessions', coverage.unique_outer_sessions], ['Independently established block count', valueText(coverage.independent_block_count)]]);
      table(study, ['Outer fold / observed sessions', 'Declared procedure action', 'Frozen alternatives', 'Scalar eligible', 'Earlier expected cash / acquisition cost · USD', 'Observed received cash / paid fees · USD'], (phase.folds || []).map(row => {
        const range = key => row.members.length ? row.members.map(member => valueText(member[key])).join(' / ') : row.action === 'no_account_no_fee' ? '0 · declared no account' : 'Unmeasured';
        const forecast = row.members.length ? row.members.map(member => valueText(funded ? member.expected_cash_received : member.forecast_metrics.cost_per_funded)).join(' / ') : 'No forecast';
        return [`${row.outer_fold} · ${period(row.window)}`, words(row.action), row.family_size, valueText(row.scalar_eligible), forecast,
          range(funded ? 'cash_received' : 'paid_fees')];
      }), `robust-reliability-folds-${phaseName}`);
      if (coverage.selected_family_folds) study.append(node('p', 'Family ambiguity: multiple frozen alternatives have no predeclared unique action. Scalar averages, calibration and paired superiority are unavailable; alternatives are not additional folds.'));
      const details = node('details'); details.append(node('summary', 'All retained fold members and comparability'));
      table(details, ['Fold', 'Frozen candidate', 'Strategy / profile / MNQ', 'Earlier forecast · USD', 'Historical observation · USD', 'Forecast error · USD', 'Comparability'], (phase.folds || []).flatMap(row => row.members.map(member => {
        const definition = member.logical_policy.definition, policy = definition.sizing;
        return [row.outer_fold, member.candidate_id.slice(0, 12), `${candidateLabel({strategy_id: definition.strategy.id, parameters: definition.strategy.parameters})} / ${member.profile.profile_id} / ${policy.micros}`,
          funded ? member.expected_cash_received : member.forecast_metrics.cost_per_funded,
          funded ? member.cash_received : member.paid_fees, member.forecast_error,
          (member.comparability_reasons || []).map(reason).join('; ') || (funded ? 'Same saved receipt estimand' : member.acquisition_comparability)];
      }))); study.append(details);
      table(study, ['Whole-procedure scalar measure', 'Value'], [
        ['Scalar availability', scalar.status], ['Declared denominator · outer folds', scalar.denominator_outer_folds],
        ...(funded ? [['Mean received cash · USD / declared fold', scalar.mean_cash_received], ['Total observed received cash · USD', scalar.total_observed_cash_received], ['Observed pending cash · USD', scalar.observed_pending_cash]]
          : [['Mean completed acquisition cost · USD', scalar.mean_acquisition_cost], ['Mean completed acquisition time · calendar days', scalar.mean_calendar_days_to_funded], ['All observed paid fees · USD', scalar.total_observed_paid_fees], ['Completed acquisitions', scalar.completed_acquisitions], ['Censored acquisitions', scalar.censored_acquisitions]])]);
      if (scalar.interpretation) study.append(node('p', scalar.interpretation));
      if (scalar.historical_interval) intervalEvidence(study, 'Historical fold-output interval for mean received cash', scalar.historical_interval);
      const errors = phase.forecast_errors || {}, calibration = phase.calibration || {};
      const forecastDetail = node('details'); forecastDetail.append(node('summary', 'Forecast versus actual and payout calibration'));
      table(forecastDetail, ['Diagnostic', 'Saved observation'], [
        ['Error availability', errors.status], ['Comparable unique-policy folds', errors.paired_fold_count], ['Mean actual minus forecast · USD', errors.mean_error],
        ['Mean absolute error · USD', errors.mean_absolute_error], ['Root mean squared error · USD', errors.root_mean_squared_error],
        ['Payout calibration evidence', calibration.status], ['Observed probability pairs / required blocks', `${calibration.historical_block_count} / ${calibration.minimum_blocks}`],
        ['Brier score · descriptive', calibration.brier_score], ['Observed receipt frequency · descriptive', calibration.observed_rate], ['Mean predicted receipt probability · descriptive', calibration.predicted_rate]]);
      forecastDetail.append(node('p', calibration.reason));
      if (errors.historical_interval) intervalEvidence(forecastDetail, 'Historical interval for forecast errors', errors.historical_interval);
      study.append(forecastDetail);
      const stability = phase.stability || {}, changes = node('details'); changes.append(node('summary', `Policy stability · ${stability.distinct_policies ?? 'unknown'} distinct logical policies`));
      table(changes, ['Fold transition', 'Family overlap · Jaccard', 'Signal changed', 'Sizing changed', 'Profile changed'], (stability.transitions || []).map(row => [
        `${row.from_fold} → ${row.to_fold}`, row.family_jaccard, valueText(row.signal_changed), valueText(row.sizing_changed), valueText(row.profile_changed)]));
      changes.append(node('p', stability.interpretation)); study.append(changes);
      const comparisons = node('section', undefined, 'robust-baseline-comparisons'); comparisons.append(node('h4', 'Paired simple-reference comparisons'));
      if (!phase.baseline_comparisons?.length) comparisons.append(node('p', 'No baseline was predeclared for this phase. There is no saved baseline comparison or evidence of improvement over a simple alternative.'));
      for (const comparison of phase.baseline_comparisons || []) {
        comparisons.append(node('h5', comparison.baseline_id), node('p', `${comparison.decision} · ${comparison.paired_outer_folds} paired of ${comparison.declared_outer_folds} declared folds · ${comparison.required ? 'required' : 'optional'} reference.`));
        table(comparisons, ['Paired comparison', 'Value'], [['Mean improvement · USD', comparison.paired_mean_improvement], ['Declared minimum mean improvement · USD', comparison.minimum_mean_improvement], ['Metric', words(comparison.metric)]]);
        table(comparisons, ['Outer fold', funded ? 'Selected received cash · USD' : 'Selected paid fees · USD', funded ? 'Reference received cash · USD' : 'Reference paid fees · USD', 'Improvement · USD', ...(funded ? [] : ['Calendar days saved'])], comparison.pairs.map(row => [row.outer_fold, row.selected, row.baseline, row.improvement, ...(funded ? [] : [row.calendar_days_improvement])]), `robust-baseline-pairs-${phaseName}-${comparison.baseline_id.replace(/[^a-z0-9]+/gi, '-')}`);
        list(comparisons, comparison.exclusions.map(row => `Fold ${row.outer_fold}: ${reason(row.reason)}`));
        intervalEvidence(comparisons, 'Paired historical fold interval', comparison.historical_interval);
        comparisons.append(node('p', comparison.interpretation));
      }
      study.append(comparisons); section.append(study);
    }
    table(section, ['Uncertainty component', 'Interpretation'], Object.entries(reliability.uncertainty_components || {}).map(([key, value]) => [words(key), value]));
    list(section, reliability.limitations); parent.append(section);
  }
  function intervalEvidence(parent, title, evidence) {
    if (!evidence) return;
    parent.append(node('p', `${title}: ${evidence.status}. ${evidence.interval ? `${evidence.interval[0]} to ${evidence.interval[1]} USD` : 'Interval unavailable'}. ${evidence.observed_outer_blocks ?? 0} observed outer blocks.`));
    if (evidence.reason || evidence.interpretation) parent.append(node('p', evidence.reason || evidence.interpretation));
  }
  function baselineControls(parent, defaults, changed) {
    const section = node('details'); section.id = 'robust-baselines-configure';
    section.append(node('summary', '7. Predeclared simple baselines'));
    section.append(node('p', 'Preview the saved strategy configurations, then choose reference policies before running. References use a declared configuration and the matching phase study’s profile, costs, calendar and receipt assumptions. A reference may fail edge qualification; it remains a comparison, never an admitted optimized policy.'));
    const notice = node('p', 'Preview source configurations to add a reference.'), rows = node('div'), actions = node('div', undefined, 'robust-actions');
    const add = button(actions, 'Add simple baseline', 'robust-baseline-add'), refresh = button(actions, 'Refresh reference choices', 'robust-baseline-refresh'); add.disabled = true;
    section.append(notice, rows, actions); parent.append(section);
    let plan = null, serial = 0;
    const references = new Map(), encodedProfile = profile => JSON.stringify(profile, Object.keys(profile).sort());
    function options(input, choices, initial = false) {
      const previous = input.value; input.replaceChildren();
      for (const [value, title] of choices) { const option = node('option', title); option.value = value; input.append(option); }
      if (choices.some(([value]) => value === previous)) { input.value = previous; input.dataset.unavailable = 'false'; }
      else if (!initial && (previous || input.dataset.unavailable === 'true')) { const missing = node('option', 'Previous selection is unavailable; choose again'); missing.value = ''; input.prepend(missing); input.value = ''; input.dataset.unavailable = 'true'; }
      else if (!choices.length) { const empty = node('option', 'Enable a phase study and refresh choices'); empty.value = ''; input.append(empty); }
    }
    function profiles(row, initial = false) {
      const study = plan?.economic_studies?.find(study => study.phase === row.phase.value);
      options(row.profile, (study?.profiles || []).map(profile => [encodedProfile(profile), `${profile.profile_id} · ${profile.rule_version}${row.phase.value === 'evaluation' ? ` · fees $${profile.evaluation_price} + $${profile.activation_fee}` : ''}`]), initial);
    }
    function updateRow(row, initial = false) {
      options(row.source, (plan?.candidates || []).map(candidate => [candidate.id, candidateLabel(candidate)]), initial);
      options(row.phase, (plan?.economic_studies || []).map(study => [study.phase, phaseLabel(study.phase)]), initial);
      profiles(row, initial);
    }
    add.onclick = () => {
      if (!plan) return;
      const number = ++serial, entry = node('fieldset'); entry.append(node('legend', `Reference ${number}`));
      const grid = node('div', undefined, 'prop-fields'); entry.append(grid); rows.append(entry);
      const prefix = `robust-baseline-${number}-`;
      const id = field(grid, 'Readable reference ID · unique within this research', prefix + 'id', `${defaults.baseline?.id || 'One MNQ reference'}${number > 1 ? ` ${number}` : ''}`, 'text'); id.maxLength = 120; id.required = false;
      const phase = select(grid, 'Independent phase', prefix + 'phase', []), source = select(grid, 'Declared signal configuration', prefix + 'source', []);
      const profile = select(grid, 'Declared phase profile', prefix + 'profile', []), quantity = field(grid, 'Fixed MNQ quantity', prefix + 'micros', defaults.baseline?.policy?.micros || 1); quantity.min = 1; quantity.max = 60; quantity.step = 1;
      const label = node('label', undefined, 'robust-source-choice'), required = node('input'); required.type = 'checkbox'; required.id = prefix + 'required'; required.checked = defaults.baseline?.required !== false;
      label.append(required, node('span', 'Required reference · missing evidence blocks a supported comparison')); entry.append(label);
      entry.append(node('p', 'Fixed quantities may be outside the optimizer quantity grid. Native dollar-risk or state-dependent references require a strategy rerun and are currently unavailable.'));
      const row = {id, phase, source, profile, quantity, required}; references.set(number, row); updateRow(row, true);
      phase.onchange = () => { profiles(row, true); changed(); }; required.onchange = changed;
      button(entry, 'Remove reference', prefix + 'remove').onclick = () => { references.delete(number); entry.remove(); changed(); };
      changed();
    };
    return {
      refresh,
      update(next) {
        plan = next; add.disabled = !plan.candidates?.length || !plan.economic_studies?.length;
        notice.textContent = add.disabled ? 'Enable an independent economic study and preview its source configurations to add a reference.'
          : `${plan.candidates.length} declared signal configurations are available. Reference edits require a new full preview before saving.`;
        for (const row of references.values()) updateRow(row);
      },
      read() {
        const result = [];
        for (const row of references.values()) {
          const id = row.id.value.trim(), micros = Number(row.quantity.value);
          if (!id || !row.source.value || !row.phase.value || !row.profile.value) throw Error('Complete each baseline ID, signal configuration, phase and profile. Refresh reference choices after changing sources or studies.');
          if (!Number.isInteger(micros) || micros < 1 || micros > (row.phase.value === 'evaluation' ? 60 : 40)) throw Error('Baseline quantities must be supported whole MNQ counts.');
          result.push({id, phase: row.phase.value, source_configuration_id: row.source.value, profile: JSON.parse(row.profile.value), policy: {micros}, required: row.required.checked});
        }
        if (new Set(result.map(row => row.id)).size !== result.length) throw Error('Each baseline needs a unique readable reference ID.');
        return result;
      },
    };
  }
  function reliabilityControls(parent, defaults) {
    const section = node('details'); section.id = 'robust-reliability-configure';
    section.append(node('summary', '8. Outer reliability · declared evidence requirements'));
    section.append(node('p', 'These requirements apply when economic studies are enabled. They are user-declared evidence limits, not universal statistical certification. Each outer fold is one unit; tied policies are alternatives and do not create additional independent observations.'));
    const grid = node('div', undefined, 'prop-fields'); section.append(grid); parent.append(section);
    const inputs = {}, labels = {
      minimum_outer_blocks: 'Minimum outer blocks', minimum_complete_fold_fraction: 'Required complete fold fraction · 0–1', confidence_level: 'Historical confidence level · 0–1',
      bootstrap_block_folds: 'Historical resampling block · outer folds', historical_bootstrap_replicates: 'Historical bootstrap repetitions', historical_bootstrap_seed: 'Historical bootstrap seed',
      minimum_calibration_blocks: 'Minimum blocks for payout-probability calibration', minimum_baseline_mean_improvement: 'Required mean improvement over a baseline · USD',
    };
    for (const [key, label] of Object.entries(labels)) {
      if (defaults.reliability?.[key] === undefined) continue;
      const input = field(grid, label, `robust-reliability-${key}`, defaults.reliability[key]); input.step = ['minimum_complete_fold_fraction', 'confidence_level', 'minimum_baseline_mean_improvement'].includes(key) ? 'any' : '1';
      if (key !== 'minimum_baseline_mean_improvement') input.min = 0;
      if (['minimum_complete_fold_fraction', 'confidence_level'].includes(key)) input.max = 1;
      inputs[key] = input;
    }
    const action = select(section, 'Predeclared action when no policy is selected', 'robust-reliability-abstention_action', [
      ['unmeasured', 'Unmeasured · do not assign a cash outcome'], ['no_account_no_fee', 'No account and no fee · explicitly zero cash']]);
    action.value = defaults.reliability?.abstention_action || 'unmeasured';
    const label = node('label', undefined, 'robust-source-choice'), required = node('input'); required.type = 'checkbox'; required.id = 'robust-reliability-require_baseline_for_recommendation'; required.checked = defaults.reliability?.require_baseline_for_recommendation !== false;
    label.append(required, node('span', 'Require baseline evidence before a future recommendation can be supported')); section.append(label);
    section.append(node('p', 'This increment assesses historical evidence only. Final holdout and deployment recommendation controls are not available. Monte Carlo precision, historical sampling uncertainty, and model/rule/execution uncertainty remain separate.'));
    return () => ({...defaults.reliability, ...Object.fromEntries(Object.entries(inputs).map(([key, input]) => [key, key === 'minimum_baseline_mean_improvement' ? input.value : Number(input.value)])),
      abstention_action: action.value, require_baseline_for_recommendation: required.checked});
  }
  function showChronologicalFamily(parent, fold) {
    const chronological = fold.chronological_replay;
    if (!chronological) return;
    const section = node('section', undefined, 'robust-outer-evidence');
    section.append(node('h3', 'Frozen-policy outer observations'), node('p', `Chronological execution: ${chronological.status}.`));
    if (chronological.interpretation) section.append(node('p', chronological.interpretation));
    if (!chronological.items?.length) {
      section.append(node('p', 'No frozen policy was replayed. An abstention has no fabricated fees, account, payout or performance observation.'));
      parent.append(section); return;
    }
    const frozen = new Map((fold.economic_selection?.phases || []).flatMap(phase => (phase.frozen_packages || []).map(item => [item.candidate_id, item])));
    table(section, ['Independent phase / frozen candidate', 'Profile / fixed MNQ', 'Historical outcome', 'Paid acquisition fees · USD', 'Received cash · USD', 'Pending receipts / activation · USD'], chronological.items.map(item => {
      const policy = frozen.get(item.candidate_id), result = item.result;
      return [`${words(item.phase)} / ${item.candidate_id.slice(0, 12)}`, policy ? `${policy.configuration.profile.profile_id} / ${policy.configuration.micros}` : 'Unavailable',
        result.outcome, item.phase === 'evaluation' ? result.paid_fees : 'Not part of this phase',
        item.phase === 'funded' ? result.cash_received : 'Not part of this phase', item.phase === 'funded' ? result.pending_cash : result.pending_activation];
    }), `robust-outer-summary-${fold.index}`);
    chronological.items.forEach((item, index) => {
      const detail = node('details'); detail.className = 'robust-outer-policy'; detail.open = index === 0;
      detail.dataset.phase = item.phase; detail.dataset.candidateId = item.candidate_id;
      detail.append(node('summary', `${words(item.phase)} · frozen ${item.candidate_id.slice(0, 12)} · ${item.result.outcome || 'observation'}`));
      detail.append(link('Open ordinary outer backtest', `#backtests/report/${item.outer_run_id}`));
      const identity = node('details'); identity.append(node('summary', 'Frozen-to-outer evidence identity'));
      table(identity, ['Evidence', 'Saved SHA-256'], [['Frozen policy', item.frozen_package_sha256], ['Selection seal', chronological.selection_seal_sha256],
        ['Replay input manifest', item.result.input_manifest_sha256], ['Chronological source book', item.result.source_book_sha256]]); detail.append(identity);
      showChronologicalReplay(detail, item.result); section.append(detail);
    });
    parent.append(section);
  }
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
    if (plan.economic_plan?.enabled) {
      const economic = plan.economic_plan;
      parent.append(node('h4', 'Predeclared independent economic studies'));
      parent.append(node('p', `Work before qualification is known: up to ${economic.estimated_training_backtests} training backtests and ${economic.estimated_outer_backtests} outer backtests, included in the total. Up to ${economic.maximum_phase_candidates} phase forecasts, including any declared references, enter the saved procedure; optimized membership uses all qualified configurations.`));
      table(parent, ['Independent phase', 'Profiles', 'Fixed policies', 'Maximum candidates per fold', 'Saved selection rule'], economic.studies.map(study => [
        phaseLabel(study.phase), study.profile_count, study.policy_count, study.max_candidates_per_fold, selectionLabel(study.selector)]), 'robust-economic-plan');
      if (economic.resolved_folds?.length) table(parent, ['Outer fold / phase', 'Forecast start', 'Outer cutoff · exclusive', 'Forecast horizon · calendar days', 'Calendar version / timezone', 'Declared closures'], economic.resolved_folds.map(item => [
        `${item.outer_fold_index} / ${words(item.phase)}`, valueText(item.calendar.start_dates), item.cutoff_date_exclusive,
        item.horizon_calendar_days ?? 'Evaluation acquisition guard', `${item.calendar.version} / ${item.calendar.timezone}`, valueText(item.calendar.closures)]), 'robust-economic-dates');
      for (const study of plan.economic_studies || []) showStudy(parent, study);
      if (economic.baseline_count) parent.append(node('p', `${economic.baseline_count} predeclared simple references add up to ${economic.estimated_baseline_training_backtests} training and ${economic.estimated_baseline_outer_backtests} outer backtests, already included in the work total. They are evaluated separately from optimized policy membership.`));
      if (economic.maximum_historical_refits) parent.append(node('p', `Conservative expected-cash work: up to ${economic.maximum_historical_refits} historical re-estimations, ${economic.maximum_historical_inner_paths} account paths and ${economic.maximum_historical_path_calendar_days} path calendar-days. These computational repetitions do not add independent historical evidence.`));
      list(parent, economic.limitations);
    }
    if (plan.baselines?.length) {
      const candidates = new Map(plan.candidates.map(candidate => [candidate.id, candidate]));
      table(parent, ['Predeclared reference', 'Phase', 'Signal configuration', 'Profile / fixed MNQ', 'Required'], plan.baselines.map(reference => [
        reference.id, words(reference.phase), candidateLabel(candidates.get(reference.source_configuration_id) || {}),
        `${reference.profile.profile_id} / ${reference.policy.micros}`, reference.required ? 'Yes' : 'No']), 'robust-baseline-plan');
    }
    if (plan.reliability) {
      const settings = node('details'); settings.append(node('summary', 'Saved outer reliability requirements'));
      table(settings, ['Requirement', 'Declared value'], Object.entries(plan.reliability).map(([key, value]) => [words(key), valueText(value)])); parent.append(settings);
    }
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
    parent.append(node('p', plan.economic_plan?.enabled
      ? 'Qualification → independent training forecasts → saved frozen family → chronological outer strategy execution and account replay. No qualified or feasible policy means abstention. Historical evidence does not authorize deployment.'
      : 'This increment runs inner qualification only. The outer periods remain reserved; economic selection, outer replay and deployment recommendation are pending.', 'robust-notice'));
  }
  function showResult(parent, record, includeDownloads = true) {
    const result = record.result;
    const economic = record.declaration.economic_studies?.length > 0;
    parent.replaceChildren(node('h3', `${record.declaration.name} · ${economic ? 'qualification and economic evidence' : 'inner qualification evidence'}`));
    parent.append(node('p', economic
      ? 'Qualification, earlier economic forecasts and frozen-policy chronological observations are separate evidence. Each phase retains its own objective; no outer result selects a new winner or authorizes deployment.'
      : 'These are chronological inner-validation results within each outer training period. They are not unseen outer outcomes or a deployment recommendation.', 'robust-notice'));
    if (!result) { parent.append(node('p', 'The saved result is not yet available.')); return; }
    const requirements = node('details'); requirements.append(node('summary', 'Saved qualification requirements'));
    table(requirements, ['Requirement', 'Saved value'], Object.entries(record.declaration.qualification).map(([key, value]) => [words(key), Array.isArray(value) ? value.join(', ') || 'None declared' : value === null ? 'Not imposed' : value]));
    parent.append(requirements);
    for (const study of record.declaration.economic_studies || []) showStudy(parent, study);
    showReliability(parent, result.reliability);
    if (economic && result.event_journal?.length) {
      const journal = node('details'); journal.id = 'robust-research-journal'; journal.append(node('summary', 'Ordered evidence: frozen selection before outer strategy execution'));
      journal.append(node('p', 'The saved sequence records the selection seal before the corresponding outer-access reservation and strategy execution. Inventory inspection and previous source access may already have occurred; this does not certify untouched data.'));
      if (record.declaration.baselines?.length) journal.append(node('p', 'Both the complete selected-family seal and the predeclared reference seal must precede every selected or reference outer execution.'));
      table(journal, ['Saved sequence', 'Event', 'Step', 'Recorded time · UTC', 'Selection / reference seal SHA-256', 'Frozen policy SHA-256'], result.event_journal.map(event => [
        event.sequence, event.kind === 'selection_seal' ? 'Frozen selection sealed' : event.kind === 'baseline_seal' ? 'Predeclared references sealed' : event.access_role === 'baseline_outer_test' ? 'Reference outer access reserved' : 'Outer access reserved before strategy execution', event.step_key,
        valueText(event.created_at), event.selection_seal_sha256 || event.reference_seal_sha256, valueText(event.frozen_package_sha256)]), 'robust-event-journal');
      parent.append(journal);
    }
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
      showEconomicSelection(section, fold);
      showChronologicalFamily(section, fold);
      showBaselines(section, fold);
      parent.append(section);
    }
    parent.append(node('h3', 'Next decision'));
    list(parent, result.readiness?.reasons || ['Outer economic replay and deployment validation are pending.']);
    parent.append(node('p', `Readiness: ${result.readiness?.status || 'INCOMPLETE'}. No deployment policy is recommended by this increment.`));
    if (includeDownloads) {
      const downloads = node('div', undefined, 'robust-actions');
      for (const file of ['report.json', 'analysis.zip', 'qualification.csv', ...(economic ? ['economic_selection.json', 'chronological_replay.json', 'research_journal.json'] : []), ...(result.reliability ? ['baseline_results.json', 'reliability.json', 'reliability_folds.csv', 'baseline_comparison.csv'] : [])]) downloads.append(link(`Download ${file}`, `${base}/${record.campaign_id}/exports/${file}`));
      parent.append(downloads);
    }
    if (record.analysis_id) parent.append(link('Open the saved analysis report', `#backtests/prop/job/${record.analysis_id}`));
  }
  function renderAnalysis(report) {
    const record = {campaign_id: report.request.campaign_id, declaration: report.request, plan: report.plan, result: report.calculations};
    document.querySelector('#prop-config').hidden = true;
    document.querySelector('#prop-report').hidden = false;
    const economic = report.request.economic_studies?.length > 0;
    document.querySelector('#prop-heading-title').textContent = economic ? 'Nested research · economic validation' : 'Nested research · inner qualification';
    document.querySelector('#prop-heading-note').textContent = economic ? 'Earlier forecasts, frozen families and chronological outer observations' : 'Saved chronological inner evidence · outer economic validation pending';
    document.querySelector('#prop-back').href = `#backtests/prop/new/${report.request.source_backtest_id}`;
    document.querySelector('#prop-back').textContent = '← Back to research configuration';
    const content = document.querySelector('#prop-report-content'); content.replaceChildren();
    const plan = node('section', undefined, 'panel prop-panel'), results = node('section', undefined, 'panel prop-panel');
    content.append(plan, results); showPlan(plan, report.plan); showResult(results, record, false);
    const downloads = node('div', undefined, 'robust-actions');
    for (const [name, path] of [['Report JSON', 'downloads/report.json'], ['Analysis ZIP', 'downloads/analysis.zip'], ['Qualification CSV', 'files/qualification.csv']]) downloads.append(link(name, `/api/prop-analyses/${report.id}/${path}`));
    if (economic) for (const file of ['economic_selection.json', 'chronological_replay.json', 'research_journal.json']) downloads.append(link(`Download ${file}`, `/api/prop-analyses/${report.id}/files/${file}`));
    if (report.calculations.reliability) for (const file of ['baseline_results.json', 'reliability.json', 'reliability_folds.csv', 'baseline_comparison.csv']) downloads.append(link(`Download ${file}`, `/api/prop-analyses/${report.id}/files/${file}`));
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
    const readEconomicStudies = economicControls(form, defaults, invalidate);
    const baselines = baselineControls(form, defaults, invalidate);
    const readReliability = reliabilityControls(form, defaults);
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
    function body(includeBaselines = true) {
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
      const economic_studies = readEconomicStudies();
      return {campaign_id: crypto.randomUUID().replaceAll('-', ''), name: name.value.trim(), source_backtest_id: source.id,
        sources: [...selected.values()].map(entry => ({[entry.kind]: entry.id, sizes: [1]})),
        folds: {...Object.fromEntries(Object.entries(foldInputs).map(([key, input]) => [key, Number(input.value)])), mode: mode.value}, qualification,
        execution_scenarios, regimes, economic_studies, baselines: includeBaselines ? baselines.read() : [],
        reliability: economic_studies.length ? readReliability() : null};
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
    async function inspect(includeBaselines = true) {
      if (busy || (includeBaselines && !form.reportValidity())) return;
      busy = true; preview.disabled = true; run.disabled = true; const versionAtCheck = revision;
      status.textContent = 'Checking sources and deriving session boundaries…';
      try {
        const request = body(includeBaselines), plan = await api(`${base}/preview`, request);
        if (!current() || revision !== versionAtCheck) return;
        baselines.update(plan); showPlan(planView, plan);
        if (!includeBaselines) {
          checked = null; status.textContent = 'Reference choices refreshed. Complete the baseline definitions, then preview the full research plan before saving.'; return;
        }
        checked = {...request, confirmed_backtest_count: plan.estimated_backtests,
          confirmed_economic_candidate_count: plan.economic_plan?.maximum_phase_candidates || null}; run.disabled = false;
        run.textContent = request.economic_studies.length ? `Save and run research · up to ${plan.estimated_backtests} backtests` : `Save and run ${plan.estimated_backtests} inner backtests`;
        status.textContent = request.economic_studies.length ? 'Source checks passed. Review the dates, phase membership and frozen selection procedure, then run.' : 'Source checks passed. Review the dates and qualification requirements, then run.';
      } catch (error) { if (current()) status.textContent = `Plan needs attention: ${error.message}`; }
      finally { busy = false; if (current()) preview.disabled = false; }
    }
    preview.onclick = () => inspect();
    baselines.refresh.onclick = () => inspect(false);
    run.onclick = async () => {
      if (busy || !checked) return;
      if (checked.confirmed_economic_candidate_count > 128 && !window.confirm(`Run all ${checked.confirmed_economic_candidate_count} predeclared phase candidates across the folds? This includes up to ${checked.confirmed_backtest_count} native backtest tasks. Qualification may reduce subsequent work; no candidates will be silently removed.`)) {
        status.textContent = 'Large research run was not confirmed. The preview remains available; no campaign was saved.'; return;
      }
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
