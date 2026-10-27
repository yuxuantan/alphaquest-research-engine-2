"""Compile the same account model used by the Python qualification reference."""
from hashlib import sha256
import json
import os
from pathlib import Path
from setuptools import Extension, setup
from Cython.Build import cythonize

source=Path(__file__).parent/'alphaquest/prop/native_engine.py'
generated=Path('build/cython');generated.mkdir(parents=True,exist_ok=True)
wrapper=generated/'_native_compiled.pyx'
wrapper.write_text('include '+json.dumps(source.resolve().as_posix())+'\nCOMPILED_SOURCE_SHA256 = '+repr(sha256(source.read_bytes()).hexdigest())+'\n')
flags=['/O2','/fp:strict'] if os.name=='nt' else ['-O3','-fno-fast-math','-ffp-contract=off']
extension=Extension('alphaquest.prop._native_compiled',[str(wrapper)],extra_compile_args=flags,optional=True)
setup(ext_modules=cythonize([extension],compiler_directives=dict(language_level=3,annotation_typing=False,infer_types=False,binding=True)))
