using System;
using System.Collections.Generic;
using System.Drawing;
using System.Globalization;
using PowerLanguage;
using PowerLanguage.Function;

namespace PowerLanguage.Strategy
{
    [IOGMode(IOGMode.Disabled)]
    public class OFB_Noise_Signal : SignalObject
    {
        [Input] public int LookbackDays { get; set; }
        [Input] public double VolatilityMultiplier { get; set; }
        [Input] public int EMALength { get; set; }
        [Input] public double StopLossPoints { get; set; }
        [Input] public int ContractsPerTrade { get; set; }
        [Input] public double RewardRisk { get; set; }
        [Input] public bool LongTrade { get; set; }
        [Input] public bool ShortTrade { get; set; }
        [Input] public int MaxTradesPerDay { get; set; }
        [Input] public int MaxStopsPerDay { get; set; }
        [Input] public int FirstEvalTime { get; set; }
        [Input] public int LastEntryTime { get; set; }
        [Input] public int FlatSignalTime { get; set; }
        [Input] public bool showValidation { get; set; }

        private const int SlotCount = 22, SlotCapacity = 100, DrawingLimit = 480;
        private readonly double[,] history = new double[SlotCount, SlotCapacity];
        private readonly int[] samples = new int[SlotCount];
        private readonly Queue<Action> drawingDeletes = new Queue<Action>();
        private XAverage ema;
        private IOrderMarket longEntry, shortEntry, reverseLong, reverseShort;
        private IOrderMarket longRevExit, shortRevExit, longEmaExit, shortEmaExit, flatLong, flatShort;
        private int tradesToday, stopsToday, lastBar;
        private double todayOpen, prevClose, lastTotalTrades;
        private double observedPosition, observedTotalTrades;
        private ITextObject validationPanel;

        public OFB_Noise_Signal(object ctx) : base(ctx)
        {
            LookbackDays = 20;
            VolatilityMultiplier = 1;
            EMALength = 20;
            StopLossPoints = 50;
            ContractsPerTrade = 2;
            RewardRisk = 0.5;
            LongTrade = ShortTrade = true;
            MaxTradesPerDay = 10;
            MaxStopsPerDay = 3;
            FirstEvalTime = 900;
            LastEntryTime = 1400;
            FlatSignalTime = 1430;
            showValidation = false;
        }

        protected override void Create()
        {
            ema = new XAverage(this);
            longEntry = Market("NoiseLong", EOrderAction.Buy);
            shortEntry = Market("NoiseShort", EOrderAction.SellShort);
            reverseLong = Market("RevToLong", EOrderAction.Buy);
            reverseShort = Market("RevToShort", EOrderAction.SellShort);
            longRevExit = Exit("LongRevExit", EOrderAction.Sell);
            shortRevExit = Exit("ShortRevExit", EOrderAction.BuyToCover);
            longEmaExit = Exit("LongEMAExit", EOrderAction.Sell);
            shortEmaExit = Exit("ShortEMAExit", EOrderAction.BuyToCover);
            flatLong = Exit("FlatLong1430", EOrderAction.Sell);
            flatShort = Exit("FlatShort1430", EOrderAction.BuyToCover);
        }

        private IOrderMarket Market(string name, EOrderAction action)
        {
            return OrderCreator.MarketNextBar(new SOrderParameters(Contracts.UserSpecified, name, action));
        }

        private IOrderMarket Exit(string name, EOrderAction action)
        {
            return OrderCreator.MarketNextBar(new SOrderParameters(Contracts.UserSpecified, name, action, OrderExit.Total));
        }

