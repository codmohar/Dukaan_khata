import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import settings
from .models import Base

log = logging.getLogger("dukaan.db")

# statement_cache_size=0 keeps asyncpg compatible with Supabase's pgbouncer transaction pooler
engine = create_async_engine(
    settings.async_database_url,
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
    """Verify database connection, auto-create tables/views, and ensure default shop exists on startup."""
    try:
        async with engine.begin() as conn:
            # Create all core tables from SQLAlchemy models
            await conn.run_sync(Base.metadata.create_all)

            # Ensure customer_balances view exists
            await conn.execute(text("""
                CREATE OR REPLACE VIEW customer_balances AS
                SELECT
                    c.id AS customer_id,
                    c.shop_id,
                    COALESCE(
                        SUM(
                            CASE
                                WHEN t.type = 'credit' THEN t.amount
                                ELSE -t.amount
                            END
                        ) FILTER (WHERE t.status = 'confirmed'),
                        0
                    ) AS balance
                FROM customers c
                LEFT JOIN transactions t ON t.customer_id = c.id
                GROUP BY c.id, c.shop_id;
            """))

            # Ensure scans and scan_lines tables exist
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS scans (
                  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                  shop_id uuid NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
                  doc_type text NOT NULL,
                  image_hash text NOT NULL,
                  status text NOT NULL DEFAULT 'review',
                  total_shown numeric(12, 2),
                  summary text,
                  warnings jsonb NOT NULL DEFAULT '[]'::jsonb,
                  created_at timestamptz NOT NULL DEFAULT now()
                );

                CREATE TABLE IF NOT EXISTS scan_lines (
                  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                  scan_id uuid NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
                  row_no int NOT NULL,
                  raw_name text,
                  customer_id uuid REFERENCES customers(id) ON DELETE SET NULL,
                  type text NOT NULL,
                  amount numeric(12, 2) NOT NULL,
                  txn_date date,
                  note text,
                  confidence real NOT NULL DEFAULT 0.5,
                  raw_text text,
                  candidates jsonb NOT NULL DEFAULT '[]'::jsonb,
                  duplicate boolean NOT NULL DEFAULT false,
                  include boolean NOT NULL DEFAULT true,
                  transaction_id uuid REFERENCES transactions(id) ON DELETE SET NULL
                );
            """))

        async with SessionLocal() as s:
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
            log.info("Database schema and default shop initialized successfully.")
    except Exception as e:
        log.warning("Database init_db notice: %s", e)
