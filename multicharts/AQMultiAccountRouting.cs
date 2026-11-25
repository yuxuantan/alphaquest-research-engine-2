using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Windows.Forms;
using ATCenterProxy.interop;
using PowerLanguage.Strategy;
using PowerLanguage.TradeManager;
using BrokerOrder = PowerLanguage.TradeManager.Order;
using BrokerPosition = PowerLanguage.TradeManager.Position;
#if !AQ_ROUTING_TEST
using System.Drawing;
#endif

namespace PowerLanguage.Function
{
    // This function is called explicitly by the chart signal. Its calculated
    // series is unused. All broker work stays on the study calculation thread.
    public class AQMultiAccountRouting : FunctionSimple<int>
    {
        private AccountRouter router;
        private SignalObject signal;
        private FollowerPicker picker;
        private string configuredDestinations, configuredProfile, configuredAccount;
        public bool Active { get; private set; }

        public AQMultiAccountRouting(CStudyControl master) : base(master) { }

        protected override int CalcBar() { return 0; }

        public void StartPicker(SignalObject owner)
        {
            StopPicker();
            if (owner.Environment.ApplicationCode == EApplicationCode.Charting && !owner.Environment.Optimizing)
            {
                try { picker = new FollowerPicker(owner); }
                catch (Exception ex)
                {
                    owner.Output.WriteLine("Follower Accounts could not initialize: {0}", ex.Message);
                }
            }
        }

        public bool OpenPicker(MouseClickArgs args)
        {
            if (picker == null || args.buttons != MouseButtons.Left) return false;
            Keys key = args.keys & Keys.KeyCode;
            bool control = key == Keys.ControlKey || key == Keys.LControlKey || key == Keys.RControlKey ||
                (args.keys & Keys.Control) == Keys.Control;
            if (control) picker.Open();
            return control;
        }

        protected override void StopCalc()
        {
            StopPicker();
            base.StopCalc();
        }

        protected override void Destroy()
        {
            StopPicker();
            if (router != null) router.Release();
            base.Destroy();
        }

        private void StopPicker()
        {
            if (picker == null) return;
            picker.Dispose();
            picker = null;
        }

        public bool Service(SignalObject owner, string destinations)
        {
            Active = false;
            var reason = owner.Environment.CalcReason;
            if (reason == CalculationReason.LeftMouseClick || reason == CalculationReason.RightMouseClick)
                return false;
            bool timer = reason == CalculationReason.Timer;
            if (picker != null) picker.Process(destinations, SaveFollowers);
            if (!owner.Environment.IsAutoTradingMode || (!owner.Environment.IsRealTimeCalc && !timer))
                return timer && (picker != null || router != null || !string.IsNullOrWhiteSpace(destinations));
            string savedDestinations;
            bool saved = FollowerSelection.TryRead(owner.PersistData, out savedDestinations);
            if (saved) destinations = savedDestinations;
            if (string.IsNullOrWhiteSpace(destinations)) return timer && picker != null;
            if (owner.Environment.OrderConfirmationRequired)
                throw new InvalidOperationException("Clear Require Order Confirmation on the primary chart before enabling multi-account routing.");

            if (router == null)
            {
                if (saved)
                    FollowerSelection.RequireAvailable(
                        FollowerRoute.Parse(destinations, owner.Account),
                        FollowerSelection.ConnectedAccounts(owner.TradeManager, owner.Account));
                signal = owner;
                configuredDestinations = destinations;
                configuredProfile = owner.Profile;
                configuredAccount = owner.Account;
                var symbol = new MCSymbolInfo
                {
                    symbol = owner.Bars.Info.ASymbolInfo2,
                    data_feed = owner.Bars.Info.DataFeed
                };
                router = new AccountRouter(owner.TradeManager, symbol, owner.Bars.Info.Name,
                    owner.Bars.Info.MinMove * owner.Bars.Info.PriceScale, destinations, configuredProfile,
                    configuredAccount, message => owner.Output.WriteLine("{0}", message), owner.GetType().Name);
            }
            else if (configuredDestinations != destinations || configuredProfile != owner.Profile ||
                configuredAccount != owner.Account)
            {
                throw new InvalidOperationException("Flatten and remove this signal before changing its multi-account routes.");
            }
            Active = !timer && owner.Environment.IsRealTimeCalc;
            router.Service(owner.Bars.CurrentBar,
                reason == CalculationReason.Default && owner.Bars.Status == EBarState.Close);
            Schedule();
            return timer;
        }

        private void SaveFollowers(SignalObject owner, string destinations)
        {
            if (owner.Environment.IsAutoTradingMode)
                throw new InvalidOperationException("Turn off Auto Trading to change followers.");
            string previous;
            if (!string.IsNullOrEmpty(owner.PersistData) &&
                !FollowerSelection.TryRead(owner.PersistData, out previous))
                throw new InvalidOperationException("This signal already uses workspace storage for other data.");
            string profile = owner.Profile, account = owner.Account;
            bool replaceRouter = router != null && (destinations != configuredDestinations ||
                (!string.IsNullOrWhiteSpace(profile) && profile != configuredProfile) ||
                (!string.IsNullOrWhiteSpace(account) && account != configuredAccount));
            if (replaceRouter) router.RequireIdleForReconfiguration();
            owner.PersistData = FollowerSelection.Encode(destinations);
            if (replaceRouter)
            {
                router.Release();
                router = null;
            }
        }

        public void Enter(int side, int quantity, AccountBracket bracket)
        {
            Update(new[] { new AccountEntry(side, quantity, null, bracket) }, false, false);
        }

        public void Reverse(int side, int quantity, AccountBracket bracket)
        {
            Update(new[] { new AccountEntry(side, quantity, null, bracket) }, false, true);
        }

        public void StopEntries(params AccountEntry[] entries)
        {
            Update(entries, true, false);
        }

        public void Flatten(int side = 0)
        {
            if (!Active) return;
            router.Flatten(side);
            Schedule();
        }

        private void Update(AccountEntry[] entries, bool refreshStops, bool flattenFirst)
        {
            if (!Active) return;
            router.Update(entries, refreshStops, flattenFirst);
            Schedule();
        }

