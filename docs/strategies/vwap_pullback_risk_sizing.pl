// =====================================================================
// VWAP PULLBACK - RISK SIZING (lean input set)
// Profile: "C.S." defaults baked in (long-only, fixed 4 contracts,
//   ADX Elev + Decay gates ON, EOD flat 15:55 CT).
// Instrument: NQ / MNQ futures, 1-minute bars.
//
// CHART: full 24h CME session (17:00-16:00 CT), Exchange time zone,
//   1-min bars, volume = trade volume. IOG OFF. MaxBarsBack >= 42.
// PROPERTIES: commission/slippage set per replication or base-case run.
//
// CORE LOGIC: unchanged from v1 port.
//   ORB 0830-0900 CT broken by close (latched) -> VWAP retest
//   (touch or close-through-reclaim) -> market entry on reclaim close.
//   Stop: pivot swing (StopMode 1, original) or pullback extreme
//   (StopMode 2). Target: last confirmed 5-strength pivot.
//
// v3: ADX GATE (both toggles TRUE in this profile)
//     ElevOK  = (UseADXElev = false)  or (ADXv >= ADXElev_Thr)
//     DecayOK = (UseADXDecay = false) or (ADXv <= ADXv[ADXDecay_LB])
//     ADX_OK  = ElevOK and DecayOK
//   Evaluated on the SIGNAL bar, entry next bar at market -> no
//   lookahead. The gate DELAYS, it does not cancel: latches persist,
//   so if the reclaim is still true later and ADX complies, it fires.
//
// v4: RISK SIZING, minimal inputs.
//   UseVolSizing true  -> Qty = IntPortion(Risk$ / perContractRisk)
//       Risk$           = MM_Capital_USD * MM_Risk_Pct / 100
//       perContractRisk = (stopDist + 2 ticks slippage pad) * BigPointValue
//       cap at Max_Contracts. If one contract risks more than Risk$,
//       Qty = 0 and the trade is skipped.
//   UseVolSizing false -> fixed PositionSize contracts.  <-- C.S. default
//   Tick size from MinMove/PriceScale, dollar value from BigPointValue:
//   NQ vs MNQ handled automatically, no TickSz/TickVal inputs.
//   Removed vs v2 module: ATR risk filter, margin cap, ladder.
// =====================================================================

Inputs:
    // ---- risk sizing ----
    UseVolSizing(false),      // C.S.: fixed size
    PositionSize(1),          // C.S.: 1 contracts
    MM_Capital_USD(500000),   // account capital
    MM_Risk_Pct(2.0),         // risk per trade, pct of capital
    Max_Contracts(1),         // hard ceiling
    // ---- trade selection ----
    TradeLongs(true),         // enable long entries
    TradeShorts(false),       // C.S.: long-only
    MinRR(0),                 // skip trade if target dist / stop dist < MinRR (0 = off)
    MaxStopPoints(0),         // skip trade if stop distance > this many points (0 = off)
    // ---- ADX gate (evaluated on the signal bar) ----
    UseADXElev(true),         // C.S.: require ADXv >= ADXElev_Thr
    ADXElev_Thr(20),
    UseADXDecay(true),        // C.S.: require ADXv <= ADXv[ADXDecay_LB]
    ADXDecay_LB(1),
    ADX_Len(14),
    // ---- strategy logic ----
    RetestMode(1),            // 1 = Touch VWAP, 2 = Close Through Then Reclaim
    StopMode(1),              // 1 = pivot swing (original), 2 = pullback extreme
    MaxTradesPerDay(1),
    StopSwingLen(20),
    TargetSwingLen(5),
    BufferMode(2),            // 1 = Ticks, 2 = Points
    BufferAmount(0),
    ORStartTime(0830),        // CT (09:30 NY)
    OREndTime(0900),          // CT (10:00 NY)
    VwapStartTime(0830),      // CT (09:30 NY)
    VwapEndTime(1700),        // CT (18:00 NY)
    EntryStartTime(0900),     // CT (10:00 NY)
    EntryEndTime(1700),       // CT (18:00 NY)
    DayResetTime(2300),       // CT (midnight NY)
    UseEODFlat(true),         // C.S.: flat before close
    EODFlatTime(1555),        // CT
    PlotTradeLevels(true);    // true = print entry details to Output Log

