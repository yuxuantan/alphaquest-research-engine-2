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
