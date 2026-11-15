from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from backend.app.core.logging import get_logger

logger = get_logger("kane_parser")

@dataclass
class NormalizedEvent:
    event_type: str
    session_id: Optional[str] = None
    timestamp: Optional[str] = None
    step_number: Optional[int] = None
    status: Optional[str] = None
    description: Optional[str] = None
    raw_event: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "step_number": self.step_number,
            "status": self.status,
            "description": self.description,
            "raw_event": self.raw_event
        }


class KaneParser:
    """
    Parser for Kane CLI NDJSON stream events.
    Follows the documented Kane CLI stream contract:
    - stdout emits NDJSON line-by-line
    - stream_start is the initial envelope
    - step lines are typeless: {"step": N, "status": "running"|"done"|"failed", "remark": "..."}
    - terminal event for 'run' is 'run_end' with status: "passed"|"failed"
    - unknown event types are preserved safely without throwing
    - malformed JSON lines are captured as malformed events
    """

    @staticmethod
    def parse_line(line: str) -> Optional[NormalizedEvent]:
        cleaned = line.strip()
        if not cleaned:
            return None

        # Parse JSON safely
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to decode NDJSON line: {cleaned[:100]}... Error: {e}")
            return NormalizedEvent(
                event_type="malformed",
                description=f"Malformed NDJSON line: {cleaned[:200]}",
                timestamp=datetime.now(timezone.utc).isoformat(),
                raw_event={"raw_text": cleaned, "parse_error": str(e)}
            )

        if not isinstance(data, dict):
            return NormalizedEvent(
                event_type="non_object",
                description="Line parsed into non-dict JSON",
                raw_event={"raw_json": data}
            )

        ts = data.get("ts") or datetime.now(timezone.utc).isoformat()
        
        # 1. Check for stream_start
        if data.get("type") == "stream_start":
            session_id = data.get("session_dir") or data.get("session_id")
            cli_version = data.get("cli_version", "unknown")
            surface = data.get("surface", "run")
            pid = data.get("pid")
            return NormalizedEvent(
                event_type="stream_start",
                session_id=session_id,
                timestamp=ts,
                description=f"Kane CLI v{cli_version} started ({surface}, pid={pid})",
                raw_event=data
            )

        # 2. Check for run_end (terminal event for 'run')
        if data.get("type") == "run_end":
            status = data.get("status")  # "passed" or "failed"
            summary = data.get("summary") or data.get("one_liner") or data.get("reason")
            session_id = data.get("session_dir")
            return NormalizedEvent(
                event_type="run_end",
                session_id=session_id,
                timestamp=ts,
                status=status,
                description=summary,
                raw_event=data
            )

        # 3. Check for test_md_done or testrun_done (terminal events for testmd/testrun)
        if data.get("type") in ("test_md_done", "testrun_done"):
            status = data.get("overall_status") or data.get("status")
            return NormalizedEvent(
                event_type=data.get("type"),
                session_id=data.get("session_id") or data.get("session_dir"),
                timestamp=ts,
                status=status,
                description=data.get("summary") or f"{data.get('type')} completed",
                raw_event=data
            )

        # 4. Check for typeless progress step events (have "step" field and no "type")
        if "step" in data and "type" not in data:
            step_num = data.get("step")
            status = data.get("status")  # "running", "done", "failed"
            remark = data.get("remark")
            return NormalizedEvent(
                event_type="step",
                timestamp=ts,
                step_number=step_num,
                status=status,
                description=remark,
                raw_event=data
            )

        # 5. Check for explicit error event
        if data.get("type") == "error":
            message = data.get("message") or data.get("reason") or "Unknown Kane CLI error"
            return NormalizedEvent(
                event_type="error",
                timestamp=ts,
                status="failed",
                description=message,
                raw_event=data
            )

        # 6. Check for warning event
        if data.get("type") == "warning":
            message = data.get("message") or "Warning reported by Kane CLI"
            return NormalizedEvent(
                event_type="warning",
                timestamp=ts,
                description=message,
                raw_event=data
            )

        # 7. Check for bifurcation event (flow split)
        if data.get("type") == "bifurcation":
            count = data.get("count", len(data.get("flows", [])))
            return NormalizedEvent(
                event_type="bifurcation",
                timestamp=ts,
                description=f"Objective split into {count} sub-flows",
                raw_event=data
            )

        # 8. Check for coverage event
        if data.get("type") == "coverage":
            cov_status = data.get("status")
            pct = data.get("pct")
            desc = f"Coverage: {pct}%" if pct is not None else f"Coverage status: {cov_status}"
            return NormalizedEvent(
                event_type="coverage",
                timestamp=ts,
                status=cov_status,
                description=desc,
                raw_event=data
            )

        # 9. Other typed event
        if "type" in data:
            event_type = str(data.get("type"))
            return NormalizedEvent(
                event_type=event_type,
                timestamp=ts,
                status=data.get("status"),
                description=data.get("message") or data.get("summary") or event_type,
                raw_event=data
            )

        # 10. Fallback: unknown event shape (preserved!)
        return NormalizedEvent(
            event_type="unknown",
            timestamp=ts,
            description="Unknown event structure",
            raw_event=data
        )

    @staticmethod
    def is_terminal_event(event: Optional[NormalizedEvent]) -> bool:
        if not event:
            return False
        return event.event_type in ("run_end", "test_md_done", "testrun_done")

    @staticmethod
    def is_terminal_success(event: Optional[NormalizedEvent]) -> bool:
        """
        A run can only become PASSED if a genuine terminal success event
        has been received and its status is confirmed against the actual Kane schema.
        Never marks a build verified without an actual successful Kane execution.
        """
        if not event:
            return False
        
        if event.event_type == "run_end":
            raw_status = event.raw_event.get("status")
            return raw_status == "passed"
        
        if event.event_type in ("test_md_done", "testrun_done"):
            raw_status = event.raw_event.get("overall_status") or event.raw_event.get("status")
            return raw_status == "passed"
        
        return False
