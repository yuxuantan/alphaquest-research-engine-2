# VWAP pullback in AQ and MultiCharts .NET

The repository contains the two maintained implementations of this strategy:

| Platform | Active source |
| --- | --- |
| AlphaQuest | [`alphaquest/strategies/vwap_pullback_risk_sizing.py`](../alphaquest/strategies/vwap_pullback_risk_sizing.py) |
| MultiCharts .NET | [`ORB_VWAP_CONT__NQ_1M_PIVOT_V01.cs`](ORB_VWAP_CONT__NQ_1M_PIVOT_V01.cs) |
| Shared scheduled NQ closures | [`calendars/cme_nq_closures.csv`](../calendars/cme_nq_closures.csv) |

The attached original C# is preserved byte-for-byte in
[`reference/ORB_VWAP_CONT__NQ_1M_PIVOT_V01.supplied.cs.txt`](reference/ORB_VWAP_CONT__NQ_1M_PIVOT_V01.supplied.cs.txt),
SHA-256 `13c2d1d20699fe89d8cc9be8d7207dc4abd4417b862d8777970fa7da34a01562`.
The original PowerLanguage source remains in `docs/strategies/` as well.
The active C# retains its original signal, ADX, sizing, order names and brackets,
with calendar-based entry eligibility and flatten timing added.

## Shared session policy

With `UseEODFlat=true` / `use_eod_flat=true`, load the CSV once when calculation
starts. Resolve only the current bar's Chicago local session-ending date:
17:00 and later belongs to the next date; a close-labelled 17:00 bar itself is
in maintenance. Weekends and `full_close` sessions prohibit entries. Within
reviewed coverage an absent exception means a regular 16:00 close. Beyond the
explicit coverage, reject the calculation rather than assume regular hours.

```text
cutoff = min(EODFlatTime, scheduled_close - 5 minutes)
flatten = first observed bar Close at/after cutoff -> MarketNextBar
entry signal = current label and next one-minute label strictly before cutoff
```

The default regular cutoff is 15:55; a configured 15:45 remains 15:45 on regular
days. A noon scheduled close gives 11:55; 12:15 gives 12:10. A missing cutoff
bar does not backdate submission to the previous observed bar. Both versions
block later submissions until an eligible next session, subject to the original
23:00 crossing reset and entry window. Those original rules are not replaced
by a new midnight reset. Setting EOD flattening off disables the calendar rules.

No future price bars, `SessionLastBar`, negative historical indices or inferred
last daytime bars establish the cutoff. A strict point-in-time historical
calendar claim still needs dated advance announcements; `verified_on` is the
review date, not announcement time. Read the [calendar maintenance guide](../calendars/README.md).

## Install and reproduce in MultiCharts .NET

1. Copy the CSV into Windows, for example
   `C:\AlphaQuest\calendars\cme_nq_closures.csv`. Preserve its bytes and compare
   `Get-FileHash -Algorithm SHA256` with `shasum -a 256` on the repository file.
   Current delivered SHA-256:
   `a71258719fdd433586250e242f5d10c78b49ea700a5312a24dc870307a05f81a`.
2. In the PowerLanguage .NET Editor use the supplied signal's class/name
   `ORB_VWAP_CONT__NQ_1M_PIVOT_V01` and replace its source with the **entire**
   active `.cs` file, including the calendar helper namespace at the end.
   Preserve your old signal separately first. Compile with the installed MC
   SDK. No additional CSV package is required. Do **not** define
   `AQ_CALENDAR_ONLY` in MC; it exists only for the standalone helper check.
3. Use full-session NQ one-minute close-labelled bars. Set the **chart timezone
   to Chicago exchange time**, including DST. `Bars.Time` is interpreted as
   that local wall time; the strategy does not infer/convert an NY/PC-local
   chart. AQ instead converts its saved source timezone through UTC to Chicago.
4. Use the supplied signal's bar-close calculation with IOG disabled. Match
   history/Maximum Bars Back to AQ's `max_bars_back` (42 for the current
   comparison), plus session template, data/roll mapping, volume, costs,
   initial capital and all signal Inputs. Keep trade volume consistent with
   the supplied C# `Bars.Ticks` series and AQ `Volume`. Do not change stop/target
   activation or fill priority while measuring the calendar change.
5. Set `SessionCalendarFile` to the Windows path, `UseEODFlat=true`, and the same
   `EODFlatTime` as AQ. Recalculate from a flat start. The Output log prints
   coverage and SHA-256 even if trade-level logging is off. A missing, malformed
   or uncovered CSV stops the calculation. Preserve that log with your export.
