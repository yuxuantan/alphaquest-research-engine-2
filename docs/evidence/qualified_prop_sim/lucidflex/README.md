# LucidFlex 50K and the revised Prop Sim workflow — 12 November 2026

This increment adds a selectable LucidFlex 50K standard account alongside Apex
50K EOD in the actual **Prop Sim** page. Both still require one frozen campaign
configuration passing mechanics, IS Broad, IS Narrow, current OOS and current
Monte Carlo. All sizing uses IS history, with prior OOS access disclosed.

## Normal-product synthetic calculation evidence

The following files use a **labeled synthetic NQ dataset**, created through the
normal dataset/campaign/backtest flow, passing the real full-period Monte Carlo
gate. They are model outputs, not market performance or future forecasts:

- `SYNTHETIC-source.csv`, `prop-sim.json`, `journey.json` preserve the source,
  qualification, profile and reproducible request.
- `configuration-portal.png` shows Lucid selected, its actual 40/40-MNQ limits,
  scenario fee, zero activation, independent ranges and source check controls.
- Evaluation/Funded `*-report.json`, `*-results.csv`, `*-analysis.zip` are the
  existing numerical owners' actual durable reports and exports.
- `evaluation-pareto.svg` and both `*-portal.png` show the actual results,
  inspection controls and sorting. No alternate API, engine or report store
  was created to generate these files.

Reproduce from the repository root, writing new output outside this evidence:

```sh
ALPHAQUEST_PROP_SIM_EVIDENCE_DIR=/private/tmp/lucidflex-reproduction \
  .venv/bin/python -m pytest -q \
  'tests/test_prop_sim_browser.py::test_prop_sim_qualified_single_configuration_real_results_and_downloads[lucidflex]'
```

The browser journey opens a real qualified IS backtest report, follows Configure
prop analysis, chooses LucidFlex 50K, checks source/settings, runs both phases,
navigates away, reopens, sorts each table, inspects/downloads the Pareto chart,
downloads CSV/JSON/ZIP and returns through Job history/reload. Its temporary
server stops at teardown. The saved source/candidate IDs belong to that isolated
catalogue; files remain inspectable after its server stops.

The scenario is 1–3 MNQ in each phase; 32 paths per size; seed 42; five-weekday
blocks; start 2026-11-16; Evaluation fee 80.50 USD; no activation fee; replacement
MNQ commission 0.50 USD per side; daily loss limit enabled; 90-day Funded horizon;
two-calendar-day modeled receipt delay; no additional Funded breach cap.

Independent expected observations for **each** size:

- Evaluation: all 32 acquisition chains complete, purchasing **36 accounts** in
  total and paying **2,898 USD**. Thus mean cost is `2898 / 32 = 90.5625 USD`, and
  mean attempts `36 / 32 = 1.125`. Their elapsed times sum to **761 calendar
  days**, so mean time is **23.78125 days**; P90 is **50 days**. First attempts
  pass in **29/32** paths. Cost is the direct mean paid fees; dividing 80.50 by
  the first-attempt pass fraction would be a different estimator and is not used.
  All three sizes tie and remain on the frontier at one shared chart coordinate.
- Funded: all 32 starts total **79,200 USD received**, **1,800 pending** and
  **90,000 gross account deductions**. Means are **2,475**, **56.25** and
  **2,812.5 USD** respectively. `79200 + 1800 = 0.9 * 90000`: trader entitlement
  is 90% of account withdrawals and pending entitlement is not received cash.
  Median receipts are **1,800**, P10 zero, first-payout probability **22/32**,
  inactivity **19/32**, and breach zero. Exact ties are disclosed in the ranking.

## Actual local-library UI inspection

`actual-*` files are separately labeled **real saved local-library** evidence,
not the synthetic fixture above:

- `actual-setup-desktop.png` / `actual-setup-mobile.png`: account selection,
  grouped phases, optional DLL, collapsed advanced controls and preflight limits.
