// Decision-state port of docs/strategies/twin_continuation.pl, with optional
// fill-activated protection in the host. See the versioned execution guide.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
#if !AQ_TWIN_CORE_ONLY
using System.Drawing;
using PowerLanguage;
#endif

namespace AlphaQuest.Twin
{
    // Prepared while the parent entry is still pending. Native special orders
    // resolve distances from the actual fill; absolute swing stops remain
    // conditional exits bound to BO-L / BO-S, including on the entry bar.
    public sealed class TwinProtectionPlan
    {
        public string Setup;
        public double? StopDistance, TargetDistance;
        public readonly List<TwinOrder> SwingStops=new List<TwinOrder>();

        public static double StopPrice(double price,double tick,bool longPosition)
        {
            if(double.IsNaN(price) || double.IsInfinity(price) || double.IsNaN(tick) || double.IsInfinity(tick) || tick<=0)
                throw new ArgumentException("Immediate protection requires finite prices and a positive symbol tick size.");
            decimal step=(decimal)tick,q=(decimal)price/step;
            return (double)((longPosition ? decimal.Floor(q) : decimal.Ceiling(q))*step);
        }

        public static TwinProtectionPlan Build(TwinCore c, IList<TwinOrder> orders, double position, string pendingSetup)
        {
            var plan=new TwinProtectionPlan();
            if(position==0)
            {
                foreach(var order in orders)
                    if(order.Entry==null)
                    {
                        string setup=order.Name.StartsWith("MO-",StringComparison.Ordinal) ? "MO" : "BO";
                        if(plan.Setup!=null && plan.Setup!=setup) throw new InvalidOperationException("Mixed parent setups cannot share immediate protection.");
                        plan.Setup=setup;
                        if(setup=="BO")
                            plan.SwingStops.Add(new TwinOrder(order.Name=="BO-L" ? "BO-LS" : "BO-SS",order.Name,
                                order.Name=="BO-L" ? "Sell" : "BuyToCover","stop",order.Name=="BO-L" ? c.StpL : c.StpS,order.Quantity));
                    }
            }
            else
            {
                if(pendingSetup!="MO" && pendingSetup!="BO")
                    throw new InvalidOperationException("Filled position has no known parent setup for immediate protection.");
                plan.Setup=pendingSetup;
            }
            if(plan.Setup=="MO") plan.StopDistance=c.MO_StopPoints;
            else if(plan.Setup=="BO")
            {
                if(c.AtrU<=0 && (c.BO_TargetMult>0 || c.BO_MaxStopMult>0))
                    throw new InvalidOperationException("Immediate BO target/cap protection requires a positive frozen 15-minute ATR.");
                if(c.BO_TargetMult>0) plan.TargetDistance=c.BO_TargetMult*c.AtrU;
                if(c.BO_MaxStopMult>0) plan.StopDistance=c.BO_MaxStopMult*c.AtrU;
            }
            return plan;
        }
    }

    // Optional chart text, kept separate from the entry/exit calculations.
    public static class ValidationText
    {
        public static string Compact(TwinCore c, DateTime stamp, double position)
        {
            return string.Format(CultureInfo.InvariantCulture,
                "TWIN/{7} {0:MM-dd HH:mm} | pos {1:0} | BO {2}\n" +
                "Open H {3} | L {4}\n" +
                "MO {5} / +/-{6:0.##} | click bar: Commentary",
                stamp,position,c.Armed ? "armed" : "idle",
                c.HaveSwH && c.SwHOpen ? c.SwH.ToString("0.##",CultureInfo.InvariantCulture) : "--",
                c.HaveSwL && c.SwLOpen ? c.SwL.ToString("0.##",CultureInfo.InvariantCulture) : "--",
                c.SHaveOsc ? c.SOscV.ToString("0.##",CultureInfo.InvariantCulture) : "--",c.MO_Trigger,
                c.ImmediateProtection ? "FILL" : "LEGACY");
        }

        public static string Momentum(TwinCore c, double minutes, double end, double position)
        {
            return string.Format(CultureInfo.InvariantCulture,
                "MO 10m end={0:0000} observed={1}/10 fullRequired={2} buckets={3}/{4}\n" +
                "close={5:G17} basis={6:G17} ATR={7:G17} raw={8:G17} prev={9:G17} osc={10:G17} trigger=+/-{11:G17}\n" +
                "freshCross={12} previousValid={13} window={14:0000}-{15:0000} inWindow={16} warm={17} fullOK={18}\n" +
                "flat={19} dailyUsedBefore={20} halfDay={21} enabled={22} allowLong={23} allowShort={24}",
                end,minutes,c.MO_FullBarsOnly,c.SNB,c.MO_Warmup,c.FC,c.SPivot,c.SatrW,c.SRaw,c.SOscPrev,c.SOscV,c.MO_Trigger,
                c.SSide,c.SHavePrev,c.MO_WindowStart,c.MO_WindowEnd,end>=c.MO_WindowStart && end<=c.MO_WindowEnd,
                c.SNB>=c.MO_Warmup,!c.MO_FullBarsOnly || minutes==10,position==0,c.STradedToday,c.SHalfDay,
                c.UseMomentum,c.MO_AllowLong,c.MO_AllowShort);
        }

