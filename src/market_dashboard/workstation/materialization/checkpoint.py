"""Durable current-state replay shards, independent of downstream evaluation clocks.

No pickle or dynamic imports. An immutable shard binds complete history, source,
calendar, corporate actions, engine versions and implementation bytes. A progress
message is never considered a checkpoint. Partial writes cannot be admitted.
"""

import hashlib
import json
from pathlib import Path

from market_dashboard.aperture.leadership import fingerprint
from market_dashboard.workstation.evidence_graph import CANONICAL

from .io import atomic_write


def engine_code_files():
    root = Path(__file__).resolve().parents[2]
    files = sorted(
        [*(root / "aperture").glob("*.py"), *(root / "features").glob("*.py")]
    )
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in files
    }


def engine_code_digest():
    return fingerprint(engine_code_files())


def compatible_code_digests(root):
    """Admit only hash-proven changes outside Structure/Setup replay dependencies.

    Old shards bound an intentionally broad aperture/features source digest.
    These two downstream decision modules cannot affect saved price-engine
    outputs. Every other source byte and the complete input identity must match.
    """
    current = engine_code_files()
    result = []
    for path in sorted((Path(root) / "compatibility").glob("*.json")):
        receipt = json.loads(path.read_bytes())
        if receipt.get("to") != fingerprint(current):
            continue
        before = receipt.get("from_files", {})
        if (
            receipt.get("schema_version") != "replay-code-compatibility-v1"
            or fingerprint(before) != receipt.get("from")
            or set(before) != set(current)
            or not {name for name in current if current[name] != before[name]}
            <= {"aperture/decision_adapters.py", "aperture/decision_risk.py"}
        ):
            raise ValueError("REPLAY_COMPATIBILITY_PROOF_INVALID")
        result.append(receipt["from"])
    return tuple(result)


class ReplayCheckpoint:
    def __init__(self, root, *, versions, source, calendar, as_of, corporate_actions):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.basis = {
            "schema": "current-engine-replay-checkpoint-v1",
            "versions": versions.model_dump(mode="json"),
            "source": source.model_dump(mode="json"),
            "calendar": [str(d) for d in calendar],
            "as_of": str(as_of),
            "code_sha256": engine_code_digest(),
            "corporate_actions": sorted(
                [str(k), str(v)] for k, v in corporate_actions.items()
            ),
        }
        self.reused = 0
        self.saved = 0
        self.compatible_codes = compatible_code_digests(self.root)
        self.aliases = {}

    def identity(self, symbol, history):
        import pyarrow as pa

        table = pa.Table.from_pandas(history, preserve_index=False)
        sink = pa.BufferOutputStream()
        with pa.ipc.new_stream(sink, table.schema) as writer:
            writer.write_table(table)
        digest = hashlib.sha256(sink.getvalue()).hexdigest()
        identity = {
            **self.basis,
            "symbol": symbol,
            "history_sha256": digest,
            "columns": list(history.columns),
            "dtypes": [str(d) for d in history.dtypes],
        }
        key = fingerprint(identity)
        self.aliases[key] = tuple(
            (fingerprint({**identity, "code_sha256": code}), code)
            for code in self.compatible_codes
        )
        return key

    def load(self, key):
        path = self.root / (key + ".json")
        basis = self.basis
        if not path.exists():
            for old_key, code in self.aliases.get(key, ()):
                candidate = self.root / (old_key + ".json")
                if candidate.exists():
                    path = candidate
                    basis = {**self.basis, "code_sha256": code}
                    break
            else:
                return None
        receipt = json.loads(path.read_bytes())
        payload = receipt["payload"]
        if (
            receipt.get("key") != path.stem
            or receipt.get("basis") != basis
            or fingerprint(payload) != receipt.get("payload_sha256")
        ):
            raise ValueError("REPLAY_CHECKPOINT_HASH_MISMATCH")
        outputs = []
        expected = (
            ("StructureEvidenceV2", "SetupOutputV2")
            if self.basis["versions"]["structure"] == "structure-engine-v2"
            else ("StructureEvidenceV1", "SetupOutputV1")
        )
        for item, name in zip(payload, expected, strict=True):
            if item["type"] != name:
                raise ValueError("REPLAY_CHECKPOINT_ENGINE_MISMATCH")
            outputs.append(CANONICAL[name].model_validate(item["value"]))
        self.reused += 1
        return tuple(outputs)

    def save(self, key, structure, setup):
        payload = [
            {"type": type(x).__name__, "value": x.model_dump(mode="json")}
            for x in (structure, setup)
        ]
        receipt = {
            "key": key,
            "basis": self.basis,
            "payload": payload,
            "payload_sha256": fingerprint(payload),
        }
        atomic_write(
            self.root / (key + ".json"),
            json.dumps(
                receipt, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode(),
        )
        self.saved += 1
