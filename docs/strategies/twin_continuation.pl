{ =====================================================================
  TWIN CONTINUATION  -  Swing Breakout + Morning Momentum, one system
  ---------------------------------------------------------------------
  INSTRUMENT   NQ or MNQ futures (continuous contract)
  CHART        Data1 only, 1-MINUTE bars. No Data2.
               (Other requiered bars are built inside the code from the 1-minute bars.)
  SESSION      24h CME Globex session template (17:00-16:00 CT)
  TIME ZONE    Central Time (CT). Bars stamped with their CLOSE time
               (MultiCharts default). Open-stamped chart: ClockShift = 1
  PROPERTIES   Intrabar Order Generation OFF, Bar Magnifier not needed,
               Max Bars Back 5 (manual), do not allow multiple entries
  HISTORY      Load at least 6 months before the test period
  COSTS        Research run: $5 commission + $1 slippage per trade (NQ)
  SIZE         Qty = 1 (1 NQ = 10 MNQ)
  SETUPS       UseBreakout - Swing Breakout on 6h swing highs/lows
               UseMomentum - Morning Momentum, 08:40-09:30 CT entries
  RULE         One position at a time. A setup only enters while flat;
               each exit only closes its own setup's entry.
===================================================================== }

Inputs:
    { --- general --- }
    UseBreakout( true ),
    UseMomentum( true ),
    Qty( 1 ),

    { --- Swing Breakout --- }
    BO_TargetMult( 2.0 ),
    BO_MaxStopMult( 0 ),
    BO_ATRPeriod( 14 ),
    BO_VolCap( 2.0 ),
    BO_VolLookback( 50 ),
    BO_SessionOpen( 1700 ),
    BO_SessionClose( 1600 ),
    BO_LastFill( 1530 ),
    BO_ExitTime( 1545 ),
    BO_PivotTF( 360 ),

    { --- Morning Momentum --- }
    MO_BasisLen( 21 ),
    MO_RangeLen( 14 ),
    MO_SignalLen( 3 ),
    MO_Trigger( 100 ),
    MO_WindowStart( 840 ),
    MO_WindowEnd( 930 ),
    MO_ExitTime( 1450 ),
    MO_StopPoints( 75 ),
    MO_Warmup( 60 ),
    MO_FullBarsOnly( true ),
    MO_AllowLong( true ),
    MO_AllowShort( true ),
    ClockShift( 0 ),
    DebugLog( false );

Arrays:
    CanH[6]( 0 ), CanL[6]( 0 ), SessRng[100]( 0 );

Vars:

    TimeC( 0 ), SmNow( 0 ), PrevSm( -1 ), Bkt( 0 ), PrevBkt( -1 ), HIdx( 0 ), PrevHIdx( -1 ),
    NewSess( false ), NewBkt( false ), NewCan( false ), SessStartM( 0 ),
    SessEndSm( 0 ), FillEndSm( 0 ), FlatSm( 0 ),

    SHi( 0 ), SLo( 0 ), NSess( 0 ), VolRatio( 0 ), RngSum( 0 ), VL( 0 ),

    BarOpen( false ), B15H( 0 ), B15L( 0 ), B15C( 0 ), B15LastH( 0 ), B15LastL( 0 ), B15LastSm( 0 ),
    CanOpen( false ), CurH( 0 ), CurL( 0 ), NC( 0 ),
    LateCan( false ), LateBar( false ), DoCan( false ), DoBar( false ), K( 0 ), J( 0 ),

    PrevC15( 0 ), TrN( 0 ), TrSum( 0 ), AtrV( 0 ), TRv( 0 ),

    GotSwH( false ), GotSwL( false ), NewSwH( 0 ), NewSwL( 0 ),
    SwH( 0 ), SwL( 0 ), LastSwH( 0 ), LastSwL( 0 ), HaveSwH( false ), HaveSwL( false ),
    SwHOpen( false ), SwLOpen( false ),

    Armed( false ), OkL( false ), OkS( false ), LvlL( 0 ), LvlS( 0 ), StpL( 0 ), StpS( 0 ),
    AtrU( 0 ), ArmTrades( 0 ),

    AlphaPivot( 0 ), AlphaOsc( 0 ), SStartMin( 0 ), SBk( 0 ), SPrevBk( -1 ), SBkDate( 0 ),
    SOpen( false ), SH( 0 ), SL_( 0 ), SC( 0 ), SN( 0 ), SEndT( 0 ),
    SNewBk( false ), SLate( false ), SDo( false ),
    FH( 0 ), FL( 0 ), FC( 0 ), FN( 0 ), FEndT( 0 ),
    SNB( 0 ), SPrevC( 0 ), Strv( 0 ), SatrW( 0 ), SPivot( 0 ), SRaw( 0 ),
    SOscV( 0 ), SOscPrev( 0 ), SHaveOsc( false ), SHavePrev( false ),
    SSide( 0 ), SFire( 0 ), STradedToday( false ), SLastDate( 0 ), SHalfDay( false );

