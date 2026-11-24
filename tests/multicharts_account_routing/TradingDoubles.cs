// API-shaped doubles for the router's order/position reconciliation tests.
using System;
using System.Collections.Generic;
using System.Linq;

namespace System.Windows.Forms
{
    [Flags]
    public enum Keys { None = 0, ControlKey = 17, LControlKey = 162, RControlKey = 163,
        KeyCode = 65535, Control = 131072 }
    public enum MouseButtons { Left, Right }
}

namespace ATCenterProxy.interop
{
    public enum MTPA_OrdrActn { eMTPA_OA_Buy, eMTPA_OA_Sell }
    public enum MTPA_OrdrCtgry { eMTPA_OC_Market, eMTPA_OC_Stop, eMTPA_OC_Limit }
    public enum MTPA_OrdrTimeInForce { eMTPA_TIF_DAY }
    public enum MTPA_OCOGroupType { eMTPA_OCOGT_CancellOthers, eMTPA_OCOGT_ReduceSize }
    public enum ETM_ConnectionChanged { eTM_CC_Disconnected, eTM_CC_Connected }
    public enum ETM_OrderAction { eTM_OA_Buy, eTM_OA_Sell }
    public enum ETM_OrderState { eTM_OS_Submitted, eTM_OS_Filled, eTM_OS_Cancelled, eTM_OS_Rejected }
}

namespace PowerLanguage.Function
{
    public abstract class FunctionSimple<T>
    {
        protected FunctionSimple(CStudyControl owner) {}
        protected abstract T CalcBar();
        protected virtual void StopCalc() {}
        protected virtual void Destroy() {}
    }

    internal sealed class FollowerAccountsWindow : IDisposable
    {
        private readonly Action<int, bool, FollowerRoute[]> request;
        private readonly PowerLanguage.Strategy.SignalObject owner;
        private int requestId;
        public FollowerPickerState Latest;
        public int Opens;

        public FollowerAccountsWindow(PowerLanguage.Strategy.SignalObject owner,
            Action<int, bool, FollowerRoute[]> request)
        {
            this.owner = owner;
            this.request = request;
            owner.FollowerWindow = this;
        }

        public void Open() { ++Opens; Submit(false, null); }
        public void Submit(bool save, FollowerRoute[] selection) { request(++requestId, save, selection); }
        public void Receive(FollowerPickerState state) { Latest = state; }
        public void Dispose() { if (owner.FollowerWindow == this) owner.FollowerWindow = null; }
    }
}

namespace PowerLanguage.TradeManager
{
    using ATCenterProxy.interop;

    public struct MCSymbolInfo { public object symbol; public string data_feed; }
    public struct OrderParams
    {
        public MTPA_OrdrActn action;
        public MTPA_OrdrCtgry category;
        public MTPA_OrdrTimeInForce tif;
        public int contracts;
        public double stop_price, limit_price;
    }
    public struct Order
    {
        public string Profile, Account;
        public int OrderID, FilledContracts;
        public double? ExecPrice;
        public ETM_OrderState State;
        public ETM_OrderAction Action;
        public bool IsDead { get { return State != ETM_OrderState.eTM_OS_Submitted; } }
    }
    public struct Position
    {
        public string Profile, Account, MCSymbol, BrokerSymbol;
        public int Value;
    }
    public sealed class Tracker<T>
    {
        public T[] Items = new T[0];
    }
    public sealed class TradingData
    {
        public readonly Tracker<Order> Orders = new Tracker<Order>();
        public readonly Tracker<Position> Positions = new Tracker<Position>();
    }
    public interface ITradeManager
    {
        void ProcessEvents();
        ITradingProfile[] TradingProfiles { get; }
        TradingData TradingData { get; }
    }
    public interface ITradingProfile
    {
        string Name { get; }
        string[] Accounts { get; }
        string CurrentAccount { get; set; }
        MCSymbolInfo CurrentSymbol { get; set; }
        ETM_ConnectionChanged ConnectionState { get; }
        int PlaceOrder(OrderParams order);
        int[] PlaceOCOOrders(MTPA_OCOGroupType group, params OrderParams[] orders);
        void CancelOrder(int orderId);
    }

