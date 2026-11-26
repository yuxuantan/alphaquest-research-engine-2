using PowerLanguage.Function;
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Globalization;
using PowerLanguage;

namespace PowerLanguage.Strategy
{
    // Apply to Data1 NQ (or MNQ), Data2 ES. Both use one-minute, close-stamped
    // Globex bars on the Exchange (Central) clock. Use one bar of MaxBarsBack.
    [MouseEvents]
    [IOGMode(IOGMode.Disabled)]
    public class OFB_RelStrength_Signal : SignalObject
    {
        [Input] public string MultiAccountFollowers { get; set; }
        private AQMultiAccountRouting multiAccount;
        [Input] public int DecideHHMM { get; set; }
        [Input] public double ZMin { get; set; }
        [Input] public int BetaDays { get; set; }
        [Input] public double StopFrac { get; set; }
        [Input] public double TgtFrac { get; set; }
        [Input] public int AtrDays { get; set; }
        [Input] public int TradeDir { get; set; }
        [Input] public int NumContracts { get; set; }
        [Input] public int RthStartHHMM { get; set; }
        [Input] public int RthEndHHMM { get; set; }
        [Input] public int FlatHHMM { get; set; }
        [Input] public bool SkipHolidays { get; set; }
        [Input] public bool showValidation { get; set; }

        private IOrderMarket longEntry, shortEntry, longFlat, shortFlat;
        private IOrderPriced longStop, shortStop, longTarget, shortTarget;
        private readonly double[] ranges = new double[60];
        private int lastBar, barsDay, rangeWindow, rangeIndex, rangeCount, previousSide, entriesToday;
        private int samples, barsSinceAnchor;
        private bool dayOK, haveRth, lastRthOK, decided;
        private double alpha, rthHigh, rthLow, averageRange, anchorNq, anchorEs, previousEs;
        private double covariance, nqSecondMoment, esSecondMoment, beta, residualVariance;
        private double stopPrice, targetPrice;

        private const int DrawingLimit = 240;
        private const int AlignmentLogLimit = 10;
        private int alignmentLogs;
        private readonly Queue<Action> drawings = new Queue<Action>();
        private ITrendLineObject activeStopLine, activeTargetLine;
        private static readonly HashSet<int> Holidays = new HashSet<int>
        {
            1100101, 1100118, 1100215, 1100402, 1100531, 1100705, 1100906, 1101125, 1101126, 1101224,
            1110117, 1110221, 1110422, 1110530, 1110704, 1110905, 1111124, 1111125, 1111226, 1120102,
            1120116, 1120220, 1120406, 1120528, 1120703, 1120704, 1120903, 1121029, 1121030, 1121122,
            1121123, 1121224, 1121225, 1130101, 1130121, 1130218, 1130329, 1130527, 1130703, 1130704,
            1130902, 1131128, 1131129, 1131224, 1131225, 1140101, 1140120, 1140217, 1140418, 1140526,
            1140703, 1140704, 1140901, 1141127, 1141128, 1141224, 1141225, 1150101, 1150119, 1150216,
            1150403, 1150525, 1150703, 1150907, 1151126, 1151127, 1151224, 1151225, 1160101, 1160118,
            1160215, 1160325, 1160530, 1160704, 1160905, 1161124, 1161125, 1161226, 1170102, 1170116,
            1170220, 1170414, 1170529, 1170703, 1170704, 1170904, 1171123, 1171124, 1171225, 1180101,
            1180115, 1180219, 1180330, 1180528, 1180703, 1180704, 1180903, 1181122, 1181123, 1181205,
            1181224, 1181225, 1190101, 1190121, 1190218, 1190419, 1190527, 1190703, 1190704, 1190902,
            1191128, 1191129, 1191224, 1191225, 1200101, 1200120, 1200217, 1200410, 1200525, 1200703,
            1200907, 1201126, 1201127, 1201224, 1201225, 1210101, 1210118, 1210215, 1210402, 1210531,
            1210705, 1210906, 1211125, 1211126, 1211224, 1220117, 1220221, 1220415, 1220530, 1220620,
            1220704, 1220905, 1221124, 1221125, 1221226, 1230102, 1230116, 1230220, 1230407, 1230529,
            1230619, 1230703, 1230704, 1230904, 1231123, 1231124, 1231225, 1240101, 1240115, 1240219,
            1240329, 1240527, 1240619, 1240703, 1240704, 1240902, 1241128, 1241129, 1241224, 1241225,
            1250101, 1250109, 1250120, 1250217, 1250418, 1250526, 1250619, 1250703, 1250704, 1250901,
            1251127, 1251128, 1251224, 1251225, 1260101, 1260119, 1260216, 1260403, 1260525, 1260619,
            1260703, 1260907, 1261126, 1261127, 1261224, 1261225, 1270101, 1270118, 1270215, 1270326,
            1270531, 1270618, 1270705, 1270906, 1271125, 1271126, 1271224,
        };

