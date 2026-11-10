using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using AlphaQuest.Twin;

class Program
{
    class Segment
    {
        public DateTime Start, End;
        public double Price;
        public bool High, Finished, Deleted;
    }
    class Drawings
    {
        public readonly List<Segment> Created = new List<Segment>();
        public readonly OpenSwingLines<Segment> Lines;
        public int Operations;
        public Drawings(int limit)
        {
            Lines = new OpenSwingLines<Segment>(limit,
                delegate(DateTime t, double p, bool h) {
                    Operations++;
                    var s = new Segment { Start=t, Price=p, High=h };
                    Created.Add(s); return s;
                },
                delegate(Segment s, DateTime t) { Operations++; s.End=t; s.Finished=true; },
                delegate(Segment s) { Check(!s.Deleted,"no duplicate deletion"); Operations++; s.Deleted=true; });
        }
    }
    static int assertions;
    static void Check(bool ok, string message)
    { assertions++; if (!ok) throw new Exception(message); }

    static object ConfirmedSource(int timeframe)
    {
        var c = new TwinCore { BO_PivotTF=timeframe, UseMomentum=false };
        var d = new Drawings(0);
        var t = new DateTime(2024,1,15,17,1,0);
        double[] highs = {104,105,106,110,106,105,104};
        double[] lows = {96,95,94,90,94,95,96};
        int bars=0;
        for (int candle=0; candle<7; candle++)
        {
            // The fourth six-hour candle is shortened by the 16:00 session end.
            int minutes = timeframe==360 && candle==3 ? 300 : timeframe;
            for (int i=0; i<minutes; i++)
            {
                if (t.Hour==16 && t.Minute==1) t=t.AddHours(1);
                c.Step(t,highs[candle],lows[candle],100,0,0,0);
                d.Lines.Update(c,t); bars++;
                if (candle<6 || i<minutes-1) Check(d.Created.Count==0,"no drawing before three right candles close");
                t=t.AddMinutes(1);
            }
        }
        Check(d.Created.Count==2,"exactly two confirmed open levels");
        Check(d.Created[0].High && d.Created[0].Price==110,"independent swing high 110");
        Check(!d.Created[1].High && d.Created[1].Price==90,"independent swing low 90");
        Check(d.Created.All(s=>s.Start==t.AddMinutes(-1)),"start at activation, no pivot backdating");
        int operations=d.Operations;
        for (int i=0; i<100000; i++) d.Lines.Update(c,t);
        Check(d.Operations==operations,"unchanged state performs no drawing operations");
        c.Step(t,110,99,100,0,0,0); d.Lines.Update(c,t);
        Check(d.Created[0].Deleted && !d.Created[1].Deleted,"equal high touch closes high only");
        t=t.AddMinutes(1);
        c.Step(t,101,90,100,0,0,0); d.Lines.Update(c,t);
        Check(d.Created.All(s=>s.Deleted),"equal low touch closes low");
        d.Lines.Clear();
        return new {timeframe=timeframe, bars=bars, high=110, low=90, no_op_updates=100000};
    }

    static void HistoryAndRecalculation()
    {
        var d=new Drawings(2);
        var c=new TwinCore { HaveSwH=true, SwHOpen=true, SwH=110, HaveSwL=true, SwLOpen=true, SwL=90 };
        var t=new DateTime(2024,1,16,11,0,0);
        d.Lines.Update(c,t);
        for (int i=1; i<=100; i++)
        {
            c.SwH=110+i;
            d.Lines.Update(c,t.AddMinutes(i));
            Check(d.Created.Count(s=>!s.Deleted && s.Finished)<=2,"history cap enforced");
            Check(d.Created.Count(s=>!s.Deleted && !s.Finished)==2,"two active drawings");
        }
        Check(d.Created[0].Deleted,"oldest history pruned");
        var previous=d.Created[d.Created.Count-2];
        Check(previous.Finished && previous.End==t.AddMinutes(100),"replacement ends segment at observed activation");
        c.SwHOpen=false; d.Lines.Update(c,t.AddMinutes(101));
        c.SwHOpen=true; d.Lines.Update(c,t.AddMinutes(102));
        Check(d.Created.Last().Start==t.AddMinutes(102),"same-price reopen starts a new segment");
        d.Lines.Clear();
        Check(d.Created.All(s=>s.Deleted),"recalculation cleans active and historical drawings");
        d.Lines.Clear();
        foreach (int limit in new int[] {-2,int.MinValue})
        {
            bool rejected=false;
            try { new Drawings(limit); } catch (ArgumentOutOfRangeException) { rejected=true; }
            Check(rejected,"out of bound history rejected");
        }
    }

