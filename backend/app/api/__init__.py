from fastapi import APIRouter
from backend.app.api.health import router as health_router
from backend.app.api.overview import router as overview_router
from backend.app.api.projects import router as projects_router
from backend.app.api.runs import router as runs_router
from backend.app.api.repairs import router as repairs_router
from backend.app.api.system import router as system_router

api_router = APIRouter(prefix="/api")
api_router.include_router(health_router)
api_router.include_router(overview_router)
api_router.include_router(projects_router)
api_router.include_router(runs_router)
api_router.include_router(repairs_router)
api_router.include_router(system_router)
