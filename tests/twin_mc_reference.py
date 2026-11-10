"""Read-only MC companion export parsing for development qualification only."""
from datetime import datetime,timedelta
from decimal import Decimal
from pathlib import Path
import posixpath
import xml.etree.ElementTree as ET
import zipfile

NS={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def read_reference(path):
    path=Path(path)
    with zipfile.ZipFile(path) as archive:
        if sum(info.file_size for info in archive.infolist())>64*1024*1024:
            raise ValueError('Reference workbook exceeds expanded-size limit.')
        strings=[''.join(node.itertext()) for node in ET.fromstring(archive.read('xl/sharedStrings.xml'))] if 'xl/sharedStrings.xml' in archive.namelist() else []
        book=ET.fromstring(archive.read('xl/workbook.xml'))
        links={r.attrib['Id']:r.attrib['Target'] for r in ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))}
        sheet=next(s for s in book.findall('m:sheets/m:sheet',NS) if s.attrib['name']=='List of Trades')
        target=links[sheet.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']]
        target=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
        trades=[];header=None
        for row in ET.fromstring(archive.read(target)).findall('m:sheetData/m:row',NS):
            cells={}
            for cell in row:
                v=cell.find('m:v',NS)
                value=v.text if v is not None else ''.join(cell.find('m:is',NS).itertext()) if cell.find('m:is',NS) is not None else ''
                if cell.attrib.get('t')=='s':value=strings[int(value)]
                cells[''.join(filter(str.isalpha,cell.attrib['r']))]=value
            if cells.get('A')=='Trade #':header=cells;continue
            if header is None:continue
            r={header[k]:v for k,v in cells.items() if k in header}
            if r.get('Type') not in ('EntryLong','EntryShort','ExitLong','ExitShort'):continue
            serial=Decimal(r['Date'])
            if serial==int(serial) and r.get('Time'):
                serial+=Decimal(r['Time'])%1
            stamp=datetime(1899,12,30)+timedelta(seconds=int((serial*86400).quantize(Decimal(1))))
            event=dict(row=int(row.attrib['r']),type=r['Type'],signal=r['Signal'],time=stamp.isoformat(' '),
                       price=r['Price'],quantity=r['Contracts'],profit=r.get('Profit ($)',''))
            if r['Type'].startswith('Entry'):
                if trades and 'exit' not in trades[-1]:raise ValueError('Reference has an unresolved entry.')
                trades.append(dict(trade=int(r['Trade #']),entry=event))
            else:
                if not trades or 'exit' in trades[-1]:raise ValueError('Reference exit has no unique entry.')
                trades[-1]['exit']=event
        if not trades or any('exit' not in t for t in trades):raise ValueError('Reference requires completed paired trades.')
    if len({t['trade'] for t in trades})!=len(trades):raise ValueError('Duplicate reference trade numbers.')
    for trade in trades:
        entry,exit=trade['entry'],trade['exit']
        if entry['quantity']!=exit['quantity']:raise ValueError('Reference entry/exit quantities differ.')
    return trades
