using System;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text.Json;
using AlphaQuest.Twin;

class Program
{
    static void Main(string[] args)
    {
        var input=JsonDocument.Parse(File.ReadAllText(args[0])).RootElement;
        var core=new TwinCore();
        foreach (var parameter in input.GetProperty("parameters").EnumerateObject())
        {
            var field=typeof(TwinCore).GetField(parameter.Name);
            field.SetValue(core, field.FieldType==typeof(bool) ? (object)parameter.Value.GetBoolean() : parameter.Value.GetDouble());
        }
        foreach (var row in input.GetProperty("bars").EnumerateArray())
        {
            var orders=core.Step(DateTime.Parse(row.GetProperty("time").GetString(),CultureInfo.InvariantCulture),
                row.GetProperty("high").GetDouble(), row.GetProperty("low").GetDouble(), row.GetProperty("close").GetDouble(),
                row.GetProperty("position").GetDouble(),row.GetProperty("entry_price").GetDouble(),row.GetProperty("total_trades").GetDouble());
            Console.WriteLine(JsonSerializer.Serialize(new {
                bar_number=row.GetProperty("bar_number").GetInt32(),atr=core.AtrV,arm_atr=core.AtrU,
                swing_hi=core.SwH,swing_lo=core.SwL,vol_ratio=core.VolRatio,armed=core.Armed,
                level_long=core.LvlL,level_short=core.LvlS,stop_long=core.StpL,stop_short=core.StpS,
                hi_open=core.SwHOpen,lo_open=core.SwLOpen,s_count=core.SNB,osc=core.SOscV,
                traded_today=core.STradedToday,
                orders=orders.Select(o=>new {name=o.Name,entry=o.Entry,action=o.Action,kind=o.Kind,price=o.Price,quantity=o.Quantity}).ToArray()
            }));
        }
    }
}
