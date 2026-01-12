with all_names as (
  select
    union_name
  from
    [f7].f7
  union all
  select
    participant
  from
    [nlrb].participant
  where
    subtype = 'Union'
  union all
  select
    union_to_certify
  from
    [nlrb].election_result
  union all
  select
    labor_organization_1_name
  from
    [nlrb].election_mode
  union all
  select
    labor_organization_2_name
  from
    [nlrb].election_mode
  union all
  select
    labor_organization_3_name
  from
    [nlrb].election_mode
  union all
  select
    specific_subject_labor_orgs
  from
    [lm20].specific_activity
  union all
  select
    "Union"
  from
    [voluntary_recognitions].voluntary_recognitions
)
select
  distinct union_name
from
  all_names
where
  union_name is not null
  and union_name != ''