        private void Schedule()
        {
            if (router.HasWorkingOrders)
                signal.ExecControl.RecalcLastBarAfter(TimeSpan.FromMilliseconds(250));
        }
    }

    public sealed class AccountBracket
    {
        public readonly double? StopPrice, TargetPrice, StopDistance, TargetDistance;
        public readonly bool OnFill;

        public AccountBracket(double? stopPrice, double? targetPrice, double? stopDistance,
            double? targetDistance, bool onFill)
        {
            if (!Finite(stopPrice) || !Finite(targetPrice) || !Finite(stopDistance) || !Finite(targetDistance) ||
                stopDistance <= 0 || targetDistance <= 0)
                throw new ArgumentException("Invalid follower bracket prices or distances.");
            StopPrice = stopPrice;
            TargetPrice = targetPrice;
            StopDistance = stopDistance;
            TargetDistance = targetDistance;
            OnFill = onFill;
        }

        private static bool Finite(double? price)
        {
            return !price.HasValue || (!double.IsNaN(price.Value) && !double.IsInfinity(price.Value));
        }

        internal bool SameAs(AccountBracket other)
        {
            return StopPrice == other.StopPrice && TargetPrice == other.TargetPrice &&
                StopDistance == other.StopDistance && TargetDistance == other.TargetDistance &&
                OnFill == other.OnFill;
        }

        internal OrderParams[] Resolve(int side, int quantity, double fill, double tick)
        {
            double? stop = StopPrice, target = TargetPrice;
            if (StopDistance.HasValue)
            {
                double relative = fill - side * StopDistance.Value;
                stop = !stop.HasValue ? relative :
                    side > 0 ? Math.Max(stop.Value, relative) : Math.Min(stop.Value, relative);
            }
            if (TargetDistance.HasValue) target = fill + side * TargetDistance.Value;

            var orders = new List<OrderParams>();
            if (stop.HasValue)
                orders.Add(AccountRouter.Order(-side, quantity, MTPA_OrdrCtgry.eMTPA_OC_Stop,
                    Round(stop.Value, tick, side < 0)));
            if (target.HasValue)
                orders.Add(AccountRouter.Order(-side, quantity, MTPA_OrdrCtgry.eMTPA_OC_Limit,
                    Round(target.Value, tick, side > 0)));
            return orders.ToArray();
        }

        private static double Round(double price, double tick, bool up)
        {
            decimal step = (decimal)tick;
            decimal units = (decimal)price / step;
            return (double)(step * (up ? decimal.Ceiling(units) : decimal.Floor(units)));
        }
    }

    public sealed class AccountEntry
    {
        public readonly int Side, Quantity;
        public readonly double? Stop;
        public readonly AccountBracket Bracket;

        public AccountEntry(int side, int quantity, double? stop, AccountBracket bracket)
        {
            if ((side != 1 && side != -1) || quantity <= 0 || bracket == null)
                throw new ArgumentException("Invalid account entry.");
            if (stop.HasValue && (double.IsNaN(stop.Value) || double.IsInfinity(stop.Value)))
                throw new ArgumentException("An entry stop must be finite.");
            Side = side;
            Quantity = quantity;
            Stop = stop;
            Bracket = bracket;
        }

        internal bool SameAs(AccountEntry other)
        {
            return Side == other.Side && Quantity == other.Quantity && Stop == other.Stop &&
                Bracket.SameAs(other.Bracket);
        }
    }

    internal sealed class AccountRouter
    {
        private enum OrderUse { Entry, Protection, Close }

        private sealed class Ticket
        {
            public int Id, Side, Filled, SubmitBar, Group;
            public double AverageFill, AppliedFillValue;
            public int Protected;
            public bool Final, Seen, CancelRequested;
            public DateTime SentAt, CancelledAt;
            public OrderUse Use;
            public OrderParams Parameters;
            public AccountEntry Entry;
        }

        private sealed class Route
        {
            public string ProfileName, Account, BrokerSymbol, Strategy;
            public ITradingProfile Profile;
            public SharedFollower Shared;
            public readonly List<Ticket> Tickets = new List<Ticket>();
            public AccountEntry[] Requested = NoEntries, Working = NoEntries;
            public bool Flatten, Armed, Faulted, StopsChanged, HaltAfterClose, Detached, SubmissionUnconfirmed;
            public int Net, RequestedBar;
            public DateTime? DriftSince;
        }

        private sealed class SharedFollower
        {
            public string ProfileName;
            public readonly HashSet<Route> Subscribers = new HashSet<Route>();
            public Route Owner;
        }

        // Share the account between strategies. Only the current owner can send or
        // cancel orders until the broker confirms its orders and exposure cleared.
        private static readonly object RoutingGate = new object();
        private static readonly Dictionary<string, SharedFollower> Followers =
            new Dictionary<string, SharedFollower>(StringComparer.OrdinalIgnoreCase);
        private static readonly TimeSpan AcknowledgementTimeout = TimeSpan.FromSeconds(10);
        private static readonly AccountEntry[] NoEntries = new AccountEntry[0];
        private readonly ITradeManager manager;
        private readonly MCSymbolInfo symbol;
        private readonly string symbolName;
        private readonly double tick;
        private readonly Action<string> log;
        private readonly List<Route> routes = new List<Route>();
        private int bar;
        private bool isBarClose;

        public bool HasWorkingOrders
        {
            get { return routes.Any(route => !route.Faulted && (route.Flatten || route.Net != 0 ||
                route.Requested.Length != 0 || route.Tickets.Any(ticket => !ticket.Final) || route.DriftSince.HasValue)); }
        }

