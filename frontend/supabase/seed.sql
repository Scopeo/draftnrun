-- Insert dummies organization
insert into public.organizations (id, created_at, name, billing_id)
select
  '00000000-0000-0000-0000-000000000000',
  now(),
  'DraftNRun-test-organization',
  '00000000-0000-0000-0000-000000000000'
where not exists (
  select 1 from public.organizations where id = '00000000-0000-0000-0000-000000000000'
);
insert into public.organizations (id, created_at, name, billing_id)
select
  '11111111-1111-1111-1111-111111111111',
  now(),
  'test2-organization',
  '11111111-1111-1111-1111-111111111111'
where not exists (
  select 1 from public.organizations where id = '11111111-1111-1111-1111-111111111111'
);
