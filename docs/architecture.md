# Architecture

[Home](../README.md) / [Docs](README.md)

[Requirements](#requirements-and-scope) · [Workflow](#end-to-end-workflow) ·
[Code](#code-architecture) · [Decisions](#decisions)

Code reviewed 31 October 2026: [6d290c5](https://github.com/yuxuantan/alphaquest-research-engine-2/tree/6d290c5e429c745a4af600e4da7218c680f9a77a).

Phase-optimization architecture review, 5 November 2026:
`71f97a61e568b39b6bf17647078dcdb2364069cb`. The status below supplements the
earlier review; it does not claim a new numerical or provider qualification.

## Requirements and scope

AlphaQuest is a local, single-user futures research app. It must:

- Validate CSV data and preserve its bytes, timezone and identity.
- Run strategies and parameter searches through the same execution engine, with explicit fills, costs and instrument settings.
- Separate in-sample (IS) research from manually launched out-of-sample (OOS) tests; save each run's settings.
- Calculate supported Apex/LucidFlex prop outcomes locally; check source trades/costs and disclose missing or bar-based risk data.
- Save reports and downloads so reopening never reruns or changes them. External generated results are comparison references only.

The business goal is to maximize expected cash received minus added costs within
a set period and loss/spending limits. Current default sizing uses annual slot
economics. The implemented budgeted method replays dated cash for one initially
unfunded slot on observed history; it is not a sampled forecast or optimizer.
The planned research layer independently minimizes evaluation acquisition
cost/calendar time using a Pareto frontier and maximizes funded-stage horizon
cash conditional on already being funded. A portfolio optimizer is optional
downstream work. The proof of concept lasts six months; set the trading
period separately. Order-book depth (L2), a tested MultiCharts .NET live route,
standalone external-backtest imports and multi-strategy allocation remain proposed.
The long-term depth goal covers historical research and live execution; define
fields, depth, event timing, coverage and replay needs per strategy. Full
MultiCharts feature parity and commercialization are outside the initial scope.
Judge the POC by mechanics, repeatability, prop accuracy, execution reliability,
research throughput, spending and engineering hours.

### Implemented versus planned

| Capability | Status at this review |
| --- | --- |
| Saved IS backtests, single-strategy parameter grids, manual OOS and local prop reports | Implemented. Each trial uses the existing engine; OOS remains manual and unlimited with recorded history. |
| Annualized joint evaluation/funded sizing | Implemented and still the default. Classified as **legacy business-level optimization**, not the target independent phase selector. Preserve calculations, regression tests and historical reports until separately approved retirement. |
| Separate evaluation/funded sources and fixed targets | Implemented in dated lifecycle and budgeted replay. This is separate phase configuration, not independent optimization. Standalone dated mode remains API/report compatible but is no longer a new portal choice. |
| Exact cash ledger and hard monthly acquisition cap | Portfolio milestones 1–2 complete per the existing progress/evidence logs. One observed path and one initially unfunded slot; modeled settlement assumptions remain explicit. |
| Independent simulation profile components | Implemented as Python APIs in `evaluation_profiles.py` and `funded_profiles.py`, with frozen contracts in `phase_profiles.py`. Single saved source per phase; existing kernels/cost/risk checks. Weekday and modeled payout-time semantics; no new portal mode or independent selector. |
| Independent Evaluation and Funded optimizers | Planned in [phase optimization](phase_optimization_plan.md). Evaluation cannot use funded payouts; Funded cannot use evaluation pass rates, acquisition fees/time or joint annualization. |
| Cross-job/strategy campaigns, phase package freeze and assessment-only OOS | Planned. Existing saved IS/OOS declarations and manual OOS primitives do not yet enforce this campaign contract. |
| Synchronized portfolio allocation/shared-account optimization | Optional, outside the initial phase implementation; later consumer of phase outputs and dependence data. See [portfolio plan](prop_portfolio_plan.md). |

## End-to-end workflow

Start with the [setup instructions](../README.md#run), then use the existing portal:

1. **Datasets:** validate/save a CSV with its source timezone, tick size and point value.
2. **Strategies → New backtest:** choose strategy, costs and IS/OOS split. Equal parameter bounds run one combination; wider ranges run a grid through the same engine. Initial runs use IS only.
3. **Open the saved report:** inspect trades, metrics and the holding comparison. New runs attempt default Apex/LucidFlex prop analyses; incompatible sources show a reason.
4. **Configure prop analysis → Check source → Run analysis:** inspect native risk data or a matching optional MultiCharts export. Choose existing annualized sizing, or budgeted cash replay with separate fixed phase sources/sizes, observed dates, monthly cap and explicit timing assumptions. Save/reopen the normal report and downloads. Annualized internal training/holdout stays within the chosen research period; budgeted replay uses the declared common observed window.
5. **Run OOS with these parameters:** manually launch from a completed IS report using its saved window/settings. Splits remain editable and attempts unlimited; record prior data access before treating OOS as untouched final evidence.

Before a final research decision, set limits and freeze the selected package
([research checks](research_workflow.md#campaign-checks)). A later live pilot also
needs real permissions, routing, protection and recovery tests; this workflow
does not place live orders. See [product steps](strategies_navigation.md) and
[prop model details](prop_simulation.md).

The proposed phase workflow extends step 4 with a phase-specific candidate set,
source checks and durable frontier/payout report. Freeze its selected package
before manual OOS assessment, which applies the frozen choices without a new
search. These controls are not available yet; the
[implementation milestones](phase_optimization_plan.md#incremental-implementation-milestones)
define the usable increments and evidence required.

## Code architecture

One local server serves the UI and APIs. Arrows show calls/data flow, not separate
services. Jobs use local threads/processes; reports and catalogues share one data root.

```mermaid
flowchart TB
    UI["Browser UI"] <--> API["FastAPI routes"]
    API --> BT["Backtest jobs: reader, strategies, fills"]
    API --> DATA["Dataset store - SQLite"]
    DATA --> BT
    BT --> SAVED["Saved reports and SQLite catalogues"]
    SAVED -- "native trades" --> PROP["Source checks and prop models"]
    XLSX["Optional measured XLSX"] --> PROP
    API --> PROP
    PROP -- "analysis results" --> SAVED
    API -- "opens saved results" --> SAVED
```

| Component | Code | Why separate |
| --- | --- | --- |
| UI and HTTP | [Portal](../alphaquest/web/index.html), [UI code](../alphaquest/web/app.js), [app](../alphaquest/app.py), [backtest API](../alphaquest/backtest_api.py), [prop API](../alphaquest/prop_api.py) | Forms/routes collect settings and coordinate work; calculations stay reusable. |
| Data | [datasets](../alphaquest/datasets.py), [reader](../alphaquest/backtest_data.py) | Validate and snapshot saved bytes; stream bars without changing source data. |
| Strategies and fills | [registry](../alphaquest/strategies/registry.py), [interface](../alphaquest/strategy.py), [execution](../alphaquest/execution.py) | Strategies request orders; the shared engine applies fills/costs. New strategies reuse execution rules. |
| Research and jobs | [splits/OOS](../alphaquest/research.py), [grids](../alphaquest/optimization.py), [workers](../alphaquest/optimization_worker.py) | Trials share the backtest path; workers calculate, the coordinator publishes. |
| Prop calculations | [source checks](../alphaquest/prop/source.py), [analysis](../alphaquest/prop/native_analysis.py), [Apex](../alphaquest/prop/native_engine.py), [Lucid](../alphaquest/prop/lucid_engine.py), [costs](../alphaquest/prop/commissions.py) | Adapt/check trades before account simulation. Firm rules and sizing remain separate from strategy backtests. |
| Independent phase profiles | [contracts/source admission](../alphaquest/prop/phase_profiles.py), [evaluation profiles](../alphaquest/prop/evaluation_profiles.py), [funded profiles](../alphaquest/prop/funded_profiles.py) | Expose single-source evaluation/acquisition and conditional-funded simulations independently. Evaluation has no funded input; Funded has no evaluation fees/pass-rate input or replacement. Reuse existing provider backends; no service, database or result store. |
| Legacy business sizing | [joint sizing](../alphaquest/prop/joint_sizing.py), [account refresh links](../alphaquest/optimization_prop.py) | Joint annualized cost/payout selection and immutable refresh history remain supported; new independent optimizers must not use their score as a phase objective. |
| Dated phase and cash replay | [phase lifecycle](../alphaquest/prop/phase_lifecycle.py), [cash ledger](../alphaquest/prop/cash_ledger.py) | Share local account transitions; distinguish paid acquisition fees, requests, deductions and modeled receipts under a hard monthly cap. |
| Default prop reports | [automatic](../alphaquest/prop/automatic.py), [backend](../alphaquest/prop/native_backend.py), [build](../setup.py) | Automatic/manual runs share local models. Optional compiled kernels use the same model source. |
| Reports and storage | [reporting](../alphaquest/reporting.py), [benchmark](../alphaquest/market_benchmark.py), [backtest store](../alphaquest/backtest_runs.py), [analysis store](../alphaquest/prop/store.py) | Stage calculations, publish completed results, reopen without replay. SQLite indexes files and job state. |
| Reuse | [replay cache](../alphaquest/replay_cache.py), [features](../alphaquest/strategy_features.py), [calculation cache](../alphaquest/prop/calculation_cache.py) | Reuse matching data/calculations by identity; never share mutable strategy positions between trials. |

A local server, SQLite and files keep setup small. Separate services or a database
server would add operations; reconsider for remote/multi-user use. See
[storage and import contracts](architecture_reference.md) for formats and limits,
[execution assumptions](backtest_contract.md) for strategy-specific behavior, and
[tests/review records](prop_simulation_review.md) for dated evidence. Code links
show implementation, not a new test pass or proof of MultiCharts trade parity.

The profile components are callable from Python and retain the current kernels'
weekday sampling and payout-time modeled receipt convention. They are not the
planned dated optimizers. `native_analysis.training_economics` and
`_funded_profile` are compatibility wrappers over the extracted acquisition and
lifetime routines. Joint selection, historical report shapes and calculations
remain supported; complete deterministic Apex/Lucid payloads match the captured
pre-refactor baseline. See [component contracts and limits](phase_optimization_plan.md#implemented-precursor-independent-simulation-profiles)
and [review evidence](prop_simulation_review.md#independent-phase-component-extraction--2026-11-05).

Planned modules are `prop/phase_optimization.py` (contracts/selection),
`prop/evaluation_optimization.py`, `prop/funded_optimization.py`,
`prop/phase_sampling.py` (dated schedules/uncertainty), and
`research_campaigns.py` (cross-job candidates/freeze). Extend existing routes,
workers, backtest catalogue and AnalysisStore. No new service, database or
backtesting engine is proposed. See the
[responsibility and contract map](phase_optimization_plan.md#target-architecture-and-module-responsibilities).

## Decisions

These choices are **proposed**; adoption dates are unset.
Test platforms and feeds on the actual setup.

| Area | Choice and reason | Alternatives / why deferred | Reconsider when |
| --- | --- | --- | --- |
| ADR-00 · Design | Established execution software plus Python research; focus custom work on prop economics. | Fully custom: more maintenance and delayed research. Platform-only: lacks the required analysis. | First campaign shows excessive cost, effort or interface problems. |
| ADR-01 · Research | ChatGPT Work for discovery, comparison and hypotheses; verify original sources to save reading time safely. | Manual review is slower. AI can misattribute or wrongly transfer findings between markets; papers do not validate our implementation. | Errors recur, sources are inaccessible or checking costs more time than saved. |
| ADR-02 · Coding | Codex with a written specification; extend Python, add C# for the execution target when justified. | Manual coding takes longer. Two implementations add maintenance and can share the same specification error; compare each with independent cases. | Execution target changes or maintaining parity stops being worthwhile. |
| ADR-03 · Visual checks | Reuse paid MultiCharts .NET charts/imports/trade markers; familiar tools and no extra visual licence while covered. | TradingView for bars, Sierra depth replay/ACSIL or Python traces; switching adds validation work. Charts/DOM alone do not prove historical depth replay or queue-aware fills. | Required features cannot be checked, or another reference meets needs more easily. |
| ADR-04 · Tracking | AlphaQuest for runs, Git for code, run folders for large logs/evidence; optional Sheets links research, campaigns, variants and run IDs. | Manual status updates can drift; a custom tracker adds code and duplicate state. Status without evidence cannot approve deployment. | Review after 10 strategies, or sooner if manual updates cause repeated errors. |
| ADR-05 · History | Start with verified/licensed Sierra history and TIP bridge features; low spending limits which strategies are possible. Specify fields/period first. | Compare bought/recorded data on equal coverage/rights. Trades alone are not synchronized quotes/depth. Rithmic bulk history remains conditional on contract/range limits; live access is not a history purchase. | A strategy needs missing fields, depth or history; no need to exhaust L1 first. |
| ADR-06 · Prop models | AlphaQuest owns simulation, sizing, economics and saved reports; no extra engine licence, but testing/maintenance still cost effort. | Platform reports/notebooks lack the full workflow. External engines remain references only. Closed trades alone may not support intraday equity rules. | Reference cases differ or build spending stops improving decisions. |
| ADR-07 · Live data | Reuse prop-provided Rithmic through MultiCharts for entitled L1/L2; avoid a second feed subscription where the needed data is included. | Databento is the planned paid option for MBO/L3 or independent history/API needs. Platform access is not custom API permission; L2 inclusion depends on the plan. | Missing fields, outages, changed fees/permissions or inadequate quality; verify depth and session limits. |
| ADR-08 · Execution/hosting | Propose MultiCharts .NET; choose Parallels/VPS by uptime, supervision and recovery needs. Count shared platform costs once. | Sierra, NinjaTrader, MotiveWave or Python adapters add integration work; VPS adds cost. Enough CPU/RAM does not prove reliability. PickMyTrade is optional, not automatically another charge. | Routing/recovery fails, licences/connections are unsuitable or another option costs less overall. |
| ADR-09 · Reconciliation | Compare expected signals/orders, submissions, acknowledgements, fills and positions with broker records; quick setup, recurring manual review. | Automated imports/APIs/aggregation need integration/testing. Broker records establish actual fills/exposure; missing protection or unexplained positions differ from ordinary fill variation. | Review exceeds 30 minutes/day or detection is too slow. |
| ADR-10 · Repeatability | Save code, inputs, settings, rules, costs, data conventions and seeds; keep credentials outside versioned evidence. | Ad hoc files lose traceability; a versioning service adds setup. Check deterministic and random outputs using declared tolerances. | Data types, machines or volume outgrow simple manifests. |
| ADR-11 · Risk controls | Define where protective orders live, who controls them, account limits, stale-data actions, emergency intervention and restart. | Untested defaults lack proof; custom order management adds maintenance. Test the actual route and do not resume into unexplained broker state. | Incident, protective-order/routing/account change or platform limits require different controls. |
| ADR-12 · Selection | Set search limits; select on development prop economics, then freeze choices before final OOS. | P&L/win rate/profit factor omit account economics; Monte Carlo cannot replace OOS. | Holdout has been reused, rules/strategy change or evidence is too imprecise. |

Keep IDs and earlier reasons when changing decisions.

The data choice is about **incremental cost and exposed fields**, not a universal
“free L2 / paid L3” split. Lucid offers market depth, but its public pages do not
confirm free L2 for every Rithmic account. Databento is our planned MBO/L3 option;
Rithmic also advertises MBO, so Databento is not the only possible supplier.
See [checked access sources and assumptions](planning.md#market-data-access).

Cost reasons remain above; [dated planning figures](planning.md) are optional.
The [future export format](designs/trade_export_v1.md) is a proposal, not a supported input.
