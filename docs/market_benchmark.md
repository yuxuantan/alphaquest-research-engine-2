# Market benchmark: fixed long holding

New single, exhaustive and CLI backtests save a market comparison in the existing
backtest report. This is historical market research, independent of prop outcomes.
It does not certify a live trading edge. Intraday holding, risk-matched sizing,
ETF total return, beta/alpha estimation and executable futures roll accounting
remain later increments.

## Product journey

1. Open **Strategies → New backtest**, select the dataset/strategy and review the
   ordinary IS/OOS declaration.
2. Under **Account & costs**, set **Holding benchmark contracts** (default 1).
   For a fixed-size strategy, choose its contract quantity. For variable sizing,
   this remains an explicitly fixed reference; it is not automatically risk
   matched using the completed backtest. This quantity applies to every trial
   of an exhaustive batch.
3. Start the IS backtest and open **Market benchmark** in its completed report.
   Inspect the strategy/holding metrics, source checks and execution assumptions.
   The chart offers aligned mark-to-market equity or cumulative excess net P&L.
   Hover or focus it and press Home/End/arrow keys to inspect exact saved values.
4. Expand monthly/yearly comparisons or source checks. Download **Comparison
   JSON** and **Aligned equity CSV**. The existing trade-close chart, summary and
   exports retain their previous definitions.
5. Select **Run OOS with these parameters** explicitly when ready. The OOS run
   uses the selected IS report's saved holding quantity. Neither form edits nor
   an OOS request can override it. No OOS data enters an IS comparison. Repeated
   OOS inspection still reduces its usefulness as independent research evidence.
6. Reopening a comparison, including after restart or source-dataset deletion,
   reads saved artifacts only. Older reports show comparison unavailable and
   remain unchanged; they are not silently replayed or enriched.

The saved policy has version `price-series-holding-v1`. An IS report with an
unsupported benchmark version cannot silently use a new version for OOS/detail;
create a new IS report. A legacy IS report without a benchmark can still launch
its ordinary manually selected OOS run, which captures the default one-contract
comparison as part of that new run.

## Calculation contract and limitations

- A separate long account enters at the **first selected bar Open**, holds a
  predeclared fixed integer quantity, then exits at the **final selected Close**.
  The Open decision is predetermined before that bar; it uses no completed-bar
  signal. Even a single-bar selection pays both fills' slippage and commission.
- Native execution-account fill/mark arithmetic calculates the holding account.
  The strategy equity comes directly from the original execution event stream;
  its P&L is not reconstructed or charged costs a second time. Benchmark costs
  are its own costs, under the same point value, tick size, slippage, commission
  and starting account equity as the strategy.
- Every selected bar's post-fill equity is saved for both accounts, including
  open-position P&L and initial capital. Max drawdown and duration use every one
  of these observations. These are **bar-close**, not tick/intrabar, measurements.
  A final holding liquidation includes the exit costs in its terminal equity.
- Net return divides net P&L by starting account equity. Futures notional is not
  treated as invested cash or posted margin. Average/maximum notional samples
  post-fill bar closes, can miss intrabar peaks, and includes flat observations.
  Its leverage denominator is **starting capital**, not contemporaneous equity.
- Strategy exposure duration and quantity-weighted average contracts use saved
  fill-bar timestamps. The timestamps label closes even for Open/intrabar fills;
  they are not measured execution times. A zero-length period has unavailable
  duration percentages. The holding percentage is 100% over a nonzero selected
  timestamp interval. Same-bar trades can have zero recorded duration while
  still paying costs and contributing to maximum quantity.
- Monthly/yearly P&L sums changes in each account's marked equity, bucketed by
  the dataset's saved source timezone. It includes entry/exit costs exactly once.
  Only observed periods appear; gaps are not filled with invented prices/dates.
  Chart spacing uses elapsed UTC time. Preview downsampling retains endpoints
  and bucket minima/maxima of both accounts **and their difference**, but never
  supplies the input to any financial metric.
- All comparisons are labelled **price-series comparison; executable futures
  performance unverified**. The dataset contract does not establish individual
  contract identity, adjustment method, roll dates/prices/costs or corporate
  actions. A stitching gap can distort profit. No symbol/name heuristic supplies
  missing provenance. No dividend, cash-interest or borrowing cashflows are
  invented; futures carry already embedded in prices is not charged again.
- There is no margin/deleveraging/liquidation model. Nonpositive equity is
  explicitly flagged; arithmetic continues hypothetically. No CAGR, Sharpe,
  estimated alpha, automatic edge verdict or trading-readiness claim is emitted.
- The VWAP strategy's existing inferred-session-close lookahead and OHLC fill
  assumptions remain visible in saved strategy provenance. The benchmark does
  not make those historical assumptions causal or establish MultiCharts parity.

## Storage, API and implementation

`alphaquest/market_benchmark.py` observes native replay bars and validated equity
events through `execution.py`/`reporting.py`. The callback runs after any strategy
preparation, preserving VWAP's buffered session replay order. Recording and
drawdown calculations have bounded memory; monthly summaries grow by calendar
period only. Full bar-close CSV storage and hash verification add disk I/O.
The additional series also increases compact-report disk usage: the former
whole-folder 50-fold reduction versus full detail no longer describes a report
that includes this required per-bar download. Qualification preserves that
reduction check for the original native artifacts, verifies identical aligned
CSVs across compact/full modes, and records comparison bytes and total savings
separately. No original native account arrays are added to compact report JSON.

