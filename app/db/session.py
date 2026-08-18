from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from ..core.config import get_settings

settings = get_settings()

# asyncpg's connect() doesn't understand the "sslmode" query-string keyword
# managed Postgres URLs use (that's psycopg/libpq-specific) — database_url
# already strips it, so SSL is requested explicitly here instead when it's
# actually needed (i.e. never for local dev's DB_* vars).
_connect_args = {"ssl": "require"} if settings.database_requires_ssl else {}

engine = create_async_engine(
    settings.database_url.replace("postgresql+psycopg", "postgresql+asyncpg"),
    echo=False,
    connect_args=_connect_args,
)
session_factory = async_sessionmaker(engine, expire_on_commit=False)
