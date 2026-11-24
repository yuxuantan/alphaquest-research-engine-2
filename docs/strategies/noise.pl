{ ==========================================================================
  INSTRUMENT   NQ futures
  TIMEFRAME    15 minutes
  TIME ZONE    Exchange time, Central (CT)
  ========================================================================== }

Inputs:
    LookbackDays(20),
    VolatilityMultiplier(1.0),
    EMALength(20),

    StopLossPoints(50),
    ContractsPerTrade(2),
    RewardRisk(0.5),

    LongTrade(true),
    ShortTrade(true),

    MaxTradesPerDay(10),
    MaxStopsPerDay(3),

    FirstEvalTime(0900),
    LastEntryTime(1400),
    FlatSignalTime(1430);


Vars:
    TodayOpen(0),
    PrevClose(0),

    CurrentHour(0),
    CurrentMinute(0),
    CurrentMinutes(0),

    FirstHour(0),
    FirstMinute(0),
    FirstMinutes(0),

    Slot(0),
    HistIndex(0),

    MoveToday(0),
    SumMove(0),
    AvgMove(0),

    UpperBase(0),
    LowerBase(0),

    UpperBand(0),
    LowerBand(0),

    EMAValue(0),

    LongTrail(0),
    ShortTrail(0),

    HistLoop(0),
    ShiftLoop(0),

    StopDollarsPerPosition(0),

    TradesToday(0),
    StopsToday(0),
    LastTotalTrades(0),

    EnoughData(false);


Arrays:
    MoveHistory[2200](0),
    SlotCount[22](0);


StopDollarsPerPosition =
    StopLossPoints *
    BigPointValue *
    ContractsPerTrade;


if ContractsPerTrade >= 1 then
begin

    SetStopContract;

    SetStopLoss(
        StopLossPoints *
        BigPointValue
    );

    SetProfitTarget(
        StopLossPoints *
        BigPointValue *
        RewardRisk
    );

end;


if CurrentBar = 1 then
begin

    LastTotalTrades = TotalTrades;

end;


if Date <> Date[1] then
begin

    TodayOpen = Open;

    if CurrentBar > 1 then
        PrevClose = Close[1];

    TradesToday = 0;
    StopsToday = 0;

    LastTotalTrades = TotalTrades;

end;


if TotalTrades > LastTotalTrades then
begin

    if PositionProfit(1) <= -StopDollarsPerPosition then
        StopsToday = StopsToday + 1;

    LastTotalTrades = TotalTrades;

end;


EMAValue =
    XAverage(
        Close,
        EMALength
    );


CurrentHour =
    IntPortion(Time / 100);

CurrentMinute =
    Time - CurrentHour * 100;

CurrentMinutes =
    CurrentHour * 60 +
    CurrentMinute;


FirstHour =
    IntPortion(FirstEvalTime / 100);

FirstMinute =
    FirstEvalTime - FirstHour * 100;

FirstMinutes =
    FirstHour * 60 +
    FirstMinute;


if Time >= FirstEvalTime and
   Time <= FlatSignalTime and
   TodayOpen > 0 and
   PrevClose > 0 then
begin

    Slot =
        IntPortion(
            (CurrentMinutes - FirstMinutes) / 15
        ) + 1;


    if Slot >= 1 and
       Slot <= 22 then
    begin

        MoveToday =
            AbsValue(
                Close / TodayOpen - 1
            );


        SumMove = 0;
        EnoughData = false;


        if SlotCount[Slot] >= LookbackDays then
        begin

            EnoughData = true;


            for HistLoop = 1 to LookbackDays
            begin

                HistIndex =
                    (Slot - 1) * 100 +
                    HistLoop;

                SumMove =
                    SumMove +
                    MoveHistory[HistIndex];

            end;


            AvgMove =
                SumMove /
                LookbackDays;


            UpperBase =
                MaxList(
                    TodayOpen,
                    PrevClose
                );


            LowerBase =
                MinList(
                    TodayOpen,
                    PrevClose
                );


            UpperBand =
                UpperBase *
                (
                    1 +
                    AvgMove *
                    VolatilityMultiplier
                );


            LowerBand =
                LowerBase *
                (
                    1 -
                    AvgMove *
                    VolatilityMultiplier
                );


            LongTrail =
                MaxList(
                    UpperBand,
                    EMAValue
                );


            ShortTrail =
                MinList(
                    LowerBand,
                    EMAValue
                );


            if Time < FlatSignalTime then
            begin

                if MarketPosition = 0 and
                   ContractsPerTrade >= 1 and
                   TradesToday < MaxTradesPerDay and
                   StopsToday < MaxStopsPerDay then
                begin

                    if Time <= LastEntryTime then
                    begin

                        if LongTrade = true and
                           Close > UpperBand and
                           Close > Open then
                        begin

                            Buy ("NoiseLong")
                                ContractsPerTrade contracts
                                next bar at market;

                            TradesToday =
                                TradesToday + 1;

                        end

                        else if ShortTrade = true and
                                Close < LowerBand and
                                Close < Open then
                        begin

                            SellShort ("NoiseShort")
                                ContractsPerTrade contracts
                                next bar at market;

                            TradesToday =
                                TradesToday + 1;

                        end;

                    end;

                end;


                if MarketPosition = 1 then
                begin

                    if Time <= LastEntryTime and
                       ShortTrade = true and
                       Close < LowerBand and
                       Close < Open then
                    begin

                        Sell ("LongRevExit")
                            next bar at market;


                        if ContractsPerTrade >= 1 and
                           TradesToday < MaxTradesPerDay and
                           StopsToday < MaxStopsPerDay then
                        begin

                            SellShort ("RevToShort")
                                ContractsPerTrade contracts
                                next bar at market;

                            TradesToday =
                                TradesToday + 1;

                        end;

                    end

                    else if Close < LongTrail then
                    begin

                        Sell ("LongEMAExit")
                            next bar at market;

                    end;

                end;


                if MarketPosition = -1 then
                begin

                    if Time <= LastEntryTime and
                       LongTrade = true and
                       Close > UpperBand and
                       Close > Open then
                    begin

                        BuyToCover ("ShortRevExit")
                            next bar at market;


                        if ContractsPerTrade >= 1 and
                           TradesToday < MaxTradesPerDay and
                           StopsToday < MaxStopsPerDay then
                        begin

                            Buy ("RevToLong")
                                ContractsPerTrade contracts
                                next bar at market;

                            TradesToday =
                                TradesToday + 1;

                        end;

                    end

                    else if Close > ShortTrail then
                    begin

                        BuyToCover ("ShortEMAExit")
                            next bar at market;

                    end;

                end;

            end;

        end;


        for ShiftLoop = 100 downto 2
        begin

            MoveHistory[
                (Slot - 1) * 100 +
                ShiftLoop
            ]
            =
            MoveHistory[
                (Slot - 1) * 100 +
                ShiftLoop - 1
            ];

        end;


        MoveHistory[
            (Slot - 1) * 100 + 1
        ]
        =
        MoveToday;


        if SlotCount[Slot] < 100 then
            SlotCount[Slot] =
                SlotCount[Slot] + 1;

    end;

end;


if Time = FlatSignalTime then
begin

    if MarketPosition = 1 then
        Sell ("FlatLong1430")
            next bar at market;


    if MarketPosition = -1 then
        BuyToCover ("FlatShort1430")
            next bar at market;

end;
