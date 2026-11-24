using System;
using System.Collections.Generic;
using System.Linq;
using System.Windows.Forms;
using ATCenterProxy.interop;
using PowerLanguage;
using PowerLanguage.Function;
using PowerLanguage.Strategy;
using PowerLanguage.TradeManager;

internal static class Program
{
    private static int checks;
    private static readonly AccountBracket Bracket = new AccountBracket(null, null, 2, 4, true);
    private static readonly AccountBracket NoBracket = new AccountBracket(null, null, null, null, true);

    private static void Check(bool condition, string message)
    {
        ++checks;
        if (!condition) throw new Exception(message);
    }

    private static AccountRouter Router(TestBroker broker, string routes, List<string> log)
    {
        return new AccountRouter(broker, new MCSymbolInfo(), "MNQ", 0.25, routes, "Primary", "Lead", log.Add);
    }

    private static void Main()
    {
        EntryAndPartialFills();
        DelayedAndGapProtection();
        StopPairReplacement();
        CompetingEntryFills();
        FlattenAndReverse();
        RejectionsAndIsolation();
        ConfigurationAndCallbacks();
        PickerWorkspaceSelection();
        PickerBeforeHostReportsPrimary();
        PickerReconfiguration();
        Console.WriteLine("MultiCharts routing checks passed: " + checks);
    }

    private static void EntryAndPartialFills()
    {
        var broker = new TestBroker();
        broker.AddProfile("First", "A", "B");
        broker.AddProfile("Second", "C");
        var router = Router(broker, "First|A;First|B;Second|C", new List<string>());
        router.Service(7, true);
        router.Update(new[] { new AccountEntry(1, 2, null, Bracket) }, false, false);
        Check(broker.Placed.Select(ticket => ticket.Snapshot.Account).SequenceEqual(new[] { "A", "B", "C" }),
            "Each account receives one independent request, including those on one shared profile");
        Check(broker.Placed.All(ticket => ticket.Parameters.category == MTPA_OrdrCtgry.eMTPA_OC_Market &&
            ticket.Parameters.contracts == 2), "The direct market request uses the strategy quantity");
        router.Service(8, false);
        router.Service(8, false);
        Check(broker.Placed.Count == 3, "Polling cannot resend a pending market entry");

        broker.Fill(broker.Placed[0], 1, 100, false);
        router.Service(8, false);
        var bracket = broker.Placed.Skip(3).ToArray();
        Check(bracket.Length == 2 && bracket.All(order => order.Snapshot.Account == "A" &&
            order.Group == MTPA_OCOGroupType.eMTPA_OCOGT_ReduceSize && order.Parameters.contracts == 1),
            "Only the filled account gets a size-one native OCO bracket");
        Check(bracket[0].Parameters.stop_price == 98 && bracket[1].Parameters.limit_price == 104,
            "First bracket uses the first follower fill");
        broker.Fill(broker.Placed[0], 2, 100.5, true);
        broker.Fill(broker.Placed[1], 2, 102, true);
        router.Service(8, false);
        Check(broker.Placed[5].Parameters.stop_price == 99 && broker.Placed[6].Parameters.limit_price == 105 &&
            broker.Placed[5].Parameters.contracts == 1, "The second bracket protects only the new fill at 101");
        Check(broker.Placed[7].Parameters.stop_price == 100 && broker.Placed[8].Parameters.limit_price == 106 &&
            broker.Placed[7].Parameters.contracts == 2, "The second account uses its own fill and quantity");
        Check(broker.Placed.Count == 9, "The third account still awaits its entry fill");
        router.Release();
    }

