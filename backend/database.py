from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import event, text
from fastapi import Request
from backend.config import settings
import logging

logger = logging.getLogger(__name__)

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=20,
    max_overflow=40,
    pool_pre_ping=True,
    pool_recycle=3600,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db(request: Request) -> AsyncSession:
    async with AsyncSessionLocal() as session:
        # SEC-4: Set RLS context from request state if authenticated
        payload = getattr(request.state, "admin_payload", None) or getattr(request.state, "worker_payload", None)
        if payload:
            await set_rls_context(
                session,
                scope_type=payload.get("scope_type", "all_india"),
                scope_id=payload.get("scope_id"),
                role=payload.get("role", "public")
            )
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Create all tables and apply RLS policies."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("""
            -- Revoke UPDATE/DELETE on vote_ledger at DB role level (SEC-1)
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'matsetu_app') THEN
                    REVOKE UPDATE, DELETE ON vote_ledger FROM matsetu_app;
                END IF;
            END $$;
        """))
        logger.info("Database initialized with RLS policies applied.")


async def set_rls_context(session: AsyncSession, scope_type: str, scope_id: str, role: str):
    """Set RLS session context for current request (SEC-4)."""
    await session.execute(
        text("SELECT set_config('app.scope_type', :st, true)"),
        {"st": scope_type}
    )
    await session.execute(
        text("SELECT set_config('app.scope_id', :si, true)"),
        {"si": scope_id}
    )
    await session.execute(
        text("SELECT set_config('app.role', :r, true)"),
        {"r": role}
    )