6. Re-run the existing **2021–2024 IS** with the actual comparison Inputs
   (including stop pivot 10, target pivot 5, ADX elevation threshold 0,
   ADX decay enabled and EOD 15:45). The constructor defaults still preserve the
   supplied C# defaults; entering these comparison values is required. Inspect
   the four rows below, then export trades and reconcile the entire report.

| Session-ending date | Independently reviewed schedule | Expected MC change |
| --- | --- | --- |
| 2021-01-18 | Close 12:00, cutoff 11:55 CT | Former late MC-only entry blocked |
| 2021-09-06 | Close 12:00, cutoff 11:55 CT | Held exposure submits flatten at 11:55, fills next Open |
| 2024-01-15 | Close 12:00, cutoff 11:55 CT | Held exposure submits flatten at 11:55, fills next Open |
| 2024-09-02 | Close 12:00, cutoff 11:55 CT | Former late MC-only entry blocked |

With complete one-minute bars, the next Open is recorded against the 11:56
close-labelled bar and ordinarily occurs around 11:55 CT. Do not compare that
label to a tick execution timestamp as though they were identical. The new AQ
IS report `030f3b33449b43b2b31d1b140be29267` has 486 trades, 28,155.00 gross,
1,934.28 commissions and 26,220.72 net. These are **AQ measured/reference
values**, not a measured result of the new MC signal. Matching them in a fresh
MC export remains the platform qualification step. Do not run new OOS to
resolve an IS calendar discrepancy.

## Data gaps and live automation boundary

AQ checks pending entries **before** filling them and cancels entries crossing
the cutoff or session boundary. In bar-close MC calculation, a next-bar order
can fill before `CalcBar` observes the next completed bar. The C# signal detects
an observed entry at/after cutoff or in a later session and throws; it also
rejects held exposure crossing the scheduled close, including a late bracket
that has already made the strategy flat. These are **backtest rejection
guards**, not broker-side cancellation or protection against a live fill.
MC's documented [per-bar calculation order](https://www.multicharts.com/trading-software/index.php?title=4.6.6_Calculation_per_Bar)
and [programming guide, section 4.6.9](https://download.multicharts.com/downloads/MultiCharts.NET-ProgrammingGuide-v1.1.pdf)
explain why current-bar signal code cannot undo orders already processed.

The calendar supplies known shortened-session deadlines automatically when
usable bars arrive. It does not discover new closures or supply a wall-clock
watchdog, broker acknowledgement, position reconciliation or outage handling.
An exception stops calculation; it does not guarantee cancellation/liquidation
of broker orders. A separate live execution design would be needed to cover
those cases. This change preserves bar-close timing for backtest comparison;
it has not been qualified for unattended live trading.

The delivered coverage ends **2026-11-02**. Extend and verify the calendar
before any later session, copy the same version to Windows, and deliberately
reload/recalculate. A running calculation keeps its initial snapshot.

At dataset EOF AQ explicitly closes remaining exposure at the last actual
Close with reason `end_of_data`. MC's end-of-history/report policy must be
matched or excluded from a platform comparison. It is not an early-close fill.
Decimal arithmetic versus MC doubles/ADX, volume provenance and stop-first
ambiguity also remain the existing platform qualification boundaries.

## Reproduce the compiled calendar comparison

With the .NET 8 SDK available, from the repository root:

```sh
.venv/bin/python tests/review_multicharts_calendar.py \
  --output artifacts/calendar-csharp-review-NEW
```

Use `--dotnet /path/to/dotnet` if it is not on PATH. The check compiles the
**same helper source in the active `.cs` file** with C# 5 syntax, excluding the
MC signal through `AQ_CALENDAR_ONLY`. It needs no MC substitutes or SDK.
It compares every covered date, including ordinary weekdays/weekends, for
15:45 and 15:55 cutoffs: **7,918 matching plans** and **31,672 boundary checks**.
Nine malformed/uncovered cases reject in both languages; UTF-8 BOM, quoted
commas, escaped quotes and embedded newlines are accepted. Actual outputs are
`artifacts/calendar-csharp-review-20261102/{build.txt,csharp-plans.csv,verification.json}`.

The compiled helper check does **not** compile the full PowerLanguage signal,
execute an MC backtest or submit a live order. Those require the installed
Windows MC SDK/host and fresh exports. No user's VM was accessed for this work.
