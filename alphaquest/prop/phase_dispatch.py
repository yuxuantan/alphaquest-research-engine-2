"""Phase-only dispatch shared by HTTP, campaigns and AnalysisStore.

Simulation, selection, numerical identity and artifact schemas remain owned by
the selected optimizer. Resolve lazily so dispatch never needs the other phase.
"""
from importlib import import_module


def module_for(phase):
    if phase not in ('evaluation', 'funded'):
        raise ValueError('Unknown independent phase; use evaluation or funded.')
    return import_module(f'.{phase}_optimization', package=__package__)


def module_for_mode(mode):
    if mode not in ('evaluation_optimization', 'funded_optimization'):
        raise ValueError('Unknown independent phase optimization mode.')
    return module_for(mode.removesuffix('_optimization'))