        public static string Snapshot(TwinCore c, DateTime stamp, double high, double low, double close,
                                      double position, double average, double trades, IList<TwinOrder> orders)
        {
            var s=new StringBuilder();
            s.AppendFormat(CultureInfo.InvariantCulture,
                "TWIN VALIDATION {0:yyyy-MM-dd HH:mm} shifted={1:0000} shift={2} H/L/C={3}/{4}/{5}\n" +
                "position={6} avgFill={7} closedTrades={8} qty={9}; submissions below are not fills\n" +
                "BO enabled={10} armed={11} frozenOkL={12} frozenOkS={13} pivotTF={14} candles={15}/7 (3L/3R) session={16:0000}-{17:0000}\n" +
                "confirmed H={18} have/open={19}/{20}; L={21} have/open={22}/{23}\n" +
                "FROZEN L entry/stop={24}/{25}; S entry/stop={26}/{27}; ATR={28} currentATR={29} warm={30}/{31}\n" +
                "volRatio={32} cap={33} lookback={34} volOK={35}; fillCutoff={36:0000} timeOK={37} flatTime={38:0000}\n" +
                "BO targetATR={39} maxStopATR={40}; MO EMA/ATR/signal={41}/{42}/{43} stopPts={44} exit={45:0000} fireNow={46} dailyUsedNow={47}\n",
                stamp,c.TimeC,c.ClockShift,high,low,close,position,average,trades,c.Qty,
                c.UseBreakout,c.Armed,c.OkL,c.OkS,c.BO_PivotTF,c.NC,c.BO_SessionOpen,c.BO_SessionClose,
                c.SwH,c.HaveSwH,c.SwHOpen,c.SwL,c.HaveSwL,c.SwLOpen,c.LvlL,c.StpL,c.LvlS,c.StpS,
                c.AtrU,c.AtrV,c.TrN,c.BO_ATRPeriod,c.VolRatio,c.BO_VolCap,c.BO_VolLookback,
                c.BO_VolCap<=0 || c.VolRatio<=c.BO_VolCap,c.BO_LastFill,c.SmNow+1<c.FillEndSm,c.BO_ExitTime,
                c.BO_TargetMult,c.BO_MaxStopMult,c.MO_BasisLen,c.MO_RangeLen,c.MO_SignalLen,c.MO_StopPoints,c.MO_ExitTime,c.SFire,c.STradedToday);
            s.AppendFormat(CultureInfo.InvariantCulture,
                "15m H/L/C={0}/{1}/{2}; armClosedTrades={3}; armTradeCountOK={4}; flat={5}; MO has priority over BO\n",
                c.B15H,c.B15L,c.B15C,c.ArmTrades,trades<=c.ArmTrades,position==0);
            s.Append(c.ImmediateProtection ? "Protection: ON FILL; native ProfitTarget/StopLoss plus conditional BO swing stops\n" :
                "Protection: FOLLOWING BAR (legacy)\n");
            if(c.BO_TargetMult>0)
                s.AppendFormat(CultureInfo.InvariantCulture,
                    "BO TP: frozen15mATR={0:G17} x multiplier={1:G17} = distancePts={2:G17}; long=actualFill+distance; short=actualFill-distance\n",
                    c.AtrU,c.BO_TargetMult,c.AtrU*c.BO_TargetMult);
            else s.Append("BO TP: disabled (BO_TargetMult=0)\n");
            s.Append(c.ImmediateProtection ? "CALCULATED ORDER CANDIDATES (MO stops / BO targets use native exits; named exits bind their entry):" :
                "SUBMIT (exits bind only their named entry):");
            foreach (var o in orders)
                if (o.Entry==null || position!=0)
                    s.AppendFormat(CultureInfo.InvariantCulture,"\n{0} {1} {2} price={3} qty={4} owner={5}",
                        o.Name,o.Action,o.Kind,o.Kind=="market" || o.Kind=="close" ? "market" : o.Price.ToString("0.#####",CultureInfo.InvariantCulture),
                        o.Entry==null ? o.Quantity : Math.Abs(position),o.Entry ?? "entry");
            s.Append("\nSession exit: chart session / GenerateExitOnClose; chart timezone must be Chicago. Bar-close observations, not intrabar fill timestamps.");
            return s.ToString();
        }

        public static string EntrySignature(TwinCore c, IList<TwinOrder> orders)
        {
            var s=new StringBuilder();
            foreach (var o in orders)
                if (o.Entry==null) s.AppendFormat(CultureInfo.InvariantCulture,"{0}:{1}:{2}:{3};",o.Name,o.Kind,o.Price,o.Quantity);
            if (s.Length==0) return "";
            s.AppendFormat(CultureInfo.InvariantCulture,"ATR={0}; stops={1}/{2}",c.AtrU,c.StpL,c.StpS);
            return s.ToString();
        }

        public static string Commentary(TwinCore c, DateTime stamp, double high, double low, double close,
            double position, double average, double trades, IList<TwinOrder> orders, string momentum,
            IList<string> crossings, string previousSignature, double previousPosition, double previousTrades)
        {
            var text=new StringBuilder();
            if(Math.Sign(position)!=previousPosition)
                text.AppendFormat(CultureInfo.InvariantCulture,"POSITION OBSERVED {0} -> {1}, average fill={2}\n",
                    previousPosition,Math.Sign(position),average);
            if(trades!=previousTrades) text.Append("CLOSED TRADE COUNT CHANGED: inspect MC trade markers for execution details.\n");
            string signature=EntrySignature(c,orders);
            if(signature!=previousSignature) text.Append(signature.Length>0 ? "ENTRY SUBMISSION CHANGED\n" : "NO ENTRY RENEWAL THIS BAR\n");
            foreach(string crossing in crossings) text.Append(crossing).Append('\n');
            if(crossings.Count==0)
                text.Append("LATEST COMPLETED MOMENTUM BUCKET (held until next completion):\n").Append(momentum).Append('\n');
            text.Append(Snapshot(c,stamp,high,low,close,position,average,trades,orders));
            return text.ToString();
        }
    }

    // Debug-only input journal. An inspected bar is reconstructed from a private
    // checkpoint copy, never by stepping the live signal backwards or twice.
    // One compact frame per bar; a deep checkpoint only every 1024 bars.
    public sealed class ValidationReplay
    {
        private const int Interval=1024;
        private struct Frame
        {
            public DateTime Time;
            public double High,Low,Close,Position,Average,Trades;
        }
        private sealed class Checkpoint
        {
            public TwinCore Core;
            public string Momentum,Signature;
        }
        private readonly List<Frame> frames=new List<Frame>();
        private readonly List<Checkpoint> checkpoints=new List<Checkpoint>();
        private int firstBar;

        public void Record(int bar, TwinCore before, DateTime stamp, double high, double low, double close,
                           double position, double average, double trades, string momentum, string previousSignature)
        {
            if(frames.Count==0) firstBar=bar;
            if(bar!=firstBar+frames.Count) throw new InvalidOperationException("Validation journal requires each completed chart bar once.");
            if(frames.Count%Interval==0)
                checkpoints.Add(new Checkpoint {Core=before.CopyForInspection(),Momentum=momentum,Signature=previousSignature});
            frames.Add(new Frame {Time=stamp,High=high,Low=low,Close=close,Position=position,Average=average,Trades=trades});
        }

        public bool TryRead(int bar, out string commentary)
        {
            commentary=null;
            int index=bar-firstBar;
            if(index<0 || index>=frames.Count) return false;
            int begin=index/Interval*Interval;
            var checkpoint=checkpoints[index/Interval];
            var copy=checkpoint.Core.CopyForInspection();
            string momentum=checkpoint.Momentum,signature=checkpoint.Signature;
            double previousPosition=begin==0 ? 0 : Math.Sign(frames[begin-1].Position);
            double previousTrades=begin==0 ? 0 : frames[begin-1].Trades;
            var crossings=new List<string>();
            copy.MomentumValidation=delegate(string text,bool crossing) {momentum=text;if(crossing) crossings.Add(text);};
            for(int i=begin;i<=index;i++)
            {
                var f=frames[i];crossings.Clear();
                var orders=copy.Step(f.Time,f.High,f.Low,f.Close,Math.Sign(f.Position),f.Average,f.Trades);
                if(i==index)
                    commentary=ValidationText.Commentary(copy,f.Time,f.High,f.Low,f.Close,f.Position,f.Average,f.Trades,
                        orders,momentum,crossings,signature,previousPosition,previousTrades);
                else
                {
                    signature=ValidationText.EntrySignature(copy,orders);
                    previousPosition=Math.Sign(f.Position);previousTrades=f.Trades;
                }
            }
            return true;
        }
    }

