using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using AlphaQuest.MarketCalendars;
#if !AQ_CALENDAR_ONLY
using PowerLanguage;

namespace PowerLanguage.Strategy
{
    // Active calendar-based port. Chart must use America/Chicago exchange time.
    // The original supplied C# is retained under multicharts/reference/.
    // Calendar-enabled defaults require NQ, Central-time 1-minute bars, full session.
    // VWAP uses Bars.Ticks, matching the original Ticks expression.
    // Stops/targets are submitted only once a position is observed, as in source.
    [IOGMode(IOGMode.Disabled)]
    public class ORB_VWAP_CONT__NQ_1M_PIVOT_V01 : SignalObject
    {
        private PowerLanguage.Function.ADX _adx;
        private IOrderMarket _longEntry, _shortEntry, _longFlat, _shortFlat;
        private IOrderPriced _longStop, _longTarget, _shortStop, _shortTarget;

        private bool _firstBar;
        private bool _prevInORB, _prevInVwap;
        private bool _prevLongLatched, _prevShortLatched;
        private bool _orbReady;
        private double _orbHigh, _orbLow;
        private double _cumPV, _cumVol, _nyVwap;
        private double _lastStopHigh, _lastStopLow;
        private double _lastTargetHigh, _lastTargetLow;
        private bool _hasStopHigh, _hasStopLow;
        private bool _hasTargetHigh, _hasTargetLow;
        private bool _longOrbBroken, _shortOrbBroken;
        private bool _longTouched, _shortTouched;
        private bool _longClosedThrough, _shortClosedThrough;
        private double _pullbackLow, _pullbackHigh;
        private double _activeStop, _activeTarget;
        private double _tickSize, _pointValue, _riskDollars;
        private int _tradesToday;
        private NqSessionCalendar _calendar;
        private NqSessionPlan _sessionPlan;
        private DateTime? _pendingEntrySession, _holdingSession;
        private double _previousPosition;

        public ORB_VWAP_CONT__NQ_1M_PIVOT_V01(object ctx) : base(ctx)
        {
            UseVolSizing = false;
            PositionSize = 1;
            MM_Capital_USD = 500000;
            MM_Risk_Pct = 2.0;
            Max_Contracts = 1;
            TradeLongs = true;
            TradeShorts = false;
            MinRR = 0;
            MaxStopPoints = 0;
            UseADXElev = true;
            ADXElev_Thr = 20;
            UseADXDecay = true;
            ADXDecay_LB = 1;
            ADX_Len = 14;
            RetestMode = 1;
            StopMode = 1;
            MaxTradesPerDay = 1;
            StopSwingLen = 20;
            TargetSwingLen = 5;
            BufferMode = 2;
            BufferAmount = 0;
            ORStartTime = 830;
            OREndTime = 900;
            VwapStartTime = 830;
            VwapEndTime = 1700;
            EntryStartTime = 900;
            EntryEndTime = 1700;
            DayResetTime = 2300;
            UseEODFlat = true;
            EODFlatTime = 1555;
            PlotTradeLevels = true;
            SessionCalendarDirectory = @"C:\AlphaQuest\calendars";
            CloseBufferMinutes = 5;
        }

        [Input] public bool UseVolSizing { get; set; }
        [Input] public int PositionSize { get; set; }
        [Input] public double MM_Capital_USD { get; set; }
        [Input] public double MM_Risk_Pct { get; set; }
        [Input] public int Max_Contracts { get; set; }
        [Input] public bool TradeLongs { get; set; }
        [Input] public bool TradeShorts { get; set; }
        [Input] public double MinRR { get; set; }
        [Input] public double MaxStopPoints { get; set; }
        [Input] public bool UseADXElev { get; set; }
        [Input] public double ADXElev_Thr { get; set; }
        [Input] public bool UseADXDecay { get; set; }
        [Input] public int ADXDecay_LB { get; set; }
        [Input] public int ADX_Len { get; set; }
        [Input] public int RetestMode { get; set; }
        [Input] public int StopMode { get; set; }
        [Input] public int MaxTradesPerDay { get; set; }
        [Input] public int StopSwingLen { get; set; }
        [Input] public int TargetSwingLen { get; set; }
        [Input] public int BufferMode { get; set; }
        [Input] public double BufferAmount { get; set; }
        [Input] public int ORStartTime { get; set; }
        [Input] public int OREndTime { get; set; }
        [Input] public int VwapStartTime { get; set; }
        [Input] public int VwapEndTime { get; set; }
        [Input] public int EntryStartTime { get; set; }
        [Input] public int EntryEndTime { get; set; }
        [Input] public int DayResetTime { get; set; }
        [Input] public bool UseEODFlat { get; set; }
        [Input] public int EODFlatTime { get; set; }
        [Input] public bool PlotTradeLevels { get; set; }
        [Input] public string SessionCalendarDirectory { get; set; }
        [Input] public int CloseBufferMinutes { get; set; }

