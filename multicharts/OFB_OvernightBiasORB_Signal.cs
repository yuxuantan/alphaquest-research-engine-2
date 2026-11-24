using System;
using System.Collections.Generic;
using System.Drawing;
using System.Globalization;
using PowerLanguage;
using PowerLanguage.Function;

namespace PowerLanguage.Strategy
{
    [IOGMode(IOGMode.Disabled)]
    public class OFB_OvernightBiasORB_Signal : SignalObject
    {
        [Input] public string MultiAccountFollowers { get; set; }
        private AQMultiAccountRouting multiAccount;
        [Input] public int SessStart { get; set; }
        [Input] public int OREnd { get; set; }
        [Input] public int LastEntry { get; set; }
        [Input] public int FlatTime { get; set; }
        [Input] public int SessEnd { get; set; }
        [Input] public int MaxTradesPerDay { get; set; }
        [Input] public double BiasLongMin { get; set; }
        [Input] public double BiasShortMax { get; set; }
        [Input] public int ADXLen { get; set; }
        [Input] public double ADXMin { get; set; }
        [Input] public double BreakSkipMult { get; set; }
        [Input] public int BarAvgLen { get; set; }
        [Input] public double MinORx { get; set; }
        [Input] public double MaxORx { get; set; }
        [Input] public int ORMedianDays { get; set; }
        [Input] public double ATR_k { get; set; }
        [Input] public int ATR_Days { get; set; }
        [Input] public double TakeProfitRR { get; set; }
        [Input] public int NumContracts { get; set; }
        [Input] public bool showValidation { get; set; }

        private ADX adx;
        private IOrderMarket longEntry, shortEntry, longFlat, shortFlat;
        private IOrderPriced longFillStop, longFillTarget, shortFillStop, shortFillTarget;
        private IOrderPriced longStop, longTarget, shortStop, shortTarget;
        private double orHigh, orLow, sessionOpen, overnightHigh, overnightLow, openingPosition, orReference;
        private double stopPrice, targetPrice, rthHigh, rthLow, rthClose, priorRthClose, atrReference, validationORBasis;
        private bool orDone, regimeOK, rthSeen;
        private int submissions, bias, orCount, atrIndex, atrFilled, lastBar;
        private readonly double[] trueRanges = new double[200];

        private const int ValidationEventLimit = 60;
        private readonly Queue<Action> validationEventDeletes = new Queue<Action>();
        private ITextObject validationPanel;
        private int observedPosition;
        private double observedTrades;
        private string submittedOrders;

        public OFB_OvernightBiasORB_Signal(object ctx) : base(ctx)
        {
            MultiAccountFollowers = string.Empty;
            SessStart = 930; OREnd = 945; LastEntry = 1300; FlatTime = 1530; SessEnd = 1600;
            MaxTradesPerDay = 4;
            BiasLongMin = 0.67; BiasShortMax = 0.33;
            ADXLen = 16; ADXMin = 20;
            BreakSkipMult = 2.5; BarAvgLen = 20;
            MinORx = 0; MaxORx = 2; ORMedianDays = 20;
            ATR_k = 0.30; ATR_Days = 15;
            TakeProfitRR = 3; NumContracts = 1;
            showValidation = false;
        }

        protected override void Create()
        {
            multiAccount = new AQMultiAccountRouting(this);
            adx = new ADX(this);
            longEntry = OrderCreator.MarketNextBar(new SOrderParameters(Contracts.UserSpecified, "ORB_L", EOrderAction.Buy));
            shortEntry = OrderCreator.MarketNextBar(new SOrderParameters(Contracts.UserSpecified, "ORB_S", EOrderAction.SellShort));
            longFillStop = OrderCreator.Stop(Exit("L-SL-FB", EOrderAction.Sell, longEntry));
            longFillTarget = OrderCreator.Limit(Exit("L-TP-FB", EOrderAction.Sell, longEntry));
            shortFillStop = OrderCreator.Stop(Exit("S-SL-FB", EOrderAction.BuyToCover, shortEntry));
            shortFillTarget = OrderCreator.Limit(Exit("S-TP-FB", EOrderAction.BuyToCover, shortEntry));
            longStop = OrderCreator.Stop(Exit("L-SL", EOrderAction.Sell, longEntry));
            longTarget = OrderCreator.Limit(Exit("L-TP", EOrderAction.Sell, longEntry));
            shortStop = OrderCreator.Stop(Exit("S-SL", EOrderAction.BuyToCover, shortEntry));
            shortTarget = OrderCreator.Limit(Exit("S-TP", EOrderAction.BuyToCover, shortEntry));
            longFlat = OrderCreator.MarketNextBar(Exit("XL", EOrderAction.Sell, longEntry));
            shortFlat = OrderCreator.MarketNextBar(Exit("XS", EOrderAction.BuyToCover, shortEntry));
        }