        public AccountRouter(ITradeManager manager, MCSymbolInfo symbol, string symbolName, double tick,
            string destinations, string primaryProfile, string primaryAccount, Action<string> log, string strategy = null)
        {
            if (string.IsNullOrWhiteSpace(primaryProfile) || string.IsNullOrWhiteSpace(primaryAccount))
                throw new InvalidOperationException("Set the primary Auto Trading profile and account first.");
            if (tick <= 0 || double.IsNaN(tick) || double.IsInfinity(tick))
                throw new InvalidOperationException("Multi-account routing requires a finite positive tick size.");

            this.manager = manager;
            this.symbol = symbol;
            this.symbolName = symbolName;
            this.tick = tick;
            this.log = log;
            foreach (FollowerRoute destination in FollowerRoute.Parse(destinations, primaryAccount))
            {
                routes.Add(new Route { ProfileName = destination.Profile, Account = destination.Account,
                    BrokerSymbol = destination.BrokerSymbol ?? symbolName, Strategy = strategy ?? symbolName });
            }
        }

        public void RequireIdleForReconfiguration()
        {
            manager.ProcessEvents();
            var orders = manager.TradingData.Orders.Items;
            var positions = manager.TradingData.Positions.Items;
            lock (RoutingGate)
            {
                foreach (Route route in routes.Where(route => route.Shared != null && route.Shared.Owner == route))
                {
                    bool flat = !AccountPositions(route, positions).Any();
                    if (!Connected(route) || !ConfirmedClear(route, flat, AccountOrders(route, orders)))
                        throw new InvalidOperationException("Confirm " + route.ProfileName + "|" + route.Account +
                            " is connected, flat, and has no working or unconfirmed orders.");
                }
            }
        }

        public void Release()
        {
            lock (RoutingGate)
            {
                foreach (Route route in routes)
                {
                    if (route.Shared == null || route.Detached) continue;
                    route.Detached = true;
                    route.Shared.Subscribers.Remove(route);
                    // Retain a detached owner's tickets until another subscriber
                    // confirms flat and final orders in a fresh broker snapshot.
                    if (route.Shared.Owner == null && route.Shared.Subscribers.Count == 0)
                        Followers.Remove(route.Account);
                }
            }
        }

        public void Service(int currentBar, bool closed)
        {
            bar = currentBar;
            isBarClose = closed;
            BrokerPosition[] positions;
            BrokerOrder[] orders;
            try
            {
                manager.ProcessEvents();
                positions = manager.TradingData.Positions.Items;
                orders = manager.TradingData.Orders.Items;
            }
            catch (Exception ex)
            {
                foreach (Route route in routes.Where(route => !route.Faulted))
                    Fault(route, "Broker tracker unavailable. Inspect orders and positions before restarting. " + ex.Message);
                return;
            }
            foreach (Route route in routes)
            {
                if (route.Faulted || route.Detached) continue;
                try
                {
                    if (!route.Armed)
                    {
                        route.Profile = manager.TradingProfiles.FirstOrDefault(profile => profile.Name == route.ProfileName);
                        if (route.Profile == null || !Connected(route) ||
                            route.Profile.Accounts == null || !route.Profile.Accounts.Contains(route.Account))
                        {
                            Fault(route, "Connect the configured profile and check its exact account name.");
                            continue;
                        }
                    }

                    lock (RoutingGate)
                    {
                        if (!route.Detached)
                            ServiceFollower(route, AccountPositions(route, positions), AccountOrders(route, orders));
                    }
                }
                catch (Exception ex)
                {
                    Fault(route, "Order status or transmission uncertain. Inspect the broker before restarting. " + ex.Message);
                }
            }
        }

        private static BrokerPosition[] AccountPositions(Route route, BrokerPosition[] positions)
        {
            return positions.Where(position => position.Profile == route.ProfileName &&
                position.Account == route.Account && position.Value != 0).ToArray();
        }

        private static BrokerOrder[] AccountOrders(Route route, BrokerOrder[] orders)
        {
            return orders.Where(order => order.Profile == route.ProfileName && order.Account == route.Account).ToArray();
        }

        private static bool ConfirmedClear(Route route, bool flat, BrokerOrder[] orders)
        {
            if (!flat || route.SubmissionUnconfirmed || orders.Any(order => !order.IsDead)) return false;
            int net = route.Net;
            foreach (Ticket ticket in route.Tickets.Where(ticket => !ticket.Final))
            {
                int index = Array.FindIndex(orders, order => order.OrderID == ticket.Id);
                if (index < 0) return false;
                BrokerOrder orderSnapshot = orders[index];
                int side = orderSnapshot.Action == ETM_OrderAction.eTM_OA_Buy ? 1 : -1;
                if (side != ticket.Side || orderSnapshot.FilledContracts < ticket.Filled ||
                    orderSnapshot.FilledContracts > ticket.Parameters.contracts) return false;
                net += side * (orderSnapshot.FilledContracts - ticket.Filled);
            }
            // A detached owner's final execution can arrive before its position snapshot.
            return net == 0;
        }

