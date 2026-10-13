"""Container entrypoint: read one task request from stdin, run one DSH task
through the real SDK/runtime inside this container, stream slim session events
as JSONL on stdout, then a final result line. The only mounted path is the
per-task workspace at /work; DSH_HOME is an in-container temp dir, so agent
file access ends at the container edge.
"""
import json
import pathlib
import sys
import tempfile


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, default=str) + "\n")
    sys.stdout.flush()


def main() -> int:
    request = json.load(sys.stdin)
    workdir = pathlib.Path("/work")
    with tempfile.TemporaryDirectory() as tmp:
        patch_path = pathlib.Path(tmp) / "patch.yml"
        patch_path.write_text(request["patch_yml"], encoding="utf-8")
        dsh_home = pathlib.Path(tmp) / "dsh_home"
        dsh_home.mkdir()

        from deepseek_harness import DeepSeekHarness, DeepSeekHarnessConfig

        cfg = DeepSeekHarnessConfig(
            provider="deepseek-official",
            model=request["model"],
            reasoning_effort=request.get("reasoning_effort"),
            max_tokens=request.get("max_tokens"),
            cwd=str(workdir),
            dsh_home=str(dsh_home),
            patches=(str(patch_path),),
            initialize_timeout_seconds=90.0,
            request_timeout_seconds=float(request.get("request_timeout_s", 300)),
            base_url=request.get("base_url"),
            api_key=request.get("api_key"),
        )

        def on_notification(notification):
            if notification.method != "session.event":
                return
            event = notification.payload.get("event")
            if isinstance(event, dict):
                _emit({"type": "event", "event": event})

        try:
            with DeepSeekHarness(cfg) as harness:
                session = harness.start_session(request["session_id"])
                result = session.run(request["prompt"], on_notification=on_notification)
        except Exception as exc:
            _emit({"type": "final", "ok": False, "error": f"{type(exc).__name__}: {exc}"})
            return 0
        _emit({
            "type": "final",
            "ok": True,
            "finish_reason": result.finish_reason,
            "final_response": result.final_response,
            "events": result.events,
        })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