Once Begin
    If BarInterval <> 1 or BarType <> 1 Then
        RaiseRunTimeError( "Twin Continuation must run on a 1-minute chart." );
    AlphaPivot = 2 / ( MO_BasisLen + 1 );
    AlphaOsc   = 2 / ( MO_SignalLen + 1 );
End;

If ClockShift <> 0 Then TimeC = MinutesToTime( TimeToMinutes( Time ) + ClockShift )
Else TimeC = Time;

{ ===== SWING BREAKOUT: clock, session range, volatility filter ===== }
SessStartM = TimeToMinutes( BO_SessionOpen );
SmNow      = Mod( TimeToMinutes( TimeC ) - 1 - SessStartM + 2880, 1440 );
SessEndSm  = Mod( TimeToMinutes( BO_SessionClose ) - SessStartM + 1440, 1440 );
FillEndSm  = Mod( TimeToMinutes( BO_LastFill ) - SessStartM + 1440, 1440 );
FlatSm     = Mod( TimeToMinutes( BO_ExitTime )    - SessStartM + 1440, 1440 );

NewSess = PrevSm < 0 or SmNow < PrevSm;
Bkt     = IntPortion( SmNow / 15 );
HIdx    = IntPortion( SmNow / BO_PivotTF );
NewBkt  = NewSess or Bkt <> PrevBkt;
NewCan  = NewSess or HIdx <> PrevHIdx;

If NewSess Then Begin
    If PrevSm >= 0 and SHi > SLo Then Begin
        For J = 99 downto 1 Begin SessRng[J] = SessRng[J-1]; End;
        SessRng[0] = SHi - SLo;
        NSess = NSess + 1;
        VL = MinList( MaxList( BO_VolLookback, 1 ), 99 );
        VolRatio = 0;
        If NSess > VL Then Begin
            RngSum = 0;
            For J = 1 to VL Begin RngSum = RngSum + SessRng[J]; End;
            If RngSum > 0 Then VolRatio = SessRng[0] / ( RngSum / VL );
        End;
    End;
    SHi = High; SLo = Low;
End
Else Begin
    SHi = MaxList( SHi, High ); SLo = MinList( SLo, Low );
End;

{ ===== SWING BREAKOUT: 15m bars, 6h candles, swing levels, arming ===== }
LateCan = NewCan and CanOpen;
LateBar = NewBkt and BarOpen;

For K = 1 to 2 Begin
    If K = 1 Then Begin
        DoCan = LateCan; DoBar = LateBar;
    End
    Else Begin

        If NewCan Then Begin CurH = High; CurL = Low; CanOpen = true; End
        Else Begin CurH = MaxList( CurH, High ); CurL = MinList( CurL, Low ); End;
        If NewBkt Then Begin B15H = High; B15L = Low; BarOpen = true; End
        Else Begin B15H = MaxList( B15H, High ); B15L = MinList( B15L, Low ); End;
        B15C = Close; B15LastH = High; B15LastL = Low; B15LastSm = SmNow;

        If SwHOpen and High >= SwH Then SwHOpen = false;
        If SwLOpen and Low  <= SwL Then SwLOpen = false;
        DoCan = CanOpen and ( Mod( SmNow + 1, BO_PivotTF ) = 0 or SmNow + 1 >= SessEndSm );
        DoBar = BarOpen and Mod( SmNow + 1, 15 ) = 0;
    End;

    If DoCan Then Begin
        CanOpen = false;
        For J = 6 downto 1 Begin CanH[J] = CanH[J-1]; CanL[J] = CanL[J-1]; End;
        CanH[0] = CurH; CanL[0] = CurL;
        NC = NC + 1;
        If NC >= 7 Then Begin
            If CanH[3] >= MaxList( CanH[4], CanH[5], CanH[6] ) and CanH[3] >= MaxList( CanH[0], CanH[1], CanH[2] ) Then Begin
                GotSwH = true; NewSwH = CanH[3];
            End;
            If CanL[3] <= MinList( CanL[4], CanL[5], CanL[6] ) and CanL[3] <= MinList( CanL[0], CanL[1], CanL[2] ) Then Begin
                GotSwL = true; NewSwL = CanL[3];
            End;
        End;
    End;

    If DoBar Then Begin
        BarOpen = false;
        If TrN = 0 Then TRv = B15H - B15L
        Else TRv = MaxList( B15H, PrevC15 ) - MinList( B15L, PrevC15 );
        TrN = TrN + 1;
        If TrN <= BO_ATRPeriod Then Begin
            TrSum = TrSum + TRv;
            If TrN = BO_ATRPeriod Then AtrV = TrSum / BO_ATRPeriod;
        End
        Else AtrV = ( AtrV * ( BO_ATRPeriod - 1 ) + TRv ) / BO_ATRPeriod;
        PrevC15 = B15C;

        If GotSwH Then Begin
            SwH = NewSwH; LastSwH = NewSwH; HaveSwH = true;
            SwHOpen = B15C < SwH and B15LastH < SwH;
            GotSwH = false;
        End;
        If GotSwL Then Begin
            SwL = NewSwL; LastSwL = NewSwL; HaveSwL = true;
            SwLOpen = B15C > SwL and B15LastL > SwL;
            GotSwL = false;
        End;

        Armed = false;
        If MarketPosition = 0 and TrN >= BO_ATRPeriod Then Begin
            AtrU = AtrV;
            LvlL = SwH; StpL = LastSwL;
            LvlS = SwL; StpS = LastSwH;
            OkL  = SwHOpen and HaveSwL and StpL < LvlL;
            OkS  = SwLOpen and HaveSwH and StpS > LvlS;
            Armed = UseBreakout and ( OkL or OkS ) and B15LastSm < FillEndSm - 1;
            If BO_VolCap > 0 and VolRatio > BO_VolCap Then Armed = false;
            ArmTrades = TotalTrades;
            If DebugLog and Armed Then
                Print( ELDateToString( Date ), " ", NumToStr( TimeC, 0 ), " BO arm",
                       "  L=", IffString( OkL, NumToStr( LvlL, 2 ), "-" ), " stp ", NumToStr( StpL, 2 ),
                       "  S=", IffString( OkS, NumToStr( LvlS, 2 ), "-" ), " stp ", NumToStr( StpS, 2 ),
                       "  ATR=", NumToStr( AtrU, 2 ), "  vol=", NumToStr( VolRatio, 2 ) );
        End;
    End;
