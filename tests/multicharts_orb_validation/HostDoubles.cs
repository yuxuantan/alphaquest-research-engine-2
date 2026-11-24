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
    public enum Contracts { UserSpecified }
    public enum OrderExit { Total }
    public enum ETextStyleH { Left }
    public enum ETextStyleV { Above, Below }
    public sealed class SOrderParameters
    {
        public string Name;
        public SOrderParameters(Contracts contracts, string name, EOrderAction action) { Name=name; }
        public SOrderParameters(Contracts contracts, string name, EOrderAction action, OrderExit exit) { Name=name; }
    }
    public interface IOrderMarket { void Send(int quantity); }
    public interface IOrderPriced { void Send(double price, int quantity); }
    public sealed class Orders
    {
        public readonly List<string> Sent = new List<string>();
        private sealed class Order : IOrderMarket, IOrderPriced
        {
            public Orders Owner; public string Name;
            public void Send(int quantity) { Owner.Sent.Add(Name + " market " + quantity); }
            public void Send(double price, int quantity)
            { Owner.Sent.Add(Name + " " + price.ToString("F2",CultureInfo.InvariantCulture) + " " + quantity); }
        }
        public IOrderMarket MarketNextBar(SOrderParameters p) { return new Order { Owner=this, Name=p.Name }; }
        public IOrderPriced Stop(SOrderParameters p) { return new Order { Owner=this, Name=p.Name }; }
        public IOrderPriced Limit(SOrderParameters p) { return new Order { Owner=this, Name=p.Name }; }
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
        void Delete();
    }
    public interface ITextObject
    {
        ChartPoint Location { get; set; } string Text { get; set; } Color Color { get; set; }
        ETextStyleH HStyle { get; set; } ETextStyleV VStyle { get; set; } void Delete();
    }
    public sealed class Line : ITrendLineObject
    {
        public ChartPoint Begin,End; public bool Deleted;
        public Color Color { get; set; } public int Size { get; set; }
        public bool ExtLeft { get; set; } public bool ExtRight { get; set; }
        public void Delete() { Deleted=true; }
    }
    public sealed class TextDrawing : ITextObject
    {
        public bool Deleted;
        public ChartPoint Location { get; set; } public string Text { get; set; } public Color Color { get; set; }
        public ETextStyleH HStyle { get; set; } public ETextStyleV VStyle { get; set; }
        public void Delete() { Deleted=true; }
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
    { public string Name="NQ"; public double MinMove=25, PriceScale=0.01, BigPointValue=20; }
    public sealed class BarData
    {
        public int CurrentBar; public EBarState Status=EBarState.Close; public bool LastBarOnChart=true;
        public readonly BarInfo Info=new BarInfo();
        public readonly Series<DateTime> Time=new Series<DateTime>();
        public readonly Series<double> High=new Series<double>(), Low=new Series<double>(),
            Close=new Series<double>(), Ticks=new Series<double>();
        public void Add(DateTime time, double high, double low, double close)
        { CurrentBar++; Time.Values.Add(time); High.Values.Add(high); Low.Values.Add(low); Close.Values.Add(close); Ticks.Values.Add(1); }
    }
    public sealed class StrategyState { public double MarketPosition; }
    public sealed class Commentary
    {
        public bool AtCommentaryBar;
        public readonly List<string> Written = new List<string>();
        public void WriteLine(string format, params object[] args) { Written.Add(string.Format(CultureInfo.InvariantCulture,format,args)); }
    }
    public abstract class SignalObject
    {
        protected SignalObject(object ctx) {}
        public readonly BarData Bars=new BarData();
        public readonly StrategyState StrategyInfo=new StrategyState();
        public readonly Orders OrderCreator=new Orders();
        public readonly Lines DrwTrendLine=new Lines(); public readonly Texts DrwText=new Texts();
        public readonly Commentary Output=new Commentary(), ExpertCommentary=new Commentary();
        protected abstract void Create(); protected abstract void StartCalc(); protected abstract void CalcBar();
        public void Initialize() { Create(); StartCalc(); }
        public void Restart() { StartCalc(); }
        public void Calculate() { CalcBar(); }
    }
}
namespace PowerLanguage.Function
{
    public sealed class ADX
    {
        public int Length; public double Value=25, Previous=26;
        public ADX(object owner) {}
        public double this[int ago] { get { return ago==0 ? Value : Previous; } }
    }
}
