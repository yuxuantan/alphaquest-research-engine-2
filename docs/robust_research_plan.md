# Robust research implementation and qualification

Audit date: 7 November 2026. Base: clean fetched `origin/main` at
`60dbccbda8e97373a3856ea6ee3fdd07313cad4f`. Work branch:
`feature/robust-research-workflow`. This is the execution checklist for the
user's complete robust research request, not evidence that planned features work.
No main commits, merges, force pushes or PR creation are authorized by this plan.

## Fresh audit and requirements traceability

Status meanings: **usable** = existing implementation with targeted historical
tests; **partial** = a useful foundation but missing requested behavior;
**missing** = no implementation found. Historical tests are not a fresh pass.
Baseline full-suite execution and its limitations are recorded below.

| Request / requirement | Audited implementation and tests | Gap / planned owner | Status |
| --- | --- | --- | --- |
| 0: dataset, hypothesis, fills and research declaration | `datasets.py`, `strategies/registry.py`, `backtest_requests.py`, `research.py`; `test_research_workflow.py`, `test_backtest_api.py` | Saved campaign-wide thresholds, hypotheses, stage gates and cost stresses | partial |
| 5.1: rolling/expanding nested windows, sessions, purge/embargo, minimum samples | Manual source-date split in `research.py`; phase dates in `prop/phase_lifecycle.py` | `research_folds.py`: explicit session convention, immutable outer/inner folds, gaps and information cutoffs; campaign orchestration runs existing backtests | missing |
| 5.1: backend leakage isolation and access history | `research_api.run_oos`, `CampaignStore.freeze/begin_assessment`; `test_campaign_assessments.py` | Fold-local runs/feature preparation, no test-driven admission, dataset-wide accessed intervals including failed attempts, holdout guard | partial |
| 5.2: temporal, parameter-region and complexity qualification | Exhaustive grid only (`optimization.py`); no qualification algorithm | `edge_qualification.py`: predeclared thresholds, all candidates with PASS/FAIL/INSUFFICIENT_EVIDENCE, full eligible set, session uncertainty and nearby settings | missing |
| 5.2: execution and causal market-condition robustness | Existing explicit fills, costs and intrabar ambiguity; `test_next_bar_execution.py`, `test_intratrade_risk.py` | Rerun cost/fill scenarios; causal regimes with available-at evidence; distinguish untested scenarios from passes | partial |
| 6: fixed whole contracts | `phase_profiles.py`, independent phase optimizers; `test_prop_phase_profiles.py` | Preserve exact fixed-path regressions | usable |
| 6: dollar/percentage risk, denominator, stop risk, rounding, skips and state | Strategy-local risk sizing exists; phase APIs accept fixed micros only | Common `prop/sizing.py` contract used inside existing account transitions; explicit stop metadata and quantity-invariant source admission | missing |
| 7: canonical trade/risk identity and cost conservation | `execution.Trade`, `prop/adapter.py`, `prop/source.py`, `commissions.py`, `intratrade.py`; adapter/cost/risk tests | Versioned native/external canonical source, stop updates, ordered events, source-limit disclosure | partial |
| 7: standalone MultiCharts ingestion | Supplemental XLSX reconciliation only; `docs/designs/trade_export_v1.md` remains a proposal | Validate complete versioned exports and import through normal report catalogue; no invented bars or excursions | missing |
| 8: deterministic dated prop replay | `phase_lifecycle.replay`, `cash_ledger.replay`; `test_prop_phases.py`, `test_prop_cash.py` | Reuse transitions/ledger for frozen independent-phase outer tests and variable sizing; separate forecast and chronological outcomes | partial |
| 9: rules, fees, receipt delays, retries, monthly cap | `lucid_rules.py`, native engines, phase profiles, ledger; relevant phase/cash tests | Field-level rule provenance, dated verification, historical versions, explicit UNVERIFIED readiness gate; no invented rules | partial |
| 9: reproducible sampling and uncertainty | Session blocks, saved seeds, phase intervals/censoring and model hashes | Sampling/model/execution/rule uncertainty scenarios; session history is evidence count, paths are not | partial |
| 9–10: independent Evaluation and Funded selection | `evaluation_optimization.py`, `funded_optimization.py`, `phase_dispatch.py`; dedicated tests | Feed only qualified configurations, richer policies and predeclared conservative selection/baselines | usable fixed-size foundation |
| 9–10: optional finite-horizon policy-pair comparison | Budgeted one-slot ledger | Compare predefined independent policy pairs using existing ledger and common horizon; never replace phase objectives | partial |
| 10: identity, hard risk/budget constraints and conservative mean | Campaign manifests, phase constraints and complete frontier/ranking | Complete policy identity, outer-evidence constraints, empirical-vs-estimation uncertainty distinction | partial |
| 11: selection-process reliability | Manual fixed-choice OOS assessment is simulated, not chronological | Outer cash/cost/breach aggregates, forecasts vs history, predeclared baselines, stability and evidence-limited calibration | missing |
| 12: procedure freeze, untouched holdout, final development rerun | Immutable IS package with prior-access history | Freeze complete algorithm; guarded optional holdout; rerun frozen selection on development; no forced winner | partial |
| 13: timestamped forward/paper signals, orders, fills and reconciliation | Completed backtest trades/risk only, no signal/order/ack IDs | Append-only supplied events and deterministic labelled replay harness; reconcile duplicate/missed/protection/cost/latency/positions | missing |
| 13: advisory monitoring, recovery and readiness | No monitoring API/UI/states | ACTIVE/WATCH/PAUSED/RETIRED with saved thresholds and recovery evidence; no default order placement or claimed broker enforcement | missing |
| 14: guided setup/check/run/freeze, durable results and downloads | Existing portal `web/campaigns.js`, `campaign_api.py`, `AnalysisStore`; campaign/browser tests | Extend same portal journey with research plan, fold evidence, recommendation and forward monitoring | partial |
| 14: accessibility, responsive UX, progress, resume/templates, large lists | Existing filters, 390px campaign checks, failed attempt history and retry | Persist stage progress/cancellation and templates; all new controls connected and tested | partial |
| 15: deterministic, leakage, statistical-property and conservation tests | Existing pytest/Playwright infrastructure, legacy numerical regressions | New specified-property tests and independent arithmetic, full regression and product browser verification | partial |
| 16: architecture/methodology/user/developer guides and status matrix | Existing guides and dated immutable evidence | Update alongside each increment, retain historical records and exact reproduction steps | partial |
| 17–20: incremental implementation, commits/pushes and final acceptance | Clean feature branch created from fetched remote default | Tested increments and all Definition of Done checks remain required | active |