End;
PrevSm = SmNow; PrevBkt = Bkt; PrevHIdx = HIdx;

{ ===== MORNING MOMENTUM: 10m buckets, oscillator, signal ===== }
If Date <> SLastDate Then Begin
    STradedToday = false;

    If SLastDate <> 0 Then Begin
        Sell       ( "MO-LX2" ) from entry ( "MO-L" ) this bar on close;
        BuyToCover ( "MO-SX2" ) from entry ( "MO-S" ) this bar on close;
    End;
    SLastDate = Date;
End;
SHalfDay = ( Month( Date ) = 7 and DayOfMonth( Date ) = 3 ) or ( Month( Date ) = 12 and DayOfMonth( Date ) = 24 )
        or ( Month( Date ) = 11 and DayOfWeek( Date ) = 5 and DayOfMonth( Date ) >= 23 and DayOfMonth( Date ) <= 29 );

SStartMin = Mod( TimeToMinutes( TimeC ) - 1 + 1440, 1440 );
SBk       = IntPortion( SStartMin / 10 );
SNewBk    = SBk <> SPrevBk or Date <> SBkDate;
SLate     = SNewBk and SOpen;
SFire     = 0;

For K = 1 to 2 Begin
    If K = 1 Then Begin
        SDo = SLate;
        FH = SH; FL = SL_; FC = SC; FN = SN; FEndT = SEndT;
    End
    Else Begin
        If SNewBk Then Begin
            SH = High; SL_ = Low; SN = 1; SOpen = true; SBkDate = Date;
        End
        Else Begin
            SH = MaxList( SH, High ); SL_ = MinList( SL_, Low ); SN = SN + 1;
        End;
        SC = Close;
        SEndT = MinutesToTime( ( SBk + 1 ) * 10 );
        If SBk = 143 Then SEndT = 0;
        SDo = SOpen and Mod( SStartMin + 1, 10 ) = 0;
        FH = SH; FL = SL_; FC = SC; FN = SN; FEndT = SEndT;
    End;

    If SDo Then Begin
        SOpen = false;
        SNB = SNB + 1;

        If SNB = 1 Then Begin
            Strv = FH - FL; SatrW = Strv; SPivot = FC;
        End
        Else Begin
            Strv   = MaxList( FH - FL, MaxList( AbsValue( FH - SPrevC ), AbsValue( FL - SPrevC ) ) );
            SatrW  = SatrW + ( Strv - SatrW ) / MO_RangeLen;
            SPivot = SPivot + ( FC - SPivot ) * AlphaPivot;
        End;
        SPrevC = FC;

        SSide = 0;
        If SatrW > 0 Then Begin
            SRaw = ( FC - SPivot ) / ( 3 * SatrW ) * 100;
            If SHaveOsc = false Then Begin
                SOscV = SRaw; SHaveOsc = true;
            End
            Else Begin
                SOscPrev = SOscV; SHavePrev = true;
                SOscV = SOscV + ( SRaw - SOscV ) * AlphaOsc;
            End;
            If SHavePrev Then Begin
                If SOscV > MO_Trigger and SOscPrev <= MO_Trigger Then SSide = 1
                Else If SOscV < -MO_Trigger and SOscPrev >= -MO_Trigger Then SSide = -1;
            End;
        End;

        If SSide <> 0 and FEndT >= MO_WindowStart and FEndT <= MO_WindowEnd
           and ( MO_FullBarsOnly = false or FN = 10 )
           and STradedToday = false and SHalfDay = false
           and MarketPosition = 0 and SNB >= MO_Warmup Then Begin
            STradedToday = true;
            If UseMomentum Then Begin
                If SSide = 1 and MO_AllowLong Then SFire = 1;
                If SSide = -1 and MO_AllowShort Then SFire = -1;
            End;
            If DebugLog Then
                Print( ELDateToString( Date ), " ", NumToStr( FEndT, 0 ), " MO side=", NumToStr( SSide, 0 ),
                       " osc=", NumToStr( SOscV, 1 ), " fire=", NumToStr( SFire, 0 ) );
        End;
    End;
