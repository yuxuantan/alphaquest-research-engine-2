from pathlib import Path
import pickle
import pytest
from test_native_forecast_profiles import catalogue
from alphaquest.prop.native_preparation import NativeBarSequence


def test_exact_spooled_rows_and_changed_bytes_reject(tmp_path):
 c=catalogue.__wrapped__();values=NativeBarSequence(c,tmp_path)
 worker=pickle.loads(pickle.dumps(values))
 for i in (0,1,42,len(c.bars)-1):assert worker[i]==c.bars[i]
 assert worker[-1]==c.bars[-1]
 worker.close()
 raw=Path(values.filename).read_bytes();Path(values.filename).write_bytes(b'X'+raw[1:])
 changed=pickle.loads(pickle.dumps(values))
 with pytest.raises(ValueError,match='spool changed'):changed[0]


@pytest.mark.parametrize('bar_budget,number_budget',[(0,0),(4096,1024),(32*1024*1024,4*1024*1024)])
def test_decoded_caches_are_bounded_exact_and_not_serialized(tmp_path,monkeypatch,bar_budget,number_budget):
 monkeypatch.setattr(NativeBarSequence,'BAR_CACHE_BYTES',bar_budget)
 monkeypatch.setattr(NativeBarSequence,'NUMBER_CACHE_BYTES',number_budget)
 c=catalogue.__wrapped__();rows=NativeBarSequence(c,tmp_path)
 for i in [*range(len(c.bars)),*reversed(range(len(c.bars)))]:
  assert rows[i]==c.bars[i]
  assert rows._bar_bytes<=bar_budget and rows._number_bytes<=number_budget
 copied=pickle.loads(pickle.dumps(rows))
 assert not copied._cache and copied._numbers.cache_info().currsize==0
 assert copied._bar_bytes==copied._number_bytes==0
 assert copied[0]==c.bars[0]
 rows.close();copied.close()
 assert rows._bar_bytes==rows._number_bytes==0