The audit read README, AGENTS, architecture, research workflow, phase plan,
prop simulation, campaign API, portfolio plan and trade-export proposal against
the source. No existing component is approved for retirement. Legacy joint
sizing, notebook dependencies, format-1/2 readers, immutable reports and earlier
evidence remain supported.

Confirmed documentation drift: the research guide's “at most 128” candidate cap
is superseded by `require_candidate_confirmation`: 128 is a confirmation
threshold, not a hard limit. Source-date manual splits and CME session campaign
dates are different conventions; nested folds must record theirs explicitly.
Existing manual OOS phase assessments resample OOS observations and must never
be labelled observed chronological account outcomes.

## Execution milestones

Each row is completed only after its functional, API/UI, independent expected
value, persistence, regression and documentation checks pass. Large milestones
are split into coherent commits and pushed at least every one or two commits.

| Milestone | Dependencies and implementation | Product increment and acceptance | Tests / principal risks | State |
| --- | --- | --- | --- | --- |
| M0: audit/plan | Fetched clean main; traceability above | Reviewable plan and documented actual gaps before code | Fresh baseline suite; no datasets/results touched | audit/plan committed; interrupted baseline recorded |
| M1a: folds and research execution | Session fold contract; immutable declarations/stage refs in existing campaign catalogue; ordinary backtest runner | From saved report configure nested windows, preview exact dates/work estimate, run inner research, reopen/download actual results | Hand-derived fold dates, embargo, source boundaries, no future features, failure/retry/idempotency | implemented; new product gates and stable affected-module regression pass |
| M1b: robust qualification | M1a; saved predeclared qualification/stress/regime/region rules | Explain every admission/rejection/insufficient result; preserve the entire qualified set for phase selection | Stable/noise/disappearing/isolated-peak/large-search controlled cases; future-data mutation cannot change earlier admission | implemented with saved API/browser evidence and stable targeted regression; phase handoff follows M2/M3 |
| M2a: canonical sources | Existing native and XLSX adapters | Normal import/source-check/report workflow supports complete standalone external trades | Identity/hash/count/time/cost/partial/ordered-event rejection and reopen | implemented for canonical imports and eligible annualized local prop analyses; external phases and dynamic sizing remain M2b/M3 dependencies |
| M2b: sizing | M2a; common state-aware policy in existing account owners | Fixed/dollar/percentage policies with named base, skips/caps and saved decisions | Hand math, changing stops/balances/cushion, unsupported sources, unchanged fixed simulations, compiled/reference parity | implemented and qualified for admitted invariant external paths and native fixed policies; native risk-based policies require a suitable strategy rerun |
| M3a: frozen economic selection and historical replay | M1/M2; existing phase optimizers and ledger | Select on development only, freeze family, replay actual outer dates including no-trade days and receipts | Phase independence, cutoff/retry/cash conservation, frozen hash guards, no reselect | implemented for supported native fixed-path policies; normal API/browser evidence and focused regression qualified; no provider/live parity claim |
| Native state-aware execution completion | Causal sizing/capture and existing execution engine | Native risk sizing must rerun strategy eligibility, fills, account halts and deductions consistently in forecast and outer replay | Independent quantity/fill/cash examples, actual changed signal path, no future entry inputs, legacy parity | implemented: native chronological MNQ/VWAP execution, candidate forecasts, independent search, conservative native refits and frozen outer/manual OOS integration; targeted release gates recorded below |
| M3b1: reliability and references | M3a; predeclared baseline/rules/scenarios | Outer coverage, forecast errors, paired references, stability, conservative historical-mean selection; permit insufficient evidence | Complete/censored/missing/family arithmetic, reference authority, history-versus-MC uncertainty, source/code identity | implemented; release evidence and final gates recorded below |
| M3b2: final procedure | M3b1; full access provenance | Complete procedure freeze, feasible holdout, current development rerun and honest recommendation | Future poisoning, full-procedure identity, holdout access/reservation guards, no last-fold promotion | implemented with guarded local-scope access, terminal refit and saved API/browser evidence; full-goal qualification remains pending |
| M4: cohesive guided UX | Incremental UI delivered throughout M1–M3 | Review end-to-end first-user journey, templates, timelines/regions/cash charts and decisions; useful cancellation/resume | Desktop/narrow browser journeys, loading/errors, export/reopen byte identity, accessibility | workspace/drafts/templates and visual review implemented at 5308d88 with saved API/browser evidence; forward monitor UI is M5 |
| M5: forward and monitoring | Frozen recommendation/event contract; no broker dependency | Timestamped supplied or explicitly synthetic paper evidence, reconciliation and advisory states/recovery | Misses/duplicates/partial fills/protection/staleness/disconnect/latency, restart and readiness gates | implemented with supplied-scope cash comparison, frozen sizing arithmetic and saved API/browser evidence; full-suite acceptance running |
| M6: final qualification | All earlier milestones | Full Definition of Done with branch/history/docs/evidence/readiness report | Full pytest/browser checks, configured static checks, reproduction and export checks, verify pushed ref/main unchanged | uninterrupted 2,270-test full suite running on frozen source; final closeout pending |

## Integration and safety of conclusions

Use `research_campaigns.py`/the existing AnalysisStore catalogue for declarations
and stage references; normal RunStore backtests and AnalysisStore artifacts own
results. A coordinator must not wait for phase jobs on AnalysisStore's own
single worker. Declare immutable fold information sets; do not repurpose the
mutable latest manual split as the nested experiment record. Reuse ordinary
strategy feature preparation restricted to each fold and cold-start windows;
never fit preprocessing on the whole dataset.

Qualification returns configurations, not a second optimizer. Parameter
membership is fixed before outer testing. Phase objectives remain independent;
an unspecified Evaluation preference preserves the full frontier/family. Do not
invent a weighted winner. Independent mean uncertainty, single-account outcome
spread, Monte Carlo error and unverified model/rule/execution assumptions have
separate fields and labels.

