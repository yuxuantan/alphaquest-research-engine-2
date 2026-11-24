{ ==========================================================================
  RELATIVE STRENGTH NQ / ES  -  RelStrength_v3   (order prefix RS)
  NQ against its ES beta, intraday continuation, long and short
  --------------------------------------------------------------------------
  INSTRUMENT   NQ futures, continuous contract (Data1: orders go here)
               ES futures, continuous contract (Data2: signal only)
  CHART        Data1 = @NQ#C, Data2 = @ES#C (IQFeed names; on another feed
               use its continuous NQ and ES). BOTH 1-MINUTE bars, from the
               same feed, same session template, same time zone. Add ES to
               the NQ chart as its second data series.
               The Bridge's own bars (ofb_bars_NQ.csv) are NQ only and
               keyed Eastern, so they cannot be Data1 here.
  SESSION      24h CME Globex session template, bars stamped with their
               CLOSE time (MultiCharts default)
  TIME ZONE    Exchange = Central Time (CT). The first RTH bar must read
               0831. RthStartHHMM / RthEndHHMM (08:30-15:00), DecideHHMM
               and FlatHHMM are all CT. On an Eastern chart (first RTH bar
               0931) move the CHART to Exchange: every window is an hour
               out otherwise, with no error.
  PROPERTIES   Intrabar Order Generation OFF, Bar Magnifier not needed
               (1-minute chart), Max Bars Back auto (it looks back 1 bar)
  FUNCTIONS    None. Plain PowerLanguage, no OFB_ calls.
  HISTORY      Load at least 3 months before the test period. The first
               trade can come after 5 RTH days, but the beta and variance
               averages start from a single bar and need about 40 RTH days
               to settle, and the average range needs AtrDays (20) days.
  HOLIDAYS     NYSE full holidays and early-close sessions 2010-2027 are
               skipped (SkipHolidays = true). The table ENDS with 2027:
               from 1 Jan 2028 no holiday or half day is skipped until the
               2028 dates are added to HolFull / HolEarly. To add a year:
               append its NYSE dates in the same YYYMMDD form (year minus
               1900, e.g. 1280117 = 17 Jan 2028), in date order, after the
               last entry, and raise NHolF / NHolE by the number added
               (the arrays hold 200 and 60).
  COSTS        Set commission and slippage in Strategy Properties. None
               are in the code.
  SIZE         NumContracts = 1. The stop is 0.6 x the 20-day average RTH
               range. On NQ, Jan-Jul 2026, that range ran 253-671 points
               (median 375), so one stop-out cost 150-400 points: $3,000-
               8,000 per NQ, $300-800 per MNQ. One NQ can lose more than a
               50K prop account's whole drawdown in one trade: use MNQ.
  SIGNAL       At DecideHHMM (09:00 CT) it measures how far NQ has moved
               since the 08:30 CT open beyond what its ES beta explains,
               as a Z score: (NQ log return - beta x ES log return) over
               the residual's spread for that many 1-minute bars. Beta and
               residual variance come from 1-minute RTH returns, averaged
               over BetaDays (20) RTH days.
               Z >= ZMin (1.25): buy NQ.  Z <= -ZMin: sell NQ short.
               Entry next bar at market. One check and one trade a day.
  EXITS        Stop StopFrac (0.6) and target TgtFrac (1.0) x the average
               RTH range (high - low) of the last AtrDays (20) clean RTH
               days, set from the entry price. Flat at FlatHHMM (15:00 CT)
               on that bar's close; anything still open outside RTH is
               closed the same way.
  DIRECTION    TradeDir 0 = both sides, 1 = long only, -1 = short only
  ORDERS       RS.L / RS.S entries, RS.LS / RS.SS stops, RS.LT / RS.ST
               targets, RS.LF / RS.SF flat at the close
  ========================================================================== }
Inputs:
	DecideHHMM(900),      { CT, check time }
	ZMin(1.25),           { entry threshold }
	BetaDays(20),         { days for beta and variance }
	StopFrac(0.6),        { stop, x average RTH range }
	TgtFrac(1.0),         { target, x average RTH range }
	AtrDays(20),          { days in the average RTH range }
	TradeDir(0),          { 0 = both sides, 1 = long only, -1 = short only }
	NumContracts(1),
	RthStartHHMM(830),    { CT }
	RthEndHHMM(1500),     { CT }
	FlatHHMM(1500),       { CT, flat this bar on close }
	SkipHolidays(true);   { skip NYSE holidays and early-close sessions }

