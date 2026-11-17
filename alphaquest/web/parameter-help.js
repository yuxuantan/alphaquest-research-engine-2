"use strict";
(() => {
  // Presentation copy only. Keep explanations out of numerical strategy files
  // so wording changes do not invalidate saved strategy/frozen-source hashes.
  const twin = {
    use_breakout: 'Enable the breakout (BO) setup: enter through a confirmed swing high or low. Momentum entries are controlled separately.',
    use_momentum: 'Enable the momentum (MO) setup: trade a crossing of the smoothed 10-minute oscillator during its entry window.',
    qty: 'Fixed contracts of the dataset instrument per trade. On NQ, 1 means one NQ contract; on MNQ, one MNQ contract. No automatic NQ/MNQ conversion.',
    bo_target_mult: 'BO profit-target distance = this multiplier × the 15-minute ATR frozen when the setup is armed, measured from the actual entry fill. Example: ATR 10 and multiplier 2 give a 20-point target before tick rounding. 0 disables the BO profit target.',
    bo_max_stop_mult: 'Cap the BO stop distance at this multiplier × the frozen 15-minute ATR, subject to tick rounding. This tightens the opposite-swing stop rather than rejecting the entry. Example: ATR 10 and multiplier 1.5 cap the planned distance at 15 points. 0 leaves the swing stop uncapped.',
    bo_atr_period: 'Number of completed 15-minute bars used for Wilder average true range (ATR). This volatility measure sets BO target distances and optional stop caps.',
    bo_vol_cap: 'Block BO setups when the most recently completed session’s high–low range exceeds this multiple of the average range of the preceding sessions. The lookback is Bo vol lookback. 2 means twice that average; 0 disables this filter.',
    bo_vol_lookback: 'Number of earlier completed session ranges used for the BO volatility-filter average, excluding the session being compared. The comparison needs this many earlier sessions plus the most recently completed session.',
    bo_session_open: 'Chicago session opening time in HHMM; 1700 means 17:00. Anchors the BO 15-minute and swing candles. Calendar-based session exits require 1700.',
    bo_session_close: 'Configured session closing time in Chicago HHMM; 1600 means 16:00. With Use session calendar on, the reviewed scheduled close supplies liquidation timing, including shortened sessions.',
    bo_last_fill: 'BO entry-order cutoff in Chicago HHMM; 1530 means 15:30. New stop-entry orders are submitted before this time and apply to the next observed bar; this is not a guarantee of a fill at the cutoff.',
    bo_exit_time: 'BO time exit in Chicago HHMM; 1545 means 15:45. Close an open BO position at the current bar Close once this time is reached. A scheduled session close can exit it earlier.',
    bo_pivot_tf: 'Duration in minutes of the session-aligned candles used to identify BO swing entry and stop levels. 360 means six hours. A swing is confirmed using three completed candles on each side.',
    mo_basis_len: 'EMA length, in completed 10-minute buckets, for the price basis at the centre of the momentum oscillator.',
    mo_range_len: 'Wilder true-range smoothing length, in completed 10-minute buckets. This volatility measure scales the momentum oscillator.',
    mo_signal_len: 'EMA smoothing length for the raw 10-minute momentum oscillator. 1 applies no additional smoothing; larger values smooth the oscillator more.',
    mo_trigger: 'Oscillator crossing threshold: a long signal crosses above +this value; a short signal crosses below its negative. This is an oscillator level, not price points or a percentage return.',
    mo_window_start: 'Earliest eligible completed 10-minute bucket end, inclusive, in Chicago HHMM. 840 means 08:40. An accepted signal submits entry for the next observed Open.',
    mo_window_end: 'Latest eligible completed 10-minute bucket end, inclusive, in Chicago HHMM. 930 means 09:30. This window filters signal times, rather than guaranteed fill times.',
    mo_exit_time: 'MO time-exit check starts at this Chicago HHMM time and runs through 16:00. 1450 means 14:50. Submit a market exit that fills at the next observed Open.',
    mo_stop_points: 'MO protective-stop distance from the actual entry fill, in instrument price points, rounded to the tick grid. 75 NQ points represent $1,500 per NQ contract or $150 per MNQ contract before costs.',
    mo_warmup: 'Minimum number of completed 10-minute buckets before MO signals are allowed. This is a bucket count, not minutes; it is separate from Max bars back.',
    mo_full_bars_only: 'Allow MO signals only from buckets containing exactly ten observed one-minute bars. Off also permits signals from partial buckets.',
    mo_allow_long: 'Allow long MO entries on upward oscillator crossings. The first eligible daily MO opportunity is still consumed when its direction is disabled, matching the strategy’s one-opportunity-per-day rule.',
    mo_allow_short: 'Allow short MO entries on downward oscillator crossings. The first eligible daily MO opportunity is still consumed when its direction is disabled, matching the strategy’s one-opportunity-per-day rule.',
    clock_shift: 'Minutes added to the Chicago strategy clock for time rules; source timestamps are unchanged. Use 0 for AlphaQuest close-labelled data. Nonzero values are for explicit legacy clock alignment.',
    debug_log: 'Write detailed BO setup and MO signal diagnostics to the application log.',
    immediate_protection: 'Activate the initial stop and any target immediately when the entry fills, following the declared intrabar price-path model. Off uses legacy next-bar protection and changes exposure on the entry bar.',
    max_bars_back: 'Skip this many leading one-minute records before BO/MO feature calculations start, for MultiCharts Max Bars Back alignment. Separate ATR and momentum warmup requirements still apply.',
    use_session_calendar: 'Use the reviewed NQ/MNQ holiday and early-close calendar to liquidate at the scheduled session Close. Requires session inputs 1700–1600. Off uses the configured fixed-clock session close.'
  };
  const catalogue = {twin_continuation: twin};
  const text = (strategyId, parameter) => catalogue[strategyId]?.[parameter.name] || parameter.description || '';
  function attach(cell, strategyId, parameter, prefix) {
    const description = text(strategyId, parameter);
    if (!description) return null;
    const help = document.createElement('small');
    help.className = 'field-help parameter-help';help.id = `${prefix}-${parameter.name}`;
    help.hidden = true;
    help.textContent = description;cell.title = description;cell.append(help);
    return help;
  }
  function describeInput(input, help) {
    if (!help) return;
    input.setAttribute('aria-describedby', help.id);
    input.title = help.textContent;
  }
  window.strategyParameterHelp = Object.freeze({text, attach, describeInput});
})();
