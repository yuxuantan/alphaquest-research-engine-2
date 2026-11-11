using System;
using System.Drawing;
using System.Linq;
using System.Reflection;
using PowerLanguage;
using Signal = PowerLanguage.Strategy.ORB_VWAP_CONT__NQ_1M_PIVOT_V01;

static class Program
{
    static int assertions;
    static DateTime Start = new DateTime(2024,1,16,9,1,0);
    static void Check(bool ok, string message) { assertions++; if(!ok) throw new Exception(message); }
    static void Set(Signal s, string name, object value)
    { typeof(Signal).GetField(name,BindingFlags.NonPublic|BindingFlags.Instance).SetValue(s,value); }
    static object Get(Signal s, string name)
    { return typeof(Signal).GetField(name,BindingFlags.NonPublic|BindingFlags.Instance).GetValue(s); }
    static Signal Setup(bool visual, bool shortSide, int retest, string calendar)
    {
        var s = new Signal(null) { ShowTradeValidation=visual, UseEODFlat=calendar!=null,
            SessionCalendarDirectory=calendar, PlotTradeLevels=false, RetestMode=retest,
            TradeLongs=!shortSide, TradeShorts=shortSide, ValidationHistoryBars=1000 };
        s.Initialize();
        // Explicit known pivots/finished ORB; no dependence on a platform's ADX or fill engine.
        s.Bars.Add(Start.AddMinutes(-1),100,100,100); s.Bars.CurrentBar=0;
        Set(s,"_firstBar",false);
        Set(s,"_orbReady",true); Set(s,"_orbHigh",105.0); Set(s,"_orbLow",95.0);
        Set(s,"_hasStopLow",true); Set(s,"_lastStopLow",90.0);
        Set(s,"_hasStopHigh",true); Set(s,"_lastStopHigh",110.0);
        Set(s,"_hasTargetHigh",true); Set(s,"_lastTargetHigh",120.0);
        Set(s,"_hasTargetLow",true); Set(s,"_lastTargetLow",80.0);
        if(retest==2) Set(s,shortSide?"_shortClosedThrough":"_longClosedThrough",true);
        return s;
    }
    static void Step(Signal s, DateTime time, bool shortSide, double position)
    {
        s.StrategyInfo.MarketPosition=position;
        s.Bars.Add(time,shortSide?102:112,shortSide?88:98,shortSide?92:108);
        s.Calculate();
    }
    static string Inspect(Signal s, int bar)
    {
        int current=s.Bars.CurrentBar;
        s.Bars.CurrentBar=bar; s.ExpertCommentary.AtCommentaryBar=true;
        int orders=s.OrderCreator.Sent.Count, lines=s.DrwTrendLine.Created.Count;
        object pv=Get(s,"_cumPV"), used=Get(s,"_tradesToday");
        s.Calculate();
        Check(orders==s.OrderCreator.Sent.Count && lines==s.DrwTrendLine.Created.Count,"inspection sends/draws nothing");
        Check(pv.Equals(Get(s,"_cumPV")) && used.Equals(Get(s,"_tradesToday")),"inspection preserves state");
        string text=s.ExpertCommentary.Written.Last();
        s.Bars.CurrentBar=current; s.ExpertCommentary.AtCommentaryBar=false;
        return text;
    }
    static void EntriesAndExits(string calendar)
    {
        foreach(bool shortSide in new[]{false,true}) foreach(int retest in new[]{1,2})
        {
            var on=Setup(true,shortSide,retest,calendar); var off=Setup(false,shortSide,retest,calendar);
            Step(on,Start,shortSide,0); Step(off,Start,shortSide,0);
            string side=shortSide?"Short":"Long";
            Check(on.OrderCreator.Sent.SequenceEqual(new[]{side+" market 1"}),"independent one-contract entry");
            string entry=Inspect(on,1);
            Check(entry.Contains("daily used BEFORE=0/1") && entry.Contains("retest latched=True reclaim signal=True"),"pre-clear gate snapshot");
            Check(entry.Contains("distance=18.00 reward=12.00") && entry.Contains("RR=0.67"),"independent risk/reward");
            Check(on.DrwTrendLine.Created.Count(l=>l.Color==Color.Red && l.Begin.Price==(shortSide?110:90))==1,"frozen SL plotted");
            Check(on.DrwTrendLine.Created.Count(l=>l.Color==Color.LimeGreen && l.Begin.Price==(shortSide?80:120))==1,"frozen TP plotted");
            double vwap=shortSide?94:106;
            Check(on.DrwTrendLine.Created.Any(l=>l.Color==Color.Goldenrod && l.End.Price==vwap),"independent HLC3 VWAP");
            Step(on,Start.AddMinutes(1),shortSide,shortSide?-1:1);
            Step(off,Start.AddMinutes(1),shortSide,shortSide?-1:1);
            string held=Inspect(on,2);
            Check(held.Contains("bracket submitted=True") && held.Contains("Submissions are not fills"),"bracket observation distinguished from fill");
            Check(on.OrderCreator.Sent.Contains(side+" SL "+(shortSide?"110.00":"90.00")+" 1"),"same frozen stop submitted");
            Step(on,Start.Date.AddHours(15).AddMinutes(55),shortSide,shortSide?-1:1);
            Step(off,Start.Date.AddHours(15).AddMinutes(55),shortSide,shortSide?-1:1);
            Check(Inspect(on,3).Contains("flatten submitted=True"),"cutoff flatten submitted, no bracket claimed");
            Check(on.OrderCreator.Sent.Last()==(shortSide?"EOD.S":"EOD.L")+" market 1","independent flatten order");
            Step(on,Start.Date.AddHours(15).AddMinutes(56),shortSide,0);
            Step(off,Start.Date.AddHours(15).AddMinutes(56),shortSide,0);
            Check(Inspect(on,4).Contains("Position observed "+(shortSide?"-1":"1")+" -> 0"),"flat observation recorded without invented exit cause");
            Check(on.OrderCreator.Sent.SequenceEqual(off.OrderCreator.Sent),"visuals on/off order parity");
            Check(off.DrwTrendLine.Created.Count==0 && off.DrwText.Created.Count==0,"disabled creates no drawings");
            Check(Inspect(on,1)==entry,"older entry inspection uses original snapshot");
        }
    }
    static void Rejections(string calendar)
    {
        foreach(string gate in new[]{"adx","rr","stop","quantity","pivot","daily","window","retest","calendar"})
        {
            var s=Setup(true,false,1,calendar);
            DateTime time=Start;
            if(gate=="adx") s.ADXElev_Thr=30;
            if(gate=="rr") s.MinRR=1;
            if(gate=="stop") s.MaxStopPoints=17;
            if(gate=="quantity") s.PositionSize=0;
            if(gate=="pivot") Set(s,"_hasTargetHigh",false);
            if(gate=="daily") s.MaxTradesPerDay=0;
            if(gate=="window") s.EntryStartTime=1000;
            if(gate=="retest") s.RetestMode=2;
            if(gate=="calendar") time=Start.Date.AddHours(15).AddMinutes(54);
            Step(s,time,false,0);
            Check(s.OrderCreator.Sent.Count==0,"reject "+gate);
            string text=Inspect(s,1);
            string expected=gate=="adx"?">= 30.00: False":gate=="quantity"?"quantity=0":
                gate=="pivot"?"target known=False":gate=="daily"?"daily used BEFORE=0/0":
                gate=="window"?"Entry window=False":gate=="retest"?"reclaim signal=False":
                gate=="calendar"?"calendar allows next-bar entry=False":"risk valid=False";
            Check(text.Contains(expected),"visible rejection "+gate);
        }
    }
    static void HistoryAndRestart()
    {
        var s=Setup(true,false,1,null); s.ValidationHistoryBars=2;
        Step(s,Start,false,0); Step(s,Start.AddMinutes(1),false,1); Step(s,Start.AddMinutes(2),false,1);
        Check(s.DrwTrendLine.Created.Take(5).All(l=>l.Deleted),"oldest frame lines pruned");
        Check(s.DrwText.Created.First().Deleted,"oldest frame entry label pruned");
        Check(Inspect(s,1).Contains("Outside retained validation history"),"expired history explicit");
        Check(Inspect(s,2).Contains("09:02"),"retained bar snapshot");
        int labels=s.DrwText.Created.Count;
        Step(s,Start.AddMinutes(3),false,1);
        Check(labels==s.DrwText.Created.Count,"held bracket refresh creates no repeated label");
        s.ShowTradeValidation=false; s.Restart();
        Check(s.DrwTrendLine.Created.All(l=>l.Deleted) && s.DrwText.Created.All(t=>t.Deleted),"restart/disable cleans owned drawings");
        var invalid=Setup(false,false,1,null); invalid.ShowTradeValidation=true; invalid.ValidationHistoryBars=0;
        bool rejected=false; try {invalid.Restart();} catch(ArgumentException) {rejected=true;}
        Check(rejected,"enabled nonpositive history rejects");
        var intrabar=Setup(true,false,1,null); intrabar.Bars.Add(Start,112,98,108); intrabar.Bars.Status=EBarState.Open; intrabar.Calculate();
        Check(intrabar.OrderCreator.Sent.Count==0 && intrabar.DrwTrendLine.Created.Count==0,"incomplete bar produces no order or drawings");
    }
    static void PullbackSizingAndWindows()
    {
        var defaults=new Signal(null);
        Check(!defaults.ShowTradeValidation && defaults.ValidationHistoryBars==1,"visuals opt in, lightweight default");
        foreach(bool shortSide in new[]{false,true})
        {
            var s=Setup(true,shortSide,1,null);
            s.StopMode=2; s.BufferMode=1; s.BufferAmount=4; s.UseVolSizing=true; s.Max_Contracts=3;
            Set(s,"_riskDollars",1000.0);
            Step(s,Start,shortSide,0);
            // Pullback 98/102, four 0.25 ticks => SL 97/103, distance 11.
            // floor(1000 / ((11 + 0.5) * 20)) = 4, capped at 3.
            Check(s.OrderCreator.Sent.Single()==(shortSide?"Short":"Long")+" market 3","independent pullback risk-sized order");
            Check(s.DrwTrendLine.Created.Any(l=>l.Color==Color.Red && l.Begin.Price==(shortSide?103:97)),"buffered pullback stop plotted");
            Check(Inspect(s,1).Contains("distance=11.00 reward=12.00"),"pullback snapshot distance");
        }
        var decay=Setup(true,false,1,null);
        ((PowerLanguage.Function.ADX)Get(decay,"_adx")).Previous=24;
        Step(decay,Start,false,0);
        Check(decay.OrderCreator.Sent.Count==0 && Inspect(decay,1).Contains("decay enabled=True: False"),"ADX decay rejection visible");
        var gaps=Setup(true,false,1,null);
        Step(gaps,Start,false,0); Step(gaps,Start.AddMinutes(1),false,0);
        var consecutive=gaps.DrwTrendLine.Created.Last(l=>l.Color==Color.Goldenrod);
        Check(consecutive.Begin.Time==Start && consecutive.End.Time==Start.AddMinutes(1),"consecutive VWAP closes joined");
        Step(gaps,Start.AddMinutes(3),false,0);
        Check(gaps.DrwTrendLine.Created.Last(l=>l.Color==Color.Goldenrod).Begin.Time==Start.AddMinutes(3),"VWAP gap not bridged");
        int count=gaps.DrwTrendLine.Created.Count(l=>l.Color==Color.Goldenrod);
        Step(gaps,Start.Date.AddHours(17).AddMinutes(1),false,0);
        Check(count==gaps.DrwTrendLine.Created.Count(l=>l.Color==Color.Goldenrod),"VWAP hidden outside window");
        Step(gaps,Start.Date.AddHours(23).AddMinutes(1),false,0);
        Check(Inspect(gaps,5).Contains("ORB building=False ready=False"),"reset clears ORB readiness");
    }
    static void LightweightAndOff()
    {
        var on=Setup(true,false,1,null); on.ValidationHistoryBars=1;
        var off=Setup(false,false,1,null);
        for(int i=0; i<1000; i++)
        {
            Step(on,Start.AddMinutes(i),false,i==0?0:1);
            Step(off,Start.AddMinutes(i),false,i==0?0:1);
            Check(on.DrwTrendLine.Created.Count(l=>!l.Deleted)<=5,"live view has at most five surviving line segments");
            Check(on.DrwText.Created.Count(t=>!t.Deleted)<=2,"live view has at most two surviving text objects");
        }
        Check(((System.Collections.ICollection)Get(on,"_validationByBar")).Count==1,"live snapshot history stays at one after 1000 bars");
        Check(((System.Collections.ICollection)Get(off,"_validationByBar")).Count==0,"off retains zero snapshots");
        Check(off.DrwTrendLine.Created.Count==0 && off.DrwText.Created.Count==0 && off.ExpertCommentary.Written.Count==0,
            "off makes zero drawing/commentary calls across 1000 bars");
        Check(on.OrderCreator.Sent.SequenceEqual(off.OrderCreator.Sent),"live mode and off submit identical orders across 1000 bars");
        Check(Get(on,"_cumPV").Equals(Get(off,"_cumPV")) && Get(on,"_tradesToday").Equals(Get(off,"_tradesToday")),
            "live mode and off retain same numerical state");
    }
    static void Main(string[] args)
    {
        EntriesAndExits(args[0]); Rejections(args[0]); HistoryAndRestart(); PullbackSizingAndWindows(); LightweightAndOff();
        Console.WriteLine("PASS: "+assertions+" assertions; actual signal compiled with C# 5 against test doubles. MC host/SDK/rendering/fills NOT verified.");
    }
}
