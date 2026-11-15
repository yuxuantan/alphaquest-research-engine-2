"""Checked Sierra trades, minute features and bounded execution windows.

SCID layout adapted from alphaquest-research-engine at 1f76adb (the user's
repository), tools/convert_sierra_scid_to_parquet.py. Original sequence is never
sorted, timestamp-clamped or aggregated into an invented execution path.
"""
from dataclasses import dataclass,replace
from datetime import datetime,timedelta,timezone
from decimal import Decimal,InvalidOperation
from functools import lru_cache
from hashlib import sha256
import csv,json,shutil,struct,tempfile
from pathlib import Path
from uuid import uuid4

import numpy as np
from fastapi import APIRouter,Request,HTTPException
from starlette.concurrency import run_in_threadpool

VERSION='trade-ticks-v1'
EPOCH=datetime(1899,12,30,tzinfo=timezone.utc)
MINUTE=60_000_000
DTYPE=np.dtype([('time','<i8'),('open','<f4'),('ask','<f4'),('bid','<f4'),('price','<f4'),('trades','<u4'),('volume','<u4'),('bid_volume','<u4'),('ask_volume','<u4')])
IMPORT_CHUNK_RECORDS=250000
INDEX=np.dtype([(n,'<i8') for n in ('close','first','count','records','unknown','price_ticks_volume','largest','source')])
CSV_COLUMNS=['timestamp','price','volume','bid_volume','ask_volume']


def us(stamp):
    d=stamp-EPOCH
    return (d.days*86400+d.seconds)*1_000_000+d.microseconds


def instant(value):return EPOCH+timedelta(microseconds=int(value))


def file_hash(path):
    with Path(path).open('rb') as f:return __import__('hashlib').file_digest(f,'sha256').hexdigest()


@lru_cache(maxsize=512)
def _verify(path,size,mtime,expected):
    # Keep small integrity witnesses independently of the bounded mapping cache.
    # A long contract chain must not rehash an early file just because its mmap
    # was evicted. Any size/mtime change triggers complete hash verification.
    if file_hash(path)!=expected:raise ValueError('Tick source/index checksum changed; restore the original source before replay.')


@lru_cache(maxsize=8)
def _checked_file(path,size,mtime,expected):
    _verify(path,size,mtime,expected)
    return np.memmap(path,dtype=DTYPE,mode='r',offset=56)


def records(source):
    path=Path(source['path'])
    if path.is_symlink():raise ValueError('Tick source cannot be a symbolic link.')
    stat=path.stat()
    return _checked_file(str(path),stat.st_size,stat.st_mtime_ns,source['sha256'])


@dataclass(frozen=True,slots=True)
class TradeFlow:
    records:int
    bid_volume:Decimal
    ask_volume:Decimal
    unknown_volume:Decimal
    price_volume:Decimal
    largest_record_volume:int

    @property
    def delta(self):return self.ask_volume-self.bid_volume
    @property
    def known_volume(self):return self.ask_volume+self.bid_volume
    @property
    def delta_pct(self):return self.delta*100/self.known_volume if self.known_volume else Decimal(0)
    @property
    def vwap(self):
        volume=self.known_volume+self.unknown_volume
        return self.price_volume/volume if volume else None


@dataclass(frozen=True,slots=True)
class TickWindow:
    source:tuple # path, hash; immutable worker-serializable catalogue reference
    first:int
    count:int
    close_us:int
    skip:int=0

    def array(self):
        path,digest=self.source
        result=records(dict(path=path,sha256=digest))[self.first:self.first+self.count]
        result=result[(result['trades']==1)&(result['volume']>0)]
        return result[self.skip:]

    def tail(self,offset):return replace(self,skip=self.skip+offset)

    def point(self,bar,offset):
        row=self.array()[offset];price=Decimal(str(float(row['price'])))
        # Modeled native/portfolio dates shift the clock, never the source path.
        stamp=instant(row['time'])+(bar.timestamp_utc-instant(self.close_us))
        return replace(bar,timestamp_utc=stamp,open=price,high=price,low=price,close=price,
            tick_window=None,flow=None)

    def first_hit(self,lower=None,upper=None):
        a=self.array()['price'];mask=np.zeros(len(a),dtype=bool)
        if lower is not None:mask|=a<=float(lower)
        if upper is not None:mask|=a>=float(upper)
        hit=np.flatnonzero(mask)
        return int(hit[0]) if len(hit) else None

    def observe(self,risk,bar,stop=None):
        if risk is None:return
        rows=self.array()[:stop]
        if len(rows):
            prices=rows['price']
            # Preserve each new adverse extreme in source order. Fixed-size
            # account replay needs the FIRST observed crossing of any floor,
            # including trade-to-trade jumps, rather than a minute minimum.
            long=risk.position.side=='long'
            frontier=np.minimum.accumulate(prices) if long else np.maximum.accumulate(prices)
            changes=np.r_[True,np.diff(frontier)!=0]
            for value in prices[changes]:risk.observe_price(Decimal(str(float(value))),gap=True)
            favorable=prices.max() if long else prices.min()
            risk.observe_price(Decimal(str(float(favorable))),gap=True)
            if stop is None:risk.full_bars+=1
            risk.cross_session |= __import__('alphaquest.intratrade',fromlist=['session']).session(bar.timestamp_utc)!=__import__('alphaquest.intratrade',fromlist=['session']).session(risk.position.entry_time_utc)