    // Drawing lifecycle only: reads the signal's completed-bar state, never
    // calculates pivots or changes orders. Generic handles keep it SDK-independent.
    public sealed class OpenSwingLines<T> where T : class
    {
        private readonly int historyLimit;
        private readonly Func<DateTime, double, bool, T> create;
        private readonly Action<T, DateTime> finish;
        private readonly Action<T> delete;
        private readonly Queue<T> history = new Queue<T>();
        private T highLine, lowLine;
        private double highPrice, lowPrice;

        public OpenSwingLines(int historyLimit, Func<DateTime, double, bool, T> create,
                              Action<T, DateTime> finish, Action<T> delete)
        {
            if (historyLimit < -1)
                throw new ArgumentOutOfRangeException("historyLimit", "Use -1 for all history, 0 for open levels only, or a positive segment count.");
            this.historyLimit = historyLimit;
            this.create = create;
            this.finish = finish;
            this.delete = delete;
        }

        public void Update(TwinCore core, DateTime stamp)
        {
            UpdateSide(ref highLine, ref highPrice, core.HaveSwH && core.SwHOpen, core.SwH, true, stamp);
            UpdateSide(ref lowLine, ref lowPrice, core.HaveSwL && core.SwLOpen, core.SwL, false, stamp);
        }

        private void UpdateSide(ref T line, ref double price, bool open, double level, bool high, DateTime stamp)
        {
            if (line != null && (!open || price != level))
            {
                if (historyLimit == 0) delete(line);
                else
                {
                    finish(line, stamp);
                    history.Enqueue(line);
                    while (historyLimit > 0 && history.Count > historyLimit) delete(history.Dequeue());
                }
                line = null;
            }
            if (open && line == null)
            {
                line = create(stamp, level, high);
                price = level;
            }
        }

        public void Clear()
        {
            if (highLine != null) delete(highLine);
            if (lowLine != null) delete(lowLine);
            highLine = lowLine = null;
            while (history.Count > 0) delete(history.Dequeue());
        }
    }

    public sealed class TwinOrder
    {
        public readonly string Name, Entry, Action, Kind;
        public readonly double Price, Quantity;
        public TwinOrder(string name, string entry, string action, string kind, double price, double quantity)
        { Name=name; Entry=entry; Action=action; Kind=kind; Price=price; Quantity=quantity; }
    }