    private static void DelayedAndGapProtection()
    {
        var broker = new TestBroker();
        broker.AddProfile("Paper", "A");
        var router = Router(broker, "Paper|A", new List<string>());
        router.Service(10, true);
        var delayed = new AccountBracket(99, 106, null, null, false);
        router.Update(new[] { new AccountEntry(1, 1, null, delayed) }, false, false);
        broker.Fill(broker.Placed[0], 1, 100, true);
        router.Service(10, true);
        router.Service(11, false);
        Check(broker.Placed.Count == 1, "A delayed strategy waits until the next completed bar");
        router.Service(11, true);
        Check(broker.Placed.Count == 3 && broker.Placed[1].Parameters.stop_price == 99 &&
            broker.Placed[2].Parameters.limit_price == 106, "The delayed bracket preserves absolute signal prices");
        router.Release();

        broker = new TestBroker();
        broker.AddProfile("Paper", "Gap");
        router = Router(broker, "Paper|Gap", new List<string>());
        router.Service(10, true);
        router.Update(new[] { new AccountEntry(1, 1, null, new AccountBracket(99, 106, null, null, true)) }, false, false);
        broker.Fill(broker.Placed[0], 1, 98, true);
        router.Service(11, false);
        router.Service(11, false);
        Check(broker.Placed.Count == 2 && broker.Placed[1].Parameters.category == MTPA_OrdrCtgry.eMTPA_OC_Market &&
            broker.Placed[1].Parameters.action == MTPA_OrdrActn.eMTPA_OA_Sell,
            "A fill through a frozen absolute stop produces a close instead of an invalid bracket");
        router.Release();
    }

    private static void StopPairReplacement()
    {
        var broker = new TestBroker();
        broker.AddProfile("Paper", "Twin");
        var router = Router(broker, "Paper|Twin", new List<string>());
        var entries = new[] { new AccountEntry(1, 1, 101, Bracket), new AccountEntry(-1, 1, 99, Bracket) };
        router.Service(1, true);
        router.Update(entries, true, false);
        Check(broker.Placed.Count == 2 && broker.Placed.All(order =>
            order.Group == MTPA_OCOGroupType.eMTPA_OCOGT_CancellOthers && order.GroupSize == 2),
            "Both Twin stop entries are issued in one OCO group on the account");
        router.Update(entries, true, false);
        Check(broker.Placed.Count == 2 && broker.Placed.All(order => !order.CancellationRequested),
            "An unchanged stop pair stays working");
        var changed = new[] { new AccountEntry(1, 1, 101.5, Bracket) };
        router.Update(changed, true, false);
        Check(broker.Placed.Count == 2 && broker.Placed.All(order => order.CancellationRequested),
            "Both old legs must be cancelled before a replacement");
        router.Service(2, false);
        Check(broker.Placed.Count == 2, "Cancellation requests are not terminal acknowledgements");
        broker.AcknowledgeCancellations();
        router.Service(2, false);
        Check(broker.Placed.Count == 3 && broker.Placed[2].Parameters.stop_price == 101.5,
            "The latest replacement is placed once after confirmed cancellations");
        router.Update(new AccountEntry[0], true, false);
        Check(broker.Placed[2].CancellationRequested, "An expired stop intent cancels the working entry");
        router.Update(new[] { new AccountEntry(-1, 1, null, Bracket) }, false, false);
        Check(broker.Placed.Count == 3, "A market signal can't overlap a previously working stop entry");
        broker.AcknowledgeCancellations();
        router.Service(2, false);
        Check(broker.Placed.Count == 4 && broker.Placed[3].Parameters.category == MTPA_OrdrCtgry.eMTPA_OC_Market,
            "The fresh market signal can follow an acknowledged stop cancellation");
        router.Release();
    }

