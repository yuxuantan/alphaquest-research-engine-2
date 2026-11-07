# Phase research campaigns

[Home](../README.md) / [Docs](README.md) / [Research workflow](research_workflow.md)

Implemented 6 November 2026. One campaign compares saved IS backtests and saved
optimization trials across strategies/jobs at declared whole-MNQ sizes. Evaluation
minimizes acquisition cost and calendar time with a Pareto frontier. Funded ranks
expected trader receipts within a saved horizon after applying hard empirical risk
constraints. The two declarations, source sets and calculations are independent.

## Normal product workflow

1. Run an ordinary IS backtest or exhaustive optimization grid. Open a saved
   backtest/trial report and choose **Configure prop analysis**.
2. Under **Independent phase research campaigns**, select **Create Evaluation
   campaign** or **Create Funded campaign** and the local account profile. The current saved
   backtest is preselected. Use **Add saved source**, choose Backtest or
   Optimization job, then select a saved item from its dropdown. Search by
   strategy, parameters, dataset, date or ID; **Load more sources** retrieves
   older matches. Full parameters and IS dates appear below the selection.
   For jobs, enter selected trial numbers or leave blank for the complete saved
   grid. Give each source its own MNQ size list.
   Eligible canonical external IS imports can use this same path. To compare
   state-aware sizing, choose **Compare sizing policies**, add the policy rows
   and explicit MNQ planning assumptions; the size list becomes hard caps.
   Every source × cap × policy combination remains in the checked membership.
3. The IS first/last sessions default to the common saved coverage within the
   selected sources' declared IS splits. These are CME Chicago session dates,
   including observed sessions with no trades. Optionally narrow the window;
   **Use full common IS window** resets it. Source or selected-trial changes
   derive it again. Declare simulation count/seeds and
   scenario start date. Calendar coverage is derived automatically and displayed
   after checking. Evaluation also declares purchase/activation prices and
   chain counts/seeds. Funded declares receipt horizon, settlement delay and
   maximum breach probability. The UI uses captured source costs; the API exposes
   the full supported phase configuration.
4. **Save and check candidates** calculates the full candidate count. Above 128,
   a confirmation dialog shows the exact count; Cancel saves nothing. Confirm
   to continue. It then reconciles every source, records full membership,
   and enables **Run campaign** only on success. Changing inputs requires a new
   check and immutable declaration. No final OOS is scheduled or inspected.
5. The same prop report screen displays all candidates, strategy parameters,
   account/rule versions, research windows, original source links and downloads.
   Evaluation shows acquisition cost, calendar mean/median/P90, pass and 30/60-day
   funding probabilities, throughput, MC error and censoring, plus a cost/time
   scatter with Pareto markers and marginal acceleration table. Funded shows
   mean/median/P10/P90 cash, first receipt probability/conditional time, breach,
   horizon survival, pending cash and empirical constraint status, plus ranking
   and an all-start receipt histogram. Strategy/size/profile filters change only
   presentation; zero, unresolved and infeasible candidates remain saved. Select resolved frontier points
   or feasible funded candidates, enter a rationale, and **Freeze selected
   candidates**. Reopen from the saved campaign links in prop configuration or
   its durable URL `/#backtests/prop/campaign/<campaign_id>`.
6. After freeze, select **Launch OOS with frozen settings**. This manually runs
   ordinary OOS backtests from the selected IS parents, then appends a linked
   assessment report. Open **Open frozen OOS assessment** and download its ZIP.
   No settings are editable on this launch, and no OOS ranking/winner is returned.
   Repeated manual launches append and display prior access; they never update IS.
   Imported sources cannot use this native rerun: their frozen package remains
   downloadable, with an explicit unavailable reason and no fabricated OOS.

Campaign reports are independent phase results. Existing annualized joint sizing
and budgeted cash-ledger workflows retain their request meanings and reports.

## Explicit sizing policies — 8 November 2026

Each source may add `sizing_policies`, a nonempty list of up to 60 distinct
configurations. Omission/null preserves legacy fixed-size candidates. Each
configuration is expanded with every declared source size (now a user cap);
there is no truncation or joint-phase score. Direct phase candidates use the
same object as optional `sizing`:

```json
{
  "policy": {
    "kind": "percentage_risk", "risk_percent": "0.2",
    "reference": "current_account_balance",
    "minimum_contracts": 1, "maximum_contracts": 40,
    "constrain_to_account_cushion": false,
    "constrain_to_daily_cushion": false
  },
  "initial_configured_capital": "50000",
  "planning_execution": {
    "tick_size": "0.25", "point_value": "2",
    "entry_slippage_ticks": 0, "stop_exit_slippage_ticks": 0,
    "commission_per_contract_per_side": "0"
  }
}
```

