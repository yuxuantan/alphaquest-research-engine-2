"use strict";
(() => {
  const colors = ['#087968', '#4164a1', '#a34e4b', '#866119', '#7558a7', '#3f758d'];
  const usd = value => Number(value).toLocaleString('en-US', {style:'currency', currency:'USD'});
  const pct = value => Number(value).toLocaleString('en-US', {style:'percent', maximumFractionDigits:1});
  const presetNames = {optimal:'Optimal', conservative:'Conservative', first_year:'First year', account_life:'Account life'};
  const node = (tag, value, className) => {
    const element = document.createElement(tag);
    if (value !== undefined) element.textContent = value;
    if (className) element.className = className;
    return element;
  };
  const button = (label, onClick) => {
    const control = node('button', label, 'button secondary');
    control.type = 'button';
    control.onclick = onClick;
    return control;
  };

  function strategyIdentity(name, details) {
    const identity = node('span', undefined, 'prop-desk-source-label');
    identity.append(node('strong', name), node('small', details));
    return identity;
  }

  function setup(get, optimizing, invalidate) {
    const portfolio = [];
    let candidates;
    let members = portfolio;
    const picker = get('source');
    const add = get('add-member');
    const includeOos = get('include-oos');
    const selected = () => picker.selectedOptions[0];
    const contains = id => members.some(member => member.source_backtest_id === id);
    const canAdd = (id, role) => Boolean(id && !contains(id)
      && (role === 'is' || (!optimizing() && members.length === 0)));
    const hasFullOos = () => members.every(member => member.oos_backtest_id);
    function preview() {
      const size = get('minimum').valueAsNumber;
      const weights = members.map(member => member.weight);
      const sum = weights.reduce((acc, weight) => acc + weight, 0);
      const valid = weights.every(weight => Number.isInteger(weight) && weight >= 1 && weight <= 1000000);
      const message = get('allocation-preview');
      message.textContent = '';
      const badges = get('members').querySelectorAll('[data-target]');
      const shares = get('members').querySelectorAll('[data-share]');
      badges.forEach(badge => { badge.hidden = optimizing(); });
      shares.forEach(share => { share.hidden = optimizing(); });
      badges.forEach(badge => { badge.textContent = '— MNQ'; });
      shares.forEach(share => { share.textContent = '—'; });
      if (!optimizing() && sum > 0 && valid && size >= 1) {
        const targets = weights.map(weight => Math.floor(size * weight / sum));
        const unused = size - targets.reduce((acc, target) => acc + target, 0);
        badges.forEach((badge, index) => { badge.textContent = targets[index] + ' MNQ'; });
        shares.forEach((share, index) => { share.textContent = pct(weights[index] / sum); });
        message.textContent = `At the ${size} MNQ minimum, ${unused} MNQ remain unused after rounding down.`;
      }
    }

    function draw() {
      get('equal').disabled = !members.length;
      get('clear').disabled = !members.length;
      const hasOos = members.some(member => member.oos_backtest_id);
      const incompleteOos = hasOos && !hasFullOos() && !optimizing();
      get('oos-option').hidden = includeOos.disabled = !hasOos || incompleteOos;
      get('basket-note').hidden = !incompleteOos;
      get('members').replaceChildren(...members.map((member, index) => {
        const row = node('article', undefined, 'prop-desk-member');
        const summary = node('div', undefined, 'prop-desk-member-summary');
        const identity = node('div', undefined, 'prop-desk-source-label');
        identity.append(node('strong', member.label), node('small', member.summary));
        const badge = node('span', undefined, 'prop-desk-quantity');
        badge.dataset.target = '';
        const share = node('span', undefined, 'prop-desk-share');
        share.dataset.share = '';
        summary.append(identity, badge, share);
        row.append(summary);
        const controls = node('div', undefined, 'prop-desk-actions prop-desk-member-actions');
        const label = node('label', `Weight for member ${index + 1}`);
        const weight = node('input');
        Object.assign(weight, {type:'number', min:'1', max:'1000000', step:'1', required:true, value:member.weight});
        weight.oninput = () => { member.weight = weight.valueAsNumber; preview(); };
        label.append(weight);
        const remove = button('Remove', () => {
          members.splice(index, 1);
          draw();
          invalidate();
        });
        remove.setAttribute('aria-label', `Remove member ${index + 1}`);
        controls.append(label, remove);
        row.append(controls);
        if (member.oos_backtest_id) {
          const linked = node('a', 'OOS report · ' + member.oosDates, 'field-help');
          linked.href = '#backtests/report/' + member.oos_backtest_id;
          row.append(linked);
        }
        return row;
      }));
      if (!members.length) get('members').append(node('p', 'Add a saved strategy from the list.', 'prop-desk-empty'));
      preview();
    }

    function addSelected() {
      const option = selected();
      if (!canAdd(option?.value, option?.dataset.role)) return;
      members.push({source_backtest_id:picker.value, label:option.dataset.strategy, summary:option.dataset.summary,
                    weight:1, oos_backtest_id:option.dataset.oos || null, oosDates:option.dataset.oosDates});
      draw();
      invalidate();
    }
    add.onclick = addSelected;
    get('equal').onclick = () => {
      for (const member of members) member.weight = 1;
      draw();
      invalidate();
    };
    get('clear').onclick = () => {
      members.length = 0;
      draw();
      invalidate();
    };

    draw();
    return {
      preview, addSelected, contains, canAdd,
      showWorkspace() {
        if (optimizing() && !candidates) candidates = portfolio.map(member => ({...member}));
        members = optimizing() ? candidates : portfolio;
        draw();
      },
      configuration() {
        const minimum = get('minimum').valueAsNumber;
        const maximum = get('maximum');
        const useOos = includeOos.checked && (optimizing() || hasFullOos());
        return {
          members:members.map(({source_backtest_id, oos_backtest_id, weight}) =>
            ({source_backtest_id, oos_backtest_id:useOos ? oos_backtest_id : null, weight})),
          minimum_micros:minimum,
          maximum_micros:maximum.value === '' && !maximum.validity.badInput ? minimum : maximum.valueAsNumber,
        };
      },
    };
  }

  function plot(parent, labels, series, {format, marker, title, startAtZero=false, positions, dots=!startAtZero}) {
    const ns = 'http://www.w3.org/2000/svg';
    const element = (tag, attrs, value) => {
      const part = document.createElementNS(ns, tag);
      for (const [name, data] of Object.entries(attrs)) part.setAttribute(name, data);
      if (value !== undefined) part.textContent = value;
      return part;
    };
    const width = Math.min(780, Math.max(250, parent.clientWidth - 24));
    const left = 67, right = width - 14, top = 20, bottom = 177;
    let low = 0, high = 0;
    for (const row of series) for (const value of (row.lower ? [...row.lower, ...row.upper] : row.values)) {
      if (value == null) continue;
      low = Math.min(low, value);
      high = Math.max(high, value);
    }
    if (low === high) high = 1;
    const steps = Math.max(1, labels.length - 1 + Number(startAtZero));
    const x = index => left + (right - left) * (positions
      ? (positions[index] - positions[0]) / Math.max(1, positions.at(-1) - positions[0])
      : (index + Number(startAtZero)) / steps);
    const y = value => bottom - (value - low) * (bottom - top) / (high - low);
    const svg = element('svg', {viewBox:`0 0 ${width} 211`, role:'img', 'aria-label':title, class:'prop-desk-chart'});
    const traces = [];
    if (marker != null && marker >= 0) {
      const from = marker === 0 ? left : Math.max(left, (x(marker) + x(marker - 1)) / 2);
      svg.append(element('rect', {x:from, y:top, width:right-from, height:bottom-top, fill:'#e9f1f4'}),
        element('line', {x1:from, x2:from, y1:top, y2:bottom, stroke:'#678795', 'stroke-dasharray':'4 4'}),
        element('text', {x:Math.min(from+4,right-26), y:top-5, class:'chart-label'}, 'OOS'));
    }
    for (let i = 0; i <= 4; i++) {
      const value = low + (high-low) * i/4;
      const ordinate = y(value);
      svg.append(element('line', {x1:left, x2:right, y1:ordinate, y2:ordinate, class:'chart-grid'}),
        element('text', {x:left-5, y:ordinate+4, 'text-anchor':'end', class:'chart-label'}, format(value)));
    }
    for (const [index, row] of series.entries()) {
      const color = row.color || colors[index % colors.length];
      const trace = element('g', {});
      if (row.lower) {
        const points = values => values.map((value, i) => value == null ? null
          : x(i) + ',' + y(value)).filter(point => point !== null);
        trace.append(element('polygon', {points:[...points(row.upper), ...points(row.lower).reverse()].join(' '),
          fill:color, 'fill-opacity':row.opacity ?? .18}));
        traces.push(trace);
        svg.append(trace);
        continue;
      }
      let path = startAtZero ? `M${left} ${y(0)}` : '', connected = startAtZero;
      for (const [i, value] of row.values.entries()) {
        if (value == null) { connected = false; continue; }
        path += `${connected ? 'L' : 'M'}${x(i)} ${y(value)} `;
        connected = true;
        if (dots) trace.append(element('circle', {cx:x(i), cy:y(value), r:3, fill:color}));
      }
      trace.append(element('path', {d:path, fill:'none', stroke:color, 'stroke-width':index ? 1.7 : 2.5,
        'stroke-dasharray':(row.dashed ?? Boolean(index)) ? '5 3' : 'none'}));
      traces.push(trace);
      svg.append(trace);
    }
    const last = labels.length - 1;
    for (const index of new Set([0, Math.floor(last/2), last])) {
      if (width < 425 && index !== 0 && index !== last) continue;
      svg.append(element('text', {x:index === 0 ? left : x(index), y:bottom+19,
        'text-anchor':index === 0 ? 'start' : index === last ? 'end' : 'middle', class:'chart-label'}, labels[index]));
    }
    const legend = node('div', undefined, 'prop-desk-actions prop-desk-legend');
    for (const [index, row] of series.entries()) {
      const key = node('button', row.label);
      key.type = 'button';
      key.setAttribute('aria-pressed', 'true');
      key.dataset.series = String(index % colors.length);
      if (row.color) key.style.setProperty('--prop-desk-series-color', row.color);
      key.onclick = () => {
        const visible = key.getAttribute('aria-pressed') === 'true';
        key.setAttribute('aria-pressed', String(!visible));
        traces[index].setAttribute('visibility', visible ? 'hidden' : 'visible');
      };
      legend.append(key);
    }
    parent.append(svg, legend);
  }

  function render(parent, job, {request, metrics, evaluationResults, fundedResults, accountRules},
      {directory='', onSizeChange, headingText, combination=null}={}) {
    const report = job.report;
    const basket = report.basket;
    const sizes = basket.sizes;
    const phase = job.phase;
    const funded = phase === 'funded';
    const heading = node('div', undefined, 'prop-desk-result-heading');
    heading.append(node('h2', headingText || (funded ? 'Funded' : 'Evaluation') + ' basket results'),
      node('p', `${report.profile_label} · ${report.simulation.simulations.toLocaleString()} paths per size · ${report.configuration.observation_sessions} trading days`, 'field-help'));
    parent.append(heading);
    const coverage = basket.windows;
    const interval = dates => `${dates[0]} to ${dates.at(-1)} · ${dates.length} observed sessions`;
    const layout = node('div', undefined, 'prop-desk-layout');
    const library = node('section', undefined, 'panel prop-desk-panel prop-desk-library');
    const center = node('div', undefined, 'prop-desk-stack prop-desk-portfolio');
    const account = node('aside', undefined, 'prop-desk-stack prop-desk-account');
    layout.append(library, center, account);
    parent.append(layout);

    library.append(node('h2', 'Strategies'));
    for (const [i, member] of basket.members.entries()) {
      const source = node('a', undefined, 'prop-desk-report-source');
      source.href = '#backtests/report/' + member.backtest_id;
      source.append(node('strong', member.strategy.replaceAll('_',' ')),
        node('small', `${member.dataset} · ${member.instrument} · ${member.backtest_id.slice(0,8)}`));
      library.append(source);
    }
    library.append(node('p', 'IS sizing · ' + interval(coverage.is), 'field-help'));
    if (coverage.oos) library.append(node('p', 'OOS chart · ' + interval(coverage.oos), 'field-help'));
    const assumptions = node('details');
    assumptions.append(node('summary', 'Shared-account assumptions'), node('p', basket.law, 'field-help'));
    if (basket.members.length === 1 && !directory && !basket.size_rule) assumptions.append(node('p', 'One-member account paths use the original single-strategy weekday sampling. The chart shows observed sessions.', 'field-help'));
    if (basket.size_rule) assumptions.append(node('p', 'This report uses shared observed-session account paths for both histories, including when the portfolio has one strategy.', 'field-help'));
    if (basket.oosNote) assumptions.append(node('p', basket.oosNote, 'field-help'));
    library.append(assumptions);

    const portfolio = node('section', undefined, 'panel prop-desk-panel prop-desk-member-card');
    const chart = node('section', undefined, 'panel prop-desk-panel prop-desk-chart-section prop-desk-equity-card');
    const timeline = node('section', undefined, 'panel prop-desk-panel prop-desk-timeline');
    timeline.hidden = !funded;
    center.append(portfolio, chart, timeline);
    const detail = node('section', undefined, 'panel prop-desk-panel prop-desk-account-result');
    const sweep = node('section', undefined, 'panel prop-desk-panel prop-desk-chart-section prop-desk-size-card');
    const ruleCard = node('section', undefined, 'panel prop-desk-panel prop-desk-rule-card');
    account.append(detail, sweep, ruleCard);
    accountRules(ruleCard, report, phase);
    sweep.append(node('h2', 'Size'));
    const selectLabel = node('label', 'Inspect tested size');
    const select = node('select');
    select.setAttribute('aria-label', 'Inspect tested size');
    for (const row of sizes) select.add(new Option(row.micros + ' MNQ', row.micros));
    const url = new URLSearchParams(location.hash.split('?')[1] || '');
    const previous = url.get('size');
    if (sizes.some(row => String(row.micros) === previous)) select.value = previous;
    else if (basket.selected_micros) select.value = basket.selected_micros;
    selectLabel.append(select);
    sweep.append(selectLabel);
    const slider = node('input');
    Object.assign(slider, {type:'range', min:0, max:sizes.length-1, step:1, disabled:sizes.length<2});
    slider.setAttribute('aria-label', 'Tested size slider');
    sweep.append(slider);
    if (basket.size_unavailable) sweep.append(node('p',
      presetNames[basket.size_rule] + ' size unavailable. ' + basket.size_unavailable, 'field-help'));
    if (basket.selected_micros && basket.size_rule !== 'manual') {
      const caption = presetNames[basket.size_rule] + ' · IS-selected ' + basket.selected_micros + ' MNQ';
      const reset = button(caption, () => {
        select.value = basket.selected_micros;
        selectedSize();
      });
      sweep.append(reset);
      if (basket.size_provisional) sweep.append(node('p',
        'Account-life sizing is provisional. At least one tested size has accounts open at cutoff.', 'field-help'));
    }
    sweep.append(node('h3', funded ? 'Trader receipts by total MNQ' : 'Evaluation outcomes by total MNQ'));
    const labels = sizes.map(row => String(row.micros));
    if (funded) {
      const series = [
        {label:'First year', values:sizes.map(row => row.metrics.first_year_mean_receipts)},
        {label:'Account life', values:sizes.map(row => row.metrics.account_life_mean_receipts)},
      ];
      if (sizes.some(row => row.metrics.open_at_cutoff)) series.push(
        {label:'Account life · cash through cutoff only', dashed:true, values:sizes.map(row =>
          row.metrics.open_at_cutoff ? row.metrics.mean_trader_receipts : null)});
      plot(sweep, labels, series, {format:value => '$' + Math.round(value).toLocaleString(), title:'Trader receipts by total MNQ'});
      sweep.append(node('p', 'First year uses 261 trading days. Where accounts remain open, cash through cutoff is a lower bound on eventual receipts.', 'field-help'));
    } else {
      plot(sweep, labels, [
        {label:'Pass', values:sizes.map(row => row.metrics.probabilities.passed)},
        {label:'Breach', values:sizes.map(row => row.metrics.probabilities.breached)},
      ], {format:pct, title:'Evaluation pass and breach by total MNQ'});
    }
    const downloads = node('div', undefined, 'prop-desk-actions');
    const base = `/api/prop-analyses/${job.id}`;
    const files = '/files/' + (directory ? directory + '/' : '');
    function download(label, path) {
      const anchor = node('a', label);
      anchor.href = base + path;
      return anchor;
    }
    downloads.append(download('Report JSON ↓', '/downloads/report.json'),
      download('All evidence ZIP ↓', '/downloads/analysis.zip'));
    library.append(downloads);
    const updateDiagnostics = window.propDeskDiagnostics.controls(center, job, request, basket.members, combination);
    let version = 0;
    async function selectedSize() {
      const current = ++version;
      const size = Number(select.value);
      const row = sizes.find(item => item.micros === size);
      updateDiagnostics(size, row.allocation.micros);
      slider.value = select.selectedIndex;
      slider.setAttribute('aria-valuetext', size + ' MNQ');
      url.set('size', String(size));
      window.history.replaceState(null, '', '#prop-desk?' + url.toString());
      onSizeChange?.(size);
      portfolio.replaceChildren(node('h2', 'Portfolio'));
      const weightTotal = report.configuration.members.reduce((total, member) => total + member.weight, 0);
      for (const [i, member] of basket.members.entries()) {
        const line = node('div', undefined, 'prop-desk-member prop-desk-member-summary');
        const identity = node('div', undefined, 'prop-desk-source-label');
        identity.append(node('strong', member.strategy.replaceAll('_', ' ')),
          node('small', 'Member ' + (i+1) + ' · ' + member.backtest_id.slice(0,8)));
        const share = report.recommendation_evidence ? row.allocation.micros[i] / size
          : report.configuration.members[i].weight / weightTotal;
        line.append(identity, node('span', row.allocation.micros[i] + ' MNQ', 'prop-desk-quantity'),
          node('span', pct(share), 'prop-desk-share'));
        portfolio.append(line);
      }
      portfolio.append(node('p', `${size} MNQ tested · ${row.allocation.unused} unused · target allocations`, 'field-help'));
      if (basket.tier_targets) {
        const tiers = node('details');
        tiers.append(node('summary', 'Tier-adjusted MNQ targets'));
        for (const tier of basket.tier_targets) tiers.append(node('p',
          `Opening profit ${usd(tier.opening_profit)} · ${tier.cap_mnq} MNQ cap · ${tier.targets.join(' / ')} MNQ by member`, 'field-help'));
        portfolio.append(tiers);
      }
      detail.replaceChildren(node('h2', funded ? 'Funded account' : 'Evaluation account'));
      timeline.replaceChildren();
      const pair = row.account_comparison;
      const accountMetrics = pair?.oos_metrics || pair?.is_metrics || row.metrics;
      if (pair) {
        const accountLabel = pair.oos_metrics ? 'Out of sample' : 'In sample';
        const days = pair.oos_metrics ? (pair.oos_days || coverage.oos) : coverage.is;
        detail.append(node('p', accountLabel + ' account paths · ' + interval(days), 'field-help'));
        detail.append(node('p', accountMetrics.path_count.toLocaleString() + ' paths · ' +
          (accountMetrics.reporting_sessions || report.configuration.observation_sessions) + ' trading days reported', 'field-help'));
        if (pair.oos_metrics) {
          const inSample = node('details');
          inSample.append(node('summary', 'In-sample comparison'));
          const comparison = funded ? [
            ['IS any payout', pct(pair.is_metrics.probability_any_payout)],
            ['IS breach before first payout', pct(pair.is_metrics.probability_breach_before_first_payout)],
            ['IS mean trader receipts', usd(pair.is_metrics.mean_trader_receipts)],
            ['IS median trader receipts', usd(pair.is_metrics.median_trader_receipts)],
            ['IS accounts open at cutoff', pair.is_metrics.open_at_cutoff.toLocaleString()],
          ] : [
            ['IS pass', pct(pair.is_metrics.probabilities.passed)],
            ['IS breach', pct(pair.is_metrics.probabilities.breached)],
            ['IS expiry or cutoff', pct(pair.is_metrics.probabilities.provider_expired ??
              pair.is_metrics.probabilities.observation_cutoff)],
            ['IS median days to target', pair.is_metrics.median_trading_days_to_target ?? '—'],
          ];
          metrics(inSample, comparison);
          detail.append(inSample, download('OOS account paths ↓', files + pair.oos_paths_file), ' ',
            download('OOS account trades ↓', files + pair.oos_trades_file));
        } else {
          detail.append(node('p', pair.unavailable, 'field-help'));
        }
      }
      if (funded) {
        const prefix = pair ? 'IS ' : '';
        metrics(detail, [[prefix + 'First-year mean trader receipts', usd(row.metrics.first_year_mean_receipts)],
          [prefix + 'Account-life mean trader receipts', row.metrics.account_life_mean_receipts == null
            ? 'Unresolved' : usd(row.metrics.account_life_mean_receipts)]]);
        if (pair && basket.reporting_preset === 'account_life' && accountMetrics.open_at_cutoff) {
          detail.append(node('p', 'Receipts through cutoff are a lower bound on account-life receipts.', 'field-help'));
        }
        fundedResults(detail, {...report, calculations:accountMetrics}, timeline);
      } else evaluationResults(detail, {...report, calculations:accountMetrics});
      detail.append(download(pair ? 'IS account paths ↓' : 'Path outcomes for this size ↓', files + `paths_${size}.json`));
      chart.replaceChildren(node('p', 'Loading saved equity…', 'field-help'));
      try {
        const result = await request(base + files + `equity_${size}.json`);
        if (current !== version) return;
        chart.replaceChildren(node('h2', 'Equity'),
          node('p', 'Historical closed trades at the selected size, net of costs.', 'field-help'));
        const series = ['Portfolio', ...basket.members.map((member, i) => `Member ${i+1}`)]
          .map((label, i) => ({label, values:result.levels.map(row => row[i])}));
        const value = input => input == null ? '—' : usd(input);
        metrics(chart, [
          ['Final net P&L', value(result.final_equity_change)],
          ['Annualized return', value(result.metrics.annual_return)],
          ['Annualized volatility', value(result.metrics.annual_volatility)],
          ['Sharpe', result.metrics.sharpe == null ? '—' : result.metrics.sharpe.toFixed(2)],
          ['Max drawdown', value(result.metrics.maximum_drawdown)],
        ]);
        plot(chart, result.dates, series, {format:value => '$' + Math.round(value).toLocaleString(),
          marker:result.dates.indexOf(result.oos_start), title:'Portfolio and members historical closed-trade equity', startAtZero:true});
        const methods = node('details');
        methods.append(node('summary', 'Chart methodology'),
          node('p', 'Session-close cumulative net P&L from admitted trades. The chart uses the same targets in IS and OOS. Account stops, tiers and payouts apply in the simulation.', 'field-help'),
          node('p', 'Annualization uses 252 observed sessions and a zero cash benchmark. Drawdown uses each admitted trade close.', 'field-help'));
        chart.append(methods);
        if (result.overlap_risk) {
          const screen = result.overlap_risk;
          const summary = node('details');
          summary.open = true;
          summary.append(node('summary', 'Overlap risk screen'), node('p',
            `Flags compare summed standalone adverse excursions at target size with ${usd(screen.threshold_usd)}, the smaller initial loss allowance. The excursions can occur at different times. Flags are advisory.`, 'field-help'));
          for (const [period, marks] of Object.entries(screen.periods)) {
            summary.append(node('p', `${period.toUpperCase()} · ${marks.overlapping} overlapping trades · ${marks.flagged} at or above threshold · ${marks.incomplete} with incomplete evidence` +
              (marks.max_combined_mae === null ? '' : ` · largest combined MAE ${usd(marks.max_combined_mae)}`), 'field-help'));
          }
          chart.append(summary);
        } else {
          chart.append(node('p', `Overlapping entries skipped · IS ${row.overlap_skips.is}` +
            (row.overlap_skips.oos == null ? '' : ` · OOS ${row.overlap_skips.oos}`), 'field-help'));
        }
        chart.append(download('Admitted trades for this size ↓', files + result.trades_file));
      } catch (error) {
        if (current === version) chart.replaceChildren(node('p', error.message));
      }
    }
    select.onchange = selectedSize;
    slider.oninput = () => {
      select.selectedIndex = Number(slider.value);
      selectedSize();
    };
    selectedSize();
  }

  function renderOptimizer(parent, job, view) {
    const {report, phase} = job;
    const {optimizer} = report;
    const accountComparison = optimizer.account_comparison;
    const funded = phase === 'funded';
    const selectedSizes = Boolean(optimizer.size_rule);
    const section = node('section', undefined, 'panel prop-desk-panel prop-desk-ranking');
    const title = (funded ? 'Funded' : 'Evaluation') + ' combination rankings';
    section.append(node('h2', title), node('p',
      `${optimizer.workload.combinations} combinations · ${optimizer.workload.pairs} tested pairs · ${optimizer.objective}`),
      node('p', optimizer.ties, 'field-help'));
    if (selectedSizes) section.append(node('p', optimizer.size_rule_label + '. Sizes with a zero target for any member are excluded from selection.', 'field-help'));
    if (optimizer.size_rule === 'account_life') section.append(node('p',
      'If any eligible size has open accounts, the selected size is provisional. Cash collected through cutoff is a lower bound on lifetime receipts.', 'field-help'));
    const settings = node('details');
    const config = report.configuration;
    const pool = node('ol');
    for (const [index, member] of config.members.entries()) {
      const source = node('a', optimizer.members[index].strategy.replaceAll('_', ' ') + ' · ' + member.source_backtest_id.slice(0,8));
      source.href = '#backtests/report/' + member.source_backtest_id;
      const item = node('li');
      item.append(source, node('span', ` · Weight ${member.weight}`));
      if (member.oos_backtest_id) {
        const child = node('a', 'OOS ' + member.oos_backtest_id.slice(0,8));
        child.href = '#backtests/report/' + member.oos_backtest_id;
        item.append(' · ', child);
      }
      pool.append(item);
    }
    settings.append(node('summary', 'Search settings and candidate pool'),
      node('p', `${report.profile_label} · ${config.observation_sessions} trading days · ${report.simulation.simulations.toLocaleString()} paths per pair`),
      node('p', `${config.minimum_members}–${config.maximum_members} members · ${config.minimum_micros}–${config.maximum_micros} MNQ`),
      node('p', 'Common IS · ' + window.propDeskBasket.interval(optimizer.is_days)), pool);
    section.append(settings);
    const tableRegion = node('div', undefined, 'prop-desk-ranking-scroll');
    tableRegion.setAttribute('role', 'region');
    tableRegion.setAttribute('aria-label', title);
    tableRegion.tabIndex = 0;
    const table = node('table');
    const heading = table.createTHead().insertRow();
    const rankingLabel = funded ? (selectedSizes ? 'Any payout' : 'First-year receipts') : 'Pass';
    const detailLabels = selectedSizes ? (funded
      ? ['Sizing receipts', ...(accountComparison ? ['IS first payout day'] : [])]
      : ['IS median pass day']) : [];
    const oosLabels = accountComparison ? [
      funded ? 'OOS any payout' : 'OOS pass',
      'OOS breach',
      funded ? 'OOS first payout day' : 'OOS median pass day',
      ...(funded ? ['OOS mean receipts', 'OOS open at cutoff'] : []),
    ] : [];
    for (const label of ['Rank', 'Members', selectedSizes ? 'Selected MNQ' : 'Total MNQ', 'Targets (MNQ)',
      rankingLabel, ...oosLabels, ...detailLabels, funded ? 'IS open at cutoff' : 'IS breach', '']) {
      const th = node('th', label);
      th.scope = 'col';
      heading.append(th);
    }
    const body = table.createTBody();
    tableRegion.append(table);
    section.append(tableRegion);
    if (accountComparison?.oos_days.length) section.append(node('p', 'Common OOS account history · ' +
      window.propDeskBasket.interval(accountComparison.oos_days) + ' · ranking uses IS only.', 'field-help'));
    const inspection = node('div');
    parent.append(section);
    view.oosAssessment(parent, job);
    parent.append(inspection);
    const controls = [];
    function open(combination, size) {
      const url = new URLSearchParams(location.hash.split('?')[1] || '');
      url.set('combination', combination.id);
      url.set('size', size);
      window.history.replaceState(null, '', '#prop-desk?' + url.toString());
      inspection.replaceChildren();
      const selected = optimizer.ranking.find(entry => entry.combination === combination.id);
      if (selectedSizes && selected) inspection.append(node('p',
        `Ranked at ${selected.micros} MNQ. Use the size controls to inspect other tested allocations.`, 'field-help'));
      const members = combination.members.map(index => optimizer.members[index]);
      const configuration = {...report.configuration,
        members:combination.members.map(index => report.configuration.members[index])};
      const pair = accountComparison?.rows[combination.id];
      const sizes = combination.sizes.map(row => pair?.micros === row.micros
        ? {...row, account_comparison:{...pair, oos_days:accountComparison.oos_days}} : row);
      const basket = {members, law:optimizer.law, sizes, reporting_preset:accountComparison?.reporting_preset,
        windows:{is:optimizer.is_days, oos:combination.oos_days.length ? combination.oos_days : null},
        oosNote:combination.oos_note};
      render(inspection, {...job, report:{...report, configuration, basket}}, view, {
        directory:combination.directory, headingText:`Inspect combination ${combination.id}`, combination:combination.id,
        onSizeChange:next => controls.forEach(({button, entry}) =>
          button.setAttribute('aria-pressed', String(entry.combination === combination.id &&
            (selectedSizes || entry.micros === next)))),
      });
    }
    for (const entry of [...optimizer.ranking, ...(optimizer.unranked || [])]) {
      const combination = optimizer.combinations[entry.combination - 1];
      const size = combination.sizes.find(row => row.micros === entry.micros);
      const labels = combination.members.map(index => {
        const member = optimizer.members[index];
        return member.strategy.replaceAll('_', ' ') + ' · ' + member.backtest_id.slice(0,8);
      });
      const row = body.insertRow();
      const pair = accountComparison?.rows[entry.combination];
      const oos = pair?.oos_metrics;
      let oosCells = oosLabels.map(() => '—');
      if (oos) {
        oosCells = funded ? [
          pct(oos.probability_any_payout), pct(oos.probability_breach),
          oos.milestones[0].median_trading_day ?? '—', usd(oos.mean_trader_receipts), oos.open_at_cutoff,
        ] : [
          pct(oos.probabilities.passed), pct(oos.probabilities.breached), oos.median_trading_days_to_target ?? '—',
        ];
      }
      let values;
      if (entry.reason) {
        values = ['Unranked', labels.join(' / '), '—', '—', '—', ...oosCells, ...detailLabels.map(() => '—'), '—'];
      } else {
        const rank = entry.rank + (entry.near_best ? ' (within 1 SE)' : entry.tied ? ' (tie)' : '');
        const details = selectedSizes ? (funded
          ? [usd(entry.size_score) + (entry.size_provisional ? ' (provisional)' : ''),
            ...(accountComparison ? [entry.median_days ?? '—'] : [])]
          : [entry.median_days ?? '—']) : [];
        values = [rank, labels.join(' / '), entry.micros, size.allocation.micros.join(' / '),
          funded && !selectedSizes ? usd(entry.score) : pct(entry.score), ...oosCells, ...details,
          funded ? pair?.is_metrics.open_at_cutoff ?? size.metrics.open_at_cutoff : pct(size.metrics.probabilities.breached)];
      }
      for (const value of values) {
        row.insertCell().textContent = value;
      }
      const button = node('button', 'Inspect', 'button secondary');
      button.setAttribute('aria-label', `Inspect combination ${entry.combination} at ${entry.micros} MNQ`);
      button.onclick = () => open(combination, entry.micros);
      const action = row.insertCell();
      if (entry.reason) action.append(node('small', entry.reason, 'field-help'));
      if (pair?.unavailable) action.append(node('small', pair.unavailable, 'field-help'));
      action.append(button);
      controls.push({entry, button});
    }
    const url = new URLSearchParams(location.hash.split('?')[1] || '');
    const saved = optimizer.combinations.find(item => item.id === Number(url.get('combination')));
    const savedSize = saved?.sizes.find(size => size.micros === Number(url.get('size')));
    const first = optimizer.ranking[0] || optimizer.unranked[0];
    if (saved && savedSize) open(saved, savedSize.micros);
    else open(optimizer.combinations[first.combination - 1], first.micros);
  }

  window.propDeskBasket = {setup, render, renderOptimizer, plot, strategyIdentity,
    interval:dates => `${dates[0]} to ${dates.at(-1)} · ${dates.length} observed sessions`};
})();
