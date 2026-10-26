# Check prop simulation subtasks 1–3

The **Prop review** screen executes the existing configuration and saved-input
adapter against small synthetic saved backtests. Every review saves an ID,
expected-versus-actual checks, and downloadable artifacts. It does not run the
future prop-account engine or claim a pass rate or payout forecast.

## Open the demonstration

From the repository, using the existing environment:

```bash
.venv/bin/python -m uvicorn alphaquest.app:app --host 127.0.0.1 --port 8000 --reload
```

Open **http://127.0.0.1:8000/#prop-review** or click **Prop review** in the app.
Choose **Rithmic**, **2 contracts**, then click **Generate review**. Expect
**44/44 checks passed**. All checks actually run; any mismatch produces a failed
review with expected and actual output retained for inspection.

Existing installations without an environment can follow the installation
instructions in [README.md](../README.md#run). This review requires a source
checkout containing `docs/prop_simulation.md`.

## 1. Implementation specification

**Deliverable:** [prop_simulation.md](prop_simulation.md), its saved copy and
SHA-256, the pinned notebook review identity, and eight visible design checks.

On the screen:

1. Expand **Read the saved specification**. Confirm the pipeline is completed
   backtest → session adapter → deterministic prop-account engine → Monte Carlo /
   sizing analysis → saved results → portal.
2. Check that all six notebook correction checks pass: holdout leakage, missing
   staged-sizing DLL, excursion normalization, differing engine behavior,
   calendar approximations, and perfect-threshold liquidation.
3. Review the feature disposition, phase/observation/calendar/accounting
   semantics, module boundaries, and numerical acceptance examples in the full
   specification. Automated presence checks support this human design review;
   they do not establish that the future engine implements the specification.
4. Download `specification.md`. It is the exact document used for that review,
   even if the repository document changes later. Its SHA-256 is displayed.

The notebook hash is the identity verified on **2026-10-25**, not a new Drive
download by this demo. The pinned value is
`f79b6c6cc54e7bd64d619bb684ec4c6537c7bcf1d1e1d3f6d5bd6e74c908f89b`.

## 2. Rules and simulation configuration

**Deliverable:** resolved `profile.json` and `simulation.json`, phase settings,
source/evidence/assumption details, and 21 visible configuration checks.

On the screen:

1. Confirm evaluation target **3,000**, trailing drawdown **2,000**, daily loss
   limit **1,000**, access **30 calendar days**, and maximum **6 contracts**.
   Funded settings appear separately, with lock profit **100** and payout rules.
2. Inspect the funded tier probes. Profit **1,499.99 → 1,500** changes the
   contract limit **2 → 3**; **2,999.99 → 3,000** changes **3 → 4** and daily
   loss limit **1,000 → 2,000**; **5,999 → 6,000** changes the daily loss limit
   **2,000 → 3,000**. The source conflict and explicit modeled resolution remain
   visible. This is a lookup demonstration, not a simulated account transition.
3. Switch to **Tradovate** and generate another review. Evaluation shows **No
   lock**; the funded lock remains **100**. Rithmic and WealthCharts evaluation
   lock profit is **3,000**. Full settings include qualifying days, strict
   consistency, withdrawal thresholds, payout ladder, and inactivity.
4. Inspect the rejection checks for fractional quantities, overlapping tier
   boundaries, funded settings with evaluation fees, and a tampered snapshot.
   A rejection check passes only when the actual validator rejects its input
   with the expected reason.
5. Review source URLs/retrieval dates, evidence status, assumptions, and unknown
   effective dates. Fixture fees are explicitly supplied as zero; these are not
   provider prices. These sources retain their recorded retrieval date, not a
   claim of verification today.
6. Download `profile.json` twice for the same platform. The profile hash stays
   identical. Changing only comparison quantity also preserves the profile
   hash. The complete simulation settings hash changes with source identity or
   configuration; each demonstration creates new synthetic source IDs.

The snapshot probe changes a separate template's version and daily limit, then
reloads the saved original snapshot and verifies its original hash. A separate
tampering probe edits saved content without updating the hash and is rejected.

## 3. Saved-backtest adapter

**Deliverable:** `source.json`, `calendar.json`, `sessions.csv`,
`observations.csv`, the original source artifacts in `bundle.zip`, and 15
visible adapter checks.

On the screen:

1. At **2 contracts**, expect gross **30**, commissions **4**, informational
   slippage **10**, and net **26 USD**. Source absolute final equity is **10,026**.
   Net already includes commissions and adverse fill slippage. Neither is
   deducted again.
2. Confirm January **5, 6, 7** each has **3 covered bars**. Trade counts are
   **0, 1, 0** and net P&L is **0, 26, 0**. Covered zero-trade sessions remain;
   they are not missing data. These are deliberately complete three-minute
   synthetic windows, not a declared full exchange session.
3. The trade-close stream has **one** completed-trade observation, **26**.
   Bar-close marks during that trade are **−7, 3, 26**. Other covered bars are
   flat zero marks. These are cumulative changes relative to that trade's
   pre-entry equity; **do not sum them**.
4. Select **1 contract** and generate again. Expect gross **15**, commissions
   **2**, informational slippage **5**, net **13**, and trade-relative marks
   **−3.5, 1.5, 13**. The original source quantity remains **2** and original
   source equity remains **10,026**. The saved source fills are unchanged.
5. In the DST example, Sunday **March 8, 20:00 New York** appears under the
   **March 9** session. March 7/8 are explicitly closed calendar labels. The
   March 6 session opens at **23:00 UTC** and March 9 opens at **22:00 UTC**.
6. Inspect actual rejections for missing coverage, variable source quantities,
   exposure spanning prop sessions, and an incompatible currency declaration.
   No measured MAE/MFE or intrabar path is fabricated.
7. Expand preserved source identity/parameters/execution/artifact hashes.
   Download `bundle.zip`: `sources/arithmetic/` contains the synthetic CSV,
   strategy source, and a completed `backtest_runs/<id>/` with `report.json`,
   `trades.csv`, and `equity.csv`. Source hashes identify those actual bytes.
   `equity.csv` contains initial equity and trade closes; `report.json` contains
   all bar-close equity samples.

## Saved outputs and repeatability

Download `review.json` or `checks.csv` for all actual/expected checks. Download
`bundle.zip` for the complete evidence, including the intentionally unsupported
variable/overnight cases and DST fixture.

Reload the page, or restart the server with the same data directory. The most
recent completed review and its ID should reappear. New reviews create separate
IDs; older bundles and snapshots stay available at their original URLs:

```text
/api/prop-review/<review-id>
/api/prop-review/<review-id>/exports/bundle.zip
```

Files live under `data/prop_reviews/<review-id>/` by default, or under
`$ALPHAQUEST_DATA_DIR/prop_reviews/`. The user's dataset library and normal
backtest catalog are not used to store the synthetic sources. This evidence
store is separate from the future simulation result store.

## Automated verification

Run the rules, adapter, review API, and real Chromium workflow checks:

```bash
.venv/bin/python -m pytest -q tests/test_prop_configuration.py tests/test_prop_sessions.py tests/test_prop_review.py tests/test_prop_review_browser.py
```

For browser checks, install the optional dependency and Chromium if needed:

```bash
.venv/bin/python -m pip install -e '.[browser]' -c requirements.lock
.venv/bin/python -m playwright install chromium
```

The browser suite checks generation, switching quantity/platform, reading the
specification, JSON download, reload persistence, navigation, mobile layout,
and visible failure/retry behavior. API checks also restart the app, independently
verify bundle hashes/values, check isolation and invalid requests, and inject a
rule regression to ensure the review can actually fail.

## Requirement for future subtasks

Every future implementation must include a concrete deliverable, an executable
demonstration with inspectable actual outputs (preferably through this web app),
independent expectations and visible validation, saved evidence, and exact
instructions to reproduce/check it. Tests supplement those outputs. Extend this
guide with each subtask's deliverable, steps, expected numbers/outcomes, and scope.
The repository's [AGENTS.md](../AGENTS.md) records this instruction for future
Codex work.