Vars:
    tickSize(0), buffer(0),
    typPrice(0), barVol(0),
    inORB(false), inVwapSess(false), inEntrySess(false),
    orbReady(false), newNyDay(false),
    orbHigh(0), orbLow(0),
    cumPV(0), cumVol(0), nyVwap(0), vwapValid(false),
    lastStopSwingHigh(0), lastStopSwingLow(0),
    lastTargetSwingHigh(0), lastTargetSwingLow(0),
    hasStopSH(false), hasStopSL(false),
    hasTgtSH(false), hasTgtSL(false),
    longOrbBroken(false), shortOrbBroken(false),
    longVwapTouched(false), shortVwapTouched(false),
    longClosedThrough(false), shortClosedThrough(false),
    tradesToday(0),
    canTrackBreak(false), canLookForEntry(false),
    longSignal(false), shortSignal(false),
    longStopPrice(0), longTargetPrice(0),
    shortStopPrice(0), shortTargetPrice(0),
    validLong(false), validShort(false),
    longLatched(false), shortLatched(false),
    pullbackLow(0), pullbackHigh(0),
    activeStop(0), activeTgt(0),
    isPivot(false), i1(0),
    // ADX gate work vars
    ADXv(0), ElevOK(false), DecayOK(false), ADX_OK(false),
    // sizing work vars
    Risk_USD_Actual(0),
    stopDist(0), Per_Contract_Risk(0), Qty(0);

Once begin
    Risk_USD_Actual = MM_Capital_USD * (MM_Risk_Pct / 100);
end;

tickSize = MinMove / PriceScale;
if BufferMode = 1 then
    buffer = BufferAmount * tickSize
else
    buffer = BufferAmount;

typPrice = (High + Low + Close) / 3;
barVol = Ticks;
if barVol <= 0 then barVol = 1;

// ---------------- ADX gate (1:1 with ADX_Gate indicator) ----------------
ADXv    = ADX(ADX_Len);
ElevOK  = (UseADXElev = false)  or (ADXv >= ADXElev_Thr);
DecayOK = (UseADXDecay = false) or (ADXv <= ADXv[ADXDecay_LB]);
ADX_OK  = ElevOK and DecayOK;

// ---------------- Session windows ----------------
inORB = Time > ORStartTime and Time <= OREndTime;
inVwapSess = Time > VwapStartTime and Time <= VwapEndTime;
inEntrySess = Time > EntryStartTime and Time <= EntryEndTime;

// ---------------- NY day reset (23:00 CT) ----------------
newNyDay = CurrentBar = 1
    or (Time > DayResetTime and Time[1] <= DayResetTime);

if newNyDay then begin
    tradesToday = 0;
    orbReady = false;
    longOrbBroken = false;   shortOrbBroken = false;
    longVwapTouched = false; shortVwapTouched = false;
    longClosedThrough = false; shortClosedThrough = false;
end;

// ---------------- ORB build ----------------
if inORB and inORB[1] = false then begin
    orbHigh = High;
    orbLow = Low;
    orbReady = false;
end;

if inORB then begin
    if High > orbHigh then orbHigh = High;
    if Low < orbLow then orbLow = Low;
end;

if inORB = false and inORB[1] then
    orbReady = true;

// ---------------- NY session VWAP ----------------
if inVwapSess and inVwapSess[1] = false then begin
    cumPV = typPrice * barVol;
    cumVol = barVol;
end
else if inVwapSess then begin
    cumPV = cumPV + typPrice * barVol;
    cumVol = cumVol + barVol;
end;

vwapValid = inVwapSess and cumVol > 0;
if vwapValid then nyVwap = cumPV / cumVol;

