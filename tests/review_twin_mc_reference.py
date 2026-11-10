"""Compare a normal saved AQ IS report to the immutable supplied MC workbook.

.venv/bin/python tests/review_twin_mc_reference.py --reference PATH --report PATH --output NEW_DIRECTORY
No new backtest, source mutation or OOS replay occurs in this comparison.
"""
import argparse
import csv
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from twin_mc_reference import read_reference

CT=ZoneInfo('America/Chicago')


def review(reference,report,output):
    output.mkdir(parents=True,exist_ok=False)
    reference_hash=sha256(reference.read_bytes()).hexdigest()
    mc=read_reference(reference)
    manifest=json.loads((report/'report.json').read_text())
    run_id=manifest.get('id',report.resolve().name)
    window=manifest['run_metadata']['selection'];start,end=window['from_date'],window['to_date']
    assert manifest['run_metadata']['research']['phase']=='is'
    expected=[t for t in mc if start<=t['entry']['time'][:10]<=end]
    with (report/'trades.csv').open(newline='') as stream:actual=list(csv.DictReader(stream))
    def local(value):return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(CT).replace(tzinfo=None).isoformat(' ')
    def key_mc(t):return (t['entry']['time'],t['entry']['signal'])
    def key_aq(t):return (local(t['entry_time_utc']),t['entry_reason'])
    a_by={key_aq(t):t for t in actual};m_by={key_mc(t):t for t in expected}
    assert len(a_by)==len(actual) and len(m_by)==len(expected),'Duplicate entry identity.'
    missing=sorted(set(m_by)-set(a_by));extra=sorted(set(a_by)-set(m_by))
    comparisons=[];all_fields=('entry_time','exit_time','side','quantity','entry_price','exit_price','reference_gross_pnl')
    for m in expected:
        a=a_by.get(key_mc(m));errors=[]
        if a is None:errors=['missing AQ entry']
        else:
            pairs=[('entry_time',local(a['entry_time_utc']),m['entry']['time']),('exit_time',local(a['exit_time_utc']),m['exit']['time']),
                   ('side',a['side'],'long' if m['entry']['type']=='EntryLong' else 'short'),
                   ('quantity',Decimal(a['contracts']),Decimal(m['entry']['quantity'])),
                   ('entry_price',Decimal(a['entry_fill_price']),Decimal(m['entry']['price'])),
                   ('exit_price',Decimal(a['exit_fill_price']),Decimal(m['exit']['price'])),
                   ('reference_gross_pnl',Decimal(a['reference_gross_pnl']),Decimal(m['entry']['profit']))]
            errors=[name for name,x,y in pairs if x!=y]
        comparisons.append(dict(mc_trade=m['trade'],mc_entry_row=m['entry']['row'],mc_exit_row=m['exit']['row'],
            aq_trade=a['trade_number'] if a else '',entry_ct=m['entry']['time'],exit_ct=m['exit']['time'],
            mc_entry=m['entry']['price'],aq_entry=a['entry_fill_price'] if a else '',mc_exit=m['exit']['price'],
            aq_exit=a['exit_fill_price'] if a else '',mc_profit=m['entry']['profit'],aq_gross=a['reference_gross_pnl'] if a else '',
            mc_exit_signal=m['exit']['signal'],aq_exit_reason=a['exit_reason'] if a else '',exact=not errors,errors='; '.join(errors)))
    with (output/'all-is-trades.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(comparisons[0]));writer.writeheader();writer.writerows(comparisons)
    early=[c for c in comparisons if c['mc_exit_signal']=='End of Day Exit']
    with (output/'early-close-trades.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(comparisons[0]));writer.writeheader();writer.writerows(early)
    net=sum(Decimal(t['entry']['profit']) for t in expected)
    result=dict(reference_sha256=reference_hash,source_dataset=manifest['run_metadata']['dataset'],source_backtest_id=run_id,
        scope=dict(phase='is',start=start,end=end,aq_oos_run=False,reference_all_trades=len(mc),compared_is_trades=len(expected),
                   supplied_reference_contains_post_is_rows=len(mc)!=len(expected),
                   prior_access='User-supplied reference includes 2025–2026 trades. Comparison and new native replay are IS-only; no claim that supplied later outcomes are untouched.'),
        source_code=manifest['run_metadata']['strategy']['source_sha256'],execution=manifest['execution_settings'],
        exact_fields=all_fields,tolerances=dict(price='0',time_seconds=0,money='0'),
        aq_trades=len(actual),mc_trades=len(expected),matched=sum(c['exact'] for c in comparisons),missing=missing,extra=extra,
        mc_reported_profit=str(net),aq_net=manifest['summary']['total_net_pnl'],early_closes=early,
        status='matched' if not missing and not extra and all(c['exact'] for c in comparisons) else 'differences',
        costs='Comparison replay sets slippage and commission to zero, matching every exported trade Profit ($) arithmetic. MC Settings export was cancelled; account cost configuration is not established.',
        limitations='Historical IS trade comparison only; alternate Inputs, intrabar ambiguity and live execution are not certified.')
    (output/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    assert sha256(reference.read_bytes()).hexdigest()==reference_hash
    print(json.dumps({k:result[k] for k in ('status','source_backtest_id','aq_trades','mc_trades','matched','aq_net')},indent=2))
    assert result['status']=='matched',result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference',type=Path,required=True);parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();review(args.reference,args.report,args.output)