    // No platform dependency: one call per completed one-minute bar.
    // Exits carry their entry identity; the host binds OrderExit.FromEntry.
    public sealed class TwinCore
    {
        public bool UseBreakout = true;
        public bool UseMomentum = true;
        public double Qty = 1;
        public double BO_TargetMult = 2.0;
        public double BO_MaxStopMult = 0;
        public double BO_ATRPeriod = 14;
        public double BO_VolCap = 2.0;
        public double BO_VolLookback = 50;
        public double BO_SessionOpen = 1700;
        public double BO_SessionClose = 1600;
        public double BO_LastFill = 1530;
        public double BO_ExitTime = 1545;
        public double BO_PivotTF = 360;
        public double MO_BasisLen = 21;
        public double MO_RangeLen = 14;
        public double MO_SignalLen = 3;
        public double MO_Trigger = 100;
        public double MO_WindowStart = 840;
        public double MO_WindowEnd = 930;
        public double MO_ExitTime = 1450;
        public double MO_StopPoints = 75;
        public double MO_Warmup = 60;
        public bool MO_FullBarsOnly = true;
        public bool MO_AllowLong = true;
        public bool MO_AllowShort = true;
        public double ClockShift = 0;
        public bool DebugLog = false;
        public bool ImmediateProtection = true;
        // Only attached in chart validation mode; called before the daily gate.
        public Action<string, bool> MomentumValidation;
        public double TimeC = 0;
        public double SmNow = 0;
        public double PrevSm = -1;
        public double Bkt = 0;
        public double PrevBkt = -1;
        public double HIdx = 0;
        public double PrevHIdx = -1;
        public bool NewSess = false;
        public bool NewBkt = false;
        public bool NewCan = false;
        public double SessStartM = 0;
        public double SessEndSm = 0;
        public double FillEndSm = 0;
        public double FlatSm = 0;
        public double SHi = 0;
        public double SLo = 0;
        public double NSess = 0;
        public double VolRatio = 0;
        public double RngSum = 0;
        public double VL = 0;
        public bool BarOpen = false;
        public double B15H = 0;
        public double B15L = 0;
        public double B15C = 0;
        public double B15LastH = 0;
        public double B15LastL = 0;
        public double B15LastSm = 0;
        public bool CanOpen = false;
        public double CurH = 0;
        public double CurL = 0;
        public double NC = 0;
        public bool LateCan = false;
        public bool LateBar = false;
        public bool DoCan = false;
        public bool DoBar = false;
        public int K = 0;
        public int J = 0;
        public double PrevC15 = 0;
        public double TrN = 0;
        public double TrSum = 0;
        public double AtrV = 0;
        public double TRv = 0;
        public bool GotSwH = false;
        public bool GotSwL = false;
        public double NewSwH = 0;
        public double NewSwL = 0;
        public double SwH = 0;
        public double SwL = 0;
        public double LastSwH = 0;
        public double LastSwL = 0;
        public bool HaveSwH = false;
        public bool HaveSwL = false;
        public bool SwHOpen = false;
        public bool SwLOpen = false;
        public bool Armed = false;
        public bool OkL = false;
        public bool OkS = false;
        public double LvlL = 0;
        public double LvlS = 0;
        public double StpL = 0;
        public double StpS = 0;
        public double AtrU = 0;
        public double ArmTrades = 0;
        public double AlphaPivot = 0;
        public double AlphaOsc = 0;
        public double SStartMin = 0;
        public double SBk = 0;
        public double SPrevBk = -1;
        public DateTime SBkDate = DateTime.MinValue;
        public bool SOpen = false;
        public double SH = 0;
        public double SL_ = 0;
        public double SC = 0;
        public double SN = 0;
        public double SEndT = 0;
        public bool SNewBk = false;
        public bool SLate = false;
        public bool SDo = false;
        public double FH = 0;
        public double FL = 0;
        public double FC = 0;
        public double FN = 0;
        public double FEndT = 0;
        public double SNB = 0;
        public double SPrevC = 0;
        public double Strv = 0;
        public double SatrW = 0;
        public double SPivot = 0;
        public double SRaw = 0;
        public double SOscV = 0;
        public double SOscPrev = 0;
        public bool SHaveOsc = false;
        public bool SHavePrev = false;
        public double SSide = 0;
        public double SFire = 0;
        public bool STradedToday = false;
        public DateTime SLastDate = DateTime.MinValue;
        public bool SHalfDay = false;
        public double[] CanH = new double[7], CanL = new double[7], SessRng = new double[100];
        internal TwinCore CopyForInspection()
        {
            var copy=(TwinCore)MemberwiseClone();
            copy.CanH=(double[])CanH.Clone();copy.CanL=(double[])CanL.Clone();copy.SessRng=(double[])SessRng.Clone();
            copy.MomentumValidation=null;
            return copy;
        }
        private static double TimeToMinutes(double t) { return Math.Truncate(t / 100) * 60 + t % 100; }
        private static double MinutesToTime(double t) { t = Mod(t,1440); return Math.Truncate(t/60)*100+t%60; }
        private static double Mod(double a, double b) { return (a % b + b) % b; }
        private static double IntPortion(double a) { return Math.Truncate(a); }
        private static double AbsValue(double a) { return Math.Abs(a); }
        private static double MaxList(params double[] a) { double r=a[0]; foreach(double v in a) r=Math.Max(r,v); return r; }
        private static double MinList(params double[] a) { double r=a[0]; foreach(double v in a) r=Math.Min(r,v); return r; }
        private static int Month(DateTime d) { return d.Month; }
        private static int DayOfMonth(DateTime d) { return d.Day; }
        private static int DayOfWeek(DateTime d) { return (int)d.DayOfWeek; }
        public List<TwinOrder> Step(DateTime stamp, double High, double Low, double Close,
        double MarketPosition, double EntryPrice, double TotalTrades)
        {
            DateTime Date=stamp.Date;
            double Time=stamp.Hour*100+stamp.Minute;
            AlphaPivot=2/(MO_BasisLen+1); AlphaOsc=2/(MO_SignalLen+1);
            var orders=new List<TwinOrder>();
            if (ClockShift != 0) TimeC = MinutesToTime ( TimeToMinutes ( Time ) + ClockShift ); else TimeC = Time;
            SessStartM = TimeToMinutes ( BO_SessionOpen );
            SmNow = Mod ( TimeToMinutes ( TimeC ) - 1 - SessStartM + 2880 , 1440 );
            SessEndSm = Mod ( TimeToMinutes ( BO_SessionClose ) - SessStartM + 1440 , 1440 );
            FillEndSm = Mod ( TimeToMinutes ( BO_LastFill ) - SessStartM + 1440 , 1440 );
            FlatSm = Mod ( TimeToMinutes ( BO_ExitTime ) - SessStartM + 1440 , 1440 );
            NewSess = PrevSm < 0 || SmNow < PrevSm;
            Bkt = IntPortion ( SmNow / 15 );
            HIdx = IntPortion ( SmNow / BO_PivotTF );
            NewBkt = NewSess || Bkt != PrevBkt;
            NewCan = NewSess || HIdx != PrevHIdx;
            if (NewSess) {
                if (PrevSm >= 0 && SHi > SLo) {
                    for (J = 99; J >= 1; J--) {
                        SessRng [ J ] = SessRng [ J - 1 ];
                    }
                    SessRng [ 0 ] = SHi - SLo;
                    NSess = NSess + 1;
                    VL = MinList ( MaxList ( BO_VolLookback , 1 ) , 99 );
                    VolRatio = 0;
                    if (NSess > VL) {
                        RngSum = 0;
                        for (J = 1; J <= VL; J++) {
                            RngSum = RngSum + SessRng [ J ];
                        }
                        if (RngSum > 0) VolRatio = SessRng [ 0 ] / ( RngSum / VL );
                    }
                }
                SHi = High;
                SLo = Low;
            } else {
                SHi = MaxList ( SHi , High );
                SLo = MinList ( SLo , Low );
            }
            LateCan = NewCan && CanOpen;
            LateBar = NewBkt && BarOpen;
            for (K = 1; K <= 2; K++) {
                if (K == 1) {
                    DoCan = LateCan;
                    DoBar = LateBar;
                } else {
                    if (NewCan) {
                        CurH = High;
                        CurL = Low;
                        CanOpen = true;
                    } else {
                        CurH = MaxList ( CurH , High );
                        CurL = MinList ( CurL , Low );
                    }
                    if (NewBkt) {
                        B15H = High;
                        B15L = Low;
                        BarOpen = true;
                    } else {
                        B15H = MaxList ( B15H , High );
                        B15L = MinList ( B15L , Low );
                    }
                    B15C = Close;
                    B15LastH = High;
                    B15LastL = Low;
                    B15LastSm = SmNow;
                    if (SwHOpen && High >= SwH) SwHOpen = false;
                    if (SwLOpen && Low <= SwL) SwLOpen = false;
                    DoCan = CanOpen && ( Mod ( SmNow + 1 , BO_PivotTF ) == 0 || SmNow + 1 >= SessEndSm );
                    DoBar = BarOpen && Mod ( SmNow + 1 , 15 ) == 0;
                }
                if (DoCan) {
                    CanOpen = false;
                    for (J = 6; J >= 1; J--) {
                        CanH [ J ] = CanH [ J - 1 ];
                        CanL [ J ] = CanL [ J - 1 ];
                    }
                    CanH [ 0 ] = CurH;
                    CanL [ 0 ] = CurL;
                    NC = NC + 1;
                    if (NC >= 7) {
                        if (CanH [ 3 ] >= MaxList ( CanH [ 4 ] , CanH [ 5 ] , CanH [ 6 ] ) && CanH [ 3 ] >= MaxList ( CanH [ 0 ] , CanH [ 1 ] , CanH [ 2 ] )) {
                            GotSwH = true;
                            NewSwH = CanH [ 3 ];
                        }
                        if (CanL [ 3 ] <= MinList ( CanL [ 4 ] , CanL [ 5 ] , CanL [ 6 ] ) && CanL [ 3 ] <= MinList ( CanL [ 0 ] , CanL [ 1 ] , CanL [ 2 ] )) {
                            GotSwL = true;
                            NewSwL = CanL [ 3 ];
                        }
                    }
                }
                if (DoBar) {
                    BarOpen = false;
                    if (TrN == 0) TRv = B15H - B15L; else TRv = MaxList ( B15H , PrevC15 ) - MinList ( B15L , PrevC15 );
                    TrN = TrN + 1;
                    if (TrN <= BO_ATRPeriod) {
                        TrSum = TrSum + TRv;
                        if (TrN == BO_ATRPeriod) AtrV = TrSum / BO_ATRPeriod;
                    } else AtrV = ( AtrV * ( BO_ATRPeriod - 1 ) + TRv ) / BO_ATRPeriod;
                    PrevC15 = B15C;
                    if (GotSwH) {
                        SwH = NewSwH;
                        LastSwH = NewSwH;
                        HaveSwH = true;
                        SwHOpen = B15C < SwH && B15LastH < SwH;
                        GotSwH = false;
                    }
                    if (GotSwL) {
                        SwL = NewSwL;
                        LastSwL = NewSwL;
                        HaveSwL = true;
                        SwLOpen = B15C > SwL && B15LastL > SwL;
                        GotSwL = false;
                    }
                    Armed = false;
                    if (MarketPosition == 0 && TrN >= BO_ATRPeriod) {
                        AtrU = AtrV;
                        LvlL = SwH;
                        StpL = LastSwL;
                        LvlS = SwL;
                        StpS = LastSwH;
                        OkL = SwHOpen && HaveSwL && StpL < LvlL;
                        OkS = SwLOpen && HaveSwH && StpS > LvlS;
                        Armed = UseBreakout && ( OkL || OkS ) && B15LastSm < FillEndSm - 1;
                        if (BO_VolCap > 0 && VolRatio > BO_VolCap) Armed = false;
                        ArmTrades = TotalTrades;
                    }
                }
            }
            PrevSm = SmNow;
            PrevBkt = Bkt;
            PrevHIdx = HIdx;
            if (Date != SLastDate) {
                STradedToday = false;
                if (SLastDate != DateTime.MinValue) {
                    orders.Add(new TwinOrder("MO-LX2", "MO-L", "Sell", "close", 0, 0));
                    orders.Add(new TwinOrder("MO-SX2", "MO-S", "BuyToCover", "close", 0, 0));
                }
                SLastDate = Date;
            }
            SHalfDay = ( Month ( Date ) == 7 && DayOfMonth ( Date ) == 3 ) || ( Month ( Date ) == 12 && DayOfMonth ( Date ) == 24 ) || ( Month ( Date ) == 11 && DayOfWeek ( Date ) == 5 && DayOfMonth ( Date ) >= 23 && DayOfMonth ( Date ) <= 29 );
            SStartMin = Mod ( TimeToMinutes ( TimeC ) - 1 + 1440 , 1440 );
            SBk = IntPortion ( SStartMin / 10 );
            SNewBk = SBk != SPrevBk || Date != SBkDate;
            SLate = SNewBk && SOpen;
            SFire = 0;
            for (K = 1; K <= 2; K++) {
                if (K == 1) {
                    SDo = SLate;
                    FH = SH;
                    FL = SL_;
                    FC = SC;
                    FN = SN;
                    FEndT = SEndT;
                } else {
                    if (SNewBk) {
                        SH = High;
                        SL_ = Low;
                        SN = 1;
                        SOpen = true;
                        SBkDate = Date;
                    } else {
                        SH = MaxList ( SH , High );
                        SL_ = MinList ( SL_ , Low );
                        SN = SN + 1;
                    }
                    SC = Close;
                    SEndT = MinutesToTime ( ( SBk + 1 ) * 10 );
                    if (SBk == 143) SEndT = 0;
                    SDo = SOpen && Mod ( SStartMin + 1 , 10 ) == 0;
                    FH = SH;
                    FL = SL_;
                    FC = SC;
                    FN = SN;
                    FEndT = SEndT;
                }
                if (SDo) {
                    SOpen = false;
                    SNB = SNB + 1;
                    if (SNB == 1) {
                        Strv = FH - FL;
                        SatrW = Strv;
                        SPivot = FC;
                    } else {
                        Strv = MaxList ( FH - FL , MaxList ( AbsValue ( FH - SPrevC ) , AbsValue ( FL - SPrevC ) ) );
                        SatrW = SatrW + ( Strv - SatrW ) / MO_RangeLen;
                        SPivot = SPivot + ( FC - SPivot ) * AlphaPivot;
                    }
                    SPrevC = FC;
                    SSide = 0;
                    if (SatrW > 0) {
                        SRaw = ( FC - SPivot ) / ( 3 * SatrW ) * 100;
                        if (SHaveOsc == false) {
                            SOscV = SRaw;
                            SHaveOsc = true;
                        } else {
                            SOscPrev = SOscV;
                            SHavePrev = true;
                            SOscV = SOscV + ( SRaw - SOscV ) * AlphaOsc;
                        }
                        if (SHavePrev) {
                            if (SOscV > MO_Trigger && SOscPrev <= MO_Trigger) SSide = 1; else if (SOscV < - MO_Trigger && SOscPrev >= - MO_Trigger) SSide = - 1;
                        }
                    }
                    if (MomentumValidation != null)
                        MomentumValidation(ValidationText.Momentum(this, FN, FEndT, MarketPosition), SSide != 0);
                    if (SSide != 0 && FEndT >= MO_WindowStart && FEndT <= MO_WindowEnd && ( MO_FullBarsOnly == false || FN == 10 ) && STradedToday == false && SHalfDay == false && MarketPosition == 0 && SNB >= MO_Warmup) {
                        STradedToday = true;
                        if (UseMomentum) {
                            if (SSide == 1 && MO_AllowLong) SFire = 1;
                            if (SSide == - 1 && MO_AllowShort) SFire = - 1;
                        }
                    }
                }
            }
            SPrevBk = SBk;
            if (SFire == 1) {
                Armed = false;
                orders.Add(new TwinOrder("MO-L", null, "Buy", "market", 0, Qty));
            }
            if (SFire == - 1) {
                Armed = false;
                orders.Add(new TwinOrder("MO-S", null, "SellShort", "market", 0, Qty));
            }
            if (MarketPosition == 1) orders.Add(new TwinOrder("MO-LS", "MO-L", "Sell", "stop", EntryPrice - MO_StopPoints, 0));
            if (MarketPosition == - 1) orders.Add(new TwinOrder("MO-SS", "MO-S", "BuyToCover", "stop", EntryPrice + MO_StopPoints, 0));
            if (TimeC >= MO_ExitTime && TimeC <= 1600) {
                orders.Add(new TwinOrder("MO-LX", "MO-L", "Sell", "market", 0, 0));
                orders.Add(new TwinOrder("MO-SX", "MO-S", "BuyToCover", "market", 0, 0));
            }
            if (Armed && ( MarketPosition != 0 || TotalTrades > ArmTrades )) Armed = false;
            if (Armed && MarketPosition == 0 && SmNow + 1 < FillEndSm) {
                if (OkL) orders.Add(new TwinOrder("BO-L", null, "Buy", "stop", LvlL, Qty));
                if (OkS) orders.Add(new TwinOrder("BO-S", null, "SellShort", "stop", LvlS, Qty));
            }
            if (MarketPosition == 1) {
                if (StpL >= EntryPrice) orders.Add(new TwinOrder("BO-L0", "BO-L", "Sell", "market", 0, 0)); else {
                    if (BO_MaxStopMult > 0) orders.Add(new TwinOrder("BO-LS", "BO-L", "Sell", "stop", MaxList ( StpL , EntryPrice - BO_MaxStopMult * AtrU ), 0)); else orders.Add(new TwinOrder("BO-LS", "BO-L", "Sell", "stop", StpL, 0));
                    if (BO_TargetMult > 0) orders.Add(new TwinOrder("BO-LT", "BO-L", "Sell", "limit", EntryPrice + BO_TargetMult * AtrU, 0));
                }
            }
            if (MarketPosition == - 1) {
                if (StpS <= EntryPrice) orders.Add(new TwinOrder("BO-S0", "BO-S", "BuyToCover", "market", 0, 0)); else {
                    if (BO_MaxStopMult > 0) orders.Add(new TwinOrder("BO-SS", "BO-S", "BuyToCover", "stop", MinList ( StpS , EntryPrice + BO_MaxStopMult * AtrU ), 0)); else orders.Add(new TwinOrder("BO-SS", "BO-S", "BuyToCover", "stop", StpS, 0));
                    if (BO_TargetMult > 0) orders.Add(new TwinOrder("BO-ST", "BO-S", "BuyToCover", "limit", EntryPrice - BO_TargetMult * AtrU, 0));
                }
            }
            if (SmNow + 1 >= FlatSm && SmNow < SessEndSm) {
                orders.Add(new TwinOrder("BO-LX", "BO-L", "Sell", "close", 0, 0));
                orders.Add(new TwinOrder("BO-SX", "BO-S", "BuyToCover", "close", 0, 0));
            }
            // Session exit is emitted by the MultiCharts host through GenerateExitOnClose().
            return orders;
        }
    }
}