        private static SOrderParameters Exit(string name, EOrderAction action, IOrderMarket entry)
        {
            // There is exactly one parent per direction. Bind the two fill-bar
            // orders to the pending market parent even as the strategy is flat.
            return new SOrderParameters(Contracts.UserSpecified, name, action, OrderExit.FromEntry(entry));
        }

        protected override void StartCalc()
        {
            while (validationEventDeletes.Count > 0) validationEventDeletes.Dequeue()();
            if (validationPanel != null) { validationPanel.Delete(); validationPanel = null; }
            observedPosition = 0;
            observedTrades = 0;
            submittedOrders = "";
            if (Bars.Info.Resolution.Type != EResolution.Minute || Bars.Info.Resolution.Size != 15)
                throw new ArgumentException("Overnight Bias ORB requires one 15-minute Globex series.");
            if (ATR_Days < 1 || ATR_Days > trueRanges.Length)
                throw new ArgumentException("ATR_Days must be between 1 and 200 (trBuf array size).");
            if (ADXLen < 1 || BarAvgLen < 1 || ORMedianDays < 1 || NumContracts < 1)
                throw new ArgumentException("Lookbacks and NumContracts must be positive.");
            adx.Length = ADXLen;
            lastBar = 0;
            Array.Clear(trueRanges, 0, trueRanges.Length);
            orCount = atrIndex = atrFilled = 0;
            stopPrice = targetPrice = priorRthClose = atrReference = orReference = 0;
            regimeOK = true;
            ResetDay(0, 999999);
        }

        private void ResetDay(double high, double low)
        {
            rthHigh = rthClose = 0;
            rthLow = 999999;
            rthSeen = false;
            orHigh = 0;
            orLow = 999999;
            orDone = false;
            submissions = bias = 0;
            sessionOpen = 0;
            openingPosition = double.NaN;
            validationORBasis = 0;
            overnightHigh = high;
            overnightLow = low;
        }

        private void RollDay(double high, double low)
        {
            if (rthSeen)
            {
                double range = rthHigh - rthLow;
                if (priorRthClose > 0)
                    range = Math.Max(range, Math.Max(Math.Abs(rthHigh - priorRthClose), Math.Abs(rthLow - priorRthClose)));
                trueRanges[atrIndex] = range;
                atrIndex = (atrIndex + 1) % ATR_Days;
                atrFilled = Math.Min(atrFilled + 1, ATR_Days);
                priorRthClose = rthClose;
            }
            atrReference = 0;
            if (atrFilled == ATR_Days)
            {
                for (int i = 0; i < ATR_Days; ++i) atrReference += trueRanges[i];
                atrReference /= ATR_Days;
            }
            ResetDay(high, low);
        }

