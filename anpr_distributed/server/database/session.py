"""
Async database session factory for SQLAlchemy 2.0 + asyncpg.

Provides:
  - get_async_session(): FastAPI dependency for request-scoped sessions
  - get_engine(): module-level engine singleton
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from server.config import DATABASE_URL

# ── Engine (singleton, created once at import) ────────────────────────────────
_engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=10,            # Good for 4-5 concurrent users + edge node
    max_overflow=5,
    pool_pre_ping=True,      # Detect stale connections
    pool_recycle=1800,        # Recycle connections every 30 min
)

_async_session_factory = async_sessionmaker(
    bind=_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


def get_engine():
    """Return the global async engine."""
    return _engine


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields a request-scoped async session."""
    async with _async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_session_context() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for use outside of FastAPI dependency injection."""
    async with _async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
