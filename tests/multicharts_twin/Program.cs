using System;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text.Json;
using AlphaQuest.Twin;

class Program
{
    static TwinCore Create(JsonElement parameters)
    {
        var core=new TwinCore();
        foreach (var parameter in parameters.EnumerateObject())
        {
            var field=typeof(TwinCore).GetField(parameter.Name);
            field.SetValue(core, field.FieldType==typeof(bool) ? (object)parameter.Value.GetBoolean() : parameter.Value.GetDouble());
        }
        return core;
    }
    static object Step(TwinCore core,JsonElement row,ref string setup)
    {
        double position=row.GetProperty("position").GetDouble();
        var orders=core.Step(DateTime.Parse(row.GetProperty("time").GetString(),CultureInfo.InvariantCulture),
            row.GetProperty("high").GetDouble(),row.GetProperty("low").GetDouble(),row.GetProperty("close").GetDouble(),
            position,row.GetProperty("entry_price").GetDouble(),row.GetProperty("total_trades").GetDouble());
        if(position==0)
        {
            setup=null;
            foreach(var order in orders) if(order.Entry==null) setup=order.Name.StartsWith("MO-",StringComparison.Ordinal) ? "MO" : "BO";
        }
        var routed=TwinOrderRouting.Active(orders,position,setup);
        var plan=TwinProtectionPlan.Build(core,routed,position,setup);
        setup=plan.Setup;
        JsonElement step;
        double tick=row.TryGetProperty("tick_size",out step) ? step.GetDouble() : 0.25;
        return new {
            bar_number=row.GetProperty("bar_number").GetInt32(),atr=core.AtrV,arm_atr=core.AtrU,
            swing_hi=core.SwH,swing_lo=core.SwL,vol_ratio=core.VolRatio,armed=core.Armed,
            level_long=core.LvlL,level_short=core.LvlS,stop_long=core.StpL,stop_short=core.StpS,
            hi_open=core.SwHOpen,lo_open=core.SwLOpen,s_count=core.SNB,osc=core.SOscV,traded_today=core.STradedToday,
            stop_distance=plan.StopDistance.HasValue ? (double?)TwinProtectionPlan.DistancePoints(plan.StopDistance.Value,tick) : null,
            target_distance=plan.TargetDistance.HasValue ? (double?)TwinProtectionPlan.DistancePoints(plan.TargetDistance.Value,tick) : null,
            orders=routed.Select(o=>new {name=o.Name,entry=o.Entry,action=o.Action,kind=o.Kind,quantity=o.Quantity,
                price=o.Kind=="limit" ? -TwinProtectionPlan.StopPrice(-o.Price,tick,o.Action=="Sell") :
                    core.ImmediateProtection && o.Entry!=null && o.Kind=="stop" ? TwinProtectionPlan.StopPrice(o.Price,tick,o.Action=="Sell") : o.Price}).ToArray(),
            swing_stops=plan.SwingStops.Select(o=>new {entry=o.Entry,price=TwinProtectionPlan.StopPrice(o.Price,tick,o.Action=="Sell")}).ToArray()
        };
    }
    static void Main(string[] args)
    {
        string setup=null;
        if(args[0]=="--stream")
        {
            var core=Create(JsonDocument.Parse(Console.ReadLine()).RootElement);
            string line;
            while((line=Console.ReadLine())!=null)
            {
                Console.WriteLine(JsonSerializer.Serialize(Step(core,JsonDocument.Parse(line).RootElement,ref setup)));
                Console.Out.Flush();
            }
            return;
        }
        var input=JsonDocument.Parse(File.ReadAllText(args[0])).RootElement;
        var saved=Create(input.GetProperty("parameters"));
        foreach(var row in input.GetProperty("bars").EnumerateArray())
            Console.WriteLine(JsonSerializer.Serialize(Step(saved,row,ref setup)));
    }
}