#if !AQ_TWIN_CORE_ONLY
namespace PowerLanguage.Strategy
{
    // Add as a SIGNAL named Twin_Continuation; Data1 1 minute, Chicago time.
    // Manual Max Bars Back = 5; IOG off; no pyramiding. See strategy guide.
    [IOGMode(IOGMode.Disabled)]
    [RecoverDrawings(false)]
    public class Twin_Continuation : SignalObject
    {
        private AlphaQuest.Twin.TwinCore core;
        private AlphaQuest.Twin.ValidationReplay validationReplay;
        private int lastProcessedBar;
        private string protectionSetup;
        private AlphaQuest.Twin.OpenSwingLines<ITrendLineObject> swingLines;
        private readonly List<string> momentumCrossings = new List<string>();
        private ITextObject validationPanel;
        private string lastMomentum, lastEntrySignature;
        private double previousValidationPosition, previousValidationTrades;
        private readonly Dictionary<string,IOrderObject> entries = new Dictionary<string,IOrderObject>();
        private readonly Dictionary<string,IOrderMarket> markets = new Dictionary<string,IOrderMarket>();
        private readonly Dictionary<string,IOrderPriced> prices = new Dictionary<string,IOrderPriced>();
        public Twin_Continuation(object ctx) : base(ctx)
        {
            UseBreakout = true;
            UseMomentum = true;
            Qty = 1;
            BO_TargetMult = 2.0;
            BO_MaxStopMult = 0;
            BO_ATRPeriod = 14;
            BO_VolCap = 2.0;
            BO_VolLookback = 50;
            BO_SessionOpen = 1700;
            BO_SessionClose = 1600;
            BO_LastFill = 1530;
            BO_ExitTime = 1545;
            BO_PivotTF = 360;
            MO_BasisLen = 21;
            MO_RangeLen = 14;
            MO_SignalLen = 3;
            MO_Trigger = 100;
            MO_WindowStart = 840;
            MO_WindowEnd = 930;
            MO_ExitTime = 1450;
            MO_StopPoints = 75;
            MO_Warmup = 60;
            MO_FullBarsOnly = true;
            MO_AllowLong = true;
            MO_AllowShort = true;
            ClockShift = 0;
            DebugLog = false;
            ImmediateProtection = true;
            ShowTradeValidation = false;
            ValidationHistoryLimit = 0;
        }
        [Input] public bool UseBreakout { get; set; }
        [Input] public bool UseMomentum { get; set; }
        [Input] public int Qty { get; set; }
        [Input] public double BO_TargetMult { get; set; }
        [Input] public double BO_MaxStopMult { get; set; }
        [Input] public int BO_ATRPeriod { get; set; }
        [Input] public double BO_VolCap { get; set; }
        [Input] public int BO_VolLookback { get; set; }
        [Input] public int BO_SessionOpen { get; set; }
        [Input] public int BO_SessionClose { get; set; }
        [Input] public int BO_LastFill { get; set; }
        [Input] public int BO_ExitTime { get; set; }
        [Input] public int BO_PivotTF { get; set; }
        [Input] public int MO_BasisLen { get; set; }
        [Input] public int MO_RangeLen { get; set; }
        [Input] public int MO_SignalLen { get; set; }
        [Input] public double MO_Trigger { get; set; }
        [Input] public int MO_WindowStart { get; set; }
        [Input] public int MO_WindowEnd { get; set; }
        [Input] public int MO_ExitTime { get; set; }
        [Input] public double MO_StopPoints { get; set; }
        [Input] public int MO_Warmup { get; set; }
        [Input] public bool MO_FullBarsOnly { get; set; }
        [Input] public bool MO_AllowLong { get; set; }
        [Input] public bool MO_AllowShort { get; set; }
        [Input] public int ClockShift { get; set; }
        [Input] public bool DebugLog { get; set; }
        [Input] public bool ImmediateProtection { get; set; }
        [Input] public bool ShowTradeValidation { get; set; }
        [Input] public int ValidationHistoryLimit { get; set; }