        public OFB_RelStrength_Signal(object ctx) : base(ctx)
        {
            MultiAccountFollowers = string.Empty;
            DecideHHMM = 900;
            ZMin = 1.25;
            BetaDays = 20;
            StopFrac = 0.6;
            TgtFrac = 1.0;
            AtrDays = 20;
            TradeDir = 0;
            NumContracts = 1;
            RthStartHHMM = 830;
            RthEndHHMM = 1500;
            FlatHHMM = 1500;
            SkipHolidays = true;
            showValidation = false;
        }

        protected override void Create()
        {
            multiAccount = new AQMultiAccountRouting(this);
            longEntry = OrderCreator.MarketNextBar(new SOrderParameters(Contracts.UserSpecified, "RS.L", EOrderAction.Buy));
            shortEntry = OrderCreator.MarketNextBar(new SOrderParameters(Contracts.UserSpecified, "RS.S", EOrderAction.SellShort));
            longStop = OrderCreator.Stop(Exit("RS.LS", EOrderAction.Sell));
            shortStop = OrderCreator.Stop(Exit("RS.SS", EOrderAction.BuyToCover));
            longTarget = OrderCreator.Limit(Exit("RS.LT", EOrderAction.Sell));
            shortTarget = OrderCreator.Limit(Exit("RS.ST", EOrderAction.BuyToCover));
            longFlat = OrderCreator.MarketThisBar(Exit("RS.LF", EOrderAction.Sell));
            shortFlat = OrderCreator.MarketThisBar(Exit("RS.SF", EOrderAction.BuyToCover));
        }

        private static SOrderParameters Exit(string name, EOrderAction action)
        {
            return new SOrderParameters(Contracts.UserSpecified, name, action, OrderExit.Total);
        }

        protected override void StartCalc()
        {
            multiAccount.StartPicker(this);
            if (activeStopLine != null) activeStopLine.Delete();
            if (activeTargetLine != null) activeTargetLine.Delete();
            activeStopLine = activeTargetLine = null;
            while (drawings.Count > 0) drawings.Dequeue()();
            lastBar = rangeIndex = rangeCount = previousSide = entriesToday = samples = barsSinceAnchor = 0;
            alignmentLogs = 0;
            dayOK = decided = true;
            haveRth = lastRthOK = false;
            rthHigh = rthLow = averageRange = anchorNq = anchorEs = previousEs = 0;
            covariance = nqSecondMoment = esSecondMoment = beta = residualVariance = 0;
            stopPrice = targetPrice = 0;
            barsDay = Math.Max(Minutes(RthEndHHMM) - Minutes(RthStartHHMM), 1);
            alpha = 2.0 / ((double)BetaDays * barsDay + 1);
            rangeWindow = Math.Min(Math.Max(AtrDays, 1), 60);
        }

        private static int Minutes(int hhmm)
        {
            return hhmm / 100 * 60 + hhmm % 100;
        }

        private static int Clock(DateTime stamp)
        {
            return stamp.Hour * 100 + stamp.Minute;
        }

        private bool InRth(int hhmm)
        {
            return hhmm > RthStartHHMM && hhmm <= RthEndHHMM;
        }