        private void ServiceFollower(Route route, BrokerPosition[] positions, BrokerOrder[] orders)
        {
            if (!Connected(route))
            {
                Fault(route, "Connection lost. Inspect all follower positions and orders before restarting.");
                return;
            }
            bool flat = positions.Length == 0;
            bool clear = flat && orders.All(order => order.IsDead);
            SharedFollower shared;
            bool registered = Followers.TryGetValue(route.Account, out shared);
            if (!registered)
                shared = new SharedFollower { ProfileName = route.ProfileName };
            if (shared.ProfileName != route.ProfileName)
            {
                Fault(route, "Use the same broker profile for every strategy sharing a follower account.");
                return;
            }

            if (shared.Owner != null && shared.Owner.Detached && ConfirmedClear(shared.Owner, flat, orders))
                shared.Owner = null;
            if (!route.Armed)
            {
                if (!registered && !clear)
                {
                    Fault(route, "Follower must start flat and have no working orders.");
                    return;
                }
                Followers[route.Account] = shared;
                route.Shared = shared;
                shared.Subscribers.Add(route);
                route.Armed = true;
                log("Multi-account armed " + route.ProfileName + "|" + route.Account + " for " + route.Strategy);
            }

            if (shared.Owner != null && shared.Owner != route)
            {
                if (route.Requested.Length != 0)
                    log("Multi-account entry skipped " + route.ProfileName + "|" + route.Account + " for " +
                        route.Strategy + ". Follower is busy with " + shared.Owner.Strategy + ".");
                route.Requested = NoEntries;
                route.Flatten = false;
                route.StopsChanged = false;
                return;
            }
            if (shared.Owner == null)
            {
                if (!clear)
                {
                    if (route.Requested.Length != 0)
                        log("Multi-account entry skipped " + route.ProfileName + "|" + route.Account + " for " +
                            route.Strategy + ". Broker tracker has exposure or working orders.");
                    route.Requested = NoEntries;
                    route.Flatten = false;
                    return;
                }
                route.Flatten = false;
                if (route.Requested.Length == 0) return;
                shared.Owner = route;
            }

            ReadOrders(route, orders);
            if (route.Faulted) return;
            if (positions.Any(position => position.MCSymbol != symbolName && position.BrokerSymbol != route.BrokerSymbol) ||
                orders.Any(order => !order.IsDead && !route.Tickets.Any(ticket => ticket.Id == order.OrderID)))
            {
                Fault(route, "Found exposure on an unexpected symbol or an order outside this router.");
                return;
            }

            int brokerPosition = positions.Sum(position => position.Value);
            if (brokerPosition == route.Net) route.DriftSince = null;
            else if (!route.DriftSince.HasValue) route.DriftSince = DateTime.UtcNow;
            else if (DateTime.UtcNow - route.DriftSince.Value >= AcknowledgementTimeout)
            {
                Fault(route, "Reported position differs from the router's confirmed fills.");
                return;
            }

            Advance(route, brokerPosition);
            if (route.Net == 0 && route.Requested.Length == 0 && !route.Flatten &&
                ConfirmedClear(route, flat, orders))
                shared.Owner = null;
        }

        public void Update(AccountEntry[] entries, bool refreshStops, bool flattenFirst)
        {
            foreach (Route route in routes)
            {
                if (!route.Armed || route.Faulted) continue;
                if (flattenFirst)
                    route.Flatten = true;
                else if (route.Flatten || route.Net != 0)
                    continue;

                if (refreshStops)
                {
                    if (route.Working.Length == entries.Length &&
                        route.Working.Zip(entries, (left, right) => left.SameAs(right)).All(equal => equal) &&
                        route.Tickets.Any(ticket => ticket.Use == OrderUse.Entry && !ticket.Final) &&
                        !route.StopsChanged)
                        continue;
                    route.StopsChanged = route.Tickets.Any(ticket => ticket.Use == OrderUse.Entry &&
                        ticket.Entry.Stop.HasValue && !ticket.Final);
                }
                else if (!flattenFirst)
                {
                    if (route.Tickets.Any(ticket => ticket.Use == OrderUse.Entry && !ticket.Final &&
                        !ticket.Entry.Stop.HasValue))
                        continue;
                    route.StopsChanged = route.Tickets.Any(ticket => ticket.Use == OrderUse.Entry && !ticket.Final);
                }

                route.Requested = entries;
                route.RequestedBar = bar;
            }
            Service(bar, isBarClose);
        }

        public void Flatten(int side)
        {
            foreach (Route route in routes)
            {
                if (!route.Armed || route.Faulted || (side != 0 && Math.Sign(route.Net) != side)) continue;
                route.Requested = NoEntries;
                route.Flatten = true;
            }
            Service(bar, isBarClose);
        }

        private static bool Connected(Route route)
        {
            return route.Profile.ConnectionState == ETM_ConnectionChanged.eTM_CC_Connected;
        }

        private void ReadOrders(Route route, BrokerOrder[] orders)
        {
            foreach (Ticket ticket in route.Tickets)
            {
                if (ticket.Final) continue;
                int index = Array.FindIndex(orders, order => order.OrderID == ticket.Id);
                if (index < 0)
                {
                    if (ticket.Seen || DateTime.UtcNow - ticket.SentAt >= AcknowledgementTimeout)
                    {
                        Fault(route, "Order #" + ticket.Id + " is missing from the tracker.");
                        return;
                    }
                    continue; // Never retry an unknown submission.
                }
                BrokerOrder snapshot = orders[index];
                ticket.Seen = true;
                if ((snapshot.Action == ETM_OrderAction.eTM_OA_Buy ? 1 : -1) != ticket.Side)
                {
                    Fault(route, "Order #" + ticket.Id + " does not match the submitted action.");
                    return;
                }
                if (snapshot.FilledContracts < ticket.Filled ||
                    snapshot.FilledContracts > ticket.Parameters.contracts)
                {
                    Fault(route, "Broker reported incompatible cumulative fills.");
                    return;
                }
                if (snapshot.FilledContracts > ticket.Filled)
                {
                    if (!snapshot.ExecPrice.HasValue)
                    {
                        Fault(route, "A fill has no execution price.");
                        return;
                    }
                    route.Net += ticket.Side * (snapshot.FilledContracts - ticket.Filled);
                    ticket.Filled = snapshot.FilledContracts;
                    ticket.AverageFill = snapshot.ExecPrice.Value;
                }
                ticket.Final = snapshot.IsDead;
                if (!ticket.Final && ticket.CancelRequested &&
                    DateTime.UtcNow - ticket.CancelledAt >= AcknowledgementTimeout)
                {
                    Fault(route, "Cancellation of order #" + ticket.Id + " is unconfirmed.");
                    return;
                }
                if (snapshot.State == ETM_OrderState.eTM_OS_Rejected)
                {
                    log("Multi-account order rejected " + route.Account + " #" + ticket.Id);
                    route.Requested = NoEntries;
                    if (ticket.Use == OrderUse.Close)
                    {
                        Fault(route, "Closing order rejected.");
                        return;
                    }
                    if (ticket.Use == OrderUse.Protection) route.Flatten = route.HaltAfterClose = true;
                }
            }
        }

