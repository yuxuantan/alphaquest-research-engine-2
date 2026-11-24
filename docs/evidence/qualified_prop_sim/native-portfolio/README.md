# Native risk, portfolio and replacement-cashflow evidence

This is an actual normal-product run on an isolated copy of the user's qualified
NQ source. It is historical research using NQ reference prices for MNQ; it is not
measured micro execution, provider certification or future-profit evidence. The
original port-8000 server, active confidence job, datasets and reports were not
changed to generate this demonstration.

## Reproduce in the existing portal

After applying the implementation, open the existing IS backtest:
`/#backtests/report/bfa89f7e4714444391e19ef577efeeb4`.

1. Click **Configure prop analysis**, then **Portfolio allocation, percentage
   risk & full cash flow**. Select VWAP pullback, `ofb_bars_NQ`, Broad 9 / Narrow 5
   (campaign candidate 2, qualified by the existing OOS and Monte Carlo record).
2. Set LucidFlex 50K, monthly fee cap $500, maximum accounts 1, compare separate
   and shared placements. Percentage risk: Evaluation 1%, Funded 0.2%, initial
   $50,000 basis, both contract ceilings 40.
3. Expand Fees/settlement/windows. Keep 40% Evaluation consistency, purchase
   $80.50, activation $0, commission $0.50 per MNQ per side, receipt lag 2 days.
   Set IS 2024-12-23 through 2024-12-31; OOS 2025-01-02 through 2025-01-10.
4. Click **Run allocation and full cash flow** once. No later confirmation is
   required. Navigate to Dataset while it runs; reopen through saved simulations
   or Job history. Source CSV validation takes time; progress reads themselves
   do not reload the price history. Stop remains available.
5. Expect three IS family members: zero accounts, one separate account, and one
   shared account with the sole strategy at 100% risk share. Expand the IS
   comparison and download the alternative's native trades/risk decisions.
6. Reload saved results. Expect the same analysis ID and immutable frozen choice,
   with no new simulation. Evidence ZIP and the individual ledgers must download.

## Independent expected observations

The two invested alternatives pay $80.50 and receive no trader cash inside this
short IS window. Their retained Evaluation P&L is **not** investor cash. Therefore
both have net cash -$80.50 and the zero-purchase baseline wins at $0.00. It remains
the frozen choice in OOS and the continuous full-period scenario. This short
example does not establish the strategy's long-horizon business viability.

The invested IS diagnostic includes a real 26 December 2024 long trade:

- Decision close 21991.50, known initial stop 21975.75.
- Planned unit risk `(21991.50 - 21975.75) × $2 + 2 × $0.50 = $32.50`.
- Risk budget `1% × $50,000 = $500`; `floor(500 / 32.50) = 15 MNQ`, below the
  40-MNQ ceiling. Planned total risk is $487.50, chosen before the next open.
- Actual fill 21991.00, exit 22053.00. Gross `(22053 - 21991) × 2 × 15 = $1,860`;
  round-trip commissions `$1 × 15 = $15`; native net **$1,845**. Planning risk is
  not deducted again. This remains below the $3,000 Evaluation target.

`independent-validation.json` audits the exported ZIP without importing the
simulation engine: file/frozen hashes, family/baseline ranking, fixed OOS choice,
whole-contract risk rounding, actual fill P&L/costs, ledger/monthly conservation,
pending-vs-received amounts and position non-overlap.

Run that audit with:

```sh
.venv/bin/python scripts/verify_native_portfolio_report.py docs/evidence/qualified_prop_sim/native-portfolio/analysis.zip
```

`rejections.json` records six actual API checks with expected HTTP status:
duplicate configurations 422, Lucid cap 41 422, dates outside qualified IS 409,
unknown account profile 422, unqualified Monte Carlo ID 409, account count 5 422.
The analytical tests separately cover known 0.2% balance-based quantities
10/9/5, fixed-base quantities 10/10/5, shared one-position arbitration,
activation reservations/receipt cutoffs, repeated payout-limit replacements,
last-Sunday inactivity without a future purchase, compact session spools with
identical results and tamper rejection, source pins, stop/retry/history/deletion.
Those fixture oracles remain in tests, not the portal.

## Saved artifacts and checks

- `simulation.json`, `summary.json`, `journey.json`: normal saved parent, summary,
  navigation/reopen observations and zero browser JavaScript errors.
- `analysis.zip`: normal sealed report, frozen package, full IS family, source
  coverage, ledgers, account/control traces and native invested-IS diagnostic.
- Desktop/mobile screenshots: compact result cards, configuration and expandable
  details; no body-level horizontal overflow at 390px.
- `independent-validation.json`, `rejections.json`: arithmetic and admission audit.

Focused validation: 21 native/runtime/API/lifecycle/deletion/history checks and
both existing automatic fixed-size browser journeys (Apex and LucidFlex) pass.
The real-data browser journey, download audit and desktop/mobile inspection also
pass. The complete historical suite was not run. Existing numerical phase owners,
legacy joint sizing, all original data/reports and the unrelated pending
`workflow.js` edit are preserved. Temporary browser servers are stopped after
inspection; no persistent server is introduced by this increment.

The native mode currently requires VWAP EOD-flat configurations on one common
NQ/MNQ dataset. Shared accounts use one open position at a time and 25% risk-share
steps. It compares observed historical cash rather than portfolio Monte Carlo
expected cash or new GO certification. Different source calendars, concurrent
shared positions and live routing are outside this increment.

## Applied to the running workspace — 2026-11-14

The user approved application and restarting unfinished OOS. `live-application.json`
records the preserved completed IS reports/frozen packages and advancing four-worker
Evaluation OOS, with Funded queued. `live-ui-check.json` verifies the applied form,
mobile layout, phase caps and real source check. All 21 focused tests pass again
in the workspace. The existing user-managed port-8000 server remains running;
all owned temporary browser servers are stopped.

`single-strategy-ui/` contains explicitly synthetic UI regression screenshots and
journey records for the existing Apex/Lucid automatic workflow. Unchanged bulky
regression reports are not duplicated here; the new native `analysis.zip` and its
independent arithmetic/reference evidence remain fully inspectable above.
