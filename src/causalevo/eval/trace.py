"""Trace records and run manifests (replayable, redacted, minimal)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class TaskTrace:
    trace_id: str
    task_id: str
    split: str
    policy_id: str
    run_id: str
    states: dict[str, bool]
    judge: dict[str, Any]
    workspace_digest_before: str
    workspace_digest_after: str
    executor: str
    duration_ms: int
    created_utc: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RunManifest:
    run_id: str
    policy_id: str
    created_utc: str
    split_seed: int
    task_count: int
    executor_kind: str
    config: dict[str, Any]
    config_sha256: str
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def config_sha256(config: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(config, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]


class TraceWriter:
    """Writes traces.jsonl (redacted-by-construction: no response bodies, no
    raw tool output, only states/digests/hashes) plus manifest.json."""

    def __init__(self, out_dir: Path) -> None:
        self.out_dir = out_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        self._fh = (out_dir / "traces.jsonl").open("a", encoding="utf-8")

    def write_trace(self, trace: TaskTrace) -> None:
        self._fh.write(json.dumps(trace.as_dict(), ensure_ascii=False) + "\n")
        self._fh.flush()

    def write_manifest(self, manifest: RunManifest) -> None:
        (self.out_dir / "manifest.json").write_text(
            json.dumps(manifest.as_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    def close(self) -> None:
        self._fh.close()
