using System;
using System.Globalization;
using System.Linq;
using PowerLanguage;
using Signal = PowerLanguage.Strategy.OFB_OvernightBiasORB_Signal;

public static class OvernightBiasOrbHostChecks
{
    private static void Check(bool condition, string message)
    {
        if (!condition) throw new Exception(message);
    }

    private static void Step(Signal signal, DateTime time, double open, double high, double low, double close)
    {
        signal.Bars.Add(time, open, high, low, close);
        signal.Calculate();
    }

    private static Signal Scenario(bool visual, bool isLong)
    {
        var signal = new Signal(null) { showValidation = visual, ATR_Days = 1, BarAvgLen = 1, NumContracts = 2 };
        signal.Initialize();
        DateTime start = new DateTime(2026, 3, 2);
        signal.Bars.Add(start.AddHours(9.5), 100, 110, 90, 100);
        signal.Bars.CurrentBar = 0;
        Step(signal, start.AddHours(9.75), 100, 110, 90, 100);
        Step(signal, start.AddHours(16), 100, 110, 90, 100);
        Check(signal.OrderCreator.Sent.Count == 0, "ATR warm-up");
        Step(signal, start.AddHours(23.75), 200, 210, 190, 200);
        start = start.AddDays(1);
        Step(signal, start, 100, 110, 90, 100);
        Step(signal, start.AddHours(9.5), 100, 110, 90, 100);
        if (isLong)
        {
            Step(signal, start.AddHours(9.75), 108, 110, 107, 108);
            Step(signal, start.AddHours(10), 108, 112, 107, 111);
        }
        else
        {
            Step(signal, start.AddHours(9.75), 92, 93, 90, 92);
            Step(signal, start.AddHours(10), 92, 93, 88, 89);
        }

        string direction = isLong ? "L" : "S";
        string stop = isLong ? "105.00" : "95.00";
        string target = isLong ? "129.00" : "71.00";
        var orders = signal.OrderCreator.Sent;
        Check(orders.SequenceEqual(new[] { "ORB_" + direction + " market 2",
            direction + "-SL-FB " + stop + " 2", direction + "-TP-FB " + target + " 2" }), "fill-bar bracket");
        Check(Object.ReferenceEquals(signal.OrderCreator.Parent[direction + "-SL-FB"],
            signal.OrderCreator.Parent[direction + "-TP-FB"]), "shared pending parent");
        signal.StrategyInfo.MarketPosition = isLong ? 2 : -2;
        signal.StrategyInfo.AvgEntryPrice = isLong ? 120 : 80;
        Step(signal, start.AddHours(10.25), 100, 102, 98, 100);
        Check(orders.Skip(3).SequenceEqual(new[] { direction + "-SL " + stop + " 2",
            direction + "-TP " + target + " 2" }), "held bracket must keep signal-close anchor");
        Step(signal, start.AddHours(15.5), 100, 102, 98, 100);
        Check(orders.Count == 6 && orders[5] == "X" + direction + " market 2", "FlatTime sends next-open exit only");
        signal.StrategyInfo.MarketPosition = 0;
        signal.TotalTrades = 1;
        Step(signal, start.AddHours(15.75), 100, 102, 98, 100);
        signal.Calculate();
        Check(orders.Count == 6 && signal.SessionExitCalls == signal.Bars.CurrentBar, "one pass per bar and session exit always generated");
        return signal;
    }

    public static string Run()
    {
        int scenarios = 0;
        foreach (bool isLong in new[] { true, false })
        {
            Signal clean = Scenario(false, isLong), visual = Scenario(true, isLong);
            Check(clean.OrderCreator.Sent.SequenceEqual(visual.OrderCreator.Sent), "validation changed orders");
            Check(clean.Output.Written.Count == 0 && clean.DrwText.Created.Count == 0 &&
                clean.DrwTrendLine.Created.Count == 0, "default-off validation");
            Check(visual.DrwTrendLine.Created.Any(line => line.Color == System.Drawing.Color.SteelBlue)
                && visual.DrwTrendLine.Created.Any(line => line.Color == System.Drawing.Color.IndianRed)
                && visual.DrwTrendLine.Created.Any(line => line.Color == System.Drawing.Color.SeaGreen), "range and bracket drawings");
            Check(visual.Output.Written.Any(line => line.Contains("prior avg") && line.Contains("bias") && line.Contains("ATR 20.000000")),
                "numeric gate diagnostics");
            Check(visual.Output.Written.Any(line => line.Contains("closed trades +1") && line.Contains("prior submission: X")),
                "observed exit distinguished from submission");
            DateTime start = visual.Bars.Time[0].Date.AddDays(1);
            for (int i = 0; i < 70; ++i)
            {
                visual.StrategyInfo.MarketPosition = 2;
                // Artificial held bar sequence to exercise chart object retention.
                Step(visual, start.AddHours(11).AddDays(i), 100, 101, 99, 100);
            }
            Check(visual.DrwText.Created.Count(d => !d.Deleted) + visual.DrwTrendLine.Created.Count(d => !d.Deleted) <= 61,
                "bounded chart objects");
            visual.Restart();
            Check(visual.DrwText.Created.All(d => d.Deleted) && visual.DrwTrendLine.Created.All(d => d.Deleted), "recalculation cleanup");
            scenarios += 2;
        }
        return scenarios.ToString(CultureInfo.InvariantCulture) + " MultiCharts .NET host-double scenarios passed";
    }
}
