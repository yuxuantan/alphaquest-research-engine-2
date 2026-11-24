"use strict";
(() => {
  const node = (tag, text, cls) => {
    const el = document.createElement(tag);
    if (text !== undefined) el.textContent = text;
    if (cls) el.className = cls;
    return el;
  };
  const link = (label, href) => {
    const anchor = node('a', label);
    anchor.href = href;
    return anchor;
  };
  const money = value => value == null ? '—' : Number(value).toLocaleString('en-US', {
    style:'currency', currency:'USD',
  });
  const rank = value => value == null ? '—' : Number(value).toFixed(1) + '%';
  const runUrl = id => '#prop-desk?analysis=' + id;
  const fileUrl = id => '/api/prop-analyses/' + id;
  const name = strategy => strategy.replaceAll('_', ' ');

  function controls(parent, job, request, members, combination=null) {
    const panel = node('section', undefined, 'panel prop-desk-panel prop-desk-diagnostic-controls');
    const select = node('select');
    for (const member of members) {
      select.add(new Option(name(member.strategy) + ' · ' + member.backtest_id.slice(0, 8), member.backtest_id));
    }
    const label = node('label', 'Strategy to diagnose');
    label.append(select);
    const basis = node('select');
    basis.add(new Option('Selected allocation', 'allocation'));
    basis.add(new Option('Standalone at 1 MNQ', 'standalone'));
    const basisLabel = node('label', 'Diagnostic sizing');
    basisLabel.append(basis);
    const allocation = node('p', undefined, 'field-help');
    const status = node('p', undefined, 'field-help');
    status.setAttribute('role', 'status');
    const run = node('button', 'Run strategy diagnostics', 'button secondary');
    run.type = 'button';
    panel.append(node('h2', 'Strategy diagnostics'), label, basisLabel, allocation, run, status);
    if (combination !== null) panel.append(node('p',
      'Luck Alone is pending verification of Bridge’s sampling and aggregation rules.', 'field-help'));
    parent.append(panel);
    let size, targets, busy = false;
    const refresh = () => {
      const standalone = basis.value === 'standalone';
      const target = standalone ? 1 : targets[select.selectedIndex];
      run.disabled = busy || !target;
      allocation.textContent = standalone ? '1 MNQ · standalone saved trades across the verified strategy history' : target
        ? `${target} MNQ from this tested allocation · standalone saved trades`
        : 'Zero target for this strategy. Select a larger tested size or another member.';
      if (!busy) status.textContent = '';
    };
    select.onchange = refresh;
    basis.onchange = refresh;
    run.onclick = async () => {
      busy = true;
      refresh();
      status.textContent = 'Verifying the saved strategy and allocation…';
      try {
        const saved = await request('/api/prop-desk/diagnostics', {
          parent_id:job.id, source_backtest_id:select.value, micros:size, combination,
          ...(basis.value === 'standalone' ? {size_basis:'standalone'} : {}),
        });
        if (panel.isConnected) location.hash = runUrl(saved.id);
      } catch (error) {
        busy = false;
        refresh();
        status.textContent = error.message;
      }
    };
    return (newSize, newTargets) => {
      size = newSize;
      targets = newTargets;
      refresh();
    };
  }

  function parentLink(configuration) {
    const params = new URLSearchParams({analysis:configuration.parent_id, size:configuration.micros});
    if (configuration.combination !== null) params.set('combination', configuration.combination);
    return link(configuration.combination === null ? '← Simulation result' : '← Optimise result',
      '#prop-desk?' + params.toString());
  }

  function sampleSteps(start, end) {
    const count = Math.min(end - start, 500);
    return count > 0
      ? Array.from({length:count + 1}, (_, i) => start + Math.round(i * (end - start) / count))
      : [start];
  }

  function conePanel(parent, data, model, metrics) {
    const panel = node('section', undefined, 'panel prop-desk-panel');
    const title = 'Equity against the Monte Carlo';
    const chart = node('div');
    const switcher = node('div', undefined, 'prop-desk-actions');
    const whole = node('button', 'Whole history', 'button secondary');
    const since = node('button', 'Since OOS started', 'button secondary');
    whole.type = since.type = 'button';
    if (data.oos_trades) switcher.append(whole, since);
    const count = data.cone.horizon_trades;
    panel.append(node('h2', title),
      node('p', `${model.cone_paths.toLocaleString()} paths · ${count} closed trades per path · Seed ${model.seed}. ` +
        (data.oos_trades ? 'The IS draws are compared with the strategy’s observed OOS outcomes.'
          : 'IS only. The illustrative projection begins at the last observed IS trade.'), 'field-help'),
      switcher, chart);
    parent.append(panel);
    function draw(oosOnly) {
      whole.setAttribute('aria-pressed', !oosOnly);
      since.setAttribute('aria-pressed', oosOnly);
      chart.replaceChildren();
      const anchor = data.is_trades;
      const start = oosOnly ? anchor : 0;
      const offset = oosOnly ? data.is_net : 0;
      const points = new Map(data.cone.points.map(point => [anchor + point.trade, point.bands]));
      const positions = [...new Set([...sampleSteps(start, anchor), ...points.keys()])].sort((a,b) => a-b);
      const band = index => positions.map(i => points.has(i) ? points.get(i)[index] + data.is_net - offset : null);
      const observed = positions.map(i => i > data.curve.length ? null
        : (i ? data.curve[i - 1].equity : 0) - offset);
      const series = [
        {label:'5th–95th percentile', lower:band(0), upper:band(4), color:'#3689b0', opacity:.16},
        {label:'25th–75th percentile', lower:band(1), upper:band(3), color:'#327ca5', opacity:.27},
        {label:'Median', values:band(2), color:'#216594', dashed:true},
        {label:'Observed equity', values:observed, color:'#b66a17', dashed:false},
      ];
      window.propDeskBasket.plot(chart, positions.map(i => 'Trade ' + (i - start)), series, {
        positions, dots:false, format:value => '$' + Math.round(value).toLocaleString(),
        title:'Strategy equity and Monte Carlo percentile bands',
        marker:data.oos_trades && !oosOnly ? positions.indexOf(anchor) + 1 : null,
      });
      const terminal = data.cone.points.at(-1).bands;
      metrics(chart, [
        ['5th percentile P&L', money(terminal[0])], ['Median P&L', money(terminal[2])],
        ['95th percentile P&L', money(terminal[4])],
        ['Observed OOS P&L', money(data.observed_oos_net)], ['OOS endpoint percentile', rank(data.cone.observed_endpoint_percentile)],
      ]);
    }
    whole.onclick = () => draw(false);
    since.onclick = () => draw(true);
    draw(false);
  }

  function drawdownPanel(parent, data, model, metrics) {
    const panel = node('section', undefined, 'panel prop-desk-panel');
    const positions = [...new Set([...sampleSteps(0, data.curve.length), data.is_trades,
      ...data.episodes.map(episode => episode.trough_trade)])].sort((a,b) => a-b);
    panel.append(node('h2', 'Drawdown since the last high'), node('p', model.drawdown_basis, 'field-help'));
    parent.append(panel);
    const lines = [{label:'Observed drawdown', values:positions.map(i => i ? data.curve[i - 1].drawdown : 0)}];
    if (data.matrix.length) {
      lines.push(...[[0, 'Warning reference'], [4, 'Critical reference']].map(([i,label]) => ({
        label, values:positions.map(trade => trade >= data.is_trades ? data.matrix[i].drawdown_usd[2] : null),
      })));
    }
    window.propDeskBasket.plot(panel, positions.map(i => 'Trade ' + i), lines, {
      positions, dots:false, format:value => '$' + Math.round(value).toLocaleString(),
      title:'Trade-close drawdown in US dollars',
      marker:data.oos_trades ? positions.indexOf(data.is_trades) + 1 : null,
    });
    const latest = data.episodes.at(-1);
    metrics(panel, [
      ['Current drawdown', money(data.current_drawdown)], ['Maximum drawdown depth', money(data.maximum_drawdown)],
      ['Longest drawdown', data.longest_drawdown_trades + ' trades'],
      ['Latest recovery', latest ? latest.recovered_at == null
        ? 'Open at last trade' : 'Recovered at trade ' + latest.recovered_at : 'No drawdown'],
    ]);
    const matrix = node('section', undefined, 'panel prop-desk-panel');
    matrix.append(node('h2', 'Drawdown and rolling sum'));
    parent.append(matrix);
    if (!data.matrix.length) {
      matrix.append(node('p', `The simulated matrix requires at least ${model.minimum_matrix_trades} saved OOS closed trades.`));
      return;
    }
    const drawdown = node('button', 'Drawdown', 'button secondary');
    const sum = node('button', 'Sum', 'button secondary');
    const switches = node('div', undefined, 'prop-desk-actions');
    drawdown.type = sum.type = 'button';
    switches.append(drawdown, sum);
    const detail = node('p', undefined, 'field-help');
    const region = node('div', undefined, 'prop-desk-ranking-scroll');
    region.setAttribute('role', 'region');
    region.setAttribute('aria-label', 'Simulated trade horizon comparisons');
    region.tabIndex = 0;
    matrix.append(switches, detail, region);
    function draw(sums) {
      drawdown.setAttribute('aria-pressed', !sums);
      sum.setAttribute('aria-pressed', sums);
      detail.textContent = `${model.matrix_paths.toLocaleString()} draws from OOS trades · Seed ${model.matrix_seed}. ` +
        (sums ? 'The observed sum uses the last N held-out trades when available.'
          : 'Percentile is the share of simulated drawdowns shallower than the last observed drawdown.');
      const table = node('table');
      const header = table.createTHead().insertRow();
      for (const heading of ['Trades', 'Observed', '5th', 'Median', '95th', 'Percentile']) {
        const th = node('th', heading);
        th.scope = 'col';
        header.append(th);
      }
      const body = table.createTBody();
      for (const row of data.matrix) {
        const line = body.insertRow();
        const values = sums ? [row.observed_sum, ...row.sum_usd] : [data.current_drawdown, ...row.drawdown_usd];
        for (const value of [row.trades, ...values.map(money), rank(sums ? row.sum_percentile : row.drawdown_percentile)]) {
          line.insertCell().textContent = value;
        }
      }
      region.replaceChildren(table);
    }
    drawdown.onclick = () => draw(false);
    sum.onclick = () => draw(true);
    draw(false);
  }

  async function render(panel, job, request, metrics) {
    const report = job.report;
    const config = report.configuration;
    const {model, windows} = report.diagnostics;
    const base = fileUrl(job.id);
    const download = node('div', undefined, 'prop-desk-actions');
    download.append(link('Strategy trades CSV ↓', base + '/files/strategy_trades.csv'),
      link('Diagnostic values JSON ↓', base + '/files/strategy_diagnostics.json'),
      link('All evidence ZIP ↓', base + '/downloads/analysis.zip'));
    const source = link(name(report.source_summary.strategy) + ' · ' + config.source_backtest_id.slice(0,8),
      '#backtests/report/' + config.source_backtest_id);
    const metadata = node('section', undefined, 'panel prop-desk-panel');
    const standalone = config.size_basis === 'standalone';
    metadata.append(parentLink(config), node('h2', 'Strategy diagnostics'), source,
      node('p', standalone ? 'Standalone at 1 MNQ · parent sizing stays fixed'
        : `${config.allocated_mnq} MNQ allocated · Weight ${config.weight} · ${config.micros} total tested MNQ`),
      node('p', model.trade_basis + ' ' + model.cost_basis, 'field-help'),
      node('p', 'IS · ' + window.propDeskBasket.interval(windows.is), 'field-help'));
    if (windows.oos) metadata.append(node('p', 'OOS · ' + window.propDeskBasket.interval(windows.oos), 'field-help'));
    metadata.append(node('p', model.sampling, 'field-help'), download);
    panel.replaceChildren(metadata);
    const status = node('p', 'Opening saved diagnostic charts…', 'field-help');
    status.setAttribute('role', 'status');
    metadata.append(status);
    try {
      const data = await request(base + '/files/strategy_diagnostics.json');
      if (!panel.isConnected) return;
      status.remove();
      metrics(metadata, [['IS trades', data.is_trades], ['OOS trades', data.oos_trades], ['Net P&L', money(data.net)]]);
      if (data.oos_trades) {
        const comparison = node('section', undefined, 'panel prop-desk-panel');
        comparison.append(node('h2', 'Held-out trades versus backtest'));
        metrics(comparison, [['IS net per trade', money(data.is_net / data.is_trades)],
          ['OOS net per trade', money(data.observed_oos_net / data.oos_trades)],
          ['IS net', money(data.is_net)], ['OOS net', money(data.observed_oos_net)]]);
        panel.append(comparison);
      }
      conePanel(panel, data, model, metrics);
      drawdownPanel(panel, data, model, metrics);
      if (data.held_out_status) {
        const saved = data.held_out_status;
        const review = node('section', undefined, 'panel prop-desk-panel');
        review.append(node('h2', 'Held-out strategy status'), node('p', saved.basis, 'field-help'));
        metrics(review, [
          ['Status', saved.status], ['Current drawdown', money(saved.drawdown)],
          ['Deepest since the high', money(saved.deepest_since_high)],
          ['Warning line', money(saved.warning_line)], ['Critical line', money(saved.critical_line)],
        ]);
        review.append(node('h3', 'Status changes'));
        const changes = node('ol');
        for (const transition of saved.transitions) changes.append(node('li',
          transition.date.slice(0, 10) + ' · Trade ' + transition.trade +
          ' · ' + transition.status + ' · ' + transition.reason + ' · ' + money(transition.drawdown)));
        review.append(saved.transitions.length ? changes : node('p', 'No status changes in this history.', 'field-help'));
        panel.append(review);
      }
    } catch (error) {
      status.textContent = error.message;
    }
  }

  window.propDeskDiagnostics = {controls, render};
})();
