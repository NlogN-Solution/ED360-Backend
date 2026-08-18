import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")


class Settings:
    # Individual DB_* vars are for local dev (matches the .env convention
    # everywhere else in this file). In production (Render), set DATABASE_URL
    # instead — Render's managed Postgres provides one directly — and it takes
    # priority; see the `database_url` property below.
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
    DB_NAME: str = os.getenv("DB_NAME", "ignition")
    DB_USER: str = os.getenv("DB_USER", "postgres")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "postgres")
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "5"))
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", str(BASE_DIR / "uploads"))

    # Cloudinary — required in production. Render's filesystem is ephemeral
    # (wiped on every deploy/restart), so local-disk uploads under UPLOAD_DIR
    # only work for local dev. When these are unset, app/core/storage.py
    # transparently falls back to local disk, so leaving them blank locally
    # is fine and matches every other integration's "unset = feature off"
    # convention in this file.
    CLOUDINARY_CLOUD_NAME: str = os.getenv("CLOUDINARY_CLOUD_NAME", "")
    CLOUDINARY_API_KEY: str = os.getenv("CLOUDINARY_API_KEY", "")
    CLOUDINARY_API_SECRET: str = os.getenv("CLOUDINARY_API_SECRET", "")

    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "change-me-super-secret")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5173")
    CORS_ORIGINS: list[str] = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174,"
            "http://localhost:5175,http://127.0.0.1:5175",
        ).split(",")
        if origin.strip()
    ]

    # Fernet key for encrypting third-party credentials (e.g. WhatsApp access tokens)
    # at rest. Generate one with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # Left blank by default like everything else here, but app/core/encryption.py
    # raises at first use (not at import time) if it's missing or malformed —
    # silently storing credentials nothing can ever decrypt again is worse than
    # a loud startup failure.
    CREDENTIAL_ENCRYPTION_KEY: str = os.getenv("CREDENTIAL_ENCRYPTION_KEY", "")

    # Meta WhatsApp Cloud API. WHATSAPP_WEBHOOK_VERIFY_TOKEN is a single value you
    # choose and paste into the Meta App dashboard's webhook subscription config —
    # it's app-level (one App = one webhook subscription), not per-organization,
    # since Meta only ever calls one shared webhook URL for every connected org.
    META_APP_SECRET: str = os.getenv("META_APP_SECRET", "")
    META_GRAPH_API_URL: str = os.getenv("META_GRAPH_API_URL", "https://graph.facebook.com")
    META_API_VERSION: str = os.getenv("META_API_VERSION", "v25.0")
    WHATSAPP_WEBHOOK_VERIFY_TOKEN: str = os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "")

    # WhatsApp Embedded Signup (the "Continue with Meta" connect flow) — both
    # app-level, same one Meta App for every organization, never org-specific.
    # META_APP_ID is public (the frontend passes it to Meta's own JS SDK);
    # META_APP_SECRET above is reused server-side for the OAuth code exchange.
    # Leaving either unset just hides the Embedded Signup button and falls
    # back to manual credential entry — see IntegrationService.
    META_APP_ID: str = os.getenv("META_APP_ID", "")
    WHATSAPP_EMBEDDED_SIGNUP_CONFIG_ID: str = os.getenv("WHATSAPP_EMBEDDED_SIGNUP_CONFIG_ID", "")

    # Gmail email integration ("Continue with Google" connect flow) — one
    # Google Cloud OAuth client shared by every organization, never
    # org-specific. GOOGLE_CLIENT_ID is public (passed to the frontend to
    # build the consent URL); GOOGLE_CLIENT_SECRET is used server-side only,
    # for the OAuth code exchange. Leaving either unset hides the "Continue
    # with Google" button — see IntegrationService.
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")

    @property
    def database_url(self) -> str:
        if self.DATABASE_URL:
            # Render (and most managed Postgres providers) hand out
            # postgres:// or postgresql://, sometimes with a driver hint
            # already baked in (postgresql+asyncpg://) and almost always a
            # "?sslmode=require" query param. Normalize the driver to
            # psycopg3 regardless of what was there, and strip sslmode — it's
            # a psycopg/libpq keyword that asyncpg's connect() doesn't
            # understand (db/session.py swaps this URL to asyncpg for the
            # runtime engine), and psycopg's default "prefer" behavior
            # negotiates SSL correctly anyway once the server requires it.
            # See `database_requires_ssl` for how the async engine still
            # gets told to require SSL explicitly.
            scheme, _, rest = self.DATABASE_URL.partition("://")
            driver = scheme.split("+")[0]
            if driver not in ("postgres", "postgresql"):
                return self.DATABASE_URL
            split = urlsplit(f"postgresql://{rest}")
            query = dict(parse_qsl(split.query))
            query.pop("sslmode", None)
            return urlunsplit(("postgresql+psycopg", split.netloc, split.path, urlencode(query), ""))
        return (
            f"postgresql+psycopg://{self.DB_USER}:{self.DB_PASSWORD}@"
            f"{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    @property
    def database_requires_ssl(self) -> bool:
        """True whenever DATABASE_URL is externally provided — that's always
        a managed Postgres instance in production, which requires SSL. Local
        dev's individual DB_* vars never need it."""
        return bool(self.DATABASE_URL)

    @property
    def upload_dir(self) -> Path:
        path = Path(self.UPLOAD_DIR)
        path.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache
def get_settings() -> Settings:
    return Settings()