        private void Advance(Route route, int brokerPosition)
        {
            var filledEntries = route.Tickets.Where(ticket => ticket.Use == OrderUse.Entry && ticket.Filled > 0).ToArray();
            if (isBarClose && bar > route.RequestedBar && route.Requested.Any(entry => !entry.Stop.HasValue))
            {
                route.Requested = NoEntries;
                log("Multi-account queued market entry expired at the next decision bar for " + route.Account);
            }
            if (!route.HaltAfterClose && filledEntries.Select(ticket => ticket.Side).Distinct().Count() > 1)
            {
                log("Both entry OCO legs filled on " + route.Account + ". Clearing the episode.");
                route.Requested = NoEntries;
                route.Flatten = route.HaltAfterClose = true;
            }
            if (!route.Flatten && route.Net != 0 && route.Tickets
                .Where(ticket => ticket.Use == OrderUse.Protection)
                .GroupBy(ticket => ticket.Group)
                .Any(group => group.Any(ticket => ticket.Final) &&
                    group.Sum(ticket => ticket.Filled) < group.First().Parameters.contracts))
            {
                log("Follower protection ended with an open remainder. Flattening " + route.Account + ".");
                route.Requested = NoEntries;
                route.Flatten = route.HaltAfterClose = true;
            }
            if (route.Flatten)
            {
                if (!Cancel(route, ticket => ticket.Use != OrderUse.Close)) return;
                if (route.Tickets.Any(ticket => ticket.Use == OrderUse.Close && !ticket.Final)) return;
                if (brokerPosition != route.Net) return;
                if (route.Net != 0)
                {
                    Send(route, new[] { Order(-Math.Sign(route.Net), Math.Abs(route.Net), MTPA_OrdrCtgry.eMTPA_OC_Market, 0) },
                        OrderUse.Close, null, MTPA_OCOGroupType.eMTPA_OCOGT_CancellOthers);
                    return;
                }
                route.Flatten = false;
                route.Tickets.Clear();
                route.Working = NoEntries;
                route.StopsChanged = false;
                if (route.HaltAfterClose)
                {
                    Fault(route, "Risk incident cleared. Review tracker activity before restarting.");
                    return;
                }
            }

            if (route.Net != 0)
            {
                route.Requested = NoEntries;
                route.StopsChanged = false;
                if (filledEntries.Any(ticket => ticket.Side != Math.Sign(route.Net)))
                {
                    Fault(route, "Opposite entry legs filled. Inspect the follower position.");
                    return;
                }
                if (route.Tickets.Any(ticket => ticket.Use == OrderUse.Protection && ticket.Filled > 0))
                    Cancel(route, ticket => ticket.Use == OrderUse.Entry);

                // A native entry OCO can still be acknowledging its sibling cancellation.
                // Protect confirmed fills while waiting for that acknowledgement.
                foreach (Ticket ticket in route.Tickets.Where(t => t.Use == OrderUse.Entry &&
                    t.Filled > t.Protected).ToArray())
                {
                    if (!ticket.Entry.Bracket.OnFill && (!isBarClose || bar <= ticket.SubmitBar)) continue;
                    int quantity = ticket.Filled - ticket.Protected;
                    double fillValue = ticket.Filled * ticket.AverageFill;
                    double incrementalPrice = (fillValue - ticket.AppliedFillValue) / quantity;
                    OrderParams[] bracket = ticket.Entry.Bracket.Resolve(ticket.Side, quantity, incrementalPrice, tick);
                    if (bracket.Any(order => order.category == MTPA_OrdrCtgry.eMTPA_OC_Stop &&
                        (incrementalPrice - order.stop_price) * ticket.Side <= 0))
                    {
                        log("Multi-account fill is beyond its stop. Flattening " + route.Account + ".");
                        route.Flatten = true;
                        return;
                    }
                    if (bracket.Length != 0)
                        Send(route, bracket, OrderUse.Protection, null, MTPA_OCOGroupType.eMTPA_OCOGT_ReduceSize);
                    ticket.Protected = ticket.Filled;
                    ticket.AppliedFillValue = fillValue;
                }
                return;
            }

            // The net from execution reports and the account snapshot can arrive in
            // different updates. Wait for both before acting on a flat account.
            if (brokerPosition != 0) return;
            if (route.Tickets.Any(ticket => ticket.Use == OrderUse.Entry && ticket.Filled > 0))
            {
                route.Requested = NoEntries;
                if (!Cancel(route, ticket => true)) return;
            }

            if (route.StopsChanged)
            {
                if (!Cancel(route, ticket => ticket.Use == OrderUse.Entry && ticket.Entry.Stop.HasValue)) return;
                route.StopsChanged = false;
            }
            if (route.Tickets.Any(ticket => !ticket.Final)) return;
            route.Tickets.Clear();
            route.Working = route.Requested;
            route.Requested = NoEntries;
            if (route.Working.Length == 0) return;

            var orders = route.Working.Select(entry => Order(entry.Side, entry.Quantity,
                entry.Stop.HasValue ? MTPA_OrdrCtgry.eMTPA_OC_Stop : MTPA_OrdrCtgry.eMTPA_OC_Market,
                entry.Stop.GetValueOrDefault())).ToArray();
            Send(route, orders, OrderUse.Entry, route.Working, MTPA_OCOGroupType.eMTPA_OCOGT_CancellOthers);
        }

        private bool Cancel(Route route, Predicate<Ticket> matches)
        {
            Ticket[] live = route.Tickets.Where(ticket => matches(ticket) && !ticket.Final).ToArray();
            foreach (Ticket ticket in live)
            {
                if (ticket.CancelRequested || !ticket.Seen) continue;
                Select(route);
                route.Profile.CancelOrder(ticket.Id);
                ticket.CancelRequested = true;
                ticket.CancelledAt = DateTime.UtcNow;
            }
            return live.Length == 0;
        }