    public sealed class TestOrder
    {
        public Order Snapshot;
        public OrderParams Parameters;
        public MTPA_OCOGroupType? Group;
        public int GroupSize;
        public bool CancellationRequested;
    }
    public sealed class TestBroker : ITradeManager
    {
        private readonly List<TestProfile> profiles = new List<TestProfile>();
        public readonly List<TestOrder> Placed = new List<TestOrder>();
        public readonly List<Position> Positions = new List<Position>();
        public ITradingProfile[] TradingProfiles { get { return profiles.ToArray(); } }
        public TradingData TradingData { get; private set; }

        public TestBroker() { TradingData = new TradingData(); }

        public TestProfile AddProfile(string name, params string[] accounts)
        {
            var profile = new TestProfile(this, name, accounts);
            profiles.Add(profile);
            return profile;
        }
        public void ProcessEvents()
        {
            TradingData.Orders.Items = Placed.Select(ticket => ticket.Snapshot).ToArray();
            TradingData.Positions.Items = Positions.ToArray();
        }
        public void Fill(TestOrder order, int cumulativeQuantity, double averageFill, bool final)
        {
            int last = order.Snapshot.FilledContracts;
            order.Snapshot.FilledContracts = cumulativeQuantity;
            order.Snapshot.ExecPrice = averageFill;
            if (final) order.Snapshot.State = ETM_OrderState.eTM_OS_Filled;
            int positionIndex = Positions.FindIndex(position => position.Profile == order.Snapshot.Profile &&
                position.Account == order.Snapshot.Account);
            Position positionSnapshot = positionIndex < 0 ? new Position {
                Profile=order.Snapshot.Profile, Account=order.Snapshot.Account, MCSymbol="MNQ"
            } : Positions[positionIndex];
            int direction = order.Snapshot.Action == ETM_OrderAction.eTM_OA_Buy ? 1 : -1;
            positionSnapshot.Value += direction * (cumulativeQuantity - last);
            if (positionIndex < 0) Positions.Add(positionSnapshot);
            else Positions[positionIndex] = positionSnapshot;
        }
        public void AcknowledgeCancellations()
        {
            foreach (TestOrder order in Placed.Where(order => order.CancellationRequested && !order.Snapshot.IsDead))
                order.Snapshot.State = ETM_OrderState.eTM_OS_Cancelled;
        }
    }
    public sealed class TestProfile : ITradingProfile
    {
        private readonly TestBroker broker;
        public string Name { get; private set; }
        public string[] Accounts { get; private set; }
        public string CurrentAccount { get; set; }
        public MCSymbolInfo CurrentSymbol { get; set; }
        public ETM_ConnectionChanged ConnectionState { get; set; }
        public bool RejectSubmission;

        public TestProfile(TestBroker broker, string name, string[] accounts)
        {
            this.broker = broker;
            Name = name;
            Accounts = accounts;
            ConnectionState = ETM_ConnectionChanged.eTM_CC_Connected;
        }

        private int Place(OrderParams order, MTPA_OCOGroupType? group, int groupSize)
        {
            if (RejectSubmission) throw new InvalidOperationException("Fixture transport failure");
            if (!Accounts.Contains(CurrentAccount)) throw new ArgumentException("Unknown account");
            int id = broker.Placed.Count + 1;
            broker.Placed.Add(new TestOrder {
                Parameters=order, Group=group, GroupSize=groupSize,
                Snapshot=new Order {
                    Profile=Name, Account=CurrentAccount, OrderID=id,
                    Action=order.action == MTPA_OrdrActn.eMTPA_OA_Buy ? ETM_OrderAction.eTM_OA_Buy : ETM_OrderAction.eTM_OA_Sell
                }
            });
            return id;
        }

        public int PlaceOrder(OrderParams order) { return Place(order,null,1); }
        public int[] PlaceOCOOrders(MTPA_OCOGroupType group, params OrderParams[] orders)
        { return orders.Select(order => Place(order,group,orders.Length)).ToArray(); }
        public void CancelOrder(int orderId)
        {
            TestOrder order = broker.Placed.Single(item => item.Snapshot.OrderID == orderId &&
                item.Snapshot.Profile == Name && item.Snapshot.Account == CurrentAccount);
            order.CancellationRequested = true;
        }
    }
}