@lru_cache(maxsize=8)
def _index(path,size,mtime,digest):
    _verify(path,size,mtime,digest)
    return np.memmap(path,dtype=INDEX,mode='r')


def check_sources(metadata):
    tick=metadata['tick_data'];p=Path(tick['index_path'])
    if p.is_symlink():raise ValueError('Tick index cannot be a symbolic link.')
    stat=p.stat();idx=_index(str(p),stat.st_size,stat.st_mtime_ns,tick['index_sha256'])
    for source in tick['sources']:records(source)
    return idx


def attach(bars,metadata):
    tick=metadata['tick_data'];idx=check_sources(metadata)
    for bar in bars:
        value=us(bar.timestamp_utc);i=int(np.searchsorted(idx['close'],value))
        if i==len(idx) or idx[i]['close']!=value:raise ValueError('Minute bar is absent from its frozen tick index.')
        r=idx[i];source=tick['sources'][int(r['source'])]
        flow=TradeFlow(int(r['records']),bar.down_vol,bar.up_vol,Decimal(int(r['unknown'])),
            Decimal(int(r['price_ticks_volume']))*Decimal(metadata['instrument_settings']['tick_size']),int(r['largest']))
        yield replace(bar,tick_window=TickWindow((source['path'],source['sha256']),int(r['first']),int(r['count']),value),flow=flow)


def header(path):
    size=path.stat().st_size
    with path.open('rb') as f:b=f.read(56)
    if len(b)!=56 or b[:4]!=b'SCID':raise ValueError('Expected a Sierra Chart SCID file with its original header.')
    hs,rs=struct.unpack_from('<II',b,4);version=struct.unpack_from('<H',b,12)[0]
    if (hs,rs,version)!=(56,40,1):raise ValueError('Supported SCID format: 56-byte header, 40-byte records, version 1 with microsecond integer timestamps.')
    if size<=56 or (size-56)%40:raise ValueError('SCID has no complete records or has a truncated record.')
    return (size-56)//40


def csv_to_scid(path,target):
    with path.open(encoding='utf-8-sig',newline='') as f,target.open('wb') as out:
        out.write(struct.pack('<4sIIHH',b'SCID',56,40,1,0)+bytes(40))
        reader=csv.DictReader(f,strict=True)
        if reader.fieldnames!=CSV_COLUMNS:raise ValueError('Trade CSV header must be: '+','.join(CSV_COLUMNS))
        for number,r in enumerate(reader,2):
            try:
                if None in r or any(v is None for v in r.values()):raise ValueError('expected exactly five cells')
                stamp=datetime.fromisoformat(r['timestamp'].replace('Z','+00:00'))
                if stamp.tzinfo is None or stamp.utcoffset()!=timedelta(0):raise ValueError('timestamps must explicitly use UTC')
                fraction=r['timestamp'].split('T')[-1].split('.')[1].split('+')[0].rstrip('Z') if '.' in r['timestamp'] else ''
                if len(fraction)>6:raise ValueError('CSV timestamps support at most six fractional digits; do not discard exchange ordering precision')
                price=Decimal(r['price']);vol,bid,ask=(int(r[k]) for k in CSV_COLUMNS[2:])
                packed=struct.pack('<q4f4I',us(stamp),0.,0.,0.,float(price),1,vol,bid,ask)
                if Decimal(str(struct.unpack_from('<f',packed,20)[0]))!=price:raise ValueError('price is not exactly representable in the supported SCID grid')
                out.write(packed)
            except (ValueError,OverflowError,struct.error,InvalidOperation) as e:raise ValueError(f'Trade CSV row {number}: {e}') from e