End;
SPrevBk = SBk;

{ ===== MORNING MOMENTUM: entry (only while flat) ===== }
If SFire = 1 Then Begin
    Armed = false;
    Buy ( "MO-L" ) Qty contracts next bar at market;
End;
If SFire = -1 Then Begin
    Armed = false;
    SellShort ( "MO-S" ) Qty contracts next bar at market;
End;

{ ===== MORNING MOMENTUM: stop loss and timed exit ===== }
If MarketPosition = 1 Then
    Sell ( "MO-LS" ) from entry ( "MO-L" ) next bar at EntryPrice - MO_StopPoints stop;
If MarketPosition = -1 Then
    BuyToCover ( "MO-SS" ) from entry ( "MO-S" ) next bar at EntryPrice + MO_StopPoints stop;
If TimeC >= MO_ExitTime and TimeC <= 1600 Then Begin
    Sell       ( "MO-LX" ) from entry ( "MO-L" ) next bar at market;
    BuyToCover ( "MO-SX" ) from entry ( "MO-S" ) next bar at market;
End;

{ ===== SWING BREAKOUT: entry orders (only while flat) ===== }
If Armed and ( MarketPosition <> 0 or TotalTrades > ArmTrades ) Then Armed = false;

If Armed and MarketPosition = 0 and SmNow + 1 < FillEndSm Then Begin
    If OkL Then Buy       ( "BO-L" ) Qty contracts next bar at LvlL stop;
    If OkS Then SellShort ( "BO-S" ) Qty contracts next bar at LvlS stop;
End;

{ ===== SWING BREAKOUT: stop loss and take profit ===== }
If MarketPosition = 1 Then Begin
    If StpL >= EntryPrice Then
        Sell ( "BO-L0" ) from entry ( "BO-L" ) next bar at market
    Else Begin
        If BO_MaxStopMult > 0 Then
            Sell ( "BO-LS" ) from entry ( "BO-L" ) next bar at MaxList( StpL, EntryPrice - BO_MaxStopMult * AtrU ) stop
        Else
            Sell ( "BO-LS" ) from entry ( "BO-L" ) next bar at StpL stop;
        If BO_TargetMult > 0 Then
            Sell ( "BO-LT" ) from entry ( "BO-L" ) next bar at EntryPrice + BO_TargetMult * AtrU limit;
    End;
End;
If MarketPosition = -1 Then Begin
    If StpS <= EntryPrice Then
        BuyToCover ( "BO-S0" ) from entry ( "BO-S" ) next bar at market
    Else Begin
        If BO_MaxStopMult > 0 Then
            BuyToCover ( "BO-SS" ) from entry ( "BO-S" ) next bar at MinList( StpS, EntryPrice + BO_MaxStopMult * AtrU ) stop
        Else
            BuyToCover ( "BO-SS" ) from entry ( "BO-S" ) next bar at StpS stop;
        If BO_TargetMult > 0 Then
            BuyToCover ( "BO-ST" ) from entry ( "BO-S" ) next bar at EntryPrice - BO_TargetMult * AtrU limit;
    End;
End;

{ ===== SWING BREAKOUT: timed exit 15:45 CT ===== }
If SmNow + 1 >= FlatSm and SmNow < SessEndSm Then Begin
    Sell       ( "BO-LX" ) from entry ( "BO-L" ) this bar on close;
    BuyToCover ( "BO-SX" ) from entry ( "BO-S" ) this bar on close;
End;

SetExitOnClose;
