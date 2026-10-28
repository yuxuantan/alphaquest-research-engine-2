# Audit of funded sizing: fed437c6d2944703b94eb45484a7039d

Date: 2026-10-28 (Asia/Singapore). Audited production commit:
`a4a3a6be8992bd3a359bddfe67babece02227569`.

**Verdict: the saved arithmetic is reproducible, but the selected 20 MNQ is not a
validated optimum and the current model is not fully qualified against current
published Apex rules.** No simulator code, report, source data or production
analysis was modified or submitted. The 14 saved report artifacts retained their
original hashes. The browser used GET requests only. All new calculations used
the report's original IS training portion; research OOS was not evaluated.

## Scope and source identity

Report: `http://127.0.0.1:8000/#backtests/prop/job/fed437c6d2944703b94eb45484a7039d`.
Source backtest: `404e70186bde41df90f2c4a4912a8013`, research phase IS.
Report JSON SHA-256:
`701e659594cd917fc2760cf483a558fc834a11f062d68adb7280b93112742edd`.
The report's captured production-source hashes and compiled-kernel fingerprint
match the executing implementation exactly. The native source CSV hash matches
its captured hash, and all 771 trades/costs reconcile without another deduction.
No measured MAE or MFE is present for any of those trades.

The internal training sample is 2017-05-22 through 2021-11-08 (1,166 weekdays).
The saved selected-size validation sample is 2021-11-09 through 2023-10-10 (501
weekdays). Both are inside the research IS. The external research OOS starts
2023-10-11 and was not used in this audit. Do not compare the training table's
71.1667% drawdown rate at 20 directly to the selected-size holdout's 34.045%:
they describe separate periods and 3,000 versus 20,000 paths respectively.

## 1. Confirmed search restriction with material effect

