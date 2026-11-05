-- Outcome AI migration 0001_b2_foundation (contract outcome.v1, planning baseline 1.0).
-- Exactly twelve application tables in the application schema, composite tenant foreign keys, append-only
-- ledger/evidence, nonrecursive membership helper, RLS (server writes only), private evidence bucket.
-- Template: __OUTCOME_SCHEMA__ (OUTCOME_DB_SCHEMA), __OUTCOME_PRIVATE_SCHEMA__ (<schema>_private, or
-- app_private for public) and __EVIDENCE_BUCKET__ (STORAGE_BUCKET). Apply with:
--   python -m services.core.migrate            (renders and applies; --print to only render)

begin;

do $$
begin
  if to_regclass('__OUTCOME_SCHEMA__.organizations') is not null then
    raise exception 'migration 0001_b2_foundation already applied (__OUTCOME_SCHEMA__.organizations exists)';
  end if;
end $$;

create schema if not exists __OUTCOME_SCHEMA__;
grant usage on schema __OUTCOME_SCHEMA__ to authenticated;

create schema if not exists __OUTCOME_PRIVATE_SCHEMA__;
revoke all on schema __OUTCOME_PRIVATE_SCHEMA__ from public;
grant usage on schema __OUTCOME_PRIVATE_SCHEMA__ to authenticated;

-- ---------------------------------------------------------------- helpers

create function __OUTCOME_PRIVATE_SCHEMA__.set_updated_at() returns trigger
language plpgsql set search_path = '' as $$
begin
  new.updated_at := now();
  return new;
end $$;

create function __OUTCOME_PRIVATE_SCHEMA__.try_uuid(value text) returns uuid
language plpgsql immutable set search_path = '' as $$
begin
  return value::uuid;
exception when others then
  return null;
end $$;

-- A tenant purge is the only path that may delete append-only rows; it is scoped to one organization
-- by a transaction-local setting that only trusted server/admin code sets.
create function __OUTCOME_PRIVATE_SCHEMA__.is_purging(org uuid) returns boolean
language sql stable set search_path = '' as $$
  select coalesce(current_setting('app.purge_tenant', true), '') = org::text;
$$;

-- ---------------------------------------------------------------- 1 organizations