The same atomic backtest report publication saves two additional artifacts:

| Artifact | Contents |
| --- | --- |
| `market_benchmark.json` | Version, quantity, source backtest ID/dataset hash, selected dates, strategy provenance, execution settings, calculation-source hashes, source checks, assumptions, holding fills, metrics, monthly/yearly results and equity checksum. |
| `market_equity.csv` | Initial balance plus every selected bar's UTC label/Close, strategy equity, holding equity, excess P&L and post-fill contract quantities. |

The manifest/catalogue carries the specification and both artifact hashes.
Compact reports save the comparison CSV without requiring a full-detail replay;
their `per_bar_equity_retained` flag still describes the full native account
array inside report JSON. No dataset/report duplication or separate database is
introduced. Backtest and optimization reuse keys include benchmark settings and
verify the new files; corruption refuses reuse/display/download rather than
recomputing on a read. Existing report deletion removes these owned files using
the ordinary backtest deletion path.

`POST /api/backtests` and exhaustive `POST /api/optimizations` accept:

```json
{"market_benchmark":{"contracts":1}}
```

Omission means one contract; booleans, strings, fractions, nonpositive integers,
values above 9007199254740991 and unknown settings are rejected. OOS accepts only
its existing request UUID and inherits the IS quantity.

| Method/path | Behaviour |
| --- | --- |
| `GET /api/backtests/{id}/market-benchmark?max_points=1000` | Verified saved comparison and bounded chart (limit 16–2000); legacy returns an unavailable explanation. No replay or source-data read. |
| `GET /api/backtests/{id}/exports/market_benchmark` | Verified saved comparison JSON download. |
| `GET /api/backtests/{id}/exports/market_equity` | Verified full aligned CSV download. |

CLI: add `--benchmark-contracts 1` to the ordinary declared-IS command. Existing
output shortcuts continue to reference the single normal saved report directory.

## Reproduce the independent arithmetic through the portal

Use an isolated data directory to preserve all existing work. From the repository:

```bash
benchmark_demo_dir="$(mktemp -d /tmp/alphaquest-market-demo.XXXXXX)"
ALPHAQUEST_DATA_DIR="$benchmark_demo_dir" .venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 18027
```

Open `http://127.0.0.1:18027/`. Upload
`tests/fixtures/market_benchmark/SYNTHETIC-holding-IS-OOS.csv`, use a visibly
**SYNTHETIC** name/symbol, timezone UTC, tick size 0.25 and point value 20.
Validate, then save. In New backtest choose **Consecutive green hold**, green
count 1, hold 2 minutes, strategy contracts 1; starting capital 10000, slippage
1 tick per fill, commission 1 per side, holding benchmark contracts 1. Declare
IS **2026-01-05 through 2026-01-06**, OOS **2026-01-07 through 2026-01-08**, review,
then start IS.

Independent expectations are committed in
`tests/fixtures/market_benchmark/expected.json`:

| Observation | IS expected | OOS expected after manual execution |
| --- | ---: | ---: |
| Selected bars | 4 | 4 |
| Strategy net P&L | 168 | 368 |
| Holding net P&L | 188 | 388 |
| Excess net P&L | -20 | -20 |
| Strategy mark-to-market max drawdown | 226 | 226 |
| Holding mark-to-market max drawdown | 220 | 220 |
| Existing trade-close max drawdown | 0 | 0 |

Holding IS: `(109.75 - 100.25) * 20 - 2 = 188`. Strategy IS:
`(109.75 - 101.25) * 20 - 2 = 168`. Holding marks are
`10000 → 10014 → 9794 → 10194 → 10188`; its maximum loss is
`10014 - 9794 = 220`. Strategy marks are
`10000 → 9994 → 9774 → 10168 → 10168`; maximum loss is `10000 - 9774 = 226`.
The final holding exit costs are paid on January 6. OOS's different 1000+ prices
must have no effect on any IS result. All prices/outcomes here are synthetic.

Download both comparison files, refresh, and confirm identical contents. Run
OOS manually, inspect its phase/parent/quantity, and download again. In this
throwaway demo only, delete the source dataset and reopen the reports: both
comparisons/downloads remain available. Do not delete real datasets to exercise
this boundary. A second IS run with holding contracts 2 should show holding net
376; its manually executed OOS should show 776 without accepting quantity edits.
Entering zero in the form is invalid; the API also rejects invalid quantities.
Stop this demonstration server with **Ctrl-C**. No persistent server is started
by the automated qualification.

## Saved qualification evidence

The actual upload/configuration/report/OOS/download/reopen/mobile journey is
saved under `artifacts/market-benchmark-20261029/browser-02/` in
`test_actual_product_market_com0/`: screenshots, original synthetic input,
independent expectations, JSON/CSV downloads, verification record and durable
backtest catalogue/report files. Earlier failed attempts are preserved separately.
The final full-suite evidence is recorded in the qualification record under the
same date directory.

To repeat all checks and capture a new independent directory (never reuse an
existing pytest `--basetemp`, which pytest clears):

```bash
benchmark_review_dir="artifacts/market-benchmark-review-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$benchmark_review_dir"
.venv/bin/python -m pytest -q tests/test_market_benchmark.py tests/test_market_benchmark_browser.py --basetemp "$benchmark_review_dir/run" --junitxml "$benchmark_review_dir/checks.xml"
```