        protected override void StartCalc()
        {
            while (drawingDeletes.Count > 0) drawingDeletes.Dequeue()();
            if (validationPanel != null) { validationPanel.Delete(); validationPanel = null; }
            if (Bars.Info.Resolution.Type != EResolution.Minute || Bars.Info.Resolution.Size != 15)
                throw new ArgumentException("Noise requires a single close-stamped 15-minute chart series.");
            if (LookbackDays < 1 || LookbackDays > SlotCapacity || EMALength < 1)
                throw new ArgumentException("LookbackDays must be 1–100 and EMALength must be positive.");
            if (ContractsPerTrade < 0 || MaxTradesPerDay < 0 || MaxStopsPerDay < 0)
                throw new ArgumentException("Noise contract and daily limit inputs must be non-negative.");
            if (!Finite(VolatilityMultiplier) || VolatilityMultiplier < 0 ||
                !Finite(StopLossPoints) || StopLossPoints <= 0 || !Finite(RewardRisk) || RewardRisk <= 0)
                throw new ArgumentException("Noise requires a non-negative multiplier and positive stop and target distances.");
            if (!ValidTime(FirstEvalTime) || !ValidTime(LastEntryTime) || !ValidTime(FlatSignalTime))
                throw new ArgumentException("Noise time inputs must be valid chart-clock HHMM.");
            ema.Price = Bars.Close;
            ema.Length = EMALength;
            Array.Clear(history, 0, history.Length);
            Array.Clear(samples, 0, samples.Length);
            todayOpen = prevClose = lastTotalTrades = 0;
            observedPosition = observedTotalTrades = 0;
            tradesToday = stopsToday = lastBar = 0;
        }

        private static bool Finite(double value)
        {
            return !double.IsNaN(value) && !double.IsInfinity(value);
        }

        private static bool ValidTime(int hhmm)
        {
            return hhmm >= 0 && hhmm <= 2359 && hhmm % 100 < 60;
        }

        private static int Minutes(int hhmm)
        {
            return hhmm / 100 * 60 + hhmm % 100;
        }

