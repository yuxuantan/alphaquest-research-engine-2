"""Select a matching AlphaQuest-owned compiled model or its Python reference."""
from functools import lru_cache
from hashlib import sha256
import os
from pathlib import Path
from . import native_engine as reference

try:
    from . import _native_compiled as compiled
except (ImportError,OSError):
    compiled=None

SOURCE_SHA256=sha256(Path(reference.__file__).read_bytes()).hexdigest()
if compiled is not None and compiled.COMPILED_SOURCE_SHA256!=SOURCE_SHA256:
    compiled=None


def module():
    mode=os.environ.get('ALPHAQUEST_PROP_BACKEND','auto')
    if mode not in ('auto','python','compiled'):raise ValueError('ALPHAQUEST_PROP_BACKEND must be auto, python or compiled.')
    if mode=='compiled' and compiled is None:raise RuntimeError('Rebuild the matching AlphaQuest compiled prop kernel before forcing compiled mode.')
    return compiled if compiled is not None and mode!='python' else reference


@lru_cache(maxsize=2)
def _identity(name):
    return dict(name=name,source_sha256=SOURCE_SHA256,
                binary_sha256=sha256(Path(compiled.__file__).read_bytes()).hexdigest() if name=='compiled' else None,
                arithmetic='Strict IEEE doubles; fast math and floating contraction disabled; unchanged MT19937 draws')


def identity():return dict(_identity('compiled' if module() is compiled else 'python'))


Rules=reference.Rules
compact_neutral_runs=reference.compact_neutral_runs
def FundedAccount(*args,**kwargs):return module().FundedAccount(*args,**kwargs)
def evaluation(*args,**kwargs):return module().evaluation(*args,**kwargs)
def funded(*args,**kwargs):return module().funded(*args,**kwargs)