        private void StartRth(double high, double low, double lastNq, double lastEs)
        {
            if (haveRth && lastRthOK)
            {
                ranges[rangeIndex] = rthHigh - rthLow;
                rangeIndex = (rangeIndex + 1) % rangeWindow;
                rangeCount = Math.Min(rangeCount + 1, rangeWindow);
            }
            if (rangeCount > 0)
            {
                double sum = 0;
                for (int i = 0; i < rangeCount; ++i) sum += ranges[i];
                averageRange = sum / rangeCount;
            }
            rthHigh = high;
            rthLow = low;
            haveRth = true;
            lastRthOK = dayOK;
            anchorNq = lastNq;
            anchorEs = lastEs;
            barsSinceAnchor = 0;
            decided = false;
        }

        private void UpdateMoments(double nq, double es, double lastNq, double lastEs)
        {
            double retNq = 10000 * Math.Log(nq / lastNq);
            double retEs = 10000 * Math.Log(es / lastEs);
            double cross = retNq * retEs, nqSq = retNq * retNq, esSq = retEs * retEs;
            if (samples == 0)
            {
                covariance = cross;
                nqSecondMoment = nqSq;
                esSecondMoment = esSq;
            }
            else
            {
                covariance += alpha * (cross - covariance);
                nqSecondMoment += alpha * (nqSq - nqSecondMoment);
                esSecondMoment += alpha * (esSq - esSecondMoment);
            }
            ++samples;
            if (nqSecondMoment > 0 && esSecondMoment > 0)
            {
                beta = covariance / esSecondMoment;
                residualVariance = nqSecondMoment - 2 * beta * covariance + (beta * beta) * esSecondMoment;
            }
        }

        protected override void OnMouseEvent(MouseClickArgs args)
        {
            if (!multiAccount.OpenPicker(args)) base.OnMouseEvent(args);
        }

