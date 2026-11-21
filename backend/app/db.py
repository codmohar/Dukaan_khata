import logging
import uuid
from sqlalchemy import text

from .config import settings
from .models import Base, Customer, Shop, Transaction

log = logging.getLogger("dukaan.db")

# Detect driver to configure connection options properly
is_postgres = "postgres" in settings.database_url.lower()

engine_kwargs = {
    "pool_pre_ping": True,
}

if is_postgres:
    # statement_cache_size=0 is required for Supabase transaction poolers (PgBouncer)
    engine_kwargs.update({
        "pool_size": 5,
        "max_overflow": 10,
        "connect_args": {"statement_cache_size": 0},
    })

try:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    engine = create_async_engine(settings.database_url, **engine_kwargs)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
except Exception as e:
    log.warning("Async engine initialization notice (requires sqlalchemy[asyncio] and greenlet): %s", e)
    AsyncSession = object
    engine = None
    SessionLocal = None


async def get_session():
    if not SessionLocal:
        raise RuntimeError("Database engine not initialized. Please install requirements: pip install -r requirements.txt")
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def init_db():
    """Ensure tables, default shop, and initial demo data are seeded on startup."""
    if not engine or not SessionLocal:
        log.warning("init_db skipped: engine or SessionLocal not initialized")
        return

    try:
        async with engine.begin() as conn:
            if is_postgres:
                try:
                    await conn.execute(text("create extension if not exists \"pgcrypto\";"))
                    await conn.execute(text("create extension if not exists \"pg_trgm\";"))
                except Exception as ext_err:
                    log.debug("Extension check notice: %s", ext_err)

            # Create tables if not already created via migrations
            await conn.run_sync(Base.metadata.create_all)

            # Idempotently apply Migration 002 columns & constraints on Postgres
            if is_postgres:
                migration_stmts = [
                    "alter table transactions drop constraint if exists transactions_type_check",
                    "alter table transactions add constraint transactions_type_check check (type in ('credit', 'payment', 'adjustment'))",
                    "alter table transactions add column if not exists payment_mode text",
                    "alter table transactions add column if not exists adjustment_reason text",
                    "alter table transactions add column if not exists due_date date",
                    "alter table transactions add column if not exists backdated_to date",
                    "alter table transactions add column if not exists items jsonb",
                    "alter table shops add column if not exists pin text default '1234'",
                    "alter table shops drop constraint if exists shops_language_check",
                    "alter table shops add constraint shops_language_check check (language in ('kn-IN', 'hi-IN', 'en-IN', 'ta-IN', 'te-IN', 'mr-IN', 'bn-IN', 'gu-IN'))",
                    # Migration 003: Scan Book (scans, scan_lines, transactions.source & scan_id)
                    "alter table transactions add column if not exists source text not null default 'voice'",
                    "alter table transactions drop constraint if exists transactions_source_check",
                    "alter table transactions add constraint transactions_source_check check (source in ('voice', 'scan', 'manual'))",
                    """create table if not exists scans (
                        id uuid primary key default gen_random_uuid(),
                        shop_id uuid not null references shops(id) on delete cascade,
                        doc_type text not null check (doc_type in ('khata_page', 'payment_proof', 'supplier_bill', 'unknown')),
                        image_hash text not null,
                        status text not null default 'review' check (status in ('review', 'approved', 'rejected')),
                        total_shown numeric(12, 2),
                        summary text,
                        warnings jsonb not null default '[]',
                        created_at timestamptz not null default now()
                    )""",
                    "create unique index if not exists scans_shop_hash_idx on scans (shop_id, image_hash) where status <> 'rejected'",
                    """create table if not exists scan_lines (
                        id uuid primary key default gen_random_uuid(),
                        scan_id uuid not null references scans(id) on delete cascade,
                        row_no int not null,
                        raw_name text,
                        customer_id uuid references customers(id) on delete set null,
                        type text not null check (type in ('credit', 'payment')),
                        amount numeric(12, 2) not null check (amount > 0),
                        txn_date date,
                        note text,
                        confidence real not null default 0.5,
                        raw_text text,
                        candidates jsonb not null default '[]',
                        duplicate boolean not null default false,
                        include boolean not null default true,
                        transaction_id uuid references transactions(id) on delete set null
                    )""",
                    "create index if not exists scan_lines_scan_idx on scan_lines (scan_id, row_no)",
                    "alter table transactions add column if not exists scan_id uuid references scans(id) on delete set null",
                    # Migration 004: Advanced Features (Household, Rules, Promises, Reconciliation, Timeline)
                    "alter table customers add column if not exists outstanding_balance numeric(12,2) not null default 0.00",
                    """create table if not exists household_members (
                        id uuid primary key default gen_random_uuid(),
                        customer_id uuid not null references customers(id) on delete cascade,
                        shop_id uuid not null references shops(id) on delete cascade,
                        member_name varchar(120) not null,
                        relationship varchar(60),
                        is_authorized boolean not null default true,
                        created_at timestamptz not null default now(),
                        unique (customer_id, member_name)
                    )""",
                    "alter table household_members alter column id set default gen_random_uuid()",
                    "create index if not exists idx_hm_customer on household_members(customer_id)",
                    "create index if not exists idx_hm_shop on household_members(shop_id)",
                    "create index if not exists idx_hm_name_trgm on household_members using gin (member_name gin_trgm_ops)",
                    """do $$ begin
                        if not exists (select 1 from pg_constraint where conname = 'uq_hm_cust_member') then
                            alter table household_members add constraint uq_hm_cust_member unique (customer_id, member_name);
                        end if;
                    end $$;""",
                    "alter table transactions add column if not exists member_id uuid references household_members(id) on delete set null",
                    "alter table transactions add column if not exists item_note text",
                    "alter table transactions add column if not exists rule_warnings jsonb not null default '[]'",
                    "alter table transactions add column if not exists transcript_snippet text",
                    "alter table transactions add column if not exists rule_override boolean not null default false",
                    "alter table transactions drop constraint if exists chk_tx_payment_mode",
                    "alter table transactions drop constraint if exists transactions_payment_mode_check",
                    "alter table transactions add constraint transactions_payment_mode_check check (payment_mode is null or lower(payment_mode) in ('cash', 'upi', 'credit', 'other'))",
                    "update transactions set payment_mode = 'credit' where type = 'credit' and payment_mode is null",
                    "update transactions set payment_mode = 'cash' where type = 'payment' and payment_mode is null",
                    "create index if not exists idx_tx_member on transactions(member_id)",
                    "create index if not exists idx_tx_item_trgm on transactions using gin (item_note gin_trgm_ops)",
                    """create table if not exists promises (
                        id uuid primary key default gen_random_uuid(),
                        shop_id uuid not null references shops(id) on delete cascade,
                        customer_id uuid references customers(id) on delete set null,
                        member_id uuid references household_members(id) on delete set null,
                        entity_name varchar(120) not null,
                        promise_type varchar(30) not null check (promise_type in ('PAYMENT_PROMISE','GOODS_RESERVATION','SUPPLIER_DELIVERY')),
                        promised_amount numeric(12,2) check (promised_amount is null or promised_amount > 0),
                        description text not null,
                        expected_date date not null,
                        status varchar(20) not null default 'PENDING' check (status in ('PENDING','FULFILLED','OVERDUE','CANCELLED')),
                        fulfilled_transaction_id uuid references transactions(id) on delete set null,
                        source_transcript text,
                        created_at timestamptz not null default now(),
                        fulfilled_at timestamptz
                    )""",
                    "create index if not exists idx_prom_shop_status_date on promises(shop_id, status, expected_date)",
                    "create index if not exists idx_prom_customer on promises(customer_id)",
                    "create index if not exists idx_prom_desc_trgm on promises using gin (description gin_trgm_ops)",
                    """create table if not exists shop_rules (
                        id uuid primary key default gen_random_uuid(),
                        shop_id uuid not null references shops(id) on delete cascade,
                        rule_category varchar(40) not null check (rule_category in ('NEW_CUSTOMER_CAP','BALANCE_CAP','TIME_CUTOFF','MEMBER_AUTH','CUSTOM_NOTE')),
                        rule_text text not null,
                        structured_condition jsonb not null,
                        is_active boolean not null default true,
                        created_at timestamptz not null default now()
                    )""",
                    "create index if not exists idx_rules_shop_active on shop_rules(shop_id, is_active)",
                    """create table if not exists daily_reconciliations (
                        id uuid primary key default gen_random_uuid(),
                        shop_id uuid not null references shops(id) on delete cascade,
                        reconciliation_date date not null default current_date,
                        recorded_cash numeric(12,2) not null,
                        actual_cash numeric(12,2) not null,
                        recorded_upi numeric(12,2) not null,
                        actual_upi numeric(12,2) not null,
                        cash_difference numeric(12,2) not null,
                        upi_difference numeric(12,2) not null,
                        status varchar(30) not null check (status in ('MATCHED','NEEDS_INVESTIGATION','RESOLVED')),
                        findings jsonb not null default '[]',
                        audit_notes text,
                        created_at timestamptz not null default now(),
                        unique (shop_id, reconciliation_date)
                    )""",
                    "create index if not exists idx_recon_shop_date on daily_reconciliations(shop_id, reconciliation_date desc)",
                    "create or replace view draft_transactions as select * from transactions where status = 'draft'",
                    "create or replace view promises_effective as select p.*, case when p.status = 'PENDING' and p.expected_date < current_date then 'OVERDUE' else p.status end as effective_status from promises p",
                    """create or replace function enforce_member_matches_customer() returns trigger as $$
                    begin
                      if NEW.member_id is not null then
                        if not exists (select 1 from household_members hm where hm.id = NEW.member_id and hm.customer_id = NEW.customer_id) then
                          raise exception 'member_id % does not belong to customer_id %', NEW.member_id, NEW.customer_id;
                        end if;
                      end if;
                      return NEW;
                    end $$ language plpgsql;""",
                    "drop trigger if exists trg_tx_member_check on transactions",
                    "create trigger trg_tx_member_check before insert or update on transactions for each row execute function enforce_member_matches_customer()",
                    "alter table household_members enable row level security",
                    "alter table promises enable row level security",
                    "alter table shop_rules enable row level security",
                    "alter table daily_reconciliations enable row level security",
                    # Migration 005: Shop Cash Book, Refund Support, Directional Money Flows
                    """create table if not exists cash_book_entries (
                        id uuid primary key default gen_random_uuid(),
                        shop_id uuid not null references shops(id) on delete cascade,
                        type varchar(20) not null check (type in ('cash_in', 'cash_out')),
                        amount numeric(12, 2) not null check (amount > 0),
                        reason varchar(100) default 'general',
                        description text,
                        payment_mode varchar(20) default 'cash',
                        transaction_date date not null default current_date,
                        created_at timestamptz not null default now()
                    )""",
                    "create index if not exists idx_cash_book_shop on cash_book_entries(shop_id)",
                    "create index if not exists idx_cash_book_date on cash_book_entries(shop_id, transaction_date)",
                    "alter table transactions drop constraint if exists transactions_type_check",
                    "alter table transactions add constraint transactions_type_check check (type in ('credit', 'payment', 'adjustment', 'refund'))",
                    "alter table transactions drop constraint if exists transactions_adjustment_reason_check",
                    "alter table transactions add constraint transactions_adjustment_reason_check check (adjustment_reason is null or lower(adjustment_reason) in ('discount', 'return', 'write_off', 'correction', 'round_off', 'refund'))",
                    "alter table transactions alter column customer_id drop not null",
                ]
                for stmt in migration_stmts:
                    try:
                        await conn.execute(text(stmt))
                    except Exception as mig_err:
                        log.debug("Migration 002 notice (%s): %s", stmt[:40], mig_err)

            # Ensure customer_balances view exists with security_invoker = true on Postgres
            invoker_clause = "with (security_invoker = true)" if is_postgres else ""
            view_sql = f"""
            create or replace view customer_balances
            {invoker_clause} as
            select 
              c.id as customer_id, 
              c.shop_id,
              coalesce(
                sum(case when t.type = 'credit' then t.amount else -t.amount end)
                filter (where t.status = 'confirmed'), 
                0
              ) as balance
            from customers c 
            left join transactions t on t.customer_id = c.id
            group by c.id, c.shop_id;
            """
            try:
                await conn.execute(text(view_sql))
                # Backfill customers.outstanding_balance from view
                await conn.execute(text("""
                    update customers c
                    set outstanding_balance = coalesce(b.balance, 0.00)
                    from customer_balances b
                    where b.customer_id = c.id
                """))
            except Exception as e:
                log.debug("View creation notice (view may already exist): %s", e)

        # Seed default shop and starter customers if table is empty
        async with SessionLocal() as s:
            target_shop_id = uuid.UUID(settings.default_shop_id)
            existing_shop = await s.get(Shop, target_shop_id)
            if not existing_shop:
                default_shop = Shop(
                    id=target_shop_id,
                    name="Sri Lakshmi Kirana Store",
                    owner_name="Manjunath Gowda",
                    phone="+91 98450 00000",
                    language="kn-IN",
                )
                s.add(default_shop)
                await s.commit()
                log.info("Initialized default shop: %s", target_shop_id)

            # Seed demo customers if none exist in default shop
            cust_count = (await s.execute(
                text("select count(*) from customers where shop_id = :sid"),
                {"sid": str(target_shop_id)}
            )).scalar() or 0

            if cust_count == 0:
                demo_customers = [
                    Customer(
                        id=uuid.UUID("11111111-0000-0000-0000-000000000001"),
                        shop_id=target_shop_id,
                        name="Ramesh Kumar",
                        phone="+91 98450 12345",
                        landmark="Opposite Bus Stand",
                    ),
                    Customer(
                        id=uuid.UUID("11111111-0000-0000-0000-000000000002"),
                        shop_id=target_shop_id,
                        name="Ramesh Gowda",
                        phone="+91 98450 67890",
                        landmark="Near Ganapathi Temple",
                    ),
                    Customer(
                        id=uuid.UUID("11111111-0000-0000-0000-000000000003"),
                        shop_id=target_shop_id,
                        name="Suresh Tailor",
                        phone="+91 94480 11223",
                        landmark="Market Cross Road",
                    ),
                    Customer(
                        id=uuid.UUID("11111111-0000-0000-0000-000000000004"),
                        shop_id=target_shop_id,
                        name="Anita Bai",
                        phone="+91 98860 33445",
                        landmark="Behind Govt School",
                    ),
                    Customer(
                        id=uuid.UUID("11111111-0000-0000-0000-000000000005"),
                        shop_id=target_shop_id,
                        name="Raju Electrician",
                        phone="+91 97410 55667",
                        landmark="Main Road Post Office",
                    ),
                ]
                s.add_all(demo_customers)
                await s.commit()
                log.info("Seeded %d demo customers", len(demo_customers))

    except Exception as e:
        log.warning("Database bootstrap notice: %s", e)
