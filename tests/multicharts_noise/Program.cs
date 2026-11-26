using System;
using System.Drawing;
using System.Linq;
using PowerLanguage;
using PowerLanguage.Strategy;

// Feed bar-close positions explicitly. These checks exercise the signal's
// submissions and visuals, with no attempt to emulate the host's fills.
internal static class Program
{
    private static readonly DateTime SignalDay = new DateTime(2026, 3, 5);

    private static void Bar(OFB_Noise_Signal signal, DateTime day, int hhmm, double open, double close)
    {
        signal.Bars.Add(day.AddHours(hhmm / 100).AddMinutes(hhmm % 100),
            open, Math.Max(open, close), Math.Min(open, close), close);
        signal.Calculate();
    }

    private static OFB_Noise_Signal Warm(bool diagnostics, int cap)
    {
        var signal = new OFB_Noise_Signal(null) { LookbackDays = 1, MaxTradesPerDay = cap, showValidation = diagnostics };
        signal.Initialize();
        signal.Bars.Add(SignalDay.AddDays(-2).AddHours(14), 1000, 1000, 1000);
        // The harness reserves one history bar, as the source needs Date[1].
        signal.Bars.CurrentBar = 0;
        Bar(signal, SignalDay.AddDays(-2), 1500, 1000, 1000);
        Bar(signal, SignalDay.AddDays(-1), 845, 1000, 1000);
        Bar(signal, SignalDay.AddDays(-1), 900, 1000, 1000);
        Bar(signal, SignalDay.AddDays(-1), 915, 1000, 1000);
        Bar(signal, SignalDay.AddDays(-1), 930, 1000, 1000);
        Bar(signal, SignalDay.AddDays(-1), 1500, 1000, 1000);
        Bar(signal, SignalDay, 845, 1000, 1000);
        Require(signal.OrderCreator.Sent.Count == 0, "Premature submission during slot warm-up");
        Require(signal.CurSpecOrdersMode == ESpecOrdersMode.PerContract, "SetStopContract basis");
        Require(signal.LastStopLoss == 1000 && signal.LastProfitTarget == 500, "50/25 points at NQ point value");
        return signal;
    }

    private static void Require(bool condition, string message)
    {
        if (!condition) throw new Exception(message);
    }

    private static OFB_Noise_Signal Reversal(bool validate, int cap, int sign)
    {
        var signal = Warm(validate, cap);
        Bar(signal, SignalDay, 900, 1000, 1000 + sign * 5);
        signal.Calculate();  // A repeated close callback cannot consume the slot twice.
        signal.StrategyInfo.MarketPosition = sign * 2;
        signal.StrategyInfo.AvgEntryPrice = 1000 + sign * 6;
        Bar(signal, SignalDay, 915, 1000, 1000 - sign * 5);
        var expected = sign > 0 ? new[] { "NoiseLong", "LongRevExit", "RevToShort" }
                               : new[] { "NoiseShort", "ShortRevExit", "RevToLong" };
        Require(signal.OrderCreator.Sent.SequenceEqual(expected.Take(cap == 1 ? 2 : 3).Select(n => n + " market 2")),
            "Reversal order sequence or submission cap");
        return signal;
    }

    public static void Main()
    {
        foreach (int sign in new[] { -1, 1 })
        {
            foreach (int cap in new[] { 1, 10 })
            {
                var plain = Reversal(false, cap, sign);
                var shown = Reversal(true, cap, sign);
                Require(plain.OrderCreator.Sent.SequenceEqual(shown.OrderCreator.Sent), "Validation changed orders");
                Require(plain.Output.Written.Count == 0 && plain.DrwTrendLine.Created.Count == 0, "Default-off diagnostics");
                Require(shown.Output.Written.Any(s => s.Contains("prior samples 1/1") && s.Contains("Upper/lower 1000/1000")),
                    "Validation missed inputs");
                Require(shown.DrwText.Created.Count == 0, "Validation added text over the native trade markers");
                string exit = sign > 0 ? "LongRevExit" : "ShortRevExit";
                Require(shown.Output.Written.Any(s => s.Contains("Next-open submission: " + exit) &&
                                                      s.Contains("Observed position 0->" + sign * 2)),
                    "Order and position details are available in Output");
                Require(shown.DrwTrendLine.Created.Count(l => l.Color == Color.SteelBlue) == 4, "Both noise bands");
                Require(shown.DrwTrendLine.Created.Count(l => l.Color == Color.DarkOrange) == 2, "Exit EMA");
                Require(shown.DrwTrendLine.Created.Any(l => l.Begin.Price == 1000 + sign * 31), "Fill-relative target level");
                Require(shown.DrwTrendLine.Created.Any(l => l.Begin.Price == 1000 - sign * 44), "Fill-relative stop level");
                shown.showValidation = false;
                shown.Restart();
                Require(shown.DrwTrendLine.Created.All(l => l.Deleted),
                    "Validation drawings survived reset");
            }
        }

        var signal = Warm(true, 10);
        signal.MaxStopsPerDay = 1;
        Bar(signal, SignalDay, 900, 1000, 1005);
        signal.TotalTrades = 1;
        signal.Positions[1].Profit = -2000;
        Bar(signal, SignalDay, 915, 1000, 1005);
        Require(signal.OrderCreator.Sent.Count == 1, "Closed loss of exactly one position stop must block a new order");
        Require(signal.Output.Written.Last().Contains("-2000 <= -2000: True"), "Loss gate diagnostics");
        Bar(signal, SignalDay, 1500, 1000, 1000);
        Bar(signal, SignalDay.AddDays(1), 845, 1000, 1000);
        Bar(signal, SignalDay.AddDays(1), 900, 1000, 1010);
        Require(signal.OrderCreator.Sent.Last() == "NoiseLong market 2" && signal.OrderCreator.Sent.Count == 2,
            "Civil date resets both gates");
        signal.StrategyInfo.MarketPosition = 2;
        Bar(signal, SignalDay.AddDays(1), 1445, 1000, 1000);
        Require(signal.OrderCreator.Sent.Count == 2 && signal.SessionExitCalls == 0, "No backup clock exit");
        Bar(signal, SignalDay.AddDays(2), 1430, 1000, 1000);
        Require(signal.OrderCreator.Sent.Last() == "FlatLong1430 market 2", "Exact clock exit independent of slot warm-up");

        Console.WriteLine("Noise C# 5 signal checks passed: price overlays, Output diagnostics, identical orders with validation enabled, both reversal sides and caps, native protection arguments, daily loss/reset, and exact flat time.");
    }
}