        protected override void Create()
        {
            _adx = new PowerLanguage.Function.ADX(this);

            _longEntry = OrderCreator.MarketNextBar(new SOrderParameters(
                Contracts.UserSpecified, "Long", EOrderAction.Buy));
            _shortEntry = OrderCreator.MarketNextBar(new SOrderParameters(
                Contracts.UserSpecified, "Short", EOrderAction.SellShort));

            _longStop = OrderCreator.Stop(new SOrderParameters(
                Contracts.UserSpecified, "Long SL", EOrderAction.Sell, OrderExit.Total));
            _longTarget = OrderCreator.Limit(new SOrderParameters(
                Contracts.UserSpecified, "Long TP", EOrderAction.Sell, OrderExit.Total));
            _shortStop = OrderCreator.Stop(new SOrderParameters(
                Contracts.UserSpecified, "Short SL", EOrderAction.BuyToCover, OrderExit.Total));
            _shortTarget = OrderCreator.Limit(new SOrderParameters(
                Contracts.UserSpecified, "Short TP", EOrderAction.BuyToCover, OrderExit.Total));

            _longFlat = OrderCreator.MarketNextBar(new SOrderParameters(
                Contracts.UserSpecified, "EOD.L", EOrderAction.Sell, OrderExit.Total));
            _shortFlat = OrderCreator.MarketNextBar(new SOrderParameters(
                Contracts.UserSpecified, "EOD.S", EOrderAction.BuyToCover, OrderExit.Total));
        }

        protected override void StartCalc()
        {
            if (ADX_Len < 1 || ADXDecay_LB < 0 ||
                StopSwingLen < 1 || TargetSwingLen < 1)
                throw new ArgumentException("Lengths must be positive; ADXDecay_LB must be >= 0.");
            if ((RetestMode != 1 && RetestMode != 2) ||
                (StopMode != 1 && StopMode != 2) ||
                (BufferMode != 1 && BufferMode != 2))
                throw new ArgumentException("RetestMode, StopMode and BufferMode must be 1 or 2.");

            if (EODFlatTime < 0 || EODFlatTime > 2359 || EODFlatTime % 100 >= 60)
                throw new ArgumentException("EODFlatTime must be a valid Chicago HHMM time.");
            NqSessionCalendar.ValidateCloseBuffer(CloseBufferMinutes);
            string calendarFile = UseEODFlat ? NqSessionCalendar.ResolveCalendarFile(Bars.Info.Name, SessionCalendarDirectory) : null;
            _calendar = UseEODFlat ? NqSessionCalendar.Load(calendarFile) : null;
            _sessionPlan = null;
            _pendingEntrySession = _holdingSession = null;
            _previousPosition = 0;
            if (_calendar != null)
                Output.WriteLine("Auto NQ CSV calendar for {0}: {1}; buffer={2} minutes; {3} through {4}; SHA256={5}; no price-bar lookahead.",
                    Bars.Info.Name, calendarFile, CloseBufferMinutes,
                    _calendar.CoverageStart.ToString("yyyy-MM-dd"),
                    _calendar.CoverageEnd.ToString("yyyy-MM-dd"), _calendar.Sha256);
            _adx.Length = ADX_Len;

            // .NET PriceScale is fractional (e.g. 0.01): MULTIPLY.
            // Do not copy the PowerLanguage MinMove / PriceScale expression.
            _tickSize = Bars.Info.MinMove * Bars.Info.PriceScale;
            _pointValue = Bars.Info.BigPointValue;
            _riskDollars = MM_Capital_USD * MM_Risk_Pct / 100.0;
            if (_tickSize <= 0 || double.IsNaN(_tickSize) || double.IsInfinity(_tickSize))
                throw new ArgumentException("Invalid instrument tick-size settings.");
            if (UseVolSizing && (_pointValue <= 0 ||
                double.IsNaN(_pointValue) || double.IsInfinity(_pointValue)))
                throw new ArgumentException("Invalid instrument BigPointValue for risk sizing.");

            _firstBar = true;
            _prevInORB = _prevInVwap = false;
            _prevLongLatched = _prevShortLatched = false;
            _orbReady = false;
            _orbHigh = _orbLow = 0;
            _cumPV = _cumVol = _nyVwap = 0;
            _lastStopHigh = _lastStopLow = 0;
            _lastTargetHigh = _lastTargetLow = 0;
            _hasStopHigh = _hasStopLow = false;
            _hasTargetHigh = _hasTargetLow = false;
            _pullbackLow = _pullbackHigh = 0;
            _activeStop = _activeTarget = 0;
            _tradesToday = 0;
            ClearLatches();

            if (PlotTradeLevels)
                Output.WriteLine("VWAP Pullback: tickSize={0}, BigPointValue={1}, riskBudget={2:F2}",
                    _tickSize, _pointValue, _riskDollars);
        }

