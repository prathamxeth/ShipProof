from typing import List
from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from backend.app.core.database import get_db
from backend.app.core.errors import ResourceNotFoundException, ShipProofException
from backend.app.models.entities import ProjectEntity
from backend.app.models.schemas import ProjectCreate, ProjectResponse
from backend.app.core.logging import get_logger
from backend.app.core.url_validator import validate_target_url
from backend.app.core.auth import verify_auth, verify_protected_action
from backend.app.core.sanitizer import sanitize_filesystem_path

router = APIRouter(prefix="/projects", tags=["Projects"])
logger = get_logger("api.projects")

def to_project_response(p: ProjectEntity) -> ProjectResponse:
    return ProjectResponse(
        id=p.id,
        name=p.name,
        target_url=p.target_url,
        repo_path=sanitize_filesystem_path(p.repo_path),
        framework=p.framework,
        description=p.description,
        created_at=p.created_at,
        updated_at=p.updated_at
    )

@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED, summary="Create a new target project", dependencies=[Depends(verify_protected_action)])
async def create_project(payload: ProjectCreate, db: AsyncSession = Depends(get_db)):
    validated_url = validate_target_url(payload.target_url)
    clean_name = payload.name.strip()

    # Prevent duplicate projects with the same name and target_url
    existing_q = await db.execute(
        select(ProjectEntity).where(
            func.lower(ProjectEntity.name) == clean_name.lower(),
            ProjectEntity.target_url == validated_url
        )
    )
    if existing_q.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A project named '{clean_name}' targeting '{validated_url}' already exists."
        )

    project = ProjectEntity(
        name=clean_name,
        target_url=validated_url,
        repo_path=payload.repo_path.strip() if payload.repo_path else None,
        framework=payload.framework or "Next.js",
        description=payload.description
    )
    db.add(project)
    await db.flush()
    await db.refresh(project)
    logger.info(f"Created project '{project.name}' (ID: {project.id})")
    return to_project_response(project)

@router.get("", response_model=List[ProjectResponse], summary="List all projects", dependencies=[Depends(verify_auth)])
async def list_projects(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ProjectEntity).order_by(ProjectEntity.created_at.desc()))
    return [to_project_response(p) for p in result.scalars().all()]

@router.get("/{project_id}", response_model=ProjectResponse, summary="Get project by ID", dependencies=[Depends(verify_auth)])
async def get_project(project_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ProjectEntity).where(ProjectEntity.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise ResourceNotFoundException("Project", project_id)
    return to_project_response(project)