        protected override void CalcBar()
        {
            if (multiAccount.Service(this, MultiAccountFollowers)) return;

            if (Bars.Status != EBarState.Close || Bars.CurrentBar <= lastBar) return;
            lastBar = Bars.CurrentBar;
            DateTime stamp = Bars.Time[0];
            int hhmm = 100 * stamp.Hour + stamp.Minute;
            double high = Bars.High[0], low = Bars.Low[0], close = Bars.Close[0];
            int quantity = (int)Math.Abs(StrategyInfo.MarketPosition);
            int side = Math.Sign(StrategyInfo.MarketPosition);

            if (stamp.Date != Bars.Time[1].Date)
                RollDay(high, low);
            else if (hhmm <= SessStart)
            {
                overnightHigh = Math.Max(overnightHigh, high);
                overnightLow = Math.Min(overnightLow, low);
            }
            if (hhmm > SessStart && hhmm <= SessEnd)
            {
                rthHigh = rthSeen ? Math.Max(rthHigh, high) : high;
                rthLow = rthSeen ? Math.Min(rthLow, low) : low;
                rthSeen = true;
                rthClose = close;
            }
            if (hhmm > SessStart && hhmm <= OREnd)
            {
                if (sessionOpen == 0)
                {
                    sessionOpen = Bars.Open[0];
                    if (overnightHigh > overnightLow)
                    {
                        openingPosition = (sessionOpen - overnightLow) / (overnightHigh - overnightLow);
                        bias = openingPosition >= BiasLongMin ? 1 : openingPosition <= BiasShortMax ? -1 : 9;
                    }
                }
                orHigh = Math.Max(orHigh, high);
                orLow = Math.Min(orLow, low);
            }

            bool locked = !orDone && hhmm > OREnd && orHigh > 0;
            double priorOR = orReference;
            if (locked)
            {
                orDone = true;
                double width = orHigh - orLow;
                regimeOK = orReference <= 0 || (width >= MinORx * orReference && width <= MaxORx * orReference);
                orReference = orReference == 0 ? width : orReference + (2.0 / (ORMedianDays + 1)) * (width - orReference);
                ++orCount;
                if (orCount < ORMedianDays) regimeOK = true;
            }

            double stopPoints = ATR_k * atrReference;
            double adxValue = adx[0];
            double averageRange = 0;
            for (int i = 1; i <= BarAvgLen; ++i) averageRange += Bars.High[i] - Bars.Low[i];
            averageRange /= BarAvgLen;

            bool atrOK = atrFilled >= ATR_Days && stopPoints > 0;
            bool adxOK = adxValue >= ADXMin;
            bool rangeOK = averageRange == 0 || high - low <= BreakSkipMult * averageRange;
            bool inWindow = hhmm > OREnd && hhmm <= LastEntry;
            bool capOK = submissions < MaxTradesPerDay;
            bool canWork = orDone && regimeOK && adxOK && atrOK && inWindow && side == 0 && capOK;
            bool longBreak = close > orHigh;
            bool shortBreak = !longBreak && close < orLow;
            string action = "";
            string observed = showValidation ? ObservePosition(side) : "";
            if (canWork && rangeOK && ((longBreak && bias == 1) || (shortBreak && bias == -1)))
            {
                bool isLong = longBreak;
                int sign = isLong ? 1 : -1;
                stopPrice = close - sign * stopPoints;
                targetPrice = close + sign * stopPoints * TakeProfitRR;
                (isLong ? longEntry : shortEntry).Send(NumContracts);
                (isLong ? longFillStop : shortFillStop).Send(stopPrice, NumContracts);
                (isLong ? longFillTarget : shortFillTarget).Send(targetPrice, NumContracts);
                if (multiAccount.Active)
                    multiAccount.Enter(sign, NumContracts, new AccountBracket(stopPrice, targetPrice, null, null, true));
                ++submissions;
                if (showValidation)
                    action = isLong ? "ORB_L next open + L-SL-FB/L-TP-FB" : "ORB_S next open + S-SL-FB/S-TP-FB";
            }

            if (side != 0)
            {
                bool isLong = side > 0;
                if (hhmm >= FlatTime)
                {
                    (isLong ? longFlat : shortFlat).Send(quantity);
                    if (showValidation) action = isLong ? "XL next open" : "XS next open";
                }
                else
                {
                    (isLong ? longStop : shortStop).Send(stopPrice, quantity);
                    (isLong ? longTarget : shortTarget).Send(targetPrice, quantity);
                    if (showValidation) action = isLong ? "L-SL/L-TP next bar" : "S-SL/S-TP next bar";
                }
            }
            GenerateExitOnClose();
            if (multiAccount.Active && (hhmm >= FlatTime || Bars.LastBarInSession))
                multiAccount.Flatten();

            if (showValidation)
            {
                if (locked) validationORBasis = priorOR;
                ShowBar(stamp, high, low, close, side, quantity, adxValue, averageRange, stopPoints,
                    atrOK, adxOK, rangeOK, inWindow, capOK, longBreak, shortBreak, locked, action, observed);
            }
        }

        private string ObservePosition(int side)
        {
            double trades = TotalTrades;
            string result = "";
            if (side != observedPosition || trades != observedTrades)
                result = string.Format(CultureInfo.InvariantCulture,
                    "Observed MP {0} -> {1}, closed trades +{2}, avg entry {3:G17}; prior submission: {4}. See native trade markers for fills.",
                    observedPosition, side, trades - observedTrades, StrategyInfo.AvgEntryPrice, submittedOrders);
            observedPosition = side;
            observedTrades = trades;
            return result;
        }