        protected override void Create()
        {
            markets["MO-L"] = OrderCreator.MarketNextBar(new SOrderParameters(Contracts.UserSpecified, "MO-L", EOrderAction.Buy));
            entries["MO-L"] = markets["MO-L"];
            markets["MO-S"] = OrderCreator.MarketNextBar(new SOrderParameters(Contracts.UserSpecified, "MO-S", EOrderAction.SellShort));
            entries["MO-S"] = markets["MO-S"];
            prices["BO-L"] = OrderCreator.Stop(new SOrderParameters(Contracts.UserSpecified, "BO-L", EOrderAction.Buy));
            entries["BO-L"] = prices["BO-L"];
            prices["BO-S"] = OrderCreator.Stop(new SOrderParameters(Contracts.UserSpecified, "BO-S", EOrderAction.SellShort));
            entries["BO-S"] = prices["BO-S"];
            markets["MO-LX2"] = OrderCreator.MarketThisBar(new SOrderParameters(Contracts.UserSpecified, "MO-LX2", EOrderAction.Sell, OrderExit.FromEntry(entries["MO-L"])));
            markets["MO-SX2"] = OrderCreator.MarketThisBar(new SOrderParameters(Contracts.UserSpecified, "MO-SX2", EOrderAction.BuyToCover, OrderExit.FromEntry(entries["MO-S"])));
            prices["MO-LS"] = OrderCreator.Stop(new SOrderParameters(Contracts.UserSpecified, "MO-LS", EOrderAction.Sell, OrderExit.FromEntry(entries["MO-L"])));
            prices["MO-SS"] = OrderCreator.Stop(new SOrderParameters(Contracts.UserSpecified, "MO-SS", EOrderAction.BuyToCover, OrderExit.FromEntry(entries["MO-S"])));
            markets["MO-LX"] = OrderCreator.MarketNextBar(new SOrderParameters(Contracts.UserSpecified, "MO-LX", EOrderAction.Sell, OrderExit.FromEntry(entries["MO-L"])));
            markets["MO-SX"] = OrderCreator.MarketNextBar(new SOrderParameters(Contracts.UserSpecified, "MO-SX", EOrderAction.BuyToCover, OrderExit.FromEntry(entries["MO-S"])));
            markets["BO-L0"] = OrderCreator.MarketNextBar(new SOrderParameters(Contracts.UserSpecified, "BO-L0", EOrderAction.Sell, OrderExit.FromEntry(entries["BO-L"])));
            prices["BO-LS"] = OrderCreator.Stop(new SOrderParameters(Contracts.UserSpecified, "BO-LS", EOrderAction.Sell, OrderExit.FromEntry(entries["BO-L"])));
            prices["BO-LT"] = OrderCreator.Limit(new SOrderParameters(Contracts.UserSpecified, "BO-LT", EOrderAction.Sell, OrderExit.FromEntry(entries["BO-L"])));
            markets["BO-S0"] = OrderCreator.MarketNextBar(new SOrderParameters(Contracts.UserSpecified, "BO-S0", EOrderAction.BuyToCover, OrderExit.FromEntry(entries["BO-S"])));
            prices["BO-SS"] = OrderCreator.Stop(new SOrderParameters(Contracts.UserSpecified, "BO-SS", EOrderAction.BuyToCover, OrderExit.FromEntry(entries["BO-S"])));
            prices["BO-ST"] = OrderCreator.Limit(new SOrderParameters(Contracts.UserSpecified, "BO-ST", EOrderAction.BuyToCover, OrderExit.FromEntry(entries["BO-S"])));
            markets["BO-LX"] = OrderCreator.MarketThisBar(new SOrderParameters(Contracts.UserSpecified, "BO-LX", EOrderAction.Sell, OrderExit.FromEntry(entries["BO-L"])));
            markets["BO-SX"] = OrderCreator.MarketThisBar(new SOrderParameters(Contracts.UserSpecified, "BO-SX", EOrderAction.BuyToCover, OrderExit.FromEntry(entries["BO-S"])));
        }

