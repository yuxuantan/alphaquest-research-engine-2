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
extensions=[Extension('alphaquest.prop._native_compiled',[str(wrapper)],extra_compile_args=flags,optional=True)]
lucid=Path(__file__).parent/'alphaquest/prop/lucid_engine.py'
lucid_wrapper=generated/'_lucid_compiled.pyx'
lucid_wrapper.write_text('include '+json.dumps(lucid.resolve().as_posix())+'\nCOMPILED_SOURCE_SHA256 = '+repr(sha256(lucid.read_bytes()).hexdigest())+'\n')
extensions.append(Extension('alphaquest.prop._lucid_compiled',[str(lucid_wrapper)],extra_compile_args=flags,optional=True))
setup(ext_modules=cythonize(extensions,compiler_directives=dict(language_level=3,annotation_typing=False,infer_types=False,binding=True)))
