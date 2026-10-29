"""Select the identical optional compiled LucidFlex implementation."""
from hashlib import sha256
from pathlib import Path
import os
from . import lucid_engine as reference
try:
    from . import _lucid_compiled as compiled
except (ImportError,OSError):
    compiled=None
SOURCE_SHA256=sha256(Path(reference.__file__).read_bytes()).hexdigest()
if compiled is not None and compiled.COMPILED_SOURCE_SHA256!=SOURCE_SHA256:compiled=None

def module():
    mode=os.environ.get('ALPHAQUEST_PROP_BACKEND','auto')
    if mode not in ('auto','python','compiled'):raise ValueError('Unknown prop backend.')
    if mode=='compiled' and compiled is None:raise RuntimeError('Rebuild the matching LucidFlex compiled prop kernel.')
    return compiled if compiled is not None and mode!='python' else reference

def identity():
    model=module()
    return dict(name='compiled' if model is compiled else 'python',source_sha256=SOURCE_SHA256,
        binary_sha256=sha256(Path(compiled.__file__).read_bytes()).hexdigest() if model is compiled else None,
        arithmetic='Strict IEEE doubles; shared observed-adverse-frontier checks')

Rules=reference.Rules
def FundedAccount(*a,**k):return module().FundedAccount(*a,**k)
def evaluation(*a,**k):return module().evaluation(*a,**k)
def funded(*a,**k):return module().funded(*a,**k)