        private void Send(Route route, OrderParams[] orders, OrderUse use,
            AccountEntry[] entries, MTPA_OCOGroupType group)
        {
            Select(route);
            route.SubmissionUnconfirmed = true;
            int[] ids = orders.Length == 1 ? new[] { route.Profile.PlaceOrder(orders[0]) } :
                route.Profile.PlaceOCOOrders(group, orders);
            if (ids == null || ids.Length != orders.Length || ids.Any(id => id <= 0) ||
                ids.Distinct().Count() != ids.Length || ids.Any(id => route.Tickets.Any(ticket => ticket.Id == id)))
            {
                string accepted = ids == null ? "none" : string.Join(", ", ids);
                throw new InvalidOperationException("Broker returned ambiguous order IDs for " + use +
                    ". Returned IDs: " + accepted + ".");
            }
            for (int index = 0; index < orders.Length; ++index)
            {
                route.Tickets.Add(new Ticket { Id = ids[index], Use = use, Parameters = orders[index],
                    Group = ids[0],
                    SubmitBar = bar, SentAt = DateTime.UtcNow,
                    Side = orders[index].action == MTPA_OrdrActn.eMTPA_OA_Buy ? 1 : -1,
                    Entry = entries == null ? null : entries[index] });
            }
            route.SubmissionUnconfirmed = false;
            log("Multi-account " + route.ProfileName + "|" + route.Account + " " + use +
                " submitted #" + string.Join(", #", ids));
        }

        private void Select(Route route)
        {
            if (!Connected(route)) throw new InvalidOperationException("Follower is disconnected.");
            route.Profile.CurrentSymbol = symbol;
            route.Profile.CurrentAccount = route.Account;
            if (route.Profile.CurrentAccount != route.Account)
                throw new InvalidOperationException("The broker profile did not select the requested account.");
        }

        internal static OrderParams Order(int side, int quantity, MTPA_OrdrCtgry category, double price)
        {
            return new OrderParams
            {
                action = side > 0 ? MTPA_OrdrActn.eMTPA_OA_Buy : MTPA_OrdrActn.eMTPA_OA_Sell,
                category = category,
                contracts = quantity,
                stop_price = category == MTPA_OrdrCtgry.eMTPA_OC_Stop ? price : 0,
                limit_price = category == MTPA_OrdrCtgry.eMTPA_OC_Limit ? price : 0,
                tif = MTPA_OrdrTimeInForce.eMTPA_TIF_DAY
            };
        }

        private void Fault(Route route, string reason)
        {
            route.Faulted = true;
            log("MULTI-ACCOUNT HALTED " + route.ProfileName + "|" + route.Account + " | " + reason);
        }
    }

    internal sealed class FollowerRoute
    {
        public readonly string Profile, Account, BrokerSymbol;

        public FollowerRoute(string profile, string account, string brokerSymbol = null)
        {
            Profile = profile;
            Account = account;
            BrokerSymbol = brokerSymbol;
        }

        public string Key { get { return Profile + "|" + Account; } }

        public override string ToString()
        {
            return BrokerSymbol == null ? Key : Key + "|" + BrokerSymbol;
        }

        public static FollowerRoute[] Parse(string destinations, string primaryAccount)
        {
            if (string.IsNullOrWhiteSpace(destinations)) return new FollowerRoute[0];
            var accounts = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            var routes = new List<FollowerRoute>();
            foreach (string destination in destinations.Split(';'))
            {
                string[] fields = destination.Split('|').Select(field => field.Trim()).ToArray();
                if ((fields.Length != 2 && fields.Length != 3) || fields.Any(string.IsNullOrEmpty))
                    throw new ArgumentException("Use Profile|Account[|BrokerSymbol] separated by semicolons.");
                if (string.Equals(fields[1], primaryAccount, StringComparison.OrdinalIgnoreCase))
                    throw new ArgumentException("Remove the primary account " + primaryAccount + " from Follower Accounts.");
                if (!accounts.Add(fields[1]))
                    throw new ArgumentException("Choose one profile for each follower account ID.");
                routes.Add(new FollowerRoute(fields[0], fields[1], fields.Length == 3 ? fields[2] : null));
            }
            return routes.ToArray();
        }
    }

    internal static class FollowerSelection
    {
        private const string Prefix = "AlphaQuest.Followers.v1\n";

        public static string Encode(string destinations) { return Prefix + destinations; }

        public static bool TryRead(string data, out string destinations)
        {
            bool saved = data != null && data.StartsWith(Prefix, StringComparison.Ordinal);
            destinations = saved ? data.Substring(Prefix.Length) : null;
            return saved;
        }

        public static FollowerRoute[] ConnectedAccounts(ITradeManager manager, string primaryAccount)
        {
            return manager.TradingProfiles
                .Where(profile => profile.ConnectionState == ETM_ConnectionChanged.eTM_CC_Connected &&
                    Representable(profile.Name))
                .SelectMany(profile => (profile.Accounts ?? new string[0])
                    .Where(account => Representable(account) &&
                        !string.Equals(account, primaryAccount, StringComparison.OrdinalIgnoreCase))
                    .Select(account => new FollowerRoute(profile.Name, account)))
                .GroupBy(route => route.Key, StringComparer.Ordinal)
                .Select(group => group.First())
                .OrderBy(route => route.Profile, StringComparer.OrdinalIgnoreCase)
                .ThenBy(route => route.Account, StringComparer.OrdinalIgnoreCase)
                .ToArray();
        }

        private static bool Representable(string value)
        {
            return !string.IsNullOrWhiteSpace(value) && value.Trim() == value &&
                value.IndexOfAny(new[] { ';', '|', '\r', '\n' }) < 0;
        }

        public static string[] Missing(FollowerRoute[] selected, FollowerRoute[] available)
        {
            return selected.Select(route => route.Key).Except(available.Select(route => route.Key), StringComparer.Ordinal)
                .ToArray();
        }

        public static void RequireAvailable(FollowerRoute[] selected, FollowerRoute[] available)
        {
            string[] missing = Missing(selected, available);
            if (missing.Length != 0)
                throw new InvalidOperationException("Followers unavailable: " + string.Join(", ", missing) +
                    ". Reconnect or update Follower Accounts.");
        }
    }

    internal sealed class FollowerPickerState
    {
        public int RequestId;
        public string PrimaryProfile, PrimaryAccount, Message;
        public FollowerRoute[] Saved, Draft, Available;
        public bool Editable, Applied;
    }

    // UI requests are posted to the chart's calculation thread. Broker reads,
    // validation and workspace writes all happen there.
    internal sealed class FollowerPicker : IDisposable
    {
        private sealed class Request
        {
            public int Id;
            public bool Save;
            public FollowerRoute[] Selection;
        }

