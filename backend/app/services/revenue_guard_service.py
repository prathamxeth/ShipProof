import asyncio
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from pathlib import Path

from backend.app.core.config import settings
from backend.app.core.logging import get_logger

logger = get_logger("revenue_guard")

class RevenueGuardService:
    """
    Revenue Guard: Autonomous 24/7 Secret Shopper Sentinel powered by Kane CLI.
    Continuously validates critical e-commerce checkout pipelines to detect silent
    conversion drops and prevent customer abandonment.
    """

    def __init__(self):
        self.enabled: bool = True
        self.interval_seconds: int = 120  # Default 2 minutes (favorable balance)
        self.target_url: str = "http://127.0.0.1:3005"
        self.objective: str = (
            "Click 'Add to Cart', then in the cart click 'Proceed to Checkout', "
            "and verify that 'Secure Checkout' is displayed."
        )
        self.last_probe_time: Optional[float] = None
        self.next_probe_time: Optional[float] = None
        self.last_run_id: Optional[str] = None
        self.last_status: str = "healthy"  # "healthy", "alarm", "running", "idle"
        self.total_probes: int = 0
        self.passed_probes: int = 0
        self.failed_probes: int = 0
        self.revenue_protected: float = 0.0
        self.revenue_at_risk: float = 0.0
        self.recent_alerts: List[Dict[str, Any]] = []

        self._task: Optional[asyncio.Task] = None
        self._running_probe: bool = False

    def start(self):
        """Starts the sentinel background polling loop."""
        if self._task and not self._task.done():
            return
        self.enabled = True
        self.next_probe_time = time.time() + self.interval_seconds
        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"Revenue Guard Sentinel started (Interval: {self.interval_seconds}s)")

    def stop(self):
        """Stops the sentinel background loop."""
        self.enabled = False
        if self._task and not self._task.done():
            self._task.cancel()
            self._task = None
        logger.info("Revenue Guard Sentinel stopped.")

    def set_interval(self, seconds: int):
        """Updates the check frequency (60s, 120s, 300s)."""
        valid_intervals = [60, 120, 300]
        if seconds not in valid_intervals:
            seconds = 120
        self.interval_seconds = seconds
        self.next_probe_time = time.time() + self.interval_seconds
        logger.info(f"Revenue Guard interval set to {seconds} seconds.")

    def get_status(self) -> Dict[str, Any]:
        """Returns the real-time operational status for UI & API consumption."""
        now = time.time()
        seconds_until_next = max(0, int((self.next_probe_time or now) - now)) if self.enabled else 0

        return {
            "enabled": self.enabled,
            "interval_seconds": self.interval_seconds,
            "interval_label": f"{self.interval_seconds // 60}m" if self.interval_seconds >= 60 else f"{self.interval_seconds}s",
            "target_url": self.target_url,
            "objective": self.objective,
            "state": "running" if self._running_probe else ("alarm" if self.last_status == "alarm" else ("active" if self.enabled else "paused")),
            "last_status": self.last_status,
            "seconds_until_next": seconds_until_next,
            "last_probe_iso": datetime.fromtimestamp(self.last_probe_time, tz=timezone.utc).isoformat() if self.last_probe_time else None,
            "next_probe_iso": datetime.fromtimestamp(self.next_probe_time, tz=timezone.utc).isoformat() if self.next_probe_time and self.enabled else None,
            "last_run_id": self.last_run_id,
            "total_probes": self.total_probes,
            "passed_probes": self.passed_probes,
            "failed_probes": self.failed_probes,
            "revenue_protected": round(self.revenue_protected, 2),
            "revenue_at_risk": round(self.revenue_at_risk, 2),
            "recent_alerts": self.recent_alerts[-5:]
        }

    async def trigger_probe(self, initiated_by: str = "manual") -> Dict[str, Any]:
        """
        Executes an immediate Autonomous Secret Shopper verification run.
        """
        if self._running_probe:
            return {"status": "busy", "message": "A Revenue Guard probe is already actively executing in Chromium."}

        self._running_probe = True
        self.last_probe_time = time.time()
        self.next_probe_time = time.time() + self.interval_seconds

        try:
            from backend.app.core.database import AsyncSessionLocal
            from backend.app.models.entities import VerificationRunEntity
            from backend.app.services.runner_service import runner_service
            from sqlalchemy import select

            self.total_probes += 1
            run_title = f"[Revenue Guard #{self.total_probes}] Secret Shopper Checkout Audit"

            async with AsyncSessionLocal() as session:
                run_entity = VerificationRunEntity(
                    title=run_title,
                    objective=self.objective,
                    target_url=self.target_url,
                    mode="verify_only",
                    status="queued"
                )
                session.add(run_entity)
                await session.commit()
                await session.refresh(run_entity)
                run_id = run_entity.id
                self.last_run_id = run_id

            logger.info(f"Revenue Guard launched probe run {run_id} ({initiated_by})")

            # Execute via runner service
            asyncio.create_task(self._monitor_probe_lifecycle(run_id))

            return {
                "status": "launched",
                "run_id": run_id,
                "title": run_title,
                "initiated_by": initiated_by,
                "target_url": self.target_url,
                "message": f"Autonomous Secret Shopper dispatched via Kane CLI (Run #{run_id[:8]})."
            }
        except Exception as e:
            self._running_probe = False
            logger.error(f"Failed to launch Revenue Guard probe: {e}")
            return {"status": "error", "message": str(e)}

    async def _monitor_probe_lifecycle(self, run_id: str):
        """Asynchronously waits for run completion and computes revenue health."""
        from backend.app.services.runner_service import runner_service
        from backend.app.core.database import AsyncSessionLocal
        from backend.app.models.entities import VerificationRunEntity
        from sqlalchemy import select

        try:
            await runner_service._execute_run_lifecycle(
                run_id=run_id,
                objective=self.objective,
                target_url=self.target_url,
                headless=True,
                timeout=120
            )

            # Query finalized run state
            async with AsyncSessionLocal() as session:
                res = await session.execute(
                    select(VerificationRunEntity).where(VerificationRunEntity.id == run_id)
                )
                run = res.scalar_one_or_none()

            if run and run.status == "passed":
                self.last_status = "healthy"
                self.passed_probes += 1
                self.revenue_protected += 99.00  # High-fidelity headphones value ($99)
                self.revenue_at_risk = 0.0
                logger.info(f"Revenue Guard probe {run_id} PASSED: checkout pipeline confirmed healthy ($99 protected)")
            else:
                self.last_status = "alarm"
                self.failed_probes += 1
                self.revenue_at_risk = 99.00
                alert_entry = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "run_id": run_id,
                    "reason": (run.failure_reason if run else "Checkout button obstruction") or "Checkout flow failed",
                    "revenue_risk": 99.00
                }
                self.recent_alerts.append(alert_entry)
                logger.warning(f"Revenue Guard CRITICAL ALARM: checkout obstructed in run {run_id} ($99 at risk)")

                # Automatically trigger autonomous repair triage
                try:
                    from backend.app.services.repair_orchestrator import repair_orchestrator
                    await repair_orchestrator.create_repair_session(run_id=run_id)
                    logger.info(f"Revenue Guard auto-generated repair session for failed probe {run_id}")
                except Exception as rep_err:
                    logger.warning(f"Could not auto-generate repair session for {run_id}: {rep_err}")

        except Exception as err:
            logger.error(f"Error during Revenue Guard lifecycle for {run_id}: {err}")
            self.last_status = "alarm"
        finally:
            self._running_probe = False

    async def _run_loop(self):
        """Internal background loop running at the selected interval."""
        logger.info("Revenue Guard background loop started.")
        try:
            # Initial settling delay on startup
            await asyncio.sleep(10.0)

            while self.enabled:
                if not self._running_probe:
                    logger.info("Revenue Guard interval trigger fired; dispatching autonomous probe...")
                    await self.trigger_probe(initiated_by="scheduled_timer")

                # Sleep until next interval
                await asyncio.sleep(self.interval_seconds)
        except asyncio.CancelledError:
            logger.info("Revenue Guard background loop cancelled.")
        except Exception as e:
            logger.error(f"Revenue Guard background loop error: {e}")

revenue_guard = RevenueGuardService()
