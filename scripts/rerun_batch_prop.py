"""Refresh N/A prop results through the normal batch API; never run strategies."""
import argparse
from collections import Counter,defaultdict
from decimal import Decimal
import csv
import io
import json
from pathlib import Path
import time
from urllib.request import Request,urlopen


def save(path,value):path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def cash_check(report):
    calculations=report['calculations'];history=calculations.get('history')
    if history is None:return
    slots=int(report['settings']['SLOTS']);ladder=calculations['rules']['ladder']
    receipts=defaultdict(Decimal);costs=defaultdict(Decimal)
    def quarter(date):return date[:4]+'Q'+str((int(date[5:7])-1)//3+1)
    for account in history['accounts']:
        costs[quarter(account['start'])]+=Decimal(str(calculations['training_economics']['cost_per_funded']))*slots
        for index,date in enumerate(account['payout_days']):
            amount=account['trader_receipts'][index][1] if 'trader_receipts' in account else ladder[index]
            receipts[quarter(date)]+=Decimal(str(amount))*slots
    for row in history['quarters']:
        assert abs(row['payouts']-round(receipts[row['period']]))<=1 # Existing cash rounds binary sums at quarter boundaries.
        assert abs(row['costs']-round(costs[row['period']]))<=1
        assert row['net']==row['payouts']-row['costs']
    assert history['totals']['net']==sum(q['net'] for q in history['quarters'])


def rerun(url,batch_id,output):
    output.mkdir(parents=True,exist_ok=False)
    base='/api/backtests/batches/'+batch_id
    def raw(path,post=False):
        req=Request(url+path,data=b'{}' if post else None,headers={'Content-Type':'application/json'})
        with urlopen(req,timeout=600) as response:return response.read()
    def get(path):return json.loads(raw(path))
    before=get(base+'/results?limit=1000')
    assert before['total']==len(before['items']),'Review all pages before refreshing this batch'
    save(output/'before-results.json',before)
    (output/'original-results.csv').write_bytes(raw(base+'/exports/results?prop_revision=0'))
    targets=[]
    for row in before['items']:
        for account,metric,item in [('apex','historical_net',row.get('prop_analysis')),
                                    ('lucid','lucid_historical_net',(row.get('prop_companions') or [None])[0])]:
            if item and row['metrics'].get(metric) is None:
                targets.append(dict(trial=row['trial'],account=account,source_id=row['run_id'],old_id=item.get('id'),
                    original_id=item.get('original_analysis_id') or item.get('id')))
    save(output/'targets.json',targets)
    print('Requested N/A analyses:',dict(Counter(t['account'] for t in targets)),flush=True)
    submitted=json.loads(raw(base+'/prop-refresh',post=True));save(output/'refresh-start.json',submitted)
    print('Queued',submitted['queued'],'reused',submitted['reused'],'blocked',submitted['blocked'],flush=True)
    started=time.monotonic();last=None
    while True:
        state=get(base+'/prop-refresh')
        save(output/'progress.json',dict(state,elapsed_seconds=time.monotonic()-started))
        value=json.dumps(state,sort_keys=True)
        if value!=last:
            print('Progress',json.dumps(state),flush=True);last=value
        if not state['pending']:break
        if time.monotonic()-started>21600:raise TimeoutError('Refresh still pending; inspect progress.json and existing catalogue; do not resubmit unknown jobs')
        time.sleep(5)
    after=get(base+'/results?limit=1000');save(output/'after-results.json',after)
    revision=after['prop_revision']
    (output/'updated-results.csv').write_bytes(raw(base+f'/exports/results?prop_revision={revision}&sort=historical_net&direction=desc'))
    assert raw(base+'/exports/results?prop_revision=0')==(output/'original-results.csv').read_bytes()
    previous={row['trial']:row for row in before['items']};current={row['trial']:row for row in after['items']}
    for trial,old in previous.items():
        new=current[trial]
        assert new['run_id']==old['run_id'] and new['parameters']==old['parameters']
        for key in old['metrics']:
            if key not in ('historical_net','lucid_historical_net') or old['metrics'][key] is not None:
                assert new['metrics'][key]==old['metrics'][key],(trial,key)
    outcomes=[]
    for target in targets:
        row=current[target['trial']];account=target['account']
        item=row['prop_analysis'] if account=='apex' else row['prop_companions'][0]
        assert item['original_analysis_id']==target['original_id']
        result=dict(target,new_id=item.get('id'),status=item['status'],historical_net=item.get('historical_net'),reason=item.get('reason'))
        if item['status']=='complete':
            report=get('/api/prop-analyses/'+item['id']+'/downloads/report.json')
            old=get('/api/prop-analyses/'+target['old_id']+'/downloads/report.json')
            assert report['source']==old['source'] and report['settings']==old['settings']
            joint=report['calculations'].get('joint_sizing',{})
            result.update(model_version=report['model_version'],selected=joint.get('selected'),
                exclusions=joint.get('excluded_acquisition_candidates'),blockers=joint.get('blocking_acquisition_candidates'),
                calculation_reused_from=report['runtime'].get('calculation_reused_from'))
            cash_check(report)
            history=report['calculations'].get('history')
            assert (history['totals']['net'] if history else None)==result['historical_net']
        outcomes.append(result)
    save(output/'outcomes.json',outcomes)
    with (output/'outcomes.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=['trial','account','old_id','new_id','status','historical_net','reason'])
        writer.writeheader();writer.writerows({k:r.get(k) for k in writer.fieldnames} for r in outcomes)
    # Verify current CSV agrees with the same pinned result links and ordering.
    exported=list(csv.DictReader(io.StringIO((output/'updated-results.csv').read_text())))
    sorted_rows=get(base+f'/results?limit=1000&sort=historical_net&direction=desc&prop_revision={revision}')['items']
    assert [int(r['trial']) for r in exported]==[r['trial'] for r in sorted_rows]
    for r in exported:
        row=current[int(r['trial'])]
        for metric in ['historical_net','lucid_historical_net']:
            assert r[metric]==('' if row['metrics'][metric] is None else str(row['metrics'][metric]))
    summary=dict(batch_id=batch_id,requested=len(targets),requested_by_account=dict(Counter(t['account'] for t in targets)),
        recovered=sum(r['historical_net'] is not None for r in outcomes),
        still_unavailable=sum(r['historical_net'] is None for r in outcomes),errors=sum(r['status']=='error' for r in outcomes),
        blocked=sum(r['status']=='incompatible' for r in outcomes),accounts=state['accounts'],revision=revision,
        already_available_values_preserved=True,original_csv_preserved=True,updated_csv_matches_table=True,
        original_strategy_backtests_executed=0,elapsed_seconds=time.monotonic()-started)
    save(output/'verification.json',summary);print('Complete',json.dumps(summary),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://localhost:8000')
    parser.add_argument('--batch-id',required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();rerun(args.url.rstrip('/'),args.batch_id,args.output)