        private readonly SignalObject owner;
        private readonly FollowerAccountsWindow window;
        private readonly Action<TimeSpan> schedule;
        private Request pending;
        private volatile bool disposed;

        public FollowerPicker(SignalObject owner)
        {
            this.owner = owner;
            schedule = owner.ExecControl.RecalcLastBarAfter;
            window = new FollowerAccountsWindow(owner, Enqueue);
        }

        public void Open()
        {
            try { window.Open(); }
            catch (Exception ex)
            {
                owner.Output.WriteLine("Follower Accounts could not open: {0}", ex.Message);
            }
        }

        private void Enqueue(int id, bool save, FollowerRoute[] selection)
        {
            if (disposed) return;
            Interlocked.Exchange(ref pending, new Request { Id = id, Save = save, Selection = selection });
            try { schedule(TimeSpan.FromMilliseconds(100)); }
            catch
            {
                Interlocked.Exchange(ref pending, null);
                throw;
            }
        }

        public void Process(string fallback, Action<SignalObject, string> save)
        {
            Request request = Interlocked.Exchange(ref pending, null);
            if (disposed || request == null) return;
            var state = new FollowerPickerState
            {
                RequestId = request.Id,
                Saved = new FollowerRoute[0],
                Available = new FollowerRoute[0],
                Draft = request.Selection
            };
            try
            {
                state.PrimaryProfile = owner.Profile;
                state.PrimaryAccount = owner.Account;
                // Editing must work even if the host doesn't report the primary while stopped.
                // The router checks the actual primary before enabling follower orders.
                state.Editable = !owner.Environment.IsAutoTradingMode;
                string saved;
                if (!FollowerSelection.TryRead(owner.PersistData, out saved)) saved = fallback;
                // A previously configured account may now be the primary. Keep
                // the row visible so it can be removed from the saved selection.
                try { state.Saved = FollowerRoute.Parse(saved, null); }
                catch (ArgumentException ex) { state.Message = ex.Message; }
                if (state.Draft == null) state.Draft = state.Saved;
                owner.TradeManager.ProcessEvents();
                state.Available = FollowerSelection.ConnectedAccounts(owner.TradeManager, state.PrimaryAccount);
                if (request.Save)
                {
                    if (!state.Editable)
                        throw new InvalidOperationException("Turn off Auto Trading to change followers.");
                    string destinations = string.Join(";", state.Draft.Select(route => route.ToString()));
                    FollowerRoute[] selected = FollowerRoute.Parse(destinations, state.PrimaryAccount);
                    FollowerSelection.RequireAvailable(selected, state.Available);
                    save(owner, destinations);
                    state.Saved = selected;
                    state.Applied = true;
                    state.Message = null;
                }
                else if (owner.Environment.IsAutoTradingMode)
                    state.Message = "Turn off Auto Trading to change followers.";
            }
            catch (Exception ex)
            {
                state.Message = ex.Message;
                if (!request.Save) state.Editable = false;
            }
            if (state.Draft == null) state.Draft = state.Saved;
            window.Receive(state);
        }

        public void Dispose()
        {
            disposed = true;
            Interlocked.Exchange(ref pending, null);
            window.Dispose();
        }
    }

#if !AQ_ROUTING_TEST
    internal sealed class FollowerAccountsWindow : IDisposable
    {
        private sealed class ChartWindow : IWin32Window
        {
            public ChartWindow(IntPtr handle) { Handle = handle; }
            public IntPtr Handle { get; private set; }
        }

        private readonly object gate = new object();
        private readonly string signalName;
        private readonly IntPtr chartHandle;
        private readonly Action<int, bool, FollowerRoute[]> request;
        private AccountsDialog dialog;
        private int nextRequestId;
        private bool running, disposed;

        public FollowerAccountsWindow(SignalObject owner, Action<int, bool, FollowerRoute[]> request)
        {
            this.request = request;
            signalName = owner.GetType().Name;
            chartHandle = owner.Environment.ChartWindowHWND;
        }

        public void Open()
        {
            lock (gate)
            {
                if (disposed) return;
                if (running)
                {
                    Post(dialog, form => form.Activate());
                    return;
                }

                var thread = new Thread(Run) { IsBackground = true, Name = "AlphaQuest Follower Accounts" };
                thread.SetApartmentState(ApartmentState.STA);
                thread.Start();
                running = true;
            }
        }

        private void Run()
        {
            try
            {
                using (var form = new AccountsDialog(signalName, request, () => Interlocked.Increment(ref nextRequestId)))
                {
                    lock (gate)
                    {
                        if (disposed) return;
                        dialog = form;
                        // Make a handle before publishing the dialog to other threads.
                        var handle = form.Handle;
                    }
                    if (chartHandle == IntPtr.Zero)
                    {
                        form.StartPosition = FormStartPosition.CenterScreen;
                        form.Show();
                    }
                    else form.Show(new ChartWindow(chartHandle));
                    Application.Run(form);
                }
            }
            catch (Exception ex)
            {
                lock (gate)
                {
                    if (disposed) return;
                }
                MessageBox.Show(ex.Message, "Follower Accounts");
            }
            finally
            {
                lock (gate)
                {
                    dialog = null;
                    running = false;
                }
            }
        }

        public void Receive(FollowerPickerState result)
        {
            lock (gate)
            {
                if (!disposed) Post(dialog, form => form.Receive(result));
            }
        }

        public void Dispose()
        {
            lock (gate)
            {
                disposed = true;
                Post(dialog, form => form.CloseForStudy());
            }
        }

        private static void Post(AccountsDialog form, Action<AccountsDialog> action)
        {
            if (form == null) return;
            try { form.BeginInvoke((MethodInvoker)(() => action(form))); }
            catch (InvalidOperationException) { } // The dialog was closed while the request was in flight.
        }
    }

    internal sealed class AccountsDialog : Form
    {
        private readonly Action<int, bool, FollowerRoute[]> request;
        private readonly Func<int> allocateRequestId;
        private ListView accounts;
        private Label primary, status;
        private Button refresh, cancel, save;
        private FollowerPickerState state;
        private int requestId;
        private bool updating, loading, saving;

