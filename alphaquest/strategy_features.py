"""Optional, code-owned pure feature streams shared by optimization trials.

A feature must depend only on selected bars and its declared parameter names.
Never cache positions, orders, fills, account values, or mutable strategy state.
Factories receive fresh readers for each trial; no state crosses trial boundaries.
"""

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
from contextlib import ExitStack, contextmanager
from types import SimpleNamespace
from itertools import islice, tee
import pickle

from .prepared_data import CHUNK_SIZE, read_stream


@dataclass(frozen=True)
class Feature:
    name: str
    version: str
    dependencies: tuple[str, ...]
    build: object  # (bars, declared_parameters_only) -> one value per bar

    def key(self, parameters):
        values = {name: getattr(parameters, name) for name in self.dependencies}
        return hashlib.sha256(json.dumps([self.name, self.version, values], sort_keys=True, default=str).encode()).hexdigest()


class FeatureReader:
    def __init__(self, path):
        self.values = read_stream(path)
        self.index = 0
        self.value = None

    def at(self, index):
        if index < self.index:
            raise ValueError("Feature readers must advance in bar order.")
        while self.index < index:
            self.value = next(self.values)
            self.index += 1
        return self.value

    def close(self):
        self.values.close()


def prepare_features(definition, prepared, values, root, progress=lambda *args: None, *, workers=1):
    """Precompute repeated dependency sets only; cap speculative temporary storage.

    Four series and 512 MiB at most (plus one chunk per active feature).
    Undeclared, unique or over-budget features use the ordinary strategy path.
    """
    if not definition.acceleration:
        return {}
    parameters = [definition.parameters(value) for value in values]
    paths = {}
    planned = []
    for feature in definition.acceleration.features:
        keys = Counter(feature.key(p) for p in parameters)
        for parameter in parameters:
            key = feature.key(parameter)
            if keys[key] <= workers or key in paths or len(paths) >= 4:
                continue
            path = root / f"feature-{key}.bin"
            paths[key] = path
            planned.append((feature, parameter, path))
    if not planned:
        return paths
    # Lockstep chunks keep tee's buffering bounded and decode input only once.
    with prepared.selected() as selected, ExitStack() as stack:
        sources = tee(selected.bars, len(planned))
        streams, generators = [], []
        for source, (feature, parameter, path) in zip(sources, planned, strict=True):
            declared = SimpleNamespace(**{name: getattr(parameter, name) for name in feature.dependencies})
            generator = iter(feature.build(source, declared))
            stack.callback(getattr(generator, "close", lambda: None))
            generators.append(generator)
            streams.append(stack.enter_context(path.open("xb")))
        count = 0
        progress("preparing_features", count, prepared.metadata["row_count"])
        while True:
            chunks = [tuple(islice(generator, CHUNK_SIZE)) for generator in generators]
            lengths = [len(chunk) for chunk in chunks]
            if not any(lengths):
                break
            if len(set(lengths)) != 1:
                raise ValueError("Every feature must produce one value per bar.")
            count += lengths[0]
            for stream, chunk in zip(streams, chunks, strict=True):
                pickle.dump(chunk, stream, protocol=5)
            progress("preparing_features", count, prepared.metadata["row_count"])
            if sum(stream.tell() for stream in streams) > 512 * 1024**2:
                # Abort every tee consumer together; never leave a lagging
                # consumer buffering the rest of the dataset in RAM.
                stack.close()
                for path in paths.values():
                    path.unlink()
                return {}
        if count != prepared.metadata["row_count"]:
            raise ValueError("Every feature must produce one value per bar.")
    return paths


@contextmanager
def create_strategy(definition, parameters, config, paths):
    strategy = definition.create(parameters, config)
    with ExitStack() as stack:
        readers = {}
        if definition.acceleration:
            for feature in definition.acceleration.features:
                if path := paths.get(feature.key(parameters)):
                    reader = FeatureReader(path)
                    stack.callback(reader.close)
                    readers[feature.name] = reader
            if readers:
                definition.acceleration.bind(strategy, readers)
        yield strategy
