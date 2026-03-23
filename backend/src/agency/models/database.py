import ssl

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agency.config import get_settings

_engine = None
_session_factory = None


def _build_db_url(raw_url: str) -> str:
    """Ensure the URL uses the asyncpg driver prefix."""
    url = raw_url.split("?")[0]  # strip query params (handled via connect_args)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        db_url = _build_db_url(settings.database_url)

        connect_args: dict = {}
        if "neon.tech" in settings.database_url or settings.app_env == "prod":
            ssl_ctx = ssl.create_default_context()
            connect_args["ssl"] = ssl_ctx

        _engine = create_async_engine(
            db_url,
            echo=settings.debug,
            pool_size=5,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory
