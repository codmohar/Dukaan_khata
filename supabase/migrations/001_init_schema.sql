-- DukaanAI Database Schema & Realtime Setup
-- Enable extensions for UUID generation and Trigram fuzzy text matching
create extension if not exists "pgcrypto";
create extension if not exists "pg_trgm";

-- 1. SHOPS TABLE
create table if not exists shops (
  id uuid primary key default gen_random_uuid(),
  name text not null default 'Sri Lakshmi Kirana Store',
  owner_name text default 'Manjunath Gowda',
  phone text default '+91 98450 00000',
  language text not null default 'kn-IN' check (language in ('kn-IN','hi-IN','en-IN')),
  created_at timestamptz not null default now()
);

-- 2. CUSTOMERS TABLE
create table if not exists customers (
  id uuid primary key default gen_random_uuid(),
  shop_id uuid not null references shops(id) on delete cascade,
  name text not null,
  phone text,
  landmark text,
  created_at timestamptz not null default now()
);

create index if not exists customers_name_trgm on customers using gin (name gin_trgm_ops);
create index if not exists customers_landmark_trgm on customers using gin (landmark gin_trgm_ops);
create index if not exists customers_shop_idx on customers (shop_id);

-- 3. TRANSACTIONS TABLE (LEDGER)
create table if not exists transactions (
  id uuid primary key default gen_random_uuid(),
  shop_id uuid not null references shops(id) on delete cascade,
  customer_id uuid not null references customers(id) on delete cascade,
  type text not null check (type in ('credit','payment')),   -- credit = udhar (customer owes), payment = jama (customer paid)
  amount numeric(12,2) not null check (amount > 0),
  note text,
  language text,
  raw_transcript text,
  status text not null default 'draft' check (status in ('draft','confirmed','cancelled')),
  created_at timestamptz not null default now(),
  confirmed_at timestamptz
);

create index if not exists transactions_shop_created_idx on transactions (shop_id, created_at desc);
create index if not exists transactions_customer_idx on transactions (customer_id);
create index if not exists transactions_status_idx on transactions (status);

-- 4. CUSTOMER BALANCES VIEW
-- Balance = what the customer owes the shop (confirmed transactions only)
-- with (security_invoker = true) enforces querying user's RLS permissions
create or replace view customer_balances
with (security_invoker = true) as
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

-- 5. REALTIME REPLICATION CONFIGURATION
-- Ensure full row payload is published during updates and deletes
alter table customers replica identity full;
alter table transactions replica identity full;

-- Safely add to supabase_realtime publication if publication exists
do $$
begin
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
    alter publication supabase_realtime add table transactions, customers;
  end if;
end $$;

-- 6. ROW LEVEL SECURITY (RLS) POLICIES
-- Permissive policies for anon and authenticated users for frictionless client sync
alter table shops enable row level security;
alter table customers enable row level security;
alter table transactions enable row level security;

do $$
begin
  if not exists (select 1 from pg_policies where policyname = 'Allow public read and write on shops') then
    create policy "Allow public read and write on shops" on shops for all using (true) with check (true);
  end if;
  if not exists (select 1 from pg_policies where policyname = 'Allow public read and write on customers') then
    create policy "Allow public read and write on customers" on customers for all using (true) with check (true);
  end if;
  if not exists (select 1 from pg_policies where policyname = 'Allow public read and write on transactions') then
    create policy "Allow public read and write on transactions" on transactions for all using (true) with check (true);
  end if;
end $$;

-- 7. SEED DATA FOR DEMO & TESTING
-- Default shop with predictable UUID
insert into shops (id, name, owner_name, phone, language)
values (
  '00000000-0000-0000-0000-000000000001',
  'Sri Lakshmi Kirana Store',
  'Manjunath Gowda',
  '+91 98450 00000',
  'kn-IN'
)
on conflict (id) do update set 
  name = excluded.name, 
  owner_name = excluded.owner_name;

-- Sample customers (including duplicate name for disambiguation test: Ramesh Kumar vs Ramesh Gowda)
insert into customers (id, shop_id, name, phone, landmark)
values 
  ('11111111-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'Ramesh Kumar', '+91 98450 12345', 'Opposite Bus Stand'),
  ('11111111-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000001', 'Ramesh Gowda', '+91 98450 67890', 'Near Ganapathi Temple'),
  ('11111111-0000-0000-0000-000000000003', '00000000-0000-0000-0000-000000000001', 'Suresh Tailor', '+91 94480 11223', 'Market Cross Road'),
  ('11111111-0000-0000-0000-000000000004', '00000000-0000-0000-0000-000000000001', 'Anita Bai', '+91 98860 33445', 'Behind Govt School'),
  ('11111111-0000-0000-0000-000000000005', '00000000-0000-0000-0000-000000000001', 'Raju Electrician', '+91 97410 55667', 'Main Road Post Office')
on conflict (id) do nothing;

-- Sample confirmed transactions
insert into transactions (id, shop_id, customer_id, type, amount, note, language, raw_transcript, status, confirmed_at, created_at)
values
  ('22222222-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', '11111111-0000-0000-0000-000000000001', 'credit', 340.00, 'Rice and dal', 'kn-IN', 'Ramesh Kumar ge 340 rupayi udhar', 'confirmed', now() - interval '2 days', now() - interval '2 days'),
  ('22222222-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000001', '11111111-0000-0000-0000-000000000002', 'credit', 650.00, 'Cooking oil and sugar', 'kn-IN', 'Ramesh Gowda 650 udhar', 'confirmed', now() - interval '1 day', now() - interval '1 day'),
  ('22222222-0000-0000-0000-000000000003', '00000000-0000-0000-0000-000000000001', '11111111-0000-0000-0000-000000000003', 'credit', 500.00, 'Atta and spices', 'hi-IN', 'Suresh ka 500 udhar likho', 'confirmed', now() - interval '3 days', now() - interval '3 days'),
  ('22222222-0000-0000-0000-000000000004', '00000000-0000-0000-0000-000000000001', '11111111-0000-0000-0000-000000000003', 'payment', 300.00, 'Cash received', 'hi-IN', 'Suresh ne 300 jama kiya', 'confirmed', now() - interval '1 day', now() - interval '1 day'),
  ('22222222-0000-0000-0000-000000000005', '00000000-0000-0000-0000-000000000001', '11111111-0000-0000-0000-000000000004', 'credit', 220.00, 'Tea powder and milk', 'kn-IN', 'Anita 220 udhar bardu', 'confirmed', now(), now()),
  -- 1 pending draft awaiting shopkeeper confirmation
  ('22222222-0000-0000-0000-000000000006', '00000000-0000-0000-0000-000000000001', '11111111-0000-0000-0000-000000000005', 'credit', 150.00, 'Batteries and soap', 'en-IN', 'Add 150 credit for Raju Electrician', 'draft', null, now())
on conflict (id) do nothing;
