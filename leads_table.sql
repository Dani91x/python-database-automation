-- Tabella Leads per la raccolta dei contatti e gestione free trial
create table if not exists public.leads (
    id uuid default gen_random_uuid() primary key,
    created_at timestamp with time zone default timezone('utc'::text, now()) not null,
    first_name text not null,
    last_name text not null,
    email text unique not null,
    phone text,
    telegram_username text,
    trial_start_date timestamp with time zone default timezone('utc'::text, now()),
    trial_end_date timestamp with time zone default timezone('utc'::text, now()) + interval '7 days',
    is_active boolean default true,
    
    -- Metadata opzionali
    source text, -- es. 'facebook_ads', 'telegram'
    notes text
);

-- RLS (Row Level Security) - Facoltativo: permetti l'inserimento pubblico per la landing page
alter table public.leads enable row level security;

create policy "Permetti inserimento pubblico leads"
on public.leads for insert
with check (true);

create policy "Solo admin può vedere i leads"
on public.leads for select
using (auth.role() = 'service_role');

-- RLS per fixture_predictions (Sola lettura pubblica)
alter table public.fixture_predictions enable row level security;

create policy "Pronostici visibili a tutti"
on public.fixture_predictions for select
using (true);

-- RLS per matches (Sola lettura pubblica)
alter table public.matches enable row level security;

create policy "Match visibili a tutti"
on public.matches for select
using (true);
