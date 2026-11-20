-- DukaanAI Migration 003: Extended Indian Languages & Reminders Table
-- Matches conversation_playbook.md (14 languages & reminder tracking)

create table if not exists reminders (
    id uuid primary key default gen_random_uuid(),
    shop_id uuid not null references shops(id) on delete cascade,
    customer_id uuid not null references customers(id) on delete cascade,
    amount numeric(12,2) not null check (amount > 0),
    due_date date,
    message text,
    status text not null default 'pending' check (status in ('pending', 'sent', 'dismissed')),
    created_at timestamptz not null default now()
);

create index if not exists reminders_shop_idx on reminders(shop_id);
create index if not exists reminders_customer_idx on reminders(customer_id);

alter table shops drop constraint if exists shops_language_check;
alter table shops add constraint shops_language_check check (
    language in (
        'kn-IN', 'hi-IN', 'en-IN', 'ta-IN', 'te-IN', 'mr-IN', 'bn-IN', 'gu-IN',
        'ml-IN', 'pa-IN', 'or-IN', 'od-IN', 'as-IN', 'ur-IN'
    )
);

alter table transactions drop constraint if exists transactions_type_check;
alter table transactions add constraint transactions_type_check check (
    type in ('credit', 'payment', 'adjustment')
);