def build(store,upload,filename,name,symbol,source_timezone,settings,progress=None):
    from .datasets import COLUMNS,validate_csv_file
    from zoneinfo import ZoneInfo
    if source_timezone!='UTC':raise ValueError('Trade tick timestamps are UTC. Select UTC; local session clocks are derived during strategy execution.')
    zone=ZoneInfo(source_timezone);tick=Decimal(settings['tick_size'])
    root=store.path.parent/'tick_sources';root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.pending-',dir=root) as temporary:
        stage=Path(temporary);raw=stage/'trades.scid'
        if filename.lower().endswith('.scid'):shutil.copyfile(upload,raw)
        elif filename.lower().endswith('.csv'):csv_to_scid(upload,raw)
        else:raise ValueError('Choose a .scid trade file or canonical trade .csv.')
        total=header(raw);a=np.memmap(raw,dtype=DTYPE,mode='r',offset=56)
        csv_path=stage/'bars.csv';index_path=stage/'minutes.bin';last=None;pending=None;ordinal=0;raw_count=0;previous_tick=None;totals=dict(volume=0,bid_volume=0,ask_volume=0)
        with csv_path.open('w',newline='') as text,index_path.open('wb') as index:
            writer=csv.writer(text,lineterminator='\n');writer.writerow(COLUMNS)
            def emit(part,start):
                nonlocal last,raw_count
                valid=part[(part['trades']==1)&(part['volume']>0)]
                if not len(valid):return
                close=(int(valid['time'][0])//MINUTE+1)*MINUTE
                if last is not None and close<=last:raise ValueError('Tick minute ordering is inconsistent.')
                price=valid['price'].astype(np.float64);vol=valid['volume'].astype(np.int64)
                bid=int(valid['bid_volume'].sum(dtype=np.int64));ask=int(valid['ask_volume'].sum(dtype=np.int64));volume=int(vol.sum())
                totals['volume']+=volume;totals['bid_volume']+=bid;totals['ask_volume']+=ask
                price_ticks=np.rint(price/float(tick)).astype(np.int64)
                if len(price_ticks)*max(abs(int(price_ticks.min())),abs(int(price_ticks.max())))*int(vol.max())>2**63-1:raise ValueError('Minute price-volume total exceeds exact supported integer range.')
                pv=int((price_ticks*vol).sum(dtype=np.int64));stamp=instant(close).astimezone(zone)
                vals=[Decimal(str(float(v))) for v in (price[0],price.max(),price.min(),price[-1])]
                writer.writerow([stamp.strftime('%m/%d/%Y'),stamp.strftime('%H:%M'),*vals,volume,ask,bid])
                index.write(np.array([(close,start,len(part),len(valid),volume-bid-ask,pv,int(vol.max()),0)],dtype=INDEX).tobytes())
                last=close;raw_count+=len(valid)
            for offset in range(0,total,IMPORT_CHUNK_RECORDS):
                chunk=a[offset:offset+IMPORT_CHUNK_RECORDS]
                # Deleted zero records may remain in Sierra files. They cannot
                # become price observations; preserve the underlying ordinals.
                valid=(chunk['trades']!=0)|(chunk['volume']!=0)
                empty=~valid
                if np.any(empty):
                    unused=chunk[empty]
                    if any(np.any(unused[name]!=0) for name in DTYPE.names):
                        raise ValueError('Quote-only or nonzero deleted records cannot be interpreted as individual trades. Supply a trade-only source.')
                v=chunk[valid]
                if len(v):
                    if np.any(v['trades']!=1) or np.any(v['volume']==0):raise ValueError('Tick replay requires individual trade records (NumberOfTrades=1 and positive volume); aggregated/quote-only records are unsupported.')
                    if np.any(~np.isfinite(v['price'])) or np.any(v['price']<=0):raise ValueError('Trade prices must be finite and positive.')
                    scaled=v['price'].astype(np.float64)/float(tick)
                    if np.any(scaled!=np.rint(scaled)):raise ValueError('Trade price is off the declared instrument tick grid.')
                    if np.any(v['bid_volume'].astype(np.uint64)+v['ask_volume'].astype(np.uint64)>v['volume']):raise ValueError('Bid plus ask volume exceeds recorded trade volume.')
                    times=v['time'];instant(int(times[0]));instant(int(times[-1]))
                    if np.any(np.diff(times)<0) or (previous_tick is not None and int(times[0])<previous_tick):raise ValueError('Trade timestamps invert. Source order cannot be repaired by sorting or clamping.')
                    previous_tick=int(times[-1])
                # Keep the final minute across chunk boundaries (including its
                # special component markers), never split a source minute.
                if pending is not None:chunk=np.concatenate((pending,chunk));offset=ordinal
                elif not len(v):continue
                positive=np.flatnonzero((chunk['trades']==1)&(chunk['volume']>0))
                if not len(positive):continue
                mins=chunk['time'][positive]//MINUTE;starts=np.r_[0,np.flatnonzero(np.diff(mins))+1]
                for i,j in zip(starts[:-1],starts[1:]):
                    left=int(positive[i]);right=int(positive[j]);emit(chunk[left:right],offset+left)
                left=int(positive[starts[-1]]);pending=chunk[left:].copy();ordinal=offset+left
                if progress:progress('validating',min(total,offset+len(chunk))*40+56,raw.stat().st_size,raw_count)
            if pending is not None:emit(pending,ordinal)
        del a
        if not raw_count:raise ValueError('No individual trades were found.')
        with csv_path.open('rb') as f:metadata=validate_csv_file(f,Path(filename).stem+".csv",source_timezone)
        metadata['instrument_settings']=settings;metadata['csv_sha256']=metadata['sha256']
        raw_hash=file_hash(raw);index_hash=file_hash(index_path)
        metadata['sha256']=sha256(json.dumps([VERSION,metadata['csv_sha256'],raw_hash,index_hash],separators=(',',':')).encode()).hexdigest()
        token=uuid4().hex;destination=root/token
        metadata['tick_data']=dict(version=VERSION,records=raw_count,raw_bytes=raw.stat().st_size,original_filename=filename,contract=symbol,
            index_path=str(destination/'minutes.bin'),index_sha256=index_hash,
            sources=[dict(path=str(destination/'trades.scid'),sha256=raw_hash,contract=symbol)],
            flow_classification=dict(**totals,unknown_volume=totals['volume']-totals['bid_volume']-totals['ask_volume'],classified_pct=str(round(Decimal(totals['bid_volume']+totals['ask_volume'])*100/Decimal(totals['volume']),2))),
            timestamp_basis='UTC source timestamp; equal timestamps retain original file order',
            bars='one-minute close-labelled trade OHLCV; ask/bid volumes retain their source classification',
            execution='ordered trade-price replay; full fills and declared slippage, not queue/latency reconstruction')
        metadata['warnings'].append('Trade ticks: aggressor-unknown volume is retained. Recorded components are not claimed to be reconstructed exchange-sized orders.')
        destination.mkdir()
        try:
            shutil.move(str(raw),destination/'trades.scid');shutil.move(str(index_path),destination/'minutes.bin')
            with csv_path.open('rb') as f:result=store.save_file(f,metadata,name,symbol,progress)
        except BaseException:shutil.rmtree(destination);raise
        return result


router=APIRouter(prefix='/api/datasets',tags=['Trade tick datasets'])


@router.post('/ticks',status_code=201)
async def upload_ticks(request:Request,filename:str,name:str,symbol:str='NQ',source_timezone:str='UTC',tick_size:str='0.25',point_value:str='20',progress_id:str|None=None,disclosure:str='standard'):
    from .datasets import instrument_settings,DuplicateDataset,InvalidDataset
    from uuid import UUID
    if not name.strip() or len(name)>120:raise HTTPException(422,'Give the dataset a name of at most 120 characters.')
    progress=None
    try:
        if len(filename)>255 or not symbol.strip() or len(symbol)>32:raise ValueError('Supply a filename up to 255 characters and a root instrument up to 32 characters.')
        settings=instrument_settings(tick_size,point_value)
        if disclosure not in ('standard','metadata_only'):raise ValueError('Choose standard or metadata_only disclosure.')
        progress=None
        if progress_id:
            operation_id=str(UUID(progress_id));request.app.state.progress.start(operation_id)
            progress=lambda *args:request.app.state.progress.update(operation_id,*args)
        with tempfile.NamedTemporaryFile(prefix='tick-upload-',suffix=Path(filename).suffix) as f:
            count=0;size=int(request.headers.get('content-length',0))
            async for chunk in request.stream():
                await run_in_threadpool(f.write,chunk);count+=len(chunk)
                if progress:progress('uploading',count,size,0)
            f.flush()
            result=await run_in_threadpool(build,request.app.state.store,Path(f.name),filename,name.strip(),symbol.strip(),source_timezone,settings,progress)
        if progress:progress('done',count,count,result['row_count'])
        return request.app.state.research_access.public_dataset(result,disclosure=disclosure,origin='tick_dataset_save')
    except DuplicateDataset as e:
        if progress:progress('failed')
        raise HTTPException(409,'This exact tick source is already saved.') from e
    except InvalidDataset as e:
        if progress:progress('failed')
        raise HTTPException(422,str(e)) from e
    except (ValueError,OverflowError,OSError,csv.Error) as e:
        if progress:progress('failed')
        raise HTTPException(422,str(e)) from e

@router.get('/ticks/example')
def trade_example():
    from fastapi.responses import Response
    return Response('timestamp,price,volume,bid_volume,ask_volume\n2026-01-05T14:30:00.000000Z,25000.25,2,0,2\n2026-01-05T14:30:00.000001Z,25000.00,1,1,0\n',media_type='text/csv',headers={'Content-Disposition':'attachment; filename="trade-ticks-example.csv"'})


def compose(store,name,symbol,segments):
    """Explicit ex-ante roll schedule; never select on same-session final volume."""
    from .datasets import COLUMNS,validate_csv_file
    from .backtest_data import read_bars
    from .session_calendar import session_date
    from datetime import date
    from zoneinfo import ZoneInfo
    if not segments or len(segments)>100:raise ValueError('Declare one to 100 non-overlapping source/session ranges.')
    sources=[];parents=[];last_session=None;rows=0;count=0;settings=None;rolls=[]
    root=store.path.parent/'tick_sources';root.mkdir(exist_ok=True)
    token=uuid4().hex;destination=root/token
    with tempfile.TemporaryDirectory(prefix='.compose-',dir=root) as temp:
        temp=Path(temp);bars_path=temp/'bars.csv';index_path=temp/'minutes.bin'
        with bars_path.open('w',newline='') as output,index_path.open('wb') as index:
            writer=csv.writer(output,lineterminator='\n');writer.writerow(COLUMNS)
            previous=None
            for item in segments:
                first=date.fromisoformat(item['first_session']);last=date.fromisoformat(item['last_session'])
                if first>last or (last_session is not None and first<=last_session):raise ValueError('Roll ranges must be ordered, non-overlapping CME session dates.')
                last_session=last;ds=store.get(item['dataset_id'])
                if not ds or not ds.get('tick_data'):raise ValueError('Every roll source must be an existing trade tick dataset.')
                if ds.get('symbol')!=symbol:raise ValueError('All roll sources must use the same declared root instrument.')
                if settings is None:settings=ds['instrument_settings']
                if any(Decimal(ds['instrument_settings'][k])!=Decimal(settings[k]) for k in settings):raise ValueError('Roll sources require identical instrument settings.')
                parents.append(ds['id']);added=0
                with read_bars(store,ds['id']) as bars:
                    for b in bars:
                        if not first<=session_date(b.timestamp_utc)<=last:continue
                        if previous is not None and b.timestamp_utc<=previous:raise ValueError('Roll sources contain overlapping timestamps.')
                        source=dict(path=b.tick_window.source[0],sha256=b.tick_window.source[1],contract=ds['tick_data']['contract'])
                        if source not in sources:sources.append(source)
                        flow=b.flow;volume=b.volume
                        stamp=b.timestamp_utc.astimezone(timezone.utc)
                        writer.writerow([stamp.strftime('%m/%d/%Y'),stamp.strftime('%H:%M'),b.open,b.high,b.low,b.close,volume,b.up_vol,b.down_vol])
                        pv=flow.price_volume/Decimal(settings['tick_size'])
                        index.write(np.array([(us(b.timestamp_utc),b.tick_window.first,b.tick_window.count,flow.records,int(flow.unknown_volume),int(pv),flow.largest_record_volume,sources.index(source))],dtype=INDEX).tobytes())
                        rows+=1;count+=flow.records;added+=1;previous=b.timestamp_utc
                if not added:raise ValueError('A roll range contains no observed source minutes.')
                rolls.append(dict(dataset_id=ds['id'],source_sha256=ds['sha256'],first_session=str(first),last_session=str(last),minutes=added))
        with bars_path.open('rb') as f:metadata=validate_csv_file(f,'composed-ticks.csv','UTC')
        metadata['csv_sha256']=metadata['sha256'];metadata['instrument_settings']=settings
        index_hash=file_hash(index_path)
        metadata['sha256']=sha256(json.dumps([VERSION,metadata['csv_sha256'],index_hash,rolls],sort_keys=True,separators=(',',':')).encode()).hexdigest()
        metadata['tick_data']=dict(version=VERSION,records=count,contract=symbol,sources=sources,
            raw_bytes=sum(Path(s['path']).stat().st_size for s in sources),index_path=str(destination/'minutes.bin'),index_sha256=index_hash,
            parent_dataset_ids=list(dict.fromkeys(parents)),roll_schedule=rolls,
            timestamp_basis='UTC source timestamp and original per-file ordinal',bars='completed one-minute trade OHLCV',
            execution='ordered trade replay; explicit unadjusted contract roll schedule; no look-ahead selection')
        metadata['warnings'].append('Explicit unadjusted contract roll schedule. Strategy indicators can cross roll gaps; research the schedule before inspecting outcomes.')
        destination.mkdir()
        try:
            shutil.move(index_path,destination/'minutes.bin')
            with bars_path.open('rb') as f:return store.save_file(f,metadata,name,symbol)
        except BaseException:shutil.rmtree(destination);raise


@router.post('/ticks/compose',status_code=201)
def compose_ticks(request:Request,body:dict):
    from .datasets import DuplicateDataset,InvalidDataset
    try:
        if set(body)!={'name','symbol','segments'}:raise ValueError('Supply name, symbol and segments.')
        if not isinstance(body['name'],str) or not body['name'].strip() or len(body['name'])>120:raise ValueError('Give the composed dataset a name of at most 120 characters.')
        result=compose(request.app.state.store,body['name'].strip(),body['symbol'],body['segments'])
        return request.app.state.research_access.public_dataset(result,origin='tick_dataset_compose')
    except DuplicateDataset as e:raise HTTPException(409,'This composed tick source already exists.') from e
    except (ValueError,KeyError,TypeError,InvalidDataset) as e:raise HTTPException(422,str(e)) from e

@router.get('/{dataset_id}/ticks/source/{source_index}')
def download_source(dataset_id:str,source_index:int,request:Request):
    from .research_access import guard_read
    from fastapi.responses import FileResponse
    ds=request.app.state.store.get(dataset_id)
    if not ds or not ds.get('tick_data'):raise HTTPException(404,'Trade tick source not found.')
    guard_read(request.app.state.store,dataset_id,origin='trade_tick_download')
    sources=ds['tick_data']['sources']
    if not 0<=source_index<len(sources):raise HTTPException(404,'Trade tick source not found.')
    source=sources[source_index];records(source)
    return FileResponse(source['path'],media_type='application/octet-stream',filename=f'{ds["name"]}-{source_index}.scid')


@router.get('/{dataset_id}/ticks/flow')
def download_flow(dataset_id:str,request:Request):
    from .research_access import guard_read
    from .backtest_data import read_bars
    from fastapi.responses import StreamingResponse
    import io
    store=request.app.state.store;ds=store.get(dataset_id)
    if not ds or not ds.get('tick_data'):raise HTTPException(404,'Trade tick source not found.')
    guard_read(store,dataset_id,origin='trade_flow_download')
    def generate():
        buffer=io.StringIO();writer=csv.writer(buffer,lineterminator='\n')
        writer.writerow(['minute_close_utc','trade_records','volume','bid_volume','ask_volume','unknown_volume','delta','delta_pct','trade_vwap','largest_record_volume'])
        yield buffer.getvalue();buffer.seek(0);buffer.truncate(0)
        with read_bars(store,dataset_id) as bars:
            for bar in bars:
                f=bar.flow
                writer.writerow([bar.timestamp_utc.isoformat(),f.records,bar.volume,f.bid_volume,f.ask_volume,f.unknown_volume,f.delta,f'{f.delta_pct:.2f}',f'{f.vwap:.8f}',f.largest_record_volume])
                if buffer.tell()>65536:yield buffer.getvalue();buffer.seek(0);buffer.truncate(0)
            if buffer.tell():yield buffer.getvalue()
    return StreamingResponse(generate(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="completed-minute-trade-flow.csv"'})