        protected override void CalcBar()
        {
            if (multiAccount.Service(this, MultiAccountFollowers)) return;

            if (Bars.Status != EBarState.Close || Bars.CurrentBar <= lastBar) return;
            var esBars = BarsOfData(2);
            DateTime stamp = Bars.Time[0], previousStamp = Bars.Time[1];
            bool first = lastBar == 0;
            if (first && (esBars == null || Bars.Info.Resolution.Type != EResolution.Minute ||
                esBars.Info.Resolution.Type != EResolution.Minute || Bars.Info.Resolution.Size != 1 ||
                esBars.Info.Resolution.Size != 1))
                throw new InvalidOperationException("Relative Strength requires synchronized one-minute NQ/MNQ Data1 and ES Data2.");

            // Read the secondary close exposed by the chart as of this Data1 bar.
            // C2[1] is the preceding Data1 calculation's C2, even when Data2 repeats.
            DateTime exposedEsStamp = esBars.Time[0];
            DateTime? usedEsStamp = null;
            double es = 0, lastEs = previousEs;
            if (exposedEsStamp <= stamp)
            {
                usedEsStamp = exposedEsStamp;
                es = esBars.Close[0];
            }
            else if (esBars.Time[1] <= stamp)
            {
                usedEsStamp = esBars.Time[1];
                es = esBars.Close[1];
            }
            bool newDate = stamp.Date != previousStamp.Date;
            if (first || newDate)
            {
                entriesToday = 0;
                int dateCode = (stamp.Year - 1900) * 10000 + stamp.Month * 100 + stamp.Day;
                dayOK = !SkipHolidays || !Holidays.Contains(dateCode);
            }
            lastBar = Bars.CurrentBar;
            previousEs = es;

            int hhmm = Clock(stamp);
            bool rth = InRth(hhmm);
            double nq = Bars.Close[0], lastNq = Bars.Close[1], high = Bars.High[0], low = Bars.Low[0];
            int side = Math.Sign(StrategyInfo.MarketPosition);
            int qty = (int)Math.Abs(StrategyInfo.MarketPosition);
            bool changed = side != previousSide;
            double entryPrice = StrategyInfo.AvgEntryPrice;
            if (side != 0 && changed)
            {
                ++entriesToday;
                stopPrice = entryPrice - side * StopFrac * averageRange;
                targetPrice = entryPrice + side * TgtFrac * averageRange;
            }

            if (rth && (newDate || !InRth(Clock(previousStamp)))) StartRth(high, low, lastNq, lastEs);
            else if (rth)
            {
                rthHigh = Math.Max(rthHigh, high);
                rthLow = Math.Min(rthLow, low);
            }
            if (rth && anchorNq > 0) ++barsSinceAnchor;
            if (rth && dayOK && lastNq > 0 && lastEs > 0 && es > 0) UpdateMoments(nq, es, lastNq, lastEs);

            int signal = 0;
            double residual = double.NaN, z = double.NaN;
            bool decision = rth && !decided && hhmm >= DecideHHMM;
            if (decision)
            {
                decided = true;
                if (dayOK && barsSinceAnchor >= 1 && samples >= 5 * barsDay &&
                    residualVariance > 0 && anchorNq > 0 && anchorEs > 0 && es > 0)
                {
                    residual = 10000 * Math.Log(nq / anchorNq) - beta * 10000 * Math.Log(es / anchorEs);
                    z = residual / Math.Sqrt(residualVariance * barsSinceAnchor);
                    if (z >= ZMin) signal = 1;
                    if (z <= -ZMin) signal = -1;
                }
            }

            int submitted = 0;
            if (signal != 0 && side == 0 && entriesToday == 0 && hhmm < FlatHHMM)
            {
                if (signal == 1 && TradeDir >= 0) { longEntry.Send(NumContracts); submitted = 1; }
                if (signal == -1 && TradeDir <= 0) { shortEntry.Send(NumContracts); submitted = -1; }
            }
            if (submitted != 0 && multiAccount.Active)
            {
                double? stopDistance = StopFrac > 0 && averageRange > 0 ? (double?)(StopFrac * averageRange) : null;
                double? targetDistance = TgtFrac > 0 && averageRange > 0 ? (double?)(TgtFrac * averageRange) : null;
                multiAccount.Enter(submitted, NumContracts, new AccountBracket(null, null, stopDistance, targetDistance, false));
            }

            bool sendStop = side != 0 && StopFrac > 0 && averageRange > 0;
            bool sendTarget = side != 0 && TgtFrac > 0 && averageRange > 0;
            bool flatten = side != 0 && (hhmm >= FlatHHMM || hhmm <= RthStartHHMM);
            if (sendStop) (side == 1 ? longStop : shortStop).Send(stopPrice, qty);
            if (sendTarget) (side == 1 ? longTarget : shortTarget).Send(targetPrice, qty);
            if (flatten) (side == 1 ? longFlat : shortFlat).Send(qty);
            if (multiAccount.Active && (hhmm >= FlatHHMM || hhmm <= RthStartHHMM))
                multiAccount.Flatten();

            if (showValidation)
            {
                if (exposedEsStamp != stamp && alignmentLogs < AlignmentLogLimit)
                {
                    ++alignmentLogs;
                    Output.WriteLine("Relative Strength Data2 alignment | Data1={0:yyyy-MM-dd HH:mm:ss} | " +
                        "Data2 exposed={1:yyyy-MM-dd HH:mm:ss} | ES used={2} | Close={3:G17}",
                        stamp, exposedEsStamp, FormatStamp(usedEsStamp), es);
                }
                if (decision)
                    ShowDecision(stamp, high, nq, es, usedEsStamp, side, residual, z, signal, submitted);
                if (changed || flatten) ShowExit(stamp, low, side, qty, entryPrice, sendStop, sendTarget, flatten);
                UpdateExitLine(ref activeStopLine, stamp, stopPrice, Color.IndianRed, sendStop && !flatten, changed);
                UpdateExitLine(ref activeTargetLine, stamp, targetPrice, Color.SeaGreen, sendTarget && !flatten, changed);
            }
            previousSide = side;
        }

        private static string FormatStamp(DateTime? stamp)
        {
            return stamp.HasValue ? stamp.Value.ToString("yyyy-MM-dd HH:mm:ss", CultureInfo.InvariantCulture) : "unavailable";
        }