        protected override void CalcBar()
        {
            // Evaluate once on completed bars; orders apply to the next bar.
            if (Bars.Status != EBarState.Close)
                return;

            DateTime stamp = DateTime.SpecifyKind(Bars.Time[0], DateTimeKind.Unspecified);
            double position = StrategyInfo.MarketPosition;
            if (UseEODFlat)
            {
                _sessionPlan = _calendar.Plan(NqSessionCalendar.SessionDate(stamp), EODFlatTime, CloseBufferMinutes);
                // MC has already processed this bar's orders before CalcBar.
                // Reject late exits even if a pending bracket made us flat.
                if (_previousPosition != 0 && _holdingSession.HasValue)
                {
                    NqSessionPlan previousPlan = _calendar.Plan(_holdingSession.Value, EODFlatTime, CloseBufferMinutes);
                    if (!previousPlan.ScheduledClose.HasValue || stamp > previousPlan.ScheduledClose.Value)
                        throw new InvalidOperationException("A held position crossed the scheduled NQ close without an observed timely fill; reject this incomplete-source MC backtest.");
                }
                if (position != 0)
                {
                    if (_previousPosition == 0)
                    {
                        if (!_pendingEntrySession.HasValue)
                            throw new InvalidOperationException("Calendar cannot establish the origin of an assigned position; start this strategy flat.");
                        _holdingSession = _pendingEntrySession;
                        NqSessionPlan entryPlan = _calendar.Plan(_holdingSession.Value, EODFlatTime, CloseBufferMinutes);
                        if (!entryPlan.AllowsFill(stamp))
                            throw new InvalidOperationException("Entry filled at/after cutoff or in a later session. Incomplete bars are incompatible; this MC backtest is not qualified.");
                    }
                    NqSessionPlan holdingPlan = _calendar.Plan(_holdingSession.Value, EODFlatTime, CloseBufferMinutes);
                    if (!holdingPlan.ScheduledClose.HasValue || stamp > holdingPlan.ScheduledClose.Value)
                        throw new InvalidOperationException("No observed liquidation price before scheduled NQ close. Do not accept an evening exit as timely flattening.");
                }
            }
            int time = stamp.Hour * 100 + stamp.Minute; // this is how the signal gets the current time
            double high = Bars.High[0];
            double low = Bars.Low[0];
            double close = Bars.Close[0];
            double buffer = BufferMode == 1 ? BufferAmount * _tickSize : BufferAmount;
            double typicalPrice = (high + low + close) / 3.0;
            double barVolume = Bars.Ticks[0];
            if (barVolume <= 0) barVolume = 1;

            // Use the built-in ADX, including its historical values.
            double adxValue = _adx[0];
            bool elevOK = !UseADXElev || adxValue >= ADXElev_Thr; // adx higher than adx elevated threshold = 20
            bool decayOK = !UseADXDecay || adxValue <= _adx[ADXDecay_LB]; // adx now less than previous bar adx for ADXDecay_LB = 1
            bool adxOK = elevOK && decayOK;

            bool inORB = time > ORStartTime && time <= OREndTime; // if in ORB time - update orb values
            bool inVwap = time > VwapStartTime && time <= VwapEndTime; // if in vwap time - update vwap values
            bool inEntry = time > EntryStartTime && time <= EntryEndTime; // if in entry time - allow enter

            // Exact reset condition from the source, including strict >.
            bool newNyDay = _firstBar; //for first time init first bar is true. 
            if (!_firstBar)// if not first bar, check if its new day by comparing with prev bar
            {
                DateTime previousStamp = Bars.Time[1];
                int previousTime = previousStamp.Hour * 100 + previousStamp.Minute;
                newNyDay = time > DayResetTime && previousTime <= DayResetTime; // day reset time is 2300 CT - this correspond to 12mn EST. this shows new day
            }
            if (newNyDay)//if new day ie past 2300 CT, then reset- dont allow entries anymore
            {
                _tradesToday = 0;
                _orbReady = false;
                ClearLatches();
            }
            
            // *** ORB time = 830-9 ***
            if (inORB && !_prevInORB) // if just got into the orb time, update orb time
            {
                _orbHigh = high;
                _orbLow = low;
                _orbReady = false;
            }
            if (inORB) // if in the orb time, update the max and min
            {
                _orbHigh = Math.Max(_orbHigh, high);
                _orbLow = Math.Min(_orbLow, low);
            }
            if (!inORB && _prevInORB) _orbReady = true; // orb is ready!
            
            // *** vwap time = 830-1700 ie us open, till end of day ***
            if (inVwap && !_prevInVwap)  // if just got into vwap time (, init
            {
                _cumPV = typicalPrice * barVolume; // this is estimated based on bar close, no trades data used at all
                _cumVol = barVolume;
            }
            else if (inVwap) // if already in vwap, add on to the cum PV and cum vol
            {
                _cumPV += typicalPrice * barVolume;
                _cumVol += barVolume;
            }
            bool vwapValid = inVwap && _cumVol > 0; 
            if (vwapValid) _nyVwap = _cumPV / _cumVol; // update the vwap based on the cum PV and cumv

            UpdatePivots();

            bool canTrackBreak = _orbReady && !inORB; //if im not in orb time, and orb is ready ie finished orb calculation, then can track break
            if (canTrackBreak && close > _orbHigh) _longOrbBroken = true; // if orb broken then set true and stay true until close
            if (canTrackBreak && close < _orbLow) _shortOrbBroken = true;

            bool canEnter = canTrackBreak && inVwap && inEntry && vwapValid;//can enter doesnt mean orb broken. later check
            bool longSignal = false; // reset signal to false every bar
            bool shortSignal = false;
            if (canEnter && _longOrbBroken)
            {
                if (RetestMode == 1)
                {
                    // if long orb broken, and current closed bar low is lower than vwap, and close is higher than vwap
                    if (low <= _nyVwap) _longTouched = true; // long touched is stateful. 
                    //only when clear latches is run will this be set to false. only clear when NEW day or trade just entered.
                    longSignal = _longTouched && close > _nyVwap;// so as long as price went under vwap, and now above its a signal
                }
                else
                {
                    // if long orb broken, and current close lower than vwap, then how can it check for close > vwap?. both cannot be true. 
                    // do the same for short side
                    if (close < _nyVwap) _longClosedThrough = true; // long closed through is stateful
                    longSignal = _longClosedThrough && close > _nyVwap; // so long as a bar closed under vwap, and now a bar close above vwap
                }
            }
            if (canEnter && _shortOrbBroken)
            {
                if (RetestMode == 1)
                {
                    if (high >= _nyVwap) _shortTouched = true;
                    shortSignal = _shortTouched && close < _nyVwap;
                }
                else
                {
                    if (close > _nyVwap) _shortClosedThrough = true;
                    shortSignal = _shortClosedThrough && close < _nyVwap;
                }
            }

            bool longLatched = _longTouched || _longClosedThrough; // touched or closed through then its latched.
            bool shortLatched = _shortTouched || _shortClosedThrough;
            if (longLatched && !_prevLongLatched) _pullbackLow = low; // find the most extreme after long latched
            else if (longLatched && low < _pullbackLow) _pullbackLow = low;
            if (shortLatched && !_prevShortLatched) _pullbackHigh = high; 
            else if (shortLatched && high > _pullbackHigh) _pullbackHigh = high;

            double longStop = (StopMode == 2 ? _pullbackLow : _lastStopLow) - buffer; // if stop mode 2, use extreme with buffer
            double shortStop = (StopMode == 2 ? _pullbackHigh : _lastStopHigh) + buffer;
            double longTarget = _lastTargetHigh;
            double shortTarget = _lastTargetLow;
            double longDistance = close - longStop;
            double shortDistance = shortStop - close;

            bool validLong = (StopMode == 2 || _hasStopLow) && _hasTargetHigh
                && (StopMode == 1 || longLatched)
                && longDistance > 0 && longTarget > close
                && (MaxStopPoints == 0 || longDistance <= MaxStopPoints)
                && (MinRR == 0 || (longTarget - close) / longDistance >= MinRR);
            bool validShort = (StopMode == 2 || _hasStopHigh) && _hasTargetLow
                && (StopMode == 1 || shortLatched)
                && shortDistance > 0 && shortTarget < close
                && (MaxStopPoints == 0 || shortDistance <= MaxStopPoints)
                && (MinRR == 0 || (close - shortTarget) / shortDistance >= MinRR);

            bool entryAllowed = !UseEODFlat || _sessionPlan.AllowsEntrySignal(stamp);
            if (position == 0 && entryAllowed && _tradesToday < MaxTradesPerDay)
            {
                if (longSignal && validLong && TradeLongs && adxOK)
                {
                    int quantity = GetQuantity(longDistance);
                    if (quantity >= 1)
                    {
                        _activeStop = longStop;
                        _activeTarget = longTarget;
                        _pendingEntrySession = UseEODFlat ? (DateTime?)_sessionPlan.Day : null;
                        _longEntry.Send(quantity);
                        LogEntry(stamp, "LONG", quantity, close, longDistance, adxValue);
                        _tradesToday++;
                        ClearLatches();
                    }
                }
                if (shortSignal && validShort && TradeShorts && adxOK)
                {
                    int quantity = GetQuantity(shortDistance);
                    if (quantity >= 1)
                    {
                        _activeStop = shortStop;
                        _activeTarget = shortTarget;
                        _pendingEntrySession = UseEODFlat ? (DateTime?)_sessionPlan.Day : null;
                        _shortEntry.Send(quantity);
                        LogEntry(stamp, "SHORT", quantity, close, shortDistance, adxValue);
                        _tradesToday++;
                        ClearLatches();
                    }
                }
            }

            // Same scheduled cutoff as AQ; no SessionLastBar or future-bar scan.
            bool flatten = UseEODFlat && (!_sessionPlan.Cutoff.HasValue || stamp >= _sessionPlan.Cutoff.Value);
            int openQuantity = (int)Math.Abs(position);
            if (position > 0)
            {
                if (flatten) _longFlat.Send(openQuantity); // flatten
                else
                {
                    _longTarget.Send(_activeTarget, openQuantity); // keep sending the target and stop
                    _longStop.Send(_activeStop, openQuantity);
                }
            }
            if (position < 0)
            {
                if (flatten) _shortFlat.Send(openQuantity);
                else
                {
                    _shortTarget.Send(_activeTarget, openQuantity);
                    _shortStop.Send(_activeStop, openQuantity);
                }
            }

            // These snapshots match the source's prior-bar boolean variables.
            _prevInORB = inORB;
            _prevInVwap = inVwap;
            _prevLongLatched = longLatched;
            _prevShortLatched = shortLatched;
            _firstBar = false;
            _previousPosition = position;
        }

