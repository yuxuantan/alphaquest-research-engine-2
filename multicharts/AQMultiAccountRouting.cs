using System;
using System.Collections.Generic;
using System.Linq;
using ATCenterProxy.interop;
using PowerLanguage.Strategy;
using PowerLanguage.TradeManager;
using BrokerOrder = PowerLanguage.TradeManager.Order;
using BrokerPosition = PowerLanguage.TradeManager.Position;

namespace PowerLanguage.Function
{
    // This function is called explicitly by the chart signal. Its calculated
    // series is unused. All broker work stays on the study calculation thread.
    public class AQMultiAccountRouting : FunctionSimple<int>
    {
        private AccountRouter router;
        private SignalObject signal;
        private string configuredDestinations, configuredProfile, configuredAccount;
        public bool Active { get; private set; }

        public AQMultiAccountRouting(CStudyControl master) : base(master) { }

        protected override int CalcBar() { return 0; }

        protected override void Destroy()
        {
            if (router != null) router.Release();
            base.Destroy();
        }

        public bool Service(SignalObject owner, string destinations)
        {
            Active = false;
            if (string.IsNullOrWhiteSpace(destinations)) return false;
            var reason = owner.Environment.CalcReason;
            if (reason == CalculationReason.LeftMouseClick || reason == CalculationReason.RightMouseClick)
                return false;
            bool timer = reason == CalculationReason.Timer;
            if (!owner.Environment.IsAutoTradingMode || (!owner.Environment.IsRealTimeCalc && !timer))
                return timer;
            if (owner.Environment.OrderConfirmationRequired)
                throw new InvalidOperationException("Clear Require Order Confirmation on the primary chart before enabling multi-account routing.");

            if (router == null)
            {
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
            var accountNames = new HashSet<string>(StringComparer.OrdinalIgnoreCase) { primaryAccount };
            foreach (string destination in destinations.Split(';'))
            {
                string[] fields = destination.Split('|').Select(field => field.Trim()).ToArray();
                if ((fields.Length != 2 && fields.Length != 3) || fields.Any(string.IsNullOrEmpty) ||
                    !accountNames.Add(fields[1]))
                    throw new ArgumentException("Use unique follower accounts as Profile|Account[|BrokerSymbol] separated by semicolons. Exclude the primary account.");
                routes.Add(new Route { ProfileName = fields[0], Account = fields[1],
                    BrokerSymbol = fields.Length == 3 ? fields[2] : symbolName });
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
}