    static object UnlimitedHistory()
    {
        var d=new Drawings(-1);
        var c=new TwinCore { HaveSwH=true, SwHOpen=true, SwH=110 };
        var t=new DateTime(2024,1,16,11,0,0);
        d.Lines.Update(c,t);
        for(int i=1;i<=1500;i++)
        {
            c.SwH=110+i;
            d.Lines.Update(c,t.AddDays(i));
        }
        Check(d.Created.Count==1501 && d.Created.All(s=>!s.Deleted),"unlimited mode retains all segments beyond previous count limit across years");
        Check(d.Created.Count(s=>s.Finished)==1500,"old segments end, only latest extends");
        Check(d.Created[0].Start==t && d.Created[0].End==t.AddDays(1),"oldest segment keeps original confirmation/replacement timestamps");
        d.Lines.Clear();
        Check(d.Created.All(s=>s.Deleted),"unlimited history also clears on recalculation");
        var finite=new Drawings(1001);
        finite.Lines.Clear();
        return new {history_limit=-1, completed_segments=1500, active_segments=1, all_retained=true};
    }

    static void ReadOnlyState()
    {
        var c=new TwinCore { HaveSwH=true, SwHOpen=true, SwH=123, HaveSwL=true, SwLOpen=false, SwL=98 };
        var options=new JsonSerializerOptions { IncludeFields=true };
        string before=JsonSerializer.Serialize(c,options);
        var d=new Drawings(1);
        d.Lines.Update(c,DateTime.Today); d.Lines.Clear();
        Check(before==JsonSerializer.Serialize(c,options),"drawing lifecycle does not mutate any signal state");
        Check(d.Created.Count==1,"broken low is not drawn");
        var absent=new TwinCore { SwHOpen=true, SwLOpen=true };
        var none=new Drawings(0); none.Lines.Update(absent,DateTime.Today);
        Check(none.Created.Count==0,"no drawing without a confirmed level");
    }

    static object MomentumDiagnostics(bool partial, bool allowPartial)
    {
        var c=new TwinCore { MO_BasisLen=3, MO_RangeLen=1, MO_SignalLen=1, MO_Trigger=10,
            MO_Warmup=2, MO_FullBarsOnly=!allowPartial, UseBreakout=false };
        var observed=new List<string>();
        c.MomentumValidation=delegate(string text, bool crossing) { if(crossing) observed.Add(text); };
        var start=new DateTime(2024,1,16,8,21,0);
        List<TwinOrder> orders=null;
        for(int i=0; i<20; i++)
        {
            if(partial && i==19) continue;
            orders=c.Step(start.AddMinutes(i),i<10?101:111,i<10?99:100,i<10?100:110,0,0,0);
        }
        if(partial) orders=c.Step(start.AddMinutes(20),111,100,110,0,0,0);
        Check(observed.Count==1,"one fresh momentum crossing observation");
        Check(Math.Abs(c.SPivot-105)<1e-10 && Math.Abs(c.SatrW-11)<1e-10,"independent EMA and ATR");
        Check(Math.Abs(c.SOscV-500.0/33.0)<1e-10,"independent oscillator normalization");
        Check(observed[0].Contains("end=0840 observed="+(partial?"9":"10")+"/10"),"exact completed bucket metadata even on late finalization");
        Check(observed[0].Contains("dailyUsedBefore=False") && observed[0].Contains("flat=True"),"snapshot before consuming daily gate");
        bool expectedFire=!partial || allowPartial;
        Check(orders.Any(o=>o.Name=="MO-L")==expectedFire,"actual MO submission matches independent complete/partial expectation");
        Check(observed[0].Contains("fullOK="+(expectedFire?"True":"False")),"visible partial gate matches submitted result");
        string snapshot=ValidationText.Snapshot(c,start.AddMinutes(20),111,100,110,0,0,0,orders);
        Check(snapshot.Contains("submissions below are not fills") && snapshot.Contains("3L/3R"),"snapshot contains execution and confirmation meaning");
        Check(ValidationText.EntrySignature(c,orders).Contains("MO-L")==expectedFire,"entry change signature follows actual orders");
        if(expectedFire) Check(snapshot.Contains("MO-L Buy market price=market qty=1 owner=entry"),"market submission not presented as a zero-price fill");
        return new { partial=partial, allow_partial=allowPartial, submitted=expectedFire,
            completed_bucket=observed[0], chart_snapshot=snapshot };
    }

