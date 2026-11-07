"""Synthetic sparse source and independent prices for two genuine strategies."""
from datetime import date,timedelta
from native_replay_fixtures import parameter_values

EXPECTED_DAILY={'consecutive_green_hold:1':'4','consecutive_green_hold:2':'12',
                'vwap_pullback_risk_sizing:1':'20','vwap_pullback_risk_sizing:2':'20'}
TIMES=('07:54','07:55','07:56','07:57','07:58','07:59','08:00','08:01',
       '08:02','08:10','08:11','09:00','09:01','09:02','09:03','16:00')


def source_bytes():
    """320 deliberately sparse observations; never represented as full minute data."""
    lines=['Date,Time,Open,High,Low,Close,Volume,UpVol,DownVol']
    current=date(2026,1,5)
    for _ in range(20):
        while current.weekday()>4:current+=timedelta(days=1)
        for clock in TIMES:
            prices={'08:00':('116','128','115','116'),'08:10':('116','117','113','116'),
                '09:01':('116','119','115','118'),'09:02':('118','121','117','120'),
                '09:03':('128','129','119','124')}.get(clock,('116','117','115','116'))
            lines.append(','.join([current.strftime('%m/%d/%Y'),clock,*prices,'1','1','0']))
        current+=timedelta(days=1)
    return ('\n'.join(lines)+'\n').encode()


def strategies():
    # Six pre-pivot observations respect max_bars_back4 followed by the
    # strategy's own 2*strength pivot warmup. Reset759 is crossed by actual bars.
    vwap=parameter_values();vwap.update(max_bars_back=4,adx_len=1,day_reset_time=759)
    return [('consecutive_green_hold',dict(green_bar_count=1,hold_minutes=1,contracts=1),'hold_minutes'),
            ('vwap_pullback_risk_sizing',vwap,'target_swing_len')]


def configuration_key(record):
    strategy=record['run_metadata']['strategy'];name=strategy['id'];parameters=strategy['parameters']
    return name+':'+str(parameters['hold_minutes' if name=='consecutive_green_hold' else 'target_swing_len'])
