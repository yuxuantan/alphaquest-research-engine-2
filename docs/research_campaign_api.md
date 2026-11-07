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