        protected override void CalcBar()
        {
            if (Bars.Status != EBarState.Close || Bars.CurrentBar <= lastBar) return;
            lastBar = Bars.CurrentBar;

            double perContractStop = StopLossPoints * Bars.Info.BigPointValue;
            double lossThreshold = -perContractStop * ContractsPerTrade;
            if (ContractsPerTrade >= 1)
            {
                CurSpecOrdersMode = ESpecOrdersMode.PerContract;
                GenerateStopLoss(perContractStop);
                GenerateProfitTarget(perContractStop * RewardRisk);
            }

            DateTime stamp = Bars.Time[0];
            int hhmm = 100 * stamp.Hour + stamp.Minute;
            double opening = Bars.Open[0], close = Bars.Close[0];
            double totalTrades = TotalTrades;
            bool dateChanged = stamp.Date != Bars.Time[1].Date;
            if (Bars.CurrentBar == 1) lastTotalTrades = totalTrades;
            if (dateChanged)
            {
                todayOpen = opening;
                if (Bars.CurrentBar > 1) prevClose = Bars.Close[1];
                tradesToday = stopsToday = 0;
                lastTotalTrades = totalTrades;
            }

            bool countedLoss = false;
            double closedProfit = double.NaN;
            if (totalTrades > lastTotalTrades)
            {
                closedProfit = Positions[1].Profit;
                countedLoss = closedProfit <= lossThreshold;
                if (countedLoss) ++stopsToday;
                lastTotalTrades = totalTrades;
            }

            double emaValue = ema[0], average = double.NaN, move = double.NaN;
            double upper = double.NaN, lower = double.NaN, longTrail = double.NaN, shortTrail = double.NaN;
            int slot = -1, priorCount = 0, priorSubmissions = tradesToday;
            double marketPosition = StrategyInfo.MarketPosition;
            int side = Math.Sign(marketPosition), quantity = (int)Math.Abs(marketPosition);
            bool entryTime = hhmm <= LastEntryTime && hhmm < FlatSignalTime;
            bool mayEnter = ContractsPerTrade >= 1 && tradesToday < MaxTradesPerDay && stopsToday < MaxStopsPerDay;
            bool longSignal = false, shortSignal = false;
            string order = "";
            bool window = hhmm >= FirstEvalTime && hhmm <= FlatSignalTime;
            if (window && todayOpen > 0 && prevClose > 0)
            {
                slot = (Minutes(hhmm) - Minutes(FirstEvalTime)) / 15;
                if (slot >= 0 && slot < SlotCount)
                {
                    priorCount = samples[slot];
                    move = Math.Abs(close / todayOpen - 1);
                    if (priorCount >= LookbackDays)
                    {
                        double sum = 0;
                        for (int i = 0; i < LookbackDays; ++i) sum += history[slot, i];
                        average = sum / LookbackDays;
                        upper = Math.Max(todayOpen, prevClose) * (1 + average * VolatilityMultiplier);
                        lower = Math.Min(todayOpen, prevClose) * (1 - average * VolatilityMultiplier);
                        longTrail = Math.Max(upper, emaValue);
                        shortTrail = Math.Min(lower, emaValue);
                        longSignal = entryTime && LongTrade && close > upper && close > opening;
                        shortSignal = entryTime && ShortTrade && close < lower && close < opening;
                        if (hhmm < FlatSignalTime)
                            order = Submit(side, quantity, close, longTrail, shortTrail, longSignal, shortSignal, mayEnter);
                    }
                    for (int i = SlotCapacity - 1; i > 0; --i) history[slot, i] = history[slot, i - 1];
                    history[slot, 0] = move;
                    if (priorCount < SlotCapacity) ++samples[slot];
                }
            }
            if (hhmm == FlatSignalTime && side != 0)
            {
                (side > 0 ? flatLong : flatShort).Send(quantity);
                order = side > 0 ? "FlatLong1430" : "FlatShort1430";
            }
            if (showValidation)
            {
                bool observed = marketPosition != observedPosition || totalTrades != observedTotalTrades;
                string summary = window || order.Length > 0 || observed || side != 0 || Bars.LastBarOnChart
                    ? string.Format(CultureInfo.InvariantCulture,
                        "Noise {0:yyyy-MM-dd HH:mm} | slot {1} | prior samples {2}/{3} | average {4:G17} x {5:G17} | new move {6:G17}\n" +
                        "Date reset={7} | date open {8:G17} | prior close {9:G17} | candle O/C {10:G17}/{11:G17}\n" +
                        "Upper/lower {12:G17}/{13:G17} | EMA {14:G17} | L/S exit levels {15:G17}/{16:G17}\n" +
                        "Entry clock={17} | L/S signal {18}/{19} | size/caps pass={20} | submissions {21}->{22}/{23} | losses {24}/{25}\n" +
                        "Last closed P/L checked {26:G17} <= {27:G17}: {28} | Next-open submission: {29}\n" +
                        "Long/short enabled={30}/{31} | contracts={32} | Clock flat={33:D4}",
                        stamp, slot + 1, priorCount, LookbackDays, average, VolatilityMultiplier, move, dateChanged, todayOpen, prevClose,
                        opening, close, upper, lower, emaValue, longTrail, shortTrail, window && entryTime,
                        longSignal, shortSignal, mayEnter, priorSubmissions, tradesToday, MaxTradesPerDay,
                        stopsToday, MaxStopsPerDay, closedProfit, lossThreshold, countedLoss,
                        order.Length > 0 ? order : "none", LongTrade, ShortTrade, ContractsPerTrade, FlatSignalTime) : "";
                if (summary.Length > 0)
                    ShowBar(stamp, summary, order, observed, marketPosition, totalTrades, upper, lower, emaValue);
                observedPosition = marketPosition;
                observedTotalTrades = totalTrades;
            }
        }