        private void UpdatePivots()
        {
            // if num bars enough
            if (Bars.CurrentBar > 2 * StopSwingLen)
            {
                // check if is pivot high given stop len
                if (IsPivotHigh(StopSwingLen))
                {
                    // update stop high (for shorts)
                    _lastStopHigh = Bars.High[StopSwingLen];
                    _hasStopHigh = true;
                }
                // check if is pivot low given stop len
                if (IsPivotLow(StopSwingLen))
                {
                    // update stop low (for longs)
                    _lastStopLow = Bars.Low[StopSwingLen];
                    _hasStopLow = true;
                }
            }
            if (Bars.CurrentBar > 2 * TargetSwingLen)
            {
                if (IsPivotHigh(TargetSwingLen))
                {
                    //update target high (for longs)
                    _lastTargetHigh = Bars.High[TargetSwingLen];
                    _hasTargetHigh = true;
                }
                if (IsPivotLow(TargetSwingLen))
                {
                    // update target low (for shorts)
                    _lastTargetLow = Bars.Low[TargetSwingLen];
                    _hasTargetLow = true;
                }
            }
        }

        private bool IsPivotHigh(int strength)
        {
            double candidate = Bars.High[strength];
            for (int i = 0; i <= 2 * strength; i++)
                if (i != strength && Bars.High[i] >= candidate) return false;
            return true;
        }

