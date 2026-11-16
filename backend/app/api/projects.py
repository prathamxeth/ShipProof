from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.app.core.database import get_db
from backend.app.core.errors import ResourceNotFoundException, ShipProofException
from backend.app.models.entities import ProjectEntity
from backend.app.models.schemas import ProjectCreate, ProjectResponse
from backend.app.core.logging import get_logger
from backend.app.core.url_validator import validate_target_url

router = APIRouter(prefix="/projects", tags=["Projects"])
logger = get_logger("api.projects")

@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED, summary="Create a new target project")
async def create_project(payload: ProjectCreate, db: AsyncSession = Depends(get_db)):
    validated_url = validate_target_url(payload.target_url)
    project = ProjectEntity(
        name=payload.name,
        target_url=validated_url,
        repo_path=payload.repo_path,
        framework=payload.framework or "Next.js",
        description=payload.description
    )
    db.add(project)
    await db.flush()
    await db.refresh(project)
    logger.info(f"Created project '{project.name}' (ID: {project.id})")
    return project

@router.get("", response_model=List[ProjectResponse], summary="List all projects")
async def list_projects(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ProjectEntity).order_by(ProjectEntity.created_at.desc()))
    return result.scalars().all()

@router.get("/{project_id}", response_model=ProjectResponse, summary="Get project by ID")
async def get_project(project_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ProjectEntity).where(ProjectEntity.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise ResourceNotFoundException("Project", project_id)
    return project
