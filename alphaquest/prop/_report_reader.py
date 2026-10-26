"""Bounded JSON reader for the repository's report object and two large arrays."""

import json


class InputError(ValueError):
    """A source cannot provide a complete, reconciled prop input."""


def require(condition, message):
    if not condition:
        raise InputError(message)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"Duplicate JSON key: {key}.")
        result[key] = value
    return result


def invalid_number(token):
    raise InputError(f"Invalid JSON number: {token}.")


class ReportReader:
    """At most one 1-M-character record plus a 64-K-character read buffer.

    The saved format writes metadata first, trades second, and equity last.
    Restrict this reader to that format instead of implementing a JSON DOM.
    """

    def __init__(self, stream, *, chunk_size=65536, record_limit=1048576):
        self.stream, self.chunk_size, self.limit = stream, chunk_size, record_limit
        self.buffer = ""
        self.eof = False
        self.decoder = json.JSONDecoder(object_pairs_hook=unique_object, parse_constant=invalid_number)

    def more(self):
        text = self.stream.read(self.chunk_size)
        self.eof = not text
        self.buffer += text

    def whitespace(self):
        self.buffer = self.buffer.lstrip(" \t\r\n")
        while not self.buffer and not self.eof:
            self.more()
            self.buffer = self.buffer.lstrip(" \t\r\n")

    def take(self, char):
        self.whitespace()
        require(self.buffer.startswith(char), f"Malformed report; expected {char!r}.")
        self.buffer = self.buffer[len(char):]

    def value(self):
        self.whitespace()
        while True:
            try:
                value, end = self.decoder.raw_decode(self.buffer)
                # A number at a chunk boundary might still have more digits.
                if end == len(self.buffer) and not self.eof:
                    self.more()
                    continue
                require(end <= self.limit, "Report record exceeds the supported size limit.")
                self.buffer = self.buffer[end:]
                return value
            except json.JSONDecodeError:
                require(not self.eof, "Invalid or truncated report JSON.")
                require(len(self.buffer) <= self.limit, "Report record exceeds the supported size limit.")
                self.more()

    def records(self):
        self.take("{")
        keys, arrays = set(), []
        metadata_size = 0
        first = True
        while True:
            self.whitespace()
            if self.buffer.startswith("}"):
                self.take("}")
                break
            if not first:
                self.take(",")
            first = False
            key = self.value()
            require(type(key) is str and key not in keys, "Invalid or duplicate top-level report key.")
            keys.add(key)
            self.take(":")
            if key in ("trades", "equity"):
                arrays.append(key)
                require(arrays == ["trades"] or arrays == ["trades", "equity"], "Unsupported report array order.")
                self.take("[")
                first_item = True
                while True:
                    self.whitespace()
                    if self.buffer.startswith("]"):
                        self.take("]")
                        break
                    if not first_item:
                        self.take(",")
                    first_item = False
                    item = self.value()
                    require(type(item) is dict, f"{key} must contain records.")
                    yield key, item
            else:
                require(not arrays, "Metadata must precede the report arrays.")
                item = self.value()
                metadata_size += len(json.dumps(item)) + len(key)
                require(metadata_size <= self.limit, "Report metadata exceeds the supported size limit.")
                yield key, item
        require(arrays == ["trades", "equity"], "Report needs trades and full equity arrays.")
        self.whitespace()
        require(not self.buffer, "Unexpected content after report JSON.")