        private bool IsPivotLow(int strength)
        {
            double candidate = Bars.Low[strength];
            for (int i = 0; i <= 2 * strength; i++)
                if (i != strength && Bars.Low[i] <= candidate) return false;
            return true;
        }

        private int GetQuantity(double stopDistance)
        {
            // Fixed-size mode is not capped by Max_Contracts in the source.
            if (!UseVolSizing) return PositionSize;
            if (stopDistance <= 0 || Max_Contracts < 1 || _riskDollars <= 0)
                return 0;
            double perContractRisk = (stopDistance + 2 * _tickSize) * _pointValue;
            if (perContractRisk <= 0) return 0;
            double quantity = Math.Floor(_riskDollars / perContractRisk);
            return (int)Math.Min(quantity, Max_Contracts);
        }

        private void ClearLatches()
        {
            _longOrbBroken = _shortOrbBroken = false;
            _longTouched = _shortTouched = false;
            _longClosedThrough = _shortClosedThrough = false;
        }

        private void LogEntry(DateTime stamp, string direction, int quantity,
            double close, double stopDistance, double adxValue)
        {
            if (PlotTradeLevels)
                Output.WriteLine(
                    "{0:yyyy-MM-dd HH:mm} {1} qty={2} close={3:F2} stop={4:F2} tgt={5:F2} stopDist={6:F2} adx={7:F2}",
                    stamp, direction, quantity, close, _activeStop, _activeTarget,
                    stopDistance, adxValue);
        }
    }
}
#endif

