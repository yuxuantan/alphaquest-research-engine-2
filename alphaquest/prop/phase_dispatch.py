"""Phase-only dispatch shared by HTTP, campaigns and AnalysisStore.

Simulation, selection, numerical identity and artifact schemas remain owned by
the selected optimizer. Resolve lazily so dispatch never needs the other phase.
"""
from importlib import import_module


def implementations_compatible(saved, current):
    """Exact identity, or the reviewed OOS source admission-only correction.

    Keep actual source hashes in reports. This directed compatibility bridge
    accepts one exact old/new phase_search revision pair, with every other
    source, kernel and environment field identical. No calculation is excluded.
    """
    if saved == current:
        return True
    before = '5fae2e873d053ed8315225cc8f72a2ca2926a73974e784941f4637dc1ba76e0a'
    after = 'a078590de6c3f748e92b54775d900f8b7b9c5ec2ed4ab14b0e65ac94cfc3a051'
    if (saved.get('files', {}).get('phase_search.py') != before
            or current.get('files', {}).get('phase_search.py') != after):
        return False
    return dict(saved, files=dict(saved['files'], **{'phase_search.py': after})) == current


def module_for(phase):
    if phase not in ('evaluation', 'funded'):
        raise ValueError('Unknown independent phase; use evaluation or funded.')
    return import_module(f'.{phase}_optimization', package=__package__)


def module_for_mode(mode):
    if mode not in ('evaluation_optimization', 'funded_optimization'):
        raise ValueError('Unknown independent phase optimization mode.')
    return module_for(mode.removesuffix('_optimization'))
