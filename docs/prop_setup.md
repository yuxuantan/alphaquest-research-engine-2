# Guided prop and strategy-research configuration

Open a saved backtest report and choose **Configure prop analysis**. The page
starts with a goal, not the legacy annualized form. Changing steps or opening
configuration never starts a calculation. Calculations, validation, selection,
workers and report storage remain owned by the existing workflows.

## Choose a goal

| Goal | Use it for | Existing owner |
|---|---|---|
| Find a robust strategy, size and account | Research across historical windows, with optional independent economic studies | Nested research |
| Compare qualified candidates | Compare saved IS candidates under one Evaluation or Funded objective | Independent phase campaign |
| Inspect one strategy/account policy | One native account-controlled historical strategy replay, optionally with a separate forecast | Native replay |

The first goal is recommended for the complete research process. A standalone
comparison does not establish strategy robustness. One replay does not select an
optimal policy or estimate future performance by itself. Unsupported goals show
the reason and an alternative before you fill a long form.

**Other analysis tools** contains explicit Legacy joint sizing, Budgeted cash
ledger and Frozen phase-pair comparison choices. Their calculations and meaning
are retained. Legacy reports are not relabeled as independent phase results.
Historical configuration-copy links reopen the corresponding explicit tool.

## Follow the relevant steps

The full research path has **Sources → Research design → Accounts and sizing →
Review and run**. Comparison, inspection and other tools skip Research design.
The selected goal collapses into **Change goal**; re-open it to switch tasks.
Inputs stay in their original forms and remain available when you return to an
initialized task on this configuration page. Revisit a step using Back or its
named step button. An unsaved page reload is not a durable draft.

### Sources

The backtest you opened is already selected. Inspect the saved identity and
coverage, then add eligible reports or optimization jobs if required. A phase
comparison derives the common saved IS window and permits explicit narrowing.
The robustness picker retains selected configurations while searching.

The compatibility panel is explicitly preliminary. It uses saved instrument,
strategy and research metadata; it does not certify complete bars, risk coverage,
provider terms or executable fills. Potential native MNQ/VWAP sources still need
the authoritative task check. Imported trades cannot acquire a native strategy
implementation. Unsupported native execution choices are explained and disabled
when known from selected metadata; a previously saved unsupported choice is
retained and blocked rather than substituted.

Task-specific catalogues/defaults load only after that goal is selected. No
unrelated phase search or legacy funded-source picker initializes on the landing
screen. Opening configuration does not inspect a new final holdout.

### Research design

Declare training/validation/test windows, qualification requirements, execution
stresses, relevant causal market conditions, reference policies, reliability and
final-evidence requirements before running. Window buffers/minimum fold counts
are contextual details beside the chronological plan. Existing backend defaults
are retained; the UI does not relax requirements to fit insufficient history.

Use the normal **Save a draft or reuse declared settings** disclosure to preserve
supported research declarations. Existing revision conflicts, missing-source
rebinds, template restrictions and exact schema/membership restoration remain
in force. Unsupported saved declarations remain inspectable and blocked; no
candidate combinations are added to make them fit the controls.

### Accounts and sizing

Evaluation asks what acquisition costs and calendar time are required. Funded
asks what trader cash is received within the declared horizon from one fresh
funded account. Enable either or both in a full research study; they retain
separate objectives, constraints and results. A qualification-only study remains
available, with its limited output disclosed. Continue asks you to enable a phase
or explicitly choose qualification only.

Compare fixed contract quantities, or supported fixed-dollar/percentage-risk
policies. Name the risk base explicitly: configured capital, current balance or
available drawdown cushion. Existing cap, rounding, cushion and planning-cost
contracts remain unchanged. Saved net P&L already includes source costs; planning
costs affect quantity decisions and do not justify deducting source costs again.
Native state-dependent sizing must pass the supported strategy/instrument/session
checks; stop metadata alone cannot prove an invariant future strategy path.

Only the active phase's fields participate in form validation. Hidden Funded
fields cannot block Evaluation and vice versa. Sampling/seeds, quantity guards,
planning assumptions and raw JSON remain contextual disclosures. No execution
method or profile is silently changed to avoid an incompatibility.

### Review and run

The study summary shows the goal, source, IS coverage, applicable phase/profile/
sizing/risk settings and current check status. It stays alongside the form on
wide screens and is expandable on small screens. Review lists every enabled form
setting, including advanced inputs. These are form values; the existing task
check below supplies authoritative resolved membership, costs, dates and work.
Defaults are not recommendations.

Use the normal **Check/Preview** action. Resolve invalid fields and admission
errors; form validation returns you to the relevant step/disclosure. Review the
full candidate population, dates, gaps, work estimate and assumptions returned by
that task. Only a passed check enables its normal Run action. Editing relevant
settings invalidates it. No combination of step navigation runs simulations.

Runs save normal backtests and AnalysisStore reports. A finished calculation is
not automatically a qualified strategy. Keep FAIL, INSUFFICIENT_EVIDENCE, no
qualified candidate, censoring, historical outcomes and forecasts distinct.

## Inspection, previous work and experienced users

**Previous analyses for this backtest** is separate from editable settings and
contains ordinary saved analyses plus loaded task-specific campaign/study history.
Opening saved results preserves their meaning and does not rerun calculations.

**Show all settings for this task** exposes the selected owner's original
sections for experienced users and for following dated reproduction instructions.
Only that task is shown. Added contextual sampling/window/JSON disclosures open;
original qualification/economic sections remain available through their normal
summaries. Switching back to guided view retains the entered settings.

## Boundaries and validation

The change is presentation/orchestration over the existing report → configure →
check → run → durable result routes. It adds no engine, report store or database.
Both phase numerical identities and legacy readers must remain unchanged.

The current end-to-end product exercises, immutable outputs, independent expected
values, compatibility/rejection checks and exact startup/shutdown reproduction are
recorded in [the review log](prop_simulation_review.md#guided-prop-configuration--2026-11-09)
and `artifacts/prop-setup-ux-20261108/README.md`.
