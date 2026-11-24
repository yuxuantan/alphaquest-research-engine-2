"""Phase-only dispatch shared by HTTP, campaigns and AnalysisStore.

Simulation, selection, numerical identity and artifact schemas remain owned by
the selected optimizer. Resolve lazily so dispatch never needs the other phase.
"""
from importlib import import_module


def implementations_compatible(saved, current):
    """Exact identity, or exact directed, reviewed non-numerical revisions.

    Preserve actual file hashes. Only the listed admission/progress pairs may
    differ; every calculation, kernel and environment field must match.
    """
    if saved == current:
        return True
    allowed = {
        'phase_search.py': {
            ('5fae2e873d053ed8315225cc8f72a2ca2926a73974e784941f4637dc1ba76e0a', 'a078590de6c3f748e92b54775d900f8b7b9c5ec2ed4ab14b0e65ac94cfc3a051'),
            ('5fae2e873d053ed8315225cc8f72a2ca2926a73974e784941f4637dc1ba76e0a', '14fbe7844bc44be5734212513172d1fc74782c380beb0ab8a3a82f5e2e7ec36c'),
            ('a078590de6c3f748e92b54775d900f8b7b9c5ec2ed4ab14b0e65ac94cfc3a051', '14fbe7844bc44be5734212513172d1fc74782c380beb0ab8a3a82f5e2e7ec36c'),
        },
        # One completed indexed path per task; metadata-only worker timing.
        # Serial/multicore financial and schedule parity is tested at 65 paths.
        'native_preparation.py': {('6777f00ea2a980c02175e5982196098684bd45cb1d5c6075e6714a0725d0dfee', 'cd3bf18941c351e8071862c53eb53e04c5e10b0d6834510cc99591bea79732c8')},
    }
    files = dict(saved.get('files', {}))
    for name, pairs in allowed.items():
        revision = current.get('files', {}).get(name)
        if (files.get(name), revision) in pairs:
            files[name] = revision
    return dict(saved, files=files) == current



def module_for(phase):
    if phase not in ('evaluation', 'funded'):
        raise ValueError('Unknown independent phase; use evaluation or funded.')
    return import_module(f'.{phase}_optimization', package=__package__)


def module_for_mode(mode):
    if mode not in ('evaluation_optimization', 'funded_optimization'):
        raise ValueError('Unknown independent phase optimization mode.')
    return module_for(mode.removesuffix('_optimization'))