        private void ShowBar(DateTime stamp, double high, double low, double close, int side, int quantity,
            double adxValue, double averageRange, double stopPoints, bool atrOK, bool adxOK, bool rangeOK,
            bool inWindow, bool capOK, bool longBreak, bool shortBreak, bool locked, string action, string observed)
        {
            bool submittedEntry = action.StartsWith("ORB_", StringComparison.Ordinal);
            bool submittedFlat = action == "XL next open" || action == "XS next open";
            if (action.Length != 0)
                submittedOrders = string.Format(CultureInfo.InvariantCulture, "{0}; stop={1:G17} target={2:G17}", action, stopPrice, targetPrice);
            string prices = (submittedEntry || (side != 0 && !submittedFlat))
                ? string.Format(CultureInfo.InvariantCulture, " | stop={0:G17} target={1:G17}", stopPrice, targetPrice) : "";
            string label = string.Format(CultureInfo.InvariantCulture,
                "{0:yyyy-MM-dd HH:mm} | MP {1} ({2}) | {3}{4}\n" +
                "ON {5:F2}–{6:F2} | open {7:F2} | fraction {8:F6} (long ≥ {9}, short ≤ {10}) | bias {11}\n" +
                "OR {12:F2}–{13:F2} locked={14} | width/EMA basis {15:F2}/{16:F2} | band {17}–{18}x pass={19} (days {20}/{21})\n" +
                "close {22:F2} | L/S break {23}/{24} | in window={25} | ADX {26:F6} ≥ {27}: {28}\n" +
                "range {29:F2} ≤ {30}x prior avg {31:F6}: {32} | ATR {33:F6} ({34}/{35}) stop pts {36:F6}: {37} | cap {38} ({39}/{40})\n" +
                "Session-close exit follows chart session.",
                stamp, side, quantity, action.Length == 0 ? "No order submitted" : action, prices,
                overnightLow, overnightHigh, sessionOpen, openingPosition, BiasLongMin, BiasShortMax, bias,
                orLow, orHigh, orDone, orHigh - orLow, validationORBasis, MinORx, MaxORx, regimeOK, orCount, ORMedianDays,
                close, longBreak && orDone, shortBreak && orDone, inWindow, adxValue, ADXMin, adxOK,
                high - low, BreakSkipMult, averageRange, rangeOK, atrReference, atrFilled, ATR_Days, stopPoints, atrOK,
                capOK, submissions, MaxTradesPerDay);
            if (locked || inWindow || action.Length != 0 || observed.Length != 0)
                Output.WriteLine("{0}{1}", label, observed.Length == 0 ? "" : "\n" + observed);
            if (locked)
            {
                int minutes = Math.Max(15, (LastEntry / 100 * 60 + LastEntry % 100) - (stamp.Hour * 60 + stamp.Minute));
                DrawLevel(stamp, minutes, orHigh, Color.SteelBlue);
                DrawLevel(stamp, minutes, orLow, Color.SteelBlue);
            }
            if (submittedEntry || (side != 0 && !submittedFlat))
            {
                DrawLevel(stamp, 15, stopPrice, Color.IndianRed);
                DrawLevel(stamp, 15, targetPrice, Color.SeaGreen);
            }
            if (submittedEntry || submittedFlat || observed.Length != 0)
            {
                var marker = DrwText.Create(new ChartPoint(stamp, high), action +
                    (observed.Length == 0 ? "" : "\nMP " + side + " | closed " + observedTrades));
                marker.Color = Color.Goldenrod;
                marker.VStyle = ETextStyleV.Above;
                Keep(() => { marker.Delete(); });
            }
            if (Bars.LastBarOnChart)
            {
                var point = new ChartPoint(stamp, low);
                if (validationPanel == null) validationPanel = DrwText.Create(point, label);
                else { validationPanel.Location = point; validationPanel.Text = label; }
                validationPanel.Color = Color.Goldenrod;
                validationPanel.HStyle = ETextStyleH.Left;
                validationPanel.VStyle = ETextStyleV.Below;
            }
        }

        private void DrawLevel(DateTime start, int minutes, double price, Color color)
        {
            var line = DrwTrendLine.Create(new ChartPoint(start, price), new ChartPoint(start.AddMinutes(minutes), price));
            line.Color = color;
            line.Size = 2;
            line.ExtLeft = line.ExtRight = false;
            Keep(() => { line.Delete(); });
        }

        private void Keep(Action delete)
        {
            validationEventDeletes.Enqueue(delete);
            if (validationEventDeletes.Count > ValidationEventLimit) validationEventDeletes.Dequeue()();
        }
    }
}