Vars:
	CalInit(false), DayOK(true), jj(0), NHolF(0), NHolE(0), TickSz(0),
	MinNow(0), RthStartMin(0), RthEndMin(0), RthOn(false), NewRTH(false),
	MP(0), EntToday(0),
	RthHi(0), RthLo(0), RthCls(0), HaveRth(false), LastRthOK(false),
	PDHi(0), PDLo(0), PDCls(0), HavePD(false), DPtr(0), DCnt(0), AvgDRng(0), DSum(0), AtrUse(20),
	C2(0), RetA(0), RetB(0), AlphaE(0), CovE(0), VarE1(0), VarE2(0), BetaE(0), ResE(0),
	NEst(0), BarsDay(78), Anc1(0), Anc2(0), NBA(0), Decided(true), RelX(0), ZRel(0),
	SigDir(0), StopPx(0), TgtPx(0);

Arrays:
	HolFull[200](0), HolEarly[60](0),
	DRng[60](0);

if CalInit = false then begin
	TickSz = MinMove / PriceScale;
	RthStartMin = IntPortion(RthStartHHMM * 0.01) * 60 + Mod(RthStartHHMM, 100);
	RthEndMin = IntPortion(RthEndHHMM * 0.01) * 60 + Mod(RthEndHHMM, 100);
	{ NYSE full holidays 2010-2027, YYYMMDD }
	HolFull[0] = 1100101; HolFull[1] = 1100118; HolFull[2] = 1100215; HolFull[3] = 1100402; HolFull[4] = 1100531; HolFull[5] = 1100705;
	HolFull[6] = 1100906; HolFull[7] = 1101125; HolFull[8] = 1101224; HolFull[9] = 1110117; HolFull[10] = 1110221; HolFull[11] = 1110422;
	HolFull[12] = 1110530; HolFull[13] = 1110704; HolFull[14] = 1110905; HolFull[15] = 1111124; HolFull[16] = 1111226; HolFull[17] = 1120102;
	HolFull[18] = 1120116; HolFull[19] = 1120220; HolFull[20] = 1120406; HolFull[21] = 1120528; HolFull[22] = 1120704; HolFull[23] = 1120903;
	HolFull[24] = 1121029; HolFull[25] = 1121030; HolFull[26] = 1121122; HolFull[27] = 1121225; HolFull[28] = 1130101; HolFull[29] = 1130121;
	HolFull[30] = 1130218; HolFull[31] = 1130329; HolFull[32] = 1130527; HolFull[33] = 1130704; HolFull[34] = 1130902; HolFull[35] = 1131128;
	HolFull[36] = 1131225; HolFull[37] = 1140101; HolFull[38] = 1140120; HolFull[39] = 1140217; HolFull[40] = 1140418; HolFull[41] = 1140526;
	HolFull[42] = 1140704; HolFull[43] = 1140901; HolFull[44] = 1141127; HolFull[45] = 1141225; HolFull[46] = 1150101; HolFull[47] = 1150119;
	HolFull[48] = 1150216; HolFull[49] = 1150403; HolFull[50] = 1150525; HolFull[51] = 1150703; HolFull[52] = 1150907; HolFull[53] = 1151126;
	HolFull[54] = 1151225; HolFull[55] = 1160101; HolFull[56] = 1160118; HolFull[57] = 1160215; HolFull[58] = 1160325; HolFull[59] = 1160530;
	HolFull[60] = 1160704; HolFull[61] = 1160905; HolFull[62] = 1161124; HolFull[63] = 1161226; HolFull[64] = 1170102; HolFull[65] = 1170116;
	HolFull[66] = 1170220; HolFull[67] = 1170414; HolFull[68] = 1170529; HolFull[69] = 1170704; HolFull[70] = 1170904; HolFull[71] = 1171123;
	HolFull[72] = 1171225; HolFull[73] = 1180101; HolFull[74] = 1180115; HolFull[75] = 1180219; HolFull[76] = 1180330; HolFull[77] = 1180528;
	HolFull[78] = 1180704; HolFull[79] = 1180903; HolFull[80] = 1181122; HolFull[81] = 1181205; HolFull[82] = 1181225; HolFull[83] = 1190101;
	HolFull[84] = 1190121; HolFull[85] = 1190218; HolFull[86] = 1190419; HolFull[87] = 1190527; HolFull[88] = 1190704; HolFull[89] = 1190902;
	HolFull[90] = 1191128; HolFull[91] = 1191225; HolFull[92] = 1200101; HolFull[93] = 1200120; HolFull[94] = 1200217; HolFull[95] = 1200410;
	HolFull[96] = 1200525; HolFull[97] = 1200703; HolFull[98] = 1200907; HolFull[99] = 1201126; HolFull[100] = 1201225; HolFull[101] = 1210101;
	HolFull[102] = 1210118; HolFull[103] = 1210215; HolFull[104] = 1210402; HolFull[105] = 1210531; HolFull[106] = 1210705; HolFull[107] = 1210906;
	HolFull[108] = 1211125; HolFull[109] = 1211224; HolFull[110] = 1220117; HolFull[111] = 1220221; HolFull[112] = 1220415; HolFull[113] = 1220530;
	HolFull[114] = 1220620; HolFull[115] = 1220704; HolFull[116] = 1220905; HolFull[117] = 1221124; HolFull[118] = 1221226; HolFull[119] = 1230102;
	HolFull[120] = 1230116; HolFull[121] = 1230220; HolFull[122] = 1230407; HolFull[123] = 1230529; HolFull[124] = 1230619; HolFull[125] = 1230704;
	HolFull[126] = 1230904; HolFull[127] = 1231123; HolFull[128] = 1231225; HolFull[129] = 1240101; HolFull[130] = 1240115; HolFull[131] = 1240219;
	HolFull[132] = 1240329; HolFull[133] = 1240527; HolFull[134] = 1240619; HolFull[135] = 1240704; HolFull[136] = 1240902; HolFull[137] = 1241128;
	HolFull[138] = 1241225; HolFull[139] = 1250101; HolFull[140] = 1250109; HolFull[141] = 1250120; HolFull[142] = 1250217; HolFull[143] = 1250418;
	HolFull[144] = 1250526; HolFull[145] = 1250619; HolFull[146] = 1250704; HolFull[147] = 1250901; HolFull[148] = 1251127; HolFull[149] = 1251225;
	HolFull[150] = 1260101; HolFull[151] = 1260119; HolFull[152] = 1260216; HolFull[153] = 1260403; HolFull[154] = 1260525; HolFull[155] = 1260619;
	HolFull[156] = 1260703; HolFull[157] = 1260907; HolFull[158] = 1261126; HolFull[159] = 1261225; HolFull[160] = 1270101; HolFull[161] = 1270118;
	HolFull[162] = 1270215; HolFull[163] = 1270326; HolFull[164] = 1270531; HolFull[165] = 1270618; HolFull[166] = 1270705; HolFull[167] = 1270906;
	HolFull[168] = 1271125; HolFull[169] = 1271224;
	NHolF = 170;
	{ NYSE early-close sessions 2010-2027, YYYMMDD }
	HolEarly[0] = 1101126; HolEarly[1] = 1111125; HolEarly[2] = 1120703; HolEarly[3] = 1121123; HolEarly[4] = 1121224; HolEarly[5] = 1130703;
	HolEarly[6] = 1131129; HolEarly[7] = 1131224; HolEarly[8] = 1140703; HolEarly[9] = 1141128; HolEarly[10] = 1141224; HolEarly[11] = 1151127;
	HolEarly[12] = 1151224; HolEarly[13] = 1161125; HolEarly[14] = 1170703; HolEarly[15] = 1171124; HolEarly[16] = 1180703; HolEarly[17] = 1181123;
	HolEarly[18] = 1181224; HolEarly[19] = 1190703; HolEarly[20] = 1191129; HolEarly[21] = 1191224; HolEarly[22] = 1201127; HolEarly[23] = 1201224;
	HolEarly[24] = 1211126; HolEarly[25] = 1221125; HolEarly[26] = 1230703; HolEarly[27] = 1231124; HolEarly[28] = 1240703; HolEarly[29] = 1241129;
	HolEarly[30] = 1241224; HolEarly[31] = 1250703; HolEarly[32] = 1251128; HolEarly[33] = 1251224; HolEarly[34] = 1261127; HolEarly[35] = 1261224;
	HolEarly[36] = 1271126;
	NHolE = 37;
	CalInit = true;