// Compiled without the MC signal only for independent calendar qualification.
// Normal MC compilation does not define AQ_CALENDAR_ONLY and includes both.
namespace AlphaQuest.MarketCalendars
{
    public sealed class NqSessionPlan
    {
        public readonly DateTime Day;
        public readonly string Kind;
        public readonly DateTime? ScheduledClose;
        public readonly DateTime? Cutoff;

        public NqSessionPlan(DateTime day, string kind, DateTime? close, DateTime? cutoff)
        { Day = day; Kind = kind; ScheduledClose = close; Cutoff = cutoff; }

        public bool AllowsFill(DateTime stamp)
        {
            return Cutoff.HasValue && stamp < Cutoff.Value
                && NqSessionCalendar.SessionDate(stamp) == Day
                && (stamp.Date == Day || stamp.TimeOfDay > TimeSpan.FromHours(17));
        }

        public bool AllowsEntrySignal(DateTime stamp)
        {
            // AQ and MC require the next one-minute close label strictly before
            // cutoff. A later data gap still needs the separate pending-fill guard.
            return AllowsFill(stamp) && AllowsFill(stamp.AddMinutes(1));
        }
    }

    public sealed class NqSessionCalendar
    {
        private sealed class ExceptionRow
        {
            public string Kind;
            public TimeSpan? Close;
        }
        private readonly Dictionary<DateTime, ExceptionRow> _rows;
        public readonly DateTime CoverageStart, CoverageEnd;
        public readonly string Sha256;
        public int RowCount { get { return _rows.Count; } }
        private static readonly string[] Header = {
            "coverage_start", "coverage_end", "session_date", "closure_type",
            "close_time_local", "timezone", "event", "source_url", "source_note", "verified_on"
        };

        private NqSessionCalendar(Dictionary<DateTime, ExceptionRow> rows,
            DateTime start, DateTime end, string hash)
        { _rows = rows; CoverageStart = start; CoverageEnd = end; Sha256 = hash; }

