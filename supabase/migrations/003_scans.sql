-- Migration 003: Image-reading agent ("Scan Book")
-- Every scan goes to review first; nothing hits the ledger until approved by the shopkeeper.
-- Uploaded photos are NEVER stored; only sha256 image_hash is kept to prevent duplicate uploads.

alter table transactions add column if not exists source text not null default 'voice';
alter table transactions drop constraint if exists transactions_source_check;
alter table transactions add constraint transactions_source_check
  check (source in ('voice', 'scan', 'manual'));

create table if not exists scans (
  id uuid primary key default gen_random_uuid(),
  shop_id uuid not null references shops(id) on delete cascade,
  doc_type text not null check (doc_type in ('khata_page', 'payment_proof', 'supplier_bill', 'unknown')),
  image_hash text not null,
  status text not null default 'review' check (status in ('review', 'approved', 'rejected')),
  total_shown numeric(12, 2),
  summary text,
  warnings jsonb not null default '[]',
  created_at timestamptz not null default now()
);

create unique index if not exists scans_shop_hash_idx
  on scans (shop_id, image_hash)
  where status <> 'rejected';

create table if not exists scan_lines (
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
);

create index if not exists scan_lines_scan_idx on scan_lines (scan_id, row_no);

alter table transactions add column if not exists scan_id uuid references scans(id) on delete set null;

-- Enable permissive RLS policies for scans & scan_lines matching existing tables
alter table scans enable row level security;
alter table scan_lines enable row level security;

do $$
begin
  if not exists (select 1 from pg_policies where policyname = 'Allow public read and write on scans') then
    create policy "Allow public read and write on scans" on scans for all using (true) with check (true);
  end if;
  if not exists (select 1 from pg_policies where policyname = 'Allow public read and write on scan_lines') then
    create policy "Allow public read and write on scan_lines" on scan_lines for all using (true) with check (true);
  end if;
end $$;