end;
{ calendar check once per calendar date: holidays and early closes are skipped }
if Date <> Date[1] or CurrentBar = 1 then begin
	EntToday = 0;
	DayOK = true;
	if SkipHolidays then begin
		for jj = 0 to NHolF - 1 begin
			if HolFull[jj] = Date then DayOK = false;
		end;
		for jj = 0 to NHolE - 1 begin
			if HolEarly[jj] = Date then DayOK = false;
		end;
	end;
end;
{ RTH by time crossing on a Globex chart in exchange time (CT), close-stamped bars }
MinNow = IntPortion(Time * 0.01) * 60 + Mod(Time, 100);
RthOn = Time > RthStartHHMM and Time <= RthEndHHMM;
NewRTH = RthOn and (Time[1] <= RthStartHHMM or Time[1] > RthEndHHMM or Date <> Date[1]);
MP = MarketPosition;
C2 = Close of Data2;

{ new entry: stop and target from the entry price }
if MP <> 0 and MP <> MP[1] then begin
	EntToday = EntToday + 1;
	if MP = 1 then begin
		StopPx = EntryPrice - StopFrac * AvgDRng;
		TgtPx = EntryPrice + TgtFrac * AvgDRng;
	end
	else begin
		StopPx = EntryPrice + StopFrac * AvgDRng;
		TgtPx = EntryPrice - TgtFrac * AvgDRng;
	end;