Source or numeric changes retain older reports and invalidate incompatible
frozen launch. Never remove calculation files from numerical identities to
avoid that rejection. Native stop data and external event semantics must be
proven before variable sizing is deployable. MAE/MFE and held-bar bounds cannot
prove ordered tick paths. Verify rules against primary sources where possible;
unverified external integrations block production readiness, not honest local
research delivery. No live order placement is enabled by this work.

## Validation and evidence log

Fresh baseline command (isolated from the user's library):

```sh
.venv/bin/python -m pytest -q \
  --basetemp /private/tmp/aq-robust-baseline-20261107 \
  --junitxml=/private/tmp/aq-robust-baseline-20261107.xml \
  > /private/tmp/aq-robust-baseline-20261107.log 2>&1
```

No lint/type checker is configured in `pyproject.toml`; use Python compilation
and JavaScript syntax checks alongside pytest where relevant. Browser tests use
existing isolated uvicorn fixtures and stop their servers. Each implementation
entry must also update `prop_simulation_review.md` with saved normal-product
outputs, independent expectations, rejection cases and exact reproduction steps.

7 November component progress: `research_folds.py` now generates immutable
session-aware nested folds, and `edge_qualification.py` assesses the complete
inner candidate set with predeclared temporal, neighboring-parameter and cost
criteria. Their focused tests pass (34 fold and 33 qualification checks).
API/UI execution and durable product evidence are now implemented; this
is not full M1 completion. Required-but-absent execution/regime evidence returns
INSUFFICIENT_EVIDENCE. Bootstrap intervals remain approximate historical
diagnostics and do not certify a persistent future edge.

The first full baseline invocation was interrupted after 630.63 seconds:
373 passed, 8 failed and 42 errors. Browser errors include macOS Chromium Mach
port permission denial inside the sandbox. Backtest failures are under separate
investigation against an immutable archive of the starting commit. The run is
not a clean baseline or full regression result. Its log and partial JUnit remain
at the paths above; rerun applicable gates with the required local test access.

Current verdict: **incomplete**. Research completion and live deployment
qualification are separate verdicts. The goal remains active.

### M1a release evidence and remaining M1 work

The [normal-product demonstration](prop_simulation_review.md#nested-inner-research-product-increment--2026-11-07)
records exact startup, URLs, field values, independent synthetic expectations,
saved downloads and stop instructions. New gates: **90 passed** (fold,
qualification and nine API integration tests), **1 browser passed** at desktop
and 390px. Python compilation, both changed JavaScript syntax checks and
`git diff --check` passed. Native VWAP Decimal parameters, no-trade insufficiency,
future-price poisoning, partial session boundaries, cooperative recovery,
cross-kind IDs, deletion races and artifact tampering are covered.

Existing regression command:

```sh
.venv/bin/python -m pytest -q tests/test_research_workflow.py \
  tests/test_research_campaigns.py tests/test_campaign_assessments.py \
  tests/test_backtest_date_range.py tests/test_backtest_preparation_browser.py \
  tests/test_campaign_portal_browser.py tests/test_prop_phase_profiles.py \
  --basetemp artifacts/robust-research-m1-20261107/regression/data \
  --junitxml artifacts/robust-research-m1-20261107/regression/junit.xml
```

That mixed run had **82 passed / 17 errors** in 463.99 seconds. All errors shared
one `test_research_campaigns.py` module fixture returning HTTP 500 while Python
sources were being edited; the generic error did not capture the root exception.
The existing publication identity hashes all Python sources and deliberately
rejects mid-calculation code changes. This is a plausible cause, not a proven
attribution. The failing test passed in isolation and after its preceding module
(25 passed); then the **entire affected campaign module passed 19/19** on stable
source in 41.23 seconds. The stable log/XML/data are under
`artifacts/robust-research-m1-20261107/campaign-regression-stable/`. No integrity
check was weakened. The mixed broad run is not labelled clean; full-suite
qualification remains M6 work. Browser/process tests used the required local
process permissions. The original interrupted baseline log/XML were preserved
under `artifacts/robust-research-m1-20261107/baseline/`.

Subsequent M1b work implements declared alternative-fill/cost scenarios, causal
market-condition evidence and strategy-complexity/signal-parameter criteria;
its evidence follows below. Integrating the qualifying set with phase policy
selection follows the M2 sizing and M3 replay dependencies. M2–M6 remain pending. In particular no
standalone external import, dynamic prop sizing, chronological outer assessment,
final deployment candidate or forward monitor is claimed by this increment.

### M1b execution and condition evidence

`execution_scenarios.py` feeds real costs/stop/limit assumptions into ordinary
backtests, preserving baseline numerics and saving both baseline/resolved costs.
`research_regimes.py` fits only inner training and classifies entries using
strictly earlier bars; it reports incomplete warmup/threshold coverage explicitly.
`research_complexity.py` separates signal, sizing and display roles. Selected
scenarios are all required; assessed regimes may be optional or required per
the declared hypothesis. Complexity gates remain optional and descriptive,
without a universal score. Cross-instrument transferability remains untested.

The [saved normal-product demonstration](prop_simulation_review.md#execution-stress-and-causal-condition-evidence--2026-11-07)
shows independent NQ scenario means $2980/−$10, required US-clock evidence,
unknown optional price regimes, a complete rejection set, desktop/narrow reopen
and byte-identical exports. Its final two browser tests passed in 73.13 seconds.
MNQ API output independently matches $297/$97 after $3 additional costs; the
required-unknown and adverse-scenario boundaries block admission. Earlier source
reports and libraries are unchanged. Final stable gates: 273 focused tests in
40.35 seconds; 132 existing regression tests in 230.08 seconds; two browser tests
in 73.13 seconds. A final source-admission guard prevents programmatic scenario
IS reports from losing fill assumptions; all 41 affected robustness/nested/manual
IS/OOS tests passed in 107.02 seconds afterward. Python compilation, JavaScript
syntax and diff checks pass. Each gate's log/JUnit/library is preserved under
`artifacts/robust-research-m1b-20261107/`; exact commands and scope are in the review.
These overlapping gates are not added into a misleading distinct-test total.
M2–M6 and the overall Definition of Done remain incomplete.

### M2a canonical import and existing prop workflow

8 November 2026: complete canonical exports now save through RunStore with
original/canonical bytes, exact trade/cost/event validation and external research
provenance. The existing catalogue/report/configure/check/run/download journey
supports the documented annualized ordered-mark subset. Unknown path invariance,
missing event coverage, unsupported currency/quantity/calendar or dated modes
reject explicitly. Original imports and prior analysis evidence are unchanged.
Ordinary read/reopen verifies immutable files without recalculation; new analysis
revalidates semantics and captures all source artifacts. This closes the audit's
standalone-import gap, not the independent-phase/dynamic-sizing gap.

The [saved product demonstration](prop_simulation_review.md#canonical-external-trades-and-local-prop-analysis--2026-11-08)
shows $4 source net, $2 per-MNQ net, $3 observed adverse excursion, an explicitly
empty validation session and unavailable funded outcomes. Final integration
regression passed 233 tests; the final import/prop boundary gate passed 38 tests.
Both import browser journeys passed. Test counts overlap and do not establish a
full-suite or provider-parity result. M2b causal sizing integration and M3–M6
remain pending; the overall verdict stays **incomplete**.
The existing report/strategy/catalogue/configuration/mobile browser regression
also passed all 29 tests in 323.84 seconds. Screenshots were inspected and all
temporary servers stopped. Python compilation, changed JavaScript syntax and
diff whitespace checks passed.

### M2b state-aware account decisions and native capture

8 November 2026: shared causal sizing now runs before each opportunity inside
the existing Apex/Lucid evaluation/funded transitions. Phase campaigns expand
the complete source × cap × policy membership and save current-balance/cushion
bases, planning assumptions, caps, skips and bounded decision detail with complete
aggregates. Complete canonical external paths are admitted under explicit
exporter invariance assumptions; native dynamic paths reject. Native reports now
retain actual initial-stop decisions separately from later fills, with immutable
sidecar downloads and replay/cache checks. Historical missing information stays
missing. Fixed unguarded native policies retain the existing numerical scenario.

The [normal-product evidence](prop_simulation_review.md#causal-sizing-and-native-decision-capture--2026-11-08)
contains both independent phase campaigns, six candidates each, exact $100 versus
0.2%-balance quantities, skip/cap cases, desktop/mobile checks and byte-identical
reopen/downloads. A native VWAP example saves three $293 trades and the
108-signal/90-stop/115.25-fill distinction; native risk sizing rejects explicitly.

Stable gates: 144 kernel/pure tests, 36 phase/import API tests, 125 existing
phase/campaign/cache/dated/cash tests and three new browser journeys pass. The
older browser regression's removed-budget assertion was updated to the actual
128-candidate confirmation flow; its full affected file passes 2/2. A final
inner-stage guard rejects policy declarations rather than ignoring them. Its
mixed gate's nine backtest failures concerned only the new sidecar file inventory;
the entire corrected API module passes 53/53 with original numerical expectations
intact. Failed/probe logs are preserved and not relabelled clean. Exact scope,
commands, hashes and remaining limits are in the review. The whole suite remains
M6 work. M3–M6 and the overall Definition of Done remain **incomplete**.

### M3a frozen economic handoff and chronological outer scenarios

8 November 2026: optional nested Evaluation/Funded studies now consume every
qualified signal configuration, create normal full-training backtests and
independent child phase reports, and seal the complete selected family before
outer execution. Evaluation constraints apply before Pareto ranking; explicit
tie preferences use phase-only identity. Internal training context verifies
source/artifact/window/implementation membership without relabeling sources IS.
The existing worker executes children inline and safely reuses them on resume.

Phase-owned chronological replay uses actual ordered observed sessions, retains
empty sessions, rejects missing declared-open dates, and separates evaluation
fees/activation/readiness from one fresh funded account's requests, deductions,
received cash and pending claims. Dated primary-provider review captures rule
discrepancies as `UNVERIFIED`; production-qualified remains false. Historical
fixed-path calculations and saved reports are preserved.

The [normal-product review](prop_simulation_review.md#frozen-phase-selection-and-chronological-outer-replay--2026-11-08)
contains exact API/browser instructions and independent $70 acquisition and
$1,500 receipt/cutoff examples, complete-family ties and abstention. Release
browser: 3 passed; existing browser regression: 4 passed. Release API: 7 passed,
including real observed bars with zero outer trades and missing-date rejection.
Stable phase/campaign regression: 95 passed; cash/profile/replay: 74 passed.
A subsequent readiness-at-guard correction has 18 chronological checks and the
fresh release API/browser demonstrations. Counts overlap and are not a full-suite
or provider-parity claim; failed/probe gates remain recorded in the review.

M3b reliability, conservative historical-mean/baseline evidence, full-procedure
freeze/final holdout/development rerun, native state-aware execution, optional
finite-horizon lifecycle comparison, forward monitoring and M6 remain pending.
The whole requested goal remains **incomplete**.

### M3b1 references, historical mean and consolidated reliability

8 November 2026: predeclared references now use normal full-training backtests,
independent phase reports and chronological outer replay. Their separate sealed
authority permits measurement after failed edge qualification without granting
recommendation eligibility. All selected/reference packages are sealed before
any outer execution. Reference identity, source/code drift, cancellation/resume,
public context injection, native dynamic-source rejection and deletion protection
are covered by the normal API journey.

`research_reliability.py` retains every declared fold and family member, separates
known actual economics from missing forecasts, preserves censored fees and
discloses missing observations. It reports matched errors, calibration, stable
logical policy identities and predeclared paired references without choosing a
new winner. Historical output intervals use explicit block assumptions, tail
resolution and exact integer inverse-CDF ranks; they do not refit the procedure
or establish independent historical blocks. Optional conservative Funded
selection uses historical session-block resampling of the fitted expected cash
mean inside the existing owner, with complete-family tail adjustment and separate
inner Monte Carlo precision requirements.

The [saved normal-product evidence](prop_simulation_review.md#predeclared-references-and-consolidated-reliability--2026-11-08)
includes positive $1,500-versus-$0 reference comparisons, unresolved/censored
references, a conservative exact family and both explicit abstention conventions.
Final evidence matches engine
`1f3f48e652be0fe1e4cd06eb0977850c02fddce93b4381d8c4a9e2c626baed27`:
90 API captures and 49 browser downloads independently rehashed; original source
artifacts unchanged; no persistent servers. Final pure/contract checks: 116 pass.
Final affected API: four pass; preceding full integration API: twenty pass.
Final browser: four pass; preceding browser regression: nine pass. Existing
phase/campaign/profile/replay regression: 107 pass. The review records exact
scope, earlier failures, commands, IDs, expected values and immutable snapshots.
These overlapping gates do not constitute full-suite or provider qualification.

At M3b1 publication, M3b2 full-procedure verification/current development
selection, native controlled execution and forecasting, and M4/M5/M6 remained
**incomplete**. Native chronological execution was implemented in the subsequent
increment below; this does not complete native forecasting or selection.

### Native chronological account control

`prop/native_replay.py` admits an ordinary saved native IS report and orchestrates
the existing backtest engine. `execution.py` calls the strategy's provisional
entry hook before quantity-dependent state commits. `KnownDecisionRisk` exposes
the decision close and known stop without the future open. Evaluation and Funded
controllers in their phase owners apply existing provider transition primitives,
actual fills, session boundaries and the shared cash ledger. Normal trading equity
keeps actual trading P&L; provider withdrawals and Evaluation account resets use
an explicit offset rather than rewriting completed trades.

The existing prop check/run routes save an ordinary controlled RunStore child and
an AnalysisStore report with source identity, decisions, session trace, actual
trades, cash ledger and ZIP. The initial supported subset is complete one-minute
continuous/base MNQ sessions, current VWAP, EOD-flat enabled and local strategy
volatility sizing disabled. Missing sessions/minutes, unreviewed calendar dates,
NQ relabeling, dated-contract expiry and incompatible costs reject. Controlled
results cannot masquerade as unconstrained IS sources. Historical reports remain
readable; changed numerical identities reject incompatible frozen launches.

Native Monte Carlo, native phase economic search and native frozen outer replay
remain pending. This deterministic historical scenario is not a recommendation,
forecast or provider qualification. Full-procedure freeze/holdout/current
development selection, forward monitoring and final qualification also remain
incomplete. See the dated normal-product journey in `prop_simulation_review.md`.


### M2d native contiguous-block forecasts

The normal native replay form optionally adds a separately declared modeled
forecast using the existing execution engine and phase controllers. Immutable
source blocks, prior-only feature warmup, persistent provider/trading cash,
explicit source/model clocks, full addressed schedules and all-path metrics are
saved in the same AnalysisStore. The source calendar remains reviewed historical
metadata; modeled target closures/early closes are explicit and unverified.
Censoring prevents completed-only acquisition means. Equal-cohort MC standard
errors are conditional numerical uncertainty, distinct from historical-law and
future uncertainty. Preflight and publication reject excessive work/size without
truncating paths. The [normal-product evidence](prop_simulation_review.md#native-contiguous-block-forecasts--2026-11-08)
includes independent $70 acquisition, $1,500 receipt and dynamic $145 mean provider
equity-change examples, null censored means and rejection boundaries.

Final API: 17 passed. Final adapter/profile/controller/contract gate: 99 passed.
Forecast browsers: four passed; historical native browsers: six passed. All 84
browser captures were rehashed; source bytes/splits and immutable reopen were
verified. Engine identity stayed
`619d0bae83c621462f869e06b0f5fd52b3bb84d4a0c07c356560a36083bc8ba9`.
Gates overlap and are not a full baseline or provider qualification. Native
optimizer/campaign integration, native conservative historical refits, full
procedure freeze/final holdout/current-development selection, forward monitoring
and final system qualification remain incomplete.
Existing phase optimizer/profile regression also passed 68 checks. Root separately
verified 64 API components and 84 browser downloads across eight saved analyses;
compilation, changed JavaScript syntax and diff checks passed. No persistent
server remains.
### M2e / M3b2 release: native phase search and guarded complete procedures

Native candidate execution now reaches independent campaign checks/searches,
conservative Funded origin-weight refits, frozen manual OOS and every qualified
nested configuration/policy. The complete native family is selected from IS;
actual outer execution uses normal controlled backtests and cannot select again.
Source/captured-child identity, complete-family resource bounds and cooperative
publication/cancellation checks remain authoritative. Legacy saved-trade and joint
requests retain their meanings.

Complete procedure freeze and terminal applications now reuse the original
inner qualification law and independent phase owners. Metadata-only upload and
the append-only local access journal protect reserved final dates across normal
readers, caches, imports and CLI entry points. Final prices become available only
after terminal selections/references are sealed. Failed or cancelled consumed
assessments remain incomplete; current selection is a separate development-only
procedure rerun. No final-derived replacement, forced winner or universal
untouched-data certificate is produced.

Shared release engine identity:
`3a0b3bc7482e85b25d358b85459b43c84a4ee7113f52876c76130080aa09313b`.
The [normal-product journey](prop_simulation_review.md#native-phase-optimization-and-complete-procedure-verification--2026-11-08)
contains exact sources, settings, saved IDs, expected quantities/cash/rejections,
downloads and startup/stop instructions. A source archive remains at
`artifacts/native-phase-optimization-m2e-20261108/qualified-source.tar.gz`.

| Stable targeted gate | Result and saved evidence |
| --- | --- |
| Native campaign, manual OOS, nested actual replay, phase contracts/cancellation | 51 passed in 309.31 s; `native-phase-optimization-m2e-20261108/api-final/` |
| Native search/refits/forecasts/draws/ties/legacy historical mean | 71 passed in 129.67 s; `owners-final/pytest.log` |
| Native controllers, chronological profiles and pure sizing | 114 passed in 29.47 s; `owners-final/controllers.log` |
| Existing campaigns/assessment, architecture, work bounds, validation and empty sources | 37 passed / 1 local-socket sandbox failure in 227.47 s; exact two-worker case passed with process access in 2.50 s; `legacy-regression-final/` |
| Procedure/access/fold/ordinary research/data/import regression | 312 passed / 1 local-socket sandbox failure in 244.28 s; exact case passed with process access in 3.09 s; one additional terminal-reference application passed in 11.91 s; `procedure-native-search-m3b2-20261108/api-gate-final/` |
| Independent access/cancellation attacks | 7 repaired checks passed in 2.05 s; original failing timezone-alias, CLI and publication-race evidence retained under `independent-review/` |
| Native campaign browser | First run 3 passed / 1 formatting-only assertion failure in 221.18 s; actual OOS rerun passed in 56.99 s; both outputs retained |
| Complete-procedure browser | 1 passed in 26.31 s; metadata-only reservation → final failed criterion → separate current development → immutable reopen |
| Saved artifacts / static checks | Root verified 29 complete reports and 454 component files against their hashes/ZIPs; product separately verified 23 downloads and 94 ZIP members. Python compilation, seven JavaScript syntax checks and whitespace checks passed. |

Counts overlap between these suites and are not summed into a full-suite claim.
Exact commands/logs/XML, matching pre/post engine identities and scripts are saved
under the two named artifact roots. All owned servers stopped. The combined
main runs with socket failures are preserved; the specific affected cases were
rerun successfully with the required local process access.

The native nested independent oracle uses nine complete synthetic MNQ sessions,
five-session training and two two-session inner validations. In each of two
outer windows, both tied $100-dollar and 0.2%-balance policies remain frozen,
submit 10/10 MNQ on the actual later sessions, earn $400 trading profit and
receive $0 cash. The protected final example retains four policies, each receives
$0, fails its predeclared $1 floor and returns no qualified deployment candidate.
These are controlled arithmetic/research-integrity demonstrations, not evidence
of persistent market edge or provider parity.

Remaining overall work: guided research catalogue/drafts/templates and integrated
visual review; predefined frozen Evaluation/Funded pair comparison; independent
timestamped forward/paper monitoring and recovery; a complete multi-strategy
end-to-end example; final full pytest/browser/static/reproducibility acceptance.
Existing statistical-property fixtures remain part of that final audit. The
overall goal remains **incomplete**; no live route is production-qualified.

### M4 guided workspace and saved visual review

8 November 2026: **Backtests → Research** now projects ordinary independent and
nested campaigns, latest terminal applications and editable pre-work drafts.
Search/filter/pagination and source selection use metadata. Drafts/templates
share the existing AnalysisStore catalogue; exact revisions prevent lost edits,
closed settings contracts prevent transferring saved result authority, and
missing sources or unsupported policy membership remain inspectable and block
execution until explicitly resolved. Every loaded declaration needs a fresh
normal preview. The existing report displays actual fold timelines, parameter
qualification plots and matched Funded forecast/actual receipts with complete
accessible tables; plots do not introduce family weights or new selection.

Release engine: `26edd1fb4462844c5e963fdf50023316758c2dc50497310afa326bcba8b3753b`.
Evaluation/Funded declared numerical identities match `79cb5b0` (28/30 files
respectively). The global application hash correctly changes for new Python
orchestration. Earlier saved reports/evidence remain unchanged.

| M4 stable targeted gate | Actual result |
| --- | --- |
| Workspace API contracts, revisions/concurrency, missing sources/full grid membership, template authority, latest final/current status and report integrity | 33 passed in 4.84 s; `artifacts/research-workspace-m4-20261108/api-final/` |
| Draft → template → fresh preview → actual nested run → catalogue/report/downloads; missing-source/baseline rebind; exact native policy round-trip/unsupported family rejection | 3 passed in 17.38 s; `browser-final/` |
| Shared native dynamic campaign and mobile navigation regression | 2 passed in 18.88 s; `browser-regression/` |
| Saved reports and static checks | Four complete reports, 58 captured files verified against sizes/SHA/ZIP bytes; four changed Python files compiled, seven JavaScript files parsed, diff check passed. |

The independent API gate separately passed 33 checks in 5.00 s. Original failed
probes are retained, including the nested template identity and missing grid
trial defects repaired before release. Final tests left no persistent server.
The source archive, exact commands, report verification script and outputs are
saved under the M4 artifact root. The normal-product journey and expected
observations are in `prop_simulation_review.md`. These are scoped checks, not the
full repository suite or provider qualification.

Remaining overall scope: predefined frozen Evaluation/Funded pair comparison;
independent timestamped forward/paper events, discrepancy monitoring and recovery;
complete multi-strategy end-to-end evidence; final full-suite/browser/static and
reproducibility acceptance. The complete goal remains **incomplete**.


### M4b/M5 frozen pairs and independent supplied observations

8 November 2026: explicit independently frozen Evaluation/Funded pairs now use
ordinary completed manual OOS sources, the existing native execution controllers
and cash ledger over a common exclusive cutoff. AnalysisStore owns declarations,
child captures and durable format-8 reports. Every named pair remains visible;
no combined selection replaces either independent phase objective. Sources,
frozen packages, declaration retries and child integrity are guarded.

Current-development reports now launch timestamped independent observations in
the existing catalogue. Strict supplied event batches support signals, intended
orders, statuses, fills, protective orders, positions, market/connection health
and separate requests/deductions/receipts. Append-only corrections, exact FIFO
money reconciliation, immutable format-9 reports and explicit advisory recovery
reuse AnalysisStore. All demonstration observations are labelled synthetic;
actual order placement and broker enforcement are unavailable.

Release Python identity:
`3f6ce9d8ef3fd05f25aa7fc4a1a85686c67aae86ee6510063c587ad982a0ff1c`.
The normal-product journeys, exact IDs, independent expected values, download
checks and server startup/shutdown steps are in `prop_simulation_review.md`.

| Stable targeted gate | Result |
| --- | --- |
| Pair API/controllers/admission/storage and complete two-strategy research journey | 25 passed in 130.39 s; `artifacts/frozen-pair-m4b-20261108/api-final/` |
| Forward contracts, persistence, API, authority and access | 56 passed in 9.63 s; `artifacts/forward-monitoring-m5-20261108/api-gate-final/` |
| Existing phase profiles, native campaigns and cancellation after disk recovery | 35 passed in 201.27 s; `artifacts/frozen-pair-m4b-20261108/legacy-regression-resumed/` |
| Actual market-series selection properties across six requested types | 7 passed in 54.55 s; `artifacts/selection-properties-m6-20261108/final-resumed/` |

A preceding legacy gate was interrupted after 54 passes when storage filled;
its evidence is retained and is not called a full pass. The first resumed browser
attempt could not launch a missing Playwright executable; the restored-browser
gate passed the pair and bound-forward journeys, with a browser-option assertion
failure in the no-qualified diagnostic case. Its exact assertion is being
corrected against the observed native disabled attribute/property, preserving
the API rejection check and original evidence. Counts overlap; no full-suite
claim follows from these targeted results.

Independent review identified two remaining local forward capabilities: a
complete compatible observation window needs a descriptive forecast-versus-cash
comparison, and supplied causal sizing decisions need arithmetic checking against
the frozen policy. Neither can be replaced by a generic external-integration
warning. Both are the next increment, followed by uninterrupted full-suite,
browser, static, export/reproducibility and final documentation acceptance.
The complete goal remains **incomplete** and live integration **unverified**.


M4b/M5 browser closeout: the no-qualified diagnostic passed its fresh exact rerun
in 7.56 s after correcting only the assertion to inspect the native disabled
attribute. All three normal journeys now pass on unchanged Python identity. The
saved browser verification index checks 20 downloads, 56 ZIP members and three
zero-POST reopens; desktop and 390 px views were inspected. All temporary servers
stopped. Python compilation, five changed JavaScript syntax checks and whitespace
validation passed. Original failed attempts remain preserved.

## Current implementation and qualification map

This is the current map, distinct from the initial audit above. **Implemented**
means the named local capability exists. **Tested** refers to saved targeted
API/browser/independent-oracle evidence; it does not imply the pending full
repository gate passed. Provider verification is never inferred from local tests.
The final forward comparison/conformance rows and repository acceptance will be
updated after their actual gates finish.

| Required stage | Local implementation / normal product entry | Implemented and tested evidence | Provider-verified / remaining boundary |
| --- | --- | --- | --- |
| Source identity, research declaration and protected data | `datasets.py`, `research_access.py`, `research.py`; Datasets metadata-only reservation → ordinary IS grid | Strict metadata/cost/split contracts, prior-access overlap and timezone/domain guards, source deletion and failed access history tested | Dataset rights/completeness and externally accessed history are supplied claims; local journal is not a global untouched-data certificate |
| Nested rolling/expanding research | `research_folds.py`, `robust_research.py`; saved IS report → Configure prop → Nested research | Actual ordinary fold-restricted backtests, purge/embargo, session boundaries, leakage/future mutation, progress/cancellation and restart tested | Model research mechanics; no claim of future edge |
| Robust configuration regions | `edge_qualification.py`, `research_complexity.py`, `research_regimes.py`; candidate evidence and plots | Complete family, temporal/concentration/region bounds, cost/execution stresses, causal regimes, PASS/FAIL/INSUFFICIENT tested; real market-series properties now 7/7 | Sparse synthetic fixtures are arithmetic demonstrations, not executable market evidence or a universal null classifier |
| Canonical external trades / MultiCharts | `trade_imports.py`, `canonical_trades.py`, `prop/source.py`; Backtests → Import external trades | Raw-byte/provenance/cost validation, complete versioned export ingestion, ordered risk-event admission, meaningful rejection and durable downloads tested | Supplied MultiCharts-compatible exports supported; exporter/platform parity and missing tick order remain unverified; incomplete measured risk is never fabricated |
| Fixed, fixed-dollar and explicit percentage risk | `prop/sizing.py`, `sizing_runtime.py`, native control and phase owners; independent campaign sizing controls | Floor/rounding/zero skips/cost reserves/caps/changing balance/cushion, native strategy reruns and captured decisions tested | Native supported complete-minute MNQ/VWAP path only; invariant external paths require an explicit source claim; other source/profile combinations reject |
| Independent Evaluation | `evaluation_profiles.py`, `evaluation_optimization.py`, `phase_dispatch.py`; Evaluation campaign | Acquisition fees/calendar-time complete Pareto, censoring, full family and phase input isolation tested | Provider rule versions are saved; known discrepancies and dated field-level verification remain in `provider_rule_review.md`; no funded objective is used |
| Independent Funded | `funded_profiles.py`, `funded_optimization.py`; Funded campaign | Fresh-account finite-horizon receipt selection, uncertainty, all tied alternatives and optional conservative historical mean tested | No Evaluation fees/pass probability/time, replacement account or joint annualized selector; payout settlement is modeled and explicitly unverified |
| Native chronological execution and separate forecasts | `native_replay.py`, `native_control.py`, `native_draws.py`, existing execution engine; native source check/run/report | Actual causal sizing/order/fill/account halts, prior-only warmup, saved block schedules and modeled calendar; ordinary outer/manual OOS child backtests tested | One-minute OHLC is not tick execution; source chronology, modeled draws and cash timing remain distinct |
| Frozen outer reliability and references | `research_phase_selection.py`, `research_reliability.py`; outer report tables/plots/downloads | Every frozen family, missing/censored/abstained outcomes, predeclared baselines, paired differences and uncertainty labels tested | Monte Carlo error differs from history/model/future uncertainty; unresolved evidence can block endorsement |
| Complete procedure, final holdout and current rerun | `research_procedure.py`, `research_procedure_store.py`; existing procedure controls | Full algorithm freeze, terminal development fit, seal-before-final, access guard, no final reselection, fresh current fit and no-qualified outcomes tested | Prior access remains visible and final history is not erased; no research status confers deployment readiness |
| Optional frozen phase-pair comparison | `prop/frozen_pairs.py`, `phase_lifecycle.py`, `cash_ledger.py`; existing prop pair controls | Exact explicit pairs, ordinary completed OOS, common cutoff, source/package/child guards, retry/cancel, receipt/fee arithmetic and mobile report tested | Historical path comparison only, no pair optimizer/ranking, new provider parity or implicit replacement |
| Guided research workspace | `research_workspace.py`, `web/research_workspace.js`, `research_visuals.js`; Backtests → Research | Search/filter, complete source selection, revisioned drafts, source-free templates, timelines/regions/cash tables, downloads and desktop/390 px journeys tested | Unsupported saved settings remain inspectable and reject rather than being silently converted |
| Independent forward observations and advisory recovery | `forward_contracts.py`, `forward_policy.py`, `forward_reconcile.py`, `forward_monitoring.py`; current report → Observe current policy | Supplied signal/intents/orders/fills/protection/positions/cash, corrections, exact money, latency/health, latched PAUSED and explicit recovery, immutable snapshots tested | Synthetic/paper/actual-import provenance stays separate; no continuous broker connection, external signal proof, automatic broker pause or order placement |
| Matched forward forecast scope and sizing conformance | `forward_comparison.py`, `forward_conformance.py`; same monitor/check/import/report workflow | Implemented; independent cash/clock/source-identity and fixed/dynamic arithmetic gates pass; final combined API/browser demonstrations running | Requires explicit prospective coverage/calendar/account claims. Cash eligibility/request/approval behavior remains unverified; descriptive differences are not broker or statistical certification |
| Whole-workflow and legacy qualification | Existing pytest/Playwright/static infrastructure; saved normal libraries | Two genuine strategies/four configurations, two independent phases, all outer outcomes and fresh terminal recommendation tested; full uninterrupted suite pending | Complete local acceptance remains required before goal completion; no production-qualified live integration |

Current unsupported behavior includes automatic account replacement in independent
Funded selection; cross-phase weighted objectives; optimizing the predefined
phase-pair list; native execution for arbitrary strategies/instruments or incomplete
minute sources; automatic promotion from final outcomes; direct TradingView,
PickMyTrade, Tradovate or other broker order placement; and inference of tick-level
fills or measured MAE/MFE from missing data. Existing legacy reports/readers retain
their original meanings and engines.

### Final acceptance record

The required uninterrupted complete pytest gate is **running** on the final
forward-comparison implementation (2,270 collected tests). Targeted successes
above must not be summed into a full-suite claim. Final qualification will record the exact source commit/hash,
command, environment, totals, elapsed time, browser/static results, saved-report
checks, reproducibility evidence and remote branch/main refs here.


M4b/M5 independent artifact closeout: root verified 53 complete saved reports and
742 component files against recorded byte counts, SHA-256 and ZIP entries across
pair/forward/two-strategy/property libraries. Verification script/index and the
full tracked `27cf056` checkout archive are saved under
`artifacts/frozen-pair-forward-m4b-m5-20261108/`. The synthetic two-strategy CSV
has the same SHA-256 as the actual uploaded dataset. Exact IDs, user steps,
expected quantities/cash and new-library commands are in the review log.
Nine current guides have valid local link destinations. These checks establish
artifact integrity and documentation consistency, not provider parity.


Final forward review before qualification also requires frozen sizing-code
identity: recalculating a saved policy under a changed sizing implementation must
withhold local conformance and forecast comparison. The supplied ledger remains
inspectable. This preserves the rule that numerical compatibility cannot be
restored by omitting changed calculation code from identity.

### M5b supplied-scope cash comparison and frozen sizing arithmetic

The existing monitor form now optionally seals a prospective single-cohort
Funded observation plan. Exact saved dates remain distinct from an explicitly
assumed calendar-pattern translation; original forecast dates and metrics are
retained. Complete account coverage, fresh opening/flat cutoff snapshots, known
pending amounts and linked gross/net cash conservation gate a descriptive
one-path receipt difference. A partial, incompatible or unknown scope stays
NOT_COMPARABLE. The checker does not require actual cash to equal the forecast:
payout eligibility, request timing and approval implementation remain unverified.
Supplied deviations are visible rather than silently converted into model paths.

Local sizing conformance reuses `prop/sizing.py` with the frozen policy/costs and
supplied causal account/stop context. It compares fixed and dollar/percentage
quantities, named denominators, caps, skips and rounding; later fills cannot enter
a sizing decision. Predecision balances reconcile to the observed ledger. Saved
and current sizing-source hashes must agree. A mismatch creates advisory PAUSED;
unknown context withholds conformance. Arithmetic agreement does not establish
strategy eligibility, provider state, external implementation or broker control.

Final release Python identity:
`1ff01f1e8e370ef6781b5ec579ce60749310fbe3c0fcb5f78030c7aa7299f5e6`.
The focused owner/API/storage/access/conformance gate passed **114 tests in
28.96 s**. The real-trade comparison browser passed **1 case in 14.97 s**:
3 MNQ earns $6 gross less $3 commissions; actual received $50 minus frozen
expected $1,500 is −$1,450, with ending provider balance $49,953. Partial coverage
withholds comparison; completing it appends a new report. Correcting a receipt
to $25 changes the API demonstration difference to −$1,475 and pending to $25,
while earlier bytes stay unchanged. The normal API publisher verified 36 downloads
and exact reopen. All inputs and receiver-clock manipulation are explicitly
synthetic test-harness evidence; product controls cannot change the server clock.

Retained failed probes found and repaired the distinction between financial
cutoff and later assessment knowledge, incompatible linked deductions, missing
sizing-source identity and coverage/access edge cases. The failed source identity
`289580777e467bbd336db1f347c8d86a9a121e2361402c59565eb28f024f41df`
and full source archive remain under `artifacts/forward-comparison-m5b-20261108/`.
Failed attempts are not included in a clean combined-gate claim. A copy-only UI
clarification after the passing browser makes the supplied trading/sizing-policy
claim explicit; final full-suite browser execution will exercise that wording.


The final authoritative dynamic API example passed **1 test in 182.93 s** on
unchanged release identity. It generates an ordinary complete-minute native
source, qualified nested study, predeclared one-MNQ reference and fresh current
procedure policy. Supplied 0.8%-balance decisions independently recompute to
10 then 9 contracts at $40 planned risk as balance moves from $50,000 to $49,900;
actual synthetic trading P&L is $80 and final equity $50,080. A changed supplied
quantity yields MISMATCH/PAUSED and preserves the earlier report. Typed provenance
is `synthetic_harness`/`SYNTHETIC_ONLY`; no complete observation horizon is claimed.
Evidence is `artifacts/forward-comparison-m5b-20261108/dynamic-api-final-v2/`.
An earlier 190.09 s passing probe is retained but used a paper type despite its
synthetic name/source; the final gate corrects that typed provenance explicitly.

The uninterrupted full suite has started with **2,270 collected tests** and
`tmp_path_retention_policy=all`, in a fresh `full-suite-v1` directory under
`artifacts/final-research-acceptance-20261108/`. Its runner saves the exact command,
PID, dependency/platform versions, initial/final Python and web hashes, exit code,
XML/logs and retained normal libraries. A dedicated fallback data directory keeps
default application startup inside that fresh evidence tree. The suite has not
finished; no overall completion or clean full-suite result is yet claimed.
