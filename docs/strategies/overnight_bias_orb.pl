// ============================================================================
// OFB_OvernightBiasORB_Signal - NQ 15-min, one data stream, 1 contract.
//
//   Time frame     15-minute bars
//   Time settings  inputs are ET; for CT use 0830 / 0845 / 1200 / 1430 / 1500
//   Session        Globex template - no calendar is hardcoded here
//   Required       Bar Magnifier 1-minute (intraday), IOG OFF
//   MaxBarsBack    250
//   Ring buffer    warmup 20 trading days (set two months to be safe). Under
//                  15 days nothing trades at all; between 15 and 20 it trades
//                  with the OR-size band silently off, which is the trap.
//
//   Zero-cost backtest
//     IS  | 01-01-2006 to 31-12-2019 | n=1112 | PF 1.35 | net $ 50,445 | DD $ 6,160
//     OOS | 01-01-2020 to 31-08-2026 | n= 599 | PF 1.66 | net $257,615 | DD $20,195
// ============================================================================

// ------------------- Inputs -------------------
inputs:
    SessStart( 0930 ),        // RTH open: starts the OR, ends the overnight range
    OREnd( 0945 ),            // OR locked here; breakouts tested only after it
    LastEntry( 1300 ),        // after this, too little session left to reach the target
    FlatTime( 1530 ),         // force flat before the close; nothing carries overnight
    SessEnd( 1600 ),          // RTH close; also bounds the ATR reference's day
    MaxTradesPerDay( 4 ),     // re-entry cap; only ever one position at a time
    BiasLongMin( 0.67 ),      // open >= this much of the o/n range -> long-only day
    BiasShortMax( 0.33 ),     // open <= this much of the o/n range -> short-only day
    ADXLen( 16 ), ADXMin( 20 ),             // trend-strength gate: sit out chop
    BreakSkipMult( 2.5 ), BarAvgLen( 20 ),  // skip breaks on candles >2.5x the prior
                                            // 20-bar range -- exhaustion moves
    MinORx( 0 ), MaxORx( 2 ), // OR-size band: rejects days whose range is out of
    ORMedianDays( 20 ),       // character, measured against a 20-day OR reference
    ATR_k( 0.30 ),            // stop = ATR_k x ATR_ref, so risk scales with volatility
    ATR_Days( 15 ),           // ATR_ref lookback; must be 1..200 (trBuf size)
    TakeProfitRR( 3 ),        // target = stop x this
    NumContracts( 1 );        // fixed size: dollar risk moves with the ATR stop

// ------------------- Variables -------------------
variables:
    intrabarpersist orHigh( 0 ), intrabarpersist orLow( 999999 ),
    intrabarpersist orDone( false ),
    intrabarpersist tradesToday( 0 ),
    intrabarpersist sessOpenPx( 0 ),
    intrabarpersist onHigh( 0 ), intrabarpersist onLow( 999999 ),
    intrabarpersist onBias( 0 ),        // +1 long only | -1 short only | 9 no trade
    intrabarpersist orMedApprox( 0 ), intrabarpersist orCount( 0 ),
    intrabarpersist regimeOK( true ),
    intrabarpersist stopPx( 0 ), intrabarpersist tgtPx( 0 ),
    intrabarpersist atrRthHi( 0 ), intrabarpersist atrRthLo( 999999 ),
    intrabarpersist atrRthCl( 0 ), intrabarpersist atrRthSeen( false ),
    intrabarpersist atrPrevCl( 0 ),
    intrabarpersist atrPos( 0 ), intrabarpersist atrFilled( 0 ),
    intrabarpersist atrRef( 0 ), intrabarpersist atrOK( false ),
    intrabarpersist stopPts( 0 ),
    onPos( 0 ),
    canWork( false ),
    adxOK( true ), barRngOK( true ), avgRng( 0 ),
    trVal( 0 ), trSum( 0 ), kk( 0 ),
    atrStopOK( false );
arrays:
    trBuf[200](0);

// ------------------- Calculations -------------------
if CurrentBar = 1 and ( ATR_Days < 1 or ATR_Days > 200 ) then
    RaiseRunTimeError( "ATR_Days must be between 1 and 200 (trBuf array size)." );

// ------------------- Session reset -------------------
if Date <> Date[1] then begin
    if atrRthSeen then begin
        trVal = atrRthHi - atrRthLo;
        if atrPrevCl > 0 then begin
            if AbsValue( atrRthHi - atrPrevCl ) > trVal then trVal = AbsValue( atrRthHi - atrPrevCl );
            if AbsValue( atrRthLo - atrPrevCl ) > trVal then trVal = AbsValue( atrRthLo - atrPrevCl );
        end;
        trBuf[atrPos] = trVal;
        atrPos = atrPos + 1;
        if atrPos >= ATR_Days then atrPos = 0;
        if atrFilled < ATR_Days then atrFilled = atrFilled + 1;
        atrPrevCl = atrRthCl;
    end;
    atrRthHi = 0;  atrRthLo = 999999;  atrRthCl = 0;  atrRthSeen = false;
    atrOK = atrFilled >= ATR_Days;
    if atrOK then begin
        trSum = 0;
        for kk = 0 to ATR_Days - 1 begin
            trSum = trSum + trBuf[kk];
        end;
        atrRef = trSum / ATR_Days;
    end
    else
        atrRef = 0;
    orHigh = 0;  orLow = 999999;  orDone = false;
    tradesToday = 0;
    sessOpenPx = 0;  onBias = 0;
    onHigh = High;  onLow = Low;
