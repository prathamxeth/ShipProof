import pytest
import io
import zipfile
import json
from pathlib import Path
from backend.app.services.evidence_service import (
    EvidenceService,
    PathTraversalError,
    ArchiveSizeLimitExceededError
)

def create_mock_zip(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname, content in files.items():
            if isinstance(content, str):
                zf.writestr(fname, content.encode("utf-8"))
            else:
                zf.writestr(fname, content)
    return buf.getvalue()

def test_safe_extract_evidence_pack(tmp_path: Path):
    service = EvidenceService(base_evidence_dir=tmp_path / "evidence")
    
    # Valid zip contents simulating Kane CLI layout
    mock_files = {
        "run.yaml": "title: Test Run\nstatus: passed\n",
        "tests/test-1/result.yaml": "verdict: passed\nsteps: []\n",
        "tests/test-1/steps/1-step-nav/screenshot.png": b"\x89PNG\r\n\x1a\nfakeimage",
        "tests/test-1/steps/1-step-nav/annotated.png": b"\x89PNG\r\n\x1a\nfakeannotated",
        "tests/test-1/steps/2-step-fail/failure.yaml": "error: Element not clickable\ntriage:\n  rca:\n    root_cause: Button disabled\n",
        "tests/test-1/logs/0-console.ndjson": '{"level":"error","text":"ReferenceError: foo is not defined"}\n{"level":"info","text":"Loaded"}\n',
        "tests/test-1/logs/0-network.har": json.dumps({
            "log": {
                "entries": [
                    {
                        "request": {
                            "url": "https://api.example.com/checkout",
                            "method": "POST",
                            "headers": [
                                {"name": "Authorization", "value": "Bearer secret-token-123"},
                                {"name": "Content-Type", "value": "application/json"}
                            ]
                        },
                        "response": {
                            "status": 500,
                            "statusText": "Internal Server Error",
                            "headers": [
                                {"name": "Set-Cookie", "value": "session=secret-session-cookie"}
                            ]
                        }
                    }
                ]
            }
        })
    }

    pack_bytes = create_mock_zip(mock_files)
    pack_file = tmp_path / "sample.evidence"
    pack_file.write_bytes(pack_bytes)

    extracted_dir = service.safe_extract_evidence_pack(pack_file, "run-101")
    assert extracted_dir.exists()

    # Parse extracted evidence
    manifest = service.parse_extracted_evidence(extracted_dir, "run-101")
    assert manifest["has_evidence"] is True
    assert manifest["has_failure_yaml"] is True
    assert "Button disabled" in str(manifest["failure_details"])
    
    # Verify screenshot discovery
    artifacts = manifest["artifacts"]
    assert len(artifacts) == 2
    types = {a["artifact_type"] for a in artifacts}
    assert "screenshot" in types
    assert "annotated_screenshot" in types

    # Verify console errors
    assert manifest["console_errors_count"] == 1
    assert "ReferenceError" in manifest["console_errors"][0]["text"]

    # Verify network HAR and secret redaction
    assert manifest["network_failures_count"] == 1
    assert manifest["network_failures"][0]["status"] == 500
    
    # Check that secrets were redacted on disk
    har_path = extracted_dir / "tests/test-1/logs/0-network.har"
    har_content = har_path.read_text()
    assert "Bearer secret-token-123" not in har_content
    assert "[REDACTED]" in har_content
    assert "secret-session-cookie" not in har_content

def test_zip_path_traversal_prevention(tmp_path: Path):
    service = EvidenceService(base_evidence_dir=tmp_path / "evidence")

    # Malicious zip with path traversal
    malicious_files = {
        "../../evil.txt": "evil payload",
        "legit.txt": "normal"
    }
    pack_bytes = create_mock_zip(malicious_files)
    pack_file = tmp_path / "malicious.evidence"
    pack_file.write_bytes(pack_bytes)

    with pytest.raises(PathTraversalError):
        service.safe_extract_evidence_pack(pack_file, "run-bad-1")

def test_archive_size_limit_enforcement(tmp_path: Path):
    # Enforce a strict small single file limit of 50 bytes for testing
    service = EvidenceService(
        base_evidence_dir=tmp_path / "evidence",
        max_single_file_bytes=50
    )

    pack_bytes = create_mock_zip({"large.txt": "A" * 200})
    pack_file = tmp_path / "huge.evidence"
    pack_file.write_bytes(pack_bytes)

    with pytest.raises(ArchiveSizeLimitExceededError):
        service.safe_extract_evidence_pack(pack_file, "run-huge")

def test_locate_evidence_pack_from_hint(tmp_path: Path):
    service = EvidenceService(base_evidence_dir=tmp_path / "evidence")
    
    # Create fake evidence file
    evidence_dir = tmp_path / "sessions" / "abc" / "evidence"
    evidence_dir.mkdir(parents=True)
    ev_file = evidence_dir / "exec-123.evidence"
    ev_file.write_bytes(b"PK0304")

    hint = f"evidence: view locally with `kane-cli evidence serve {ev_file}`"
    found = service.locate_evidence_pack("run-1", stderr_hint=hint)
    assert found is not None
    assert found.resolve() == ev_file.resolve()
