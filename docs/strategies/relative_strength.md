# Relative Strength

Relative Strength tests whether an unusually large NQ move, after accounting for ES, continues intraday. The supplied [RelStrength_v3 PowerLanguage](relative_strength.pl) is the reference. The ports are [AlphaQuest](../../alphaquest/strategies/relative_strength.py) and [MultiCharts .NET](../../multicharts/signals/relative_strength/OFB_RelStrength_Signal.cs). In AlphaQuest open **Campaign → Relative Strength** to read the explanation before choosing a dataset.

## Signal and execution

- Use close-stamped one-minute Globex data. The default Central-time calculation window is strictly after 08:30 through 15:00, so the first regular-session bar is 08:31. The opening anchors are the preceding observed NQ and ES closes.
- Express both one-minute log returns in basis points. Update the exponential averages of the cross-product and squared returns on each eligible minute, including the decision bar. The default smoothing factor is 2 ÷ (20 × 390 + 1). Beta is the cross-product average divided by the ES squared-return average. The residual variance is the exponentially weighted second moment of the hedged return.
- Make one check on the first eligible RTH close at or after 09:00. The source requires at least five sessions' worth of eligible minutes, positive residual variance and valid anchors. Z is the NQ move from its anchor minus beta times the ES move, divided by the square root of residual variance times observed bars since the anchor. A Z of +1.25 or greater buys at the following open. A Z of −1.25 or less sells short at the following open. Trade direction and the daily entry limit also apply.
- When the new position is first observed at the entry bar's close, measure 0.6× the average prior RTH high–low range for the stop and 1.0× for the target from the actual fill. The range window is a simple average of up to 20 prior eligible sessions and is updated at the next RTH start. Each leg can be disabled independently with a nonpositive multiplier. The two orders can first fill on the bar **after the entry bar**.
- The source sends a same-close exit on the first held bar whose clock is at or above the flat time, or at or below the RTH start. Default flat time is 15:00 CT. An already active bracket can execute before that bar's close. Missing bars are never synthesized. AlphaQuest labels any ordinary dataset-end liquidation `end_of_data`.
- The two exact lists in the source skip 170 full closures and 37 early closes from 2010 through 2027 by default. Skipped days do not update the return moments, contribute range observations or permit entry. Dates after the table ends have no automatic holiday exclusions.

For example, NQ up 60 bp and ES up 20 bp at beta 1.5 leaves a +30 bp residual. At a 20 bp residual standard deviation for the observed opening window, Z is +1.5. If the long fills at 20,000 and the average prior range is 300 points, the stop and target submitted at the entry close are 19,820 and 20,300.

## Prepare and run in AlphaQuest

1. Export the same continuous NQ and ES one-minute trade-price bars with the same session template and roll convention. MNQ is supported as Data1 if you want to calculate and trade on MNQ bars. Keep both of the original exports for reconciliation. Use the usual AlphaQuest header `Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol` for each and record their true source timezones.
2. Pair the raw files by exact UTC close timestamp. Specify `--es-timezone` if ES has a different source timezone. The command checks both streams and aborts on any unmatched row. The result retains all primary fields and appends `ESClose`.

   ```sh
   .venv/bin/python -m alphaquest.pair_relative_strength NQ.csv ES.csv NQ-ES.csv --timezone America/Chicago
   ```

3. In **Datasets**, validate and save the paired CSV with its primary file's timezone, explicit primary symbol, tick size and monetary point value. The saved dataset hash covers every ES close used in the strategy. The CSV format also accepts an exact `ESClose` column appended by an equivalent external process.
4. From **Campaign → Relative Strength**, select **New backtest**, choose the paired dataset, and declare IS and OOS dates and costs. Use **Open mechanic validation → Run**. Add about three months of leading history to each replay's selected calculation range for a settled comparison. AlphaQuest starts each IS/OOS replay from its selected first bar. The first selected bar supplies the one-bar lookback, and the source initializes its ES series variable before eligible return calculation begins. Match the first loaded timestamp in MultiCharts.
5. Download the trades and saved review JSON. Compare real charts and platform exports before confirming the mechanics checklist. AlphaQuest uses its minute OHLC model for active orders. For two touched levels, the path visits the nearer extreme first, Low first on ties. Check fractional-tick order prices, gap fills and both-touched cases against your MultiCharts settings. AlphaQuest records stop and target exits as `stop_loss` and `take_profit`. The timed closes retain `RS.LF` and `RS.SF`.

