from pathlib import Path
import json
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List

from backend.app.core.auth import verify_auth, verify_protected_action
from backend.app.services.revenue_guard_service import revenue_guard

router = APIRouter(prefix="/guard", tags=["Revenue Guard Sentinel"])

class GuardToggleRequest(BaseModel):
    enabled: bool = Field(description="Enable or pause the sentinel")

class GuardIntervalRequest(BaseModel):
    interval_seconds: int = Field(ge=30, le=600, description="Interval in seconds (60, 120, 300)")

@router.get(
    "/status",
    summary="Get Revenue Guard operational state and countdown",
    status_code=status.HTTP_200_OK
)
async def get_guard_status(user: str = Depends(verify_auth)):
    return revenue_guard.get_status()

@router.post(
    "/toggle",
    summary="Toggle Revenue Guard background sentinel",
    status_code=status.HTTP_200_OK
)
async def toggle_guard(payload: GuardToggleRequest, user: str = Depends(verify_protected_action)):
    if payload.enabled:
        revenue_guard.start()
    else:
        revenue_guard.stop()
    return revenue_guard.get_status()

@router.post(
    "/interval",
    summary="Update Revenue Guard check frequency",
    status_code=status.HTTP_200_OK
)
async def set_guard_interval(payload: GuardIntervalRequest, user: str = Depends(verify_protected_action)):
    revenue_guard.set_interval(payload.interval_seconds)
    return revenue_guard.get_status()

@router.post(
    "/probe",
    summary="Trigger an immediate Autonomous Secret Shopper audit run",
    status_code=status.HTTP_200_OK
)
async def trigger_guard_probe(user: str = Depends(verify_protected_action)):
    result = await revenue_guard.trigger_probe(initiated_by=f"operator:{user}")
    if result.get("status") == "error":
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result.get("message"))
    return result

@router.get(
    "/defect",
    summary="Get e-commerce store defect status",
    status_code=status.HTTP_200_OK
)
async def get_store_defect_status(user: str = Depends(verify_auth)):
    cfg_file = Path("demo_targets/sample_store/config.json")
    if cfg_file.exists():
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"defect_enabled": False}

@router.post(
    "/defect",
    summary="Toggle e-commerce store checkout defect for live demo verification",
    status_code=status.HTTP_200_OK
)
async def toggle_store_defect(payload: Optional[Dict[str, Any]] = None, user: str = Depends(verify_protected_action)):
    cfg_file = Path("demo_targets/sample_store/config.json")
    cfg = {
        "defect_enabled": False,
        "defect_type": "checkout_button_broken",
        "defect_description": "Checkout button has broken ID and disabled state preventing order completion"
    }
    if cfg_file.exists():
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            pass
    
    current = cfg.get("defect_enabled", False)
    if payload and "enabled" in payload and payload["enabled"] is not None:
        new_val = bool(payload["enabled"])
    else:
        new_val = not current
    
    cfg["defect_enabled"] = new_val
    with open(cfg_file, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    
    return {
        "defect_enabled": new_val,
        "message": f"Store defect is now {'ENABLED (Checkout Obstructed - $99 at risk)' if new_val else 'DISABLED (Store Healthy)'}"
    }
