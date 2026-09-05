from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import DATABASE_URL

# Sync engine — only for table creation (metadata.create_all)
_sync_engine = create_engine(DATABASE_URL, echo=False)

# Async engine — for all CRUD operations (FastAPI routes)
_async_url = DATABASE_URL.replace("postgresql+psycopg://", "postgresql+asyncpg://")
async_engine = create_async_engine(_async_url, echo=False)

AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    autoflush=False,
    expire_on_commit=False,
)

# Sync sessionmaker — for background scheduler tasks running in ThreadPoolExecutor
_SyncSessionLocal = sessionmaker(bind=_sync_engine, expire_on_commit=False)

Base = declarative_base()


async def get_db():
    """Async DB dependency for FastAPI routes."""
    async with AsyncSessionLocal() as session:
        yield session


def get_sync_session():
    """Return a sync session for background/scheduler tasks."""
    return _SyncSessionLocal()


def init_db():
    """Create all tables (sync, called at startup)."""
    Base.metadata.create_all(_sync_engine)
