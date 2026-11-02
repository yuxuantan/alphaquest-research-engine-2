using System;
using System.Globalization;
using AlphaQuest.MarketCalendars;

internal static class Program
{
    private static string Clock(DateTime? value)
    { return value.HasValue ? value.Value.ToString("HH:mm", CultureInfo.InvariantCulture) : ""; }
    private static int Main(string[] args)
    {
        try
        {
            NqSessionCalendar calendar = NqSessionCalendar.Load(args[0]);
            Console.WriteLine("sha256," + calendar.Sha256);
            Console.WriteLine("session_date,eod,buffer,kind,close,cutoff,signal_before,signal_last,fill_before,fill_at");
            if (args.Length > 1)
            {
                // Explicit probe permits qualification of unknown date rejection.
                if (args[1] == "symbol")
                    Console.WriteLine(NqSessionCalendar.ResolveCalendarFile(args[2], args[3]));
                else
                    calendar.Plan(DateTime.ParseExact(args[1],"yyyy-MM-dd",CultureInfo.InvariantCulture),1555,
                                  args.Length > 2 ? Int32.Parse(args[2],CultureInfo.InvariantCulture) : 5);
                return 0;
            }
            for (DateTime day = calendar.CoverageStart; day <= calendar.CoverageEnd; day = day.AddDays(1))
                foreach (int eod in new int[] { 1545, 1555 })
                foreach (int buffer in new int[] { 1, 5, 10, 1440 })
                {
                    NqSessionPlan plan = calendar.Plan(day,eod,buffer);
                    bool a = false, b = false, c = false, d = false;
                    if (plan.Cutoff.HasValue)
                    {
                        DateTime cutoff = plan.Cutoff.Value;
                        a = plan.AllowsEntrySignal(cutoff.AddMinutes(-2));
                        b = plan.AllowsEntrySignal(cutoff.AddMinutes(-1));
                        c = plan.AllowsFill(cutoff.AddMinutes(-1));
                        d = plan.AllowsFill(cutoff);
                    }
                    Console.WriteLine(String.Format(CultureInfo.InvariantCulture,
                        "{0:yyyy-MM-dd},{1},{2},{3},{4},{5},{6},{7},{8},{9}",
                        day,eod,buffer,plan.Kind,Clock(plan.ScheduledClose),Clock(plan.Cutoff),a,b,c,d));
                }
            return 0;
        }
        catch (Exception error)
        { Console.Error.WriteLine(error.Message); return 1; }
    }
}