- `actual-results-desktop.png` / `actual-results-mobile.png`: completed Lucid run
  `64f1f4603bdf40e9b776b3668cd1e227`, normal results-first page, profile/source
  identity, phase navigation and controls. It uses the previously qualified VWAP
  configuration, 1–10 MNQ and 128 paths per size/phase, without changing prior
  backtests or results.
- `actual-ui-verification.json`: run/profile, report digests, mobile overflow,
  mutation requests, browser errors and historical Apex reopening observations.

Open `http://127.0.0.1:8000/#prop-sim?analysis=64f1f4603bdf40e9b776b3668cd1e227`
to inspect the saved real Lucid run. Existing Apex reports, including
`5d5d999ba9a5479183fbe66cbeb04576`, remain readable with their original inputs.
The read-only browser review launched no additional jobs or server.

## Focused numerical and rejection checks

```sh
.venv/bin/python -m pytest -q tests/test_lucid_calendar_acquisition.py tests/test_prop_sim.py
.venv/bin/python -m pytest -q tests/test_evaluation_optimization.py tests/test_funded_optimization.py
```

Independent small calendar oracles prove three +1,000 USD sessions meet a 3,000
USD target with 40% consistency: Friday/Monday/Tuesday pass, Wednesday readiness
is five calendar days from Friday; a Monday closure shifts readiness by one day.
Thirty calendar days of inactivity expire an account on a closed Sunday without
inventing a traded session. The optional daily stop can turn a two-trade day
into a loss/breach, while DLL-off permits its net positive day; every retry fee
is retained. A calendar computation guard censors an active account instead of
calling it a provider failure. Unsupported weekday guards reject.

API integration checks both profiles' actual source check/run/export/reopen
flow, profile cache separation, fee-versus-Funded independence, 41-MNQ rejection
for Lucid, unknown profiles and nonzero Lucid activation rejection, qualification
forgery, report integrity, cancellation-compatible workers, and preserved Apex
results. Numerical source files remain in implementation identity; old reports
are retained, and incompatible frozen numerical packages are not silently
re-launched with changed code. Browser tests also verify dense Pareto points,
resource warnings and mobile empty-source boundaries. No full legacy suite was
run for this increment.

## Supported profile and modeling boundaries

Lucid uses the standard **40%** Evaluation consistency option, optional DLL
(on/off), 40-MNQ ceiling in both phases, no provider Evaluation expiry and zero
activation. The existing local fixed **1,200 USD soft DLL** remains an explicit
unverified amount assumption. The 50% consistency add-on is not implemented.
Funded reuses the existing 5 × 150 USD winning-day, 50%-of-profit withdrawal
(up to 2,000 USD), 90% share and five-payout simulated-stage model; live-account
profits/transition timing after that stage are not fabricated.

Evaluation now samples saved fixed-signal trades on declared scenario dates and
calls the existing Lucid session kernel, including weekends/closures for
inactivity. Fresh retry streams are independently seeded. Means require every
chain to reach readiness before numerical guards (default 3,650 calendar days /
10,000 attempts). Otherwise unconditional means are unavailable, while all
accrued fees and restricted observed durations remain reported. First/last
attempt details are bounded and labeled; totals include every attempt. Funded
has no Evaluation fee/probability/time in its inputs or selection.

Prices/commission/receipt delay are editable scenarios, not checkout or bank
settlement certification. Source signals remain fixed under account pauses;
held-OHLC risk is conservative bar data, not measured tick execution. Calendars
are declared weekdays/closures; next-open-session readiness and calendar receipt
lags are model conventions, not measured provider latency. No provider/live
numerical parity or future robustness is claimed.

Primary documentation reviewed for this increment:
[Evaluation](https://support.lucidtrading.com/en/articles/12945790-lucidflex-evaluation-account),
[Customization](https://support.lucidtrading.com/en/articles/16226050-lucidflex-customization),
[Funded](https://support.lucidtrading.com/en/articles/12945795-lucidflex-funded-account),
[Payouts](https://support.lucidtrading.com/en/articles/12945796-lucidflex-payouts).