// ---------------- Pivot detection ----------------
if CurrentBar > 2 * StopSwingLen then begin
    isPivot = true;
    for i1 = 0 to 2 * StopSwingLen begin
        if i1 <> StopSwingLen and High[i1] >= High[StopSwingLen] then
            isPivot = false;
    end;
    if isPivot then begin
        lastStopSwingHigh = High[StopSwingLen];
        hasStopSH = true;
    end;

    isPivot = true;
    for i1 = 0 to 2 * StopSwingLen begin
        if i1 <> StopSwingLen and Low[i1] <= Low[StopSwingLen] then
            isPivot = false;
    end;
    if isPivot then begin
        lastStopSwingLow = Low[StopSwingLen];
        hasStopSL = true;
    end;
end;

if CurrentBar > 2 * TargetSwingLen then begin
    isPivot = true;
    for i1 = 0 to 2 * TargetSwingLen begin
        if i1 <> TargetSwingLen and High[i1] >= High[TargetSwingLen] then
            isPivot = false;
    end;
    if isPivot then begin
        lastTargetSwingHigh = High[TargetSwingLen];
        hasTgtSH = true;
    end;

    isPivot = true;
    for i1 = 0 to 2 * TargetSwingLen begin
        if i1 <> TargetSwingLen and Low[i1] <= Low[TargetSwingLen] then
            isPivot = false;
    end;
    if isPivot then begin
        lastTargetSwingLow = Low[TargetSwingLen];
        hasTgtSL = true;
    end;
end;

// ---------------- ORB break latching ----------------
canTrackBreak = orbReady and inORB = false;

if canTrackBreak and Close > orbHigh then longOrbBroken = true;
if canTrackBreak and Close < orbLow then shortOrbBroken = true;

// ---------------- Retest logic ----------------
canLookForEntry = canTrackBreak and inVwapSess and inEntrySess and vwapValid;

longSignal = false;
shortSignal = false;

if canLookForEntry and longOrbBroken then begin
    if RetestMode = 1 then begin
        if Low <= nyVwap then longVwapTouched = true;
        longSignal = longVwapTouched and Close > nyVwap;
    end;
    if RetestMode = 2 then begin
        if Close < nyVwap then longClosedThrough = true;
        longSignal = longClosedThrough and Close > nyVwap;
    end;
end;

if canLookForEntry and shortOrbBroken then begin
    if RetestMode = 1 then begin
        if High >= nyVwap then shortVwapTouched = true;
        shortSignal = shortVwapTouched and Close < nyVwap;
    end;
    if RetestMode = 2 then begin
        if Close > nyVwap then shortClosedThrough = true;
        shortSignal = shortClosedThrough and Close < nyVwap;
    end;
end;

// ---------------- Pullback extreme tracking (StopMode 2) ----------------
longLatched = longVwapTouched or longClosedThrough;
shortLatched = shortVwapTouched or shortClosedThrough;

if longLatched and longLatched[1] = false then
    pullbackLow = Low
else if longLatched and Low < pullbackLow then
    pullbackLow = Low;

if shortLatched and shortLatched[1] = false then
    pullbackHigh = High
else if shortLatched and High > pullbackHigh then
    pullbackHigh = High;

// ---------------- Stop / target levels ----------------
if StopMode = 2 then begin
    longStopPrice = pullbackLow - buffer;
    shortStopPrice = pullbackHigh + buffer;
end
else begin
    longStopPrice = lastStopSwingLow - buffer;
    shortStopPrice = lastStopSwingHigh + buffer;
end;
longTargetPrice = lastTargetSwingHigh;
shortTargetPrice = lastTargetSwingLow;

validLong = (StopMode = 2 or hasStopSL) and hasTgtSH
    and (StopMode = 1 or longLatched)
    and longStopPrice < Close and longTargetPrice > Close
    and (MaxStopPoints = 0 or Close - longStopPrice <= MaxStopPoints)
    and (MinRR = 0 or (Close - longStopPrice > 0
         and (longTargetPrice - Close) / (Close - longStopPrice) >= MinRR));
