// Test doubles ONLY: compile/exercise the real signal locally, not an MC SDK/host qualification.
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Globalization;

namespace PowerLanguage
{
    public enum IOGMode { Disabled }
    public sealed class IOGModeAttribute : Attribute { public IOGModeAttribute(IOGMode mode) {} }
    public sealed class InputAttribute : Attribute {}
    public enum EOrderAction { Buy, SellShort, Sell, BuyToCover }
    public enum EBarState { Close, Open }
    public enum ESpecOrdersMode { PerPosition, PerContract }
    public enum Contracts { UserSpecified }
    public sealed class OrderExit
    {
        public static readonly OrderExit Total = new OrderExit();
        public IOrderMarket Parent;
        public static OrderExit FromEntry(IOrderMarket entry) { return new OrderExit { Parent=entry }; }
    }
    public enum EResolution { Minute }
    public sealed class ResolutionInfo { public EResolution Type; public int Size=15; }
    public enum ETextStyleH { Left }
    public enum ETextStyleV { Above, Below }
    public sealed class SOrderParameters
    {
        public string Name;
        public OrderExit Exit;
        public SOrderParameters(Contracts contracts, string name, EOrderAction action) { Name=name; }
        public SOrderParameters(Contracts contracts, string name, EOrderAction action, OrderExit exit) { Name=name; Exit=exit; }
    }
    public interface IOrderMarket { void Send(int quantity); }
    public interface IOrderPriced { void Send(double price, int quantity); }
    public sealed class Orders
    {
        public readonly List<string> Sent = new List<string>();
        public readonly Dictionary<string, IOrderMarket> Parent = new Dictionary<string, IOrderMarket>();
        private sealed class Order : IOrderMarket, IOrderPriced
        {
            public Orders Owner; public string Name; public string MarketTiming = " market ";
            public void Send(int quantity) { Owner.Sent.Add(Name + MarketTiming + quantity); }
            public void Send(double price, int quantity)
            { Owner.Sent.Add(Name + " " + price.ToString("F2",CultureInfo.InvariantCulture) + " " + quantity); }
        }
        public IOrderMarket MarketNextBar(SOrderParameters p) { return new Order { Owner=this, Name=p.Name }; }
        public IOrderMarket MarketThisBar(SOrderParameters p) { return new Order { Owner=this, Name=p.Name, MarketTiming=" this close " }; }
        private IOrderPriced Priced(SOrderParameters p)
        {
            if (p.Exit != null && p.Exit.Parent != null) Parent.Add(p.Name, p.Exit.Parent);
            return new Order { Owner=this, Name=p.Name };
        }
        public IOrderPriced Stop(SOrderParameters p) { return Priced(p); }
        public IOrderPriced Limit(SOrderParameters p) { return Priced(p); }
    }
    public struct ChartPoint
    {
        public DateTime Time; public double Price;
        public ChartPoint(DateTime time, double price) { Time=time; Price=price; }
    }
    public interface ITrendLineObject
    {
        Color Color { get; set; } int Size { get; set; }
        bool ExtLeft { get; set; } bool ExtRight { get; set; }
        bool Delete();
    }
    public interface ITextObject
    {
        ChartPoint Location { get; set; } string Text { get; set; } Color Color { get; set; }
        ETextStyleH HStyle { get; set; } ETextStyleV VStyle { get; set; } bool Delete();
    }
    public sealed class Line : ITrendLineObject
    {
        public ChartPoint Begin,End; public bool Deleted;
        public Color Color { get; set; } public int Size { get; set; }
        public bool ExtLeft { get; set; } public bool ExtRight { get; set; }
        public bool Delete() { bool removed = !Deleted; Deleted = true; return removed; }
    }
    public sealed class TextDrawing : ITextObject
    {
        public bool Deleted;
        public ChartPoint Location { get; set; } public string Text { get; set; } public Color Color { get; set; }
        public ETextStyleH HStyle { get; set; } public ETextStyleV VStyle { get; set; }
        public bool Delete() { bool removed = !Deleted; Deleted = true; return removed; }
    }
    public sealed class Lines
    {
        public readonly List<Line> Created = new List<Line>();
        public ITrendLineObject Create(ChartPoint begin, ChartPoint end)
        { var line=new Line { Begin=begin, End=end }; Created.Add(line); return line; }
    }
    public sealed class Texts
    {
        public readonly List<TextDrawing> Created = new List<TextDrawing>();
        public ITextObject Create(ChartPoint location, string text)
        { var drawing=new TextDrawing { Location=location, Text=text }; Created.Add(drawing); return drawing; }
    }
    public sealed class Series<T>
    {
        public readonly List<T> Values = new List<T>();
        public T this[int ago] { get { return Values[Values.Count-1-ago]; } }
    }
    public sealed class BarInfo
    {
        public string Name="NQ", DataFeed="Test";
        public object ASymbolInfo2;
        public double MinMove=25, PriceScale=0.01, BigPointValue=20;
        public readonly ResolutionInfo Resolution=new ResolutionInfo();
    }
    public sealed class BarData
    {
        public int CurrentBar; public EBarState Status=EBarState.Close; public bool LastBarOnChart=true, LastBarInSession;
        public readonly BarInfo Info=new BarInfo();
        public readonly Series<DateTime> Time=new Series<DateTime>();
        public readonly Series<double> Open=new Series<double>(), High=new Series<double>(), Low=new Series<double>(),
            Close=new Series<double>(), Ticks=new Series<double>();
        public void Add(DateTime time, double high, double low, double close)
        { Add(time,close,high,low,close); }
        public void Add(DateTime time, double open, double high, double low, double close)
        { CurrentBar++; Time.Values.Add(time); Open.Values.Add(open); High.Values.Add(high); Low.Values.Add(low); Close.Values.Add(close); Ticks.Values.Add(1); }
    }
    public sealed class StrategyState { public double MarketPosition, AvgEntryPrice; }
    public sealed class PositionStats { public double Profit; }
    public sealed class Commentary
    {
        public bool AtCommentaryBar;
        public readonly List<string> Written = new List<string>();
        public void WriteLine(string format, params object[] args) { Written.Add(string.Format(CultureInfo.InvariantCulture,format,args)); }
    }
    public class CStudyControl {}
    public enum EApplicationCode { Unknown, Charting, Scanner, Portfolio }
    public enum CalculationReason { Default, Timer, LeftMouseClick, RightMouseClick }
    public sealed class CalculationEnvironment
    {
        public bool IsAutoTradingMode, IsRealTimeCalc, OrderConfirmationRequired, Optimizing;
        public EApplicationCode ApplicationCode;
        public CalculationReason CalcReason;
    }
    public sealed class CalculationControl
    {
        public int Timers;
        public void RecalcLastBarAfter(TimeSpan interval) { ++Timers; }
    }
}
namespace PowerLanguage.Strategy
{
    public abstract class SignalObject : CStudyControl
    {
        protected SignalObject(object ctx) {}
        public string Profile, Account;
        public string PersistData;
        internal PowerLanguage.Function.FollowerToolbar FollowerToolbar;
        public PowerLanguage.TradeManager.ITradeManager TradeManager;
        public readonly CalculationEnvironment Environment = new CalculationEnvironment();
        public readonly CalculationControl ExecControl = new CalculationControl();
        public readonly BarData Bars=new BarData();
        public readonly BarData SecondaryBars=new BarData();
        protected BarData BarsOfData(int number) { return number == 2 ? SecondaryBars : Bars; }
        public readonly StrategyState StrategyInfo=new StrategyState();
        public readonly Orders OrderCreator=new Orders();
        public readonly Lines DrwTrendLine=new Lines(); public readonly Texts DrwText=new Texts();
        public readonly Commentary Output=new Commentary(), ExpertCommentary=new Commentary();
        public int TotalTrades, SessionExitCalls;
        public readonly PositionStats[] Positions = { new PositionStats(), new PositionStats() };
        public ESpecOrdersMode CurSpecOrdersMode;
        public double LastStopLoss, LastProfitTarget;
        protected void GenerateStopLoss(double amount) { LastStopLoss = amount; }
        protected void GenerateProfitTarget(double amount) { LastProfitTarget = amount; }
        protected void GenerateExitOnClose() { SessionExitCalls++; }
        protected abstract void Create(); protected abstract void StartCalc(); protected abstract void CalcBar();
        public void Initialize() { Create(); StartCalc(); }
        public void Restart() { StartCalc(); }
        public void Calculate() { CalcBar(); }
    }
}
namespace PowerLanguage.Function
{
    public sealed class XAverage
    {
        public PowerLanguage.Series<double> Price;
        public int Length;
        public XAverage(object owner) {}
        public double this[int ago]
        {
            get
            {
                int last = Price.Values.Count - 1 - ago;
                double ema = Price.Values[1], alpha = 2.0 / (Length + 1);
                for (int i = 2; i <= last; ++i) ema += alpha * (Price.Values[i] - ema);
                return ema;
            }
        }
    }
    public sealed class ADX
    {
        public int Length; public double Value=25, Previous=26;
        public ADX(object owner) {}
        public double this[int ago] { get { return ago==0 ? Value : Previous; } }
    }
}