    private static void CompetingEntryFills()
    {
        var broker = new TestBroker();
        broker.AddProfile("Paper", "Twin");
        var log = new List<string>();
        var router = Router(broker, "Paper|Twin", log);
        router.Service(1, true);
        router.Update(new[] { new AccountEntry(1, 2, 101, Bracket),
            new AccountEntry(-1, 2, 99, Bracket) }, true, false);
        broker.Fill(broker.Placed[0], 2, 101, true);
        broker.Fill(broker.Placed[1], 1, 99, false);
        router.Service(2, false);
        Check(broker.Placed.Count == 2 && broker.Placed[1].CancellationRequested,
            "A dual OCO fill triggers cancellation before neutralizing the remainder");
        broker.AcknowledgeCancellations();
        router.Service(2, false);
        Check(broker.Placed.Count == 3 && broker.Placed[2].Parameters.contracts == 1 &&
            broker.Placed[2].Parameters.action == MTPA_OrdrActn.eMTPA_OA_Sell,
            "A dual OCO fill closes only the unmatched exposure");
        broker.Fill(broker.Placed[2], 1, 100, true);
        router.Service(2, false);
        router.Update(new[] { new AccountEntry(1, 1, null, Bracket) }, false, false);
        Check(broker.Placed.Count == 3 && log.Any(message => message.Contains("HALTED")),
            "The account stays halted after clearing both OCO fills");
        router.Release();
    }

    private static void FlattenAndReverse()
    {
        var broker = new TestBroker();
        broker.AddProfile("Paper", "Reverse");
        var router = Router(broker, "Paper|Reverse", new List<string>());
        router.Service(1, true);
        router.Update(new[] { new AccountEntry(1, 2, null, Bracket) }, false, false);
        broker.Fill(broker.Placed[0], 2, 100, true);
        router.Service(2, false);
        router.Update(new[] { new AccountEntry(-1, 1, null, Bracket) }, false, true);
        Check(broker.Placed.Count == 3 && broker.Placed.Skip(1).All(order => order.CancellationRequested),
            "Reversal first clears both sides of the old protective bracket");
        broker.AcknowledgeCancellations();
        router.Service(2, false);
        Check(broker.Placed.Count == 4 && broker.Placed[3].Parameters.contracts == 2 &&
            broker.Placed[3].Parameters.action == MTPA_OrdrActn.eMTPA_OA_Sell,
            "Close size is confirmed exposure, not the requested reversal size");
        router.Service(2, false);
        Check(broker.Placed.Count == 4, "No reverse entry while the closing order is pending");
        broker.Fill(broker.Placed[3], 2, 101, true);
        router.Service(2, false);
        Check(broker.Placed.Count == 5 && broker.Placed[4].Parameters.contracts == 1 &&
            broker.Placed[4].Parameters.action == MTPA_OrdrActn.eMTPA_OA_Sell,
            "Opposite entry follows only after the position is confirmed flat");

        broker.Fill(broker.Placed[4], 1, 101, true);
        router.Service(3, false);
        var stop = broker.Placed[5];
        var target = broker.Placed[6];
        Check(stop.Parameters.stop_price == 103 && target.Parameters.limit_price == 97,
            "Short brackets use the correct side and distances");
        broker.Fill(target, 1, 97, true);
        stop.Snapshot.State = ETM_OrderState.eTM_OS_Cancelled;
        router.Service(3, false);
        Check(broker.Placed.Count == 7, "A completed OCO exit never emits another close");
        router.Release();
    }

    private static void RejectionsAndIsolation()
    {
        var broker = new TestBroker();
        broker.AddProfile("Bad", "A").RejectSubmission = true;
        broker.AddProfile("Paper", "B", "C");
        var log = new List<string>();
        var router = Router(broker, "Bad|A;Paper|B;Paper|C", log);
        broker.Positions.Add(new Position { Profile="Paper", Account="C", MCSymbol="MNQ", Value=1 });
        router.Service(1, true);
        router.Update(new[] { new AccountEntry(1, 1, null, Bracket) }, false, false);
        Check(broker.Placed.Count == 1 && broker.Placed[0].Snapshot.Account == "B",
            "A transport failure and a non-flat startup do not prevent the healthy follower from routing");
        Check(log.Count(entry => entry.Contains("HALTED")) == 2, "Each failed route is identified in the log");
        broker.Fill(broker.Placed[0], 1, 100, true);
        router.Service(2, false);
        broker.Placed[1].Snapshot.State = ETM_OrderState.eTM_OS_Rejected;
        router.Service(2, false);
        Check(broker.Placed[2].CancellationRequested, "A protective stop rejection cancels the sibling");
        broker.AcknowledgeCancellations();
        router.Service(2, false);
        Check(broker.Placed.Count == 4 && broker.Placed[3].Parameters.category == MTPA_OrdrCtgry.eMTPA_OC_Market,
            "Confirmed exposure is flattened on protective-order rejection");
        broker.Fill(broker.Placed[3], 1, 100, true);
        router.Service(2, false);
        router.Update(new[] { new AccountEntry(1, 1, null, Bracket) }, false, false);
        Check(broker.Placed.Count == 4 && log.Any(message => message.Contains("Risk incident cleared")),
            "A rejected bracket cannot silently start another trade after the emergency close");
        router.Release();
    }

