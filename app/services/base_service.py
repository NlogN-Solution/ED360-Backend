from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.base import Base


class BaseService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, model: type[Base], instance_id: Any) -> Base | None:
        return await self.session.get(model, instance_id)

    async def delete(self, instance: Base) -> Base:
        await self.session.delete(instance)
        await self.session.commit()
        return instance

    async def save(self, instance: Base) -> Base:
        self.session.add(instance)
        await self.session.commit()
        await self.session.refresh(instance)
        return instance

    async def update(self, instance: Base, data: dict[str, Any]) -> Base:
        for key, value in data.items():
            setattr(instance, key, value)
        return await self.save(instance)

    @staticmethod
    def to_dict(instance: Base, exclude: set[str] | None = None) -> dict[str, Any]:
        exclude = exclude or set()
        return {k: v for k, v in instance.__dict__.items() if not k.startswith("_") and k not in exclude}