The strategy supports fixed saved-path scaling. Controlled native sizing and new stop-based sizing require different protection mechanics and are unavailable for this port.

## Install and check in MultiCharts .NET

Create a signal named `OFB_RelStrength_Signal` in the PowerLanguage .NET Editor and paste the complete C# file. Use NQ as Data1 and ES as Data2, both one-minute continuous series from the same feed. Set close timestamps, show the Exchange clock and verify that the first regular-session bar reads 08:31. Use IOG off, Bar Magnifier off and MaxBarsBack 1 for the first comparison. Start with matching costs and chart history. The signal uses the native secondary-stream accessor and native next-open/this-close orders. [MultiCharts .NET Programming Guide](https://download.multicharts.com/downloads/MultiCharts.NET-ProgrammingGuide-v1.0.pdf)

Turn `showValidation=true` on in the signal Inputs and recalculate. The Output window records daily decisions, including rejected ones, with both anchors and closes, beta, residual variance, Z, warm-up counts, direction, position and calendar gates. The entry-bar close prints the observed fill reference, range and submitted exits. Red stop and green target lines start at the first bracket submission and extend right while the orders are active. After an exit, each line ends on the bar where the signal observes the position close or submits the scheduled same-close exit. The chart keeps the most recent 240 historical drawings plus any active stop and target lines. Use native strategy markers and the Strategy Performance Report for actual fills and exit reasons. Recalculate with `showValidation=false` to compare the exported trade lists.

The signal can calculate when Data2's latest available bar is older than the current Data1 bar. It uses the ES close exposed by the chart as of that NQ bar. If the exposed timestamp is later, it checks one Data2 bar back. If neither exposed bar is at or before the NQ timestamp, ES is unavailable for that calculation, so the return update and any entry decision requiring ES are ineligible. Existing positions still get their normal exit processing. As in PowerLanguage, the previous ES input is the value used on the preceding Data1 calculation. With `showValidation=true`, Output lists the first ten alignment differences with the Data1 time, exposed Data2 time and ES bar used. Every decision also shows the ES timestamp used. For AlphaQuest parity, compare a window where both exports have matching timestamps. AlphaQuest's paired CSV import still requires exact alignment.

## Reproduce local validation

The browser journey uses **synthetic** paired bars. It verifies that the campaign explanation precedes dataset selection, unpaired NQ is disabled, the normal workflow publishes the mechanics report and the saved details reopen after reload. The fixture's prior eligible ranges are 20 points. Two extreme moves on supplied holidays are skipped. One long enters at 20,100 on the 09:01-labelled bar. That bar touches both prospective exits while they are inactive. The 09:02-labelled bar hits the 20,120 target for $400 before costs, with no slippage or commission. The fixture does not substitute for the actual NQ/ES comparison.

Saved browser evidence includes the [campaign page](../evidence/relative-strength-mechanics-20261124/relative-strength-campaign.png), [trades CSV](../evidence/relative-strength-mechanics-20261124/trades.csv) and [mechanics review with the saved report](../evidence/relative-strength-mechanics-20261124/mechanic-review.json). The synthetic portal test leaves MultiCharts confirmation pending.

```sh
.venv/bin/pytest -q tests/test_relative_strength.py tests/test_strategy_sizing_contract.py
ALPHAQUEST_TEST_BROWSER_CHANNEL=chrome .venv/bin/pytest -q tests/test_campaign_mechanics_browser.py -k relative_strength
dotnet run --project tests/multicharts_relative_strength/RelativeStrengthCheck.csproj
```

The C# harness compiles the complete C# 5 signal against test doubles using the .NET 9 SDK. It exercises long and short submissions, calendar and warm-up gates, matched, lagging and ahead ES timestamps, independently disabled stop and target legs, the same-close exit, and order equality with validation on and off. Installed MultiCharts .NET compilation, draw rendering and trade-for-trade comparison with the original PowerLanguage remain to be verified on Windows.
