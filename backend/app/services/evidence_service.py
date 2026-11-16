from pathlib import Path
from typing import Optional, Dict, Any, List
import os
import zipfile
import re
import json
import yaml
from datetime import datetime, timezone
from backend.app.core.config import settings
from backend.app.core.logging import get_logger

logger = get_logger("evidence_service")

# Security limits for ZIP extraction
DEFAULT_MAX_TOTAL_UNCOMPRESSED_BYTES = 100 * 1024 * 1024  # 100 MB
DEFAULT_MAX_SINGLE_FILE_BYTES = 50 * 1024 * 1024          # 50 MB
DEFAULT_MAX_ENTRY_COUNT = 1000

# Redaction patterns for sensitive headers and credentials
SENSITIVE_HEADER_KEYS = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "proxy-authorization",
    "access-token",
    "token"
}

class PathTraversalError(Exception):
    pass

class ArchiveSizeLimitExceededError(ValueError):
    pass


class EvidenceService:
    """
    Handles discovery, security verification, safe extraction,
    and structured parsing of Kane CLI evidence packs (.evidence ZIP archives).
    """

    def __init__(
        self,
        base_evidence_dir: Optional[Path] = None,
        max_total_bytes: int = DEFAULT_MAX_TOTAL_UNCOMPRESSED_BYTES,
        max_single_file_bytes: int = DEFAULT_MAX_SINGLE_FILE_BYTES,
        max_entry_count: int = DEFAULT_MAX_ENTRY_COUNT
    ):
        self.base_evidence_dir = base_evidence_dir or settings.EVIDENCE_DIR
        self.base_evidence_dir.mkdir(parents=True, exist_ok=True)
        self.max_total_bytes = max_total_bytes
        self.max_single_file_bytes = max_single_file_bytes
        self.max_entry_count = max_entry_count

    def locate_evidence_pack(
        self,
        run_id: str,
        session_dir: Optional[str] = None,
        stderr_hint: Optional[str] = None
    ) -> Optional[Path]:
        """
        Locates the .evidence file produced by a Kane CLI run.
        Searches:
        1. Explicit stderr hint: 'kane-cli evidence serve <path>'
        2. {session_dir}/evidence/*.evidence
        3. ~/.testmuai/kaneai/sessions/<session_id>/evidence/*.evidence
        4. {workspace}/.testmuai/evidence/*.evidence
        """
        # 1. Parse stderr hint if available
        if stderr_hint:
            match = re.search(r"kane-cli evidence serve\s+['\"]?([^\s'\"]+\.evidence)['\"]?", stderr_hint)
            if match:
                candidate = Path(match.group(1)).expanduser().resolve()
                if candidate.exists() and candidate.is_file():
                    logger.info(f"Found evidence pack from stderr hint: {candidate}")
                    return candidate

        # 2. Check session_dir
        if session_dir:
            sess_path = Path(session_dir).expanduser().resolve()
            if sess_path.exists():
                evidence_subdir = sess_path / "evidence"
                if evidence_subdir.exists():
                    evidence_files = sorted(evidence_subdir.glob("*.evidence"), key=os.path.getmtime, reverse=True)
                    if evidence_files:
                        logger.info(f"Found evidence pack in session_dir: {evidence_files[0]}")
                        return evidence_files[0]

        # 3. Check ~/.testmuai/kaneai/sessions/*/evidence/*.evidence
        user_testmu_sessions = Path.home() / ".testmuai" / "kaneai" / "sessions"
        if user_testmu_sessions.exists():
            evidence_files = sorted(user_testmu_sessions.glob("*/evidence/*.evidence"), key=os.path.getmtime, reverse=True)
            if evidence_files:
                return evidence_files[0]

        # 4. Check workspace .testmuai/evidence/*.evidence
        workspace_evidence = settings.WORKSPACE_DIR / ".testmuai" / "evidence"
        if workspace_evidence.exists():
            evidence_files = sorted(workspace_evidence.glob("*.evidence"), key=os.path.getmtime, reverse=True)
            if evidence_files:
                return evidence_files[0]

        logger.warning(f"No evidence pack found for run {run_id}")
        return None

    def safe_extract_evidence_pack(self, pack_path: Path, run_id: str) -> Path:
        """
        Safely extracts a .evidence zip pack into a sandboxed destination directory.
        Strictly prevents zip path traversal attacks and checks archive size bounds.
        """
        if not pack_path.exists() or not pack_path.is_file():
            raise FileNotFoundError(f"Evidence pack not found: {pack_path}")

        if not run_id or not re.match(r"^[a-zA-Z0-9_\-]+$", run_id):
            raise PathTraversalError(f"Invalid run_id for evidence extraction: '{run_id}'")

        dest_dir = (self.base_evidence_dir / run_id).resolve()
        base_dir = self.base_evidence_dir.resolve()
        if base_dir not in dest_dir.parents or dest_dir == base_dir:
            raise PathTraversalError(f"Evidence destination directory escapes base directory: {dest_dir}")

        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_str = str(dest_dir)

        total_extracted_bytes = 0

        with zipfile.ZipFile(pack_path, "r") as zf:
            infolist = zf.infolist()
            if len(infolist) > self.max_entry_count:
                raise ArchiveSizeLimitExceededError(f"Evidence archive contains {len(infolist)} entries; maximum allowed is {self.max_entry_count}")

            for member in infolist:
                # 1. Path traversal check: verify member target is strictly within dest_dir
                member_path = member.filename
                if os.path.isabs(member_path) or ".." in Path(member_path).parts:
                    raise PathTraversalError(f"Malicious zip entry detected (path traversal): {member_path}")

                target_path = (dest_dir / member_path).resolve()
                if not str(target_path).startswith(dest_str):
                    raise PathTraversalError(f"Target path {target_path} escapes extract directory {dest_str}")

                # 2. File size checks
                if member.file_size > self.max_single_file_bytes:
                    raise ArchiveSizeLimitExceededError(
                        f"Zip entry {member_path} uncompressed size {member.file_size} exceeds max {self.max_single_file_bytes}"
                    )

                total_extracted_bytes += member.file_size
                if total_extracted_bytes > self.max_total_bytes:
                    raise ArchiveSizeLimitExceededError(
                        f"Total uncompressed size exceeds limit of {self.max_total_bytes} bytes"
                    )

            # Safely extract all members
            zf.extractall(dest_dir)

        logger.info(f"Safely extracted evidence pack {pack_path} to {dest_dir} ({total_extracted_bytes} bytes)")
        return dest_dir

    def parse_extracted_evidence(self, extracted_dir: Path, run_id: str) -> Dict[str, Any]:
        """
        Inspects extracted evidence files:
        - failure.yaml (triage, error, rca)
        - result.yaml
        - screenshot.png & annotated.png (mapped to steps)
        - console.ndjson (errors/warnings)
        - network.har (4xx/5xx requests with credentials sanitized and rewritten)
        """
        manifest: Dict[str, Any] = {
            "run_id": run_id,
            "extracted_dir": str(extracted_dir),
            "has_evidence": True,
            "has_failure_yaml": False,
            "failure_details": None,
            "artifacts": [],
            "console_errors_count": 0,
            "network_failures_count": 0,
            "console_errors": [],
            "network_failures": [],
        }

        # 1. Search for failure.yaml
        failure_files = list(extracted_dir.glob("**/failure.yaml"))
        if failure_files:
            manifest["has_failure_yaml"] = True
            try:
                with open(failure_files[0], "r", encoding="utf-8") as f:
                    failure_content = yaml.safe_load(f)
                    manifest["failure_details"] = failure_content
            except Exception as e:
                logger.warning(f"Failed to parse failure.yaml: {e}")
                manifest["failure_details"] = {"parse_error": str(e)}

        # 2. Discover screenshots (both .png and .jpg/.jpeg)
        for img_path in extracted_dir.glob("**/*"):
            if img_path.is_file() and img_path.suffix.lower() in (".png", ".jpg", ".jpeg"):
                fname = img_path.name
                rel_path = str(img_path.relative_to(extracted_dir))
                
                # Extract step number from path if present (e.g., steps/1-0-1/screenshot.jpg)
                step_idx = None
                step_match = re.search(r"steps/(\d+)-", rel_path)
                if step_match:
                    step_idx = int(step_match.group(1))

                artifact_type = "annotated_screenshot" if "annotated" in fname else "screenshot"
                manifest["artifacts"].append({
                    "step_index": step_idx,
                    "artifact_type": artifact_type,
                    "filename": fname,
                    "relative_path": rel_path,
                    "file_size_bytes": img_path.stat().st_size
                })

        # 3. Parse console logs (*-console.ndjson)
        console_logs = list(extracted_dir.glob("**/logs/*-console.ndjson"))
        for clog in console_logs:
            try:
                with open(clog, "r", encoding="utf-8") as f:
                    for line in f:
                        line_str = line.strip()
                        if not line_str:
                            continue
                        try:
                            entry = json.loads(line_str)
                            level = str(entry.get("level", "")).lower()
                            if level in ("error", "warning") or "error" in str(entry).lower():
                                manifest["console_errors"].append(entry)
                        except json.JSONDecodeError:
                            continue
            except Exception as e:
                logger.warning(f"Error reading console log {clog}: {e}")

        manifest["console_errors_count"] = len(manifest["console_errors"])

        # 4. Parse network HAR (*-network.har), sanitize secrets and rewrite file
        har_files = list(extracted_dir.glob("**/logs/*-network.har"))
        for hfile in har_files:
            try:
                modified = False
                with open(hfile, "r", encoding="utf-8") as f:
                    har_data = json.load(f)
                    entries = har_data.get("log", {}).get("entries", [])
                    for entry in entries:
                        response = entry.get("response", {})
                        status = response.get("status", 200)
                        
                        # Sanitize sensitive headers in request and response
                        request = entry.get("request", {})
                        if "headers" in request:
                            for h in request["headers"]:
                                if str(h.get("name", "")).lower() in SENSITIVE_HEADER_KEYS:
                                    h["value"] = "[REDACTED]"
                                    modified = True
                        if "headers" in response:
                            for h in response["headers"]:
                                if str(h.get("name", "")).lower() in SENSITIVE_HEADER_KEYS:
                                    h["value"] = "[REDACTED]"
                                    modified = True

                        # Track 4xx/5xx failures
                        if status >= 400:
                            manifest["network_failures"].append({
                                "url": request.get("url"),
                                "method": request.get("method"),
                                "status": status,
                                "statusText": response.get("statusText")
                            })

                if modified:
                    with open(hfile, "w", encoding="utf-8") as f:
                        json.dump(har_data, f, indent=2)
            except Exception as e:
                logger.warning(f"Error reading network HAR {hfile}: {e}")

        manifest["network_failures_count"] = len(manifest["network_failures"])
        return manifest