end
else begin
    if Time <= SessStart then begin
        if High > onHigh then onHigh = High;
        if Low  < onLow  then onLow  = Low;
    end;
end;

// Strictly after the open stamp: on close-stamped bars SessStart is pre-open.
if Time > SessStart and Time <= SessEnd then begin
    if atrRthSeen = false then begin
        atrRthHi = High;  atrRthLo = Low;  atrRthSeen = true;
    end
    else begin
        if High > atrRthHi then atrRthHi = High;
        if Low  < atrRthLo then atrRthLo = Low;
    end;
    atrRthCl = Close;
end;

// ------------------- direction bias, frozen once per day -------------------
if sessOpenPx = 0 and Time > SessStart and Time <= OREnd then begin
    sessOpenPx = Open;
    if onHigh > onLow then begin
        onPos = ( sessOpenPx - onLow ) / ( onHigh - onLow );   // open's place in the o/n range
        if onPos >= BiasLongMin then onBias = 1
        else if onPos <= BiasShortMax then onBias = -1
        else onBias = 9;
    end;
end;

// ------------------- opening range -------------------
if Time > SessStart and Time <= OREnd then begin
    if High > orHigh then orHigh = High;
    if Low  < orLow  then orLow  = Low;
end;
if orDone = false and Time > OREnd and orHigh > 0 then begin
    orDone = true;
    regimeOK = true;
    if orMedApprox > 0 then
        regimeOK = ( orHigh - orLow ) >= MinORx * orMedApprox
               and ( orHigh - orLow ) <= MaxORx * orMedApprox;
    if orMedApprox = 0 then orMedApprox = orHigh - orLow
    else orMedApprox = orMedApprox + ( 2 / ( ORMedianDays + 1 ) ) * ( ( orHigh - orLow ) - orMedApprox );
    orCount = orCount + 1;
    if orCount < ORMedianDays then regimeOK = true;      // warmup
end;
stopPts   = ATR_k * atrRef;
atrStopOK = atrOK and stopPts > 0;         // no ATR yet -> skip the session

// ------------------- Gates -------------------
adxOK  = ADX( ADXLen ) >= ADXMin;    // native = Wilder; a simple-average lookalike
                                     // passes different bars
avgRng = Average( High - Low, BarAvgLen )[1];
barRngOK = avgRng = 0 or ( High - Low ) <= BreakSkipMult * avgRng;
canWork = orDone and regimeOK and adxOK
          and atrStopOK
          and Time > OREnd and Time <= LastEntry
          and MarketPosition = 0 and tradesToday < MaxTradesPerDay;

// ------------------- Entry -------------------
// First bar CLOSING beyond the OR. A rejected break does not kill the side.
if canWork then begin
    if Close > orHigh then begin
        if barRngOK and onBias = 1 then begin
            stopPx = Close - stopPts;
            tgtPx  = Close + stopPts * TakeProfitRR;
            Buy ( "ORB_L" ) NumContracts contracts next bar at market;
            Sell ( "L-SL-FB" ) next bar at stopPx stop;
            Sell ( "L-TP-FB" ) next bar at tgtPx limit;
            tradesToday = tradesToday + 1;
        end;
    end
    else if Close < orLow then begin
        if barRngOK and onBias = -1 then begin
            stopPx = Close + stopPts;
            tgtPx  = Close - stopPts * TakeProfitRR;
            SellShort ( "ORB_S" ) NumContracts contracts next bar at market;
            BuyToCover ( "S-SL-FB" ) next bar at stopPx stop;
            BuyToCover ( "S-TP-FB" ) next bar at tgtPx limit;
            tradesToday = tradesToday + 1;
        end;
    end;
end;

// ------------------- Exits -------------------
// Re-issued every bar in position; the entry block covers the fill bar. Both
// legs anchor on the SIGNAL bar's close.
if MarketPosition = 1 then begin
    if Time >= FlatTime then
        Sell ( "XL" ) next bar at market
    else begin
        Sell ( "L-SL" ) next bar at stopPx stop;
        Sell ( "L-TP" ) next bar at tgtPx limit;
    end;
end;
if MarketPosition = -1 then begin
    if Time >= FlatTime then
        BuyToCover ( "XS" ) next bar at market
    else begin
        BuyToCover ( "S-SL" ) next bar at stopPx stop;
        BuyToCover ( "S-TP" ) next bar at tgtPx limit;
    end;
end;
SetExitOnClose;
