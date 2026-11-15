import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.app.core.config import settings
from backend.app.core.logging import get_logger
from backend.app.models.entities import VerificationRunEntity, VerificationStepEntity, ProjectEntity
from backend.app.models.schemas import RepairPacketModel
from backend.app.services.evidence_service import EvidenceService
from backend.app.services.git_service import GitService

logger = get_logger("repair_packet_service")

class RepairPacketService:
    """
    Builds structured, sanitized repair packets from actual Kane CLI failure evidence.
    Never fabricates failure details or touches files outside the designated target project.
    """

    def __init__(self):
        self.evidence_service = EvidenceService()

    async def build_packet(
        self,
        run_id: str,
        db: AsyncSession,
        custom_project_dir: Optional[Path] = None
    ) -> RepairPacketModel:
        # 1. Fetch run entity with steps
        res = await db.execute(
            select(VerificationRunEntity)
            .where(VerificationRunEntity.id == run_id)
            .options(
                selectinload(VerificationRunEntity.steps),
                selectinload(VerificationRunEntity.project)
            )
        )
        run = res.scalar_one_or_none()
        if not run:
            raise ValueError(f"Run {run_id} not found")

        # 2. Determine target project directory
        project_dir: Path
        if custom_project_dir:
            project_dir = custom_project_dir.resolve()
        elif run.project and run.project.repo_path:
            project_dir = Path(run.project.repo_path).resolve()
        else:
            # Default to workspace root
            project_dir = settings.WORKSPACE_DIR.resolve()

        # 3. Identify failed step
        failed_step_num = None
        failed_remark = run.failure_reason
        for s in run.steps:
            if s.status == "failed":
                failed_step_num = s.step_index
                failed_remark = s.remark or s.error_message or failed_remark
                break

        # 4. Ingest evidence if extracted
        ev_dir = settings.EVIDENCE_DIR / run_id
        failure_yaml = None
        screenshot_paths = []
        console_errors = []
        network_errors = []

        if ev_dir.exists() and ev_dir.is_dir():
            manifest = self.evidence_service.parse_extracted_evidence(ev_dir, run_id)
            failure_yaml = manifest.get("failure_details")
            console_errors = manifest.get("console_errors", [])
            network_errors = manifest.get("network_failures", [])
            for art in manifest.get("artifacts", []):
                rel = art.get("relative_path")
                if rel:
                    screenshot_paths.append(rel)

        # 5. Git status & commit before repair
        git_sha = GitService.get_current_sha(settings.WORKSPACE_DIR)

        # 6. Safely locate candidate source files within project_dir (only within project boundary)
        relevant_files = []
        if project_dir.exists():
            for p in project_dir.glob("**/*"):
                if p.is_file() and p.suffix in (".py", ".tsx", ".ts", ".jsx", ".js", ".html", ".css", ".json"):
                    # Exclude node_modules, .venv, .git, .next
                    parts = p.parts
                    if any(ignored in parts for ignored in ("node_modules", ".venv", ".git", ".next", "__pycache__")):
                        continue
                    try:
                        rel = str(p.relative_to(project_dir))
                        relevant_files.append(rel)
                    except ValueError:
                        pass

        packet = RepairPacketModel(
            run_id=run.id,
            kane_session_id=run.kane_session_id,
            target_url=run.target_url,
            objective=run.objective,
            failed_step=failed_step_num,
            failure_message=failed_remark,
            failure_yaml=failure_yaml,
            screenshot_paths=screenshot_paths,
            console_errors=console_errors,
            network_errors=network_errors,
            project_dir=str(project_dir),
            relevant_files=relevant_files[:30],  # Bound to top 30 relevant files
            git_commit_before=git_sha,
            created_at=datetime.now(timezone.utc).isoformat()
        )

        return packet

    @staticmethod
    def format_repair_prompt(packet: RepairPacketModel) -> str:
        """
        Formats a comprehensive markdown prompt instructing the Antigravity Agent
        how to diagnose and repair the verified defect.
        """
        lines = [
            "# ShipProof Autonomous Repair Request",
            "",
            "## 1. Test Verification Context",
            f"- **Run ID:** `{packet.run_id}`",
            f"- **Target URL:** `{packet.target_url}`",
            f"- **Natural-Language Objective:** {packet.objective}",
            f"- **Failed Step Index:** `{packet.failed_step or 'Unknown'}`",
            f"- **Actual Failure Message:** {packet.failure_message or 'Assertion failed'}",
            "",
            "## 2. Kane CLI Ground-Truth Evidence",
        ]

        if packet.kane_session_id:
            lines.append(f"- **Kane Session Directory:** `{packet.kane_session_id}`")

        if packet.failure_yaml:
            lines.extend([
                "### Failure Triage (from `failure.yaml`):",
                "```yaml",
                json.dumps(packet.failure_yaml, indent=2),
                "```"
            ])

        if packet.console_errors:
            lines.extend([
                "### Browser Console Errors:",
                "```json",
                json.dumps(packet.console_errors[:5], indent=2),
                "```"
            ])

        if packet.network_errors:
            lines.extend([
                "### Network Failures (4xx / 5xx):",
                "```json",
                json.dumps(packet.network_errors[:5], indent=2),
                "```"
            ])

        lines.extend([
            "",
            "## 3. Target Codebase",
            f"- **Project Directory:** `{packet.project_dir}`",
            "- **Candidate Source Files:**",
        ])
        for f in packet.relevant_files[:15]:
            lines.append(f"  - `{f}`")

        lines.extend([
            "",
            "## 4. Instructions for Antigravity Agent",
            "1. Inspect the relevant source files above.",
            "2. Identify the root cause preventing the browser from fulfilling the objective.",
            "3. Formulate a minimal, surgical fix.",
            "4. Apply the edit to the target application source code.",
            "5. Do NOT modify unrelated files or change test objectives.",
            "6. Prepare for Kane re-verification."
        ])

        return "\n".join(lines)