end;

BarsDay = MaxList(IntPortion((RthEndMin - RthStartMin) / BarInterval), 1);
AlphaE = 2 / (BetaDays * BarsDay + 1);

{ new RTH day: average range; anchors = closes of the last bar before the open }
if NewRTH then begin
	{ close the previous RTH day: prior-day levels and the average RTH range }
	AtrUse = MinList(MaxList(AtrDays, 1), 60);
	if HaveRth and LastRthOK then begin
		PDHi = RthHi;
		PDLo = RthLo;
		PDCls = RthCls;
		HavePD = true;
		DRng[DPtr] = RthHi - RthLo;
		DPtr = Mod(DPtr + 1, AtrUse);
		if DCnt < AtrUse then DCnt = DCnt + 1;
	end;
	DSum = 0;
	for jj = 0 to DCnt - 1 begin
		DSum = DSum + DRng[jj];
	end;
	if DCnt > 0 then AvgDRng = DSum / DCnt;
	RthHi = High;
	RthLo = Low;
	RthCls = Close;
	HaveRth = true;
	LastRthOK = DayOK;
	Anc1 = Close[1];
	Anc2 = C2[1];
	NBA = 0;
	Decided = false;
end
else if RthOn then begin
	RthHi = MaxList(RthHi, High);
	RthLo = MinList(RthLo, Low);
	RthCls = Close;
end;
if RthOn and Anc1 > 0 then NBA = NBA + 1;

{ bar-return moments from RTH bars in bp: beta of Data1 on Data2, residual variance }
if RthOn and DayOK and Close[1] > 0 and C2[1] > 0 and C2 > 0 then begin
	RetA = 10000 * Log(Close / Close[1]);
	RetB = 10000 * Log(C2 / C2[1]);
	if NEst = 0 then begin
		CovE = RetA * RetB;
		VarE1 = Square(RetA);
		VarE2 = Square(RetB);
	end
	else begin
		CovE = CovE + AlphaE * (RetA * RetB - CovE);
		VarE1 = VarE1 + AlphaE * (Square(RetA) - VarE1);
		VarE2 = VarE2 + AlphaE * (Square(RetB) - VarE2);
	end;
	NEst = NEst + 1;
	if VarE1 > 0 and VarE2 > 0 then begin
		BetaE = CovE / VarE2;
		ResE = VarE1 - 2 * BetaE * CovE + Square(BetaE) * VarE2;
	end;
end;

{ one check at DecideHHMM: Z of the relative move since the open }
SigDir = 0;
if RthOn and Decided = false and Time >= DecideHHMM then begin
	Decided = true;
	if DayOK and NBA >= 1 and NEst >= 5 * BarsDay and ResE > 0
		and Anc1 > 0 and Anc2 > 0 and C2 > 0 then begin
		RelX = 10000 * Log(Close / Anc1) - BetaE * 10000 * Log(C2 / Anc2);
		ZRel = RelX / SquareRoot(ResE * NBA);
		if ZRel >= ZMin then SigDir = 1;
		if ZRel <= -ZMin then SigDir = -1;
	end;
end;

if SigDir <> 0 and MP = 0 and EntToday = 0 and Time < FlatHHMM then begin
	if SigDir = 1 and TradeDir >= 0 then Buy ("RS.L") NumContracts contracts next bar at market;
	if SigDir = -1 and TradeDir <= 0 then SellShort ("RS.S") NumContracts contracts next bar at market;
end;

{ exits: stop and target }
if MP = 1 then begin
	if StopFrac > 0 and AvgDRng > 0 then Sell ("RS.LS") next bar at StopPx stop;
	if TgtFrac > 0 and AvgDRng > 0 then Sell ("RS.LT") next bar at TgtPx limit;
end;
if MP = -1 then begin
	if StopFrac > 0 and AvgDRng > 0 then BuyToCover ("RS.SS") next bar at StopPx stop;
	if TgtFrac > 0 and AvgDRng > 0 then BuyToCover ("RS.ST") next bar at TgtPx limit;
end;

{ flat by FlatHHMM; also closes anything still open outside RTH }
if MP <> 0 and (Time >= FlatHHMM or Time <= RthStartHHMM) then begin
	if MP = 1 then Sell ("RS.LF") this bar on close;
	if MP = -1 then BuyToCover ("RS.SF") this bar on close;
end;
