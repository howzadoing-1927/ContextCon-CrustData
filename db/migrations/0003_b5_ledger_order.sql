-- Outcome AI migration 0003_b5_ledger_order: decisions written in one transaction must keep their write order.
-- now() is constant per transaction; clock_timestamp() advances, so (created_at, id) stays chronological.

begin;

do $$
begin
  if (select column_default from information_schema.columns
      where table_schema = '__OUTCOME_SCHEMA__' and table_name = 'decisions' and column_name = 'created_at') like '%clock_timestamp%' then
    raise exception 'migration 0003_b5_ledger_order already applied';
  end if;
end $$;

alter table __OUTCOME_SCHEMA__.decisions alter column created_at set default clock_timestamp();

commit;
