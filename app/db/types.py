from enum import Enum as PyEnum
from typing import Type

from sqlalchemy import Enum as SQLEnum


def enum_type(enum_cls: Type[PyEnum], name: str, create_type: bool = False, **kwargs):
    return SQLEnum(
        enum_cls,
        name=name,
        create_type=create_type,
        values_callable=lambda enum: [member.value for member in enum],
        **kwargs,
    )