create table __OUTCOME_SCHEMA__.organizations (
  id uuid primary key default gen_random_uuid(),
  name text not null check (length(name) between 1 and 200),
  website_url text,
  timezone text not null default 'UTC',
  approved_profile_json jsonb not null default '{}'::jsonb,
  profile_version integer not null default 0 check (profile_version >= 0),
  approved_at timestamptz,
  approved_by uuid references auth.users (id) on delete restrict,
  last_profile_approval_key text,
  last_profile_approval_hash text,
  policy_json jsonb not null default '{}'::jsonb,
  config_version integer not null default 0 check (config_version >= 0),
  runtime_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- ---------------------------------------------------------------- 2 memberships

create table __OUTCOME_SCHEMA__.memberships (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references __OUTCOME_SCHEMA__.organizations (id) on delete restrict,
  user_id uuid not null references auth.users (id) on delete restrict,
  role text not null check (role in ('owner', 'member')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (organization_id, id),
  unique (organization_id, user_id)
);
create index memberships_user_idx on __OUTCOME_SCHEMA__.memberships (user_id);

-- ---------------------------------------------------------------- 3 connections

create table __OUTCOME_SCHEMA__.connections (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references __OUTCOME_SCHEMA__.organizations (id) on delete restrict,
  provider text not null check (provider = 'google'),
  purpose text not null check (purpose in ('seller', 'buyer_test')),
  status text not null check (status in ('pending', 'connected', 'reauth_required', 'revoked')),
  account_email text,
  granted_scopes text[] not null default '{}',
  encrypted_tokens bytea,
  token_key_version integer,
  expires_at timestamptz,
  calendar_id text,
  oauth_state_hash text,
  oauth_expires_at timestamptz,
  oauth_initiator_user_id uuid references auth.users (id) on delete restrict,
  oauth_return_path text,
  connect_request_key text,
  connect_request_hash text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (organization_id, id),
  unique (organization_id, provider, purpose)
);

-- ---------------------------------------------------------------- 4 campaigns

create table __OUTCOME_SCHEMA__.campaigns (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references __OUTCOME_SCHEMA__.organizations (id) on delete restrict,
  request_key text not null check (length(request_key) between 1 and 128),
  request_hash text not null check (request_hash ~ '^[0-9a-f]{64}$'),
  request_text text not null check (length(request_text) between 1 and 4000),
  mode text not null check (mode = 'simulation'),
  buyer_test_email text not null,
  status text not null check (status in (
    'draft', 'running', 'waiting_reply', 'completed', 'no_match', 'needs_human', 'paused', 'stopped', 'failed')),
  stage text not null,
  version integer not null default 0 check (version >= 0),
  normalized_plan_json jsonb,
  profile_version integer not null check (profile_version >= 1),
  config_version integer not null check (config_version >= 1),
  limits_json jsonb not null,
  budget_json jsonb not null default '{}'::jsonb,
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (organization_id, id),
  unique (organization_id, request_key)
);
create index campaigns_org_status_idx on __OUTCOME_SCHEMA__.campaigns (organization_id, status);

-- ---------------------------------------------------------------- 5 prospects

create table __OUTCOME_SCHEMA__.prospects (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references __OUTCOME_SCHEMA__.organizations (id) on delete restrict,
  campaign_id uuid not null,
  canonical_company_ref text not null check (length(canonical_company_ref) > 0),
  canonical_person_ref text check (canonical_person_ref is null or length(canonical_person_ref) > 0),
  identity_json jsonb not null default '{}'::jsonb,
  fit_json jsonb not null default '{}'::jsonb,
  hypothesis_json jsonb not null default '[]'::jsonb,
  status text not null check (status in ('researching', 'qualified', 'rejected', 'needs_evidence')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (organization_id, id),
  foreign key (organization_id, campaign_id) references __OUTCOME_SCHEMA__.campaigns (organization_id, id) on delete restrict
);
create unique index prospects_identity_uniq on __OUTCOME_SCHEMA__.prospects
  (organization_id, campaign_id, canonical_company_ref, canonical_person_ref)
  where canonical_person_ref is not null;
create index prospects_org_campaign_status_idx on __OUTCOME_SCHEMA__.prospects (organization_id, campaign_id, status);

-- ---------------------------------------------------------------- 6 evidence (immutable)

create table __OUTCOME_SCHEMA__.evidence (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references __OUTCOME_SCHEMA__.organizations (id) on delete restrict,
  campaign_id uuid,
  prospect_id uuid,
  entity_kind text not null,
  entity_id uuid,
  source_kind text not null check (source_kind in (
    'crustdata', 'seller_website', 'operator', 'google_message', 'google_calendar', 'policy')),
  source_url text,
  provider_ref text,
  field_path text,
  excerpt text not null,
  retrieved_at timestamptz not null,
  source_as_of timestamptz,
  content_sha256 text not null check (content_sha256 ~ '^[0-9a-f]{64}$'),
  storage_path text,
  fact_status text not null check (fact_status in ('observed', 'operator_approved', 'hypothesis', 'conflicted')),
  metadata_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (organization_id, id),
  check (storage_path is null or storage_path like organization_id::text || '/%'),
  foreign key (organization_id, campaign_id) references __OUTCOME_SCHEMA__.campaigns (organization_id, id) on delete restrict,
  foreign key (organization_id, prospect_id) references __OUTCOME_SCHEMA__.prospects (organization_id, id) on delete restrict
);
create index evidence_org_campaign_prospect_idx on __OUTCOME_SCHEMA__.evidence (organization_id, campaign_id, prospect_id);

-- ---------------------------------------------------------------- 8 conversations (before decisions/tasks)

create table __OUTCOME_SCHEMA__.conversations (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references __OUTCOME_SCHEMA__.organizations (id) on delete restrict,
  campaign_id uuid not null,
  prospect_id uuid not null,
  connection_id uuid not null,
  buyer_test_email text not null,
  provider_thread_id text,
  state text not null check (state in (
    'researching', 'qualified', 'drafting', 'waiting_reply', 'evaluating_reply', 'offering_slots',
    'waiting_slot_acceptance', 'booking', 'booked', 'completed',
    'declined', 'suppressed', 'needs_human', 'send_unknown', 'stopped')),
  version integer not null default 0 check (version >= 0),
  last_inbound_at timestamptz,
  next_poll_at timestamptz,
  crm_json jsonb not null default '{}'::jsonb,
  handoff_json jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (organization_id, id),
  unique (organization_id, id, connection_id),
  unique (organization_id, campaign_id, prospect_id),
  foreign key (organization_id, campaign_id) references __OUTCOME_SCHEMA__.campaigns (organization_id, id) on delete restrict,
  foreign key (organization_id, prospect_id) references __OUTCOME_SCHEMA__.prospects (organization_id, id) on delete restrict,
  foreign key (organization_id, connection_id) references __OUTCOME_SCHEMA__.connections (organization_id, id) on delete restrict
);
create unique index conversations_thread_uniq on __OUTCOME_SCHEMA__.conversations (connection_id, provider_thread_id)
  where provider_thread_id is not null;

-- ---------------------------------------------------------------- 10 tasks

create table __OUTCOME_SCHEMA__.tasks (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references __OUTCOME_SCHEMA__.organizations (id) on delete restrict,
  campaign_id uuid not null,
  conversation_id uuid,
  kind text not null check (kind in (
    'normalize_mission', 'research', 'qualify_and_draft', 'send_email', 'poll_inbox', 'handle_reply',
    'check_slots', 'book_meeting', 'write_handoff', 'notify_owner', 'reconcile_action')),
  dedupe_key text not null check (length(dedupe_key) between 1 and 300),
  payload_json jsonb not null,
  status text not null check (status in ('ready', 'leased', 'succeeded', 'failed', 'cancelled')),
  run_after timestamptz not null default now(),
  attempt integer not null default 0 check (attempt >= 0),
  max_attempts integer not null default 3 check (max_attempts > 0),
  lease_owner text,
  lease_until timestamptz,
  lease_generation bigint not null default 0 check (lease_generation >= 0),
  last_error_json jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (organization_id, id),
  unique (organization_id, dedupe_key),
  check (status <> 'leased' or (lease_owner is not null and lease_until is not null)),
  foreign key (organization_id, campaign_id) references __OUTCOME_SCHEMA__.campaigns (organization_id, id) on delete restrict,
  foreign key (organization_id, conversation_id) references __OUTCOME_SCHEMA__.conversations (organization_id, id) on delete restrict
);
create index tasks_claim_idx on __OUTCOME_SCHEMA__.tasks (status, run_after, lease_until);

-- ---------------------------------------------------------------- 7 decisions (append-only ledger)

create table __OUTCOME_SCHEMA__.decisions (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references __OUTCOME_SCHEMA__.organizations (id) on delete restrict,
  campaign_id uuid not null,
  prospect_id uuid,
  conversation_id uuid,
  task_id uuid,
  kind text not null check (length(kind) between 1 and 100),
  status text not null check (status in ('accepted', 'rejected', 'blocked', 'resolved')),
  reason text not null,
  evidence_ids uuid[] not null default '{}',
  input_refs_json jsonb not null default '{}'::jsonb,
  model_metadata_json jsonb,
  policy_result_json jsonb not null,
  proposed_action_json jsonb,
  resolution_json jsonb,
  created_at timestamptz not null default now(),
  unique (organization_id, id),
  foreign key (organization_id, campaign_id) references __OUTCOME_SCHEMA__.campaigns (organization_id, id) on delete restrict,
  foreign key (organization_id, prospect_id) references __OUTCOME_SCHEMA__.prospects (organization_id, id) on delete restrict,
  foreign key (organization_id, conversation_id) references __OUTCOME_SCHEMA__.conversations (organization_id, id) on delete restrict,
  foreign key (organization_id, task_id) references __OUTCOME_SCHEMA__.tasks (organization_id, id) on delete restrict
);
create index decisions_org_campaign_created_idx on __OUTCOME_SCHEMA__.decisions (organization_id, campaign_id, created_at, id);

-- ---------------------------------------------------------------- 11 actions (durable outbox)

create table __OUTCOME_SCHEMA__.actions (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references __OUTCOME_SCHEMA__.organizations (id) on delete restrict,
  campaign_id uuid not null,
  conversation_id uuid,
  decision_id uuid not null,
  kind text not null check (kind in ('email_send', 'calendar_insert', 'owner_notify')),
  idempotency_key text not null check (length(idempotency_key) between 1 and 300),
  request_hash text not null check (request_hash ~ '^[0-9a-f]{64}$'),
  state text not null check (state in ('prepared', 'executing', 'succeeded', 'failed', 'unknown', 'cancelled')),
  payload_json jsonb not null,
  result_json jsonb,
  provider_ref text,
  attempt integer not null default 0 check (attempt >= 0),
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (organization_id, id),
  unique (organization_id, idempotency_key),
  foreign key (organization_id, campaign_id) references __OUTCOME_SCHEMA__.campaigns (organization_id, id) on delete restrict,
  foreign key (organization_id, conversation_id) references __OUTCOME_SCHEMA__.conversations (organization_id, id) on delete restrict,
  foreign key (organization_id, decision_id) references __OUTCOME_SCHEMA__.decisions (organization_id, id) on delete restrict
);
create index actions_org_state_idx on __OUTCOME_SCHEMA__.actions (organization_id, state);

-- ---------------------------------------------------------------- 9 messages

create table __OUTCOME_SCHEMA__.messages (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references __OUTCOME_SCHEMA__.organizations (id) on delete restrict,
  conversation_id uuid not null,
  connection_id uuid not null,
  action_id uuid,
  direction text not null check (direction in ('inbound', 'outbound')),
  provider_message_id text,
  rfc_message_id text,
  provider_thread_id text,
  in_reply_to text,
  from_email text not null,
  to_emails text[] not null,
  subject text not null default '',
  body_text text not null,
  body_sha256 text not null check (body_sha256 ~ '^[0-9a-f]{64}$'),
  received_at timestamptz,
  status text not null check (status in ('planned', 'sent', 'received', 'unknown')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (organization_id, id),
  unique (connection_id, provider_message_id),
  unique (organization_id, action_id),
  foreign key (organization_id, conversation_id, connection_id)
    references __OUTCOME_SCHEMA__.conversations (organization_id, id, connection_id) on delete restrict,
  foreign key (organization_id, connection_id) references __OUTCOME_SCHEMA__.connections (organization_id, id) on delete restrict,
  foreign key (organization_id, action_id) references __OUTCOME_SCHEMA__.actions (organization_id, id) on delete restrict
);
create index messages_conversation_received_idx on __OUTCOME_SCHEMA__.messages (conversation_id, received_at, id);

-- ---------------------------------------------------------------- 12 suppressions

create table __OUTCOME_SCHEMA__.suppressions (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references __OUTCOME_SCHEMA__.organizations (id) on delete restrict,
  identity_kind text not null check (identity_kind in ('email', 'company', 'person')),
  identity_value text not null check (length(identity_value) > 0),
  reason text not null,
  source_message_id uuid,
  created_by uuid references auth.users (id) on delete restrict,
  created_at timestamptz not null default now(),
  unique (organization_id, id),
  unique (organization_id, identity_kind, identity_value),
  foreign key (organization_id, source_message_id) references __OUTCOME_SCHEMA__.messages (organization_id, id) on delete restrict
);

-- ---------------------------------------------------------------- triggers

do $$
declare t text;
begin
  foreach t in array array['organizations', 'memberships', 'connections', 'campaigns', 'prospects',
                           'conversations', 'tasks', 'actions', 'messages']
  loop
    execute format(
      'create trigger %I before update on __OUTCOME_SCHEMA__.%I for each row execute function __OUTCOME_PRIVATE_SCHEMA__.set_updated_at()',
      t || '_set_updated_at', t);
  end loop;
end $$;

create function __OUTCOME_PRIVATE_SCHEMA__.decisions_append_only() returns trigger
language plpgsql set search_path = '' as $$
begin
  if tg_op = 'DELETE' then
    if __OUTCOME_PRIVATE_SCHEMA__.is_purging(old.organization_id) then
      return old;
    end if;
    raise exception 'decisions are append-only' using errcode = '42501';
  end if;
  if old.status = 'blocked' and new.status = 'resolved'
     and old.resolution_json is null and new.resolution_json is not null
     and (to_jsonb(new) - 'status' - 'resolution_json') = (to_jsonb(old) - 'status' - 'resolution_json') then
    return new;
  end if;
  raise exception 'decisions are append-only except one blocked->resolved resolution' using errcode = '42501';
end $$;

create trigger decisions_append_only before update or delete on __OUTCOME_SCHEMA__.decisions
  for each row execute function __OUTCOME_PRIVATE_SCHEMA__.decisions_append_only();

create function __OUTCOME_PRIVATE_SCHEMA__.evidence_immutable() returns trigger
language plpgsql set search_path = '' as $$
begin
  if tg_op = 'DELETE' and __OUTCOME_PRIVATE_SCHEMA__.is_purging(old.organization_id) then
    return old;
  end if;
  raise exception 'evidence is immutable' using errcode = '42501';
end $$;

create trigger evidence_immutable before update or delete on __OUTCOME_SCHEMA__.evidence
  for each row execute function __OUTCOME_PRIVATE_SCHEMA__.evidence_immutable();

-- ---------------------------------------------------------------- membership helper (nonrecursive)

-- SECURITY DEFINER runs as the migration owner (table owner), so reading memberships here does not
-- re-enter memberships RLS. Fixed empty search_path; schema not exposed through the Data API.
create function __OUTCOME_PRIVATE_SCHEMA__.is_member(org uuid, min_role text default 'member') returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (
    select 1
    from __OUTCOME_SCHEMA__.memberships m
    where m.organization_id = org
      and m.user_id = (select auth.uid())
      and (min_role = 'member' or m.role = 'owner')
  );
$$;
revoke all on function __OUTCOME_PRIVATE_SCHEMA__.is_member(uuid, text) from public;
grant execute on function __OUTCOME_PRIVATE_SCHEMA__.is_member(uuid, text) to authenticated;
revoke all on function __OUTCOME_PRIVATE_SCHEMA__.try_uuid(text) from public;
grant execute on function __OUTCOME_PRIVATE_SCHEMA__.try_uuid(text) to authenticated;

-- ---------------------------------------------------------------- RLS and grants

do $$
declare t text;
begin
  foreach t in array array['organizations', 'memberships', 'connections', 'campaigns', 'prospects', 'evidence',
                           'decisions', 'conversations', 'messages', 'tasks', 'actions', 'suppressions']
  loop
    execute format('alter table __OUTCOME_SCHEMA__.%I enable row level security', t);
    execute format('revoke all on table __OUTCOME_SCHEMA__.%I from anon, authenticated', t);
  end loop;
end $$;

-- Browser reads only through FastAPI in P0; these SELECT policies exist so direct-client access is
-- tenant-scoped rather than open. No client write grants anywhere. connections/tasks/actions: no access.
grant select (id, name, website_url, timezone, approved_profile_json, profile_version, approved_at,
              config_version, created_at, updated_at)
  on __OUTCOME_SCHEMA__.organizations to authenticated;
grant select on __OUTCOME_SCHEMA__.memberships, __OUTCOME_SCHEMA__.campaigns, __OUTCOME_SCHEMA__.prospects, __OUTCOME_SCHEMA__.evidence, __OUTCOME_SCHEMA__.decisions,
                __OUTCOME_SCHEMA__.conversations, __OUTCOME_SCHEMA__.messages, __OUTCOME_SCHEMA__.suppressions
  to authenticated;

create policy organizations_member_read on __OUTCOME_SCHEMA__.organizations
  for select to authenticated using (__OUTCOME_PRIVATE_SCHEMA__.is_member(id));
create policy memberships_member_read on __OUTCOME_SCHEMA__.memberships
  for select to authenticated using (user_id = (select auth.uid()) or __OUTCOME_PRIVATE_SCHEMA__.is_member(organization_id));

do $$
declare t text;
begin
  foreach t in array array['campaigns', 'prospects', 'evidence', 'decisions', 'conversations', 'messages',
                           'suppressions']
  loop
    execute format(
      'create policy %I on __OUTCOME_SCHEMA__.%I for select to authenticated using (__OUTCOME_PRIVATE_SCHEMA__.is_member(organization_id))',
      t || '_member_read', t);
  end loop;
end $$;

-- ---------------------------------------------------------------- private evidence storage

insert into storage.buckets (id, name, public)
values ('__EVIDENCE_BUCKET__', '__EVIDENCE_BUCKET__', false)
on conflict (id) do update set public = false;

drop policy if exists "__EVIDENCE_BUCKET__ member read" on storage.objects;
create policy "__EVIDENCE_BUCKET__ member read" on storage.objects
  for select to authenticated
  using (
    bucket_id = '__EVIDENCE_BUCKET__'
    and __OUTCOME_PRIVATE_SCHEMA__.is_member(__OUTCOME_PRIVATE_SCHEMA__.try_uuid((storage.foldername(name))[1]))
  );

commit;