    private sealed class Study : SignalObject
    {
        private AQMultiAccountRouting routing;
        public string Routes;
        public bool EmitEntry;
        public int Decisions;
        public Study() : base(null) {}
        protected override void Create() { routing = new AQMultiAccountRouting(this); }
        protected override void StartCalc() { routing.StartPicker(this); }
        protected override void OnMouseEvent(MouseClickArgs args)
        {
            if (!routing.OpenPicker(args)) base.OnMouseEvent(args);
        }
        protected override void CalcBar()
        {
            if (routing.Service(this,Routes)) return;
            ++Decisions;
            if (EmitEntry) routing.Enter(1,1,NoBracket);
        }
    }

    private static Study PickerStudy(TestBroker broker, string routes, string saved = null)
    {
        var study = new Study {
            Routes=routes, PersistData=saved, Profile="Paper", Account="Primary",
            TradeManager=broker, EmitEntry=true
        };
        study.Bars.Info.Name = "MNQ";
        study.Environment.ApplicationCode = EApplicationCode.Charting;
        study.Initialize();
        return study;
    }

    private static FollowerPickerState Pick(Study study, bool save, FollowerRoute[] selection = null)
    {
        study.FollowerWindow.Submit(save, selection);
        int decisions = study.Decisions;
        study.Environment.CalcReason = CalculationReason.Timer;
        study.Calculate();
        study.Environment.CalcReason = CalculationReason.Default;
        Check(study.Decisions == decisions, "A picker timer cannot trigger a new strategy decision");
        return study.FollowerWindow.Latest;
    }