`native_analysis.py:235` constructs only sizes 1 through `min(20,max_micros)`.
The configured `MAX_TOTAL_NQ=4` allows 40 micro-equivalents. This 20 ceiling is
an extra search restriction, not the user's maximum or the funded account's
ultimate permitted tier. The account simulator already clamps actual size to
its current tier. A request for 40 starts at 20 and can grow to 30/40 later.
That structure agrees with the current [Apex PA scaling description](https://apextraderfunding.com/help-center/additional-helpful-items/scaling-levels-pa-explained/).

I reran points 1, 10, 19 and 20 with the original counts/seeds/kernel; every saved
training statistic matched exactly. I then evaluated 21 through 40, using the
same 3,000 lifetime and 3,000 first-year accounts per point, original training
rows and seed 42. No validation period was used to choose the diagnostic winner.

| Requested MNQ | Annualized net / slot | Lifetime payout | Drawdown failure | Inactive closure | Completed all 6 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | -1,895.73 | 0.00 | 0.00% | 100.00% | 0.00% |
| 10 | 2,607.97 | 1,325.50 | 80.97% | 17.07% | 1.93% |
| 20 | 4,625.97 | 2,907.50 | 71.17% | 18.83% | 10.00% |
| 25 | 5,066.53 | 3,276.00 | 67.40% | 19.40% | 13.20% |
| 30 | 5,652.57 | 3,663.00 | 63.03% | 19.73% | 17.23% |
| 40 | 6,985.55 | 4,120.00 | 59.53% | 18.17% | 22.30% |

40 is highest in this diagnostic extension, improving the unchanged model's
selection objective by **51.01%** over 20. This establishes that the omitted
candidates matter; it does not establish that 40 is suitable real-account sizing.
It remains a training estimate under the audited assumptions. A future fix should
honor the feasible user/tier limits and disclose when a winner lies on a search
boundary. The evaluation grid independently stops at 20 plus a capped 25 endpoint,
so that stage also needs an explicit search-range specification.

## 2. Lower drawdown failure at larger size can be internally coherent

The selection is `max(slot_year)`, not a multi-objective minimum-drawdown search.
There is no drawdown-rate constraint in that argmax. Even in the saved table,
20 is not the minimum drawdown row: 1 MNQ has 0% because every account closes
inactive before a drawdown failure. The rate rises to 80.97% at 10, then falls.

Drawdown, inactivity and completed-six-payout outcomes compete to terminate an
account. The [current payout rules](https://apextraderfunding.com/help-center/eod-trailing-drawdown-accounts/eod-payouts/)
close a PA after six payouts. A larger size may reach those fixed-dollar targets
and end exposure sooner. In this model the DLL also truncates large losing days,
while gains scale, and the account floor stops trailing after its lock threshold.
Consequently unconditional drawdown-failure probability need not rise with size.
This does not mean each individual trade has less risk.

Independent deterministic example, explicitly synthetic: 40 days of +300 per NQ,
followed by five large losing days. Both quantities receive the same source path.
10 MNQ is still trading and fails on day 44; 20 completes all six payouts on day
31 and has no subsequent exposure. An independent scalar ledger reproduces both
states, as well as 400 randomized adversarial state-transition cases.

The simulation does impose a 2,000-trading-day lifetime computation guard and a
separate 261-day first-year horizon. These are model horizons, not funded-account
expiry rules. At the saved 20 point no training/validation accounts remain open
at the lifetime guard, so censoring does not explain its decline in failure rate.

## 3. Confirmed qualification gaps

### Current inactivity policy is not modeled exactly

`Rules.inactivity_window=21` counts weekdays, whereas the [published inactivity
policy](https://apextraderfunding.com/help-center/billing/inactivity-policy-on-performance-accounts-pa/)
uses rolling 30 calendar days, including weekends/holidays and the purchase day.
`advance` also skips its check whenever today's profit reaches 50, even if only
one activity day exists in its rolling window.

A synthetic Friday-start counterexample is saved: purchase 2026-01-02; the only
50-profit day within its initial calendar window is 2026-01-30; the second is
2026-02-02, after the January 31 window end. The model stays open because it omits
weekend checks and lets a qualifying current day bypass closure. This cannot be
certified as enforcing the published initial 30-day rule. An exact implementation
needs dated calendar transitions rather than a generic weekday counter.

### Consistency equality differs from current published wording

The [payout text](https://apextraderfunding.com/help-center/eod-trailing-drawdown-accounts/eod-payouts/)
prohibits a single day comprising 50% or more of cycle profit. The model uses
`best_day <= 0.5 * cycle_profit`. With default rules, daily profits
2,000 / 500 / 500 / 500 / 500 produce a first payout of 1,500 on day five, despite
the largest day equalling exactly 50%. The existing engine test deliberately
preserves this inclusive boundary. Arithmetic parity with that test does not
qualify the boundary against the published rule.

### Intratrade risk is not measured in this report

All 771 trades use the close-only MAE fallback: adverse excursion is zero for
winning trades and the absolute realized loss for losing trades. A profitable
trade can cross the account floor before recovering. A saved synthetic probe
shows the identical winning close surviving with adverse=0 and failing with
adverse=500 per NQ. This is a demonstration of missing information, not a claim
that this excursion occurred in the actual source. Measured excursions or an
adequately specified event replay are needed to qualify real intratrade failure
probabilities. [Apex enforces its account floor intraday](https://apextraderfunding.com/help-center/eod-trailing-drawdown-accounts/eod-drawdown-explained/).

The model clips DLL liquidation exactly to the threshold. The [published DLL
explanation](https://apextraderfunding.com/help-center/additional-helpful-items/daily-loss-limit-explained/)
says liquidation is at market and can fill above or below it. This is an
optimistic execution assumption whose sizing impact needs separate sensitivity
qualification; it is not established by source-cost reconciliation.

### Annual net per slot is a fixed-economics renewal heuristic

The actual selection expression is:

```
261 * (mean lifetime payout - (49 / 0.525 + 129)) / (mean lifetime days + 5)
```

The saved selected-size evaluation instead reports a 76.135% validation pass rate
and 11.9461 mean funding-chain days. Those estimates are not used for training
selection: the model deliberately fixes 52.5% and five days. The UI discloses
that assumption, but the score is not an independently simulated first-calendar-
year net forecast. Any source-calibrated replacement objective must be estimated
on training data; using the later validation outcomes to choose a new size would
introduce selection leakage. Correcting the search ceiling alone does not
qualify this economic objective or the resulting position size.

The provider's scaling and DLL pages also differ by one dollar at the last tier
boundary (5,999 versus 6,000). This audit uses the model's existing 6,000 boundary;
that provider inconsistency requires clarification for an exact-rule version.

## Evidence and reproduction

Evidence directory: `artifacts/prop-sizing-audit-fed437c6-20261028/`.

- `audit-results.json`: source identity, original and extended results, explicit
  limitations and deterministic probes.
- `extended_training_sweep.csv`: full-precision unchanged-model diagnostics.
- `saved-sizing-default.png` and `saved-sizing-by-drawdown.png`: the actual saved
  portal table, including the 1-MNQ lowest-drawdown row. No POSTs were sent.
- `preservation-before.json` / `preservation-after.json`: all 14 original report
  artifacts match; no production numerical report was rewritten.
- `official-source-checks.json`: links and facts checked on the audit date.
- `focused-tests.log`: 15 existing engine/compiled checks passed; one unrelated
  full portal test was deselected. These checks qualify the chosen-model
  arithmetic, not current provider-rule fidelity.
- `reproduce-audit.py.txt`: complete standalone read-only reproduction script.

From the repository root, with the existing environment:

```bash
.venv/bin/python artifacts/prop-sizing-audit-fed437c6-20261028/reproduce-audit.py.txt
.venv/bin/python -m pytest -q tests/test_native_prop_engine.py \
  tests/test_native_prop_compiled.py -k 'not standard_count_portal'
```

Expected: source/kernel hashes match; 400 independent ledger cases and the
synthetic probes pass; original sizing points 1/10/19/20 reproduce exactly;
40 is highest in the extended training sweep at approximately 6,985.55 annualized
net/slot; all original saved files retain their hashes. The script writes only
audit evidence, never a production job or analysis. Browser instances were closed;
no temporary or persistent server was started/restarted for this audit.

Corrections should be introduced as a new qualified model version with explicit
search bounds, full terminal-outcome reporting and source/rule limitations.
Earlier reports/evidence must remain immutable.
