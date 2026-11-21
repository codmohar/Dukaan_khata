import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import settings

log = logging.getLogger("dukaan.db")

# statement_cache_size=0 keeps asyncpg compatible with Supabase's pgbouncer transaction pooler
engine = create_async_engine(
    settings.database_url,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    connect_args={"statement_cache_size": 0},
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session():
    """Dependency for FastAPI route handlers."""
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def init_db():
    """Verify database connection and ensure default shop exists on startup."""
    try:
        async with SessionLocal() as s:
            await s.execute(text("SELECT 1"))
            # Ensure default shop exists
            shop_id = settings.default_shop_id or "00000000-0000-0000-0000-000000000001"
            res = await s.execute(
                text("SELECT id FROM shops WHERE id = :sid"),
                {"sid": shop_id}
            )
            if not res.scalar():
                await s.execute(
                    text("""
                        INSERT INTO shops (id, name, owner_name, phone, language)
                        VALUES (:sid, 'Sri Lakshmi Kirana Store', 'Manjunath Gowda', '+91 98450 00000', 'kn-IN')
                        ON CONFLICT (id) DO NOTHING
                    """),
                    {"sid": shop_id}
                )
                await s.commit()
            log.info("Database connection and shop verification successful.")
    except Exception as e:
        log.warning("Database init_db notice: %s", e)
