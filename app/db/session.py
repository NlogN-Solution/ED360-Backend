from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from ..core.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.database_url.replace("postgresql+psycopg", "postgresql+asyncpg"), echo=False)
session_factory = async_sessionmaker(engine, expire_on_commit=False)