    static void EnabledDisabledParity()
    {
        var off=new TwinCore { BO_PivotTF=15, MO_Trigger=1, MO_Warmup=2 };
        var on=new TwinCore { BO_PivotTF=15, MO_Trigger=1, MO_Warmup=2 };
        int completions=0;
        on.MomentumValidation=delegate(string text, bool crossing) { completions++; };
        var drawings=new Drawings(5);
        var rng=new Random(7321);
        var start=new DateTime(2024,1,15,17,1,0);
        var fields=typeof(TwinCore).GetFields().Where(f=>f.Name!="MomentumValidation").ToArray();
        double price=1000;
        for(int i=0;i<4000;i++)
        {
            var stamp=start.AddMinutes(i);
            if(stamp.Hour==16 || rng.Next(19)==0) continue;
            price+=rng.Next(-4,5);
            var a=off.Step(stamp,price+2,price-2,price,0,0,0);
            var b=on.Step(stamp,price+2,price-2,price,0,0,0);
            Check(JsonSerializer.Serialize(a,new JsonSerializerOptions {IncludeFields=true})==
                  JsonSerializer.Serialize(b,new JsonSerializerOptions {IncludeFields=true}),"enabled/disabled orders identical");
            drawings.Lines.Update(on,stamp);
            ValidationText.Snapshot(on,stamp,price+2,price-2,price,0,0,0,b);
            foreach(var f in fields)
            {
                object x=f.GetValue(off),y=f.GetValue(on);
                Check(x is double[] ? ((double[])x).SequenceEqual((double[])y) : object.Equals(x,y),
                      "enabled/disabled complete signal state: "+f.Name);
            }
        }
        Check(completions>100,"enabled observer exercised across sessions and missing minutes");
        drawings.Lines.Clear();
    }

    static object CompactSummary()
    {
        var c=new TwinCore { HaveSwH=true, SwHOpen=true, SwH=22111.25,
            HaveSwL=true, SwLOpen=false, SwL=21253, Armed=true,
            SHaveOsc=true, SOscV=-31.05955470672217, AtrU=50 };
        var stamp=new DateTime(2024,12,31,16,0,0);
        string text=ValidationText.Compact(c,stamp,1);
        Check(text.Split('\n').Length==3,"chart summary limited to three lines");
        Check(text.Split('\n').All(s=>s.Length<=64),"NQ chart summary fits a compact width");
        Check(text.Contains("Open H 22111.25 | L --"),"only open confirmed swing prices shown");
        Check(text.Contains("MO -31.06 / +/-100"),"rounded chart oscillator, exact value retained in detailed snapshot");
        Check(text.Contains("BO armed") && text.Contains("pos 1"),"compact entry context");
        string empty=ValidationText.Compact(new TwinCore(),stamp,0);
        Check(empty.Contains("H -- | L --") && empty.Contains("MO --"),"warmup does not fabricate zero levels");
        var orders=new List<TwinOrder> {new TwinOrder("BO-L",null,"Buy","stop",22111.25,1)};
        string details=ValidationText.Snapshot(c,stamp,21300,21280,21290,1,21295,499,orders);
        Check(details.Contains("FROZEN") && details.Contains("volRatio=") && details.Contains("BO-L Buy stop"),
            "on-demand detail retains risk, eligibility and exact submissions");
        Check(details.Contains("frozen15mATR=50 x multiplier=2 = distancePts=100"),"explicit independently expected 2x 15m ATR TP distance");
        c.BO_TargetMult=0;
        Check(ValidationText.Snapshot(c,stamp,21300,21280,21290,1,21295,499,orders).Contains("BO TP: disabled"),
            "disabled target not shown as an active zero-distance TP");
        return new { chart_panel=text, selected_bar_details=details };
    }