    private static void PickerWorkspaceSelection()
    {
        var broker = new TestBroker();
        broker.AddProfile("Paper", "Primary", "PickerA", "PickerB", "PickerC");
        broker.AddProfile("Other", Enumerable.Range(0,20).Select(n => "Other" + n).ToArray());
        var disconnected = broker.AddProfile("Offline", "PickerMissing");
        disconnected.ConnectionState = ETM_ConnectionChanged.eTM_CC_Disconnected;
        var study = PickerStudy(broker,"Paper|PickerA|BrokerMNQ;Offline|PickerMissing");
        Check(study.FollowerWindow.Opens == 0, "Chart initialization opens no window");
        study.Click(new MouseClickArgs { keys=Keys.None, buttons=MouseButtons.Left });
        study.Click(new MouseClickArgs { keys=Keys.ControlKey, buttons=MouseButtons.Right });
        Check(study.FollowerWindow.Opens == 0, "Ordinary clicks do not open the account picker");
        study.Click(new MouseClickArgs { keys=Keys.ControlKey, buttons=MouseButtons.Left });
        study.Environment.CalcReason = CalculationReason.Timer;
        study.Calculate();
        study.Environment.CalcReason = CalculationReason.Default;
        var state = study.FollowerWindow.Latest;
        Check(study.FollowerWindow.Opens == 1 && state.Saved.Length == 2 && study.Decisions == 0,
            "Ctrl+left-click opens the picker and loads saved routes without evaluating a trade");
        Check(state.PrimaryAccount == "Primary" && state.Available.Length == 23 &&
            state.Available.All(route => route.Account != "Primary"), "The current inventory excludes the primary");
        Check(state.Draft.Any(route => route.Key == "Offline|PickerMissing") &&
            FollowerSelection.Missing(state.Draft,state.Available).SequenceEqual(new[] { "Offline|PickerMissing" }),
            "A disconnected saved follower remains visible and is flagged");
        Check(!Pick(study,true,state.Draft).Applied && string.IsNullOrEmpty(study.PersistData),
            "An unavailable account cannot be silently saved or removed");

        var draft = state.Draft.Where(route => route.Profile != "Offline")
            .Concat(state.Available.Where(route => route.Profile == "Other")).ToArray();
        Check(Pick(study,false,draft).Draft.Length == 21 && string.IsNullOrEmpty(study.PersistData),
            "Refreshing keeps pending choices without persisting them");
        Check(Pick(study,false).Draft.Length == 2, "Reopening after Cancel loads the original selection");
        state = Pick(study,true,draft);
        string destinations;
        Check(state.Applied && FollowerSelection.TryRead(study.PersistData,out destinations) &&
            destinations.Contains("Paper|PickerA|BrokerMNQ"), "Saving preserves an existing broker-symbol override");
        Check(broker.Placed.Count == 0 && state.Saved.Length == 21, "A variable number of selected accounts saves without orders");

        var restored = PickerStudy(broker,"Paper|PickerC",study.PersistData);
        Check(Pick(restored,false).Saved.Length == 21,
            "A recreated signal restores its workspace selection");
        Check(Pick(restored,true,new FollowerRoute[0]).Applied, "The picker supports saving without followers");
        restored.Environment.IsAutoTradingMode = restored.Environment.IsRealTimeCalc = true;
        restored.Calculate();
        Check(broker.Placed.Count == 0, "An explicitly empty workspace selection overrides legacy text");
        int decisions = restored.Decisions;
        restored.Environment.CalcReason = CalculationReason.Timer;
        restored.Calculate();
        Check(restored.Decisions == decisions, "A late picker timer with no pending request remains broker-only");

        var stale = PickerStudy(broker,"", FollowerSelection.Encode("Paper|PickerB;Offline|PickerMissing"));
        stale.Environment.IsAutoTradingMode = stale.Environment.IsRealTimeCalc = true;
        bool rejected = false;
        try { stale.Calculate(); }
        catch (InvalidOperationException ex) { rejected = ex.Message.Contains("Offline|PickerMissing"); }
        Check(rejected && broker.Placed.Count == 0,
            "A saved selection that went offline blocks follower startup instead of silently starting a subset");
    }

    private static void PickerBeforeHostReportsPrimary()
    {
        var broker = new TestBroker();
        broker.AddProfile("Paper", "Primary", "PendingPrimaryFollower");
        var study = PickerStudy(broker,"");
        study.Profile = study.Account = "";
        var state = Pick(study,false);
        Check(state.Editable && state.Available.Length == 2,
            "Connected accounts remain selectable while Auto Trading is off and the primary is unreported");
        Check(Pick(study,true,state.Available.Where(route => route.Account == "PendingPrimaryFollower").ToArray()).Applied &&
            broker.Placed.Count == 0, "Saving followers with an unreported primary does not send orders");

        study.Environment.IsAutoTradingMode = study.Environment.IsRealTimeCalc = true;
        bool missingPrimary = false;
        try { study.Calculate(); }
        catch (InvalidOperationException ex) { missingPrimary = ex.Message.Contains("primary Auto Trading profile and account"); }
        Check(missingPrimary && broker.Placed.Count == 0, "Routing requires the actual chart primary at startup");

        study.Profile = "Paper";
        study.Account = "Primary";
        study.Calculate();
        Check(broker.Placed.Count == 1 && broker.Placed[0].Snapshot.Account == "PendingPrimaryFollower",
            "Routing uses the saved follower after the primary becomes known");

        var collision = PickerStudy(broker,"");
        collision.Profile = collision.Account = "";
        var primaryChoice = Pick(collision,false).Available.Where(route => route.Account == "Primary").ToArray();
        Check(Pick(collision,true,primaryChoice).Applied, "The picker can save a draft before knowing which account is primary");
        collision.Profile = "Paper";
        collision.Account = "Primary";
        collision.Environment.IsAutoTradingMode = collision.Environment.IsRealTimeCalc = true;
        bool duplicatePrimary = false;
        try { collision.Calculate(); }
        catch (ArgumentException ex) { duplicatePrimary = ex.Message.Contains("Remove the primary account"); }
        Check(duplicatePrimary && broker.Placed.Count == 1,
            "A selected follower that turns out to be the primary blocks routing before a duplicate order");
    }

