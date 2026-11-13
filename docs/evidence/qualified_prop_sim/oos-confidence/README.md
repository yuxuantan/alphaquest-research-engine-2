# Frozen Prop Sim OOS qualification — 2026-11-13

These are actual normal-product downloads and screenshots from isolated Apex and
LucidFlex browser journeys. **Every market price and execution example here is
SYNTHETIC.** They prove local arithmetic, admission and product integration; they
are not observed trading results, provider parity or a forecast. No user data,
server, running job or Windows VM was changed. Temporary servers stopped at test
teardown. No real forward-trading evidence was fabricated.

## What to inspect

Each account-profile folder contains:

- `configure.png`: backtest-report entry into the existing Prop Sim form, source
  selection, separate phase searches and explicit eight-path test declaration.
- `evaluation-qualification.png`, `funded-qualification.png`: actual GO rows,
  OOS/IS confidence bounds, evidence requirements and **Forward execution PENDING**.
- `forward-declaration.png`: checking a frozen GO policy through the existing
  supplied-event monitor. The declaration is checked only; no future paper trades
  or automatic live approval are generated.
- `mobile-results.png`: saved result reopened at a 390-pixel viewport; the results
  table scrolls within its container.
- `*-qualification.zip`: complete sealed reports, both IS/OOS trade/risk captures,
  account paths, historical-bootstrap traces and checksums through normal downloads.
- `*-qualification.json`, `*-historical_bootstrap.json`, `*-source_checks.json`,
  `*-qualification_policy.json`, `*-oos_qualification.json`: inspectable report and
  artifact downloads. `simulation.json`/`journey.json` record normal product IDs.
- `SYNTHETIC-source.csv`: the actual normal dataset download, including artificial
  future-dated bars. Those dates do not represent future market observations.

`forward-synthetic-boundary/` contains a separately sealed normal-product
synthetic-monitor assessment and its Prop Sim execution review. Frozen sizing
matches, but there is just **one closed trade in one session**, with explicitly
synthetic provenance. The correct execution verdict is **INSUFFICIENT_EVIDENCE**,
regardless of a checked trade row. Original events and declarations remain
inspectable. It cannot become a passing prospective paper-trading record.

## Independent expected observations

The synthetic dataset repeats one identical six-trade daily pattern on every
weekday from 2024-01-01 through 2026-12-31. IS is 2024–2025 and OOS is 2026. OOS
has twelve complete months, 261 weekdays and `261 × 6 = 1,566` closed source
trades. The chosen strategy is `consecutive_green_hold`, green count 3, hold 16
minutes, one original NQ contract, then the explicit phase size is ten MNQ.

Because **every numeric daybook is identical**, independently resampling blocks
from either period can only reconstruct the same numerical history. Therefore
all 10,000 OOS/IS metric ratios, and both ends of every percentile interval, must
be exactly **1.00**. The implementation records one distinct evaluated complete
history in each period (`[1, 1]`); this is exact memoization, not reduced paths or
fabricated bootstrap results. Each calculation still uses all eight requested
account paths. This constant-history oracle does not test real-market uncertainty.

| Local profile / phase | Independently checkable expected result |
| --- | --- |
| Apex Evaluation | First-attempt pass on every path; $49 purchase + $129 activation = **$178** acquisition cost; one pass session plus one activation session = **2 calendar days** for the Monday scenario start |
| Apex Funded | Every path receives **$13,000** in the captured payout ledger within the saved 90-day horizon; all eight paths, including any zeros, enter the mean |
| LucidFlex Evaluation | One **$80.50** purchase, no activation fee; identical positive days need three days to satisfy 40% consistency, hence **3 calendar days** |
| LucidFlex Funded | Five modeled $2,000 account deductions at 90% trader entitlement = `5 × 2,000 × .90 =` **$9,000** received per path; account deductions are $10,000, not trader cash |

Identical results pass the historical 1.50 maximum / 0.70 minimum ratio margins.
Forward execution stays PENDING in both profile journeys. No business dollar
policy was declared. The original IS selection/report is retained; OOS does not
select a winner. All 33 existing phase numerical source hashes match HEAD and
the working tree (`numerical-identities.json`). New qualification/forward hashes
are sealed separately in the reports.

Read-only verification, with no engine calls or resimulation:

```sh
.venv/bin/python scripts/verify_prop_oos_qualification_evidence.py
```

Expected: four verified account/phase records, all bounds exactly 1.00 and forward
PENDING. `independent-verification.json` records that command's actual output.

## Reproduce the actual workflow

For an existing fully qualified campaign, open its IS backtest report, follow
**Prop Sim**, choose account and phase size ranges, **Check source and settings**,
then **Run Evaluation and Funded**. In each phase select eligible IS rows, enter
the rationale, freeze, and click **Run OOS qualification**. Dollar limits are not
required. Follow the job while it runs or navigate away and return. Read the
individual ratios/bounds and evidence checks, download the normal ZIP and reload.
Actual variable histories may be NO_GO or insufficient; GO is not promised.

After historical GO, expand **Paper execution and parity review** and choose
**Configure paper observation**. Select the frozen family member, declare the
source and paper provenance, check and create the existing observation monitor.
Import genuine timestamped events using that monitor's documented schema and
assess them. Back in Prop Sim, choose the completed bound assessment, load its
closed trades, check signal/execution parity for each and enter review notes.
Save the execution review. Twenty distinct recorded trading sessions, thirty
closed trades and zero unexplained issues are required; missing evidence remains
insufficient. Other-phase bindings, stale/unassessed events and paused/retired
monitors reject. The supplied connection and manual parity assertions remain
uncertified.

Automated reproduction creates a labeled synthetic dataset through the normal
campaign/backtest APIs and uses the real portal, workers and downloads:

```sh
.venv/bin/python -m pytest -q tests/test_prop_oos_qualification.py
ALPHAQUEST_PROP_QUALIFICATION_EVIDENCE_DIR=/private/tmp/aq-oos-confidence \
  .venv/bin/python -m pytest -q tests/test_prop_oos_qualification_browser.py
```

The browser test normally creates its own complete synthetic source. To save
setup time only, `ALPHAQUEST_QUALIFICATION_SEED_LIBRARY` may name an isolated copy
of that already-created synthetic test library; each browser test clones it
before starting its temporary server. It never points at or mutates a user
library. The captured run used this option after the full API journey had already
created and qualified the synthetic history.

Focused boundary tests cover equality, clearly adverse and overlapping intervals,
undefined ratios, evidence/precision floors, exact local resampling/path retention,
foreign family/phase binding, synthetic and retrospective observations, missing
trade review, unexplained issues, idempotent review, deletion retention and sealed
reuse. Coverage-only account-start diagnostics require no dollar declaration and
reuse the completed qualification without another historical search. Existing
business-policy/revision and current-procedure forward-monitor regressions pass.