    static object RepeatedHistoricalInspection()
    {
        var live=new TwinCore {BO_PivotTF=15,MO_Trigger=2,MO_Warmup=2};
        var journal=new ValidationReplay();
        var drawings=new Drawings(3);
        var expected=new Dictionary<int,string>();
        var crossings=new List<string>();
        string momentum="MO: awaiting a completed 10-minute bucket.",signature="";
        double previousPosition=0,previousTrades=0,trades=0,price=21000;
        live.MomentumValidation=delegate(string text,bool crossing) {momentum=text;if(crossing) crossings.Add(text);};
        var start=new DateTime(2024,1,15,17,1,0);
        var rng=new Random(131);
        int bar=7;
        for(int i=0;i<3600;i++)
        {
            var stamp=start.AddMinutes(i);
            if(stamp.Hour==16 || rng.Next(29)==0) continue;
            price+=rng.Next(-10,11);
            double position=i%137<20 ? 2 : i%137<40 ? -1 : 0;
            if(previousPosition!=0 && Math.Sign(position)!=previousPosition) trades++;
            journal.Record(bar,live,stamp,price+3,price-3,price,position,price-1,trades,momentum,signature);
            crossings.Clear();
            var orders=live.Step(stamp,price+3,price-3,price,Math.Sign(position),price-1,trades);
            expected[bar]=ValidationText.Commentary(live,stamp,price+3,price-3,price,position,price-1,trades,
                orders,momentum,crossings,signature,previousPosition,previousTrades);
            drawings.Lines.Update(live,stamp);
            signature=ValidationText.EntrySignature(live,orders);
            previousPosition=Math.Sign(position);previousTrades=trades;bar++;
        }
        var options=new JsonSerializerOptions {IncludeFields=true};
        string before=JsonSerializer.Serialize(live.CopyForInspection(),options);
        int drawingOperations=drawings.Operations;
        var selected=new List<int> {7,1030,1031,2054,2055,bar-1,7,bar-1,1031,8};
        for(int i=0;i<120;i++) selected.Add(rng.Next(7,bar));
        foreach(int selectedBar in selected)
        {
            string text;
            Check(journal.TryRead(selectedBar,out text),"recorded historical bar found");
            Check(text==expected[selectedBar],"nonsequential repeated selection matches original bar context exactly");
            Check(before==JsonSerializer.Serialize(live.CopyForInspection(),options),"inspection does not mutate any live core field/array");
            Check(drawings.Operations==drawingOperations,"inspection makes no drawing operations");
        }
        string missing;
        Check(!journal.TryRead(6,out missing) && !journal.TryRead(bar,out missing),"unavailable history explicitly rejects instead of using live state");
        bool rejected=false;
        try {journal.Record(bar-1,live,start,1,0,1,0,0,0,momentum,signature);}
        catch(InvalidOperationException) {rejected=true;}
        Check(rejected,"duplicate input cannot advance journal");
        drawings.Lines.Clear();
        return new {recorded_bars=expected.Count,selected_bars=selected.Count,exact_commentary_match=true,
            live_state_unchanged=true,drawing_operations_during_inspection=0};
    }