    private static void PickerReconfiguration()
    {
        var broker = new TestBroker();
        broker.AddProfile("Paper", "Primary", "ChangeA", "ChangeB");
        var study = PickerStudy(broker,"",FollowerSelection.Encode("Paper|ChangeA"));
        var state = Pick(study,false);
        var next = state.Available.Where(route => route.Account == "ChangeB").ToArray();

        study.FollowerWindow.Submit(true,next);
        study.Environment.IsAutoTradingMode = true;
        study.Environment.CalcReason = CalculationReason.Timer;
        study.Calculate();
        Check(!study.FollowerWindow.Latest.Applied && study.PersistData.EndsWith("Paper|ChangeA"),
            "Saving is blocked if Auto Trading is switched on before the request reaches the calculation thread");
        study.Environment.IsRealTimeCalc = true;
        study.Environment.CalcReason = CalculationReason.Default;
        study.Calculate();
        Check(broker.Placed.Count == 1 && broker.Placed[0].Snapshot.Account == "ChangeA",
            "Trading uses the last saved follower");
        study.Environment.IsAutoTradingMode = false;
        study.Profile = study.Account = "";
        Check(!Pick(study,true,next).Applied && study.PersistData.EndsWith("Paper|ChangeA") &&
            study.FollowerWindow.Latest.Message.Contains("unconfirmed orders"),
            "Replacing followers waits while an old route still has working orders");
        broker.Placed[0].Snapshot.State = ETM_OrderState.eTM_OS_Cancelled;
        Check(Pick(study,true,next).Applied && study.PersistData.EndsWith("Paper|ChangeB") &&
            broker.Placed.Count == 1, "Clearing the old route permits editing without a new order");
        study.Profile = "Paper";
        study.Account = "Primary";
        study.Environment.IsAutoTradingMode = true;
        study.Calculate();
        Check(broker.Placed.Count == 2 && broker.Placed[1].Snapshot.Account == "ChangeB",
            "The next real-time decision uses the new saved follower");
    }

    private static void ConfigurationAndCallbacks()
    {
        var broker = new TestBroker();
        broker.AddProfile("Paper", "A");
        var log = new List<string>();
        foreach (string invalid in new[] { "Paper|Lead", "Paper|A;Second|a", "Paper|", "Paper" })
        {
            bool rejected = false;
            try { Router(broker,invalid,log); }
            catch (ArgumentException) { rejected = true; }
            Check(rejected, "Malformed, duplicate and primary account routes are rejected");
        }

        var study = new Study { Routes="Paper|A", Profile="Primary", Account="Lead", TradeManager=broker, EmitEntry=true };
        study.Bars.Info.Name = "MNQ";
        study.Initialize();
        study.Calculate();
        study.Environment.IsAutoTradingMode = true;
        study.Calculate();
        study.Environment.IsRealTimeCalc = true;
        study.Environment.CalcReason = CalculationReason.LeftMouseClick;
        study.Calculate();
        Check(broker.Placed.Count == 0 && study.ExecControl.Timers == 0,
            "Historical, automation-off and commentary callbacks never route");
        study.Environment.CalcReason = CalculationReason.Default;
        study.Calculate();
        Check(broker.Placed.Count == 1 && study.ExecControl.Timers == 1, "A real-time decision routes and schedules tracking");
        int decisions = study.Decisions;
        study.Environment.CalcReason = CalculationReason.Timer;
        study.Calculate();
        Check(study.Decisions == decisions && broker.Placed.Count == 1,
            "Timer services broker state without evaluating the strategy again");
    }
}
