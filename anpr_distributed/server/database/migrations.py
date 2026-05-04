"""
Database initialization: create tables and seed default admin user.

Replaces init_db() + create_default_admin() from the old database.py.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy.ext.asyncio import create_async_engine

from server.config import DATABASE_URL
from server.database.models import Base, User
from server.database.session import get_session_context
from server.auth.password import hash_password

LOGGER = logging.getLogger("anpr.server.migrations")


async def create_tables() -> None:
    """Create all tables if they don't exist."""
    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    LOGGER.info("Database tables created/verified.")


async def seed_default_admin() -> None:
    """Create the default admin user if no admin exists."""
    from sqlalchemy import select

    async with get_session_context() as session:
        result = await session.execute(
            select(User).where(User.username == "admin")
        )
        existing = result.scalar_one_or_none()

        if existing is None:
            admin = User(
                username="admin",
                full_name="System Administrator",
                password_hash=hash_password("admin123"),
                role="admin",
                is_active=True,
            )
            session.add(admin)
            await session.flush()
            LOGGER.info("Default admin user created (username: admin, password: admin123)")


async def init_database() -> None:
    """Full database initialization: tables + seed data."""
    await create_tables()
    await seed_default_admin()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(init_database())
