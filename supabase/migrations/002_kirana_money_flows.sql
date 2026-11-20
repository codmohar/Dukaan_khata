-- Migration 002: Kirana Money Flows (Adjustments, Payment Modes, Due Dates, Backdating, Itemized Bills)

-- 1. Allow 'adjustment' in transactions.type (for returns, discounts, write-offs, corrections)
alter table transactions drop constraint if exists transactions_type_check;
alter table transactions add constraint transactions_type_check
  check (type in ('credit', 'payment', 'adjustment'));

-- 2. Add payment_mode, adjustment_reason, due_date, backdated_to, and items JSONB
alter table transactions add column if not exists payment_mode text
  check (payment_mode is null or payment_mode in ('cash', 'upi', 'other'));

alter table transactions add column if not exists adjustment_reason text
  check (adjustment_reason is null or adjustment_reason in ('discount', 'return', 'write_off', 'correction'));

alter table transactions add column if not exists due_date date;
alter table transactions add column if not exists backdated_to date;
alter table transactions add column if not exists items jsonb;

-- 3. Widen shops.language constraint to support all Indian languages
alter table shops drop constraint if exists shops_language_check;
alter table shops add constraint shops_language_check
  check (language in ('kn-IN', 'hi-IN', 'en-IN', 'ta-IN', 'te-IN', 'mr-IN', 'bn-IN', 'gu-IN'));

-- 4. Index due_date for upcoming collection reminders
create index if not exists transactions_due_date_idx on transactions (shop_id, due_date)
  where due_date is not null and status = 'confirmed';

-- 5. Refresh customer_balances view (credit adds to balance; payment and adjustment reduce balance; negative = customer advance)
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

