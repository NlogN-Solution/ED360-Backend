from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.auth import require_role
from ..api.deps import get_db_session
from ..core.storage import delete_upload, save_upload
from ..core.tenant import scoped_org_id
from ..models import User
from ..models.enums import ResourceType
from ..schemas.resource import ResourceArticleCreate, ResourceList, ResourceRead, ResourceUpdate
from ..services.resource_service import ResourceService

router = APIRouter(tags=["Resources"])

# Mirrors frontend/src/constants/permissions.ts's `resources` module exactly.
VIEW_ROLES = ("admin", "super_admin", "counsellor", "staff")
MANAGE_ROLES = ("admin", "super_admin")


async def get_resource_service(session: AsyncSession = Depends(get_db_session)) -> ResourceService:
    return ResourceService(session)


def _require_org(user: User) -> UUID:
    if user.organization_id is None:
        raise HTTPException(status_code=400, detail="No organization context")
    return user.organization_id


@router.get("/resources", response_model=ResourceList, summary="List resources")
async def list_resources(
    page: int = 1,
    limit: int = 20,
    category: str | None = None,
    type: ResourceType | None = None,
    search: str | None = None,
    service: ResourceService = Depends(get_resource_service),
    user: User = Depends(require_role(*VIEW_ROLES)),
) -> ResourceList:
    organization_id = _require_org(user)
    resources, total = await service.list_resources(organization_id, page, limit, category=category, type_=type, search=search)
    return ResourceList(items=resources, total=total, page=page, limit=limit)


@router.post("/resources/articles", response_model=ResourceRead, summary="Write a knowledge-base article")
async def create_article(
    payload: ResourceArticleCreate,
    service: ResourceService = Depends(get_resource_service),
    user: User = Depends(require_role(*MANAGE_ROLES)),
) -> ResourceRead:
    organization_id = _require_org(user)
    data = payload.model_dump()
    data["type"] = ResourceType.ARTICLE
    return await service.create_resource(organization_id, data, user.id)


@router.post("/resources/files", response_model=ResourceRead, summary="Upload a resource file")
async def upload_resource_file(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    description: str | None = Form(None),
    category: str | None = Form(None),
    service: ResourceService = Depends(get_resource_service),
    user: User = Depends(require_role(*MANAGE_ROLES)),
) -> ResourceRead:
    organization_id = _require_org(user)

    content = await file.read()
    file_url = save_upload(content, file.filename, folder="resources")

    data = {
        "type": ResourceType.FILE,
        "title": title or file.filename,
        "description": description,
        "category": category,
        "file_url": file_url,
        "original_file_name": file.filename,
        "mime_type": file.content_type,
        "file_size": len(content),
    }
    return await service.create_resource(organization_id, data, user.id)


@router.get("/resources/{resource_id}", response_model=ResourceRead, summary="Get a resource")
async def get_resource(
    resource_id: UUID,
    service: ResourceService = Depends(get_resource_service),
    user: User = Depends(require_role(*VIEW_ROLES)),
) -> ResourceRead:
    resource = await service.get_resource(resource_id, organization_id=scoped_org_id(user))
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return resource


@router.patch("/resources/{resource_id}", response_model=ResourceRead, summary="Update a resource")
async def update_resource(
    resource_id: UUID,
    payload: ResourceUpdate,
    service: ResourceService = Depends(get_resource_service),
    user: User = Depends(require_role(*MANAGE_ROLES)),
) -> ResourceRead:
    resource = await service.get_resource(resource_id, organization_id=scoped_org_id(user))
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return await service.update_resource(resource, payload.model_dump(exclude_unset=True))


@router.delete("/resources/{resource_id}", status_code=204, summary="Delete a resource")
async def delete_resource(
    resource_id: UUID,
    service: ResourceService = Depends(get_resource_service),
    user: User = Depends(require_role(*MANAGE_ROLES)),
) -> None:
    resource = await service.get_resource(resource_id, organization_id=scoped_org_id(user))
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    if resource.type == ResourceType.FILE:
        delete_upload(resource.file_url)
    await service.delete_resource(resource)