        private string Submit(int side, int quantity, double close, double longTrail, double shortTrail,
            bool longSignal, bool shortSignal, bool mayEnter)
        {
            if (side == 0 && mayEnter && (longSignal || shortSignal))
            {
                (longSignal ? longEntry : shortEntry).Send(ContractsPerTrade);
                ++tradesToday;
                return longSignal ? "NoiseLong" : "NoiseShort";
            }
            bool opposite = side > 0 ? shortSignal : longSignal;
            if (side != 0 && opposite)
            {
                (side > 0 ? longRevExit : shortRevExit).Send(quantity);
                if (mayEnter)
                {
                    (side > 0 ? reverseShort : reverseLong).Send(ContractsPerTrade);
                    ++tradesToday;
                    return side > 0 ? "LongRevExit + RevToShort" : "ShortRevExit + RevToLong";
                }
                return side > 0 ? "LongRevExit" : "ShortRevExit";
            }
            if (side > 0 && close < longTrail)
            {
                longEmaExit.Send(quantity);
                return "LongEMAExit";
            }
            if (side < 0 && close > shortTrail)
            {
                shortEmaExit.Send(quantity);
                return "ShortEMAExit";
            }
            return "";
        }

        private void ShowBar(DateTime stamp, string summary, string order, bool observed,
            double marketPosition, double totalTrades, double upper, double lower, double emaValue)
        {
            double stop = double.NaN, target = double.NaN;
            double entryPrice = StrategyInfo.AvgEntryPrice;
            if (marketPosition != 0 && ContractsPerTrade >= 1)
            {
                int side = Math.Sign(marketPosition);
                double tick = Bars.Info.MinMove * Bars.Info.PriceScale;
                double stopTicks = (entryPrice - side * StopLossPoints) / tick;
                double targetTicks = (entryPrice + side * StopLossPoints * RewardRisk) / tick;
                stop = tick * (side > 0 ? Math.Floor(stopTicks) : Math.Ceiling(stopTicks));
                target = tick * (side > 0 ? Math.Ceiling(targetTicks) : Math.Floor(targetTicks));
                Level(stamp, stop, Color.IndianRed);
                Level(stamp, target, Color.SeaGreen);
            }
            if (Finite(upper))
            {
                Level(stamp, upper, Color.SteelBlue);
                Level(stamp, lower, Color.SteelBlue);
                Level(stamp, emaValue, Color.DarkOrange);
            }
            summary += string.Format(CultureInfo.InvariantCulture,
                "\nObserved position {0}->{1} | total closed {2}->{3} | avg entry {4:G17} | held SL/TP {5:G17}/{6:G17}" +
                "\nAttached distances {7:G17}/{8:G17} points from actual entry. See trade markers for fills.",
                observedPosition, marketPosition, observedTotalTrades, totalTrades, entryPrice, stop, target,
                StopLossPoints, StopLossPoints * RewardRisk);
            Output.WriteLine("{0}", summary);
            if (order.Length > 0 || observed)
            {
                string label = order.Length > 0 ? "Next open: " + order : "Observed position / closed trades changed";
                var marker = DrwText.Create(new ChartPoint(stamp, Bars.High[0]), label);
                marker.Color = Color.Goldenrod;
                marker.VStyle = ETextStyleV.Above;
                Keep(() => marker.Delete());
            }
            if (Bars.LastBarOnChart)
            {
                var point = new ChartPoint(stamp, Bars.Low[0]);
                if (validationPanel == null) validationPanel = DrwText.Create(point, summary);
                else { validationPanel.Location = point; validationPanel.Text = summary; }
                validationPanel.Color = Color.Goldenrod;
                validationPanel.HStyle = ETextStyleH.Left;
                validationPanel.VStyle = ETextStyleV.Below;
            }
        }

        private void Level(DateTime stamp, double price, Color color)
        {
            if (!Finite(price)) return;
            var line = DrwTrendLine.Create(new ChartPoint(stamp.AddMinutes(-15), price), new ChartPoint(stamp, price));
            line.Color = color;
            line.Size = 2;
            line.ExtLeft = line.ExtRight = false;
            Keep(() => line.Delete());
        }

        private void Keep(Action delete)
        {
            drawingDeletes.Enqueue(delete);
            if (drawingDeletes.Count > DrawingLimit) drawingDeletes.Dequeue()();
        }
    }
}
