"use strict";
(() => {
  const get = id => document.getElementById('prop-desk-' + id);
  const form = get('form');
  const source = get('source');
  const phase = get('phase');
  const profile = get('profile');
  const minimum = get('minimum');
  const maximum = get('maximum');
  const horizon = get('horizon');
  const inputs = get('inputs');
  const checkStatus = get('check-status');
  const launch = get('launch');
  const history = get('history');
  const result = get('result');
  const optimise = get('optimise');
  const minimumMembers = get('min-members');
  const fundedSizeRule = get('funded-size-rule');
  const pageSize = 30;
  let searchView = false;
  let automaticMinimum = true;
  const optimizing = () => searchView;
  const basket = window.propDeskBasket.setup(get, optimizing, updateSelection);
  let defaults, defaultHorizon, sourceOffset, historyOffset, generation = 0, polling;
  const phaseButtons = form.querySelectorAll('[data-desk-phase]');
  const simulationSizeRule = get('simulation-size-rule');
  const horizonShortcuts = get('horizon-shortcuts');
  const automaticSize = () => Boolean(simulationSizeRule.value && simulationSizeRule.value !== 'manual');
  const compareOosAccounts = terms => get('include-oos-accounts').checked &&
    terms.members.some(member => member.oos_backtest_id);

  const node = (tag, content, cls) => {
    const element = document.createElement(tag);
    if (content !== undefined) element.textContent = content;
    if (cls) element.className = cls;
    return element;
  };
  const link = (label, href) => {
    const element = node('a', label);
    element.href = href;
    return element;
  };
  const title = value => value === 'evaluation' ? 'Evaluation' : 'Funded';
  const human = value => (value || '').replaceAll('_', ' ');
  const money = value => Number(value).toLocaleString('en-US', {style:'currency', currency:'USD'});
  const percent = value => value.toLocaleString('en-US', {style:'percent', maximumFractionDigits:1});
  const units = value => value == null ? '—' : Number(value).toLocaleString('en-US');
  const runUrl = id => '#prop-desk?analysis=' + id;
  const optimiseUrl = '#prop-desk?view=optimise';

  function isFixed(terms) {
    return !optimizing() && !automaticSize() && terms.members.length === 1 && !terms.members[0].oos_backtest_id
      && maximum.value === '' && !maximum.validity.badInput;
  }

  async function request(path, body) {
    const response = await fetch(path, body === undefined ? undefined : {
      method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify(body),
    });
    const data = await response.json();
    if (!response.ok) {
      const detail = data.detail;
      throw new Error(typeof detail === 'string' ? detail : detail?.[0]?.msg || 'Prop Desk request failed.');
    }
    return data;
  }

  function enableForm() {
    inputs.disabled = !defaults || source.options.length < 2;
    updateRunButton();
  }

  function updateRunButton() {
    const terms = basket.configuration();
    launch.disabled = optimizing() ? !updateWorkload(terms) : !terms.members.length;
  }

  function updateWorkload({members, minimum_micros, maximum_micros}) {
    const message = get('workload');
    const min = minimumMembers.valueAsNumber;
    const max = members.length;
    const days = horizon.valueAsNumber;
    if (!(1 <= min && min <= max && Number.isInteger(min))) {
      message.textContent = 'Add strategies to meet the minimum.';
      return false;
    }
    if (!(minimum_micros >= 1 && Number.isInteger(minimum_micros) &&
          Number.isInteger(maximum_micros) && maximum_micros >= minimum_micros && days >= 1)) {
      message.textContent = 'Set a valid MNQ range and observation horizon.';
      return false;
    }
    let count = 0n;
    let choose = 1n;
    for (let size = 1; size <= max; size++) {
      choose = choose * BigInt(members.length - size + 1) / BigInt(size);
      if (size >= min) count += choose;
    }
    const limit = Math.min(defaults.optimizer.max_pairs, Math.floor(defaults.optimizer.max_pair_sessions / days));
    let effectiveMaximum = maximum_micros;
    if (!maximum.value && !maximum.validity.badInput) {
      const gridSize = Math.max(1, Number(BigInt(limit) / count));
      effectiveMaximum = Math.min(Number(maximum.max), minimum_micros + gridSize - 1);
      maximum.placeholder = String(effectiveMaximum);
    }
    const sizes = Math.max(1, effectiveMaximum - minimum_micros + 1);
    const pairs = count * BigInt(sizes);
    const summary = `${count.toLocaleString()} combinations · ${pairs.toLocaleString()} combination-size pairs`;
    const allowed = pairs <= BigInt(limit);
    message.textContent = allowed ? summary
      : summary + `. Limit ${limit} at this horizon. Reduce the pool, raise the member minimum, or narrow the MNQ range.`;
    return allowed;
  }

  function updateSelection(resetHorizon = false) {
    if (automaticMinimum) minimum.value = Math.max(1, basket.configuration().members.length);
    if (defaults) accountSettings(resetHorizon);
    updateRunButton();
    checkStatus.textContent = '';
    const open = get('source-link');
    open.hidden = !source.value;
    if (source.value) open.href = '#backtests/report/' + source.value;
    updateSources();
    basket.preview();
  }

  function updateSources() {
    const selected = source.selectedOptions[0];
    get('add-member').disabled = !basket.canAdd(source.value, selected?.dataset.role);
    for (const card of get('strategies').children) {
      const active = card.dataset.source === source.value;
      card.classList.toggle('is-selected', active);
      card.querySelector('.prop-desk-source-select').setAttribute('aria-pressed', String(active));
      const add = card.querySelector('.prop-desk-quick-add');
      const included = basket.contains(card.dataset.source);
      add.disabled = !basket.canAdd(card.dataset.source, card.dataset.role);
      add.hidden = add.disabled && !included;
      add.textContent = included ? '✓' : '+';
      card.querySelector('.prop-desk-source-note').hidden = !add.hidden;
    }
  }

  function sourceLabel(option) {
    const label = node('div', undefined, 'prop-desk-source-label');
    const note = node('small', 'Single-strategy runs only', 'prop-desk-source-note');
    note.hidden = true;
    label.append(node('strong', option.dataset.strategy), node('small', option.dataset.summary), note);
    if (option.dataset.oos) label.append(node('small', 'OOS linked'));
    return label;
  }

  function addSourceCard(option) {
    const card = node('div', undefined, 'prop-desk-source-card');
    card.dataset.source = option.value;
    card.dataset.role = option.dataset.role || '';
    const pick = node('button', undefined, 'prop-desk-source-select');
    pick.type = 'button';
    pick.append(sourceLabel(option));
    function select() {
      source.value = option.value;
      source.dispatchEvent(new Event('input', {bubbles:true}));
    }
    pick.onclick = select;
    const add = node('button', '+', 'prop-desk-quick-add');
    add.type = 'button';
    add.setAttribute('aria-label', 'Add ' + option.dataset.strategy + ' ' + option.value.slice(0, 8));
    add.onclick = () => {
      select();
      basket.addSelected();
    };
    card.draggable = true;
    card.ondragstart = event => {
      if (!basket.canAdd(option.value, option.dataset.role)) {
        event.preventDefault();
        return;
      }
      event.dataTransfer.setData('application/x-alphaquest-strategy', option.value);
      event.dataTransfer.effectAllowed = 'copy';
    };
    card.append(pick, add);
    get('strategies').append(card);
  }

  function accountSettings(resetHorizon) {
    const selected = defaults.profiles[profile.value];
    minimum.max = maximum.max = selected.caps[phase.value];
    const expiry = phase.value === 'evaluation' ? selected.evaluation_expiry : null;
    if (simulationSizeRule.dataset.phase !== phase.value) {
      simulationSizeRule.dataset.phase = phase.value;
      const presets = phase.value === 'evaluation' ? [['Optimal', 'optimal'], ['Conservative', 'conservative']]
        : [['First year', 'first_year'], ['Account life', 'account_life']];
      simulationSizeRule.replaceChildren(new Option('Manual', 'manual'),
        ...presets.map(([label, value]) => new Option(label, value)));
    }
    get('simulation-size-label').hidden = simulationSizeRule.disabled = optimizing();
    const terms = basket.configuration();
    const hasOos = terms.members.some(member => member.oos_backtest_id);
    get('oos-accounts-option').hidden = optimizing() || !hasOos || automaticSize();
    const basketFunded = !isFixed(terms) && phase.value === 'funded';
    const selectSizeRule = optimizing() && basketFunded;
    get('funded-size-label').hidden = fundedSizeRule.disabled = !selectSizeRule;
    const minimumHorizon = basketFunded ? defaults.basket_first_year : 1;
    const nextHorizon = basketFunded ? (optimizing() || simulationSizeRule.value === 'first_year' ||
      (simulationSizeRule.value === 'manual' && compareOosAccounts(terms))
      ? defaults.basket_first_year : defaults.basket_life_cutoff)
      : selected[phase.value + '_horizon'];
    const minimumRaised = minimumHorizon > Number(horizon.min);
    if (resetHorizon || defaultHorizon === undefined || horizon.valueAsNumber === defaultHorizon ||
        (minimumRaised && horizon.valueAsNumber < minimumHorizon)) horizon.value = nextHorizon;
    horizon.min = minimumHorizon;
    defaultHorizon = nextHorizon;
    horizon.readOnly = expiry !== null;
    horizonShortcuts.hidden = phase.value !== 'evaluation' || horizon.readOnly;
    for (const shortcut of horizonShortcuts.querySelectorAll('button')) {
      shortcut.setAttribute('aria-pressed', String(horizon.value === shortcut.dataset.deskDays));
    }
    const count = Math.min(defaults.optimizer.max_pairs,
      Math.floor(defaults.optimizer.max_pair_sessions / (horizon.valueAsNumber || nextHorizon)));
    const autoMaximum = Math.min(Number(maximum.max), minimum.valueAsNumber + count - 1);
    maximum.placeholder = !optimizing() && automaticSize() ? String(autoMaximum) : 'Optional';
    get('size-note').textContent = automaticSize()
      ? (simulationSizeRule.value === 'conservative' ? 'Conservative caps IS breach probability at 20%. ' : '') +
        'Automatic sizing uses IS only. Leave maximum blank to test through the displayed default.'
      : 'Enter a maximum to inspect the sizing and equity charts for a single strategy.';
    for (const button of phaseButtons) button.setAttribute('aria-pressed', String(button.dataset.deskPhase === phase.value));
    get('horizon-note').textContent = expiry !== null
      ? `This local Evaluation model expires after ${expiry} trading days.`
      : phase.value === 'evaluation'
        ? 'The observation cutoff limits the simulation. This local Evaluation model has no provider expiry.'
        : 'Accounts still open on the last simulated trading day are counted as open at cutoff.';
  }

  async function loadSources(offset, token) {
    inputs.disabled = true;
    checkStatus.textContent = 'Loading qualified strategies…';
    const previous = source.value;
    const data = await request(`/api/prop-desk/sources?offset=${offset}&limit=${pageSize}`);
    if (token !== generation) return;
    if (offset && !data.items.length) return loadSources(0, token);
    source.replaceChildren(new Option('Choose a qualified strategy', ''));
    get('strategies').replaceChildren();
    for (const run of data.items) {
      const dates = `${run.start_utc.slice(0, 10)} to ${run.end_utc.slice(0, 10)}`;
      const name = human(run.strategy);
      const option = new Option(`${run.dataset} · ${name} · ${dates} · ${run.id.slice(0, 8)}`, run.id);
      option.dataset.role = run.role || '';
      if (run.oos) {
        option.dataset.oos = run.oos.id;
        option.dataset.oosDates = `${run.oos.first_session} to ${run.oos.last_session}`;
      }
      option.dataset.strategy = name.charAt(0).toUpperCase() + name.slice(1);
      option.dataset.summary = [run.dataset, run.id.slice(0, 8), dates].join(' · ');
      source.add(option);
      addSourceCard(option);
    }
    if (data.items.some(run => run.id === previous)) source.value = previous;
    sourceOffset = offset;
    get('source-prev').disabled = offset === 0;
    get('source-next').disabled = offset + pageSize >= data.total;
    updateSelection();
    if (!data.total) checkStatus.textContent = 'No qualified strategies. Complete Mechanics, IS Broad, IS Narrow, OOS and Monte Carlo in Campaigns.';
    enableForm();
  }

  async function loadHistory(offset, token) {
    const data = await request(`/api/prop-desk?offset=${offset}`);
    if (token !== generation) return;
    historyOffset = offset;
    const parent = get('history-items');
    if (offset === 0) parent.replaceChildren();
    const list = offset === 0 ? node('ul', undefined, 'prop-desk-runs') : parent.querySelector('ul');
    for (const job of data.items) {
      const row = node('li');
      const timestamp = new Date(job.created_at_utc).toLocaleString();
      const name = job.mode === 'diagnostics' ? 'Strategy diagnostics'
        : job.mode === 'oos' ? 'OOS account assessment'
          : title(job.phase) + (['optimizer', 'subsets'].includes(job.mode) ? ' optimiser' : '');
      row.append(link(`${name} · ${timestamp} · ${job.source_backtest_id.slice(0, 8)}`, runUrl(job.id)),
                 node('span', ' · ' + job.status, 'muted'));
      list.append(row);
    }
    if (offset === 0) parent.append(data.items.length ? list : node('p', 'No Prop Desk runs yet.', 'muted'));
    get('history-next').hidden = !data.has_more;
  }

  function submission() {
    const common = {phase:phase.value, profile_id:profile.value, observation_sessions:horizon.valueAsNumber};
    const terms = basket.configuration();
    if (optimizing()) {
      const body = {...common, ...terms, minimum_members:minimumMembers.valueAsNumber, compare_accounts:true};
      if (!maximum.value && !maximum.validity.badInput) body.maximum_micros = Number(maximum.placeholder);
      if (phase.value === 'funded') body.funded_size_rule = fundedSizeRule.value;
      return {endpoint:'/optimizer/subsets', body};
    }
    if (isFixed(terms)) return {endpoint:'', body:{...common,
      source_backtest_id:terms.members[0].source_backtest_id, micros:terms.minimum_micros}};
    const body = {...common, ...terms};
    if (automaticSize() || compareOosAccounts(terms)) {
      body.simulation_size_rule = simulationSizeRule.value;
      if (automaticSize() && !maximum.value && !maximum.validity.badInput) body.maximum_micros = Number(maximum.placeholder);
    }
    return {endpoint:'/basket', body};
  }

  function sourceDetails(parent, info) {
    parent.append(node('p', `${info.dataset} · ${human(info.strategy)} · ${info.instrument}`),
      node('p', `${info.first_session} to ${info.last_session} · ${units(info.trades)} trades · ${units(info.source_sessions)} source weekdays`, 'field-help'));
    if (info.research_phase) parent.append(node('p', 'Saved research phase · ' + info.research_phase.toUpperCase(), 'field-help'));
    const details = node('details');
    details.append(node('summary', 'Source and execution assumptions'),
      node('p', info.risk_basis), node('p', info.session_convention),
      node('p', 'Saved net costs are retained. NQ exposure is scaled to MNQ using the saved trade path.'),
      link('Open backtest report', '#backtests/report/' + info.backtest_id));
    parent.append(details);
  }

  form.addEventListener('input', event => {
    if (event.target === minimum) automaticMinimum = false;
    updateSelection([profile, phase].includes(event.target));
  });
  for (const button of phaseButtons) button.onclick = () => {
    if (button.dataset.deskPhase === phase.value) return;
    phase.value = button.dataset.deskPhase;
    phase.dispatchEvent(new Event('input', {bubbles:true}));
  };
  get('open-history').onclick = () => history.focus();
  optimise.onclick = () => { location.hash = optimiseUrl; };
  for (const shortcut of horizonShortcuts.querySelectorAll('button')) shortcut.onclick = () => {
    horizon.value = shortcut.dataset.deskDays;
    horizon.dispatchEvent(new Event('input', {bubbles:true}));
  };
  const portfolio = get('members');
  portfolio.ondragover = event => {
    if (event.dataTransfer.types.includes('application/x-alphaquest-strategy')) event.preventDefault();
  };
  portfolio.ondrop = event => {
    const id = event.dataTransfer.getData('application/x-alphaquest-strategy');
    if (!id || !Array.from(source.options).some(option => option.value === id)) return;
    event.preventDefault();
    source.value = id;
    basket.addSelected();
  };

  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (inputs.disabled || launch.disabled) return;
    const token = generation;
    const {endpoint, body} = submission();
    inputs.disabled = true;
    checkStatus.textContent = 'Checking saved sources and preparing the simulation…';
    try {
      const job = await request('/api/prop-desk' + endpoint, body);
      if (token === generation) location.hash = runUrl(job.id);
    } catch (error) {
      if (token === generation) checkStatus.textContent = error.message;
    } finally {
      if (token === generation) enableForm();
    }
  });

  function metrics(parent, rows) {
    const list = node('dl', undefined, 'prop-desk-metrics');
    for (const [name, value] of rows) {
      const entry = node('div');
      entry.append(node('dt', name), node('dd', value));
      list.append(entry);
    }
    parent.append(list);
  }

  function outcomeBar(parent, parts) {
    const ns = 'http://www.w3.org/2000/svg';
    const bar = document.createElementNS(ns, 'svg');
    bar.setAttribute('viewBox', '0 0 100 4');
    bar.setAttribute('preserveAspectRatio', 'none');
    bar.setAttribute('aria-hidden', 'true');
    bar.setAttribute('class', 'prop-desk-outcomes');
    let position = 0;
    for (const [fraction, tone] of parts) {
      const segment = document.createElementNS(ns, 'rect');
      segment.setAttribute('x', position);
      segment.setAttribute('width', Math.max(0, fraction * 100));
      segment.setAttribute('height', '4');
      segment.setAttribute('class', tone);
      bar.append(segment);
      position += fraction * 100;
    }
    parent.append(bar);
  }

  function evaluationResults(parent, report) {
    const {probabilities, median_trading_days_to_target, pass_rate_interval_95} = report.calculations;
    const expired = report.rules.provider_expiry_trading_sessions !== null;
    metrics(parent, [
      ['Passed', percent(probabilities.passed)],
      ['Breached', percent(probabilities.breached)],
      [expired ? 'Provider expired' : 'Open at observation cutoff',
       percent(expired ? probabilities.provider_expired : probabilities.observation_cutoff)],
      ['Median trading days to target', units(median_trading_days_to_target)],
    ]);
    outcomeBar(parent, [[probabilities.passed, 'positive'], [probabilities.breached, 'negative'],
      [expired ? probabilities.provider_expired : probabilities.observation_cutoff, 'neutral']]);
    parent.append(node('p', `Median among passing attempts. 95% simulation interval for pass rate ${percent(pass_rate_interval_95[0])}–${percent(pass_rate_interval_95[1])}.`, 'field-help'));
  }

  function fundedResults(parent, report, timeline=parent) {
    const c = report.calculations;
    metrics(parent, [
      ['Any payout', percent(c.probability_any_payout)],
      ['Completed payout ladder', percent(c.probability_complete_ladder)],
      ['Breached before first payout', percent(c.probability_breach_before_first_payout)],
      ['Breached at any point', percent(c.probability_breach)],
      ['Mean account deductions', money(c.mean_account_deductions)],
      ['Mean trader receipts', money(c.mean_trader_receipts)],
      ...(c.median_trader_receipts == null ? [] : [['Median trader receipts', money(c.median_trader_receipts)]]),
    ]);
    parent.append(node('p', `${units(c.open_at_cutoff)} accounts open at cutoff · ${units(c.inactive)} closed for inactivity. Cash means include all simulated accounts. Receipts are credited at payout deduction under this model.`, 'field-help'));
    timeline.append(node('h3', 'Payout milestones'));
    const wrap = node('div', undefined, 'library-table-scroll');
    wrap.tabIndex = 0;
    wrap.setAttribute('role', 'region');
    wrap.setAttribute('aria-label', 'Payout milestones table');
    const table = node('table', undefined, 'library-table');
    const header = table.createTHead().insertRow();
    for (const label of ['Payout', 'Reached', 'Median trading day', 'Deduction cap']) {
      const th = node('th', label);
      th.scope = 'col';
      header.append(th);
    }
    const body = table.createTBody();
    for (const milestone of c.milestones) {
      const row = body.insertRow();
      row.insertCell().textContent = milestone.payout;
      const reach = row.insertCell();
      const meter = document.createElement('meter');
      meter.max = 1;
      meter.value = milestone.probability;
      meter.setAttribute('aria-hidden', 'true');
      reach.append(node('span', percent(milestone.probability)), meter);
      row.insertCell().textContent = units(milestone.median_trading_day);
      row.insertCell().textContent = money(milestone.account_deduction_cap);
    }
    wrap.append(table);
    timeline.append(wrap, node('p', 'Reach is a share of all accounts. Each median uses only accounts that reached that payout.', 'field-help'));
  }

  function accountRules(parent, report, view) {
    const rules = report.rules;
    const details = node('details');
    details.append(node('summary', 'Local account rules applied'));
    const list = node('dl', undefined, 'prop-desk-rules');
    const add = (label, value) => list.append(node('dt', label), node('dd', value));
    add('Starting balance', money(rules.starting_balance));
    if (view === 'evaluation') {
      add('Profit target', `${money(rules.profit_target)} · ${rules.pass_checked.toLowerCase()}`);
      add('Trailing drawdown', `${money(rules.maximum_trailing_drawdown)} · ${rules.trail_updates.toLowerCase()} · floor capped at ${money(rules.starting_balance + rules.trailing_floor_lock_profit)}`);
      add('Daily loss limit', `${money(rules.daily_loss_limit)} · ${rules.daily_loss_action}`);
      add('Best-day consistency', rules.consistency_percent == null ? 'None' : `At most ${rules.consistency_percent}% of total profit`);
      add('Provider expiry in local model', rules.provider_expiry_trading_sessions == null
        ? 'None' : `${rules.provider_expiry_trading_sessions} trading days`);
      add('Position ceiling', `${rules.max_mnq} MNQ`);
      add('Inactivity enforcement', rules.inactivity_enforced ? 'Enabled' : 'Disabled');
    } else {
      add('Trailing drawdown', `${money(rules.max_dd)} · ${rules.trail_updates.toLowerCase()} · floor locks at ${money(rules.starting_balance + rules.lock_profit)}`);
      add('Qualifying days', `${rules.qualifying_days} days of ${money(rules.qualifying_profit)}+ per payout cycle`);
      add('Payout ladder', rules.ladder.map(money).join(' / '));
      add('Payout timing', rules.payout_timing);
      if (rules.provider === 'lucidflex') {
        add('Withdrawal and split', `Up to ${percent(rules.withdrawal_fraction)} of profit, ${money(rules.minimum_request)} gross minimum, trader receives ${percent(rules.payout_share)}`);
        add('Inactivity enforcement', rules.inactivity_enforced ? `${rules.inactivity_calendar_days} calendar days` : 'Disabled · operator-maintained activity assumed');
      } else {
        add('Payout and safety net', `Scheduled amounts paid in full above the ${money(rules.safety_net)} profit buffer`);
        add('Best-day consistency', `At most ${percent(rules.consistency)} of cycle profit`);
        add('Approval day counts', rules.approval_day_counts ? 'Yes' : 'No');
        add('Inactivity', `${rules.inactivity_days} days of ${money(rules.inactivity_profit)}+ in a ${rules.inactivity_window}-session rolling window`);
      }
      add('Contract and loss-limit tiers', rules.levels.map(([profit, cap, loss]) =>
        `${money(profit)}+ starting profit · ${cap} MNQ · ${money(loss)} daily loss limit`).join(' / '));
    }
    details.append(list);
    parent.append(details);
  }

  function oosComparison(parent, job) {
    const {configuration, calculations, oos_assessment:assessment} = job.report;
    const {is, oos, reporting_window:windowDays} = calculations;
    const evaluation = job.phase === 'evaluation';
    const lifetime = configuration.size_rule === 'account_life';
    const ratio = (count, total) => `${percent(count / total)} (${units(count)}/${units(total)})`;
    const rows = [
      ['Observed sessions', side => units(side.sessions)],
      ['Admitted historical trades', side => units(side.admitted_trades)],
      ['Simulated paths', side => units(side.path_count)],
    ];
    if (evaluation) {
      for (const [key,label] of [['passed','Pass'], ['breached','Breach'],
        ['provider_expired','Provider expiry'], ['observation_cutoff','Observation cutoff']]) {
        if (Object.hasOwn(is.outcome_counts, key)) rows.push([label,
          side => ratio(side.outcome_counts[key], side.path_count)]);
      }
      rows.push(['Median trading days to pass', side => units(side.median_trading_days_to_target)]);
    } else {
      rows.push(
        ['Any payout', side => ratio(side.any_payout_count, side.path_count)],
        ['Breach before first payout', side => ratio(side.breach_before_first_payout_count, side.path_count)],
        ['Open at window end', side => ratio(side.open_at_window_end, side.path_count)],
        ['Open without a payout', side => ratio(side.open_without_payout, side.path_count)],
        [lifetime ? 'Mean trader receipts through cutoff' : 'Mean first-year trader receipts',
          side => money(side.mean_trader_receipts)],
        ['Mean account deductions', side => money(side.mean_account_deductions)],
      );
      if (lifetime) rows.push(['Resolved lifetime mean receipts', side => side.resolved_lifetime_mean_receipts == null
        ? 'Unresolved at cutoff' : money(side.resolved_lifetime_mean_receipts)]);
    }
    const preset = evaluation ? 'Single-attempt Evaluation' : lifetime ? 'Account life' : 'First year';
    parent.append(node('p', `${preset} · ${windowDays} trading days reported · ${configuration.observation_sessions} trading days simulated`),
      node('p', 'IS history · ' + window.propDeskBasket.interval(assessment.windows.is), 'field-help'),
      node('p', 'OOS history · ' + window.propDeskBasket.interval(assessment.windows.oos), 'field-help'),
      node('p', 'Each estimate resamples its observed history at the same frozen allocation.', 'field-help'));
    const table = node('table', undefined, 'prop-desk-oos-comparison');
    const head = table.createTHead().insertRow();
    for (const text of ['Metric', 'In sample', 'Out of sample']) {
      const th = node('th', text);
      th.scope = 'col';
      head.append(th);
    }
    const body = table.createTBody();
    for (const [label, value] of rows) {
      const row = body.insertRow();
      const heading = node('th', label);
      heading.scope = 'row';
      row.append(heading);
      for (const side of [is, oos]) row.insertCell().textContent = value(side);
    }
    parent.append(table);
    if (lifetime && [is, oos].some(side => side.open_at_window_end)) parent.append(node('p',
      'Rates are observed through cutoff. Receipts through cutoff are a lower bound on lifetime receipts for any history with open accounts.', 'field-help'));
  }

  function oosAssessment(parent, job) {
    const assessment = job.report.oos_assessment;
    if (!assessment) return;
    const panel = node('section', undefined, 'panel prop-desk-panel');
    panel.append(node('h2', 'OOS account assessment'));
    parent.append(panel);
    if (assessment.unavailable) {
      panel.append(node('p', assessment.unavailable, 'field-help'));
      return;
    }
    panel.append(node('p', `First-ranked combination ${assessment.combination} · ${assessment.micros} MNQ frozen in IS`, 'field-help'));
    const status = node('p', undefined, 'field-help');
    status.setAttribute('role', 'status');
    if (assessment.saved) {
      panel.append(link('Open OOS account assessment', runUrl(assessment.saved.id)), status);
      if (assessment.saved.status === 'complete') request('/api/prop-desk/' + assessment.saved.id)
        .then(saved => { if (panel.isConnected) oosComparison(panel, saved); })
        .catch(error => { status.textContent = error.message; });
      return;
    }
    const run = node('button', 'Run OOS account assessment', 'button secondary');
    run.type = 'button';
    panel.append(run, status);
    run.onclick = async () => {
      run.disabled = true;
      status.textContent = 'Verifying the saved OOS sources and frozen settings…';
      try {
        const saved = await request('/api/prop-desk/oos-assessments', {parent_id:job.id});
        if (panel.isConnected) location.hash = runUrl(saved.id);
      } catch (error) {
        run.disabled = false;
        status.textContent = error.message;
      }
    };
  }

  function renderJob(job) {
    const panel = node('section', undefined, 'panel prop-desk-panel');
    panel.append(['optimizer', 'subsets'].includes(job.mode)
      ? link('← Optimise', optimiseUrl) : link('← Prop Desk setup', '#prop-desk'));
    if (job.status !== 'complete') {
      const status = node('p', job.error || job.progress);
      status.setAttribute('role', 'status');
      const heading = job.mode === 'oos' ? 'OOS account assessment'
        : job.mode === 'diagnostics' ? 'Strategy diagnostics' : title(job.phase) + ' simulation';
      panel.append(node('h2', heading), status);
      result.replaceChildren(panel);
      return;
    }
    const report = job.report;
    if (job.mode === 'oos') {
      const config = report.configuration;
      const base = '/api/prop-analyses/' + job.id;
      panel.replaceChildren(link('← Optimise result', runUrl(config.parent_id) +
        '&combination=' + config.combination + '&size=' + config.micros),
        node('h2', 'OOS account assessment'),
        node('p', `${report.profile_label} · Combination ${config.combination} · ${config.micros} tested MNQ · Targets ${config.allocation.micros.join(' / ')} MNQ`, 'field-help'));
      oosComparison(panel, job);
      const downloads = node('div', undefined, 'prop-desk-actions');
      downloads.append(link('Report JSON ↓', base + '/downloads/report.json'),
        link('OOS account paths ↓', base + '/files/oos_account_paths.json'),
        link('Admitted OOS trades ↓', base + '/files/admitted_oos_trades.csv'),
        link('All evidence ZIP ↓', base + '/downloads/analysis.zip'));
      panel.append(downloads);
      result.replaceChildren(panel);
      return;
    }
    if (report.diagnostics) {
      panel.className = 'prop-desk-stack prop-desk-diagnostic-report';
      result.replaceChildren(panel);
      window.propDeskDiagnostics.render(panel, job, request, metrics);
      return;
    }
    if (report.basket || report.optimizer) {
      panel.className = 'prop-desk-report';
      result.replaceChildren(panel);
      const render = report.optimizer ? window.propDeskBasket.renderOptimizer : window.propDeskBasket.render;
      render(panel, job, {request, metrics, evaluationResults, fundedResults, accountRules, oosAssessment});
      return;
    }
    const config = report.configuration;
    panel.append(node('h2', title(job.phase) + ' result'),
      node('p', `${report.profile_label} · ${config.micros} MNQ requested · ${config.observation_sessions} trading days`, 'field-help'));
    if (job.phase === 'evaluation') evaluationResults(panel, report);
    else fundedResults(panel, report);
    panel.append(node('p', `${units(report.simulation.simulations)} simulated paths · ${report.sampling.block_weekdays}-weekday sample blocks. Estimates are conditional on the saved history.`, 'field-help'));
    accountRules(panel, report, job.phase);
    sourceDetails(panel, report.source_summary);
    const downloads = node('div', undefined, 'prop-desk-actions');
    const base = '/api/prop-analyses/' + job.id;
    downloads.append(link('Report JSON ↓', base + '/downloads/report.json'),
      link('Path outcomes ↓', base + '/files/path_outcomes.json'),
      link('All evidence ZIP ↓', base + '/downloads/analysis.zip'));
    panel.append(downloads);
    window.propDeskDiagnostics.controls(panel, job, request, [report.source_summary])(config.micros, [config.micros]);
    result.replaceChildren(panel);
  }

  async function watch(id, token) {
    try {
      const job = await request('/api/prop-desk/' + encodeURIComponent(id));
      if (token !== generation) return;
      renderJob(job);
      if (['queued', 'running'].includes(job.status)) polling = setTimeout(() => watch(id, token), 600);
    } catch (error) {
      if (token === generation) result.replaceChildren(link('← Prop Desk setup', '#prop-desk'), node('p', error.message));
    }
  }

  async function navigate() {
    const token = ++generation;
    clearTimeout(polling);
    const [path, query] = location.hash.split('?');
    if (path !== '#prop-desk') return;
    const params = new URLSearchParams(query);
    const id = params.get('analysis');
    form.hidden = history.hidden = Boolean(id);
    result.hidden = !id;
    try {
      if (id) {
        result.replaceChildren(node('p', 'Opening Prop Desk run…', 'muted'));
        await watch(id, token);
        return;
      }
      searchView = params.get('view') === 'optimise';
      get('workspace-title').textContent = optimizing() ? 'Optimise' : 'Simulation';
      get('simulation-back').hidden = !optimizing();
      optimise.hidden = optimizing();
      get('portfolio-title').textContent = optimizing() ? 'Candidate pool' : 'Portfolio';
      get('add-member').textContent = optimizing() ? 'Add to candidate pool' : 'Add to portfolio';
      get('allocation-preview').hidden = optimizing();
      get('size-note').hidden = optimizing();
      get('optimizer-fields').hidden = get('workload').hidden = minimumMembers.disabled = !optimizing();
      basket.showWorkspace();
      if (!defaults) {
        const settings = await request('/api/prop-desk/defaults');
        if (token !== generation) return;
        defaults = settings;
        for (const [key, value] of Object.entries(defaults.profiles)) profile.add(new Option(value.label, key));
      }
      await Promise.all([loadSources(sourceOffset || 0, token), loadHistory(0, token)]);
    } catch (error) {
      if (token === generation) {
        if (id) result.replaceChildren(link('← Prop Desk setup', '#prop-desk'), node('p', error.message));
        else checkStatus.textContent = error.message;
      }
    }
  }

  const pageSources = offset => loadSources(offset, generation).catch(error => {
    checkStatus.textContent = error.message;
    enableForm();
  });
  get('source-prev').onclick = () => pageSources(sourceOffset - pageSize);
  get('source-next').onclick = () => pageSources(sourceOffset + pageSize);
  get('history-next').onclick = async () => {
    const button = get('history-next');
    const token = generation;
    button.disabled = true;
    try { await loadHistory(historyOffset + 20, token); }
    catch (error) { if (token === generation) get('history-items').append(node('p', error.message)); }
    finally { button.disabled = false; }
  };
  window.addEventListener('hashchange', navigate);
  navigate();
})();