        public AccountsDialog(string signalName, Action<int, bool, FollowerRoute[]> request, Func<int> allocateRequestId)
        {
            this.request = request;
            this.allocateRequestId = allocateRequestId;
            Text = "Follower Accounts — " + signalName;
            AutoScaleMode = AutoScaleMode.Dpi;
            ClientSize = new Size(520, 408);
            MinimumSize = new Size(460, 280);
            StartPosition = FormStartPosition.CenterParent;
            ShowInTaskbar = false;
            Controls.Add(BuildPanel());
            Shown += delegate { Request(false, null); };
        }

        protected override void OnFormClosing(FormClosingEventArgs args)
        {
            if (saving && args.CloseReason == CloseReason.UserClosing) args.Cancel = true;
            base.OnFormClosing(args);
        }

        public void CloseForStudy()
        {
            saving = false;
            Close();
        }

        private Control BuildPanel()
        {
            var panel = new TableLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(12),
                RowCount = 4, ColumnCount = 1, AutoSize = false };
            panel.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            panel.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            panel.RowStyles.Add(new RowStyle(SizeType.Absolute, 48));
            panel.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            primary = new Label { AutoSize = true, Margin = new Padding(3, 3, 3, 8) };
            accounts = new ListView { View = View.Details, CheckBoxes = true, FullRowSelect = true, Dock = DockStyle.Fill,
                HideSelection = false, HeaderStyle = ColumnHeaderStyle.Nonclickable, AccessibleName = "Follower accounts" };
            accounts.Columns.Add("Account", 290);
            accounts.Columns.Add("Availability", 145);
            accounts.ItemChecked += delegate { if (!updating) ShowSelection(); };
            status = new Label { Dock = DockStyle.Fill, TextAlign = ContentAlignment.MiddleLeft };
            refresh = new Button { Text = "Refresh", AutoSize = true };
            cancel = new Button { Text = "Cancel", AutoSize = true };
            save = new Button { AutoSize = true };
            refresh.Click += delegate { Request(false, state == null ? null : Selected()); };
            cancel.Click += delegate { Close(); };
            CancelButton = cancel;
            save.Click += delegate { Request(true, Selected()); };
            var actions = new FlowLayoutPanel { Dock = DockStyle.Fill, AutoSize = true, FlowDirection = FlowDirection.RightToLeft };
            actions.Controls.Add(save);
            actions.Controls.Add(cancel);
            actions.Controls.Add(refresh);
            panel.Controls.Add(primary, 0, 0);
            panel.Controls.Add(accounts, 0, 1);
            panel.Controls.Add(status, 0, 2);
            panel.Controls.Add(actions, 0, 3);
            return panel;
        }

        private FollowerRoute[] Selected()
        {
            return accounts.CheckedItems.Cast<ListViewItem>().Select(item => (FollowerRoute)item.Tag).ToArray();
        }

        private void Request(bool persist, FollowerRoute[] selection)
        {
            loading = true;
            saving = persist;
            status.Text = persist ? "Checking and saving followers…" : "Checking broker profiles…";
            accounts.Enabled = refresh.Enabled = save.Enabled = false;
            cancel.Enabled = !persist;
            try
            {
                requestId = allocateRequestId();
                request(requestId, persist, selection);
            }
            catch (Exception ex)
            {
                loading = saving = false;
                ShowSelection();
                status.Text = ex.Message;
            }
        }

        public void Receive(FollowerPickerState result)
        {
            if (IsDisposed || result.RequestId != requestId) return;
            loading = saving = false;
            if (result.Applied)
            {
                Close();
                return;
            }
            state = result;
            primary.Text = string.IsNullOrWhiteSpace(result.PrimaryAccount)
                ? "Primary: checked when Auto Trading starts. Choose only followers here."
                : "Primary: " + result.PrimaryAccount +
                    (string.IsNullOrWhiteSpace(result.PrimaryProfile) ? "" : " · " + result.PrimaryProfile);

            updating = true;
            accounts.BeginUpdate();
            accounts.Items.Clear();
            accounts.Groups.Clear();
            var chosen = result.Draft.ToDictionary(route => route.Key, StringComparer.Ordinal);
            var available = new HashSet<string>(result.Available.Select(route => route.Key), StringComparer.Ordinal);
            var rows = result.Available.Where(route => !chosen.ContainsKey(route.Key)).Concat(result.Draft)
                .OrderBy(route => route.Account, StringComparer.OrdinalIgnoreCase);
            foreach (var group in rows.GroupBy(route => route.Profile).OrderBy(group => group.Key, StringComparer.OrdinalIgnoreCase))
            {
                var header = new ListViewGroup(group.Key);
                accounts.Groups.Add(header);
                foreach (FollowerRoute route in group)
                {
                    var row = new ListViewItem(route.Account, header) { Tag = route };
                    row.SubItems.Add(available.Contains(route.Key) ? "Connected" : "Unavailable");
                    accounts.Items.Add(row);
                    row.Checked = chosen.ContainsKey(route.Key);
                }
            }
            accounts.EndUpdate();
            updating = false;
            ShowSelection();
        }

        private void ShowSelection()
        {
            if (loading) return;
            FollowerRoute[] selected = Selected();
            save.Text = selected.Length == 0 ? "Save without followers" :
                "Save " + selected.Length + (selected.Length == 1 ? " follower" : " followers");
            bool missing = state != null && FollowerSelection.Missing(selected, state.Available).Length != 0;
            bool duplicate = selected.Select(route => route.Account)
                .Distinct(StringComparer.OrdinalIgnoreCase).Count() != selected.Length;
            accounts.Enabled = state != null && state.Editable;
            refresh.Enabled = cancel.Enabled = true;
            save.Enabled = accounts.Enabled && !missing && !duplicate;
            status.Text = state != null && state.Message != null ? state.Message :
                missing ? "Reconnect or uncheck the unavailable accounts." :
                duplicate ? "Choose one profile for each account ID." :
                selected.Length + " selected · " + (selected.Length + 1) + " accounts including the primary";
        }

    }
#endif
}