This example explicitly assumes zero planning costs, not a verified market fee.
Fixed-dollar policies supply `risk_dollars`; fixed contracts supply `contracts`.
Only fields for the chosen kind may be present. Percentage references are
initial configured capital, current account balance or available drawdown
cushion. Money is a bounded decimal string, whole quantities are strict integers,
and guards are strict booleans. See the [arithmetic/source contract](prop_simulation.md#state-aware-independent-phase-sizing--2026-11-08).

Policy, planning execution, source/cost/risk identity and implementation hashes
enter the candidate key and freeze. Distinct policies at the same cap remain
distinct through native fixed-policy OOS matching. Phase reports save complete
decision aggregates and bounded retained detail, with ordinary
`sizing_summary.json` / `sizing_decisions.csv` / JSON / ZIP downloads. Planning
costs never become an additional deduction from source net returns.

## Automatic calendar coverage — 7 November 2026

The portal no longer asks for a Calendar coverage end. **Save and check candidates**
lets the server resolve it, then shows the resulting date in the check status.
The historical IS window stays unchanged; extending a simulated calendar does not
require future market bars or imply verified future market/provider conditions.

For campaign requests using the default `user-declared-weekdays-v1` calendar,
`search_settings.calendar.coverage_end` may be omitted:

- Evaluation: latest `start_dates` entry + `retry.max_calendar_days`, using the
  existing 3,650-day default when omitted. This is exact civil-day addition,
  including leap days, rather than adding ten calendar years. The chain cutoff
  and attempt limits are unchanged.
- Funded: latest start + `horizon_calendar_days`. Fixed civil-day receipt delays
  may leave pending receipts after that cutoff; they do not extend the simulated
  trading horizon or require further calendar coverage.

The normalized `manifest.request.calendar` and report/download `request.json`
save a concrete end date. Run, freeze, OOS and reopen use this saved request;
they never recalculate coverage for an existing campaign. An equivalent explicitly
specified calendar has the same numerical identity/reuse behavior. Explicit API
coverage remains supported and is validated as before, including rejection of
insufficient coverage. Other calendar version labels require explicit coverage;
automatic derivation does not invent coverage for externally versioned calendars.
Direct standalone `/api/prop-analyses` searches retain their explicit calendar
contract. See [saved workflow evidence](prop_simulation_review.md#automatic-campaign-calendar-coverage--2026-11-07).

## Valid IS window defaults — 7 November 2026

`POST /api/research-campaigns/source-window` accepts `{"sources": [...]}` using
the normal saved Backtest/Optimization job references and optional trial lists.
It resolves exactly the selected saved members, intersects each declared IS
split with its actual `period_start_utc`/`period_end_utc` converted to CME session
dates, then returns their common `is_window`, per-source declared/saved bounds
and the date convention. The form uses that metadata for its initial values and
date bounds; it does not copy the wider split declaration into the date fields.

This read-only metadata operation creates no campaign, loads no trade/dataset
or OOS outcomes and does not simulate or qualify sources. Incomplete, missing,
OOS/undeclared sources and disjoint windows reject. A pending/failed window
lookup leaves Save/check and Run disabled; stale lookup responses are discarded.
Normal Save/check still validates dates, source identity, costs, risk and common
research protocol. Explicit API windows are never silently clipped or changed.

Manual narrowing remains available within the displayed bounds. Edits to other
simulation settings preserve it; changing the source/trial selection restores
the automatic common window. The independent scenario start date and future
calendar coverage remain separate. Existing saved requests/reports and phase
implementation identities are unchanged. See [normal-product evidence](prop_simulation_review.md#valid-is-window-defaults--2026-11-07).

## Choosing the source type

Use **Backtest** for a completed IS report, including an individual trial report.
Use **Optimization job** for the parent IS grid. The dropdown shows its saved
status and disables incomplete jobs; resume those grids before selecting them.
You may select an already completed trial directly as a Backtest without selecting
or resuming its parent grid. Switching source type clears the previous selection.
OOS and undeclared reports are excluded. Listing a source does not certify its
compatibility: **Save and check candidates** still validates the selected sources.

The arithmetic demo IDs in the review log are backtest IDs; leave both source
rows set to Backtest and search for those IDs. Direct API requests still use IDs
and retain explicit errors for wrong-type, missing and incomplete sources.

## Admission, budget and scaling

- There is no maximum-candidate field or fixed candidate-count ceiling. The
  server counts selected saved trials × declared sizes **before** source checking
  or calculation. Above 128, campaign creation returns HTTP 409 with
  `detail.code="candidate_confirmation_required"`, `candidate_count` and
  `confirmation_threshold`. After explicit user confirmation, resend the same
  declaration with `confirmed_candidate_count` equal to the returned count.
  Missing or mismatched acknowledgement rejects without saving/queueing a
  campaign. Exactly 128 needs no confirmation; edits require checking again.
  No hidden top-N, ranking-based
  pruning, default winner or silent truncation. Different parameters are
  ordinary grid trials; campaigns never manufacture parameters without backtesting.
- `maximum_candidates` is deprecated: old API declarations remain accepted and
  saved history stays unchanged, but this field no longer limits new searches.
  Confirmation is recorded in the campaign manifest/declaration and campaign
  export, outside numerical inputs. Standalone phase `/api/prop-analyses/check`
  and submit requests also require `confirmed_candidate_count` above 128; their
  explicit candidate lists have no count ceiling. The existing path/day/queue
  and report-byte limits still apply, even after confirmation.
- A referenced optimization must be complete. An omitted trial list expands the
  entire grid and verifies its saved membership. Missing, failed, interrupted or
  incomplete members reject; resume the ordinary optimization first. Explicit
  trial lists preserve the original grid definition, full grid count, selected
  indices and failed-trial metadata. The campaign candidate count includes the selected
  source × size search, not the earlier grid's total work; both counts remain
  visible. Repeated sizes, repeated trial indices and duplicate candidates,
  including the same backtest reached through a job alias or an equivalent
  strategy/parameter/size saved under another report ID, reject.
- All candidates share the declared IS window, dataset identity, research split,
  execution/cost protocol and one supported account profile/version. OOS and
  undeclared sources reject. Prior-access *metadata* is captured at declaration
  and refreshed at freeze; no OOS prices, metrics or automatic joint results enter
  selection. A prior-access record never implies untouched final evidence.
- Admission reuses `prepare_phase_source`: NQ/MNQ identity, quantities, net costs,
  captured intratrade risk, a common risk convention (measured excursions and
  held-OHLC bounds cannot be mixed), intraday-flat trades and qualified fixed-quantity
  strategies. Linear MNQ scenarios preserve entry/exit behavior and proportional
  costs only. Native volatility/account-dependent source sizing rejects. A different sizing or
  execution policy requires a fresh ordinary backtest; unsupported dynamic
  sources are not made scalable by supplying a size list. No liquidity/market
  impact or measured MAE/MFE is invented.
  Canonical external sources instead retain exporter-declared IS sessions and
  path invariance, complete ordered marks, exact costs and causal stops for
  risk-based policies. These declarations are not independently verified market
  evidence. Native and external provenance/risk conventions cannot be silently
  mixed. Native risk-based/cushion policies require a suitable strategy rerun;
  optional decision capture alone does not establish signal invariance.
- Evaluation currently supports local Apex EOD. Funded supports local Apex EOD and
  LucidFlex. Rule versions come from `GET /api/research-campaigns/defaults`.
  These are implemented local snapshots, not live provider verification.

## API

All routes use the existing FastAPI host/origin checks and local worker. UUID path
parameters accept normal UUID strings; request/source IDs use lowercase 32-digit
hex. Unknown fields reject. Invalid inputs return 422, missing campaigns 404, and
immutable-ID conflicts, changed numerical identities, premature reads/freezes or
queue saturation return 409. Source files disappearing during a new check reject.

| Method and path | Behavior |
| --- | --- |
| `GET /api/research-campaigns/defaults` | Current local profile versions. |
| `GET /api/research-campaigns/sources?kind=backtest_id&q=&offset=0&limit=50` | Search saved IS source metadata. Kind is `backtest_id` or `optimization_id`; limit 1–100, offset ≥0, query ≤200 characters. Returns `items`, `total`, `offset`, `limit`; each item includes `selectable`. |
| `POST /api/research-campaigns` | Validate and save immutable declaration; 201. Identical campaign-ID retry returns its saved record. Different declaration with the same ID returns 409. |
| `GET /api/research-campaigns?source_id=...&limit=50&offset=0` | Saved campaign navigation, optionally filtered to a member backtest. Limit 1–100. |
| `GET /api/research-campaigns/{id}` | Saved declaration, manifest, current calculation status and frozen package. Reopens without calculation. |
| `POST /api/research-campaigns/{id}/check` | Recheck source identity and numerical implementation; return all candidate checks. |
| `POST /api/research-campaigns/{id}/run` | Idempotently queue/reuse the ordinary phase analysis; 202. No overrides. |
| `GET /api/research-campaigns/{id}/attempts` | All retained calculation attempts and their statuses/errors, including interrupted attempts. |
| `GET /api/research-campaigns/{id}/candidates` | All completed candidate results, including unresolved/infeasible/dominated members. |
| `GET /api/research-campaigns/{id}/selection` | Evaluation frontier/acceleration or funded ranking/constraints/near-ties. |
| `GET /api/research-campaigns/{id}/exports/{kind}` | `campaign.json`, `results.json`, `results.csv`, `report.json`, `source_checks.json`, `analysis.zip`, `frozen_package.json`. |
| `POST /api/research-campaigns/{id}/freeze` | Immutable explicit candidate selection, optional names and rationale, linked to report and campaign hashes. Exact retry reopens it. |
| `POST /api/research-campaigns/{id}/assessments` | Manual frozen OOS launch; body only `request_id` (new UUID hex). Reuses the ordinary OOS backtest path, queues an assessment-only phase report, and returns 202. |
| `GET /api/research-campaigns/{id}/assessments` | Append-only attempts, pre-launch access history, OOS source IDs, calculation progress/errors and saved report links. |

`campaign.json` is a saved-declaration/status export; status can evolve during
execution. `results.*` and ZIP come directly from the sealed AnalysisStore report.
The frozen package contains immutable references, selected candidate IDs, hashes
and access metadata. It does not duplicate trade files or the calculation report.
Download both campaign/freeze records and the analysis ZIP for offline review.

The source picker projects metadata from the existing catalogue: ID, strategy,
parameters/grid ranges, dataset name, creation date, IS dates, status and trial
count. It does not return performance outcomes or read trade/report files. Results
are ordered newest first, with ID as a stable tie-breaker. Search ignores case
and treats strategy underscores as spaces. For example:

```bash
curl -sS --get http://127.0.0.1:8000/api/research-campaigns/sources \
  --data-urlencode 'kind=optimization_id' \
  --data-urlencode 'q=consecutive green' --data-urlencode 'limit=50'
```

### Example Evaluation declaration

Use real saved IDs from the normal backtest/optimization endpoints. This example
is a request template, not a claim that the example IDs or provider prices exist.
Retrieve `profile.rule_version` from `/api/research-campaigns/defaults` and replace
all angle-bracket values before submission:

```json
{
  "campaign_id": "<new UUID hex>",
  "phase": "evaluation",
  "profile": {
    "profile_id": "apex-50k-eod",
    "rule_version": "<saved local version>",
    "evaluation_price": "30",
    "activation_fee": "40"
  },
  "sources": [
    {"optimization_id": "<VWAP job ID>", "trials": [1, 2, 3], "sizes": [10, 20, 30]},
    {"optimization_id": "<Green Hold job ID>", "trials": [1, 2], "sizes": [10, 20]}
  ],
  "is_window": {"first_session": "2026-01-05", "last_session": "2026-01-14"},
  "simulation": {"simulations": 1000, "seed": 42, "max_micros": 40},
  "sampling": {"block_weekdays": 5, "chain_simulations": 1000, "chain_seed": 45},
  "costs": {"mode": "source"},
  "retry": {"activation_delay_sessions": 1, "retry_delay_calendar_days": 0},
  "search_settings": {
    "calendar": {"start_dates": ["2026-01-05"]}
  }
}
```

The expansion is `3 × 3 + 2 × 2 = 13`. Trial numbers are the saved job's `trial`
values, not positions in a sorted display. A direct saved source uses
`{"backtest_id":"<ID>","sizes":[10,20]}`. Optional `trade_file` and
`export_timezone` live on each source entry for an explicit reconciled companion
export; no automatic export discovery occurs during campaign selection. Initial portal
prop configuration also requests `discover_exports=false`; supply an explicit
companion path when needed instead of scanning unrelated Downloads files.

### Independent Funded declaration

Use a **new campaign ID** and independently chosen `sources` and `sizes`. Set
`phase` to `funded`; the profile contains only `profile_id`, `rule_version` and
optional funded `daily_loss_limit`/`approval_day_counts`. Remove evaluation price,
activation fee and `retry`. Sampling accepts only `block_weekdays`.

```json
{
  "calendar": {"start_dates": ["2026-01-05"], "coverage_end": "2037-01-01"},
  "horizon_calendar_days": 90,
  "receipt_delay_calendar_days": 4,
  "constraints": {
    "maximum_account_breach_probability": 0.1,
    "minimum_probability_first_payout": 0.5,
    "minimum_p10_payouts": 0,
    "maximum_position_size": 20
  },
  "bootstrap_replicates": 400,
  "bootstrap_seed": 137,
  "near_tie_cash": 0
}
```

This is the funded `search_settings` object. Acquisition fees/probabilities/time
are forbidden. Receipt delay is explicit, including zero; requests due exactly
at the exclusive horizon remain pending. Hard constraints filter empirical
estimates, not confidence-certified future risk. The saved horizon is one fresh
funded account with no implicit replacement.

Submit and inspect using the existing local server:

```bash
curl -sS -H 'Content-Type: application/json' --data-binary @campaign-request.json \
  http://127.0.0.1:8000/api/research-campaigns
curl -sS -X POST http://127.0.0.1:8000/api/research-campaigns/CAMPAIGN_ID/check
curl -sS -X POST http://127.0.0.1:8000/api/research-campaigns/CAMPAIGN_ID/run
curl -sS http://127.0.0.1:8000/api/research-campaigns/CAMPAIGN_ID
curl -sS http://127.0.0.1:8000/api/research-campaigns/CAMPAIGN_ID/selection
```

Freeze after completion with the exact IDs returned by selection:

```json
{"candidate_ids":["<candidate SHA-256>"],"rationale":"Chosen IS cost/time trade-off under the declared constraints.","names":{"<candidate SHA-256>":"Conservative IS choice"}}
```

Multiple evaluation frontier points may be frozen as an explicit family. Funded
selection may freeze any feasible ranked candidate(s); the rationale preserves
the manual decision rather than silently overriding it with the displayed winner.
Unresolved competitors block freeze. A different frozen choice requires a new
campaign; no frozen record is overwritten.

## Storage, reuse and recovery

`research_campaigns`, `campaign_sources`, `campaign_jobs`, `campaign_analyses` and
`campaign_assessments`
are additive tables in the **existing** `prop_analyses/catalog.sqlite3`. They hold
small manifests/references. Original strategies/parameters, source/risk/cost hashes,
IS declaration/access metadata, profile/fees, sampling/seeds, calendar, objective,
constraints, candidate count/confirmation, screening/refinement state and numerical identity are saved.
Original optimization grids/trials stay in the backtest catalogue. Calculations,
source captures, CSV/JSON and ZIP are published once in normal AnalysisStore.
Equivalent campaigns reuse the same valid immutable analysis, including when
source declaration order differs. No campaign directory copies trades/reports.

One exhaustive declared sampling stage is implemented: screening is validated,
queued/running, error or complete; refinement is explicitly `not_requested`.
There is no adaptive pruning or automatic precision refinement. The numerical
identity uses the phase implementation/kernel/source-admission hashes separately
from presentation. Web styling and documentation changes do not invalidate it;
changed calculation code or inputs require a new campaign. Saved completed
reports still reopen without the current calculator or dataset reader.

The normal single analysis worker and exact 128 MiB report cap apply, plus existing
phase path/day preflight bounds. Campaign submission rejects when eight analyses
are pending. An interrupted worker becomes an error on startup. Explicit Run
retries the immutable declaration, preserves the failed attempt and reuses any
valid completed calculation; partial output is never a completed selection.
Concurrent identical Run calls share the same lock/idempotency key. A damaged
completed report fails closed rather than mutating a frozen result.

All campaign source backtests, explicitly referenced jobs and calculation attempts
are dependency protected, including after completion/freeze. There is no campaign
retirement/deletion API in this increment. Other datasets/backtests/results and
previous evidence remain unchanged.

## Scope and reproducible evidence

This delivers campaigns over **already saved** grids/trials, portal comparisons,
IS selection freeze and manual frozen-package OOS assessment. It does not launch
new parameter grids or implement adaptive screening/refinement. Portfolio
optimization is not implemented. Provider/external-engine parity is not claimed.

The frozen package captures candidate names/strategy/parameters, source identity,
account declarations, actual rule source snapshots, model/code hashes, costs,
seeds, scenario calendar/horizon, search history/criteria and prior access.
Assessment uses the same calendar/start cohort and horizon on resampled OOS
observations, rather than changing the declared experiment. No size search or
selector runs. Funded empirical risk limits are checked per frozen candidate;
Evaluation re-estimates acquisition metrics without an OOS frontier. Assessment
reports have `selection_status: assessment_only_no_reselection`, `winner: null`
and empty frontier/ranking. They never mutate the frozen package or IS report.
Ordinary automatic joint reports on OOS sources retain their legacy meaning.

The manual launch currently supports captured native-risk sources. A frozen
candidate using a separate measured export rejects before OOS execution because
an independently reconciled OOS export is required. Changed calculation/rule code
also rejects; no new engine silently substitutes for the frozen implementation.
Failed or interrupted launches remain in history. Use a new manual request ID to
append a fresh attempt; exact network retries return the saved attempt. Restart
marks interrupted launches as errors. Reads/reloads/downloads never launch OOS.
Previously accessed OOS remains labelled, with unlimited manual history.

See [the review log](prop_simulation_review.md#phase-research-campaigns--2026-11-06)
for actual saved campaign IDs, independent expected outputs, downloads and exact
reproduction commands. The independent reviewer imports only the Python standard
library; test-only analytical expectations never enter product calculations.
# Nested inner research API — 7 November 2026

The additive `/api/research-campaigns/robust` routes use the same application,
campaign reference tables, backtest catalogue and AnalysisStore as phase
campaigns. Existing Evaluation/Funded requests retain their meaning.

- `GET /defaults`: explicit fold and qualification defaults.
- `POST /preview`: source checks, complete candidate membership, exact nested
  session dates and estimated ordinary backtest count; no jobs are launched.
- `POST /`: save immutable `campaign_id`, `name`, `source_backtest_id`, `sources`,
  `folds`, `qualification` and optional `confirmed_backtest_count`. `sources`
  reuses saved report/grid selectors; `sizes` must be `[1]` because this step
  qualifies the saved strategy quantities, not prop-sizing alternatives.
  `sizing_policies` must be omitted/null; inner qualification cannot silently
  consume or select a prop-policy declaration.
- `GET /?source_id=...`, `GET /{id}`: history/status/progress and completed result.
- `POST /{id}/check`, `/run`, `/cancel`: validate identity, enqueue/resume through
  the existing worker, or request safe-checkpoint cancellation. Repeated Run
  returns the existing active/completed analysis. Source/code drift rejects.
- `GET /{id}/exports/{kind}`: `campaign.json`, `report.json`, `analysis.zip`,
  `qualification.csv`, `research_plan.json`, or `calculations.json`.

Reports use format 6, phase `research_integrity`, and analysis mode
`nested_research`. `calculations.folds` saves qualification, inner source
references and evidence. `outer_test_status` and `policy_selection_status` are
`not_run`; overall readiness is `INCOMPLETE`. A completed analysis means inner
qualification finished, not that the requested full research workflow passed.
Inner backtests carry research phase `inner` and explicit roles/windows; they
cannot masquerade as ordinary IS sources or launch manual OOS. Required missing
assessments remain insufficient. Qualification bootstrap settings, candidate
membership and approximate historical uncertainty are saved, with no winner.

## Nested economic extension — 8 November 2026

`economic_studies` defaults to `[]`; at most one Evaluation and one Funded study
may be declared. Each study contains `phase`, `profiles`, `policies` (fixed
`micros`, with optional supported sizing contract), `simulation`, `sampling`,
`costs`, `search_settings`, `selector`, and Evaluation-only `retry`. GET defaults
returns complete phase-specific templates. Opposite-phase fields and native
risk-based policies reject during preview. Inner source `sizing_policies` remain
invalid; economics has its own stage declaration.

Evaluation selectors support `pareto_family`, `min_cost_under_time_cap`, or
`min_time_under_cost_cap`, with optional `maximum_cost_per_funded`,
`maximum_expected_calendar_days`, and `minimum_pass_probability`. These map to
the Evaluation owner's feasibility contract before Pareto ranking. Funded uses
`maximum_expected_received_cash`, optional `minimum_expected_cash`, and its
existing breach/payout/downside constraints. Ties default to
`keep_all_exact_ties`; explicit `configuration_id` preference uses a phase-only
configuration digest, excluding generated source IDs and opposite-phase settings.

Forecast starts and Funded cash horizons derive from each outer window;
conflicting overrides reject. Preview `economic_plan` records maximum candidate
membership, policy-training/outer backtest counts and resolved fold calendars.
Large searches require exact `confirmed_economic_candidate_count`; qualification
may reduce work but cannot silently omit a PASS configuration.

Completed folds add `economic_selection` and `chronological_replay`. Normal child
phase reports retain `training_context`, `provider_rules` and
`deployment_readiness`. Training context is an internal coordinator argument,
never an accepted public phase request field. Public phase selection still
rejects inner and outer sources. Evaluation's public request now also accepts
optional `constraints` (null preserves the original unconstrained behavior).

Additional normal exports: `economic_selection.json`, `chronological_replay.json`
and `research_journal.json`. The ordered journal seals a complete family before
each recorded outer access. No-qualified/insufficient states create no fabricated
outer path. Child report rule evidence uses
`/api/prop-analyses/{id}/files/provider_rules.json`; it is also in the normal ZIP.
Readiness remains `INCOMPLETE`, `production_qualified: false` until later workflow
and qualification requirements are satisfied.

## Nested references and reliability extension — 8 November 2026

Optional `baselines` declares at most sixteen unique references, each with `id`,
`phase`, `source_configuration_id` (from preview's complete signal membership),
`profile`, `policy: {micros, sizing?}`, and strict boolean `required` (default
true). The source and normalized same-phase profile must belong to the declared
study. Duplicate definitions, unavailable native dynamic policies and unsupported
sources reject before execution. References may fail edge qualification and
still be measured, with `recommendation_eligible: false`. They never enter the
optimizer's qualified candidate set.

Server-only `nested-phase-reference-v1` context binds reference declarations,
training sources, observed sessions, code and artifacts. It carries reference
IDs rather than qualified configuration IDs. Typed baseline seals precede every
selected/reference outer access and survive cancellation/resumption. Public
phase endpoints reject reference/inner/outer sources as ordinary IS inputs.

Optional `reliability` accepts the strict `ReliabilitySettings` contract:
`minimum_outer_blocks` (5), `minimum_complete_fold_fraction` (1),
`confidence_level` (.95), `bootstrap_block_folds` (1),
`historical_bootstrap_replicates` (1000), `historical_bootstrap_seed` (137),
`minimum_calibration_blocks` (20), `minimum_baseline_mean_improvement` ("0"),
`require_baseline_for_recommendation` (true), and `abstention_action`
(`unmeasured` or explicit `no_account_no_fee`). GET defaults returns the complete
template. Values are saved before outer execution. Insufficient coverage,
families, censored acquisition means and unresolved reference thresholds remain
explicit; they are not silently converted into zero returns or selected winners.

Funded selectors additionally support `conservative_expected_received_cash`,
which must be paired with `search_settings.conservative_objective`:
`method: historical_block_bootstrap_lower_mean`, `confidence_level`, `replicates`,
`block_sessions`, `minimum_history_sessions`, `minimum_history_blocks`,
`simulations_per_replicate`, `history_seed`, `simulation_seed`, and
`maximum_mc_standard_error`. The ordinary maximum-mean selector must omit this
configuration. The public Funded phase request also accepts this optional
contract. Default null preserves the existing objective. Unsupported history or
insufficient tail resolution returns unresolved candidates and no winner.
Preview and admission share resource bounds across all candidate refits:
50 million path calendar days, one million captured historical indices, and the
existing report-capture bound. No silent candidate or replicate truncation occurs.

Completed format-6 `nested-research-v3` reports include `calculations.reliability`
and each fold's `baseline_results`. Additional normal exports are
`baseline_results.json`, `reliability.json`, `reliability_folds.csv`, and
`baseline_comparison.csv`. Conservative child reports capture
`historical_mean_cash.json` through their existing file/ZIP routes. Reopening
uses immutable saved artifacts. `INSUFFICIENT_EVIDENCE` and
`ASSESSABLE_WITH_LIMITATIONS` describe research evidence only; neither makes
`production_qualified` true or supplies the unfinished final deployment package.

## Native historical phase replay

Use the existing `POST /api/prop-analyses/check` and `POST /api/prop-analyses`
with `mode: "native_phase_replay"`. This is a deterministic source rerun, not a
campaign optimizer. `GET /api/prop-analyses/defaults` supplies supported native
profiles, retry defaults and explicit receipt assumptions under
`native_phase_replay`.

Required fields: `phase`, `source_backtest_id`, `profile`, strict integer
`micros` (quantity or risk-policy cap, 1–40). Optional `max_micros` defaults to 40;
`micros` cannot exceed it. Optional `sizing` uses the common policy contract;
omission means fixed contracts. `costs` defaults to source/MNQ and cannot replace
saved execution costs. Optional `period` has `first_session`/`last_session`
(inclusive CME session dates within saved IS). Evaluation accepts `retry`, but
no receipt fields. Funded accepts no retry inputs and requires
`receipt_delay_calendar_days` and `receipt_amount_convention`
(`kernel_entitlement_unrounded` or `usd_cents_half_up`). Unknown fields reject.
Calendar, source coverage and strategy identity are checked server-side.

Check returns `native.source_check`, the admitted period/session inventory,
effective sizing and captured provenance. Submission returns the ordinary queued
analysis record. The completed report has
`request.mode == "native_phase_replay"`, `native_backtest_id`, `calculations`
(the phase owner's actual historical result) and `production_qualified: false`.
Download normal report JSON/ZIP or the captured file links. The child backtest
also exposes `/api/backtests/{id}/exports/native_account_control` with integrity
validation. Source and child IDs are protected during execution; completed ZIPs
retain their actual trade, equity, risk, decision and control evidence even if a
user later deletes a standalone child. Cache reuse verifies both the sealed
analysis and original child artifacts. Selector parameters remain unsupported.
The optional native forecast extension below adds explicit sampling parameters.


## Optional native forecast

`native_phase_replay` accepts optional `native_forecast` with the following strict
contract (omission preserves the actual historical-only request):

```json
{
  "model": "observed_contiguous_blocks_with_prior_prefix_v1",
  "simulations": 4,
  "seed": 1729,
  "block_sessions": 1,
  "horizon_calendar_days": 9,
  "capture_paths": 2,
  "calendar": {
    "start_dates": ["2026-01-26"],
    "coverage_end": "2026-02-05",
    "closures": [],
    "timezone": "America/Chicago",
    "version": "explicit-demo-weekdays-v1"
  },
  "early_closes": {}
}
```

These are labeled synthetic example dates, not an official exchange calendar.
Defaults expose supported limits, model and assumptions but do not silently
supply verified future dates. `simulations` is total paths, strict integer 2–512;
`seed` is a strict unsigned 32-bit integer; `block_sessions` is 1, 5 or 10;
`horizon_calendar_days` is 1–365; `capture_paths` is 1–20 and cannot exceed paths.
Booleans are not integers. Calendar starts/closures are JSON arrays of canonical
ISO dates; at most 16 distinct starts; total paths must divide evenly between
starts. Version is explicitly required. Early-close values are local `HH:MM`
before 16:00 on covered open weekdays. All target starts follow the admitted IS
source, and every requested target shape must have a source pool.

Check adds the full `native_forecast_plan`: source catalogue and hash, complete
addressed schedules, target contexts, cohort allocation, selected capture indices
and bounded work. Submission uses this same checked plan. The saved report's
`calculations` remains the actual historical result; top-level `native_forecast`
is the distinct modeled result with all-path metrics and uncertainty. Dedicated
forecast files use ordinary `/api/prop-analyses/{id}/files/{name}` and ZIP routes.
Changing any declaration invalidates the earlier check. No selector, current
recommendation or historical-law confidence claim is implied by this option.

## Native execution in independent campaigns and nested studies

Independent phase request bodies now accept optional `native_execution`:

```json
{
  "model": "observed_contiguous_blocks_with_prior_prefix_v1",
  "horizon_calendar_days": 9,
  "capture_paths": 1,
  "early_closes": {}
}
```

Omission preserves the saved-trade execution path. This explicit method uses the
existing phase `simulation` paths/seed, `sampling.block_weekdays` (1, 5 or 10),
profile, sizing and calendar. Native Funded horizon must equal its saved search
horizon. Native Evaluation requires matching chain path counts/seeds and uses
the native sequential retry results for acquisition metrics. No fee/pass-ratio
substitute enters its selection. Total native paths are 2–512, at most 16 equally
allocated start cohorts, horizon 1–365 civil days, capture 1–20 paths and no more
than the path count. All dates and target shapes pass the same native calendar
and source admission as standalone replay.

Campaign declarations place this value in `search_settings.native_execution`.
`check` includes each candidate's complete native source/forecast plan and family
work. Unsupported native sources, profiles, calendars or scaling reject before
queueing. The current implementation admits complete one-minute MNQ VWAP sources
with EOD-flat enabled and strategy-local volatility sizing disabled. Fixed
contracts, dollar risk and percentage risk all execute causal quantity decisions
inside the actual strategy/account path. Every declared source × cap × policy ×
profile combination stays in the population; unsupported members are not dropped.

Nested economic studies use the same `search_settings.native_execution` but
derive each forecast's horizon from that fold's exact outer civil cutoff when
the horizon is omitted. An explicit horizon must agree. Inner qualified
configuration membership is complete, selections are sealed, and outer execution
uses original ordered bars without forecasting. Terminal procedure applications
use explicit application/procedure identities and the same owners; no synthetic
outer fold is inserted.

`POST /api/prop-analyses/{id}/cancel` and
`POST /api/research-campaigns/{id}/cancel` request cooperative cancellation for
new independent phase jobs. Analysis status exposes
`capabilities.cooperative_cancel` and `capabilities.stop_requested`. Unsupported
jobs or completed jobs reject cancellation. Accepted stops cannot publish a
partial population; explicit retry starts the full saved declaration again.
Cancellation is not a request to delete earlier reports or source evidence.

A native frozen campaign's existing manual assessment endpoint reruns the
unchanged family on actual OOS chronology. It requires complete reviewed open
sessions through the saved horizon, may include closed/weekend receipt days, and
never shortens a horizon to fit the supplied data. Assessment results have
`selection_status: assessment_only_no_reselection`, empty ranking/frontier and
no winner. `native_chronological_replay` identifies the actual path; ordinary
controlled child backtests and their immutable captured files appear under
`native_backtests`. Idempotent reuse checks both the saved report and live child
manifest/artifact identity. Earlier fixed-path OOS assessment semantics remain
unchanged and explicitly labeled.


## Complete-procedure and protected-session API


- Existing robust request/defaults: `terminal_selection`, `final_evidence`; plan `session_inventory` is now the fully eligible development inventory, excluding partial source-timezone IS sessions and later source sessions. Raw metadata-only inventory remains available to the reservation checker.
- `POST /api/datasets/{id}/research-reservations/preview` and `POST .../research-reservations`: `{request_id,first_session,last_session,market_domain:"CME:NASDAQ100",external_access:"declared_not_inspected"|"inspected"|"unknown"}`. GET lists reservations; POST `.../{reservation_id}/release` takes `{request_id,reason}`.
- `POST /api/research-campaigns/robust/{id}/procedure/preview`: `{reservation_id:null|id,source_snapshot_id:null|dataset_id}`. Response includes complete terminal window/development/access/economic work review and `preview_sha256`.
- `POST .../procedure/freeze`: same fields plus `{procedure_id,expected_preview_sha256}`. The procedure and reservation binding commit atomically.
- `POST .../final-verification/preview`: `{procedure_sha256,reservation_id,source_snapshot_id}`. POST `.../run` adds `{request_id,expected_preview_sha256}`.
- `POST .../development-selection/run`: `{request_id,procedure_sha256}`. No signal/policy/candidate/window override is accepted.
- GET `.../applications/{application_id}`, POST `.../cancel`, and GET `.../exports/{kind}` reuse existing progress, retry and saved report patterns. Fixed exports include report/archive, procedure, terminal plan, qualification, economic selection, references, final verification, recommendation, access evidence and ordered research journal.

The existing report UI renders the freeze/application progression, complete qualification and phase forecast families, actual held-out observations, readiness reasons and normal report/download links. It contains no analytical fixture oracle or demo-only page.


For source lineage, local access scope, terminal selection and recommendation semantics, see the [workflow](research_workflow.md#complete-procedure-freeze-and-terminal-applications-m3b2). Historical reports stay readable; code/source changes prevent incompatible new calculations.

## Research workspace API

`GET /api/research-workspace` projects existing phase campaigns, nested campaigns
and editable drafts. Parameters: `q` (maximum 200 characters), `kind`
(`phase|nested|draft`), `phase` (`evaluation|funded`), `status`, `sort`
(`newest|oldest|name`), `offset` and `limit` (1–100). Empty filters are permitted.
The response has `items,total,offset,limit,sort`. Each item includes the source,
phase/backend, original campaign status, latest attempt status/stage, separate
`final_application` and `current_application`, bounded saved-readiness projection
and `next_action`. Status filtering follows the latest application rather than
hiding its failure behind the original campaign's success. These reads launch
neither source-price preparation nor numerical workers.

The same prefix provides `GET/POST /drafts` and `/templates`, and
`GET/PUT/DELETE /drafts/{id}` or `/templates/{id}`. Lists accept `q,offset,limit`.
Create returns 201 with a server UUID and revision 1. Update requires the exact
saved revision; stale writes return 409 without applying edits. Delete requires
`?revision=N` and removes only that editable document. No report or dataset is
removed. Draft and template records share the existing AnalysisStore SQLite
catalogue and have a checksummed, versioned payload, not a new result store.

```json
{
  "schema_version": "research-workspace-v1",
  "kind": "nested",
  "name": "My research draft",
  "declaration": {
    "source_backtest_id": "<saved IS report UUID>",
    "sources": [{"backtest_id": "<saved IS report UUID>", "sizes": [1]}]
  }
}
```

Drafts normalize the ordinary robust declaration and strip ephemeral campaign
IDs and work confirmations. GET additionally returns source summaries, the
anchor and missing/unusable sources. It checks full selected grid membership;
missing non-anchor trials cannot silently reduce the candidate family. Drafts do
not pin unused source records. Frozen campaigns retain their existing protection.

Templates use `settings` instead of `declaration`. The closed allowlist is
`folds,qualification,execution_scenarios,regimes,economic_studies,reliability,terminal_selection,final_evidence`.
Existing phase contracts validate settings without inventing dates or running a
preview. Source-bound baselines, embedded identities/outcomes/access claims and
unknown nested phase settings reject. Payloads are limited to 512 KiB. An
unsupported saved schema remains readable with `editable:false` and an explicit
warning; PUT rejects rather than converting it. Every document declares
`requires_fresh_preview:true`. Saving configuration grants no research-access,
selection or execution authority.

## Predefined frozen lifecycle comparison

The existing `POST /api/prop-analyses/check` and `POST /api/prop-analyses` accept a
strict `mode: "predefined_lifecycle_comparison"` request. This is a downstream
historical comparison of explicitly chosen independent freezes, with no selector.
It accepts only already completed ordinary manual OOS reports belonging to each
exact frozen IS parent. Check never launches another OOS attempt.

```json
{
  "mode": "predefined_lifecycle_comparison",
  "request_id": "<new UUID hex>",
  "window": {"first_session": "2026-01-26", "cutoff_date_exclusive": "2026-02-09"},
  "pairs": [{
    "id": "My explicit Evaluation and Funded pair",
    "evaluation": {"campaign_id": "<UUID>", "package_sha256": "<SHA256>",
      "candidate_id": "<SHA256>", "source_backtest_id": "<ordinary OOS UUID>"},
    "funded": {"campaign_id": "<UUID>", "package_sha256": "<SHA256>",
      "candidate_id": "<SHA256>", "source_backtest_id": "<ordinary OOS UUID>"}
  }],
  "continuation": "first_ready_session_until_common_cutoff",
  "replacement": "none"
}
```

The common window spans 1–365 civil days and cannot exceed either frozen native
forecast horizon. Both policies require the same supported provider/program,
rule version, underlying dataset and timestamp interpretation. Different signal
parameters and sizing policies are permitted. Current native source requirements
still apply: admitted complete one-minute MNQ/VWAP data, exact parent mapping,
compatible costs, reviewed calendar and complete observed open-session coverage.
Imported trades, mixed execution backends, protected final tokens, unselected
members, changed packages and unsupported budgets reject. The maximum declaration
is 20 named pairs; the complete family must also fit the 50-million-bar work and
100-MiB estimated capture bounds. Unsupported members are never dropped.

Check returns `pair_comparison` with each immutable policy/source/package and
server-derived application binding. Evaluation actually purchases/retries/passes
according to its frozen policy. A fresh Funded account starts only at the actual
funded-ready event before the common exclusive cutoff; there is no replacement.
A separate continuation binding identifies this remaining-horizon chronological
observation. The independent Funded forecast and its original horizon stay
unchanged. Acquisition incomplete by the cutoff leaves Funded unstarted and all
paid fees visible. Payout receipt exactly at the cutoff stays pending.

The saved format-8 report contains all declared pairs in order,
`selection_status: comparison_only_no_selection`, `winner:null`, exact receipts,
pending entitlements, paid Evaluation/activation fees and net trader cash. Source
profit, provider equity and account deductions are not trader receipts or extra
expenses. Each phase uses the existing native engine/controller and its ordinary
controlled backtest; the standard report captures child manifests and files.
`request.json`, `source_check.json`, `results.json`, `cash_ledger.json/csv` and
`pairs/{number}/` package/binding/result/cash downloads use the usual file/ZIP
routes. Both original freezes remain unchanged.

The request ID binds the exact declaration and checked identity. Exact queued or
complete repeats reuse the same analysis; changed declarations, code/source
identity or live child manifests/artifacts reject reuse. Failed/cancelled work
may retry its exact binding. Cooperative cancellation uses the ordinary analysis
cancel endpoint and cannot publish a partial pair population. Completed comparison
sources/children stay pinned until the analysis is explicitly deleted. A deleted
comparison retains a request-ID tombstone; it cannot be silently recreated by the
same request. Previously accessed OOS is never described as an untouched holdout.

## Timestamped forward observations — 8 November 2026

Forward monitoring uses the existing application and AnalysisStore. It accepts
supplied records and produces immutable assessments; it does not place orders,
connect to a broker or certify the platform's strategy implementation. The
complete contract is in `forward_contracts.py`; orchestration and authoritative
policy membership are in `forward_monitoring.py` and `forward_policy.py`.

| Route under `/api/forward-monitors` | Meaning |
| --- | --- |
| `GET /defaults` | Strict schemas, threshold defaults, provenance kinds and input limits. |
| `POST /check`, `POST /` | Check and save an immutable monitor declaration. Creation returns 201; an exact declaration retry returns 200. |
| `GET /?limit=50&offset=0&q=&application_id=` | Compact metadata projection, `{items,total,limit,offset,projection_only:true}`; at most 100 items per page. No report parsing or recalculation. |
| `GET /{id}` | Captured policy/check, advisory state at its saved clock, pending observations, control history and recovery authority. |
| `POST /{id}/events/check?filename=...`, `POST /{id}/events?filename=...` | Validate and import exact UTF-8 JSON bytes. Check does not import events, but supplied market/financial exposure is already recorded in research access history. |
| `GET /{id}/events?offset=0&limit=100` | Bounded immutable event/correction history with original accepted receive clocks. |
| `POST /{id}/assess` | Queue a normal assessment of the captured event/control head at an explicit UTC clock. |
| `POST /{id}/control` | Append advisory pause, acknowledged recovery or retirement. |
| `GET /{id}/snapshots`, `GET /{id}/batches` | Normal analysis records and original batch metadata. |
| `GET /{id}/batches/{batch_id}/download` | Exact original input bytes, checked against their saved SHA-256. |
| `GET /{id}/exports/events.jsonl`, `declaration.json` | Complete retained event history and monitor declaration/provenance. |

A declaration has the following shape. All money/prices are finite plain decimal
strings; quantities and sequence numbers are strict integers. Unknown fields and
nonfinite/exponent money reject. `order_placement_enabled` must be strict false.

```json
{
  "schema_version": "aq-forward-monitor-v1",
  "monitor_id": "<UUID hex>",
  "name": "My supplied observation monitor",
  "observation_kind": "synthetic_harness",
  "policy_binding": {
    "campaign_id": "<robust campaign UUID>",
    "application_id": "<current-development application UUID>",
    "phase": "funded",
    "package_sha256": "<exact selected current package SHA256>",
    "family_preference_reason": null
  },
  "source": {
    "source_id": "my-events",
    "label": "Declared supplied source; no verified connection",
    "adapter": "timestamped_events_v1",
    "connection_claim": "supplied_records_only",
    "position_cost_basis": "unknown"
  },
  "instrument": {"symbol":"MNQ","tick_size":"0.25","point_value":"2","currency":"USD"},
  "initial_balance": "50000",
  "thresholds": {"maximum_position_contracts":3},
  "control_mode": "advisory_only",
  "order_placement_enabled": false
}
```

`policy_binding` may be omitted only for an explicitly unbound
`synthetic_harness` diagnostic. `paper` and `actual_import` require an eligible
latest current-development application. A retained family requires a recorded
preference reason. The server verifies authoritative application/report seals,
complete PASS membership, exact phase/package/candidate/configuration/strategy,
training report and source artifacts. A no-qualified recommendation, old fold,
final-only fit, reference policy or changed identity cannot become a bound policy.
Current observation contracts are whole MNQ with 0.25 tick, $2/point and a fresh
$50,000 baseline; original NQ/MNQ training provenance stays separate. A successful
check grants observation admission, never trading authorization.

An event envelope is `{"schema_version":"aq-forward-events-v1","batch_id":
"<UUID hex>","source_id":"my-events","events":[...]}`. Events have immutable
`event_id`, explicit `event_time_utc`, optional positive `source_sequence`, a
`kind` discriminator and its strict payload. Supported kinds are `signal`,
`intent`, `order`, `order_status`, `fill`, `protection_intent`, `protection`,
`position`, `market`, `heartbeat`, `connection`, `cash` and `void`. Orders/fills
also declare `execution_kind: synthetic|paper|actual`. Server accepted-receive
clocks are not caller fields. Ambiguous equal-time market/economic/connectivity
order remains unresolved; sorting cannot manufacture causality.

A fill's commission is the total supplied fee for that fill, charged once.
Slippage is diagnostic against the supplied known intent/trigger price and is
not another deduction. FIFO lots and flat-to-flat trade episodes are the declared
bookkeeping convention. Unknown supplied cost basis remains unknown through
partial exits. Whole-account profit requires an observed initial flat position
and matching initial account balance. Protective fills accumulate against their
original order; cancelled/stale protection cannot cover a new position.

Cash categories distinguish `payout_request`, `provider_deduction`,
`trader_receipt`, `evaluation_purchase_fee` and `activation_fee`. Requests declare
`request_amount_basis: unknown|trader_entitlement|gross_withdrawal` and may supply
`expected_trader_amount`. Unknown entitlement leaves pending receipts unknown;
an entitlement above a declared gross request is retained as a discrepancy.
`net_trader_cash` is actual receipts minus paid Evaluation and activation fees.
Provider deductions, account equity and trade P&L do not become extra trader-cash
income or expenses.

Limits are 4 MiB/5,000 events per batch and 100,000 events, 1,000 batches or 32 MiB
of original inputs per monitor. The same batch ID with changed bytes, or event
ID with changed content, rejects 409. Exact retries add no fills and retain the
first accepted receive clock. Corrections require a new event ID, an active
`supersedes_event_id` and a reason; forks reject. Original bytes and all event
versions remain inspectable, and corrections never mutate earlier reports.

Check/import records supplied price/financial observations even when they overlap
protected final sessions: these separate inputs have already been exposed.
Reservations remain intact, but subsequent final eligibility reflects the
recorded access. No protected dataset read is granted. Synthetic inputs also
conservatively affect their market domain because their claimed independence
cannot be verified. Pure heartbeat/connectivity records do not invent price
access.

Assessment accepts `{"request_id":"<UUID hex>","as_of_utc":"<UTC ISO>"}`.
It freezes input/control heads and code identity before the normal worker runs.
The format-9 `forward-monitor-v1` report stores the declaration, captured policy,
original batches, normalized history, reconciliation and explicit clock/scope
facts. Standard prop-analysis `report.json`, `analysis.zip` and `/files/{name}`
routes provide downloads. Reopen verifies saved bytes without reconciliation or
policy reselection; new calculations reject changed source/event/declaration
identity. Monitor policy sources and reports remain deletion-pinned.

Controls accept `request_id`, `action: pause|resume|retire`, `reason`, and for
resume the exact `acknowledged_snapshot_sha256` returned by GET detail as
`last_completed_snapshot_sha256`. Recovery requires the latest assessed event
head, resolved intrinsic/current blockers and a recent server-clock assessment.
Old resolved incidents may be acknowledged through their captured sequence;
current drawdown, missing health or unreconciled position/causal evidence cannot
be waived. Retirement is terminal. These controls cannot stop external orders.

`calculations.forward_evidence` distinguishes synthetic, retrospective and
supplied post-monitor observations. Analysis reservation time, selection seal
and unknown actual publication time are labeled separately; monitor creation
after completed-report verification provides a conservative publication bound.
`forecast_comparison` presents captured forecast/horizon/calendar and actual
receipt/duration diagnostics with `NOT_COMPARABLE` reasons. Matched calibration,
connected strategy equivalence and account-state sizing verification are not
implemented. ACTIVE is an advisory assessment at its saved clock, not continuously
verified live health. Saved evidence and exact reproduction are in the dated
[forward monitoring review](prop_simulation_review.md#timestamped-forward-observations--2026-11-08).
