using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using ATCenterProxy.interop;
using PowerLanguage.Strategy;
using PowerLanguage.TradeManager;
using BrokerOrder = PowerLanguage.TradeManager.Order;
using BrokerPosition = PowerLanguage.TradeManager.Position;
#if !AQ_ROUTING_TEST
using System.Drawing;
using System.Windows.Forms;
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

        public void StartPicker(SignalObject owner, string destinations)
        {
            StopPicker();
            if (owner.Environment.ApplicationCode == EApplicationCode.Charting && !owner.Environment.Optimizing)
                picker = new FollowerPicker(owner, destinations);
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
                    configuredAccount, message => owner.Output.WriteLine("{0}", message));
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
            bool replaceRouter = router != null && (destinations != configuredDestinations ||
                owner.Profile != configuredProfile || owner.Account != configuredAccount);
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
            public string ProfileName, Account, BrokerSymbol;
            public ITradingProfile Profile;
            public readonly List<Ticket> Tickets = new List<Ticket>();
            public AccountEntry[] Requested = NoEntries, Working = NoEntries;
            public bool Flatten, Armed, Faulted, StopsChanged, HaltAfterClose;
            public int Net, RequestedBar;
            public DateTime? DriftSince;
        }

        private static readonly object OrderPlacement = new object();
        private static readonly Dictionary<string, Route> AccountOwners =
            new Dictionary<string, Route>(StringComparer.OrdinalIgnoreCase);
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
            string destinations, string primaryProfile, string primaryAccount, Action<string> log)
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
                    BrokerSymbol = destination.BrokerSymbol ?? symbolName });
            }
        }

        public void RequireIdleForReconfiguration()
        {
            manager.ProcessEvents();
            var orders = manager.TradingData.Orders.Items;
            var positions = manager.TradingData.Positions.Items;
            foreach (Route route in routes.Where(route => route.Armed))
            {
                var accountOrders = orders.Where(order =>
                    order.Profile == route.ProfileName && order.Account == route.Account).ToArray();
                if (!Connected(route) ||
                    positions.Any(position => position.Profile == route.ProfileName &&
                        position.Account == route.Account && position.Value != 0) ||
                    accountOrders.Any(order => !order.IsDead) ||
                    route.Tickets.Any(ticket => !ticket.Final &&
                        !accountOrders.Any(order => order.OrderID == ticket.Id && order.IsDead)))
                    throw new InvalidOperationException("Confirm " + route.ProfileName + "|" + route.Account +
                        " is connected, flat, and has no working or unconfirmed orders.");
            }
        }

        public void Release()
        {
            lock (OrderPlacement)
            {
                foreach (Route route in routes)
                {
                    string key = route.ProfileName + "|" + route.Account;
                    Route owner;
                    if (AccountOwners.TryGetValue(key, out owner) && owner == route)
                        AccountOwners.Remove(key);
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
                if (route.Faulted) continue;
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

                    var accountPositions = positions.Where(position =>
                        position.Profile == route.ProfileName && position.Account == route.Account && position.Value != 0)
                        .ToArray();
                    var accountOrders = orders.Where(order =>
                        order.Profile == route.ProfileName && order.Account == route.Account).ToArray();

                    if (!route.Armed)
                    {
                        if (accountPositions.Length != 0 || accountOrders.Any(order => !order.IsDead))
                        {
                            Fault(route, "Follower must start flat and have no working orders.");
                            continue;
                        }
                        lock (OrderPlacement)
                        {
                            string key = route.ProfileName + "|" + route.Account;
                            if (AccountOwners.ContainsKey(key))
                            {
                                Fault(route, "Another signal already uses this follower account.");
                                continue;
                            }
                            AccountOwners.Add(key, route);
                            route.Armed = true;
                        }
                        log("Multi-account armed " + route.ProfileName + "|" + route.Account);
                    }

                    if (!Connected(route))
                    {
                        Fault(route, "Connection lost. Inspect all follower positions and orders before restarting.");
                        continue;
                    }

                    ReadOrders(route, accountOrders);
                    if (route.Faulted) continue;
                    if (accountPositions.Any(position => position.MCSymbol != symbolName && position.BrokerSymbol != route.BrokerSymbol) ||
                        accountOrders.Any(order => !order.IsDead && !route.Tickets.Any(ticket => ticket.Id == order.OrderID)))
                    {
                        Fault(route, "Found exposure on an unexpected symbol or an order outside this router.");
                        continue;
                    }

                    int brokerPosition = accountPositions.Sum(position => position.Value);
                    if (brokerPosition == route.Net) route.DriftSince = null;
                    else if (!route.DriftSince.HasValue) route.DriftSince = DateTime.UtcNow;
                    else if (DateTime.UtcNow - route.DriftSince.Value >= AcknowledgementTimeout)
                    {
                        Fault(route, "Reported position differs from the router's confirmed fills.");
                        continue;
                    }
                    Advance(route, brokerPosition);
                }
                catch (Exception ex)
                {
                    Fault(route, "Order status or transmission uncertain. Inspect the broker before restarting. " + ex.Message);
                }
            }
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
                lock (OrderPlacement)
                {
                    Select(route);
                    route.Profile.CancelOrder(ticket.Id);
                }
                ticket.CancelRequested = true;
                ticket.CancelledAt = DateTime.UtcNow;
            }
            return live.Length == 0;
        }

        private void Send(Route route, OrderParams[] orders, OrderUse use,
            AccountEntry[] entries, MTPA_OCOGroupType group)
        {
            int[] ids;
            lock (OrderPlacement)
            {
                Select(route);
                ids = orders.Length == 1 ? new[] { route.Profile.PlaceOrder(orders[0]) } :
                    route.Profile.PlaceOCOOrders(group, orders);
            }
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
            var accounts = new HashSet<string>(StringComparer.OrdinalIgnoreCase) { primaryAccount };
            var routes = new List<FollowerRoute>();
            foreach (string destination in destinations.Split(';'))
            {
                string[] fields = destination.Split('|').Select(field => field.Trim()).ToArray();
                if ((fields.Length != 2 && fields.Length != 3) || fields.Any(string.IsNullOrEmpty) ||
                    !accounts.Add(fields[1]))
                    throw new ArgumentException("Use unique follower accounts as Profile|Account[|BrokerSymbol] separated by semicolons. Exclude the primary account.");
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
        private readonly FollowerToolbar toolbar;
        private readonly Action<TimeSpan> schedule;
        private Request pending;
        private volatile bool disposed;

        public FollowerPicker(SignalObject owner, string fallback)
        {
            this.owner = owner;
            schedule = owner.ExecControl.RecalcLastBarAfter;
            string saved;
            if (!FollowerSelection.TryRead(owner.PersistData, out saved)) saved = fallback;
            int count;
            try { count = FollowerRoute.Parse(saved, owner.Account).Length; }
            catch (ArgumentException) { count = 0; }
            toolbar = new FollowerToolbar(owner, count, Enqueue);
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
                state.Editable = !owner.Environment.IsAutoTradingMode &&
                    !string.IsNullOrWhiteSpace(state.PrimaryProfile) &&
                    !string.IsNullOrWhiteSpace(state.PrimaryAccount);
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
                        throw new InvalidOperationException(owner.Environment.IsAutoTradingMode
                            ? "Turn off Auto Trading to change followers."
                            : "Select the primary account in Strategy Properties → Auto Trading.");
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
                else if (!state.Editable)
                    state.Message = "Select the primary account in Strategy Properties → Auto Trading.";
            }
            catch (Exception ex)
            {
                state.Message = ex.Message;
                if (!request.Save) state.Editable = false;
            }
            if (state.Draft == null) state.Draft = state.Saved;
            toolbar.Receive(state);
        }

        public void Dispose()
        {
            disposed = true;
            Interlocked.Exchange(ref pending, null);
            toolbar.Dispose();
        }
    }