        private void ShowDecision(DateTime stamp, double high, double nq, double es, DateTime? usedEsStamp, int side,
            double residual, double z, int signal, int submitted)
        {
            string action = submitted == 1 ? "RS.L next open" : submitted == -1 ? "RS.S next open" : "No entry submitted";
            Output.WriteLine(
                "{0:yyyy-MM-dd HH:mm} CT | {1} | calendar eligible={2} | samples={3}/{4} | in RTH bars={5}\n" +
                "NQ close/anchor={6:G17}/{7:G17} | ES close/anchor={8:G17}/{9:G17} | beta={10:G17} | " +
                "residual variance={11:G17} | residual bp={12:G17} | Z={13:G17} | threshold={14:G17}\n" +
                "signal={15} | TradeDir={16} | MP={17} | filled today={18} | before flat cutoff={19} | " +
                "entry qty={20} | avg RTH range={21:G17} ({22} days) | ES used={23}",
                stamp, action, dayOK, samples, 5 * barsDay, barsSinceAnchor, nq, anchorNq, es, anchorEs,
                beta, residualVariance, residual, z, ZMin, signal, TradeDir, side, entriesToday,
                Clock(stamp) < FlatHHMM, NumContracts, averageRange, rangeCount, FormatStamp(usedEsStamp));
            Marker(stamp, high, string.Format(CultureInfo.InvariantCulture,
                "{0}\nZ {1:F3} / ±{2:G} | β {3:F3}\nClean {4} | Samples {5}/{6}",
                action, z, ZMin, beta, dayOK, samples, 5 * barsDay), ETextStyleV.Above);
        }

        private void ShowExit(DateTime stamp, double low, int side, int qty, double entryPrice,
            bool sendStop, bool sendTarget, bool flatten)
        {
            string stop = sendStop ? (side == 1 ? "RS.LS " : "RS.SS ") + stopPrice.ToString("G17", CultureInfo.InvariantCulture) : "off";
            string target = sendTarget ? (side == 1 ? "RS.LT " : "RS.ST ") + targetPrice.ToString("G17", CultureInfo.InvariantCulture) : "off";
            string flat = !flatten ? "none" : side == 1 ? "RS.LF this close" : "RS.SF this close";
            Output.WriteLine(
                "{0:yyyy-MM-dd HH:mm} CT | Observed MP {1} -> {2} | qty={3} | avg entry={4:G17} | " +
                "avg RTH range={5:G17} | StopFrac={6:G17} | TgtFrac={7:G17} | next-bar stop={8} | target={9} | flat={10} | " +
                "FlatHHMM={11} | RthStartHHMM={12}. See native markers for fills.",
                stamp, previousSide, side, qty, entryPrice, averageRange, StopFrac, TgtFrac, stop, target,
                flat, FlatHHMM, RthStartHHMM);
            Marker(stamp, low, string.Format(CultureInfo.InvariantCulture,
                "Observed MP {0} → {1}\nNext bar: stop {2} | target {3}\nFlat submission: {4}",
                previousSide, side, stop, target, flat), ETextStyleV.Below);
        }

        private void Marker(DateTime stamp, double price, string text, ETextStyleV style)
        {
            var label = DrwText.Create(new ChartPoint(stamp, price), text);
            label.Color = Color.Goldenrod;
            label.VStyle = style;
            Keep(() => { label.Delete(); });
        }

        private void UpdateExitLine(ref ITrendLineObject active, DateTime stamp, double price, Color color,
            bool working, bool positionChanged)
        {
            if (active != null && (!working || positionChanged))
            {
                var finished = active;
                finished.End = new ChartPoint(stamp, finished.PriceValue(stamp));
                finished.ExtRight = false;
                active = null;
                Keep(() => { finished.Delete(); });
            }
            if (!working || active != null) return;
            active = DrwTrendLine.Create(new ChartPoint(stamp, price), new ChartPoint(stamp.AddMinutes(1), price));
            active.Color = color;
            active.Size = 2;
            active.ExtLeft = false;
            active.ExtRight = true;
        }

        private void Keep(Action delete)
        {
            drawings.Enqueue(delete);
            if (drawings.Count > DrawingLimit) drawings.Dequeue()();
        }
    }
}
