"""Bounded JSON traversal preserving the existing canonical fingerprint bytes."""

import hashlib
import json


def snapshot_chunks(snapshot, *, exclude=()):
    # Dump one evidence/index row at a time, never the entire model dictionary.
    fields = type(snapshot).model_fields
    for_open = True
    yield b"{"
    for name in sorted(fields):
        value = getattr(snapshot, name)
        field = fields[name]
        if name in exclude or (field.exclude_if and field.exclude_if(value)):
            continue
        if not for_open:
            yield b","
        for_open = False
        yield json.dumps(name).encode() + b":"
        if name in ("evidence", "record_index"):
            yield b"["
            for index, row in enumerate(value):
                if index:
                    yield b","
                yield json.dumps(
                    row.model_dump(mode="json"),
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode()
            yield b"]"
        else:
            item = snapshot.model_dump(mode="json", include={name})[name]
            yield json.dumps(
                item, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
    yield b"}"


def snapshot_digest(snapshot):
    digest = hashlib.sha256()
    for chunk in snapshot_chunks(
        snapshot, exclude={"generated_at", "logical_fingerprint"}
    ):
        digest.update(chunk)
    return digest.hexdigest()


def snapshot_sizes(snapshot):
    sizes = {}
    for name in type(snapshot).model_fields:
        value = getattr(snapshot, name)
        field = type(snapshot).model_fields[name]
        if field.exclude_if and field.exclude_if(value):
            continue
        if name in ("evidence", "record_index"):
            sizes[name] = (
                2
                + max(0, len(value) - 1)
                + sum(
                    len(
                        json.dumps(
                            row.model_dump(mode="json"),
                            sort_keys=True,
                            separators=(",", ":"),
                            allow_nan=False,
                        ).encode()
                    )
                    for row in value
                )
            )
        else:
            sizes[name] = len(
                json.dumps(
                    snapshot.model_dump(mode="json", include={name})[name],
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode()
            )
    total = (
        2
        + max(0, len(sizes) - 1)
        + sum(len(json.dumps(k).encode()) + 1 + v for k, v in sizes.items())
    )
    return total, sizes


class JSONStream:
    """Incremental strict JSON reader; only one evidence row is decoded at once."""

    def __init__(self, stream):
        self.stream, self.buffer, self.eof = stream, "", False
        self.decoder = json.JSONDecoder()

    def fill(self):
        chunk = self.stream.read(65536)
        self.eof = not chunk
        self.buffer += chunk

    def space(self):
        self.buffer = self.buffer.lstrip()
        while not self.buffer and not self.eof:
            self.fill()
            self.buffer = self.buffer.lstrip()

    def token(self, expected):
        self.space()
        if not self.buffer.startswith(expected):
            raise ValueError("SNAPSHOT_JSON_SYNTAX")
        self.buffer = self.buffer[len(expected) :]

    def value(self):
        self.space()
        while True:
            try:
                value, end = self.decoder.raw_decode(self.buffer)
                if end == len(self.buffer) and not self.eof:
                    self.fill()
                    continue
                self.buffer = self.buffer[end:]
                return value
            except json.JSONDecodeError:
                if self.eof:
                    raise ValueError("SNAPSHOT_JSON_TRUNCATED") from None
                self.fill()


def read_stream(stream):
    from .evidence_graph import EvidenceNodeV2
    from .snapshot_v2 import CompactRecordV2, WorkstationSnapshotV2

    reader = JSONStream(stream)
    reader.token("{")
    values = {}
    while True:
        key = reader.value()
        if not isinstance(key, str) or key in values:
            raise ValueError("SNAPSHOT_DUPLICATE_OR_INVALID_KEY")
        reader.token(":")
        if key in ("evidence", "record_index"):
            model = EvidenceNodeV2 if key == "evidence" else CompactRecordV2
            reader.token("[")
            rows = []
            reader.space()
            while not reader.buffer.startswith("]"):
                rows.append(model.model_validate(reader.value()))
                reader.space()
                if reader.buffer.startswith("]"):
                    break
                reader.token(",")
                reader.space()
                if reader.buffer.startswith("]"):
                    raise ValueError("SNAPSHOT_JSON_SYNTAX")
            reader.token("]")
            values[key] = tuple(rows)
            del rows
        else:
            values[key] = reader.value()
        reader.space()
        if reader.buffer.startswith("}"):
            break
        reader.token(",")
    reader.token("}")
    reader.space()
    if reader.buffer or not reader.eof:
        raise ValueError("SNAPSHOT_JSON_TRAILING_CONTENT")
    return WorkstationSnapshotV2.model_validate(values)