        public static DateTime SessionDate(DateTime chicagoStamp)
        {
            return chicagoStamp.Date.AddDays(chicagoStamp.TimeOfDay >= TimeSpan.FromHours(17) ? 1 : 0);
        }

        public static string ResolveCalendarFile(string symbol, string directory)
        {
            string normalized = (symbol ?? "").Trim().ToUpperInvariant();
            if (!Regex.IsMatch(normalized, @"\A@?NQ(?:[!#12]*|[FGHJKMNQUVXZ][0-9]{1,4})(?:[. ]CME)?\z"))
                throw new ArgumentException("No reviewed session calendar for instrument '" + normalized + "'. Calendar EOD flattening currently supports NQ only.");
            if (String.IsNullOrWhiteSpace(directory))
                throw new ArgumentException("SessionCalendarDirectory is required when UseEODFlat is enabled.");
            return Path.Combine(directory, "cme_nq_closures.csv");
        }

        public static void ValidateCloseBuffer(int minutes)
        {
            if (minutes < 1 || minutes > 1440)
                throw new ArgumentException("Close buffer minutes must be an integer from 1 through 1440.");
        }

        public NqSessionPlan Plan(DateTime day, int eodFlatTime, int closeBufferMinutes = 5)
        {
            ValidateCloseBuffer(closeBufferMinutes);
            day = day.Date;
            if (day < CoverageStart || day > CoverageEnd)
                throw new ArgumentException(String.Format(CultureInfo.InvariantCulture,
                    "NQ session calendar does not cover {0:yyyy-MM-dd}; reviewed coverage is {1:yyyy-MM-dd} through {2:yyyy-MM-dd}. Update the shared CSV.",
                    day, CoverageStart, CoverageEnd));
            if (eodFlatTime < 0 || eodFlatTime > 2359 || eodFlatTime % 100 >= 60)
                throw new ArgumentException("EOD cutoff must use valid HHMM Chicago time.");
            if (day.DayOfWeek == DayOfWeek.Saturday || day.DayOfWeek == DayOfWeek.Sunday)
                return new NqSessionPlan(day, "weekend", null, null);
            ExceptionRow row;
            bool exception = _rows.TryGetValue(day, out row);
            if (exception && row.Kind == "full_close")
                return new NqSessionPlan(day, "full_close", null, null);
            DateTime close = day.Add(exception ? row.Close.Value : TimeSpan.FromHours(16));
            DateTime configured = day.AddHours(eodFlatTime / 100).AddMinutes(eodFlatTime % 100);
            DateTime buffered = close.AddMinutes(-closeBufferMinutes);
            return new NqSessionPlan(day, exception ? "early_close" : "regular", close,
                configured < buffered ? configured : buffered);
        }