validShort = (StopMode = 2 or hasStopSH) and hasTgtSL
    and (StopMode = 1 or shortLatched)
    and shortStopPrice > Close and shortTargetPrice < Close
    and (MaxStopPoints = 0 or shortStopPrice - Close <= MaxStopPoints)
    and (MinRR = 0 or (shortStopPrice - Close > 0
         and (Close - shortTargetPrice) / (shortStopPrice - Close) >= MinRR));

// ---------------- Entries with risk sizing ----------------
if MarketPosition = 0 and tradesToday < MaxTradesPerDay then begin

    if longSignal and validLong and TradeLongs and ADX_OK then begin

        stopDist = Close - longStopPrice;
        Qty = PositionSize;

        if UseVolSizing then begin
            Qty = 0;
            if stopDist > 0 then begin
                Per_Contract_Risk = (stopDist + 2 * tickSize) * BigPointValue;
                if Per_Contract_Risk > 0 then
                    Qty = IntPortion(Risk_USD_Actual / Per_Contract_Risk);
                Qty = MinList(Qty, Max_Contracts);
            end;
        end;

        if Qty >= 1 then begin
            Buy ("Long") Qty contracts next bar at market;
            activeStop = longStopPrice;
            activeTgt = longTargetPrice;
            if PlotTradeLevels then
                Print(Date:7:0, " ", Time:4:0,
                    " LONG  qty=", Qty:3:0,
                    " close=", Close:8:2,
                    " stop=", longStopPrice:8:2,
                    " tgt=", longTargetPrice:8:2,
                    " stopDist=", stopDist:6:2,
                    " adx=", ADXv:6:2);
            tradesToday = tradesToday + 1;
            longOrbBroken = false;   shortOrbBroken = false;
            longVwapTouched = false; shortVwapTouched = false;
            longClosedThrough = false; shortClosedThrough = false;
        end;
    end;

    if shortSignal and validShort and TradeShorts and ADX_OK then begin

        stopDist = shortStopPrice - Close;
        Qty = PositionSize;

        if UseVolSizing then begin
            Qty = 0;
            if stopDist > 0 then begin
                Per_Contract_Risk = (stopDist + 2 * tickSize) * BigPointValue;
                if Per_Contract_Risk > 0 then
                    Qty = IntPortion(Risk_USD_Actual / Per_Contract_Risk);
                Qty = MinList(Qty, Max_Contracts);
            end;
        end;

        if Qty >= 1 then begin
            SellShort ("Short") Qty contracts next bar at market;
            activeStop = shortStopPrice;
            activeTgt = shortTargetPrice;
            if PlotTradeLevels then
                Print(Date:7:0, " ", Time:4:0,
                    " SHORT qty=", Qty:3:0,
                    " close=", Close:8:2,
                    " stop=", shortStopPrice:8:2,
                    " tgt=", shortTargetPrice:8:2,
                    " stopDist=", stopDist:6:2,
                    " adx=", ADXv:6:2);
            tradesToday = tradesToday + 1;
            longOrbBroken = false;   shortOrbBroken = false;
            longVwapTouched = false; shortVwapTouched = false;
            longClosedThrough = false; shortClosedThrough = false;
        end;
    end;

end;

// ---------------- Exits: bracket ----------------
if MarketPosition = 1 then begin
    if UseEODFlat and Time >= EODFlatTime and Time < DayResetTime then
        Sell ("EOD.L") next bar at market
    else begin
        Sell ("Long TP") next bar at activeTgt limit;
        Sell ("Long SL") next bar at activeStop stop;
    end;
end;

if MarketPosition = -1 then begin
    if UseEODFlat and Time >= EODFlatTime and Time < DayResetTime then
        BuyToCover ("EOD.S") next bar at market
    else begin
        BuyToCover ("Short TP") next bar at activeTgt limit;
        BuyToCover ("Short SL") next bar at activeStop stop;
    end;
end;
