using System;
using System.Collections.Generic;
using System.Linq;
using PowerLanguage.Strategy;

static class Program
{
    private static void Check(bool condition, string message)
    {
        if (!condition) throw new Exception(message);
    }

    private static void Feed(OFB_RelStrength_Signal signal, DateTime stamp, double nq, double es, double high, double low, bool calculate)
    {
        signal.Bars.Add(stamp, high, low, nq);
        signal.SecondaryBars.Add(stamp, es, es, es);
        if (calculate) signal.Calculate();
    }

    private static List<string> Run(int direction, bool show, bool permit, bool stopEnabled, bool targetEnabled)
    {
        var signal = new OFB_RelStrength_Signal(null) { showValidation = show, TradeDir = permit ? 0 : -direction,
            StopFrac = stopEnabled ? .6 : 0, TgtFrac = targetEnabled ? 1 : 0 };
        signal.Bars.Info.Resolution.Size = signal.SecondaryBars.Info.Resolution.Size = 1;
        signal.Initialize();
        int[] days = { 20, 21, 24, 25, 26, 27, 28 };
        double[] move = { 0, 1, 0, -1 };
        for (int day = 0; day < days.Length; ++day)
        {
            var anchor = new DateTime(2025, 11, days[day], 8, 30, 0);
            if (day == 0) Feed(signal, anchor.AddMinutes(-1), 19999, 5000.25, 20010, 19990, false);
            for (int i = 0; i <= 390; ++i)
            {
                bool skippedShock = day >= 5 && i == 30;
                Feed(signal, anchor.AddMinutes(i), skippedShock ? 20400 : 20000 + move[i % 4],
                    i % 2 == 0 ? 5000 : 5000.25, skippedShock ? 20410 : 20010, 19990, true);
            }
        }
        Check(signal.OrderCreator.Sent.Count == 0, "No trades before warmup or on supplied full and early holidays.");
        var session = new DateTime(2025, 12, 1, 8, 30, 0);
        for (int i = 0; i < 30; ++i)
            Feed(signal, session.AddMinutes(i), 20000 + move[i % 4], i % 2 == 0 ? 5000 : 5000.25, 20010, 19990, true);
        var decision = session.AddMinutes(30);
        Check(signal.OrderCreator.Sent.Count == 0, "No order before 09:00.");
        double fill = 20000 + direction * 100;
        Feed(signal, decision, fill, 5000, fill + 1, fill - 1, true);
        signal.Calculate();
        if (!permit)
        {
            Check(signal.OrderCreator.Sent.Count == 0, "TradeDir blocks order.");
            return signal.OrderCreator.Sent;
        }
        string name = direction > 0 ? "RS.L" : "RS.S";
        Check(signal.OrderCreator.Sent.SequenceEqual(new[] { name + " market 1" }), "Decision submits only the next-open entry.");
        signal.StrategyInfo.MarketPosition = direction;
        signal.StrategyInfo.AvgEntryPrice = fill;
        Feed(signal, decision.AddMinutes(1), fill, 5000.25, fill + 30, fill - 30, true);
        var expected = new List<string> { name + " market 1" };
        if (stopEnabled) expected.Add(direction > 0 ? "RS.LS 20088.00 1" : "RS.SS 19912.00 1");
        if (targetEnabled) expected.Add(direction > 0 ? "RS.LT 20120.00 1" : "RS.ST 19880.00 1");
        Check(signal.OrderCreator.Sent.SequenceEqual(expected), "Entry close submits frozen enabled exits at independent prices.");
        Feed(signal, decision.AddHours(6), fill, 5000, fill + 1, fill - 1, true);
        string flat = direction > 0 ? "RS.LF" : "RS.SF";
        Check(signal.OrderCreator.Sent.Last() == flat + " this close 1", "15:00 flattens on this close.");
        if (show)
        {
            Check(signal.Output.Written.Any(s => s.Contains("samples=1980/1950") &&
                s.Contains("NQ close/anchor=" + fill + "/20000") && s.Contains("ES close/anchor=5000/5000")),
                "Decision Output reports anchors and sample gates.");
            Check(signal.Output.Written.Any(s => s.Contains("avg RTH range=20") && s.Contains(flat + " this close")),
                "Output reports 20-point range and flat submission.");
            Check(signal.DrwText.Created.Count > 0 &&
                signal.DrwTrendLine.Created.Count == (stopEnabled ? 1 : 0) + (targetEnabled ? 1 : 0), "Draws enabled legs only.");
            signal.Restart();
            Check(signal.DrwText.Created.All(t => t.Deleted) && signal.DrwTrendLine.Created.All(t => t.Deleted), "Restart clears drawings.");
        }
        else
            Check(signal.Output.Written.Count == 0 && signal.DrwText.Created.Count == 0 && signal.DrwTrendLine.Created.Count == 0,
                "Validation off is silent.");
        return signal.OrderCreator.Sent;
    }

    public static void Main()
    {
        foreach (int direction in new[] { 1, -1 })
        {
            foreach (bool stop in new[] { true, false })
                foreach (bool target in new[] { true, false })
                    Check(Run(direction, false, true, stop, target).SequenceEqual(Run(direction, true, true, stop, target)),
                        "Validation preserves the order stream.");
            Run(direction, true, false, true, true);
        }
        var signal = new OFB_RelStrength_Signal(null);
        signal.Bars.Info.Resolution.Size = signal.SecondaryBars.Info.Resolution.Size = 1;
        signal.Initialize();
        var stamp = new DateTime(2025, 12, 1, 8, 30, 0);
        Feed(signal, stamp, 20000, 5000, 20000, 20000, false);
        signal.Bars.Add(stamp.AddMinutes(1), 20000, 20000, 20000);
        signal.SecondaryBars.Add(stamp.AddMinutes(2), 5000, 5000, 5000);
        try { signal.Calculate(); throw new Exception("Mismatched feeds should fail."); }
        catch (InvalidOperationException ex) { Check(ex.Message.Contains("matching Data1 and Data2"), "Alignment error."); }
        Console.WriteLine("Relative Strength: long/short, warmup, holidays, alignment, stop/target toggles, order timing and validation on/off passed.");
    }
}