        private static bool ValidTime(int value)
        { return value >= 0 && value <= 2359 && value % 100 < 60; }

        protected override void StartCalc()
        {
            lastProcessedBar=-1;
            protectionSetup=null;
            validationReplay=ShowTradeValidation ? new AlphaQuest.Twin.ValidationReplay() : null;
            if(ShowTradeValidation) Output.WriteLine("Twin validation v3 StartCalc: full calculation reset.");
            if (swingLines != null) { swingLines.Clear(); swingLines = null; }
            if (validationPanel != null) { validationPanel.Delete(); validationPanel = null; }
            momentumCrossings.Clear();
            lastMomentum = "MO: awaiting a completed 10-minute bucket.";
            lastEntrySignature = "";
            previousValidationPosition = previousValidationTrades = 0;
            if (ValidationHistoryLimit < -1)
                throw new ArgumentException("ValidationHistoryLimit must be -1 (all history), 0 (open only), or a positive segment count.");
            if (Bars.Info.Resolution.Type != EResolution.Minute || Bars.Info.Resolution.Size != 1)
                throw new ArgumentException("Twin Continuation must run on a 1-minute chart.");
            if (Qty < 1 || BO_ATRPeriod < 1 || BO_VolLookback < 1 || BO_VolLookback > 99 ||
                BO_PivotTF < 1 || BO_PivotTF > 1440 || MO_BasisLen < 1 || MO_RangeLen < 1 ||
                MO_SignalLen < 1 || MO_Warmup < 1 || ClockShift < -1440 || ClockShift > 1440)
                throw new ArgumentException("Invalid quantity, lookback or clock shift; see strategy guide.");
            foreach (int value in new int[] {BO_SessionOpen, BO_SessionClose, BO_LastFill, BO_ExitTime,
                                             MO_WindowStart, MO_WindowEnd, MO_ExitTime})
                if (!ValidTime(value)) throw new ArgumentException("Session and window inputs must be HHMM.");
            foreach (double value in new double[] {BO_TargetMult, BO_MaxStopMult, BO_VolCap, MO_Trigger, MO_StopPoints})
                if (double.IsNaN(value) || double.IsInfinity(value) || value < 0)
                    throw new ArgumentException("Multipliers, trigger and stop must be finite and nonnegative.");
            if (MO_StopPoints <= 0 || BO_SessionOpen == BO_SessionClose || MO_WindowStart > MO_WindowEnd)
                throw new ArgumentException("Stop must be positive; session and momentum window must be valid.");
            core = new AlphaQuest.Twin.TwinCore();
            core.UseBreakout = UseBreakout;
            core.UseMomentum = UseMomentum;
            core.Qty = Qty;
            core.BO_TargetMult = BO_TargetMult;
            core.BO_MaxStopMult = BO_MaxStopMult;
            core.BO_ATRPeriod = BO_ATRPeriod;
            core.BO_VolCap = BO_VolCap;
            core.BO_VolLookback = BO_VolLookback;
            core.BO_SessionOpen = BO_SessionOpen;
            core.BO_SessionClose = BO_SessionClose;
            core.BO_LastFill = BO_LastFill;
            core.BO_ExitTime = BO_ExitTime;
            core.BO_PivotTF = BO_PivotTF;
            core.MO_BasisLen = MO_BasisLen;
            core.MO_RangeLen = MO_RangeLen;
            core.MO_SignalLen = MO_SignalLen;
            core.MO_Trigger = MO_Trigger;
            core.MO_WindowStart = MO_WindowStart;
            core.MO_WindowEnd = MO_WindowEnd;
            core.MO_ExitTime = MO_ExitTime;
            core.MO_StopPoints = MO_StopPoints;
            core.MO_Warmup = MO_Warmup;
            core.MO_FullBarsOnly = MO_FullBarsOnly;
            core.MO_AllowLong = MO_AllowLong;
            core.MO_AllowShort = MO_AllowShort;
            core.ClockShift = ClockShift;
            core.DebugLog = DebugLog;
            core.ImmediateProtection = ImmediateProtection;
            if (ShowTradeValidation)
            {
                swingLines = new AlphaQuest.Twin.OpenSwingLines<ITrendLineObject>(
                    ValidationHistoryLimit, CreateSwingLine, FinishSwingLine, delegate(ITrendLineObject line) { line.Delete(); });
                core.MomentumValidation = delegate(string text, bool crossing) {
                    lastMomentum = text;
                    if (crossing) momentumCrossings.Add(text);
                };
            }
        }

