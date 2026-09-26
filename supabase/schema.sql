create table if not exists public.market_reports (
  report_day date primary key,
  body text not null,
  chart_base64 text,
  created_at timestamptz not null default now()
);
alter table public.market_reports enable row level security;
revoke all on public.market_reports from anon, authenticated;
-- Only the service key held by GitHub Actions and the Edge Function can read/write.