        public static NqSessionCalendar Load(string path)
        {
            if (String.IsNullOrWhiteSpace(path))
                throw new ArgumentException("A calendar CSV path is required when UseEODFlat is enabled.");
            byte[] bytes = File.ReadAllBytes(path);
            string text = new UTF8Encoding(false, true).GetString(bytes);
            if (text.Length > 0 && text[0] == '\uFEFF') text = text.Substring(1);
            string hash;
            using (SHA256 algorithm = SHA256.Create())
            {
                byte[] digest = algorithm.ComputeHash(bytes);
                StringBuilder hex = new StringBuilder();
                foreach (byte value in digest) hex.Append(value.ToString("x2", CultureInfo.InvariantCulture));
                hash = hex.ToString();
            }
            Dictionary<DateTime, ExceptionRow> rows = new Dictionary<DateTime, ExceptionRow>();
            DateTime start = DateTime.MinValue, end = DateTime.MinValue, previous = DateTime.MinValue;
            int record = 0;
            foreach (string[] cells in ReadCsv(text))
            {
                record++;
                if (cells.Length != Header.Length)
                    throw new FormatException("Calendar CSV record has the wrong number of columns.");
                if (record == 1)
                {
                    for (int i = 0; i < Header.Length; i++)
                        if (cells[i] != Header[i]) throw new FormatException("Calendar CSV headers/order do not match the shared schema.");
                    continue;
                }
                for (int i = 0; i < cells.Length; i++)
                    if (cells[i] != cells[i].Trim() || (i != 4 && cells[i].Length == 0))
                        throw new FormatException("Calendar CSV has whitespace or an empty required value.");
                DateTime from = ParseDate(cells[0]), through = ParseDate(cells[1]);
                DateTime day = ParseDate(cells[2]);
                ParseDate(cells[9]); // Review date is not an announcement date.
                if (record == 2) { start = from; end = through; }
                if (from != start || through != end || start > end)
                    throw new FormatException("Calendar coverage bounds must agree on every row.");
                if (day < start || day > end || day <= previous
                    || day.DayOfWeek == DayOfWeek.Saturday || day.DayOfWeek == DayOfWeek.Sunday)
                    throw new FormatException("Calendar exceptions must be covered unique weekdays in ascending order.");
                previous = day;
                if (cells[5] != "America/Chicago")
                    throw new FormatException("Calendar timezone must be America/Chicago.");
                Uri source;
                if (!Uri.TryCreate(cells[7], UriKind.Absolute, out source) || source.Scheme != "https" || String.IsNullOrEmpty(source.Host))
                    throw new FormatException("Calendar source must be an absolute HTTPS URL.");
                TimeSpan? close = null;
                if (cells[3] == "full_close")
                {
                    if (cells[4].Length != 0) throw new FormatException("full_close must have an empty close time.");
                }
                else if (cells[3] == "early_close")
                {
                    DateTime parsed;
                    if (cells[4].Length != 5 || !DateTime.TryParseExact(cells[4], "HH:mm",
                        CultureInfo.InvariantCulture, DateTimeStyles.None, out parsed)
                        || parsed.TimeOfDay >= TimeSpan.FromHours(16))
                        throw new FormatException("early_close requires HH:MM before 16:00.");
                    close = parsed.TimeOfDay;
                }
                else throw new FormatException("Calendar closure_type must be early_close or full_close.");
                rows.Add(day, new ExceptionRow { Kind = cells[3], Close = close });
            }
            if (rows.Count == 0) throw new FormatException("Calendar contains no exception rows.");
            return new NqSessionCalendar(rows, start, end, hash);
        }

        private static DateTime ParseDate(string value)
        {
            DateTime result;
            if (!DateTime.TryParseExact(value, "yyyy-MM-dd", CultureInfo.InvariantCulture,
                DateTimeStyles.None, out result) || value.Length != 10)
                throw new FormatException("Calendar dates must use YYYY-MM-DD.");
            return result;
        }

        // RFC 4180 fields, including escaped quotes, embedded commas/newlines,
        // UTF-8 BOM (handled by Load), LF and CRLF. No dependency DLL required.
        private static IEnumerable<string[]> ReadCsv(string text)
        {
            List<string> row = new List<string>();
            StringBuilder field = new StringBuilder();
            bool quoted = false, afterQuote = false, recordStarted = false;
            for (int i = 0; i < text.Length; i++)
            {
                char c = text[i];
                if (quoted)
                {
                    if (c == '"')
                    {
                        if (i + 1 < text.Length && text[i + 1] == '"') { field.Append('"'); i++; }
                        else { quoted = false; afterQuote = true; }
                    }
                    else field.Append(c);
                    recordStarted = true;
                    continue;
                }
                if (c == ',' || c == '\r' || c == '\n')
                {
                    row.Add(field.ToString()); field.Length = 0; afterQuote = false;
                    if (c == ',') { recordStarted = true; continue; }
                    if (c == '\r' && i + 1 < text.Length && text[i + 1] == '\n') i++;
                    // Skip genuinely blank lines, as Python csv.DictReader does.
                    if (recordStarted || row.Count != 1 || row[0].Length != 0) yield return row.ToArray();
                    row.Clear(); recordStarted = false;
                }
                else if (c == '"')
                {
                    if (field.Length != 0 || afterQuote) throw new FormatException("Invalid CSV quote.");
                    quoted = true; recordStarted = true;
                }
                else
                {
                    if (afterQuote) throw new FormatException("Characters after a closing CSV quote.");
                    field.Append(c); recordStarted = true;
                }
            }
            if (quoted) throw new FormatException("Unterminated quoted CSV field.");
            if (recordStarted || row.Count != 0 || field.Length != 0)
            { row.Add(field.ToString()); yield return row.ToArray(); }
        }
    }
}