        private ITrendLineObject CreateSwingLine(DateTime stamp, double price, bool high)
        {
            // Begin at confirmation/activation, never at the earlier pivot candle.
            var line = DrwTrendLine.Create(new ChartPoint(stamp, price), new ChartPoint(stamp.AddMinutes(1), price));
            line.Color = high ? Color.Red : Color.Green;
            line.Size = 2;
            line.ExtLeft = false;
            line.ExtRight = true;
            return line;
        }

        private void PrepareImmediateProtection(IList<AlphaQuest.Twin.TwinOrder> orders, double position)
        {
            var plan=AlphaQuest.Twin.TwinProtectionPlan.Build(core,orders,position,protectionSetup);
            protectionSetup=plan.Setup;
            CurSpecOrdersMode=ESpecOrdersMode.PerContract;
            double pointValue=Bars.Info.BigPointValue;
            if(double.IsNaN(pointValue) || double.IsInfinity(pointValue) || pointValue<=0)
                throw new InvalidOperationException("Immediate protection requires a positive symbol BigPointValue.");
            // Reissue each completed bar while the parent is pending or held.
            // No IOG/core replay is needed for these native fill-activated exits.
            if(plan.TargetDistance.HasValue) GenerateProfitTarget(plan.TargetDistance.Value*pointValue);
            if(plan.StopDistance.HasValue) GenerateStopLoss(plan.StopDistance.Value*pointValue);
            foreach(var stop in plan.SwingStops)
                prices[stop.Name].Send(AlphaQuest.Twin.TwinProtectionPlan.StopPrice(stop.Price,
                    Bars.Info.MinMove*Bars.Info.PriceScale,stop.Action=="Sell"),Qty);
        }

        private static void FinishSwingLine(ITrendLineObject line, DateTime stamp)
        {
            line.End = new ChartPoint(stamp, line.PriceValue(stamp));
            line.ExtRight = false;
        }

        private string BuildTradeValidationCommentary(DateTime stamp, double position, IList<AlphaQuest.Twin.TwinOrder> orders)
        {
            return AlphaQuest.Twin.ValidationText.Commentary(core,stamp,Bars.High[0],Bars.Low[0],Bars.Close[0],
                StrategyInfo.MarketPosition,StrategyInfo.AvgEntryPrice,TotalTrades,orders,lastMomentum,momentumCrossings,
                lastEntrySignature,previousValidationPosition,previousValidationTrades);
        }

        private void DrawTradeValidation(DateTime stamp, double position, IList<AlphaQuest.Twin.TwinOrder> orders)
        {
            swingLines.Update(core, stamp);
            if (Bars.LastBarOnChart)
            {
                string text = AlphaQuest.Twin.ValidationText.Compact(core, stamp, StrategyInfo.MarketPosition);
                var point = new ChartPoint(stamp, Bars.High[0]);
                if (validationPanel == null) validationPanel = DrwText.Create(point, text);
                else { validationPanel.Location = point; validationPanel.Text = text; }
                validationPanel.Color = Color.Goldenrod;
                validationPanel.HStyle = ETextStyleH.Left;
                validationPanel.VStyle = ETextStyleV.Above;
            }
            lastEntrySignature = AlphaQuest.Twin.ValidationText.EntrySignature(core, orders);
            previousValidationPosition = position;
            previousValidationTrades = TotalTrades;
        }

        protected override void CalcBar()
        {
            if(ShowTradeValidation)
            {
                // Registration must execute even for an inspection-only callback.
                ExpertCommentary.WriteLine("Twin Continuation trade validation v3");
                if(Bars.CurrentBar<=lastProcessedBar)
                {
                    if(ExpertCommentary.AtCommentaryBar)
                    {
                        string saved;
                        ExpertCommentary.WriteLine("{0}",validationReplay.TryRead(Bars.CurrentBar,out saved) ? saved :
                            "No completed-bar validation record for this bar. Recalculate with ShowTradeValidation=true.");
                    }
                    return; // No live-core Step, order Send, exit generator or drawing mutation.
                }
            }
            if(Bars.CurrentBar<=lastProcessedBar || Bars.Status!=EBarState.Close) return;
            DateTime stamp = Bars.Time[0];
            double position = Math.Sign(StrategyInfo.MarketPosition);
            if (ShowTradeValidation)
            {
                validationReplay.Record(Bars.CurrentBar,core,stamp,Bars.High[0],Bars.Low[0],Bars.Close[0],
                    StrategyInfo.MarketPosition,StrategyInfo.AvgEntryPrice,TotalTrades,lastMomentum,lastEntrySignature);
                momentumCrossings.Clear();
            }
            var orders = core.Step(stamp, Bars.High[0], Bars.Low[0], Bars.Close[0],
                                   position, StrategyInfo.AvgEntryPrice, TotalTrades);
            lastProcessedBar=Bars.CurrentBar;
            if(ImmediateProtection) PrepareImmediateProtection(orders,position);
            foreach (var order in orders)
            {
                // The native fill-relative target owns BO TP in immediate mode;
                // avoid submitting a second target on subsequent held bars.
                if(ImmediateProtection && (order.Name=="BO-LT" || order.Name=="BO-ST" || order.Name=="MO-LS" || order.Name=="MO-SS")) continue;
                int quantity = order.Entry == null ? Qty : (int)Math.Abs(StrategyInfo.MarketPosition);
                if (quantity < 1) continue;
                if (order.Kind == "market" || order.Kind == "close") markets[order.Name].Send(quantity);
                else
                {
                    double price=order.Price;
                    if(ImmediateProtection && (order.Name=="BO-LS" || order.Name=="BO-SS"))
                        price=AlphaQuest.Twin.TwinProtectionPlan.StopPrice(price,Bars.Info.MinMove*Bars.Info.PriceScale,order.Action=="Sell");
                    prices[order.Name].Send(price, quantity);
                }
            }
            if (DebugLog && (core.Armed || core.SFire != 0))
                Output.WriteLine("{0:yyyy-MM-dd HH:mm} BO armed={1} L={2} S={3} ATR={4} vol={5}; MO osc={6} fire={7}",
                    stamp, core.Armed, core.LvlL, core.LvlS, core.AtrU, core.VolRatio, core.SOscV, core.SFire);
            GenerateExitOnClose();
            if (ShowTradeValidation)
            {
                if (ExpertCommentary.AtCommentaryBar)
                    ExpertCommentary.WriteLine("{0}", BuildTradeValidationCommentary(stamp, position, orders));
                DrawTradeValidation(stamp, position, orders);
            }
        }
    }
}
#endif
