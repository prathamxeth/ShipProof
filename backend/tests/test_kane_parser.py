import pytest
from backend.app.services.kane_parser import KaneParser, NormalizedEvent

def test_parse_stream_start():
    line = '{"type":"stream_start","cli_version":"0.10.4","surface":"run","pid":12345,"v":1,"ts":"2026-11-16T01:00:00Z","session_dir":"/path/to/session"}'
    event = KaneParser.parse_line(line)
    assert event is not None
    assert event.event_type == "stream_start"
    assert event.session_id == "/path/to/session"
    assert "0.10.4" in event.description
    assert event.raw_event["pid"] == 12345

def test_parse_typeless_step_events():
    # Step running
    line1 = '{"step": 1, "status": "running", "remark": "Navigate to https://example.com", "ts": "2026-11-16T01:00:01Z"}'
    ev1 = KaneParser.parse_line(line1)
    assert ev1 is not None
    assert ev1.event_type == "step"
    assert ev1.step_number == 1
    assert ev1.status == "running"
    assert ev1.description == "Navigate to https://example.com"

    # Step done
    line2 = '{"step": 1, "status": "done", "remark": "Navigated to https://example.com"}'
    ev2 = KaneParser.parse_line(line2)
    assert ev2 is not None
    assert ev2.event_type == "step"
    assert ev2.step_number == 1
    assert ev2.status == "done"

    # Step failed
    line3 = '{"step": 2, "status": "failed", "remark": "Button with text Login not found"}'
    ev3 = KaneParser.parse_line(line3)
    assert ev3 is not None
    assert ev3.event_type == "step"
    assert ev3.step_number == 2
    assert ev3.status == "failed"
    assert "Button with text Login" in ev3.description

def test_parse_terminal_passed_event():
    line = '{"type":"run_end","status":"passed","summary":"Successfully verified page","one_liner":"Verified example.com","duration":12.4,"session_dir":"/sessions/abc-123"}'
    ev = KaneParser.parse_line(line)
    assert ev is not None
    assert ev.event_type == "run_end"
    assert ev.status == "passed"
    assert ev.session_id == "/sessions/abc-123"
    assert KaneParser.is_terminal_event(ev) is True
    assert KaneParser.is_terminal_success(ev) is True

def test_parse_terminal_failed_event():
    line = '{"type":"run_end","status":"failed","summary":"Assertion failed at step 3","reason":"Element not visible","session_dir":"/sessions/abc-123"}'
    ev = KaneParser.parse_line(line)
    assert ev is not None
    assert ev.event_type == "run_end"
    assert ev.status == "failed"
    assert KaneParser.is_terminal_event(ev) is True
    assert KaneParser.is_terminal_success(ev) is False

def test_missing_terminal_event_not_passed():
    # If run_end is missing, is_terminal_success must be False
    assert KaneParser.is_terminal_success(None) is False
    step_ev = KaneParser.parse_line('{"step": 1, "status": "done", "remark": "All done"}')
    assert KaneParser.is_terminal_success(step_ev) is False

def test_unknown_event_handling():
    line = '{"some_unseen_type":"custom_flow","random_key":42,"message":"Custom agent telemetry"}'
    ev = KaneParser.parse_line(line)
    assert ev is not None
    assert ev.event_type == "unknown"
    assert ev.raw_event["random_key"] == 42
    assert ev.raw_event["some_unseen_type"] == "custom_flow"

def test_malformed_json_handling():
    line = '{"type": "step", "unclosed_string: 123'
    ev = KaneParser.parse_line(line)
    assert ev is not None
    assert ev.event_type == "malformed"
    assert "raw_text" in ev.raw_event
    assert "parse_error" in ev.raw_event

def test_empty_line_handling():
    assert KaneParser.parse_line("") is None
    assert KaneParser.parse_line("   \n") is None