    static object ImmediateProtectionPlans()
    {
        var c=new TwinCore {AtrU=8,StpL=90,StpS=110,BO_TargetMult=2,BO_MaxStopMult=1.5};
        var entries=new List<TwinOrder> {new TwinOrder("BO-L",null,"Buy","stop",110,2),
            new TwinOrder("BO-S",null,"SellShort","stop",90,2)};
        var pending=TwinProtectionPlan.Build(c,entries,0,null);
        Check(pending.Setup=="BO" && pending.TargetDistance==16 && pending.StopDistance==12,"native fill-relative BO target/cap distances");
        Check(pending.SwingStops.Count==2 && pending.SwingStops[0].Price==90 && pending.SwingStops[1].Price==110,
            "both conditional swing stops exist before a parent fills");
        Check(pending.SwingStops[0].Entry=="BO-L" && pending.SwingStops[1].Entry=="BO-S" && pending.SwingStops.All(o=>o.Quantity==2),
            "staged stops preserve parent ownership and planned quantity while flat");
        var held=TwinProtectionPlan.Build(c,new List<TwinOrder>(),1,"BO");
        Check(held.TargetDistance==16 && held.StopDistance==12,"native amounts renewed while held");
        Check(120.25+held.TargetDistance.Value==136.25,"gap fill preserves actual-fill target instead of trigger-price target");
        Check(TwinProtectionPlan.StopPrice(108.15,.25,true)==108 && TwinProtectionPlan.StopPrice(112.35,.25,false)==112.5,
            "absolute/capped stops use the same adverse tick rounding as native stop amounts");
        c.BO_MaxStopMult=0;c.BO_TargetMult=0;
        var disabled=TwinProtectionPlan.Build(c,entries,0,null);
        Check(!disabled.TargetDistance.HasValue && !disabled.StopDistance.HasValue && disabled.SwingStops.Count==2,
            "zero target/cap leaves only conditional absolute swing protection");
        var mo=TwinProtectionPlan.Build(c,new List<TwinOrder> {new TwinOrder("MO-S",null,"SellShort","market",0,1)},0,null);
        Check(mo.Setup=="MO" && mo.StopDistance==75 && !mo.TargetDistance.HasValue && mo.SwingStops.Count==0,
            "MO has a native fixed-distance stop and no inherited BO target");
        Check(TwinProtectionPlan.Build(c,new List<TwinOrder>(),0,"MO").Setup==null,"flat without a pending parent does not retain old setup protection");
        bool rejected=false;
        try {TwinProtectionPlan.Build(c,new List<TwinOrder>(),1,null);} catch(InvalidOperationException) {rejected=true;}
        Check(rejected,"unidentified holding rejects rather than applying the wrong setup stop");
        c.AtrU=0;c.BO_TargetMult=2;rejected=false;
        try {TwinProtectionPlan.Build(c,entries,0,null);} catch(InvalidOperationException) {rejected=true;}
        Check(rejected,"zero frozen ATR cannot silently disable an enabled native target/cap");
        return new {pending_swing_stops=2,bo_target_distance=16,bo_stop_cap_distance=12,mo_stop_distance=75,
            actual_fill_gap_example_target=136.25};
    }

    static void Main()
    {
        var cases=new object[] {ConfirmedSource(15), ConfirmedSource(360)};
        HistoryAndRecalculation(); ReadOnlyState();
        var momentum=new object[] {MomentumDiagnostics(false,false),MomentumDiagnostics(true,false),MomentumDiagnostics(true,true)};
        EnabledDisabledParity();
        var compact=CompactSummary();
        var unlimited=UnlimitedHistory();
        var inspection=RepeatedHistoricalInspection();
        var protection=ImmediateProtectionPlans();
        Console.WriteLine(JsonSerializer.Serialize(new {status="passed",assertions=assertions,cases=cases,
            momentum=momentum,compact=compact,unlimited=unlimited,inspection=inspection,protection=protection,multicharts_host_verified=false}));
    }
}
