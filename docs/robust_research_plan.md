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
| M2a: canonical sources | Existing native and XLSX adapters | Normal import/source-check/report workflow supports complete standalone external trades | Identity/hash/count/time/cost/partial/ordered-event rejection and reopen | pending |
| M2b: sizing | M2a; common state-aware policy in existing account owners | Fixed/dollar/percentage policies with named base, skips/caps and saved decisions | Hand math, changing stops/balances/cushion, unsupported sources, unchanged fixed simulations, compiled/reference parity | pending |
| M3a: frozen economic selection and historical replay | M1/M2; existing phase optimizers and ledger | Select on development only, freeze family, replay actual outer dates including no-trade days and receipts | Phase independence, cutoff/retry/cash conservation, frozen hash guards, no reselect | pending |
| M3b: reliability and final procedure | M3a; predeclared baseline/rules/scenarios/access history | Outer aggregate, uncertainty, baseline, complete procedure freeze/holdout/final rerun; permit no qualified candidate | Future poisoning, holdout access guards, limited calibration, uncertainty semantics, source/code identity | pending |
| M4: cohesive guided UX | Incremental UI delivered throughout M1–M3 | Review end-to-end first-user journey, templates, timelines/regions/cash charts and decisions; useful cancellation/resume | Desktop/narrow browser journeys, loading/errors, export/reopen byte identity, accessibility | pending |
| M5: forward and monitoring | Frozen recommendation/event contract; no broker dependency | Timestamped supplied or explicitly synthetic paper evidence, reconciliation and advisory states/recovery | Misses/duplicates/partial fills/protection/staleness/disconnect/latency, restart and readiness gates | pending |
| M6: final qualification | All earlier milestones | Full Definition of Done with branch/history/docs/evidence/readiness report | Full pytest/browser checks, configured static checks, reproduction and export checks, verify pushed ref/main unchanged | pending |

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
