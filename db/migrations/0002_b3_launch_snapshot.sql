-- Outcome AI migration 0002_b3_launch_snapshot: immutable approved-profile/policy snapshot per campaign,
-- so later profile or policy edits cannot change what a running campaign is allowed to say or do.

begin;

do $$
begin
  if exists (
    select 1 from information_schema.columns
    where table_schema = '__OUTCOME_SCHEMA__' and table_name = 'campaigns' and column_name = 'launch_snapshot_json'
  ) then
    raise exception 'migration 0002_b3_launch_snapshot already applied';
  end if;
end $$;

alter table __OUTCOME_SCHEMA__.campaigns
  add column launch_snapshot_json jsonb not null default '{}'::jsonb;

create function __OUTCOME_PRIVATE_SCHEMA__.campaign_snapshot_immutable() returns trigger
language plpgsql set search_path = '' as $$
begin
  if new.launch_snapshot_json is distinct from old.launch_snapshot_json
     or new.profile_version is distinct from old.profile_version
     or new.config_version is distinct from old.config_version
     or new.request_hash is distinct from old.request_hash
     or new.request_text is distinct from old.request_text then
    raise exception 'campaign launch snapshot is immutable' using errcode = '42501';
  end if;
  return new;
end $$;

create trigger campaigns_snapshot_immutable before update on __OUTCOME_SCHEMA__.campaigns
  for each row execute function __OUTCOME_PRIVATE_SCHEMA__.campaign_snapshot_immutable();

commit;