#if !AQ_ROUTING_TEST
    internal sealed class FollowerToolbar : IDisposable
    {
        private readonly ICustomToolBar host;
        private readonly Action<int, bool, FollowerRoute[]> request;
        private ToolStripDropDownButton button;
        private ToolStripDropDown popup;
        private ListView accounts;
        private Label primary, status;
        private Button refresh, cancel, save;
        private FollowerPickerState state;
        private int requestId;
        private bool updating, loading, saving;
        private volatile bool disposed;

        public FollowerToolbar(SignalObject owner, int count, Action<int, bool, FollowerRoute[]> request)
        {
            this.request = request;
            host = owner.ChartToolBar;
            if (host == null) return;
            host.AccessToolBarAsync(toolBar =>
            {
                if (disposed) return;
                button = new ToolStripDropDownButton(Caption(count))
                {
                    ToolTipText = "Choose follower accounts for " + owner.GetType().Name
                };
                popup = new ToolStripDropDown();
                Control panel = BuildPanel();
                popup.Items.Add(new ToolStripControlHost(panel) { AutoSize = false, Size = panel.Size,
                    Margin = Padding.Empty, Padding = Padding.Empty });
                button.DropDown = popup;
                button.DropDownOpening += delegate
                {
                    state = null;
                    accounts.Items.Clear();
                    primary.Text = "Loading connected accounts…";
                    Request(false, null);
                };
                popup.Closing += (sender, args) =>
                {
                    if (args.CloseReason == ToolStripDropDownCloseReason.ItemClicked ||
                        (saving && args.CloseReason != ToolStripDropDownCloseReason.CloseCalled))
                        args.Cancel = true;
                };
                toolBar.Items.Add(button);
                host.Visible = true;
            });
        }

        private Control BuildPanel()
        {
            var panel = new TableLayoutPanel { Width = 435, Height = 354, Padding = new Padding(10),
                RowCount = 4, ColumnCount = 1, AutoSize = false };
            panel.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            panel.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            panel.RowStyles.Add(new RowStyle(SizeType.Absolute, 48));
            panel.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            primary = new Label { AutoSize = true, Margin = new Padding(3, 3, 3, 8) };
            accounts = new ListView { View = View.Details, CheckBoxes = true, FullRowSelect = true, Dock = DockStyle.Fill,
                HideSelection = false, HeaderStyle = ColumnHeaderStyle.Nonclickable, AccessibleName = "Follower accounts" };
            accounts.Columns.Add("Account", 225);
            accounts.Columns.Add("Availability", 145);
            accounts.ItemChecked += delegate { if (!updating) ShowSelection(); };
            status = new Label { Dock = DockStyle.Fill, TextAlign = ContentAlignment.MiddleLeft };
            refresh = new Button { Text = "Refresh", AutoSize = true };
            cancel = new Button { Text = "Cancel", AutoSize = true };
            save = new Button { AutoSize = true };
            refresh.Click += delegate { Request(false, state == null ? null : Selected()); };
            cancel.Click += delegate { popup.Close(); };
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

        private static string Caption(int count)
        {
            return count == 0 ? "Follower Accounts" : "Follower Accounts (" + count + ")";
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
            try { request(++requestId, persist, selection); }
            catch (Exception ex)
            {
                loading = saving = false;
                ShowSelection();
                status.Text = ex.Message;
            }
        }

        public void Receive(FollowerPickerState result)
        {
            if (host == null || disposed) return;
            host.AccessToolBarAsync(toolBar =>
            {
                if (disposed || button == null || result.RequestId != requestId) return;
                loading = saving = false;
                button.Text = Caption(result.Saved.Length);
                if (!popup.Visible) return;
                if (result.Applied)
                {
                    popup.Close();
                    return;
                }
                state = result;
                primary.Text = string.IsNullOrEmpty(result.PrimaryAccount)
                    ? "Primary account: select in Strategy Properties"
                    : "Primary: " + result.PrimaryAccount + " · " + result.PrimaryProfile;

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
            });
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

        public void Dispose()
        {
            disposed = true;
            if (host == null) return;
            try
            {
                host.AccessToolBarAsync(toolBar =>
                {
                    if (button == null) return;
                    toolBar.Items.Remove(button);
                    popup.Dispose();
                    button.Dispose();
                    if (toolBar.Items.Count == 0) host.Visible = false;
                });
            }
            catch (ObjectDisposedException) { }
        }
    }
#endif
}
