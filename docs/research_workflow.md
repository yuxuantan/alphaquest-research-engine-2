# Editable IS / OOS research workflow

The prop configuration page now uses a [goal-led guided flow](prop_setup.md), with the existing all-settings view available for dated examples.

Start with the [complete campaign walkthrough](#first-complete-campaign-a-practical-walkthrough).
The [acceptance checklist](robust_research_plan.md#final-acceptance-record) records
current repository qualification separately from each study's evidence.

## External trade imports

Open **Strategies → Import trades**, select a complete
[`aq-trade-export-v1` JSON export](designs/trade_export_v1.md), and **Check import**.
Review counts, exact cost reconciliation, original hash, time/session conventions,
research declaration and risk coverage before **Save imported report**. Saving
uses the ordinary report catalogue; importing identical bytes returns the same
report. Reusing an export ID with changed bytes rejects. A partial export or
inconsistent cost/event/completion record cannot be saved.

The saved report contains actual trade-close equity, source currency, original
trade IDs and downloadable original/canonical files. It does not invent market
bars, a holding benchmark, native risk replay or an untouched OOS split. Exported
IS/OOS/prior-access declarations are retained as exporter claims. A matching
declared dataset hash does not link the import to an unrelated local dataset.

Use **Configure prop analysis → Check source** for model eligibility. The current
annualized route requires complete ordered marks, declared no-trade sessions,
supported intraday USD NQ/MNQ trades and explicit path-invariance assumptions.
Review the reason if unavailable; importing does not certify simulation or live
readiness. For an eligible source, choose source/override commissions, run the
normal analysis, then reopen/export the immutable report and its captured input
files. Eligible exporter-declared IS sources can also create independent phase
campaigns with explicit policies as described below. Native nested backtest
reruns and automatic external OOS generation remain unavailable. The [saved synthetic journey](prop_simulation_review.md#canonical-external-trades-and-local-prop-analysis--2026-11-08)
includes exact inputs, expected arithmetic and rejection examples.

## Phase sizing policies

To remove an obsolete independent phase campaign, open **Research → Manage
campaign → Delete campaign**. Review the number of references being released.
Source backtests, saved reports and prior-access history are kept. Frozen,
assessed, active or dependent campaigns remain protected with the blocking IDs
shown. Once its references are released, use the ordinary backtest delete action
if you also want to remove a source. See the [deletion contract](research_campaign_api.md#remove-an-unused-phase-campaign).

From **Configure prop analysis → Compare qualified candidates**, choose Evaluation or Funded in Accounts and sizing. Each
source row defaults to the existing fixed-size list. Choose **Compare sizing
policies** to add fixed contracts, fixed dollar risk or percentage risk. The
same size list becomes hard MNQ caps; checking expands every declared source,
trial, cap and policy without truncating membership. Signal parameters remain
the saved configurations; sizing does not reoptimize them.

For percentage risk choose **initial configured capital**, **current account
balance**, or **available drawdown cushion**. Supported accounts start with
$50,000 configured capital; the source backtest's initial equity is not the prop
account balance. Current balance changes after profits, losses and account
deductions. Cushion is current equity minus the applicable account floor, with
the provider's session trail/tier timing retained. Declare planning commission,
entry slippage and stop-exit slippage explicitly. These affect the planned loss
denominator only; source P&L already includes its observed costs.

Whole contracts round down from risk budget divided by stop distance × MNQ point
value plus planned loss-side costs. Minimum/maximum contracts and optional
account/daily cushion constraints are explicit. A constraint protects planned
loss strictly below a touched floor; it is not a guarantee against gaps. Zero
quantity skips the opportunity with no costs or activity, while the account's
calendar still advances. Inspect aggregate counts and retained per-trade
decisions in the normal phase report and `sizing_decisions.csv` download.
When detail retention is bounded, complete aggregate counts remain available and
the report says which detail was retained; simulation membership is unchanged.

Risk policies require causal initial stops, decision reference prices and an
admitted invariant source path. External declarations remain unverified
assumptions. New native reports capture signal/stop decisions separately from
later fills, but native strategies may change behavior after a skipped/resized
position and therefore require a suitable rerun. Missing stops, unsupported
timing or signal dependence reject explicitly. Fixed unguarded native policies
retain the existing fixed-path scenario. Freezes retain the entire policy and
planning configuration. Imported packages can be frozen/downloaded, but cannot
launch a native OOS rerun for an external strategy.

## Nested inner research

Implementation increment, 7 November 2026: open a completed IS backtest,
**Configure prop analysis → Find a robust strategy, size and account**. Use the Sources and Research design steps; **Show all settings for this task** exposes the named nested sections used in older examples.
Choose saved IS reports or whole saved grids to declare the candidate parameter
set. Existing full-period performance does not enter qualification. All sources
must share dataset identity and execution costs; duplicates and OOS candidates
reject. Previously accessed development data is disclosed, not called untouched.

1. Name the research and select configurations. This increment uses each
   strategy's saved quantities; one source-sizing configuration is required per
   strategy. Quantity knobs and display switches cannot manufacture neighboring
   signal configurations. Declare independent prop policies separately under
   **Economic validation**, after the inner qualification controls.
2. Declare rolling or expanding outer training/test lengths and inner
   training/validation lengths, in observed Chicago session dates. Each session
   begins at 17:00 Chicago local time. Purge and embargo are consecutive buffers
   between retained training and validation; both count observed sessions.
3. Review the qualification requirements before running. Thresholds are
   research-specific, not universal. Small samples, missing required scenarios
   or regimes, unresolved bootstrap tails and missing neighbors produce
   **INSUFFICIENT_EVIDENCE**. Net cash stress adds the declared amount once per
   completed trade; baseline costs are already included.
   Under **Execution scenarios**, add named commission/slippage/stop/limit
   assumptions for actual validation reruns. Every selected scenario must pass
   the declared scenario threshold. Under **Market conditions**, choose labels
   to assess and separately choose those required for your hypothesis. Optional
   regimes remain visible but do not veto a specialized strategy.
4. **Preview dates and source checks** shows every outer/inner window, excluded
   sessions and exact backtest count. Large plans require that count to be
   confirmed. **Save and run** freezes the declaration and creates normal
   backtests restricted to each inner window, with cold strategy/feature state.
5. Inspect every PASS/FAIL/INSUFFICIENT_EVIDENCE row, the complete approved set,
   reasons, sample counts, historical uncertainty and neighboring configurations.
   Expand the evidence to inspect actual scenario returns, causal condition
   coverage, unknown labels, training calibration and descriptive complexity.
   Open individual backtests or download the ordinary AnalysisStore JSON/CSV/ZIP.
   Saved research history reopens without recomputation. Cancellation stops at a
   safe checkpoint; Run resumes completed backtests after checking their hashes.

With Economic validation disabled, the run stops at inner qualification and no
outer test is launched. With it enabled, the following stage runs from the same
saved declaration. The later native-execution, complete-procedure and forward
observation sections describe their implemented extensions. Local repository qualification passed the complete 2,315-test suite on 8 November
2026; see the [acceptance record](robust_research_plan.md#final-acceptance-record).
Each study still reports its own evidence sufficiency and no winner is forced.

### Nested economic validation

8 November 2026: enable Evaluation, Funded, or both under **Economic validation**.
Declare account profiles, fixed MNQ policy quantities, costs, sampling and seeds.
The full PASS configuration set is crossed with every declared profile and
policy. There is no second signal-parameter search and no hidden top-N reduction.
This initial fixed-path increment rejected native risk-based sizing. The later
[Native policy search and actual later observations](#native-policy-search-and-actual-later-observations) extension below now
reruns supported complete-minute MNQ/VWAP strategies inside account state for
fixed-dollar and percentage policies; unsupported source/profile combinations
still reject before research starts.

Evaluation retains the entire feasible cost/calendar-time Pareto frontier by
default. An explicit preference may minimize cost under a time cap, or time
under a cost cap. Pass-probability and cost/time limits apply before nondominance.
Exact ties remain together unless a phase-only configuration tie preference was
declared. Funded independently maximizes expected trader cash received from one
fresh funded account within the fold's horizon; it uses no acquisition inputs.

Preview shows the full work estimate and each fold's forecast dates. Every
funded horizon starts at its outer test's first session and ends the day after
the last observed session. Calendar closures are declarations, not inferred from
missing bars. Missing declared-open outer sessions reject instead of becoming
zero-trade days. Observed sessions without trades remain present.

Each admitted signal configuration gets a normal backtest on the full outer
training window. The phase forecast is a normal durable analysis. A sealed
selection journal captures the full selected family, parameters, rules, costs,
source identities, implementation and predeclared preference before any outer
strategy execution. Inner sources keep their explicit research role; they are
not relabeled public IS sources. Cancellation/resume verifies completed child
reports and source hashes before reuse.

The report separates training forecasts from **Historical chronological replay**:
one source path per frozen policy, in actual date order, with no reshuffling or
reselection. Evaluation retains failed purchase costs, retry waits, activation
payments and unresolved acquisition time. Readiness exactly at the numerical
retry guard can complete acquisition if it precedes the outer cutoff; no new
trade, purchase or fee occurs at that guard. The outer cutoff stays exclusive.
Funded starts fresh once and has no
replacement. Requests, account deductions, received cash and pending amounts are
separate. A receipt at the exclusive cutoff remains pending. The unrounded
entitlement convention matches the phase forecast; neither convention verifies
bank settlement.

The saved-trade-path execution mode produces fixed-signal-path account scenarios.
Account pauses/skips can alter a native strategy's future eligibility; that mode
does not establish a full strategy rerun. The native method described below
reruns supported strategy paths, while live execution remains unverified. Inspect **Provider rule review** and its dated primary
sources; unresolved discrepancies block production-qualified claims. No selected
outer-fold policy is a current deployment recommendation.

Download `economic_selection.json`, `chronological_replay.json`,
`research_journal.json` and the normal ZIP. Child phase reports include
`provider_rules.json`, full candidate membership, source captures and sizing
traces. Reopening uses saved artifacts. If qualification admits nothing, the
report saves an abstention seal and creates no selected-policy outer outcomes.
Separately declared references remain measurable as described below.

### Reliability and predeclared references

Declare reference policies before starting the nested campaign. Each names a
signal configuration from the declared candidate set, a same-phase account
profile and a fixed quantity/policy. Its normal training forecast and frozen
package are sealed before any selected or reference outer execution. A reference
is still measured if it fails edge qualification; it remains explicitly
ineligible for recommendation. References do not enter the optimizer's selection
set. The initial fixed-path version rejected native dynamic references; the
later native extension below performs their real account-controlled strategy
reruns and preserves the same predeclaration and phase-isolation rules.

The report's reliability section follows the changing selection procedure across
all declared outer folds. It shows coverage, matched forecast errors, actual
receipts or acquisition fees, censoring, reference differences and changes in
signal/sizing/profile choice. A retained family is one historical fold with
several alternatives. Its members remain inspectable without implicit weights,
an aggregate return or an outcome-selected winner. Missing forecasts do not erase
valid observed economics. Missing outer outcomes stay missing. By default an
abstention has unmeasured economics; the optional predeclared **No account, no
fee** action explicitly assigns zero cash and fees to such a decision.

Funded comparisons pair the same profile, costs, receipt convention, horizon and
historical fold. Pending cash and equity are not receipts. Evaluation expected
eventual acquisition cost/time is not compared as though it were the same
estimand as a censored finite-horizon attempt. Paid fees remain in totals, but
acquisition means require every action to finish. Completed-only reference pairs
are descriptive; incomplete pairings cannot establish a threshold result.

Reliability defaults require five outer blocks and complete fold coverage;
payout calibration requires twenty comparable unique-action blocks. These are
declared research assumptions, not universal certification. The circular
fold-output bootstrap requires at least two blocks and five expected draws in
each tail at the declared confidence. It does not refit the procedure and cannot
establish independent historical blocks. Increasing Monte Carlo paths does not
increase historical evidence. Shared regimes and overlapping training windows
remain limitations even when descriptive thresholds are met.

Funded selection additionally offers **Highest historical lower bound on expected
trader cash**. This explicit objective resamples verified historical session
blocks, re-estimates mean cash using the existing funded account owner, and
selects a nominal lower percentile of those means. It retains every declared
candidate in its family-tail adjustment. Session/block counts, tail resolution,
inner paths per start cohort and a declared Monte Carlo standard-error ceiling
must pass; otherwise selection is insufficient. Defaults require 60 observed
sessions and 12 blocks, 200 history replicates, 64 paths per replicate and a $25
standard-error ceiling. This estimates historical mean sensitivity, not a single
account's payout p10, a guaranteed future lower bound, or mean minus a nominal
Monte Carlo error bar. Ordinary public native phase searches without a verified
observed-session inventory report insufficient history; exporter coverage remains
a disclosed exporter assumption.

Download `reliability.json`, `reliability_folds.csv`, `baseline_comparison.csv`
and `baseline_results.json` from the same durable report. Conservative child
reports also capture `historical_mean_cash.json`, including exact historical
indices, seeds and schedule hashes. All reports remain research evidence;
`production_qualified` stays false. The later complete-procedure and observation
sections below implement final freeze, guarded holdout, fresh current selection
and independent monitoring as separate stages; they do not convert this
reliability report into a production certificate.

Execution scenarios change the existing execution engine's actual fills and
strategy callbacks. Additional commission is per contract per side; market
slippage is additional ticks per applicable fill. Stop exits add the separate
stop slippage, including opening gaps. Limit penetration requires the declared
number of ticks beyond the target; disabling price improvement fills eligible
opening targets at their limit. Existing conservative stop-first ambiguity
handling remains. These are deterministic OHLC sensitivities: queue position,
partial fills, depth and real fill probabilities are unverified. Saved run
metadata retains both baseline and resolved settings so detailed replay cannot
charge scenario costs twice. Zero/default assumptions retain baseline behavior.

Market conditions use bars strictly before each entry. Volatility and source
volume thresholds are fitted only to the inner training window, and validation
features start cold. Unknown warmup/insufficient-fit classifications remain
visible and prevent admission when that regime is required. Trend/range uses
predeclared directional efficiency; volatility uses point-based true ranges,
including instruments with nonpositive prices. Source volume is only a liquidity
proxy, not executable depth or spread evidence. Asia/Europe/US labels are saved
Chicago clock buckets, not claims about exchange opening hours. Regime means
are contributions per covered validation session, including zero contributions;
minimum regime sessions counts sessions with classified trades. Overlapping
labels must not be summed as independent results.

Complexity evidence records signal/sizing/display roles, varying signal search
dimensions and enabled optional entry filters. Optional declared limits can
reject an overly broad search or excessive filters. A limit requiring unreviewed
roles produces insufficient evidence. Simpler configurations are compared on
the same validation windows, with other-parameter confounding disclosed; no
universal complexity penalty or automatic winner is imposed. Cross-instrument
transferability remains untested by this same-dataset research increment.
Parameters of disabled controls cannot establish neighbors or distinct signal
candidates: for example, changing the ADX threshold while its filter is off is
not another tested signal. Equivalent numeric spellings are normalized for this
comparison while original source parameters/hashes remain unchanged. Reports
created programmatically with an existing execution scenario cannot supply a
new baseline or launch manual OOS, because those routes do not inherit arbitrary
scenario assumptions. Select the original baseline and declare research
scenarios explicitly.

Both manual source-date splits and these session-date folds retain their own
conventions. Boundary sessions that are only partially covered by the saved IS
report are excluded. Missing market sessions are not inferred from missing bars.
Every replay starts flat and cold and must complete normally; no position or
fitted state crosses a fold. These restrictions do not certify arbitrary
imported outcomes or unknown feature horizons. Bootstrap repetitions are
computation, not additional historical observations; intervals remain approximate
and may miss future regime/model/execution uncertainty.

The existing manual IS/OOS workflow below remains available unchanged.

Implementation update, 2026-11-06: [phase research campaigns](research_campaign_api.md)
compare saved IS backtests/trials across strategies and optimization jobs, expand
whole-MNQ sizes under a declared budget, run independent Evaluation/Funded
objectives, and freeze explicit IS choices. Open a saved report → Configure prop
analysis → Independent phase research campaigns → Save and check → Run → durable
results/downloads → Freeze. Original source links, access metadata and selection
provenance are retained in the existing catalogues/AnalysisStore.

Campaign selection never launches or inspects final OOS. After freezing, use
**Launch OOS with frozen settings** to invoke the existing ordinary OOS backtest
path from each selected IS parent and append an assessment-only phase report.
The server accepts only an idempotent request ID: parameters, sources, size,
profile/rules, costs, seeds, horizon and calendar cannot be overridden. Only the
source period moves to that parent's saved OOS window. Assessment uses OOS
observations to estimate the frozen model's acquisition cost/time or payouts/risk
under the same scenario calendar; it is not a chronological live-trading forecast.
No OOS ranking/frontier search or IS-package update occurs. Frozen named families
remain explicit; assessing several candidates does not permit choosing a new
winner while calling those observations untouched. Access metadata appears at
freeze and before each launch, including prior failed/interrupted attempts.
Ordinary automatic joint reports attached to OOS backtests are legacy outputs,
not independent phase assessments. Existing editable splits and unlimited manual
OOS remain unchanged. Automatic new-grid launch and adaptive refinement are planned.
Annualized joint sizing remains legacy business-level optimization. The dated
exact cash ledger remains implemented for one observed path/slot; portfolio
optimization remains optional later work. Historical sections below retain their
dated scope and are not claims that the completed ledger/phase backends are absent.

Every new portal/API/CLI backtest or optimisation requires a chronological split.
Choose explicit inclusive dates in the saved source timezone, or an IS percentage
strictly between 0 and 100. Percentage mode assigns complete chronological trading
dates with floor(IS% × date count) dates to IS. Both windows must contain bars;
IS end must precede OOS start, and all dates must lie within the dataset.

Split settings remain editable after a run. The latest submitted split is a form
prefill for the next IS run. Editing any split input requires Review IS/OOS split
again. A new submission saves its own split snapshot; earlier reports and active
optimisation jobs retain their recorded dates, settings and results. Previously
viewed data is not made untouched by changing a split.

## Campaign budgets and computation

Generate candidate strategies/parameters with ordinary IS grids, optionally
unchecking automatic legacy prop reports. Saved-trade-path campaigns reuse saved
trades/risk; native campaigns rerun the supported strategy for each declared
account path. Complete saved-source/job/trial × size/policy membership is counted
before execution; searches above 128 require explicit
confirmation of the exact count (128 is not a hard cap). Duplicates,
incomplete jobs, mismatched splits/costs and unsupported sources reject before
execution. Legacy Historical net is not a candidate pruning criterion. Failed or
rejected campaign revisions remain research history; OOS access is never erased.

Predeclare path counts, calendar/start cohort, costs, horizon/receipt assumptions,
constraints and seeds. A changed declaration is a new immutable campaign revision.
Check the complete candidate table, censoring and uncertainty before freezing.
The product records numerical settings and a rationale; research acceptance,
owner/time/spending limits and untouched-data claims still need independent
justification. Automatic new-grid generation and adaptive confirmation remain
unimplemented. [Exact resource/metric contracts](phase_optimization_plan.md#implemented-metric-and-selection-contracts).

## Manual OOS execution

1. Select dataset, strategy, split and settings, review the split and run IS.
   Initial backtests, exhaustive grids and their automatic prop analyses use IS
   only. No OOS job is scheduled automatically.
2. Open a completed IS report, including an individual optimisation trial.
3. Select **Run OOS with these parameters** and confirm. The server uses that
   report's saved OOS window, parameters and execution costs, even if a later IS
   run changed the form's split. To change them, run a new IS backtest first.
4. Inspect the ordinary durable OOS backtest and its automatic prop report.
   Configure → check source → run can reopen the saved prop analysis or use new
   prop settings on this manually executed OOS source.

There is **no OOS attempt limit**. Failed/interrupted requests stay in execution
history and do not prevent new requests. A request UUID remains idempotent:
network retries return the same saved result/status instead of duplicating work.
Legacy reports and OOS reports cannot launch an OOS backtest; select completed IS.
Full-detail and risk replays remain IS actions; another OOS replay requires manual
selection from IS. Source identity and strategy implementation checks remain.

Research metadata and execution history use the existing backtest catalogue.
Existing datasets, report files and historical attempts are preserved. No migration
or reset is needed: old three-attempt histories cease to enforce any limit.
Legacy full-history prop sources outside the latest declared IS window require
an explicitly declared IS/OOS backtest; saved downloads remain readable.
The prop model's internal training/validation split stays inside the selected
research period and never reads OOS during an IS run.

## API and CLI

`POST /api/backtests` and `POST /api/optimizations` require `sample_split`:

```json
{"sample_split":{"mode":"percentage","is_percent":70}}
```

```json
{"sample_split":{"mode":"dates","is_start":"2020-01-01","is_end":"2023-12-31","oos_start":"2024-01-01","oos_end":"2025-12-31"}}
```

`GET /api/backtests/research-plan?dataset_id=...&strategy_id=...` returns the
latest submitted split, execution history and legacy report count. Compatibility
fields are `budget: null`, `remaining: null`, `exhausted: false`; `used` is a
history count only. Preview validates without running or saving a declaration.
`GET /api/backtests/{id}/oos` returns the selected report's own saved split.
`POST /api/backtests/{IS-id}/oos` accepts only `{"request_id":"<UUID>"}` and an
optional progress_id query UUID. Responses are 201 for completion, 200 for a saved
retry, 202 while running, or 409 for an invalid source or a failed/interrupted
request UUID. Start a new explicit request to retry a failed operation. It does
not accept parameter/date/cost overrides. CLI remains IS-only; use the saved IS
report/API for manual OOS execution. CLI split settings are editable on each run.

## Current qualification

See the [active acceptance record](robust_research_plan.md#final-acceptance-record)
for current repository qualification. The dated Editable declarations and manual
unlimited OOS entry (2026-10-29) in [the review log](prop_simulation_review.md)
retains that earlier product evidence and its reproduction steps.

## Campaign checks

These are campaign criteria, not new product limits. Splits remain editable and
manual OOS unlimited; record prior access to identify untouched evidence.
**PASS** advances; missing values/evidence → **INCONCLUSIVE**; broken limits → **FAIL**.

### Research and mechanics

For each finding, record source, sample, method, costs and limits; distinguish
the reported result from our inference. Published results do not validate our
implementation or transfer to another market automatically.

A strategy specification covers indicators, warm-up, timing, sessions, orders,
sizing and exits. Test entries, exits, no-trade cases, boundaries and intrabar
ambiguity. Compare signals/order intentions separately from fills: two matching
implementations can share one specification error. Visual examples should explain
both trades and no-trades. Bridge features need calculation, timestamp/as-of and
look-ahead checks, plus installed-build and historical/live comparisons.

Data records include source/contracts, fields, timezone/timestamps, sessions,
gaps, rolls, preprocessing, rights and feature-availability times. Compare data
offers on the same fields and periods; trades alone do not establish quotes/depth.
Where a prop rule depends on unrealized equity, supply intratrade equity/exposure.

### Campaign declaration

Before search, save the following. Values remain **unset** until supplied.

| Field | Required values |
| --- | --- |
| People/dates | Owner/reviewer; POC and review dates; separate trading period, timezone and receipt cutoff. |
| Resources | Spending and engineering-hour caps, review deadline; separate future commitments, sunk cash and forecasts. |
| Search | Development/final holdout dates, prior access, parameter/sizing/allocation counts and total trial cap; count failed/abandoned trials. |
| Frozen package | Code/input hashes, integer sizes/allocation, fills/costs, dated firm rules and selection rule before final OOS. |
| Outcomes | Minimum cash by cutoff; loss/drawdown cap; maximum budget-overrun probability; sample/event counts and uncertainty width. |
| Comparisons | Exact identity/count/native costs; field-specific absolute/relative floating tolerances fixed before comparison. |
| Operations | Stale-data age, alert/recovery limits, forward-test sessions/events, exposure caps and stop/resume policy. |

### Checks before advancing

| Gate | PASS requires | Gap |
| --- | --- | --- |
| Plan | All required values set/versioned/frozen before assessment; spending, hours and trials within limits. | Phase calculation inputs are now saved by campaigns; owner/resource/operations acceptance values still require a declaration. |
| Data | Zero unexplained invalid rows, duplicates, time-order or identity errors; required fields/sessions/history, rights and feature-availability times checked; exclusions recorded. | CSV checks exist; campaign coverage/rights need evidence. |
| Mechanics/exports | 100% of deterministic cases match; zero unexplained signal/order differences; IDs, quantities and UTC instants match. Native money exact; companion net within USD 1e-8. | Canonical `aq-trade-export-v1` import is implemented; worksheet/canonical admission limits apply. External platform equivalence still needs independent evidence. |
| Prop/reports | All independent lifecycle/first-breach cases match, including recovering winners, gaps and cost boundaries. Random simulations meet preset tolerances; reopen keeps hashes unchanged without recalculation. | Past evidence applies only to the tested model/version; no live approval. |
| Research | Frozen package passes cash, loss, spending, sample and precision limits on clean final data; cost/data/block-length stress tests pass. | Internal holdout is not final OOS; annual sizing cannot prove cash-by-deadline performance. |
| Operations | Rejection, duplicate, partial-fill, disconnect, stale-data, protection, forced-flatten and restart tests meet timing/exposure limits; no unexplained orders/positions; broker records match. | Supplied-event reconciliation and advisory recovery are tested locally. Installed platform/broker compatibility, account/API permissions and connected operational behavior remain unverified. |

### Cash horizons versus retained legacy objective

[Retained legacy annualized sizing](../alphaquest/prop/native_analysis.py) uses training data:

`slot_year = 261 × (expected lifetime payout - acquisition cost) / (expected account days + replacement days)`

Annual results and historical replay use model timing assumptions; they do not
forecast all costs and cash receipts by a calendar deadline.

For that proposed forecast, count receipts paid by cutoff minus fees/operating
cash paid within the period. Record liabilities and sunk cash separately. Freeze
evaluation/replacement delays, approval/settlement, eligibility, payment dates
and shared-cost allocation before selection. Unpaid equity and payout requests
are not receipts. The observed one-slot cash ledger is implemented; conditional Funded campaigns
estimate received cash independently. A general finite-horizon multi-account
selector remains pending and needs its own contract and qualification.
Exclude sunk costs from future choices, but retain actual spending/cash history.

If final OOS influences a revision, that data becomes development evidence;
obtain fresh final evidence where needed. An operational-only fix may reuse
research evidence only if a recorded impact check shows no change to the strategy
or research assumptions. A stop requires diagnosis and the relevant retests.

Use the [export contract](architecture_reference.md#multicharts-to-alphaquest-contract)
for current limits. Available checks: [source/API](../tests/test_prop_analysis_api.py),
[costs](../tests/test_prop_commissions.py), [risk](../tests/test_intratrade_risk.py),
[research](../tests/test_research_workflow.py) and
[reference comparisons](../scripts/verify_native_prop.py).
See the [dated review records](prop_simulation_review.md) for saved results;
new runs need evidence for their exact model/version. In a fresh run/evidence
folder save date, code revision/local changes, input/settings hashes, model,
command, expected/actual values and artifact hashes. Keep earlier snapshots.

Live setup checks must record installed edition/build/bitness, API/ABI, permissions,
actual depth samples, reconnects, order protection and broker reconciliation.
Check freshness, stale-data detection and historical/live feature consistency.
Attribute each trade to a strategy or recorded manual action. Keep unmatched
orders/positions visible; missing records are not a clean reconciliation. Compare
signals, submissions, acknowledgements, fills and final positions. Normal fill
variation is different from missing protection; do not restart into unexplained
broker state. Record protective-order location/ownership and emergency actions.
Vendor pages alone do not prove these. Background pointers, not rechecked here:
[MultiCharts depth discussion](https://www.multicharts.com/discussion/viewtopic.php?p=152176&view=show),
[Sierra depth API](https://www.sierrachart.com/index.php?page=doc/c_ACSILDepthBars.php),
[Sierra replay discussion](https://www.sierrachart.com/SupportBoard.php?Page=1&ThreadID=96234).

## Historical qualification of the retired lock and three-attempt policy

The following records describe the former behavior and preserve earlier evidence.
They do not specify the current editable/unlimited policy above.

## Reproducible qualification

Run from a fresh artifact path (never overwrite prior saved evidence):

```bash
PYTHONPATH=. python -m pytest -q tests/test_research_workflow.py \
  tests/test_research_browser.py --basetemp artifacts/research-review-NEW
```

`artifacts/is-oos-20261028/browser-01/` contains actual browser outputs. In
`test_percentage_is_sweep_selec0/`, the labelled synthetic CSV has 120 weekdays,
three bars per weekday, one contract and no trading costs. The 50/50 split gives
60 trades and 180,000 CU net separately in each period. Independent default prop
expectation in each period: 360,000 payouts - 7,120 evaluation/activation fees =
352,880 Historical net, with normal simulation counts. Both native source checks,
IS/OOS report JSON, prop downloads, cash screenshots, batch rows and source-bound
budget are saved. The configured prop analysis reopens without recomputation.

The explicit-date browser case uses two weekdays. Each period has exactly one
trade earning (103 - 100) * 10 = 30 CU. Its prop source is correctly incompatible
because each period has only one session weekday. It confirms cancellation spends
nothing, three attempts exhaust the shared budget, the fourth request is blocked,
and IS remains available. Unit/API cases independently cover chronology, empty
windows, invalid/missing declarations, concurrent requests, duplicate UUIDs,
parameter freezing, deletion/re-upload, recovery and failed attempts.

Existing fill/report fixture oracles retain every original source row as IS and
append a labelled synthetic reserved date through `tests/research_fixtures.py`.
There is no production bypass or reduced simulation count. New research checks
use ordinary clients and genuine multi-date sources. Browser fixture servers stop
through their normal cleanup; no additional persistent demo server is needed.

Final qualification against code commit `bafa7b0`: **801 checks passed**, with no
failures/errors/skips (24 existing dependency/notebook warnings). The complete
log and JUnit record are `artifacts/is-oos-20261028/final-suite.log` and
`final-suite.xml`. The final product journey, original reports, source checks,
downloads and budget proof are in `final-suite/test_percentage_is_sweep_selec0/`;
the exhaustion/cancellation proof is in `final-suite/test_explicit_dates_required_b0/`.
`qualification.json` records the independent per-period values and immutable code
commit. The running checkout retains its own read-only live verification and
before/after preservation evidence under `artifacts/is-oos-20261028/`.

### Native historical account-state replay

From an ordinary MNQ VWAP IS report, open **Configure prop analysis → Inspect one strategy/account policy**. Select Evaluation or fresh Funded, the profile
and common sizing policy, then Check native source and Run native replay. The
first supported subset requires complete one-minute sessions, EOD-flat enabled
and strategy-local volatility sizing disabled. Results link the actual controlled
backtest, causal decisions, provider session states, requests/deductions/receipts
and durable downloads. Historical scenario status stays separate from the optional
native Monte Carlo forecast below. Native policy selection is now available in
independent campaigns and nested studies as described below. See the [saved journey
and independent expected values](prop_simulation_review.md#native-chronological-strategy-and-account-replay--2026-11-08).


### Optional native Monte Carlo forecast

In the same native form, enable **Add native Monte Carlo forecast**. Declare total
paths/seed, contiguous source block length, modeled calendar horizon, retained
path count and an explicitly versioned target calendar. Source checking shows
observed sessions separately from modeled cohorts and rejects unsupported shapes
or excessive work. Run saves the actual historical child plus a separate forecast
in the same normal durable report. Inspect all-path statistics, censored
Evaluation means, separate receipts/pending/deductions, selected detail paths and
both source/model clocks. Conditional Monte Carlo error is not future confidence.
Reopening/downloading does not resimulate. The [saved demonstration](prop_simulation_review.md#native-contiguous-block-forecasts--2026-11-08)
contains exact declarations, independent dynamic quantities/cash, rejection cases,
source bytes and startup/shutdown steps. Native candidate optimization and frozen
outer application are described next.

### Native policy search and actual later observations

From the same saved IS report, choose an Evaluation or Funded campaign and select
the native strategy rerun execution method. Keep the phase objective visible:
Evaluation compares acquisition cost and calendar time; Funded compares receipts
within its horizon from a fresh account. Declare the complete set of sources,
whole-contract caps and sizing policies before checking. The native method
currently admits complete one-minute MNQ sessions from the supported EOD-flat
VWAP strategy with its local volatility sizing disabled. Unsupported strategies,
instruments, incomplete sessions or unavailable block shapes reject at checking.

Native Evaluation and Funded campaigns support the local Apex EOD 50K and
LucidFlex 50K models. Lucid Evaluation requires native execution and zero
activation fee; its saved-trade-path counterpart remains unsupported. Its model
uses a $3,000 target, 40% best-day consistency and no evaluation expiry. Fees,
provider rules and timing retain their disclosed verification status. The
Evaluation form names retry delay in calendar days and activation delay in
eligible sessions; their defaults are 0 and 1. Changing execution mode retains
your selected profiles, fees and timing and blocks an unsupported combination
instead of substituting another profile. Nested drafts/templates preserve the
same choices and still require fresh preview.

Native checking shows the complete candidate population, source and target
calendars, simulation work and retained paths. Running saves every candidate's
paths, schedules and forecast in the existing analysis. The Funded point-mean
selector retains exact ties; Evaluation retains the Pareto family. A conservative
mean option refits native forecasts under historical block-origin weights and
reports unresolved refits explicitly. Its historical interval and conditional
Monte Carlo error remain separate from per-account cash dispersion and future
uncertainty.

In nested research, choose the same native method under **Economic validation**.
Every configuration that passes the inner qualification enters the phase search
with every declared policy. The full selected family is frozen before outer
strategy execution. Metadata/inventory preparation may parse and hash source
bytes; this is not a claim that those bytes were never read. Each outer
application runs actual bars once, without sampling
or reselection, and links its ordinary controlled backtest. Fixed-path campaigns
keep their earlier meanings and calculations. A frozen native campaign's manual
OOS action also uses actual chronology, requires its full declared horizon and
never publishes a new ranking. Requests, account deductions, pending amounts and
modeled receipts are separate saved fields.

Queued/running independent searches offer **Stop**. A requested stop ends at the
next safe boundary and cannot publish a partial candidate population as an
optimum. Run again restarts the complete declaration with its saved seeds.
Completed report reopening and downloads do not recalculate. Source, code,
captured artifact and controlled child catalogue changes prevent incompatible
reuse. Final-procedure controls below apply to the entire research algorithm,
not just these selected-policy manual OOS checks.

Both phase identities capture the provider source files, exact-money helpers
and selected Apex/Lucid runtimes. A changed identity rejects a new frozen
launch before OOS access. Saved reports and downloads remain readable unchanged.


## Complete-procedure freeze and terminal applications (M3b2)

Implemented on the existing robust research report, with normal backtests, phase owners, workers and AnalysisStore reports. This increment adds no simulation engine, service, or result database. Existing completed research reports remain immutable. A completed campaign can freeze one complete server-derived procedure; each final/current application is a separate saved AnalysisStore report.

The original research declaration now includes `terminal_selection` and `final_evidence`. Historical campaigns without these declarations can still reopen but cannot acquire a retrospectively declared procedure freeze. A new evaluated declaration is required. The procedure captures every expanded signal configuration and its implementation, qualification/neighbor/complexity rules, folds/gaps, causal regime settings, execution scenarios, independent phase studies/policies/profiles/calendars/seeds/constraints/ties/native law, references, reliability settings and complete engine/data identity. It binds the original report/artifact fingerprint and the exact eligible development session content. The SHA saved in the existing catalogue is authoritative; a modified client blob with a new selfhash is not authority.

Terminal planning uses the predeclared outer training length and rolling/expanding mode. It excludes the declared purge/embargo sessions at the end of development, reruns the same inner qualification over that retained training history, then searches the complete PASS population independently for each phase. All predeclared references retain separate measurement-only admission. The target is the next declared `outer_test_sessions` open dates from the phase calendar; it is price-free modeled calendar metadata, not verified future observations. Terminal applications have their own application/procedure/role discriminants and never claim a fabricated outer fold. No last-fold policy is promoted.

Current-development selection uses the same pinned development snapshot and complete frozen algorithm. It excludes the reserved/consumed final window, even after final assessment. An appended/reformatted source may be chosen before freeze only if every original development session has identical canonical observations and counts, with matching instrument and timestamp interpretation; that exact snapshot is then pinned. Changing criteria, source content, costs, code, or the terminal window requires a new evaluated procedure.

Final verification is optional and only available with a matching reservation and eligible local access evidence. Qualification, phase choices/families and references are durably sealed before final authorization and the first final strategy execution. Assessment applies every frozen member without reselection, ranking replacement or implicit family weights. It records one chronological historical observation for each policy. `final_evidence.require_evaluation_completed_acquisition` and `minimum_funded_trader_receipts` are optional predeclared outcome gates, default `null`; no arbitrary zero-cash certification is implied. Any failed explicit gate, incomplete consumed assessment, insufficient required evidence or unqualified current membership prevents a deployment recommendation. Families remain families. Provider/model/operational blockers remain visible, and every result keeps `production_qualified=false`.

A failed or cancelled final attempt remains consumed once its durable access authorization exists. Current-development reports derive incomplete status from that exact authorization/application, rather than calling it “not requested.” Cancellation is cooperative between durable steps. Completed backtests/phase reports are retained and verified on resume; cancellation accepted during archive staging is rechecked under the publication lock before a completed report can appear. Saved reports reopen without resimulation or mutation.

### Access provenance and feasible fresh-data workflow

A shared append-only access journal lives in the existing AnalysisStore catalogue. A fresh workspace records its scope from creation; an older workspace retains unknown earlier history. Retained backtests and manual OOS attempts establish prior access, including cross-strategy outcomes. Existing normal price readers, prepared/cache paths, optimization dispatch, imports, CSV downloads and the command-line bar reader honor the same journal. Price access is recorded before work/return, including consumer failures. Metadata-only validation and inventory can parse/hash raw bytes but return only timestamps, counts, schema and hashes; this is explicitly not an untouched-byte claim.

Dataset validate/save accept `disclosure=metadata_only`. The response omits OHLC previews and later dataset metadata remains hidden. Reserve the final range before initial IS research to avoid preview/download/outcome contamination. The server derives every actual session in the chosen inclusive range; callers cannot omit inconvenient dates. Ordinary requests overlapping RESERVED/BOUND sessions reject with 409. Explicit release permits ordinary manual research and permanently records the decision. Consumed final history remains available for honest subsequent manual access but cannot obtain a clean reservation again.

The guard uses market/instrument information lineage and session coverage, with raw/canonical content witnesses; it does not equate “new raw SHA” with “untouched.” NQ and MNQ share the Nasdaq information domain while retaining distinct execution contracts. Differing captured source timezones use conservative two-civil-date overlap padding to prevent shifted CSV interpretations laundering the same observations. Unknown lineage/history cannot grant eligibility. Existing CLI readers attach to the existing journal without creating a worker, database or false fresh scope. External prior-access declarations are unverified and never override known overlap. Eligibility is labeled `ELIGIBLE_UNDER_DECLARED_LOCAL_SCOPE`, never a universal untouched certificate.


### Current boundaries


This does not establish external absence of prior access, official provider parity, future profitability, live execution readiness or automatic trading authorization. A holdout can be infeasible/previously accessed/unknown; that status is retained. Missing or partial evidence cannot produce a forced winner. A single final outcome does not estimate or prove a future mean. The [research workspace](#research-workspace-drafts-and-templates-m4) and supplied forward observations are implemented; see the [complete workflow](#first-complete-campaign-a-practical-walkthrough) and [matched-scope observation guide](prop_simulation_review.md#complete-supplied-funded-scope-and-causal-sizing-diagnostics). Neither establishes live broker integration.

## Research workspace, drafts and templates (M4)

Open **Research** in the main navigation, or **Strategies → Research workspace**.
This is the library of saved campaigns, strategy studies and drafts. A campaign
compares saved backtests under one set of assumptions: Evaluation compares
acquisition cost/time, while Funded compares modeled trader receipts. Strategy
studies test choices across historical training and test windows. Expand **What
is this page for?** for these definitions.

Start with **Search saved research**; no filter is required. Enter a name,
strategy or dataset, or paste a campaign ID, any linked backtest ID, an activity
ID, a report ID, or a link containing one ID. Search includes every retained
campaign source and activity, including sources other than the representative
backtest on the card. Readable strategy names such as `consecutive green hold`
work as well as stored identifiers. Use **Campaigns**, **Strategy studies** or
**Drafts** to narrow the library. **More filters** reveals phase, run status and
order; active filters remain visible when collapsed. **Clear search and filters**
returns to all saved work.

Each card shows its purpose, strategy, dataset, full campaign ID and linked
backtest/activity counts. **View results** opens a durable completed report;
**Manage campaign** opens campaign details and deletion eligibility. A completed
run can still have no qualified candidate; evidence outcomes and limitations
remain distinct from run status. **Details and limitations** reveals the saved
stage, frozen procedure identity and evidence reasons. The catalogue follows the
latest calculation attempt, with final verification and current development
visible separately. A later failed assessment does not disappear behind an
earlier completed campaign. Browsing/searching never starts a run.

To create work, choose **Start new research**, find an in-sample backtest and
**Open source report**. From that ordinary report choose **Configure prop
analysis**, then configure and check sources before explicitly running. The
source picker loads only when requested. If no source exists, choose **Run a new
backtest first**.
Inside the existing nested configuration, expand **Save a draft or reuse declared settings**. Save a
named draft, resume it from Research, or save a separate copy. Drafts retain the
complete declared source set, baselines and settings. They are editable pre-work,
not frozen research evidence. Every reload or template application requires a
fresh source/date preview before running. If another tab has saved a newer
revision, your form edits remain visible; reload or copy rather than overwrite.

Templates contain reusable research settings only. They cannot carry source
identities, saved outcomes, selected candidates or holdout eligibility. A form
with source-bound baselines must remain a draft until those references are
explicitly rebound; saving a template does not silently remove them. Applying a
template keeps the newly chosen source and requires a new preview.

Deleting an unused source does not delete its draft. Research shows the missing
source and preserves the declaration for download. Rebind the anchor in a new
draft, then explicitly revise every unavailable source/reference; the original
record stays unchanged. Unsupported saved schema versions or policy combinations
remain inspectable and downloadable but cannot run through controls that would
change their meaning. In particular, a non-Cartesian saved sizing family is not
silently expanded to a Cartesian family.

Date previews use the actual observed sessions, with excluded sessions/gaps and
complete tables. Saved reports add interactive numeric parameter qualification
plots and matched Funded forecast/actual receipt plots. PASS, FAIL and insufficient
evidence use distinct symbols as well as colors. Evaluation acquisition metrics
are not plotted as Funded receipts. Each family member remains visible without
inventing a probability for ties; chart display limits are labeled and complete
rows/downloads remain available. Readiness is saved evidence, never a new
selection or a production certificate computed by the catalogue.

## Compare predefined frozen phase policies

After independently running and freezing Evaluation and Funded campaigns, open
the existing prop configuration's lifecycle comparison controls. Choose one exact
frozen candidate for each phase and a completed ordinary manual OOS report for
its original IS parent. The phases may use different signal parameters or sizing.
Both must use compatible native MNQ execution and the same provider/account rules
and observed market dataset. If an OOS source is missing, manually execute the
ordinary source report's OOS first; Check does not execute or inspect a new final
holdout on your behalf.

Name each pair and explicitly set the common first session and exclusive cutoff.
Check the complete membership, source identities, coverage, work estimate and
frozen costs before running. Both original selections remain unchanged. The
result shows actual acquisition fees/readiness, subsequent fresh Funded start,
received and pending cash, and net trader cash. Evaluation profit and unused
provider equity are not payouts. If readiness never occurs before the cutoff,
Funded stays unstarted. A receipt on the cutoff is pending, not received.

This is one previously accessed historical path per pair, with no ranking or
probabilities across the declared pairs. Its shorter Funded continuation is
explicitly distinct from the independent full-horizon forecast. Open each normal
controlled backtest or download the exact packages, bindings, phase traces and
cash ledger. A stopped comparison can retry the exact declaration; changing its
sources, policies or dates needs a new request. This workflow does not certify
provider rules, executable fills or future profitability.

## First complete campaign: a practical walkthrough

This example is a research exercise. Use a clearly labeled synthetic source for
learning, then a licensed dataset whose instrument, timestamps, costs and session
coverage you have checked. A passing calculation is not a trading recommendation.

1. **Save market data.** In Datasets, set the real symbol, source timezone, tick
   size and point value before validation. If reserving final evidence, choose
   metadata-only inspection and declare the possible final session interval
   before opening its prices. Previous inspection cannot be undone by reuploading.
2. **Save strategy hypotheses.** In Strategies, create an IS parameter grid with
   a separate manual OOS interval. Keep quantity fixed in each signal grid;
   declare prop sizing independently later. Save a second strategy grid on the
   same dataset/costs to compare hypotheses. You can disable automatic legacy
   prop reports for these new grids while retaining later manual research.
3. **Start research from a report.** Open an ordinary IS trial, then Configure
   prop analysis → Find a robust strategy, size and account. Select all intended IS configurations/grids,
   name the study and save a draft. The Research workspace can reopen it later.
4. **Declare the evidence rules first.** Set training/validation/test lengths,
   purge/embargo, minimum observations, neighboring-parameter requirements and
   economic thresholds. Add realistic execution stresses and relevant causal
   market conditions. More simulation repetitions improve numerical resolution;
   they do not add historical observations. Add a simple reference before testing
   if a later recommendation must demonstrate improvement over it.
5. **Choose each economic objective separately.** Evaluation searches acquisition
   cost and calendar time. Funded searches receipts within its saved horizon from
   a fresh account. Select fixed contracts or explicit dollar/percentage-risk
   policies, account rules, costs, calendars and seeds. Native risk policies need
   the supported complete-minute MNQ/VWAP source and actual strategy reruns.
   Unsupported sources reject before a calculation starts.
6. **Preview, then run.** Inspect the actual session timeline, complete candidate
   membership, excluded windows and work estimate. Resolve blockers. Run creates
   normal restricted backtests and immutable phase reports. Stop/retry controls
   retain completed evidence and verify identities before reuse.
7. **Review what happened.** Open the saved report from Research. Inspect rejected
   regions, qualified configurations, every frozen phase family, forecast versus
   actual outer results, cash/drawdowns and reference comparisons. A tie remains
   a family. Missing/censored evidence stays explicit; do not interpret a large
   path count as a large independent historical sample.
8. **Freeze the whole procedure.** Review the terminal training law and any final
   reservation before freezing. Run guarded final verification only if eligible.
   It applies frozen choices and may block endorsement; it never chooses a
   replacement from the final outcomes. Run current-development selection as a
   separate fresh application of the frozen procedure. It may correctly return
   **NO QUALIFIED DEPLOYMENT CANDIDATE**.
9. **Observe before deployment.** From an eligible current report, choose an
   exact retained policy and open forward observation. Bind supplied paper/actual
   records only to authoritative current membership; name an explicit preference
   if several policies remain. A no-qualified result permits only an unbound,
   labeled synthetic diagnostic. Import timestamped events, assess at an explicit
   UTC clock, inspect discrepancies/cash and follow the recorded recovery steps.
   Use **Check current policy and observation declaration → Create declared
   observation monitor**, then **Check selected event bytes → Import these reviewed
   event bytes → Save a new observation assessment**. The [observation guide](prop_simulation_review.md#complete-supplied-funded-scope-and-causal-sizing-diagnostics)
   explains optional complete coverage, calendar translation and sizing events.
   Monitoring is advisory and does not stop broker orders.
10. **Keep the evidence.** Download normal JSON/CSV/ZIP artifacts and reopen saved
    reports without recomputation. Record the source, assumptions and remaining
    provider/execution checks. The optional frozen-pair comparison is downstream
    of separate phase freezes and does not turn a historical net-cash result into
    a new optimizer or a live readiness certificate.

The dated demonstrations in `prop_simulation_review.md` give exact synthetic
source files, saved IDs, field values, expected arithmetic, rejection cases and
startup/shutdown commands. The four-configuration/two-strategy example shows why
an honest completed campaign can retain eight Funded alternatives and still
return no qualified candidate.


## Cancel queued backtest work

Open **Strategies → Backtest activity** to see queued/running jobs. A queued
activity has **Cancel queued activity** in its row and detail header. Confirm to
prevent that activity from starting; dismiss to leave it queued. The saved status
becomes Cancelled and persists after reload/restart. Other jobs continue in order.
If it starts before the request is accepted, cancellation is rejected and the
page refreshes its current state. Running backtests cannot be stopped with this
action.

Cancellation retains all saved results, including reports from an earlier failed
attempt whose resume was queued. Deleting those is a separate action with the
existing campaign/source protections. A cancelled activity is terminal: start a
new activity to run that declaration again. Do not restart the server to cancel
one job, since that affects other work.
